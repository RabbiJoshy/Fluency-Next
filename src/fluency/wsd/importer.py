"""Import a complete, externally produced WSD bundle into immutable Stage 04."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

from fluency.core.canonical_json import canonical_json
from fluency.core.hashing import canonical_content_id, file_content_id, validate_content_id
from fluency.core.manifests import StageManifest, build_stage_cache_key
from fluency.core.workspace import Workspace
from fluency.pipeline.planning import load_pipeline_profile
from fluency.release.io import atomic_write, json_bytes
from fluency.wsd.contracts import WSDAssignment
from fluency.wsd.menus import build_analysis_id
from fluency.wsd.multiword import MULTIWORD_SOURCE_ADAPTER


BUNDLE_VERSION = "wsd-assignment-bundle/v1"
STAGE_VERSION = "wsd-assignment-import/v1"
REPORT_VERSION = "wsd-report/v1"
STAGE_RELATIVE = Path("stages/04_wsd_assignments")


class WSDAssignmentImportError(ValueError):
    """Raised when external assignments do not bind exactly to the selected run."""


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _validated_multiword_analysis(assignment: WSDAssignment, pair: Any):
    """Admit a multiword selection only if its identity is self-verifying.

    Returns the (headword, part_of_speech, sense_ids) triple the provider-menu
    path returns, or None when this is not a declared multiword selection.
    """

    expression = (assignment.evidence or {}).get("selected_multiword")
    if not isinstance(expression, str) or not expression:
        return None
    expected = build_analysis_id(
        card_id=assignment.card_id,
        source_adapter=MULTIWORD_SOURCE_ADAPTER,
        source_analysis_key=expression,
    )
    if assignment.menu_analysis_id != expected:
        raise WSDAssignmentImportError(
            f"multiword analysis ID does not recompute from its expression: {pair}"
        )
    records = (assignment.evidence or {}).get("multiword_candidates")
    if not isinstance(records, list) or not any(
        isinstance(item, dict) and item.get("expression") == expression for item in records
    ):
        raise WSDAssignmentImportError(
            f"multiword selection is not backed by a declared candidate: {pair}"
        )
    return (expression, "PHRASE", {assignment.selected_sense_id})


def _load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise WSDAssignmentImportError(f"required WSD artifact does not exist: {path}") from error
    except json.JSONDecodeError as error:
        raise WSDAssignmentImportError(f"WSD artifact is invalid JSON: {path}") from error
    if not isinstance(value, dict):
        raise WSDAssignmentImportError(f"WSD artifact must contain an object: {path}")
    return value


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _implementation_content_id() -> str:
    package = Path(__file__).resolve().parent
    paths = (Path(__file__).resolve(), package / "contracts.py")
    return canonical_content_id(
        {str(path.relative_to(package)): file_content_id(path) for path in paths}
    )


def _stage_inputs(run: Path) -> tuple[dict[str, str], dict[str, Path]]:
    paths = {
        "inventory": run / "stages/01_inventory/output/inventory.json",
        "sense_menu": run / "stages/02_sense_menu/output/sense-menu.json",
        "candidates": run / "stages/03_sentence_harvest/output/candidates.json",
        "sentence_bank": run / "stages/03_sentence_harvest/output/sentence-bank.jsonl",
    }
    try:
        inputs = {name: file_content_id(path) for name, path in paths.items()}
    except FileNotFoundError as error:
        raise WSDAssignmentImportError(
            f"required preceding stage output is missing: {error.filename}"
        ) from error
    return inputs, paths


def _expected_pairs(
    candidate_payload: dict[str, Any],
) -> tuple[list[tuple[str, str]], dict[str, str]]:
    ordered: list[tuple[str, str]] = []
    surfaces: dict[str, str] = {}
    for card in candidate_payload.get("cards", []):
        card_id = card.get("card_id")
        surface = card.get("display_form")
        if not isinstance(card_id, str) or not isinstance(surface, str):
            raise WSDAssignmentImportError("candidate cards have invalid identity")
        surfaces[card_id] = surface
        for candidate in card.get("candidates", []):
            sentence_id = candidate.get("sentence_id")
            if not isinstance(sentence_id, str):
                raise WSDAssignmentImportError("candidate sentence identity is invalid")
            ordered.append((card_id, sentence_id))
    if len(ordered) != len(set(ordered)):
        raise WSDAssignmentImportError("candidate pool contains duplicate card/sentence pairs")
    return ordered, surfaces


def _menu_index(menu_payload: dict[str, Any]) -> dict[str, dict[str, tuple[str, str, set[str]]]]:
    result: dict[str, dict[str, tuple[str, str, set[str]]]] = {}
    for card in menu_payload.get("cards", []):
        analyses: dict[str, tuple[str, str, set[str]]] = {}
        for analysis in card.get("analyses", []):
            analyses[analysis["menu_analysis_id"]] = (
                analysis["headword"],
                analysis["part_of_speech"],
                {sense["sense_id"] for sense in analysis.get("senses", [])},
            )
        result[card["card_id"]] = analyses
    return result


def _validate_method(method: Any) -> dict[str, Any]:
    if not isinstance(method, dict):
        raise WSDAssignmentImportError("WSD bundle method must be an object")
    expected = {
        "profile_id",
        "implementation_version",
        "implementation_content_id",
        "model_revisions",
        "random_seed",
    }
    if set(method) != expected:
        raise WSDAssignmentImportError("WSD method fields do not match the bundle contract")
    for name in ("profile_id", "implementation_version"):
        if not isinstance(method[name], str) or not method[name]:
            raise WSDAssignmentImportError(f"WSD method requires {name}")
    try:
        validate_content_id(method["implementation_content_id"])
    except (TypeError, ValueError) as error:
        raise WSDAssignmentImportError(
            "WSD method implementation_content_id is invalid"
        ) from error
    revisions = method["model_revisions"]
    if not isinstance(revisions, dict) or not revisions or any(
        not isinstance(name, str)
        or not name
        or not isinstance(revision, str)
        or not revision
        for name, revision in revisions.items()
    ):
        raise WSDAssignmentImportError("WSD method requires pinned model revisions")
    if not isinstance(method["random_seed"], int) or method["random_seed"] < 0:
        raise WSDAssignmentImportError("WSD method random seed is invalid")
    return method


def import_wsd_assignments(
    workspace: Workspace,
    *,
    run_id: str,
    language: str,
    mode: str,
    bundle_path: Path,
    started_at: datetime | None = None,
) -> Path:
    """Validate and publish a complete external assignment bundle exactly once."""

    started_at = datetime.now(UTC) if started_at is None else started_at
    run = workspace.root / "runs" / language / mode / run_id
    run_manifest_path = run / "manifest.json"
    run_manifest = _load_object(run_manifest_path)
    if (
        run_manifest.get("run_id") != run_id
        or run_manifest.get("language") != language
        or run_manifest.get("mode") != mode
    ):
        raise WSDAssignmentImportError("run identity does not match the requested WSD import")
    profile = load_pipeline_profile(run / "profile.json")
    if profile["language"] != language or profile["mode"] != mode:
        raise WSDAssignmentImportError("run profile identity does not match")
    for stage_name in ("01_inventory", "02_sense_menu", "03_sentence_harvest"):
        preceding = _load_object(run / f"stages/{stage_name}/output/manifest.json")
        if preceding.get("status") != "complete":
            raise WSDAssignmentImportError(
                f"preceding stage is not complete: {stage_name}"
            )

    bundle_path = bundle_path.expanduser().resolve()
    wsd_raw_root = workspace.root / "raw/wsd"
    if not _inside(bundle_path, wsd_raw_root):
        raise WSDAssignmentImportError(
            f"WSD bundle must be inside the workspace raw/wsd directory: {bundle_path}"
        )
    bundle = _load_object(bundle_path)
    expected_bundle_fields = {
        "bundle_version",
        "run_id",
        "language",
        "mode",
        "coverage",
        "method",
        "inputs",
        "assignments",
        "sampling",
    }
    if set(bundle) != expected_bundle_fields or bundle.get("bundle_version") != BUNDLE_VERSION:
        raise WSDAssignmentImportError("unsupported WSD assignment bundle")
    sampling = bundle.get("sampling")
    if not isinstance(sampling, dict) or not isinstance(sampling.get("policy"), dict):
        raise WSDAssignmentImportError("WSD bundle must declare its occurrence sampling policy")
    for name in ("occurrences_considered", "occurrences_selected", "occurrences_not_evaluated"):
        if not isinstance(sampling.get(name), int):
            raise WSDAssignmentImportError(f"WSD sampling report requires {name}")
    if sampling["occurrences_selected"] + sampling["occurrences_not_evaluated"] != sampling["occurrences_considered"]:
        # Coverage is the point of this stage: if selected and not-evaluated do
        # not reconstitute what was considered, occurrences went missing between
        # harvest and WSD without any outcome recording that they did.
        raise WSDAssignmentImportError("WSD sampling counts do not account for every occurrence")
    if (
        bundle.get("run_id") != run_id
        or bundle.get("language") != language
        or bundle.get("mode") != mode
    ):
        raise WSDAssignmentImportError("WSD bundle identity does not match the run")
    if bundle.get("coverage") != "complete_candidate_pool":
        raise WSDAssignmentImportError("WSD bundle must explicitly cover the complete candidate pool")
    method = _validate_method(bundle.get("method"))

    inputs, input_paths = _stage_inputs(run)
    if bundle.get("inputs") != inputs:
        raise WSDAssignmentImportError(
            "WSD bundle input hashes do not exactly match this run"
        )
    candidate_payload = _load_object(input_paths["candidates"])
    menu_payload = _load_object(input_paths["sense_menu"])
    ordered_pairs, surfaces = _expected_pairs(candidate_payload)
    expected_set = set(ordered_pairs)
    menus = _menu_index(menu_payload)
    menu_content_id = inputs["sense_menu"]

    raw_assignments = bundle.get("assignments")
    if not isinstance(raw_assignments, list):
        raise WSDAssignmentImportError("WSD bundle assignments must be an array")
    assignments: dict[tuple[str, str], WSDAssignment] = {}
    counts: Counter[str] = Counter()
    for index, raw in enumerate(raw_assignments):
        try:
            assignment = WSDAssignment.from_dict(raw)
        except (AttributeError, KeyError, TypeError, ValueError) as error:
            raise WSDAssignmentImportError(
                f"invalid WSD assignment at index {index}: {error}"
            ) from error
        pair = (assignment.card_id, assignment.sentence_id)
        if pair in assignments:
            raise WSDAssignmentImportError(f"duplicate WSD assignment: {pair}")
        if pair not in expected_set:
            raise WSDAssignmentImportError(f"assignment is not a harvested candidate: {pair}")
        if assignment.surface_form != surfaces[assignment.card_id]:
            raise WSDAssignmentImportError(f"assignment surface does not match card: {pair}")
        if assignment.status != "no_menu" and assignment.model_revisions != method["model_revisions"]:
            raise WSDAssignmentImportError(
                f"assignment model revisions do not match the method manifest: {pair}"
            )
        if assignment.status == "no_menu" and assignment.model_revisions:
            raise WSDAssignmentImportError(
                f"no_menu assignment cannot claim executed model revisions: {pair}"
            )
        card_menu = menus.get(assignment.card_id)
        if card_menu is None:
            raise WSDAssignmentImportError(f"assignment card is missing from sense menu: {pair}")
        if assignment.status == "no_menu":
            if card_menu:
                raise WSDAssignmentImportError(f"no_menu claimed for a card with analyses: {pair}")
        else:
            if assignment.sense_menu_content_id != menu_content_id:
                raise WSDAssignmentImportError(f"assignment uses a stale sense menu: {pair}")
        if assignment.status == "assigned":
            selected = card_menu.get(assignment.menu_analysis_id)
            if selected is None:
                # A multiword sense is a TYPED inventory extension, not a
                # provider menu analysis, so it is legitimately absent from the
                # card menu. It is admitted only if the assignment declares it
                # and the analysis ID recomputes from the declared expression --
                # so an arbitrary ID cannot be passed off as one, and the
                # closed-menu guarantee still holds for every provider sense.
                selected = _validated_multiword_analysis(assignment, pair)
            if selected is None:
                raise WSDAssignmentImportError(f"selected analysis is not in the card menu: {pair}")
            headword, part_of_speech, sense_ids = selected
            if assignment.selected_sense_id not in sense_ids:
                raise WSDAssignmentImportError(f"selected sense is not in the analysis: {pair}")
            if (
                assignment.selected_tuple is None
                or assignment.selected_tuple.headword != headword
                or assignment.selected_tuple.part_of_speech != part_of_speech
            ):
                raise WSDAssignmentImportError(f"selected tuple does not match the analysis: {pair}")
        assignments[pair] = assignment
        counts[assignment.status] += 1

    if set(assignments) != expected_set:
        missing = len(expected_set - set(assignments))
        extra = len(set(assignments) - expected_set)
        raise WSDAssignmentImportError(
            f"WSD bundle coverage is incomplete: {missing} missing, {extra} extra"
        )

    output = run / STAGE_RELATIVE / "output"
    if output.exists():
        raise WSDAssignmentImportError(
            "WSD assignment output already exists; create a new run instead of overwriting it"
        )
    report = {
        "report_version": REPORT_VERSION,
        "run_id": run_id,
        "language": language,
        "profile_ids": {
            "pipeline": profile["profile_id"],
            "method": method["profile_id"],
        },
        "input_content_ids": {**inputs, "assignment_bundle": file_content_id(bundle_path)},
        "assignment_counts": {
            status: counts.get(status, 0)
            for status in ("assigned", "abstained", "rejected", "no_menu")
        },
        "fallbacks": [],
    }
    method_payload = {
        "bundle_version": BUNDLE_VERSION,
        "coverage": "complete_candidate_pool",
        "method": method,
        "source_bundle_content_id": file_content_id(bundle_path),
    }
    config_content_id = canonical_content_id(
        {"pipeline_wsd": profile["wsd"], "external_method": method}
    )
    implementation_content_id = _implementation_content_id()
    stage_inputs = {**inputs, "assignment_bundle": file_content_id(bundle_path)}

    temporary_root = workspace.root / ".fluency/temporary"
    temporary = Path(tempfile.mkdtemp(prefix="wsd-import-", dir=temporary_root))
    try:
        with (temporary / "assignments.jsonl").open("w", encoding="utf-8") as stream:
            for pair in ordered_pairs:
                stream.write(canonical_json(assignments[pair].to_dict()))
                stream.write("\n")
        (temporary / "method.json").write_bytes(json_bytes(method_payload))
        (temporary / "report.json").write_bytes(json_bytes(report))
        stage = StageManifest(
            stage_name="wsd_assignments",
            stage_version=STAGE_VERSION,
            cache_key=build_stage_cache_key(
                stage_name="wsd_assignments",
                stage_version=STAGE_VERSION,
                implementation_hash=implementation_content_id,
                config_hash=config_content_id,
                inputs=stage_inputs,
                model_revisions=method["model_revisions"],
                random_seed=method["random_seed"],
            ),
            implementation_hash=implementation_content_id,
            config_hash=config_content_id,
            status="running",
            started_at=_timestamp(started_at),
            inputs=stage_inputs,
            model_revisions=method["model_revisions"],
            random_seed=method["random_seed"],
            outputs={},
        ).complete(
            {
                "assignments": file_content_id(temporary / "assignments.jsonl"),
                "method": file_content_id(temporary / "method.json"),
                "report": file_content_id(temporary / "report.json"),
            }
        )
        stage_manifest = stage.to_dict()
        (temporary / "manifest.json").write_bytes(json_bytes(stage_manifest))
        output.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)

    contract_path = run / STAGE_RELATIVE / "contract.json"
    contract = _load_object(contract_path)
    contract["status"] = "complete"
    contract["completed_at"] = stage_manifest["completed_at"]
    contract["output_directory"] = "output"
    contract["manifest_content_id"] = file_content_id(output / "manifest.json")
    atomic_write(contract_path, contract, temporary_root)

    run_manifest["status"] = "running"
    run_manifest["inputs"] = {**run_manifest.get("inputs", {}), **stage_manifest["inputs"]}
    atomic_write(run_manifest_path, run_manifest, temporary_root)
    return output
