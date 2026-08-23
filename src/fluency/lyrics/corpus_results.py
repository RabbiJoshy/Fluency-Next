"""Algorithm-neutral bulk import of exact Lyrics WSD result bundles."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any, Callable

from fluency.core.hashing import file_content_id
from fluency.core.workspace import Workspace
from fluency.lyrics.corpus import PLAN_VERSION, SAFE_ID
from fluency.lyrics.wsd_results import import_lyrics_wsd_results
from fluency.release.io import atomic_write


CATALOG_VERSION = "lyrics-wsd-corpus-bundle-catalog/v1"
REPORT_VERSION = "lyrics-wsd-corpus-import-report/v1"


class LyricsCorpusResultImportError(ValueError):
    """Raised when a corpus result catalog is incomplete, stale, or conflicting."""


def _object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LyricsCorpusResultImportError(f"{label} is unavailable or invalid: {path}") from error
    if not isinstance(value, dict):
        raise LyricsCorpusResultImportError(f"{label} must contain an object")
    return value


def _verify_outputs(output: Path, manifest: dict[str, Any], run_id: str) -> None:
    outputs = manifest.get("outputs")
    if not isinstance(outputs, dict):
        raise LyricsCorpusResultImportError(f"WSD result stage has no output ledger: {run_id}")
    for filename, expected in outputs.items():
        path = output / filename
        if Path(filename).name != filename or not path.is_file() or file_content_id(path) != expected:
            raise LyricsCorpusResultImportError(f"WSD result output is missing or corrupt: {run_id}/{filename}")


def _completed_import(
    output: Path,
    *,
    run_id: str,
    bundle_content_id: str,
) -> bool:
    if not output.exists():
        return False
    manifest_path = output / "manifest.json"
    manifest = _object(manifest_path, "WSD result manifest")
    if (
        manifest.get("run_id") != run_id
        or manifest.get("stage") != "wsd_results"
        or manifest.get("status") != "complete"
        or manifest.get("inputs", {}).get("bundle") != bundle_content_id
    ):
        raise LyricsCorpusResultImportError(
            f"existing WSD result conflicts with the selected bundle: {run_id}"
        )
    _verify_outputs(output, manifest, run_id)
    return True


def import_lyrics_corpus_results(
    repository_root: Path,
    workspace: Workspace,
    *,
    plan_path: Path,
    preparation_report_path: Path,
    catalog_path: Path,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Import complete per-song bundles from any method satisfying the contract."""

    plan_path = plan_path.expanduser().resolve()
    preparation_report_path = preparation_report_path.expanduser().resolve()
    catalog_path = catalog_path.expanduser().resolve()
    try:
        plan_path.relative_to((workspace.root / "raw/lyrics/corpus-plans").resolve())
        preparation_report_path.relative_to((workspace.root / "runs").resolve())
        catalog_path.relative_to((workspace.root / "raw/wsd").resolve())
    except ValueError as error:
        raise LyricsCorpusResultImportError("plan, preparation report and bundle catalog must belong to this workspace") from error
    plan = _object(plan_path, "Lyrics corpus plan")
    preparation = _object(preparation_report_path, "corpus WSD-preparation report")
    catalog = _object(catalog_path, "corpus WSD bundle catalog")
    if plan.get("plan_version") != PLAN_VERSION or plan.get("status") != "planned_sources_only":
        raise LyricsCorpusResultImportError("unsupported Lyrics corpus plan")
    language = plan.get("language")
    plan_id = plan.get("plan_id")
    if (
        preparation.get("status") != "complete"
        or preparation.get("plan_id") != plan_id
        or preparation.get("plan_content_id") != file_content_id(plan_path)
        or preparation.get("execution_status") != "not_run"
    ):
        raise LyricsCorpusResultImportError("exact corpus WSD preparation has not completed")
    required_catalog_fields = {
        "catalog_version", "plan_id", "plan_content_id", "language", "coverage",
        "method_profile_id", "bundles",
    }
    if (
        set(catalog) != required_catalog_fields
        or catalog.get("catalog_version") != CATALOG_VERSION
        or catalog.get("plan_id") != plan_id
        or catalog.get("plan_content_id") != file_content_id(plan_path)
        or catalog.get("language") != language
        or catalog.get("coverage") != "complete_song_runs"
        or not isinstance(catalog.get("method_profile_id"), str)
        or SAFE_ID.fullmatch(catalog["method_profile_id"]) is None
        or not isinstance(catalog.get("bundles"), dict)
    ):
        raise LyricsCorpusResultImportError("WSD bundle catalog does not match the exact corpus contract")
    songs = [
        (source, song)
        for source in plan.get("included_sources", [])
        if isinstance(source, dict)
        for song in source.get("songs", [])
        if isinstance(song, dict)
    ]
    run_ids = [song.get("planned_run_id") for _source, song in songs]
    if (
        len(run_ids) != preparation.get("song_run_count")
        or any(not isinstance(run_id, str) for run_id in run_ids)
        or set(catalog["bundles"]) != set(run_ids)
    ):
        raise LyricsCorpusResultImportError("WSD bundle catalog must cover every planned song exactly once")

    bundles: dict[str, tuple[Path, str]] = {}
    for run_id in run_ids:
        entry = catalog["bundles"][run_id]
        if not isinstance(entry, dict) or set(entry) != {"path", "content_id"}:
            raise LyricsCorpusResultImportError(f"invalid WSD bundle reference: {run_id}")
        relative = entry["path"]
        expected = entry["content_id"]
        if not isinstance(relative, str) or Path(relative).is_absolute() or not isinstance(expected, str):
            raise LyricsCorpusResultImportError(f"unsafe WSD bundle reference: {run_id}")
        path = (workspace.root / relative).resolve()
        try:
            path.relative_to((workspace.root / "raw/wsd").resolve())
        except ValueError as error:
            raise LyricsCorpusResultImportError(f"WSD bundle escapes raw/wsd: {run_id}") from error
        if not path.is_file() or file_content_id(path) != expected:
            raise LyricsCorpusResultImportError(f"WSD bundle is unavailable or corrupt: {run_id}")
        bundle = _object(path, "WSD result bundle")
        if bundle.get("run_id") != run_id or bundle.get("language") != language:
            raise LyricsCorpusResultImportError(f"WSD bundle identity mismatch: {run_id}")
        if bundle.get("method", {}).get("profile_id") != catalog["method_profile_id"]:
            raise LyricsCorpusResultImportError(f"WSD method profile drift: {run_id}")
        bundles[run_id] = (path, expected)

    branch_root = (
        workspace.root / "runs" / language / "lyrics-corpora" / plan_id
        / "methods" / catalog["method_profile_id"] / "songs"
    )
    created = skipped = result_count = 0
    statuses: Counter[str] = Counter()
    for index, (source, song) in enumerate(songs, start=1):
        run_id = song["planned_run_id"]
        bundle_path, bundle_id = bundles[run_id]
        output = branch_root / run_id / "wsd_results"
        if _completed_import(
            output, run_id=run_id, bundle_content_id=bundle_id
        ):
            skipped += 1
            action = "skipped"
        else:
            import_lyrics_wsd_results(
                repository_root, workspace, run_id=run_id,
                language=language, bundle_path=bundle_path,
                output_path=output, publish_run_stage=False,
            )
            created += 1
            action = "created"
        report = _object(
            output / "report.json",
            "song WSD-result report",
        )
        result_count += report["request_count"]
        statuses.update(report["result_counts"])
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
        "preparation_report_content_id": file_content_id(preparation_report_path),
        "bundle_catalog_content_id": file_content_id(catalog_path),
        "language": language,
        "method_profile_id": catalog["method_profile_id"],
        "method_branch": branch_root.relative_to(workspace.root).as_posix(),
        "song_run_count": len(songs),
        "result_count": result_count,
        "result_counts": dict(sorted(statuses.items())),
        "coverage": "complete_song_runs",
    }
    report_path = (
        workspace.root / "runs" / language / "lyrics-corpora" / plan_id
        / f"wsd-import-report-{catalog['method_profile_id']}.json"
    )
    if report_path.exists():
        prior = _object(report_path, "corpus WSD-import report")
        without_time = lambda value: {key: item for key, item in value.items() if key != "completed_at"}
        if without_time(prior) != without_time(completion):
            raise LyricsCorpusResultImportError("existing corpus WSD-import report conflicts with this catalog")
    else:
        atomic_write(report_path, completion, workspace.root / ".fluency/temporary")
    return {
        **completion,
        "created_this_invocation": created,
        "skipped_this_invocation": skipped,
        "report_path": str(report_path),
    }
