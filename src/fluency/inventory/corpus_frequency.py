"""Compile and read immutable surface-frequency snapshots from text corpora."""

from __future__ import annotations

from collections import Counter
import csv
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Callable
import unicodedata

from fluency.core.hashing import canonical_content_id, file_content_id
from fluency.core.workspace import Workspace
from fluency.languages.surfaces import normalizer_for_language
from fluency.release.io import json_bytes


ADAPTER_ID = "corpus-surface-frequency/v1"
SNAPSHOT_VERSION = "corpus-surface-frequency-snapshot/v1"
FREQUENCIES_FILE = "surface-frequencies.tsv"
MANIFEST_FILE = "manifest.json"
_SNAPSHOT_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


class CorpusFrequencyError(ValueError):
    """Raised when a corpus frequency snapshot is ambiguous or malformed."""


@dataclass(frozen=True, slots=True)
class CorpusFrequencySnapshot:
    frequencies: dict[str, float]
    counts: dict[str, int]
    manifest: dict[str, Any]
    frequencies_content_id: str


ProgressCallback = Callable[[dict[str, int]], None]


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _load_tokenization_policy(repository_root: Path, language: str) -> dict[str, Any]:
    path = repository_root / "config" / "languages" / language / "tokenization.json"
    try:
        policy = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise CorpusFrequencyError(f"language tokenization policy does not exist: {path}") from error
    except json.JSONDecodeError as error:
        raise CorpusFrequencyError(f"language tokenization policy is invalid JSON: {path}") from error
    if not isinstance(policy, dict) or policy.get("schema_version") != f"{language}-tokenization/v1":
        raise CorpusFrequencyError("unsupported language tokenization policy")
    selection = policy.get("surface_frequency")
    if not isinstance(selection, dict):
        raise CorpusFrequencyError("language policy has no surface-frequency configuration")
    pattern = selection.get("token_pattern")
    forbidden = selection.get("reject_line_if_contains")
    if not isinstance(pattern, str) or not pattern:
        raise CorpusFrequencyError("surface-frequency token pattern is required")
    try:
        re.compile(pattern, re.UNICODE)
    except re.error as error:
        raise CorpusFrequencyError("surface-frequency token pattern is invalid") from error
    if not isinstance(forbidden, list) or not all(
        isinstance(value, str) and value for value in forbidden
    ):
        raise CorpusFrequencyError("surface-frequency forbidden substrings are invalid")
    if selection.get("frequency_measure") != "surface_token_occurrences_per_million":
        raise CorpusFrequencyError("unsupported corpus frequency measure")
    return policy


def compile_corpus_frequency_snapshot(
    repository_root: Path,
    workspace: Workspace,
    *,
    language: str,
    corpus_path: Path,
    snapshot_id: str,
    provider: str,
    created_at: datetime | None = None,
    progress_callback: ProgressCallback | None = None,
) -> Path:
    """Count one pinned corpus once and publish a reusable immutable snapshot."""

    if _SNAPSHOT_ID.fullmatch(snapshot_id) is None:
        raise CorpusFrequencyError("snapshot_id must be a safe, explicit identifier")
    if not provider or not re.fullmatch(r"[a-z][a-z0-9_-]*", provider):
        raise CorpusFrequencyError("provider must be a safe, explicit identifier")
    source = corpus_path.expanduser().resolve()
    if not _inside(source, workspace.root / "raw"):
        raise CorpusFrequencyError(
            f"corpus must be pinned inside the workspace raw directory: {source}"
        )
    if not source.is_file():
        raise CorpusFrequencyError(f"corpus snapshot does not exist: {source}")
    initial_source_stat = source.stat()
    output = workspace.root / "raw" / "frequency" / language / provider / snapshot_id
    if output.exists():
        raise CorpusFrequencyError(
            "frequency snapshot already exists; use a new snapshot ID instead of overwriting it"
        )

    policy = _load_tokenization_policy(repository_root, language)
    frequency_policy = policy["surface_frequency"]
    token_pattern = re.compile(frequency_policy["token_pattern"], re.UNICODE)
    forbidden = tuple(value.casefold() for value in frequency_policy["reject_line_if_contains"])
    normalize = normalizer_for_language(language)

    @lru_cache(maxsize=65_536)
    def normalize_cached(value: str) -> str:
        return normalize(value)

    counts: Counter[str] = Counter()
    digest = hashlib.sha256()
    source_bytes = 0
    source_lines = 0
    accepted_lines = 0
    rejected_lines = 0
    total_tokens = 0
    with source.open("rb") as stream:
        for raw_line in stream:
            source_lines += 1
            source_bytes += len(raw_line)
            digest.update(raw_line)
            try:
                line = raw_line.decode("utf-8")
            except UnicodeDecodeError as error:
                raise CorpusFrequencyError(
                    f"corpus is not valid UTF-8 at line {source_lines}"
                ) from error
            if source_lines == 1:
                line = line.removeprefix("\ufeff")
            line = unicodedata.normalize("NFC", line)
            folded = line.casefold()
            if any(marker in folded for marker in forbidden):
                rejected_lines += 1
            else:
                accepted_lines += 1
                tokens = token_pattern.findall(line)
                total_tokens += len(tokens)
                counts.update(normalize_cached(token) for token in tokens)
            if progress_callback is not None and source_lines % 1_000_000 == 0:
                progress_callback(
                    {
                        "source_lines": source_lines,
                        "source_bytes": source_bytes,
                        "total_tokens": total_tokens,
                        "unique_surfaces": len(counts),
                    }
                )
    if not counts or total_tokens == 0:
        raise CorpusFrequencyError("corpus yielded no usable surface tokens")
    final_source_stat = source.stat()
    if (
        final_source_stat.st_size != initial_source_stat.st_size
        or final_source_stat.st_mtime_ns != initial_source_stat.st_mtime_ns
    ):
        raise CorpusFrequencyError("corpus changed while its frequency snapshot was compiling")

    created_at = datetime.now(UTC) if created_at is None else created_at
    relative_source = str(source.relative_to(workspace.root))
    implementation_content_id = canonical_content_id(
        {
            "compiler": file_content_id(Path(__file__).resolve()),
            "tokenization_policy": policy,
        }
    )
    temporary_root = workspace.root / ".fluency" / "temporary"
    temporary = Path(tempfile.mkdtemp(prefix="corpus-frequency-", dir=temporary_root))
    try:
        frequencies_path = temporary / FREQUENCIES_FILE
        with frequencies_path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
            writer.writerow(("surface", "count", "frequency_per_million"))
            for surface, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
                writer.writerow((surface, count, f"{count * 1_000_000 / total_tokens:.12f}"))
        frequencies_content_id = file_content_id(frequencies_path)
        manifest = {
            "snapshot_version": SNAPSHOT_VERSION,
            "snapshot_id": snapshot_id,
            "language": language,
            "provider": provider,
            "source_adapter": ADAPTER_ID,
            "frequency_measure": frequency_policy["frequency_measure"],
            "created_at": created_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "provenance_status": "reconstructed",
            "license": "unknown",
            "source_uris": [],
            "source_path": relative_source,
            "source_content_id": f"sha256:{digest.hexdigest()}",
            "source_bytes": source_bytes,
            "source_modified_at": datetime.fromtimestamp(
                initial_source_stat.st_mtime, tz=UTC
            ).isoformat().replace("+00:00", "Z"),
            "source_lines": source_lines,
            "accepted_lines": accepted_lines,
            "rejected_lines": rejected_lines,
            "total_tokens": total_tokens,
            "unique_surfaces": len(counts),
            "normalization_policy": policy["schema_version"],
            "normalization_config_id": canonical_content_id(policy),
            "implementation_content_id": implementation_content_id,
            "frequencies_file": FREQUENCIES_FILE,
            "frequencies_content_id": frequencies_content_id,
        }
        (temporary / MANIFEST_FILE).write_bytes(json_bytes(manifest))
        output.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return output


def load_corpus_frequency_snapshot(
    path: Path,
    *,
    expected_language: str,
    expected_snapshot_id: str,
) -> CorpusFrequencySnapshot:
    """Validate and read a compiled corpus-frequency snapshot."""

    try:
        manifest = json.loads((path / MANIFEST_FILE).read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise CorpusFrequencyError(f"frequency snapshot manifest does not exist: {path}") from error
    except json.JSONDecodeError as error:
        raise CorpusFrequencyError("frequency snapshot manifest is invalid JSON") from error
    if not isinstance(manifest, dict) or manifest.get("snapshot_version") != SNAPSHOT_VERSION:
        raise CorpusFrequencyError("unsupported corpus frequency snapshot")
    if manifest.get("language") != expected_language:
        raise CorpusFrequencyError("frequency snapshot language does not match the run")
    if manifest.get("snapshot_id") != expected_snapshot_id:
        raise CorpusFrequencyError("frequency snapshot ID does not match the requested snapshot")
    if manifest.get("source_adapter") != ADAPTER_ID:
        raise CorpusFrequencyError("frequency snapshot adapter does not match the run")
    if manifest.get("frequencies_file") != FREQUENCIES_FILE:
        raise CorpusFrequencyError("frequency snapshot file identity is invalid")
    frequencies_path = path / FREQUENCIES_FILE
    frequencies_content_id = file_content_id(frequencies_path)
    if frequencies_content_id != manifest.get("frequencies_content_id"):
        raise CorpusFrequencyError("frequency snapshot content hash does not match its manifest")

    frequencies: dict[str, float] = {}
    counts: dict[str, int] = {}
    with frequencies_path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        if set(reader.fieldnames or ()) != {"surface", "count", "frequency_per_million"}:
            raise CorpusFrequencyError("frequency snapshot table has an unexpected schema")
        previous: tuple[int, str] | None = None
        for row in reader:
            surface = row["surface"]
            try:
                count = int(row["count"])
                frequency = float(row["frequency_per_million"])
            except (TypeError, ValueError) as error:
                raise CorpusFrequencyError("frequency snapshot contains an invalid value") from error
            if not surface or count <= 0 or frequency <= 0 or surface in counts:
                raise CorpusFrequencyError("frequency snapshot contains an invalid surface row")
            order = (-count, surface)
            if previous is not None and order < previous:
                raise CorpusFrequencyError("frequency snapshot rows are not deterministically ranked")
            previous = order
            counts[surface] = count
            frequencies[surface] = frequency
    if len(counts) != manifest.get("unique_surfaces"):
        raise CorpusFrequencyError("frequency snapshot surface count does not match its manifest")
    return CorpusFrequencySnapshot(
        frequencies=frequencies,
        counts=counts,
        manifest=manifest,
        frequencies_content_id=frequencies_content_id,
    )
