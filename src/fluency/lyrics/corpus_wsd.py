"""Resumable WSD-request preparation for an exact Lyrics corpus."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any, Callable

from fluency.core.hashing import file_content_id
from fluency.core.workspace import Workspace
from fluency.lyrics.corpus import PLAN_VERSION
from fluency.lyrics.wsd import (
    prepare_lyrics_wsd_stage,
    wsd_preparation_implementation_content_id,
)
from fluency.core.io import atomic_write


REPORT_VERSION = "lyrics-corpus-wsd-preparation-report/v1"


class LyricsCorpusWSDPreparationError(ValueError):
    """Raised when corpus WSD preparation cannot prove an exact boundary."""


def _object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LyricsCorpusWSDPreparationError(f"{label} is unavailable or invalid: {path}") from error
    if not isinstance(value, dict):
        raise LyricsCorpusWSDPreparationError(f"{label} must contain an object")
    return value


def _verify_outputs(output: Path, manifest: dict[str, Any], run_id: str) -> None:
    outputs = manifest.get("outputs")
    if not isinstance(outputs, dict):
        raise LyricsCorpusWSDPreparationError(f"WSD preparation has no output ledger: {run_id}")
    for filename, expected in outputs.items():
        path = output / filename
        if Path(filename).name != filename or not path.is_file() or file_content_id(path) != expected:
            raise LyricsCorpusWSDPreparationError(
                f"WSD preparation output is missing or corrupt: {run_id}/{filename}"
            )


def _expected_inputs(run: Path) -> dict[str, str]:
    owners = {
        "source": run / "stages/01_source_ingest/output",
        "process": run / "stages/02_process/output",
        "lexical": run / "stages/03_lexical_menu/output",
    }
    manifests = {name: _object(path / "manifest.json", f"{name} manifest") for name, path in owners.items()}
    files = (
        ("source", "lines", "lines.jsonl"),
        ("source", "alignments", "alignments.jsonl"),
        ("process", "occurrences", "occurrences.jsonl"),
        ("process", "analysis_units", "analysis-units.jsonl"),
        ("lexical", "lexical_candidates", "lexical-candidates.jsonl"),
        ("lexical", "sense_menu", "sense-menu.json"),
    )
    result: dict[str, str] = {}
    for owner, key, filename in files:
        path = owners[owner] / filename
        actual = file_content_id(path)
        if manifests[owner].get("outputs", {}).get(filename) != actual:
            raise LyricsCorpusWSDPreparationError(f"upstream WSD input changed: {run.name}/{key}")
        result[key] = actual
    return result


def _completed(
    repository_root: Path, workspace: Workspace, *, language: str, run_id: str
) -> bool:
    run = workspace.root / "runs" / language / "lyrics" / run_id
    output = run / "stages/04_wsd_prepare/output"
    if not output.exists():
        return False
    manifest = _object(output / "manifest.json", "WSD preparation manifest")
    if (
        manifest.get("run_id") != run_id
        or manifest.get("stage") != "wsd_prepare"
        or manifest.get("status") != "complete"
        or manifest.get("inputs") != _expected_inputs(run)
        or manifest.get("implementation_content_id")
        != wsd_preparation_implementation_content_id(repository_root)
        or manifest.get("execution_status") != "not_run"
    ):
        raise LyricsCorpusWSDPreparationError(
            f"existing WSD preparation conflicts with the current exact inputs: {run_id}"
        )
    _verify_outputs(output, manifest, run_id)
    return True


def prepare_lyrics_corpus_wsd(
    repository_root: Path,
    workspace: Workspace,
    *,
    plan_path: Path,
    lexical_report_path: Path,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Prepare every song request pool without executing any WSD method."""

    plan_path = plan_path.expanduser().resolve()
    lexical_report_path = lexical_report_path.expanduser().resolve()
    try:
        plan_path.relative_to((workspace.root / "raw/lyrics/corpus-plans").resolve())
        lexical_report_path.relative_to((workspace.root / "runs").resolve())
    except ValueError as error:
        raise LyricsCorpusWSDPreparationError("plan and lexical report must belong to this workspace") from error
    plan = _object(plan_path, "Lyrics corpus plan")
    lexical_report = _object(lexical_report_path, "corpus lexical-menu completion report")
    if plan.get("plan_version") != PLAN_VERSION or plan.get("status") != "planned_sources_only":
        raise LyricsCorpusWSDPreparationError("unsupported Lyrics corpus plan")
    language = plan.get("language")
    plan_id = plan.get("plan_id")
    if (
        lexical_report.get("status") != "complete"
        or lexical_report.get("plan_id") != plan_id
        or lexical_report.get("plan_content_id") != file_content_id(plan_path)
        or lexical_report.get("wsd_status") != "not_run"
    ):
        raise LyricsCorpusWSDPreparationError("exact corpus lexical menus have not completed")
    songs = [
        (source, song)
        for source in plan.get("included_sources", [])
        if isinstance(source, dict)
        for song in source.get("songs", [])
        if isinstance(song, dict)
    ]
    if len(songs) != lexical_report.get("song_run_count"):
        raise LyricsCorpusWSDPreparationError("lexical report does not cover the corpus song ledger")

    created = skipped = request_count = translation_count = 0
    eligibility: Counter[str] = Counter()
    for index, (source, song) in enumerate(songs, start=1):
        run_id = song.get("planned_run_id")
        if not isinstance(run_id, str):
            raise LyricsCorpusWSDPreparationError("corpus plan contains an incomplete run identity")
        if _completed(repository_root, workspace, language=language, run_id=run_id):
            skipped += 1
            action = "skipped"
        else:
            prepare_lyrics_wsd_stage(repository_root, workspace, run_id=run_id, language=language)
            created += 1
            action = "created"
        report = _object(
            workspace.root / "runs" / language / "lyrics" / run_id
            / "stages/04_wsd_prepare/output/report.json",
            "song WSD preparation report",
        )
        request_count += report["request_count"]
        translation_count += report["translation_available_count"]
        eligibility.update(report["eligibility_counts"])
        if progress is not None:
            progress({
                "completed": index,
                "planned": len(songs),
                "action": action,
                "artist_slug": source["artist_slug"],
                "source_record_id": song["source_record_id"],
                "run_id": run_id,
            })

    completion = {
        "report_version": REPORT_VERSION,
        "status": "complete",
        "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "plan_id": plan_id,
        "plan_content_id": file_content_id(plan_path),
        "lexical_report_content_id": file_content_id(lexical_report_path),
        "language": language,
        "implementation_content_id": wsd_preparation_implementation_content_id(repository_root),
        "song_run_count": len(songs),
        "request_count": request_count,
        "eligibility_counts": dict(sorted(eligibility.items())),
        "executable_request_count": eligibility["ready"],
        "translation_available_count": translation_count,
        "execution_status": "not_run",
    }
    report_path = (
        workspace.root / "runs" / language / "lyrics-corpora" / plan_id
        / "wsd-preparation-report.json"
    )
    if report_path.exists():
        prior = _object(report_path, "corpus WSD-preparation report")
        without_time = lambda value: {key: item for key, item in value.items() if key != "completed_at"}
        if without_time(prior) != without_time(completion):
            raise LyricsCorpusWSDPreparationError("existing WSD-preparation report conflicts with this run")
    else:
        atomic_write(report_path, completion, workspace.root / ".fluency/temporary")
    return {
        **completion,
        "created_this_invocation": created,
        "skipped_this_invocation": skipped,
        "report_path": str(report_path),
    }
