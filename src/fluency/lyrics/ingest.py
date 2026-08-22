"""Immutable source-ingestion stage for language-agnostic lyrics records."""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any

from fluency.core.artifacts import store_artifact_bytes
from fluency.core.hashing import canonical_content_id, file_content_id
from fluency.core.workspace import Workspace
from fluency.lyrics.lineage import build_lineage_event
from fluency.lyrics.records import (
    ALIGNMENT_VERSION,
    LINE_VERSION,
    RAW_SONG_VERSION,
    build_alignment_id,
    build_line_id,
    build_section_id,
    build_song_id,
    validate_line_alignment,
    validate_lyrics_line,
    validate_raw_song,
)
from fluency.release.io import atomic_write, json_bytes


STAGE_VERSION = "lyrics-source-ingest/v1"
ADAPTER_ID = "legacy-genius-batch/v1"
ALIGNMENT_ADAPTER_ID = "legacy-position-alignment/v1"
SECTION_PATTERN = re.compile(r"^\[(?P<label>[^\]]+)\]\s*$")
SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class LyricsIngestError(ValueError):
    """Raised when an immutable lyrics source stage cannot be constructed."""


def _load_json(path: Path, expected: type | tuple[type, ...]) -> Any:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LyricsIngestError(f"source JSON is unavailable or invalid: {path}") from error
    if not isinstance(value, expected):
        raise LyricsIngestError(f"source JSON has the wrong top-level shape: {path}")
    return value


def _find_song(batch: list[Any], source_record_id: str) -> dict[str, Any]:
    matches = [item for item in batch if isinstance(item, dict) and str(item.get("id")) == source_record_id]
    if len(matches) != 1:
        raise LyricsIngestError(
            f"expected exactly one source song {source_record_id}; found {len(matches)}"
        )
    song = matches[0]
    for field in ("title", "artist", "lyrics"):
        if not isinstance(song.get(field), str) or not song[field].strip():
            raise LyricsIngestError(f"source song {field} is missing")
    return song


def _clean_provider_prefix(raw_text: str) -> tuple[str, int]:
    marker = raw_text.find("[")
    if marker < 0:
        return raw_text, 0
    return raw_text[marker:], marker


def _section_details(label: str) -> tuple[str, list[str]]:
    kind, separator, performers = label.partition(":")
    if not separator:
        return label.strip(), []
    names = [name.strip() for name in re.split(r"\s*(?:&|,| y | and | et | e )\s*", performers) if name.strip()]
    return kind.strip(), names


def _extract_lines(*, song_id: str, language: str, raw_text: str) -> list[dict[str, Any]]:
    document, prefix_offset = _clean_provider_prefix(raw_text)
    section_id: str | None = None
    section_label: str | None = None
    section_kind: str | None = None
    performers: list[str] = []
    section_ordinal = -1
    lyric_position = 0
    offset = prefix_offset
    records: list[dict[str, Any]] = []
    for source_line in document.splitlines(keepends=True):
        text = source_line.rstrip("\r\n")
        stripped = text.strip()
        start = offset + (len(text) - len(text.lstrip()))
        end = start + len(stripped)
        offset += len(source_line)
        if not stripped:
            continue
        section_match = SECTION_PATTERN.fullmatch(stripped)
        if section_match:
            section_ordinal += 1
            section_label = section_match.group("label").strip()
            section_kind, performers = _section_details(section_label)
            section_id = build_section_id(song_id=song_id, ordinal=section_ordinal, label=section_label)
            continue
        line_id = build_line_id(song_id=song_id, source_position=lyric_position, text=stripped)
        records.append(
            {
                "record_version": LINE_VERSION,
                "line_id": line_id,
                "song_id": song_id,
                "language": language,
                "source_position": lyric_position,
                "source_span": [start, end],
                "text": stripped,
                "section": {
                    "section_id": section_id,
                    "ordinal": section_ordinal if section_id else None,
                    "label": section_label,
                    "kind_label": section_kind,
                    "performers": performers,
                },
            }
        )
        lyric_position += 1
    return records


def _legacy_translations(
    *,
    translations: dict[str, Any],
    source_record_id: str,
    lines: list[dict[str, Any]],
    target_language: str,
    snapshot_content_id: str,
) -> list[dict[str, Any]]:
    song = translations.get("songs", {}).get(source_record_id, {})
    candidates: dict[str, deque[dict[str, str | None]]] = defaultdict(deque)
    for pair in song.get("lines", []) if isinstance(song, dict) else []:
        if isinstance(pair, dict) and isinstance(pair.get("spanish"), str) and isinstance(pair.get("english"), str):
            candidates[pair["spanish"]].append(
                {"text": pair["english"], "provider": pair.get("source")}
            )
    adapter = ALIGNMENT_ADAPTER_ID
    method = "legacy ordered exact-text join"
    if not candidates and "songs" not in translations:
        adapter = "legacy-example-translation-map/v1"
        method = "legacy exact-text map lookup"
        for source_text, value in translations.items():
            if not isinstance(source_text, str) or not isinstance(value, dict):
                continue
            target_text = value.get("english")
            if isinstance(target_text, str) and target_text.strip():
                candidates[source_text].append(
                    {"text": target_text, "provider": value.get("source")}
                )
    alignments: list[dict[str, Any]] = []
    line_ids = {line["line_id"] for line in lines}
    for line in lines:
        matches = candidates.get(line["text"])
        if not matches:
            continue
        match = matches.popleft()
        text = str(match["text"])
        record = {
            "record_version": ALIGNMENT_VERSION,
            "alignment_id": build_alignment_id(
                line_id=line["line_id"],
                language=target_language,
                text=text,
                snapshot_content_id=snapshot_content_id,
            ),
            "line_id": line["line_id"],
            "target": {"language": target_language, "text": text},
            "source": {
                "adapter": adapter,
                "snapshot_content_id": snapshot_content_id,
                "method": method,
                "provider": match.get("provider"),
            },
            "confidence": None,
            "review_status": "unreviewed_legacy_materialization",
        }
        validate_line_alignment(record, line_ids=line_ids)
        alignments.append(record)
    return alignments


def _jsonl_bytes(records: list[dict[str, Any]]) -> bytes:
    return b"".join(json_bytes(record) for record in records)


def ingest_legacy_genius_song(
    workspace: Workspace,
    *,
    source_batch: Path,
    source_record_id: str,
    snapshot_id: str,
    run_id: str,
    language: str,
    artist_id: str,
    artist_name: str,
    translations_path: Path | None = None,
    translation_language: str = "en",
    started_at: datetime | None = None,
) -> Path:
    """Ingest one legacy source song without carrying forward downstream decisions."""

    if SAFE_RUN_ID.fullmatch(run_id) is None:
        raise LyricsIngestError("run_id must be a safe explicit identifier")
    if not all(value.strip() for value in (snapshot_id, language, artist_id, artist_name)):
        raise LyricsIngestError("snapshot, language, and artist identities must be explicit")
    started_at = datetime.now(UTC) if started_at is None else started_at.astimezone(UTC)
    source_batch = source_batch.expanduser().resolve()
    source_bytes = source_batch.read_bytes()
    raw_artifact = store_artifact_bytes(
        workspace,
        source_bytes,
        filename="legacy-genius-batch.json",
        media_type="application/json",
        schema="legacy-genius-batch/v1",
        created_by_stage=STAGE_VERSION,
    )
    batch = json.loads(source_bytes)
    if not isinstance(batch, list):
        raise LyricsIngestError("legacy Genius batch must contain a list")
    legacy = _find_song(batch, source_record_id)
    song_id = build_song_id(
        adapter=ADAPTER_ID,
        snapshot_content_id=raw_artifact.artifact_id,
        source_record_id=source_record_id,
    )
    raw_song = {
        "record_version": RAW_SONG_VERSION,
        "song_id": song_id,
        "language": language,
        "title": legacy["title"].strip(),
        "artist": {"id": artist_id, "name": artist_name},
        "raw_text": legacy["lyrics"],
        "source": {
            "name": "Genius",
            "adapter": ADAPTER_ID,
            "snapshot_id": snapshot_id,
            "snapshot_content_id": raw_artifact.artifact_id,
            "source_record_id": source_record_id,
            "license": "legacy source terms not recorded; review before redistribution",
            "attribution": legacy.get("artist") or artist_name,
            "url": legacy.get("url"),
            "provider_payload": {"legacy_batch_file": source_batch.name},
        },
    }
    validate_raw_song(raw_song)
    lines = _extract_lines(song_id=song_id, language=language, raw_text=raw_song["raw_text"])
    for line in lines:
        validate_lyrics_line(line, song_id=song_id, language=language)

    translation_artifact = None
    alignments: list[dict[str, Any]] = []
    if translations_path is not None:
        translation_bytes = translations_path.expanduser().resolve().read_bytes()
        translation_artifact = store_artifact_bytes(
            workspace,
            translation_bytes,
            filename="legacy-aligned-translations.json",
            media_type="application/json",
            schema="legacy-aligned-translations/v1",
            created_by_stage=STAGE_VERSION,
        )
        translations = json.loads(translation_bytes)
        if not isinstance(translations, dict):
            raise LyricsIngestError("legacy aligned translations must contain an object")
        alignments = _legacy_translations(
            translations=translations,
            source_record_id=source_record_id,
            lines=lines,
            target_language=translation_language,
            snapshot_content_id=translation_artifact.artifact_id,
        )

    source_ref = {"kind": "source_snapshot", "id": raw_artifact.artifact_id, "revision": None, "content_id": raw_artifact.artifact_id}
    events = [
        build_lineage_event(
            subject={"kind": "song", "id": song_id},
            phase="acquire",
            operation="preserve",
            run_id=run_id,
            method_id=ADAPTER_ID,
            input_refs=[source_ref],
            output_refs=[{"kind": "raw_song", "id": song_id, "revision": None, "content_id": None}],
            evidence_kind="direct",
        )
    ]
    events.extend(
        build_lineage_event(
            subject={"kind": "segment", "id": line["line_id"]},
            phase="extract",
            operation="preserve",
            run_id=run_id,
            method_id=ADAPTER_ID,
            input_refs=[{"kind": "raw_song", "id": song_id, "revision": None, "content_id": None}],
            output_refs=[{"kind": "lyrics_line", "id": line["line_id"], "revision": None, "content_id": None}],
            evidence_kind="direct",
            decision={"source_span": line["source_span"], "source_position": line["source_position"]},
        )
        for line in lines
    )
    events.extend(
        build_lineage_event(
            subject={"kind": "segment", "id": alignment["line_id"]},
            phase="align",
            operation="align",
            run_id=run_id,
            method_id=alignment["source"]["adapter"],
            input_refs=[
                {"kind": "lyrics_line", "id": alignment["line_id"], "revision": None, "content_id": None},
                {"kind": "translation_snapshot", "id": translation_artifact.artifact_id, "revision": None, "content_id": translation_artifact.artifact_id},
            ],
            output_refs=[{"kind": "line_alignment", "id": alignment["alignment_id"], "revision": None, "content_id": None}],
            evidence_kind="materialized_snapshot",
            decision={"target_language": alignment["target"]["language"], "review_status": alignment["review_status"]},
        )
        for alignment in alignments
    )

    run_directory = workspace.root / "runs" / language / "lyrics" / run_id
    output_directory = run_directory / "stages" / "01_source_ingest" / "output"
    if output_directory.exists():
        raise LyricsIngestError("source-ingest output already exists; use a new run instead of overwriting it")
    temporary_root = workspace.root / ".fluency" / "temporary"
    temporary = Path(tempfile.mkdtemp(prefix="lyrics-source-", dir=temporary_root))
    try:
        (temporary / "song.json").write_bytes(json_bytes(raw_song))
        (temporary / "lines.jsonl").write_bytes(_jsonl_bytes(lines))
        (temporary / "alignments.jsonl").write_bytes(_jsonl_bytes(alignments))
        (temporary / "lineage.jsonl").write_bytes(_jsonl_bytes(events))
        report = {
            "report_version": "lyrics-source-report/v1",
            "song_id": song_id,
            "source_record_id": source_record_id,
            "language": language,
            "line_count": len(lines),
            "alignment_count": len(alignments),
            "unaligned_line_count": len(lines) - len(alignments),
            "lineage_event_count": len(events),
            "source_snapshot_content_id": raw_artifact.artifact_id,
            "translation_snapshot_content_id": translation_artifact.artifact_id if translation_artifact else None,
        }
        (temporary / "report.json").write_bytes(json_bytes(report))
        outputs = {
            name: file_content_id(temporary / name)
            for name in ("song.json", "lines.jsonl", "alignments.jsonl", "lineage.jsonl", "report.json")
        }
        manifest = {
            "manifest_version": STAGE_VERSION,
            "run_id": run_id,
            "stage": "source_ingest",
            "status": "complete",
            "started_at": started_at.isoformat().replace("+00:00", "Z"),
            "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "adapter": ADAPTER_ID,
            "implementation_content_id": canonical_content_id(
                {
                    "ingest": file_content_id(Path(__file__)),
                    "records": file_content_id(Path(__file__).with_name("records.py")),
                    "lineage": file_content_id(Path(__file__).with_name("lineage.py")),
                }
            ),
            "inputs": {
                "source_snapshot": raw_artifact.artifact_id,
                **({"translation_snapshot": translation_artifact.artifact_id} if translation_artifact else {}),
            },
            "outputs": outputs,
        }
        (temporary / "manifest.json").write_bytes(json_bytes(manifest))
        output_directory.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temporary, output_directory)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)

    run_manifest_path = run_directory / "manifest.json"
    run_manifest = {
        "manifest_version": "lyrics-run/v1",
        "run_id": run_id,
        "language": language,
        "mode": "lyrics",
        "artist": {"id": artist_id, "name": artist_name},
        "status": "running",
        "stages": {
            "source_ingest": {
                "path": "stages/01_source_ingest/output",
                "manifest_content_id": file_content_id(output_directory / "manifest.json"),
            }
        },
    }
    if run_manifest_path.exists():
        existing = _load_json(run_manifest_path, dict)
        if existing != run_manifest:
            raise LyricsIngestError("existing lyrics run manifest conflicts with this source stage")
    else:
        atomic_write(run_manifest_path, run_manifest, temporary_root)
    return output_directory
