"""Create an inspectable run skeleton without executing expensive data stages."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

from fluency.core.canonical_json import canonical_json_bytes
from fluency.core.hashing import content_id
from fluency.core.manifests import create_run_manifest
from fluency.core.workspace import Workspace
from fluency.pipeline.budget import (
    BudgetError,
    check_wsd_budget,
    display_examples_per_card,
    wsd_budget_per_card,
)
from fluency.core.io import json_bytes


PROFILE_VERSION = "speech-pipeline-profile/v1"
PLAN_VERSION = "speech-pipeline-plan/v1"
CONTRACT_VERSION = "pipeline-stage-contract/v1"
STAGE_ORDER = (
    "inventory",
    "sense_menu",
    "sentence_harvest",
    "wsd_assignments",
    "example_selection",
    "release_build",
)

# What each stage actually reads. The linear STAGE_ORDER is an execution
# sequence, not a dependency chain, and flattening the two hides a real fact:
# `sense_menu` and `sentence_harvest` are siblings. Both read only the
# inventory; neither reads the other. Running the menu first is a scheduling
# preference -- it is cheap and fails fast on a bad dictionary snapshot -- and
# not a data dependency.
#
# Declared because "I changed one thing, what moved?" is otherwise unanswerable
# from the artifacts: re-running the menu does not invalidate a harvest, and
# changing corpus does not invalidate a menu, but the numbering suggests both do.
STAGE_INPUTS = {
    "inventory": (),
    "sense_menu": ("inventory",),
    "sentence_harvest": ("inventory",),
    "wsd_assignments": ("sense_menu", "sentence_harvest"),
    "example_selection": ("sentence_harvest", "wsd_assignments"),
    "release_build": ("inventory", "sense_menu", "example_selection"),
}


def stage_dependencies(stage: str) -> tuple[str, ...]:
    """Return the stages whose output this stage reads."""

    if stage not in STAGE_INPUTS:
        raise PipelineProfileError(f"unknown pipeline stage: {stage}")
    return STAGE_INPUTS[stage]


def stages_invalidated_by(stage: str) -> tuple[str, ...]:
    """Return the stages that must be rebuilt if this stage's output changes.

    Transitive, so it answers the question directly rather than requiring the
    caller to walk the graph and get the sibling case wrong.
    """

    if stage not in STAGE_INPUTS:
        raise PipelineProfileError(f"unknown pipeline stage: {stage}")
    dirty = {stage}
    changed = True
    while changed:
        changed = False
        for candidate, inputs in STAGE_INPUTS.items():
            if candidate not in dirty and dirty.intersection(inputs):
                dirty.add(candidate)
                changed = True
    return tuple(name for name in STAGE_ORDER if name in dirty and name != stage)
STAGE_OUTPUTS = {
    "inventory": ("inventory", "surface-inventory/v1"),
    "sense_menu": ("sense_menu", "sense-menu/v1"),
    "sentence_harvest": ("sentences", "sentence-harvest/v1"),
    "wsd_assignments": ("wsd_assignments", "wsd-assignments/v1"),
    "example_selection": ("example_selection", "example-selection/v1"),
    "release_build": ("release", "speech-release/v1"),
}
STAGE_DEPENDENCIES = {
    "inventory": (),
    "sense_menu": ("inventory",),
    "sentence_harvest": ("inventory",),
    "wsd_assignments": ("inventory", "sense_menu", "sentence_harvest"),
    "example_selection": (
        "inventory",
        "sentence_harvest",
    ),
    "release_build": ("inventory", "sense_menu", "example_selection"),
}


class PipelineProfileError(ValueError):
    """Raised when a run profile could permit drift or legacy contamination."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PipelineProfileError(message)


def validate_pipeline_profile(profile: dict[str, Any]) -> None:
    """Fail closed on identity, input, fallback, and stage-order decisions."""

    _require(profile.get("profile_version") == PROFILE_VERSION, "unsupported profile version")
    for field in ("profile_id", "language", "locale"):
        _require(isinstance(profile.get(field), str) and bool(profile[field]), f"{field} is required")
    _require(profile.get("mode") == "speech", "profile mode must be speech")

    identity = profile.get("identity")
    _require(isinstance(identity, dict), "identity policy is required")
    _require(identity.get("unit_type") == "surface", "card identity must be surface-only")
    _require(identity.get("identity_version") == "surface-card/v1", "unsupported card identity")
    _require(identity.get("allow_lemma_identity") is False, "lemma identity must remain disabled")

    source_policy = profile.get("source_policy")
    _require(isinstance(source_policy, dict), "source policy is required")
    _require(source_policy.get("fresh_snapshots_only") is True, "only fresh source snapshots are allowed")
    _require(source_policy.get("allow_legacy_inputs") is False, "legacy inputs must remain disabled")
    _require(
        isinstance(source_policy.get("allow_recovered_inputs"), bool),
        "recovered-input policy must be explicit",
    )
    _require(source_policy.get("fallback_policy") == "none", "input fallback must remain disabled")

    scope = profile.get("scope")
    _require(isinstance(scope, dict), "audit scope is required")
    _require(
        isinstance(scope.get("surface_limit"), int) and scope["surface_limit"] > 0,
        "surface limit must be a positive integer",
    )
    _require(display_examples_per_card(scope) == 3, "Speech profiles must target up to three final examples per surface")
    _require(
        scope.get("shortfall_policy") in {"block_release", "publish_explicit"},
        "example shortfall policy is invalid",
    )

    inventory = profile.get("inventory")
    _require(isinstance(inventory, dict), "inventory adapter policy is required")
    _require(
        isinstance(inventory.get("source_adapter"), str) and bool(inventory["source_adapter"]),
        "inventory source adapter is required",
    )
    _require(
        isinstance(inventory.get("language_policy"), str) and bool(inventory["language_policy"]),
        "inventory language policy is required",
    )
    recovered_inventory = inventory.get("source_adapter") == "recovered-surface-ranking/v1"
    _require(
        source_policy["allow_recovered_inputs"] is recovered_inventory,
        "recovered-input permission must exactly match the selected inventory adapter",
    )
    _require(inventory.get("output_schema") == "surface-inventory/v1", "unsupported inventory output")
    _require(inventory.get("identity_unit") == "surface", "inventory identity must be surface-only")
    _require(inventory.get("lemma_role") == "excluded", "inventory must exclude lemma data")

    sense_menu = profile.get("sense_menu")
    _require(isinstance(sense_menu, dict), "sense-menu adapter policy is required")
    _require(
        isinstance(sense_menu.get("source_adapter"), str) and bool(sense_menu["source_adapter"]),
        "sense-menu source adapter is required",
    )
    _require(
        isinstance(sense_menu.get("language_policy"), str) and bool(sense_menu["language_policy"]),
        "sense-menu language policy is required",
    )
    _require(sense_menu.get("output_schema") == "sense-menu/v1", "unsupported sense-menu output")
    _require(
        isinstance(sense_menu.get("source_edition"), str) and bool(sense_menu["source_edition"]),
        "sense-menu source edition is required",
    )
    _require(sense_menu.get("gloss_language") == "en", "WSD requires English sense glosses")
    _require(sense_menu.get("join_key") == "surface_card_id", "sense menus must join by surface-card identity")
    _require(sense_menu.get("lemma_role") == "lookup_metadata_only", "lemmas cannot become card identity")
    _require(
        sense_menu.get("snapshot_id") is None
        or (isinstance(sense_menu.get("snapshot_id"), str) and bool(sense_menu["snapshot_id"])),
        "sense-menu snapshot ID is invalid",
    )

    harvest = profile.get("harvest")
    _require(isinstance(harvest, dict), "harvest policy is required")
    for field in ("shared_policy", "language_policy"):
        _require(
            isinstance(harvest.get(field), str) and bool(harvest[field]),
            f"harvest {field} is required",
        )
    _require(
        harvest.get("source_policy") in {"exclusive", "explicit_union"},
        "harvest source policy is invalid",
    )
    sources = harvest.get("sources")
    _require(
        isinstance(sources, list)
        and bool(sources)
        and len(sources) == len(set(sources))
        and all(isinstance(source, str) and source for source in sources),
        "harvest sources are invalid",
    )
    _require(
        harvest.get("source_policy") != "exclusive" or len(sources) == 1,
        "exclusive harvesting requires exactly one source",
    )
    try:
        budget = wsd_budget_per_card(harvest)
        display_limit = display_examples_per_card(scope)
    except BudgetError as error:
        raise PipelineProfileError(str(error)) from error
    _require(
        budget >= display_limit,
        "the per-card WSD budget cannot be below the number of examples displayed",
    )
    try:
        check_wsd_budget(profile)
    except BudgetError as error:
        raise PipelineProfileError(str(error)) from error

    _require(profile.get("stage_order") == list(STAGE_ORDER), "pipeline stage order is not canonical")
    wsd = profile.get("wsd")
    _require(isinstance(wsd, dict), "WSD policy is required")
    _require(
        wsd.get("strategy") == "language-adapted-closed-menu/v1",
        "unsupported WSD strategy",
    )
    for field in ("shared_profile", "language_profile", "model_profile"):
        _require(
            isinstance(wsd.get(field), str) and bool(wsd[field]),
            f"WSD {field} is required",
        )
    _require(wsd.get("require_model_pins") is True, "WSD models must be pinned before execution")
    _require(
        wsd.get("execution_status")
        in {"blocked_pending_assets", "blocked_pending_benchmark", "ready"},
        "WSD execution status is invalid",
    )
    revisions = wsd.get("model_revisions")
    _require(
        isinstance(revisions, dict)
        and all(isinstance(name, str) and name and isinstance(value, str) for name, value in revisions.items()),
        "WSD model revisions are invalid",
    )
    _require(
        wsd["execution_status"] != "ready" or bool(revisions),
        "a ready WSD profile requires pinned model revisions",
    )
    _require(
        not wsd["execution_status"].startswith("blocked_") or not revisions,
        "a blocked WSD profile cannot claim runnable model revisions",
    )

    release = profile.get("release")
    _require(isinstance(release, dict), "release policy is required")
    _require(release.get("activation") == "manual", "pipeline runs must not activate releases")
    _require(release.get("fallback_policy") == "none", "release fallback must remain disabled")


def load_pipeline_profile(path: Path) -> dict[str, Any]:
    try:
        profile = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise PipelineProfileError(f"pipeline profile does not exist: {path}") from error
    except json.JSONDecodeError as error:
        raise PipelineProfileError(f"pipeline profile is not valid JSON: {path}") from error
    _require(isinstance(profile, dict), "pipeline profile must contain an object")
    validate_pipeline_profile(profile)
    return profile


def _acceptance(stage: str, *, surfaces: int, examples: int) -> list[str]:
    rules = {
        "inventory": [
            f"exactly {surfaces} unique surface-card identities",
            "rank and source evidence present for every surface",
            "no lemma-derived card identity fields",
        ],
        "sense_menu": [
            f"all {surfaces} inventory cards represented",
            "every sense has a stable ID, part of speech, translation, and source reference",
        ],
        "sentence_harvest": [
            f"all {surfaces} surfaces scanned against the explicitly selected source snapshots",
            "at least three retained candidates per surface before WSD",
            "source record, license, attribution, and snapshot hash retained per sentence",
            "candidate pools remain larger than the final three-example selection",
        ],
        "wsd_assignments": [
            "every retained card/sentence candidate carries an explicit outcome: assigned, "
            "rejected, abstained, no-menu, or not-evaluated because the per-surface "
            "execution cap was reached",
            "the occurrence sampling policy, cap and selected/not-evaluated counts are recorded, "
            "and those counts reconstitute every occurrence considered",
            "a single-option menu is reported as a deterministic default, never as a model decision",
            "external method implementation and model revisions pinned",
            "inventory, menu, candidate, and sentence-bank hashes match this run exactly",
            "scores, decision status, and rejection reason remain inspectable",
        ],
        "example_selection": [
            "up to three harvested examples selected per surface without requiring WSD",
            "selection remains stable when optional WSD assignments are attached later",
            "no fallback examples from another run",
        ],
        "release_build": [
            f"exactly {surfaces} cards and no more than {examples} examples",
            "every layer hash points to this run's approved artifacts",
            "missing WSD or example coverage remains visible rather than blocking publication",
            "candidate remains inactive until explicit approval",
        ],
    }
    return rules[stage]


def _stage_contract(profile: dict[str, Any], stage: str, ordinal: int) -> dict[str, Any]:
    surfaces = profile["scope"]["surface_limit"]
    examples = surfaces * display_examples_per_card(profile["scope"])
    output_name, output_schema = STAGE_OUTPUTS[stage]
    contract: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "ordinal": ordinal,
        "stage_name": stage,
        "status": "pending",
        "requires_stage_outputs": list(STAGE_DEPENDENCIES[stage]),
        "output": {"name": output_name, "schema": output_schema},
        "acceptance": _acceptance(stage, surfaces=surfaces, examples=examples),
    }
    if stage == "inventory":
        contract["external_inputs"] = ["fresh_frequency_source_snapshot"]
        contract["source_adapter"] = profile["inventory"]
    elif stage == "sense_menu":
        contract["external_inputs"] = ["fresh_dictionary_source_snapshot"]
        contract["source_adapter"] = profile["sense_menu"]
    elif stage == "sentence_harvest":
        contract["external_inputs"] = [
            f"fresh_{source}_source_snapshot" for source in profile["harvest"]["sources"]
        ]
        contract["method"] = profile["harvest"]
    elif stage == "wsd_assignments":
        contract["external_inputs"] = ["complete_wsd_assignment_bundle"]
        contract["method"] = profile["wsd"]
    return contract


def create_pipeline_plan(
    workspace: Workspace,
    profile: dict[str, Any],
    *,
    started_at: datetime | None = None,
    suffix: str | None = None,
) -> Path:
    """Create stage folders and contracts only; do not ingest or execute data."""

    validate_pipeline_profile(profile)
    started_at = datetime.now(UTC) if started_at is None else started_at
    profile_bytes = canonical_json_bytes(profile) + b"\n"
    stage_paths = tuple(
        f"stages/{ordinal:02d}_{stage}/contract.json"
        for ordinal, stage in enumerate(STAGE_ORDER, start=1)
    )
    run = create_run_manifest(
        language=profile["language"],
        mode=profile["mode"],
        profile=profile["profile_id"],
        config_hash=content_id(profile_bytes),
        inputs={},
        stages=stage_paths,
        started_at=started_at,
        suffix=suffix,
    )
    contracts = [
        _stage_contract(profile, stage, ordinal)
        for ordinal, stage in enumerate(STAGE_ORDER, start=1)
    ]
    plan = {
        "plan_version": PLAN_VERSION,
        "run_id": run.run_id,
        "profile_id": profile["profile_id"],
        "profile_content_id": content_id(profile_bytes),
        "execution_status": "not_started",
        "targets": {
            "surface_cards": profile["scope"]["surface_limit"],
            "examples_per_surface": display_examples_per_card(profile["scope"]),
            "total_examples": (
                profile["scope"]["surface_limit"]
                * display_examples_per_card(profile["scope"])
            ),
            "candidate_cap_per_surface": wsd_budget_per_card(profile["harvest"]),
            "wsd_budget_per_card": wsd_budget_per_card(profile["harvest"]),
            **check_wsd_budget(profile),
        },
        "stage_order": list(STAGE_ORDER),
        "release_activation": "manual_only",
    }
    target = workspace.root / "runs" / profile["language"] / profile["mode"] / run.run_id
    temporary_root = workspace.root / ".fluency" / "temporary"
    temporary = Path(tempfile.mkdtemp(prefix="pipeline-plan-", dir=temporary_root))
    try:
        (temporary / "manifest.json").write_bytes(json_bytes(run.to_dict()))
        (temporary / "profile.json").write_bytes(profile_bytes)
        (temporary / "plan.json").write_bytes(json_bytes(plan))
        for path, contract in zip(stage_paths, contracts, strict=True):
            contract_path = temporary / path
            contract_path.parent.mkdir(parents=True, exist_ok=True)
            contract_path.write_bytes(json_bytes(contract))
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return target
