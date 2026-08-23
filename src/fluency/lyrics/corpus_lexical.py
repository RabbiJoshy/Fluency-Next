"""Resumable provider-menu executor for an exact processed Lyrics corpus."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Callable

from fluency.core.hashing import canonical_content_id, file_content_id
from fluency.core.workspace import Workspace
from fluency.lyrics.corpus import PLAN_VERSION, SAFE_ID
from fluency.lyrics.lexical import (
    KAIKKI_ADAPTER_ID,
    SPANISHDICT_ADAPTER_ID,
    build_lyrics_lexical_menu_stage,
    build_provider_menu,
    lexical_implementation_content_id,
    lexical_lookup_forms,
)
from fluency.release.io import atomic_write, json_bytes
from fluency.sense_menu.config import load_sense_menu_language_policy
from fluency.sense_menu.spanishdict import REQUIRED_FILES as SPANISHDICT_FILES


REPORT_VERSION = "lyrics-corpus-lexical-menu-report/v1"
SHARED_MENU_VERSION = "lyrics-corpus-provider-menu/v1"


class LyricsCorpusLexicalError(ValueError):
    """Raised when a bulk lexical-menu run cannot prove exact provenance."""


def _object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LyricsCorpusLexicalError(f"{label} is unavailable or invalid: {path}") from error
    if not isinstance(value, dict):
        raise LyricsCorpusLexicalError(f"{label} must contain an object")
    return value


def _jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    except (OSError, json.JSONDecodeError) as error:
        raise LyricsCorpusLexicalError(f"required JSONL is unavailable or invalid: {path}") from error


def _snapshot_content_id(path: Path, provider: str) -> str:
    if provider != "spanishdict":
        if not path.is_file():
            raise LyricsCorpusLexicalError("Wiktionary dictionary snapshot must be one immutable file")
        return file_content_id(path)
    if not path.is_dir():
        raise LyricsCorpusLexicalError("SpanishDict dictionary snapshot must be one immutable directory")
    files: dict[str, str] = {}
    for filename in SPANISHDICT_FILES:
        source = path / filename
        if not source.is_file():
            raise LyricsCorpusLexicalError(f"SpanishDict snapshot file is missing: {filename}")
        files[filename] = file_content_id(source)
    artifact = path / "artifact.json"
    if not artifact.is_file():
        raise LyricsCorpusLexicalError("SpanishDict snapshot artifact manifest is missing")
    return canonical_content_id({"manifest": file_content_id(artifact), "files": files})


def _verify_outputs(output: Path, manifest: dict[str, Any], run_id: str) -> None:
    outputs = manifest.get("outputs")
    if not isinstance(outputs, dict):
        raise LyricsCorpusLexicalError(f"lexical-menu run has no output ledger: {run_id}")
    for filename, content_id in outputs.items():
        path = output / filename
        if Path(filename).name != filename or not path.is_file() or file_content_id(path) != content_id:
            raise LyricsCorpusLexicalError(f"lexical-menu output is missing or corrupt: {run_id}/{filename}")


def _require_completed_song_menu(
    workspace: Workspace,
    *,
    language: str,
    run_id: str,
    expected_implementation: str,
    snapshot_content_id: str,
    policy_content_id: str,
) -> bool:
    run = workspace.root / "runs" / language / "lyrics" / run_id
    output = run / "stages/03_lexical_menu/output"
    if not output.exists():
        return False
    stage_manifest = _object(output / "manifest.json", "lexical-menu manifest")
    process_manifest = _object(
        run / "stages/02_process/output/manifest.json", "processing manifest"
    )
    expected_inputs = {
        "analysis_units": process_manifest.get("outputs", {}).get("analysis-units.jsonl"),
        "routes": process_manifest.get("outputs", {}).get("routes.jsonl"),
        "dictionary_snapshot": snapshot_content_id,
        "language_policy": policy_content_id,
    }
    if (
        stage_manifest.get("run_id") != run_id
        or stage_manifest.get("stage") != "lexical_menu"
        or stage_manifest.get("status") != "complete"
        or stage_manifest.get("inputs") != expected_inputs
        or stage_manifest.get("implementation_content_id") != expected_implementation
    ):
        raise LyricsCorpusLexicalError(
            f"existing lexical-menu run conflicts with this exact corpus menu: {run_id}"
        )
    _verify_outputs(output, stage_manifest, run_id)
    return True


def build_lyrics_corpus_lexical_menus(
    repository_root: Path,
    workspace: Workspace,
    *,
    plan_path: Path,
    dictionary_snapshot: Path,
    snapshot_id: str,
    language_policy_id: str,
    menu_id: str,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Build one provider union, then exact compact menus for every planned song."""

    if SAFE_ID.fullmatch(menu_id) is None:
        raise LyricsCorpusLexicalError("unsafe corpus menu ID")
    plan_path = plan_path.expanduser().resolve()
    dictionary_snapshot = dictionary_snapshot.expanduser().resolve()
    try:
        plan_path.relative_to((workspace.root / "raw/lyrics/corpus-plans").resolve())
        dictionary_snapshot.relative_to((workspace.root / "raw").resolve())
    except ValueError as error:
        raise LyricsCorpusLexicalError("plan and dictionary snapshot must be pinned in this workspace") from error
    plan = _object(plan_path, "Lyrics corpus plan")
    if plan.get("plan_version") != PLAN_VERSION or plan.get("status") != "planned_sources_only":
        raise LyricsCorpusLexicalError("unsupported Lyrics corpus plan")
    language = plan.get("language")
    plan_id = plan.get("plan_id")
    if not isinstance(language, str) or not isinstance(plan_id, str):
        raise LyricsCorpusLexicalError("Lyrics corpus plan identity is incomplete")
    policy = load_sense_menu_language_policy(
        repository_root, policy_id=language_policy_id, language=language
    )
    snapshot_content_id = _snapshot_content_id(dictionary_snapshot, policy["provider"])
    policy_content_id = canonical_content_id(policy)
    process_report_path = (
        workspace.root / "runs" / language / "lyrics-corpora" / plan_id / "process-report.json"
    )
    process_report = _object(process_report_path, "corpus processing completion report")
    if (
        process_report.get("status") != "complete"
        or process_report.get("plan_id") != plan_id
        or process_report.get("plan_content_id") != file_content_id(plan_path)
    ):
        raise LyricsCorpusLexicalError("exact corpus processing has not completed")
    songs = [
        (source, song)
        for source in plan.get("included_sources", [])
        if isinstance(source, dict)
        for song in source.get("songs", [])
        if isinstance(song, dict)
    ]
    if len(songs) != plan.get("totals", {}).get("songs"):
        raise LyricsCorpusLexicalError("corpus song ledger does not match its declared total")

    song_forms: dict[str, set[str]] = {}
    union: set[str] = set()
    for _source, song in songs:
        run_id = song.get("planned_run_id")
        if not isinstance(run_id, str):
            raise LyricsCorpusLexicalError("corpus plan contains an incomplete run identity")
        process = workspace.root / "runs" / language / "lyrics" / run_id / "stages/02_process/output"
        manifest = _object(process / "manifest.json", "processing manifest")
        for filename in ("analysis-units.jsonl", "routes.jsonl"):
            if file_content_id(process / filename) != manifest.get("outputs", {}).get(filename):
                raise LyricsCorpusLexicalError(f"processing artifact changed after completion: {run_id}/{filename}")
        forms = lexical_lookup_forms(
            _jsonl(process / "analysis-units.jsonl"), _jsonl(process / "routes.jsonl")
        )
        song_forms[run_id] = forms
        union.update(forms)

    implementation = lexical_implementation_content_id(
        repository_root,
        language_policy_id=language_policy_id,
        source_adapter=(
            SPANISHDICT_ADAPTER_ID if policy["provider"] == "spanishdict"
            else KAIKKI_ADAPTER_ID
        ),
    )
    union_content_id = canonical_content_id(sorted(union))
    shared = (
        workspace.root / "runs" / language / "lyrics-corpora" / plan_id
        / "lexical-menus" / menu_id
    )
    shared_manifest_path = shared / "manifest.json"
    expected_shared_inputs = {
        "plan": file_content_id(plan_path),
        "processing_report": file_content_id(process_report_path),
        "dictionary_snapshot": snapshot_content_id,
        "language_policy": policy_content_id,
        "lookup_union": union_content_id,
    }
    if shared.exists():
        shared_manifest = _object(shared_manifest_path, "corpus provider-menu manifest")
        if (
            shared_manifest.get("manifest_version") != SHARED_MENU_VERSION
            or shared_manifest.get("inputs") != expected_shared_inputs
            or shared_manifest.get("implementation_content_id") != implementation
        ):
            raise LyricsCorpusLexicalError("existing corpus provider menu conflicts with this run")
        _verify_outputs(shared, shared_manifest, menu_id)
        menu = _object(shared / "sense-menu.json", "corpus provider menu")
    else:
        menu, provider_report, _policy = build_provider_menu(
            repository_root,
            language=language,
            dictionary_snapshot=dictionary_snapshot,
            snapshot_id=snapshot_id,
            language_policy_id=language_policy_id,
            lookup_forms=union,
        )
        if menu.get("snapshot_content_id") != snapshot_content_id:
            raise LyricsCorpusLexicalError("provider adapter snapshot identity drifted")
        temporary_root = workspace.root / ".fluency/temporary"
        temporary_root.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix="lyrics-corpus-menu-", dir=temporary_root))
        try:
            (temporary / "sense-menu.json").write_bytes(json_bytes(menu))
            (temporary / "provider-report.json").write_bytes(json_bytes(provider_report))
            outputs = {
                filename: file_content_id(temporary / filename)
                for filename in ("sense-menu.json", "provider-report.json")
            }
            manifest = {
                "manifest_version": SHARED_MENU_VERSION,
                "status": "complete",
                "menu_id": menu_id,
                "language": language,
                "source_adapter": menu["source_adapter"],
                "implementation_content_id": implementation,
                "inputs": expected_shared_inputs,
                "outputs": outputs,
            }
            (temporary / "manifest.json").write_bytes(json_bytes(manifest))
            shared.parent.mkdir(parents=True, exist_ok=True)
            os.replace(temporary, shared)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)

    created = skipped = 0
    status_totals: Counter[str] = Counter()
    candidate_count = analysis_count = sense_count = 0
    for index, (source, song) in enumerate(songs, start=1):
        run_id = song["planned_run_id"]
        if _require_completed_song_menu(
            workspace,
            language=language,
            run_id=run_id,
            expected_implementation=implementation,
            snapshot_content_id=snapshot_content_id,
            policy_content_id=policy_content_id,
        ):
            skipped += 1
            action = "skipped"
        else:
            build_lyrics_lexical_menu_stage(
                repository_root,
                workspace,
                run_id=run_id,
                language=language,
                dictionary_snapshot=dictionary_snapshot,
                snapshot_id=snapshot_id,
                language_policy_id=language_policy_id,
                _prepared_menu=menu,
                _prepared_policy=policy,
            )
            created += 1
            action = "created"
        report = _object(
            workspace.root / "runs" / language / "lyrics" / run_id
            / "stages/03_lexical_menu/output/report.json",
            "song lexical-menu report",
        )
        candidate_count += report["candidate_count"]
        analysis_count += report["ready_analysis_count"]
        sense_count += report["ready_sense_count"]
        status_totals.update(report["status_counts"])
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
        "processing_report_content_id": file_content_id(process_report_path),
        "menu_id": menu_id,
        "shared_menu_manifest_content_id": file_content_id(shared_manifest_path),
        "language": language,
        "dictionary_snapshot_content_id": snapshot_content_id,
        "language_policy_content_id": policy_content_id,
        "implementation_content_id": implementation,
        "song_run_count": len(songs),
        "lookup_form_count": len(union),
        "candidate_count": candidate_count,
        "ready_analysis_reference_count": analysis_count,
        "ready_sense_reference_count": sense_count,
        "status_counts": dict(sorted(status_totals.items())),
        "wsd_status": "not_run",
    }
    report_path = (
        workspace.root / "runs" / language / "lyrics-corpora" / plan_id
        / f"lexical-menu-report-{menu_id}.json"
    )
    if report_path.exists():
        prior = _object(report_path, "corpus lexical-menu completion report")
        comparable = {key: value for key, value in completion.items() if key != "completed_at"}
        if {key: value for key, value in prior.items() if key != "completed_at"} != comparable:
            raise LyricsCorpusLexicalError("existing corpus lexical-menu report conflicts with this run")
    else:
        atomic_write(report_path, completion, workspace.root / ".fluency/temporary")
    return {
        **completion,
        "created_this_invocation": created,
        "skipped_this_invocation": skipped,
        "report_path": str(report_path),
    }
