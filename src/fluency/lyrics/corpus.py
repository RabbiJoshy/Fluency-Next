"""Plan an exact multi-source Lyrics corpus without executing song pipelines."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import re
from typing import Any

from fluency.core.artifacts import store_artifact_bytes
from fluency.core.hashing import file_content_id
from fluency.core.workspace import Workspace
from fluency.release.io import atomic_write, json_bytes


PLAN_VERSION = "lyrics-corpus-plan/v1"
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
ADAPTERS = {
    "legacy_genius_batch_directory/v1": "batches",
    "legacy_genius_song_directory/v1": "songs",
}


class LyricsCorpusPlanError(ValueError):
    pass


def _object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LyricsCorpusPlanError(f"corpus config is unavailable or invalid: {path}") from error
    if not isinstance(value, dict):
        raise LyricsCorpusPlanError("corpus config must contain an object")
    return value


def _song_rows(path: Path, adapter: str) -> list[dict[str, Any]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LyricsCorpusPlanError(f"invalid source JSON: {path}") from error
    if not isinstance(value, list):
        raise LyricsCorpusPlanError(f"source file must contain a song list: {path}")
    if adapter == "legacy_genius_song_directory/v1" and len(value) != 1:
        raise LyricsCorpusPlanError(f"one-song adapter requires exactly one record: {path}")
    rows: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            raise LyricsCorpusPlanError(f"source song must be an object: {path}")
        for field in ("id", "title", "artist", "lyrics"):
            if item.get(field) is None or not str(item[field]).strip():
                raise LyricsCorpusPlanError(f"source song is missing {field}: {path}")
        rows.append(item)
    return rows


def build_lyrics_corpus_plan(
    workspace: Workspace,
    *,
    config_path: Path,
    source_repository: Path,
    plan_id: str,
) -> Path:
    """Pin exact source files and emit a no-execution, per-song run ledger."""

    if SAFE_ID.fullmatch(plan_id) is None:
        raise LyricsCorpusPlanError("unsafe corpus plan ID")
    config_path = config_path.expanduser().resolve()
    source_repository = source_repository.expanduser().resolve()
    config = _object(config_path)
    if config.get("plan_version") != PLAN_VERSION:
        raise LyricsCorpusPlanError("unsupported Lyrics corpus plan config")
    language = config.get("language")
    if not isinstance(language, str) or not language:
        raise LyricsCorpusPlanError("corpus language must be explicit")
    destination = workspace.root / "raw/lyrics/corpus-plans" / plan_id / "manifest.json"
    if destination.exists():
        raise LyricsCorpusPlanError("corpus plan already exists; choose a new plan ID")

    included: list[dict[str, Any]] = []
    scoped_ids: set[tuple[str, str]] = set()
    global_sources: dict[str, list[str]] = {}
    total_files = total_songs = 0
    for source in config.get("included_sources", []):
        if not isinstance(source, dict):
            raise LyricsCorpusPlanError("included source must be an object")
        slug = source.get("artist_slug")
        name = source.get("artist_name")
        adapter = source.get("adapter")
        relative = source.get("relative_path")
        if not all(isinstance(value, str) and value for value in (slug, name, adapter, relative)):
            raise LyricsCorpusPlanError("included source identity is incomplete")
        if SAFE_ID.fullmatch(slug) is None or adapter not in ADAPTERS:
            raise LyricsCorpusPlanError(f"unsupported source identity or adapter: {slug}")
        directory = (source_repository / relative).resolve()
        try:
            directory.relative_to(source_repository)
        except ValueError as error:
            raise LyricsCorpusPlanError("source path escapes the source repository") from error
        file_pattern = source.get("file_pattern", "*.json")
        if not isinstance(file_pattern, str) or not file_pattern or Path(file_pattern).name != file_pattern:
            raise LyricsCorpusPlanError(f"unsafe source file pattern: {file_pattern!r}")
        files = sorted(directory.glob(file_pattern))
        if not files:
            raise LyricsCorpusPlanError(f"source contains no JSON files: {directory}")
        translation_record = None
        translation_relative = source.get("translation_relative_path")
        if translation_relative is not None:
            if not isinstance(translation_relative, str) or not translation_relative:
                raise LyricsCorpusPlanError(f"invalid translation path for {slug}")
            translation_path = (source_repository / translation_relative).resolve()
            try:
                translation_path.relative_to(source_repository)
            except ValueError as error:
                raise LyricsCorpusPlanError("translation path escapes the source repository") from error
            translation_value = _object(translation_path)
            translation_bytes = translation_path.read_bytes()
            translation_artifact = store_artifact_bytes(
                workspace, translation_bytes, filename="legacy-aligned-translations.json",
                media_type="application/json", schema="legacy-aligned-translations/v1",
                created_by_stage=PLAN_VERSION,
            )
            songs_with_translations = translation_value.get("songs")
            coverage_count = len(songs_with_translations) if isinstance(songs_with_translations, dict) else len(translation_value)
            translation_record = {
                "relative_path": translation_path.relative_to(source_repository).as_posix(),
                "snapshot_content_id": translation_artifact.artifact_id,
                "bytes": len(translation_bytes),
                "songs_with_materialized_translations": coverage_count,
            }
        file_records: list[dict[str, Any]] = []
        song_records: list[dict[str, Any]] = []
        for path in files:
            rows = _song_rows(path, adapter)
            # Use the same canonical object metadata as the one-song ingest.
            # The plan may encounter a batch already pinned by an audit run;
            # identical bytes must resolve to that object, not acquire a second
            # schema merely because this higher-level ledger discovered it.
            artifact = store_artifact_bytes(
                workspace, path.read_bytes(), filename="legacy-genius-batch.json",
                media_type="application/json", schema="legacy-genius-batch/v1",
                created_by_stage=PLAN_VERSION,
            )
            file_records.append({
                "relative_path": path.relative_to(source_repository).as_posix(),
                "snapshot_content_id": artifact.artifact_id,
                "bytes": path.stat().st_size,
                "song_count": len(rows),
            })
            for row in rows:
                source_id = str(row["id"])
                key = (slug, source_id)
                if key in scoped_ids:
                    raise LyricsCorpusPlanError(f"duplicate source song within {slug}: {source_id}")
                scoped_ids.add(key)
                global_sources.setdefault(source_id, []).append(slug)
                song_records.append({
                    "source_record_id": source_id,
                    "title": str(row["title"]).strip(),
                    "credited_artist": str(row["artist"]).strip(),
                    "source_snapshot_content_id": artifact.artifact_id,
                    "planned_run_id": f"{slug}-{source_id}-{plan_id}",
                })
        included.append({
            "artist_slug": slug, "artist_name": name, "adapter": adapter,
            "file_pattern": file_pattern,
            "source_file_count": len(file_records), "song_count": len(song_records),
            "files": file_records, "translation_source": translation_record,
            "songs": song_records,
        })
        total_files += len(file_records)
        total_songs += len(song_records)

    excluded = config.get("excluded_sources", [])
    if not isinstance(excluded, list) or any(not isinstance(item, dict) for item in excluded):
        raise LyricsCorpusPlanError("excluded_sources must be a list of explicit records")
    collisions = [
        {"source_record_id": source_id, "artist_slugs": sorted(slugs)}
        for source_id, slugs in global_sources.items() if len(set(slugs)) > 1
    ]
    manifest = {
        "plan_version": PLAN_VERSION,
        "plan_id": plan_id,
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "language": language,
        "status": "planned_sources_only",
        "source_config_content_id": file_content_id(config_path),
        "source_repository": str(source_repository),
        "cross_source_duplicate_policy": config.get("cross_source_duplicate_policy"),
        "included_sources": included,
        "excluded_sources": excluded,
        "cross_source_collisions": collisions,
        "totals": {
            "included_artist_sources": len(included),
            "source_files": total_files,
            "songs": total_songs,
            "cross_source_collisions": len(collisions),
        },
        "executed_stages": [],
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(destination, manifest, workspace.root / ".fluency/temporary")
    return destination
