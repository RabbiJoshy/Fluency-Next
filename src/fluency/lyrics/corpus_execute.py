"""Resumable full-corpus execution of the pinned placeholder Spanish WSD method."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any, Callable

from fluency.core.hashing import file_content_id
from fluency.core.workspace import Workspace
from fluency.lyrics.corpus import PLAN_VERSION
from fluency.lyrics.corpus_results import CATALOG_VERSION
from fluency.lyrics.wsd_execute import (
    METHOD_PROFILE,
    build_spanish_v5_runtime,
    execute_spanish_v5_lyrics,
    spanish_v5_required_texts,
)
from fluency.lyrics.wsd_results import BUNDLE_VERSION
from fluency.core.io import atomic_write


class LyricsCorpusWSDExecutionError(ValueError):
    """Raised when placeholder corpus WSD cannot safely execute or resume."""


def _object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LyricsCorpusWSDExecutionError(f"{label} is unavailable or invalid: {path}") from error
    if not isinstance(value, dict):
        raise LyricsCorpusWSDExecutionError(f"{label} must contain an object")
    return value


def _verify_bundle(
    path: Path, *, run_id: str, request_content_id: str, menu_content_id: str
) -> None:
    bundle = _object(path, "existing corpus WSD bundle")
    if (
        bundle.get("bundle_version") != BUNDLE_VERSION
        or bundle.get("run_id") != run_id
        or bundle.get("language") != "es"
        or bundle.get("mode") != "lyrics"
        or bundle.get("coverage") != "complete_request_pool"
        or bundle.get("request_file_content_id") != request_content_id
        or bundle.get("sense_menu_content_id") != menu_content_id
        or bundle.get("method", {}).get("profile_id") != METHOD_PROFILE
    ):
        raise LyricsCorpusWSDExecutionError(f"existing WSD bundle conflicts: {run_id}")


def execute_spanish_v5_corpus(
    repository_root: Path,
    workspace: Workspace,
    *,
    plan_path: Path,
    preparation_report_path: Path,
    env_file: Path | None = None,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Execute the current best-so-far method once over an exact prepared corpus."""

    plan_path = plan_path.expanduser().resolve()
    preparation_report_path = preparation_report_path.expanduser().resolve()
    plan = _object(plan_path, "Lyrics corpus plan")
    preparation = _object(preparation_report_path, "Lyrics corpus WSD preparation report")
    if (
        plan.get("plan_version") != PLAN_VERSION
        or plan.get("status") != "planned_sources_only"
        or plan.get("language") != "es"
    ):
        raise LyricsCorpusWSDExecutionError("placeholder v5 execution requires an exact Spanish corpus plan")
    plan_id = plan.get("plan_id")
    if (
        preparation.get("status") != "complete"
        or preparation.get("execution_status") != "not_run"
        or preparation.get("plan_id") != plan_id
        or preparation.get("plan_content_id") != file_content_id(plan_path)
    ):
        raise LyricsCorpusWSDExecutionError("WSD preparation does not cover this exact corpus")
    songs = [
        (source, song)
        for source in plan.get("included_sources", []) if isinstance(source, dict)
        for song in source.get("songs", []) if isinstance(song, dict)
    ]
    if len(songs) != preparation.get("song_run_count"):
        raise LyricsCorpusWSDExecutionError("prepared song count disagrees with the corpus plan")

    bundle_root = (
        workspace.root / "raw/wsd/results/es/lyrics/corpora"
        / plan_id / METHOD_PROFILE
    )
    bundle_paths: dict[str, Path] = {}
    missing: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for source, song in songs:
        run_id = song.get("planned_run_id")
        if not isinstance(run_id, str):
            raise LyricsCorpusWSDExecutionError("corpus song has no stable planned run")
        run = workspace.root / "runs/es/lyrics" / run_id
        request_path = run / "stages/04_wsd_prepare/output/requests.jsonl"
        menu_path = run / "stages/03_lexical_menu/output/sense-menu.json"
        request_id = file_content_id(request_path)
        menu_id = file_content_id(menu_path)
        target = bundle_root / f"{run_id}.json"
        bundle_paths[run_id] = target
        if target.exists():
            _verify_bundle(
                target, run_id=run_id,
                request_content_id=request_id, menu_content_id=menu_id,
            )
        else:
            missing.append((source, song))

    runtime = None
    if missing:
        print(
            f"Collecting exact embedding requirements for {len(songs)} songs before publication...",
            flush=True,
        )
        required_texts: list[str] = []
        for position, (_source, song) in enumerate(songs, start=1):
            required_texts.extend(
                spanish_v5_required_texts(workspace, run_id=song["planned_run_id"])
            )
            if position % 25 == 0 or position == len(songs):
                print(f"  collected requirements {position}/{len(songs)}", flush=True)
        delta = (
            workspace.root / "cache/derived/wsd/es/corpora" / plan_id
            / METHOD_PROFILE / "gemini-delta"
        )
        runtime = build_spanish_v5_runtime(
            workspace, required_texts=required_texts,
            delta=delta, env_file=env_file,
        )

    missing_ids = {song["planned_run_id"] for _source, song in missing}
    created = skipped = 0
    for position, (source, song) in enumerate(songs, start=1):
        run_id = song["planned_run_id"]
        if run_id in missing_ids:
            execute_spanish_v5_lyrics(
                repository_root, workspace, run_id=run_id,
                runtime=runtime, output_path=bundle_paths[run_id],
            )
            created += 1
            action = "created"
        else:
            skipped += 1
            action = "skipped"
        if progress is not None:
            progress({
                "completed": position, "planned": len(songs), "action": action,
                "artist_slug": source["artist_slug"],
                "source_record_id": song["source_record_id"], "run_id": run_id,
            })

    bundles = {
        run_id: {
            "path": path.relative_to(workspace.root).as_posix(),
            "content_id": file_content_id(path),
        }
        for run_id, path in bundle_paths.items()
    }
    catalog = {
        "catalog_version": CATALOG_VERSION,
        "plan_id": plan_id, "plan_content_id": file_content_id(plan_path),
        "language": "es", "coverage": "complete_song_runs",
        "method_profile_id": METHOD_PROFILE, "bundles": bundles,
    }
    catalog_path = (
        workspace.root / "raw/wsd/catalogs/es/lyrics" / plan_id
        / f"{METHOD_PROFILE}.json"
    )
    if catalog_path.exists():
        if _object(catalog_path, "existing corpus WSD catalog") != catalog:
            raise LyricsCorpusWSDExecutionError("existing corpus WSD catalog conflicts")
    else:
        atomic_write(catalog_path, catalog, workspace.root / ".fluency/temporary")
    return {
        "status": "complete", "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "plan_id": plan_id, "method_profile_id": METHOD_PROFILE,
        "song_run_count": len(songs), "created_this_invocation": created,
        "skipped_this_invocation": skipped, "catalog_path": str(catalog_path),
    }
