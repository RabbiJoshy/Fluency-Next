"""Resumable processing executor for an exact Lyrics corpus plan."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from fluency.core.artifacts import store_artifact_bytes, verify_artifact
from fluency.core.hashing import file_content_id
from fluency.core.workspace import Workspace
from fluency.lyrics.corpus import (
    LyricsCorpusPlanError,
    PLAN_VERSION,
    SAFE_ID,
    _require_completed_planned_run,
)
from fluency.lyrics.process import (
    PROCESSING_INPUT_FILENAMES,
    PROCESSING_INPUT_SPECS,
    PROCESSING_TEXT_INPUTS,
    PreparedLyricsProcessing,
    prepare_lyrics_processing,
    process_lyrics_run,
    processing_implementation_content_id,
)
from fluency.core.io import atomic_write


PROFILE_VERSION = "lyrics-corpus-processing-profile/v1"
PROFILE_SOURCE_VERSION = "lyrics-corpus-processing-profile-source/v1"
REPORT_VERSION = "lyrics-corpus-processing-report/v1"


class LyricsCorpusProcessingError(ValueError):
    """Raised when bulk processing cannot prove an exact resumable boundary."""


def _object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LyricsCorpusProcessingError(f"{label} is unavailable or invalid: {path}") from error
    if not isinstance(value, dict):
        raise LyricsCorpusProcessingError(f"{label} must contain an object")
    return value


def build_lyrics_corpus_processing_profile(
    workspace: Workspace,
    *,
    plan_path: Path,
    config_path: Path,
    source_repository: Path,
    profile_id: str,
) -> Path:
    """Pin artist-specific processing inputs and publish one immutable profile."""

    if SAFE_ID.fullmatch(profile_id) is None:
        raise LyricsCorpusProcessingError("unsafe processing profile ID")
    plan_path = plan_path.expanduser().resolve()
    config_path = config_path.expanduser().resolve()
    source_repository = source_repository.expanduser().resolve()
    plan = _object(plan_path, "Lyrics corpus plan")
    config = _object(config_path, "Lyrics processing profile source")
    if plan.get("plan_version") != PLAN_VERSION or plan.get("status") != "planned_sources_only":
        raise LyricsCorpusProcessingError("unsupported Lyrics corpus plan")
    if config.get("profile_source_version") != PROFILE_SOURCE_VERSION:
        raise LyricsCorpusProcessingError("unsupported Lyrics processing profile source")
    language = plan.get("language")
    if config.get("language") != language or not isinstance(language, str):
        raise LyricsCorpusProcessingError("processing profile source language does not match the plan")
    specs = PROCESSING_INPUT_SPECS.get(language)
    if specs is None:
        raise LyricsCorpusProcessingError(f"no processing input contract is installed for {language!r}")
    shared = config.get("shared_inputs")
    artist_sources = config.get("artist_sources")
    if not isinstance(shared, dict) or not isinstance(artist_sources, list):
        raise LyricsCorpusProcessingError("processing profile source is incomplete")
    if any(not isinstance(name, str) or not isinstance(value, str) for name, value in shared.items()):
        raise LyricsCorpusProcessingError("shared processing inputs must map names to artifact IDs")
    for name, artifact_id in shared.items():
        if name not in specs:
            raise LyricsCorpusProcessingError(f"unknown shared processing input: {name}")
        try:
            metadata = verify_artifact(workspace, artifact_id)
        except ValueError as error:
            raise LyricsCorpusProcessingError(f"shared input is unavailable or corrupt: {name}") from error
        if metadata.schema != specs[name]:
            raise LyricsCorpusProcessingError(f"shared input schema does not match: {name}")

    plan_sources = plan.get("included_sources")
    if not isinstance(plan_sources, list):
        raise LyricsCorpusProcessingError("corpus plan contains no artist sources")
    plan_slugs = [
        source.get("artist_slug") for source in plan_sources if isinstance(source, dict)
    ]
    if (
        len(plan_slugs) != len(plan_sources)
        or any(not isinstance(slug, str) or not slug for slug in plan_slugs)
        or len(set(plan_slugs)) != len(plan_slugs)
    ):
        raise LyricsCorpusProcessingError("corpus plan has invalid artist source identities")
    expected_slugs = set(plan_slugs)
    artist_inputs: dict[str, dict[str, str]] = {}
    source_paths: dict[str, dict[str, str]] = {}
    for source in artist_sources:
        if not isinstance(source, dict):
            raise LyricsCorpusProcessingError("artist processing source must be an object")
        slug = source.get("artist_slug")
        inputs = source.get("inputs")
        if not isinstance(slug, str) or slug not in expected_slugs or not isinstance(inputs, dict):
            raise LyricsCorpusProcessingError("artist processing source identity is invalid")
        if slug in artist_inputs:
            raise LyricsCorpusProcessingError(f"duplicate artist processing source: {slug}")
        pinned: dict[str, str] = {}
        recorded_paths: dict[str, str] = {}
        for name, relative in inputs.items():
            if name not in specs or not isinstance(relative, str) or not relative:
                raise LyricsCorpusProcessingError(f"invalid artist input for {slug}: {name}")
            path = (source_repository / relative).resolve()
            try:
                path.relative_to(source_repository)
            except ValueError as error:
                raise LyricsCorpusProcessingError("artist processing input escapes source repository") from error
            data = path.read_bytes()
            metadata = store_artifact_bytes(
                workspace,
                data,
                filename=PROCESSING_INPUT_FILENAMES[name],
                media_type="text/plain" if name in PROCESSING_TEXT_INPUTS else "application/json",
                schema=specs[name],
                created_by_stage=PROFILE_SOURCE_VERSION,
            )
            pinned[name] = metadata.artifact_id
            recorded_paths[name] = path.relative_to(source_repository).as_posix()
        artist_inputs[slug] = dict(sorted(pinned.items()))
        source_paths[slug] = dict(sorted(recorded_paths.items()))
    if set(artist_inputs) != expected_slugs:
        missing = sorted(str(slug) for slug in expected_slugs - artist_inputs.keys())
        unexpected = sorted(artist_inputs.keys() - expected_slugs)
        raise LyricsCorpusProcessingError(
            "artist processing sources do not match the corpus: "
            + f"missing={missing}, unexpected={unexpected}"
        )
    destination = workspace.root / "raw/lyrics/processing-profiles" / profile_id / "manifest.json"
    if destination.exists():
        raise LyricsCorpusProcessingError("processing profile already exists; choose a new profile ID")
    profile = {
        "profile_version": PROFILE_VERSION,
        "profile_id": profile_id,
        "language": language,
        "routing_mode": config.get("routing_mode"),
        "plan_id": plan.get("plan_id"),
        "plan_content_id": file_content_id(plan_path),
        "source_config_content_id": file_content_id(config_path),
        "source_repository": str(source_repository),
        "shared_inputs": dict(sorted(shared.items())),
        "artist_inputs": dict(sorted(artist_inputs.items())),
        "artist_source_paths": dict(sorted(source_paths.items())),
        "executed_stages": [],
    }
    atomic_write(destination, profile, workspace.root / ".fluency/temporary")
    return destination


def _verify_outputs(output: Path, stage_manifest: dict[str, Any], run_id: str) -> None:
    outputs = stage_manifest.get("outputs")
    if not isinstance(outputs, dict):
        raise LyricsCorpusProcessingError(f"processing run has no output ledger: {run_id}")
    for filename, expected_content_id in outputs.items():
        if (
            not isinstance(filename, str)
            or Path(filename).name != filename
            or not isinstance(expected_content_id, str)
        ):
            raise LyricsCorpusProcessingError(f"processing run has an invalid output ledger: {run_id}")
        path = output / filename
        if not path.is_file() or file_content_id(path) != expected_content_id:
            raise LyricsCorpusProcessingError(
                f"processing output is missing or corrupt: {run_id}/{filename}"
            )


def _require_completed_processing_run(
    workspace: Workspace,
    *,
    language: str,
    run_id: str,
    prepared: PreparedLyricsProcessing,
) -> bool:
    run_directory = workspace.root / "runs" / language / "lyrics" / run_id
    output = run_directory / "stages/02_process/output"
    if not output.exists():
        return False
    run_manifest_path = run_directory / "manifest.json"
    stage_manifest_path = output / "manifest.json"
    source_manifest_path = run_directory / "stages/01_source_ingest/output/manifest.json"
    try:
        run_manifest = _object(run_manifest_path, "Lyrics run manifest")
        stage_manifest = _object(stage_manifest_path, "processing stage manifest")
        source_manifest = _object(source_manifest_path, "source-ingest stage manifest")
        source_lines = source_manifest["outputs"]["lines.jsonl"]
    except (KeyError, TypeError) as error:
        raise LyricsCorpusProcessingError(f"processing run is structurally incomplete: {run_id}") from error
    expected_inputs = {
        **{name: metadata.artifact_id for name, metadata in prepared.pinned.items()},
        "source_lines": source_lines,
    }
    if (
        stage_manifest.get("manifest_version") != "lyrics-processing-stage/v2"
        or stage_manifest.get("run_id") != run_id
        or stage_manifest.get("stage") != "process"
        or stage_manifest.get("status") != "complete"
        or stage_manifest.get("inputs") != expected_inputs
        or stage_manifest.get("implementation_content_id")
        != processing_implementation_content_id(language)
    ):
        raise LyricsCorpusProcessingError(
            f"existing processing run conflicts with the selected profile: {run_id}"
        )
    _verify_outputs(output, stage_manifest, run_id)
    stage_reference = run_manifest.get("stages", {}).get("process", {})
    if (
        stage_reference.get("path") != "stages/02_process/output"
        or stage_reference.get("manifest_content_id") != file_content_id(stage_manifest_path)
    ):
        raise LyricsCorpusProcessingError(f"processing stage reference is invalid: {run_id}")
    return True


def process_lyrics_corpus_plan(
    workspace: Workspace,
    *,
    plan_path: Path,
    profile_path: Path,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Process every planned song with one exact, cached language profile."""

    plan_path = plan_path.expanduser().resolve()
    profile_path = profile_path.expanduser().resolve()
    plan_root = (workspace.root / "raw/lyrics/corpus-plans").resolve()
    profile_root = (workspace.root / "raw/lyrics/processing-profiles").resolve()
    try:
        plan_path.relative_to(plan_root)
    except ValueError as error:
        raise LyricsCorpusProcessingError(
            "corpus processing accepts only plans pinned inside this workspace"
        ) from error
    try:
        profile_path.relative_to(profile_root)
    except ValueError as error:
        raise LyricsCorpusProcessingError(
            "corpus processing accepts only profiles pinned inside this workspace"
        ) from error
    plan = _object(plan_path, "Lyrics corpus plan")
    profile = _object(profile_path, "Lyrics processing profile")
    if plan.get("plan_version") != PLAN_VERSION or plan.get("status") != "planned_sources_only":
        raise LyricsCorpusProcessingError("unsupported Lyrics corpus plan")
    if profile.get("profile_version") != PROFILE_VERSION:
        raise LyricsCorpusProcessingError("unsupported Lyrics processing profile")
    language = plan.get("language")
    if profile.get("language") != language or not isinstance(language, str):
        raise LyricsCorpusProcessingError("processing profile language does not match the corpus plan")
    if (
        profile.get("plan_id") != plan.get("plan_id")
        or profile.get("plan_content_id") != file_content_id(plan_path)
    ):
        raise LyricsCorpusProcessingError("processing profile is bound to a different corpus plan")
    profile_id = profile.get("profile_id")
    routing_mode = profile.get("routing_mode")
    shared_inputs = profile.get("shared_inputs")
    artist_inputs = profile.get("artist_inputs")
    if (
        not isinstance(profile_id, str)
        or SAFE_ID.fullmatch(profile_id) is None
        or not isinstance(routing_mode, str)
        or not isinstance(shared_inputs, dict)
        or not isinstance(artist_inputs, dict)
    ):
        raise LyricsCorpusProcessingError("processing profile is incomplete")
    sources = plan.get("included_sources")
    if not isinstance(sources, list):
        raise LyricsCorpusProcessingError("corpus plan contains no artist sources")
    slugs = [source.get("artist_slug") for source in sources if isinstance(source, dict)]
    if (
        len(slugs) != len(sources)
        or any(not isinstance(slug, str) for slug in slugs)
        or len(set(slugs)) != len(slugs)
        or set(artist_inputs) != set(slugs)
    ):
        raise LyricsCorpusProcessingError("processing profile artist inputs do not match the corpus")
    prepared_by_artist: dict[str, PreparedLyricsProcessing] = {}
    exact_inputs: dict[str, dict[str, str]] = {}
    for slug in slugs:
        scoped = artist_inputs[slug]
        if not isinstance(scoped, dict):
            raise LyricsCorpusProcessingError(f"artist processing inputs are invalid: {slug}")
        merged = {**shared_inputs, **scoped}
        if any(
            not isinstance(name, str) or not isinstance(value, str)
            for name, value in merged.items()
        ):
            raise LyricsCorpusProcessingError(
                f"processing inputs must map names to artifact IDs: {slug}"
            )
        prepared_by_artist[slug] = prepare_lyrics_processing(
            workspace,
            language=language,
            routing_mode=routing_mode,
            artifact_ids=merged,
        )
        exact_inputs[slug] = dict(sorted(merged.items()))
    songs = [
        (source, song)
        for source in sources
        if isinstance(source, dict)
        for song in source.get("songs", [])
        if isinstance(song, dict)
    ]
    if len(songs) != plan.get("totals", {}).get("songs"):
        raise LyricsCorpusProcessingError("corpus song ledger does not match its declared total")
    created = skipped = 0
    artist_counts: dict[str, dict[str, int]] = {}
    for index, (source, song) in enumerate(songs, start=1):
        artist_slug = source.get("artist_slug")
        artist_name = source.get("artist_name")
        source_record_id = song.get("source_record_id")
        source_snapshot_id = song.get("source_snapshot_content_id")
        run_id = song.get("planned_run_id")
        translation = source.get("translation_source")
        translation_id = (
            translation.get("snapshot_content_id") if isinstance(translation, dict) else None
        )
        if not all(
            isinstance(value, str) and value
            for value in (
                artist_slug, artist_name, source_record_id, source_snapshot_id, run_id,
            )
        ):
            raise LyricsCorpusProcessingError("corpus plan contains an incomplete song identity")
        try:
            source_complete = _require_completed_planned_run(
                workspace,
                language=language,
                run_id=run_id,
                artist_slug=artist_slug,
                artist_name=artist_name,
                source_record_id=source_record_id,
                source_snapshot_id=source_snapshot_id,
                translation_snapshot_id=translation_id,
            )
        except LyricsCorpusPlanError as error:
            raise LyricsCorpusProcessingError(str(error)) from error
        if not source_complete:
            raise LyricsCorpusProcessingError(f"source ingest has not completed: {run_id}")
        counts = artist_counts.setdefault(
            artist_slug, {"planned": 0, "created": 0, "skipped": 0}
        )
        counts["planned"] += 1
        prepared = prepared_by_artist[artist_slug]
        if _require_completed_processing_run(
            workspace, language=language, run_id=run_id, prepared=prepared
        ):
            skipped += 1
            counts["skipped"] += 1
            action = "skipped"
        else:
            process_lyrics_run(
                workspace,
                run_id=run_id,
                language=language,
                routing_mode=routing_mode,
                _prepared=prepared,
            )
            created += 1
            counts["created"] += 1
            action = "created"
        if progress is not None:
            progress({
                "completed": index,
                "planned": len(songs),
                "action": action,
                "artist_slug": artist_slug,
                "source_record_id": source_record_id,
                "run_id": run_id,
            })

    completion = {
        "report_version": REPORT_VERSION,
        "status": "complete",
        "plan_id": plan["plan_id"],
        "plan_content_id": file_content_id(plan_path),
        "profile_id": profile_id,
        "profile_content_id": file_content_id(profile_path),
        "language": language,
        "routing_mode": routing_mode,
        "processing_implementation_content_id": processing_implementation_content_id(language),
        "artist_input_artifact_ids": dict(sorted(exact_inputs.items())),
        "song_run_count": len(songs),
    }
    report_path = (
        workspace.root / "runs" / language / "lyrics-corpora" / plan["plan_id"]
        / "process-report.json"
    )
    if report_path.exists():
        if _object(report_path, "corpus processing completion report") != completion:
            raise LyricsCorpusProcessingError(
                "existing corpus processing report conflicts with this plan or profile"
            )
    else:
        atomic_write(report_path, completion, workspace.root / ".fluency/temporary")
    return {
        **completion,
        "created_this_invocation": created,
        "skipped_this_invocation": skipped,
        "artist_counts": artist_counts,
        "report_path": str(report_path),
    }
