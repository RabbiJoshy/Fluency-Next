"""Migrate only the approved retained Spanish source and paid-compute assets."""

from __future__ import annotations

import ast
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
from typing import Any

from fluency.core.hashing import file_content_id
from fluency.core.workspace import Workspace
from fluency.languages.spanish.surfaces import normalize_surface
from fluency.release.io import json_bytes


MANIFEST_VERSION = "retained-source-artifact/v1"
AUDIT_COMMIT = "23f1ad4387feb4a599815eaa6846e1201b5f402a"
MIGRATION_ID = "spanish-retained-assets-v1"
EXPECTED_SURFACE_COUNT = 9_999
EXPECTED_SENTENCE_COUNT = 42_650
EXPECTED_CANDIDATE_SURFACE_COUNT = 9_954
EXPECTED_EMBEDDING_COUNT = 276_724
EXPECTED_EMBEDDING_DIMENSIONS = 3_072
EXPECTED_HASHES = {
    "inventory/word_inventory.json": "946ff114dbffb8cea116daec9ef70877571edad5d0e5e642964123d59b25eeb9",
    "inventory/word_inventory.json.meta.json": "d9ee28849bb4f35bedd153242bffa8f2b5760176941c9313e99c1769a47b6fb3",
    "sentences/sentence_bank.jsonl": "f6c6c5903270d62575276d0ef21a2e00f7611c9f6762ed7875097ffea47527fe",
    "sentences/word_candidates.json": "13a65ae1466c30e17be8a6f76b4dd1c4629fec962f9dd93c6b05e3971641dee9",
    "sentences/harvest_manifest.json": "ccbffd5e58e4e1c2ae7c47c3393e0e4a915795ea62e96de357edeea9ec4e27dd",
    "embeddings/vec.npy": "0614e32740bbf8d0850d6769547056684ba894d39583fb621fcc1d0fc7917c99",
    "embeddings/vec_index.json": "3f654402a27e0b3cb347fc0737a65fd5a395daf1d8a081bda81be711732ad2cb",
    "embeddings/manifest.json": "ddb1046f8e447a6fc427a0871f2b18458ab86d63a5889bfd78a9678d80dd20ff",
}


class SpanishAssetMigrationError(ValueError):
    """Raised when retained sources differ from the audited migration ledger."""


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _clone_or_copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["cp", "-c", "-p", str(source), str(target)],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        shutil.copy2(source, target)


def _copy_verified(source: Path, target: Path, expected_digest: str) -> dict[str, Any]:
    if not source.is_file():
        raise SpanishAssetMigrationError(f"retained source file does not exist: {source}")
    _clone_or_copy(source, target)
    content_id = file_content_id(target)
    if content_id != f"sha256:{expected_digest}":
        raise SpanishAssetMigrationError(f"retained source hash changed: {source}")
    return {"path": target.name, "sha256": expected_digest, "bytes": target.stat().st_size}


def _npy_shape(path: Path) -> tuple[tuple[int, ...], str, bool]:
    with path.open("rb") as stream:
        if stream.read(6) != b"\x93NUMPY":
            raise SpanishAssetMigrationError("Gemini vector payload is not an NPY file")
        major, _minor = stream.read(2)
        length_size = 2 if major == 1 else 4
        header_length = struct.unpack("<H" if length_size == 2 else "<I", stream.read(length_size))[0]
        try:
            header = ast.literal_eval(stream.read(header_length).decode("latin1").strip())
        except (SyntaxError, ValueError) as error:
            raise SpanishAssetMigrationError("Gemini NPY header is invalid") from error
    shape = header.get("shape")
    dtype = header.get("descr")
    fortran = header.get("fortran_order")
    if not isinstance(shape, tuple) or not all(isinstance(value, int) for value in shape):
        raise SpanishAssetMigrationError("Gemini NPY shape is invalid")
    if not isinstance(dtype, str) or not isinstance(fortran, bool):
        raise SpanishAssetMigrationError("Gemini NPY dtype/order is invalid")
    return shape, dtype, fortran


def _content_record(directory: Path, filename: str, row_count: int | None = None) -> dict[str, Any]:
    path = directory / filename
    record: dict[str, Any] = {
        "path": filename,
        "sha256": file_content_id(path).removeprefix("sha256:"),
        "bytes": path.stat().st_size,
    }
    if row_count is not None:
        record["record_count"] = row_count
    return record


def migrate_spanish_retained_assets(
    workspace: Workspace,
    *,
    source_repository: Path,
    recovered_at: datetime | None = None,
) -> dict[str, Path]:
    """Copy verified inventory, sentences, and Gemini cache; never assignments."""

    source_root = source_repository.expanduser().resolve()
    source_base = source_root / "Data" / "Spanish" / "layers"
    targets = {
        "inventory": workspace.root / "raw/inventories/es/recovered/fluency-2026-07-28-surface-ranking-v1",
        "sentences": workspace.root / "raw/sentence_banks/es/opensubtitles/2026-08-15-harvest-v1",
        "embeddings": workspace.root / "raw/embeddings/google-gemini/gemini-embedding-001/recovered-2026-08-20-v1",
    }
    existing = [str(path) for path in targets.values() if path.exists()]
    if existing:
        raise SpanishAssetMigrationError(
            "retained asset target already exists; refusing overwrite: " + ", ".join(existing)
        )
    source_files = {
        "inventory": {
            "word_inventory.json": source_base / "word_inventory.json",
            "word_inventory.json.meta.json": source_base / "word_inventory.json.meta.json",
        },
        "sentences": {
            "sentence_bank.jsonl": source_base / "subtitles/sentence_bank.jsonl",
            "word_candidates.json": source_base / "subtitles/word_candidates.json",
            "harvest_manifest.json": source_base / "subtitles/harvest_manifest.json",
        },
        "embeddings": {
            "vec.npy": source_base / "sense_vectors/vec.npy",
            "vec_index.json": source_base / "sense_vectors/vec_index.json",
            "manifest.json": source_base / "sense_vectors/manifest.json",
        },
    }
    recovered_at = datetime.now(UTC) if recovered_at is None else recovered_at
    temporary_root = workspace.root / ".fluency" / "temporary"
    temporary = Path(tempfile.mkdtemp(prefix="spanish-retained-", dir=temporary_root))
    promoted: list[Path] = []
    try:
        for family, files in source_files.items():
            family_root = temporary / family
            for filename, source in files.items():
                _copy_verified(
                    source,
                    family_root / filename,
                    EXPECTED_HASHES[f"{family}/{filename}"],
                )

        inventory_root = temporary / "inventory"
        inventory = json.loads((inventory_root / "word_inventory.json").read_text(encoding="utf-8"))
        if not isinstance(inventory, list):
            raise SpanishAssetMigrationError("surface inventory must be an array")
        surfaces = [normalize_surface(str(row.get("word", ""))) for row in inventory if isinstance(row, dict)]
        if len(surfaces) != EXPECTED_SURFACE_COUNT or len(set(surfaces)) != EXPECTED_SURFACE_COUNT:
            raise SpanishAssetMigrationError(
                f"surface inventory is not exactly {EXPECTED_SURFACE_COUNT:,} unique surfaces"
            )
        inventory_manifest = {
            "schema_version": MANIFEST_VERSION,
            "artifact_kind": "surface_inventory_source",
            "language": "es",
            "mode_scope": "speech",
            "provider": "recovered-fluency",
            "snapshot_id": "fluency-2026-07-28-surface-ranking-v1",
            "provenance_status": "reconstructed",
            "recovered_at": _timestamp(recovered_at),
            "recovered_from": {"repository": str(source_root), "audit_commit": AUDIT_COMMIT},
            "content_files": [
                _content_record(inventory_root, "word_inventory.json", len(inventory)),
                _content_record(inventory_root, "word_inventory.json.meta.json", 1),
            ],
            "coverage": {"surface_records": len(inventory)},
            "frequency_measure": "recovered_corpus_count_upstream_unknown",
            "notes": [
                "List order is retained as the migration ranking.",
                "known_lemmas are lookup evidence only and are never imported into card identity.",
            ],
        }
        (inventory_root / "artifact.json").write_bytes(json_bytes(inventory_manifest))

        sentence_root = temporary / "sentences"
        sentence_ids: set[str] = set()
        with (sentence_root / "sentence_bank.jsonl").open(encoding="utf-8") as stream:
            for line in stream:
                record = json.loads(line)
                sentence_id = record.get("id") if isinstance(record, dict) else None
                if not isinstance(sentence_id, str) or not sentence_id or sentence_id in sentence_ids:
                    raise SpanishAssetMigrationError("sentence bank contains an invalid/duplicate ID")
                sentence_ids.add(sentence_id)
        candidates = json.loads((sentence_root / "word_candidates.json").read_text(encoding="utf-8"))
        if not isinstance(candidates, dict):
            raise SpanishAssetMigrationError("sentence candidate map must be an object")
        if len(sentence_ids) != EXPECTED_SENTENCE_COUNT:
            raise SpanishAssetMigrationError("sentence bank record count differs from the audit")
        if len(candidates) != EXPECTED_CANDIDATE_SURFACE_COUNT:
            raise SpanishAssetMigrationError("sentence candidate coverage differs from the audit")
        candidate_links = 0
        for surface, pools in candidates.items():
            if not isinstance(surface, str) or not isinstance(pools, dict):
                raise SpanishAssetMigrationError("sentence candidate map contains an invalid surface")
            for pool in ("clean", "held"):
                ids = pools.get(pool)
                if not isinstance(ids, list) or not all(value in sentence_ids for value in ids):
                    raise SpanishAssetMigrationError("sentence candidate map references an unknown sentence")
                candidate_links += len(ids)
        sentence_manifest = {
            "schema_version": MANIFEST_VERSION,
            "artifact_kind": "sentence_bank",
            "language": "es",
            "mode_scope": "speech",
            "provider": "opensubtitles",
            "snapshot_id": "2026-08-15-harvest-v1",
            "provenance_status": "reconstructed",
            "license": "unknown",
            "source_uris": [],
            "recovered_at": _timestamp(recovered_at),
            "recovered_from": {"repository": str(source_root), "audit_commit": AUDIT_COMMIT},
            "content_files": [
                _content_record(sentence_root, "sentence_bank.jsonl", len(sentence_ids)),
                _content_record(sentence_root, "word_candidates.json", len(candidates)),
                _content_record(sentence_root, "harvest_manifest.json", 1),
            ],
            "coverage": {
                "sentence_records": len(sentence_ids),
                "surface_candidate_records": len(candidates),
                "candidate_links": candidate_links,
            },
            "notes": ["clean/held labels are retained evidence, not final selection decisions."],
        }
        (sentence_root / "artifact.json").write_bytes(json_bytes(sentence_manifest))

        embedding_root = temporary / "embeddings"
        index = json.loads((embedding_root / "vec_index.json").read_text(encoding="utf-8"))
        if not isinstance(index, dict) or len(index) != EXPECTED_EMBEDDING_COUNT:
            raise SpanishAssetMigrationError(
                f"Gemini exact-text index does not contain {EXPECTED_EMBEDDING_COUNT:,} rows"
            )
        positions = set(index.values())
        if positions != set(range(len(index))):
            raise SpanishAssetMigrationError("Gemini exact-text index positions are not contiguous")
        shape, dtype, fortran = _npy_shape(embedding_root / "vec.npy")
        if (
            shape != (EXPECTED_EMBEDDING_COUNT, EXPECTED_EMBEDDING_DIMENSIONS)
            or dtype not in {"<f2", "|f2"}
            or fortran
        ):
            raise SpanishAssetMigrationError("Gemini vector matrix shape/dtype/order changed")
        embedding_manifest = {
            "schema_version": MANIFEST_VERSION,
            "artifact_kind": "embedding_cache",
            "language": None,
            "mode_scope": None,
            "provider": "google-gemini",
            "snapshot_id": "gemini-embedding-001-recovered-2026-08-20-v1",
            "provenance_status": "reconstructed",
            "recovered_at": _timestamp(recovered_at),
            "recovered_from": {"repository": str(source_root), "audit_commit": AUDIT_COMMIT},
            "content_files": [
                _content_record(embedding_root, "vec.npy", shape[0]),
                _content_record(embedding_root, "vec_index.json", len(index)),
                _content_record(embedding_root, "manifest.json", 1),
            ],
            "model": {
                "name": "gemini-embedding-001",
                "task_type": "SEMANTIC_SIMILARITY",
                "dimensions": shape[1],
                "dtype": "float16",
                "normalized": True,
            },
            "coverage": {"exact_text_vectors": len(index)},
            "notes": [
                "The historical inner manifest count is stale; shape and exact-text index agree at 276,724.",
                "Cache misses are normal and changed text never reuses an old vector.",
            ],
        }
        (embedding_root / "artifact.json").write_bytes(json_bytes(embedding_manifest))

        for family, target in targets.items():
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(temporary / family, target)
            promoted.append(target)
    except Exception:
        for path in reversed(promoted):
            shutil.rmtree(path, ignore_errors=True)
        raise
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return targets
