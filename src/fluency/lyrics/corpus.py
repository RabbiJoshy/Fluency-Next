"""Plan an exact multi-source Lyrics corpus without executing song pipelines."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import re
from typing import Any, Callable

from fluency.core.artifacts import artifact_directory, store_artifact_bytes, verify_artifact
from fluency.core.hashing import file_content_id
from fluency.core.workspace import Workspace
from fluency.lyrics.ingest import ingest_legacy_genius_song
from fluency.core.io import atomic_write


PLAN_VERSION = "lyrics-corpus-plan/v1"
INGEST_REPORT_VERSION = "lyrics-corpus-ingest-report/v1"
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


def _load_planned_artifact(
    workspace: Workspace,
    artifact_id: str,
    *,
    expected_schema: str,
    expected_type: type,
) -> tuple[Any, Any, Path]:
    try:
        metadata = verify_artifact(workspace, artifact_id)
    except ValueError as error:
        raise LyricsCorpusPlanError(f"planned artifact is unavailable or corrupt: {artifact_id}") from error
    if metadata.schema != expected_schema:
        raise LyricsCorpusPlanError(
            f"planned artifact {artifact_id} has schema {metadata.schema!r}; "
            f"expected {expected_schema!r}"
        )
    payload = artifact_directory(workspace, artifact_id) / metadata.filename
    try:
        value = json.loads(payload.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LyricsCorpusPlanError(f"planned artifact is not valid JSON: {artifact_id}") from error
    if not isinstance(value, expected_type):
        raise LyricsCorpusPlanError(f"planned artifact has the wrong top-level shape: {artifact_id}")
    return metadata, value, payload


def _require_completed_planned_run(
    workspace: Workspace,
    *,
    language: str,
    run_id: str,
    artist_slug: str,
    artist_name: str,
    source_record_id: str,
    source_snapshot_id: str,
    translation_snapshot_id: str | None,
) -> bool:
    run_directory = workspace.root / "runs" / language / "lyrics" / run_id
    if not run_directory.exists():
        return False
    run_manifest_path = run_directory / "manifest.json"
    output = run_directory / "stages/01_source_ingest/output"
    stage_manifest_path = output / "manifest.json"
    report_path = output / "report.json"
    try:
        run_manifest = json.loads(run_manifest_path.read_text(encoding="utf-8"))
        stage_manifest = json.loads(stage_manifest_path.read_text(encoding="utf-8"))
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LyricsCorpusPlanError(
            f"planned run exists but is incomplete or invalid: {run_id}"
        ) from error
    expected_artist = {"id": artist_slug, "name": artist_name}
    if (
        not isinstance(run_manifest, dict)
        or run_manifest.get("run_id") != run_id
        or run_manifest.get("language") != language
        or run_manifest.get("mode") != "lyrics"
        or run_manifest.get("artist") != expected_artist
        or not isinstance(stage_manifest, dict)
        or stage_manifest.get("status") != "complete"
        or stage_manifest.get("run_id") != run_id
        or not isinstance(report, dict)
        or report.get("source_record_id") != source_record_id
        or report.get("language") != language
        or report.get("source_snapshot_content_id") != source_snapshot_id
        or report.get("translation_snapshot_content_id") != translation_snapshot_id
    ):
        raise LyricsCorpusPlanError(f"existing run conflicts with the pinned corpus plan: {run_id}")
    outputs = stage_manifest.get("outputs")
    if not isinstance(outputs, dict):
        raise LyricsCorpusPlanError(f"existing run has no verifiable output ledger: {run_id}")
    for filename, expected_content_id in outputs.items():
        if not isinstance(filename, str) or Path(filename).name != filename or not isinstance(expected_content_id, str):
            raise LyricsCorpusPlanError(f"existing run has an invalid output ledger: {run_id}")
        path = output / filename
        if not path.is_file() or file_content_id(path) != expected_content_id:
            raise LyricsCorpusPlanError(f"existing run output is missing or corrupt: {run_id}/{filename}")
    stage_reference = run_manifest.get("stages", {}).get("source_ingest", {})
    if (
        stage_reference.get("path") != "stages/01_source_ingest/output"
        or stage_reference.get("manifest_content_id") != file_content_id(stage_manifest_path)
    ):
        raise LyricsCorpusPlanError(f"existing run stage reference is invalid: {run_id}")
    return True


def ingest_lyrics_corpus_plan(
    workspace: Workspace,
    *,
    plan_path: Path,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Materialize every planned song as a resumable immutable source-ingest run."""

    plan_path = plan_path.expanduser().resolve()
    plan_root = (workspace.root / "raw/lyrics/corpus-plans").resolve()
    try:
        plan_path.relative_to(plan_root)
    except ValueError as error:
        raise LyricsCorpusPlanError("corpus ingest accepts only plans pinned inside this workspace") from error
    manifest = _object(plan_path)
    if manifest.get("plan_version") != PLAN_VERSION or manifest.get("status") != "planned_sources_only":
        raise LyricsCorpusPlanError("unsupported or already-mutated Lyrics corpus plan")
    plan_id = manifest.get("plan_id")
    language = manifest.get("language")
    sources = manifest.get("included_sources")
    if (
        not isinstance(plan_id, str)
        or SAFE_ID.fullmatch(plan_id) is None
        or not isinstance(language, str)
        or not language
        or not isinstance(sources, list)
    ):
        raise LyricsCorpusPlanError("corpus plan identity or sources are invalid")

    source_cache: dict[str, tuple[Any, list[Any], Path]] = {}
    translation_cache: dict[str, tuple[Any, dict[str, Any], Path]] = {}
    planned = sum(
        len(source.get("songs", []))
        for source in sources
        if isinstance(source, dict) and isinstance(source.get("songs"), list)
    )
    created = skipped = completed = 0
    artist_counts: dict[str, dict[str, int]] = {}
    for source in sources:
        if not isinstance(source, dict):
            raise LyricsCorpusPlanError("corpus plan contains an invalid artist source")
        artist_slug = source.get("artist_slug")
        artist_name = source.get("artist_name")
        songs = source.get("songs")
        if (
            not isinstance(artist_slug, str)
            or SAFE_ID.fullmatch(artist_slug) is None
            or not isinstance(artist_name, str)
            or not artist_name
            or not isinstance(songs, list)
        ):
            raise LyricsCorpusPlanError("corpus plan contains an invalid artist source identity")
        translation = source.get("translation_source")
        translation_id = None
        prepared_translation = None
        if translation is not None:
            if not isinstance(translation, dict) or not isinstance(translation.get("snapshot_content_id"), str):
                raise LyricsCorpusPlanError(f"invalid translation snapshot for {artist_slug}")
            translation_id = translation["snapshot_content_id"]
            if translation_id not in translation_cache:
                translation_cache[translation_id] = _load_planned_artifact(
                    workspace, translation_id,
                    expected_schema="legacy-aligned-translations/v1", expected_type=dict,
                )
            prepared_translation = translation_cache[translation_id]
        counts = artist_counts.setdefault(artist_slug, {"planned": len(songs), "created": 0, "skipped": 0})
        for song in songs:
            if not isinstance(song, dict):
                raise LyricsCorpusPlanError(f"invalid planned song for {artist_slug}")
            source_record_id = song.get("source_record_id")
            source_id = song.get("source_snapshot_content_id")
            run_id = song.get("planned_run_id")
            if not all(isinstance(value, str) and value for value in (source_record_id, source_id, run_id)):
                raise LyricsCorpusPlanError(f"incomplete planned song identity for {artist_slug}")
            if SAFE_ID.fullmatch(run_id) is None:
                raise LyricsCorpusPlanError(f"unsafe planned run ID: {run_id!r}")
            if source_id not in source_cache:
                source_cache[source_id] = _load_planned_artifact(
                    workspace, source_id,
                    expected_schema="legacy-genius-batch/v1", expected_type=list,
                )
            source_metadata, source_records, source_payload = source_cache[source_id]
            if _require_completed_planned_run(
                workspace, language=language, run_id=run_id,
                artist_slug=artist_slug, artist_name=artist_name,
                source_record_id=source_record_id, source_snapshot_id=source_id,
                translation_snapshot_id=translation_id,
            ):
                skipped += 1
                counts["skipped"] += 1
                action = "skipped"
            else:
                translation_metadata = translation_records = None
                if prepared_translation is not None:
                    translation_metadata, translation_records, _ = prepared_translation
                ingest_legacy_genius_song(
                    workspace,
                    source_batch=source_payload,
                    source_record_id=source_record_id,
                    snapshot_id=f"{plan_id}:{artist_slug}",
                    run_id=run_id,
                    language=language,
                    artist_id=artist_slug,
                    artist_name=artist_name,
                    _source_artifact=source_metadata,
                    _source_records=source_records,
                    _translation_artifact=translation_metadata,
                    _translation_records=translation_records,
                )
                created += 1
                counts["created"] += 1
                action = "created"
            completed += 1
            if progress is not None:
                progress({
                    "completed": completed, "planned": planned, "action": action,
                    "artist_slug": artist_slug, "source_record_id": source_record_id,
                    "run_id": run_id,
                })

    completion = {
        "report_version": INGEST_REPORT_VERSION,
        "status": "complete",
        "plan_id": plan_id,
        "plan_content_id": file_content_id(plan_path),
        "language": language,
        "song_run_count": planned,
        "artist_source_count": len(sources),
    }
    report_path = workspace.root / "runs" / language / "lyrics-corpora" / plan_id / "ingest-report.json"
    if report_path.exists():
        if _object(report_path) != completion:
            raise LyricsCorpusPlanError("existing corpus completion report conflicts with this plan")
    else:
        atomic_write(report_path, completion, workspace.root / ".fluency/temporary")
    return {
        **completion,
        "created_this_invocation": created,
        "skipped_this_invocation": skipped,
        "artist_counts": artist_counts,
        "report_path": str(report_path),
    }
