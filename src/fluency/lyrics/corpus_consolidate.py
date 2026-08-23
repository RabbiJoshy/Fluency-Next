"""Resumable consolidation of every WSD-complete song in a Lyrics corpus."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any, Callable

from fluency.core.hashing import file_content_id
from fluency.core.workspace import Workspace
from fluency.lyrics.consolidate import (
    consolidate_lyrics_run,
    consolidation_implementation_content_id,
    consolidation_policy,
)
from fluency.lyrics.corpus import PLAN_VERSION
from fluency.release.io import atomic_write


REPORT_VERSION = "lyrics-corpus-consolidation-report/v1"


class LyricsCorpusConsolidationError(ValueError):
    """Raised when exact corpus consolidation cannot safely resume."""


def _object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LyricsCorpusConsolidationError(f"{label} is unavailable or invalid: {path}") from error
    if not isinstance(value, dict):
        raise LyricsCorpusConsolidationError(f"{label} must contain an object")
    return value


def _verify_outputs(output: Path, manifest: dict[str, Any], run_id: str) -> None:
    outputs = manifest.get("outputs")
    if not isinstance(outputs, dict):
        raise LyricsCorpusConsolidationError(f"consolidation has no output ledger: {run_id}")
    for filename, expected in outputs.items():
        path = output / filename
        if Path(filename).name != filename or not path.is_file() or file_content_id(path) != expected:
            raise LyricsCorpusConsolidationError(
                f"consolidation output is missing or corrupt: {run_id}/{filename}"
            )


def _expected_branch_inputs(run: Path, wsd: Path) -> dict[str, str]:
    owners = {
        "source": run / "stages/01_source_ingest/output",
        "process": run / "stages/02_process/output",
        "lexical": run / "stages/03_lexical_menu/output",
        "prepare": run / "stages/04_wsd_prepare/output",
        "wsd": wsd,
    }
    manifests = {name: _object(path / "manifest.json", f"{name} manifest") for name, path in owners.items()}
    files = (
        ("source", "song", "song.json"),
        ("source", "lines", "lines.jsonl"),
        ("source", "alignments", "alignments.jsonl"),
        ("process", "occurrences", "occurrences.jsonl"),
        ("process", "analysis_units", "analysis-units.jsonl"),
        ("process", "routes", "routes.jsonl"),
        ("lexical", "lexical_candidates", "lexical-candidates.jsonl"),
        ("lexical", "sense_menu", "sense-menu.json"),
        ("prepare", "requests", "requests.jsonl"),
        ("wsd", "results", "results.jsonl"),
        ("wsd", "wsd_method", "method.json"),
    )
    result: dict[str, str] = {}
    for owner, key, filename in files:
        path = owners[owner] / filename
        actual = file_content_id(path)
        if manifests[owner].get("outputs", {}).get(filename) != actual:
            raise LyricsCorpusConsolidationError(f"upstream consolidation input changed: {run.name}/{key}")
        result[key] = actual
    return result


def _completed(
    repository_root: Path,
    workspace: Workspace,
    *,
    language: str,
    run_id: str,
    wsd: Path,
    output: Path,
    policy: dict[str, Any],
) -> bool:
    run = workspace.root / "runs" / language / "lyrics" / run_id
    if not output.exists():
        return False
    manifest_path = output / "manifest.json"
    manifest = _object(manifest_path, "consolidation manifest")
    if (
        manifest.get("run_id") != run_id
        or manifest.get("stage") != "consolidation"
        or manifest.get("status") != "complete"
        or manifest.get("inputs") != _expected_branch_inputs(run, wsd)
        or manifest.get("policy") != policy
        or manifest.get("implementation_content_id")
        != consolidation_implementation_content_id(repository_root)
    ):
        raise LyricsCorpusConsolidationError(
            f"existing consolidation conflicts with the selected policy or implementation: {run_id}"
        )
    _verify_outputs(output, manifest, run_id)
    return True


def consolidate_lyrics_corpus(
    repository_root: Path,
    workspace: Workspace,
    *,
    plan_path: Path,
    wsd_import_report_path: Path,
    example_cap_per_sense: int = 12,
    translation_language: str = "en",
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Consolidate all songs only after one exact complete WSD import."""

    plan_path = plan_path.expanduser().resolve()
    wsd_import_report_path = wsd_import_report_path.expanduser().resolve()
    try:
        plan_path.relative_to((workspace.root / "raw/lyrics/corpus-plans").resolve())
        wsd_import_report_path.relative_to((workspace.root / "runs").resolve())
    except ValueError as error:
        raise LyricsCorpusConsolidationError("plan and WSD import report must belong to this workspace") from error
    plan = _object(plan_path, "Lyrics corpus plan")
    wsd_report = _object(wsd_import_report_path, "corpus WSD-import report")
    if plan.get("plan_version") != PLAN_VERSION or plan.get("status") != "planned_sources_only":
        raise LyricsCorpusConsolidationError("unsupported Lyrics corpus plan")
    language = plan.get("language")
    plan_id = plan.get("plan_id")
    if (
        wsd_report.get("status") != "complete"
        or wsd_report.get("plan_id") != plan_id
        or wsd_report.get("plan_content_id") != file_content_id(plan_path)
        or wsd_report.get("coverage") != "complete_song_runs"
    ):
        raise LyricsCorpusConsolidationError("exact corpus WSD import has not completed")
    songs = [
        (source, song)
        for source in plan.get("included_sources", [])
        if isinstance(source, dict)
        for song in source.get("songs", [])
        if isinstance(song, dict)
    ]
    if len(songs) != wsd_report.get("song_run_count"):
        raise LyricsCorpusConsolidationError("WSD import does not cover the corpus song ledger")
    method_profile_id = wsd_report.get("method_profile_id")
    expected_branch = (
        workspace.root / "runs" / language / "lyrics-corpora" / plan_id
        / "methods" / str(method_profile_id) / "songs"
    )
    if wsd_report.get("method_branch") != expected_branch.relative_to(workspace.root).as_posix():
        raise LyricsCorpusConsolidationError("WSD import report names an unexpected method branch")
    policy = consolidation_policy(
        example_cap_per_sense=example_cap_per_sense,
        translation_language=translation_language,
    )
    created = skipped = card_count = example_count = selected_count = non_study_count = 0
    statuses: Counter[str] = Counter()
    for index, (source, song) in enumerate(songs, start=1):
        run_id = song.get("planned_run_id")
        if not isinstance(run_id, str):
            raise LyricsCorpusConsolidationError("corpus plan contains an incomplete run identity")
        wsd = expected_branch / run_id / "wsd_results"
        output = expected_branch / run_id / "consolidation"
        if _completed(
            repository_root, workspace, language=language, run_id=run_id,
            wsd=wsd, output=output, policy=policy,
        ):
            skipped += 1
            action = "skipped"
        else:
            consolidate_lyrics_run(
                repository_root, workspace, run_id=run_id, language=language,
                example_cap_per_sense=example_cap_per_sense,
                translation_language=translation_language,
                wsd_output_path=wsd, output_path=output, publish_run_stage=False,
            )
            created += 1
            action = "created"
        report = _object(
            output / "report.json",
            "song consolidation report",
        )
        card_count += report["study_card_count"]
        example_count += report["assigned_example_count"]
        selected_count += report["selected_example_count"]
        non_study_count += report["non_study_disposition_count"]
        statuses.update(report["status_counts"])
        if progress is not None:
            progress({
                "completed": index, "planned": len(songs), "action": action,
                "artist_slug": source["artist_slug"],
                "source_record_id": song["source_record_id"], "run_id": run_id,
            })
    completion = {
        "report_version": REPORT_VERSION,
        "status": "complete",
        "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "plan_id": plan_id,
        "plan_content_id": file_content_id(plan_path),
        "wsd_import_report_content_id": file_content_id(wsd_import_report_path),
        "language": language,
        "method_profile_id": method_profile_id,
        "method_branch": expected_branch.relative_to(workspace.root).as_posix(),
        "implementation_content_id": consolidation_implementation_content_id(repository_root),
        "policy": policy,
        "song_run_count": len(songs),
        "song_card_reference_count": card_count,
        "assigned_example_count": example_count,
        "selected_example_count": selected_count,
        "non_study_disposition_count": non_study_count,
        "status_counts": dict(sorted(statuses.items())),
    }
    report_path = (
        workspace.root / "runs" / language / "lyrics-corpora" / plan_id
        / f"consolidation-report-{wsd_report['method_profile_id']}.json"
    )
    if report_path.exists():
        prior = _object(report_path, "corpus consolidation report")
        without_time = lambda value: {key: item for key, item in value.items() if key != "completed_at"}
        if without_time(prior) != without_time(completion):
            raise LyricsCorpusConsolidationError("existing corpus consolidation report conflicts with this run")
    else:
        atomic_write(report_path, completion, workspace.root / ".fluency/temporary")
    return {
        **completion,
        "created_this_invocation": created,
        "skipped_this_invocation": skipped,
        "report_path": str(report_path),
    }
