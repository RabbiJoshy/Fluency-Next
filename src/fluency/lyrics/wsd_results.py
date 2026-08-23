"""Validate and publish complete occurrence-level Lyrics WSD result bundles."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

from fluency.core.hashing import canonical_content_id, file_content_id, validate_content_id
from fluency.core.workspace import Workspace
from fluency.lyrics.lineage import build_lineage_event
from fluency.lyrics.lexical import index_menu_analyses, resolve_candidate_analyses
from fluency.release.io import atomic_write, json_bytes


BUNDLE_VERSION = "lyrics-wsd-result-bundle/v1"
RESULT_VERSION = "wsd-result/v2"
STAGE_VERSION = "lyrics-wsd-result-import/v1"
READY_STATUSES = frozenset({"assigned", "abstained", "rejected"})
NON_EXECUTED_STATUSES = frozenset({"no_menu", "ineligible", "review"})


class LyricsWSDResultImportError(ValueError):
    pass


def _object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LyricsWSDResultImportError(f"required JSON is unavailable or invalid: {path}") from error
    if not isinstance(value, dict):
        raise LyricsWSDResultImportError(f"required JSON must contain an object: {path}")
    return value


def _jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        values = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    except (OSError, json.JSONDecodeError) as error:
        raise LyricsWSDResultImportError(f"required JSONL is unavailable or invalid: {path}") from error
    if not all(isinstance(value, dict) for value in values):
        raise LyricsWSDResultImportError(f"JSONL contains a non-object: {path}")
    return values


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _method(value: Any) -> dict[str, Any]:
    expected = {
        "profile_id", "source_method_id", "source_repository_commit",
        "implementation_version", "implementation_content_id", "model_revisions",
        "asset_refs", "parameters", "optional_methods", "random_seed",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise LyricsWSDResultImportError("WSD method fields do not match the Lyrics bundle contract")
    for field in ("profile_id", "source_method_id", "source_repository_commit", "implementation_version"):
        if not isinstance(value[field], str) or not value[field]:
            raise LyricsWSDResultImportError(f"WSD method requires {field}")
    validate_content_id(value["implementation_content_id"])
    for field in ("model_revisions",):
        mapping = value[field]
        if not isinstance(mapping, dict) or not mapping or any(
            not isinstance(key, str) or not key or not isinstance(item, str) or not item
            for key, item in mapping.items()
        ):
            raise LyricsWSDResultImportError(f"WSD method requires pinned {field}")
    refs = value["asset_refs"]
    if not isinstance(refs, dict) or not refs:
        raise LyricsWSDResultImportError("WSD method requires exact asset references")
    for name, reference in refs.items():
        if not isinstance(name, str) or not name or not isinstance(reference, dict) or set(reference) != {"path", "content_id"}:
            raise LyricsWSDResultImportError("WSD asset reference fields are invalid")
        if not isinstance(reference["path"], str) or not reference["path"] or Path(reference["path"]).is_absolute():
            raise LyricsWSDResultImportError("WSD asset paths must be workspace-relative")
        validate_content_id(reference["content_id"])
    if not isinstance(value["parameters"], dict) or not isinstance(value["optional_methods"], dict):
        raise LyricsWSDResultImportError("WSD method parameters and optional methods must be objects")
    if not isinstance(value["random_seed"], int) or value["random_seed"] < 0:
        raise LyricsWSDResultImportError("WSD method random seed is invalid")
    return value


def _validate_result(
    result: dict[str, Any],
    request: dict[str, Any],
    candidate: dict[str, Any],
    *,
    menu_content_id: str,
    analyses: list[dict[str, Any]],
) -> None:
    required = {
        "result_version", "result_id", "request_id", "run_id", "language", "mode",
        "target", "occurrence_id", "surface_card_id", "surface_form", "status",
        "menu_content_id", "menu_analysis_id", "selected_sense_id", "selected_tuple",
        "decision_path", "evidence", "confidence", "input_artifact_ids",
    }
    if set(result) != required or result.get("result_version") != RESULT_VERSION:
        raise LyricsWSDResultImportError("WSD result fields do not match the v2 contract")
    for field in ("request_id", "run_id", "language", "mode", "target", "occurrence_id", "surface_card_id", "surface_form"):
        if result[field] != request[field]:
            raise LyricsWSDResultImportError(f"WSD result does not match its request: {field}")
    body = {key: value for key, value in result.items() if key != "result_id"}
    expected_result_id = "wsd_result_" + canonical_content_id(body).removeprefix("sha256:")[:32]
    if result["result_id"] != expected_result_id:
        raise LyricsWSDResultImportError("WSD result identity does not match its content")
    status = result["status"]
    eligibility = request["eligibility"]
    if eligibility == "ready":
        if status not in READY_STATUSES or result["menu_content_id"] != menu_content_id:
            raise LyricsWSDResultImportError("ready request has an invalid executed disposition")
    else:
        if status != eligibility:
            raise LyricsWSDResultImportError("non-executable request disposition changed during WSD")
        if any(result[field] is not None for field in ("menu_content_id", "menu_analysis_id", "selected_sense_id", "selected_tuple", "confidence")):
            raise LyricsWSDResultImportError("non-executable result claims model/menu output")
        if result["decision_path"]:
            raise LyricsWSDResultImportError("non-executable result cannot claim a decision path")
    if not isinstance(result["decision_path"], list) or not all(isinstance(item, str) and item for item in result["decision_path"]):
        raise LyricsWSDResultImportError("WSD result decision path is invalid")
    if not isinstance(result["evidence"], dict) or not isinstance(result["input_artifact_ids"], list):
        raise LyricsWSDResultImportError("WSD result evidence/provenance is invalid")
    if result["confidence"] is not None and (
        isinstance(result["confidence"], bool) or not isinstance(result["confidence"], (int, float))
        or not 0 <= result["confidence"] <= 1
    ):
        raise LyricsWSDResultImportError("WSD confidence is invalid")
    if status == "assigned":
        analyses_by_id = {analysis["menu_analysis_id"]: analysis for analysis in analyses}
        analysis = analyses_by_id.get(result["menu_analysis_id"])
        if analysis is None:
            raise LyricsWSDResultImportError("assigned result selected an analysis outside its exact menu")
        senses = {sense["sense_id"] for sense in analysis["senses"]}
        if result["selected_sense_id"] not in senses:
            raise LyricsWSDResultImportError("assigned result selected a sense outside its exact analysis")
        if result["selected_tuple"] != {
            "headword": analysis["headword"], "part_of_speech": analysis["part_of_speech"]
        }:
            raise LyricsWSDResultImportError("assigned result tuple does not match its analysis")
        if not result["decision_path"]:
            raise LyricsWSDResultImportError("assigned result requires a decision path")
    elif status in READY_STATUSES and any(
        result[field] is not None for field in ("menu_analysis_id", "selected_sense_id", "selected_tuple")
    ):
        raise LyricsWSDResultImportError("non-assigned result cannot claim a selected sense")


def import_lyrics_wsd_results(
    repository_root: Path,
    workspace: Workspace,
    *,
    run_id: str,
    language: str,
    bundle_path: Path,
    output_path: Path | None = None,
    publish_run_stage: bool = True,
    started_at: datetime | None = None,
) -> Path:
    run = workspace.root / "runs" / language / "lyrics" / run_id
    run_manifest_path = run / "manifest.json"
    run_manifest = _object(run_manifest_path)
    if run_manifest.get("run_id") != run_id or run_manifest.get("language") != language or run_manifest.get("mode") != "lyrics":
        raise LyricsWSDResultImportError("Lyrics run identity does not match WSD import")
    prepare = run / "stages/04_wsd_prepare/output"
    lexical = run / "stages/03_lexical_menu/output"
    prepare_manifest = _object(prepare / "manifest.json")
    lexical_manifest = _object(lexical / "manifest.json")
    request_path = prepare / "requests.jsonl"
    candidate_path = lexical / "lexical-candidates.jsonl"
    menu_path = lexical / "sense-menu.json"
    hashes = {
        "requests": file_content_id(request_path),
        "lexical_candidates": file_content_id(candidate_path),
        "sense_menu": file_content_id(menu_path),
    }
    if prepare_manifest.get("outputs", {}).get("requests.jsonl") != hashes["requests"]:
        raise LyricsWSDResultImportError("prepared WSD requests changed after completion")
    if lexical_manifest.get("outputs", {}).get("lexical-candidates.jsonl") != hashes["lexical_candidates"] or lexical_manifest.get("outputs", {}).get("sense-menu.json") != hashes["sense_menu"]:
        raise LyricsWSDResultImportError("lexical WSD inputs changed after completion")
    bundle_path = bundle_path.expanduser().resolve()
    if not _inside(bundle_path, workspace.root / "raw/wsd"):
        raise LyricsWSDResultImportError("Lyrics WSD bundle must be inside workspace/raw/wsd")
    bundle = _object(bundle_path)
    expected_bundle = {
        "bundle_version", "run_id", "language", "mode", "coverage",
        "request_file_content_id", "sense_menu_content_id", "method", "results",
    }
    if set(bundle) != expected_bundle or bundle.get("bundle_version") != BUNDLE_VERSION:
        raise LyricsWSDResultImportError("unsupported Lyrics WSD result bundle")
    if (bundle.get("run_id"), bundle.get("language"), bundle.get("mode")) != (run_id, language, "lyrics"):
        raise LyricsWSDResultImportError("Lyrics WSD bundle identity does not match the run")
    if bundle.get("coverage") != "complete_request_pool" or bundle.get("request_file_content_id") != hashes["requests"] or bundle.get("sense_menu_content_id") != hashes["sense_menu"]:
        raise LyricsWSDResultImportError("Lyrics WSD bundle does not cover these exact inputs")
    method = _method(bundle.get("method"))
    for name, reference in method["asset_refs"].items():
        asset_path = (workspace.root / reference["path"]).resolve()
        if not _inside(asset_path, workspace.root) or not asset_path.is_file():
            raise LyricsWSDResultImportError(f"WSD method asset is unavailable: {name}")
        if file_content_id(asset_path) != reference["content_id"]:
            raise LyricsWSDResultImportError(f"WSD method asset content changed: {name}")
    requests = _jsonl(request_path)
    candidates = _jsonl(candidate_path)
    analyses_by_card = index_menu_analyses(_object(menu_path))
    request_by_id = {request["request_id"]: request for request in requests}
    candidate_by_id = {candidate["lexical_candidate_id"]: candidate for candidate in candidates}
    if len(request_by_id) != len(requests) or len(candidate_by_id) != len(candidates):
        raise LyricsWSDResultImportError("WSD inputs contain duplicate stable identities")
    raw_results = bundle.get("results")
    if not isinstance(raw_results, list):
        raise LyricsWSDResultImportError("Lyrics WSD bundle results must be an array")
    results: dict[str, dict[str, Any]] = {}
    counts: Counter[str] = Counter()
    for result in raw_results:
        if not isinstance(result, dict) or not isinstance(result.get("request_id"), str):
            raise LyricsWSDResultImportError("Lyrics WSD bundle contains an invalid result")
        request_id = result["request_id"]
        if request_id in results or request_id not in request_by_id:
            raise LyricsWSDResultImportError("Lyrics WSD result identity is duplicate or unknown")
        request = request_by_id[request_id]
        candidate = candidate_by_id.get(request["lexical_candidate_id"])
        if candidate is None:
            raise LyricsWSDResultImportError("WSD request lost its lexical candidate")
        _validate_result(
            result,
            request,
            candidate,
            menu_content_id=hashes["sense_menu"],
            analyses=resolve_candidate_analyses(candidate, analyses_by_card),
        )
        results[request_id] = result
        counts[result["status"]] += 1
    if set(results) != set(request_by_id):
        raise LyricsWSDResultImportError(
            f"Lyrics WSD coverage is incomplete: expected {len(requests)}, received {len(results)}"
        )
    output = run / "stages/05_wsd_results/output" if output_path is None else output_path.resolve()
    if not _inside(output, workspace.root / "runs"):
        raise LyricsWSDResultImportError("Lyrics WSD output must be inside workspace/runs")
    if output_path is not None and publish_run_stage:
        raise LyricsWSDResultImportError(
            "an external WSD branch cannot replace the source run's canonical stage reference"
        )
    if output.exists():
        raise LyricsWSDResultImportError("Lyrics WSD output already exists; create a new run")
    started_at = datetime.now(UTC) if started_at is None else started_at.astimezone(UTC)
    temporary_root = workspace.root / ".fluency/temporary"
    temporary = Path(tempfile.mkdtemp(prefix="lyrics-wsd-results-", dir=temporary_root))
    try:
        ordered = [results[request["request_id"]] for request in requests]
        (temporary / "results.jsonl").write_bytes(b"".join(json_bytes(result) for result in ordered))
        events = [build_lineage_event(
            subject=request["target"], phase="assign",
            operation="assign" if results[request["request_id"]]["status"] == "assigned" else "abstain",
            run_id=run_id, method_id=method["source_method_id"],
            input_refs=[{"kind": "wsd_request", "id": request["request_id"]}],
            output_refs=[{"kind": "wsd_result", "id": results[request["request_id"]]["result_id"]}],
            evidence_kind="direct",
            decision={"status": results[request["request_id"]]["status"]},
            reason_codes=results[request["request_id"]]["evidence"].get("reason_codes", []),
        ) for request in requests]
        (temporary / "lineage.jsonl").write_bytes(b"".join(json_bytes(event) for event in events))
        (temporary / "method.json").write_bytes(json_bytes(method))
        report = {
            "report_version": "lyrics-wsd-result-report/v1", "run_id": run_id,
            "language": language, "request_count": len(requests),
            "result_counts": dict(sorted(counts.items())), "coverage": "complete_request_pool",
            "method_profile_id": method["profile_id"], "fallbacks": [],
        }
        (temporary / "report.json").write_bytes(json_bytes(report))
        outputs = {name: file_content_id(temporary / name) for name in ("results.jsonl", "lineage.jsonl", "method.json", "report.json")}
        manifest = {
            "manifest_version": STAGE_VERSION, "run_id": run_id, "stage": "wsd_results",
            "status": "complete", "started_at": started_at.isoformat().replace("+00:00", "Z"),
            "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "method_id": method["source_method_id"],
            "implementation_content_id": canonical_content_id({
                "implementation": file_content_id(Path(__file__)),
                "schema": file_content_id(repository_root / "schemas/wsd-result-v2.schema.json"),
            }),
            "inputs": {**hashes, "bundle": file_content_id(bundle_path)},
            "model_revisions": method["model_revisions"], "asset_refs": method["asset_refs"],
            "outputs": outputs,
        }
        (temporary / "manifest.json").write_bytes(json_bytes(manifest))
        output.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    if publish_run_stage:
        stages = dict(run_manifest.get("stages", {}))
        stages["wsd_results"] = {
            "path": "stages/05_wsd_results/output",
            "manifest_content_id": file_content_id(output / "manifest.json"),
        }
        run_manifest["stages"] = stages
        atomic_write(run_manifest_path, run_manifest, temporary_root)
    return output
