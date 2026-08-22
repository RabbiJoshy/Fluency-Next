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
from fluency.release.io import json_bytes


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
        "sense_menu",
        "sentence_harvest",
        "wsd_assignments",
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
    _require(source_policy.get("fallback_policy") == "none", "input fallback must remain disabled")

    scope = profile.get("scope")
    _require(isinstance(scope, dict), "audit scope is required")
    _require(
        isinstance(scope.get("surface_limit"), int) and scope["surface_limit"] > 0,
        "surface limit must be a positive integer",
    )
    _require(scope.get("examples_per_surface") == 3, "Speech profiles must target three final examples per surface")
    _require(scope.get("shortfall_policy") == "block_release", "example shortfalls must block release")

    inventory = profile.get("inventory")
    _require(isinstance(inventory, dict), "inventory adapter policy is required")
    _require(
        isinstance(inventory.get("source_adapter"), str) and bool(inventory["source_adapter"]),
        "inventory source adapter is required",
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
    _require(sense_menu.get("output_schema") == "sense-menu/v1", "unsupported sense-menu output")
    _require(sense_menu.get("source_edition") == "enwiktionary", "French sense glosses must come from English Wiktionary")
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
    _require(
        isinstance(harvest.get("candidate_cap_per_surface"), int)
        and harvest["candidate_cap_per_surface"] >= scope["examples_per_surface"],
        "harvest candidate cap cannot be below the final example target",
    )

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
        wsd.get("execution_status") in {"blocked_pending_benchmark", "ready"},
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
        wsd["execution_status"] != "blocked_pending_benchmark" or not revisions,
        "a benchmark-blocked WSD profile cannot claim model revisions",
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
            f"all {examples} harvested sentences resolved against the selected sense-menu artifact",
            "embedding and reranker model revisions pinned",
            "scores, decision status, and rejection reason remain inspectable",
        ],
        "example_selection": [
            "exactly three WSD-assigned examples selected per surface",
            "no fallback examples from another run",
        ],
        "release_build": [
            f"exactly {surfaces} cards and {examples} examples",
            "every layer hash points to this run's approved artifacts",
            "candidate remains inactive until explicit approval",
        ],
    }
    return rules[stage]


def _stage_contract(profile: dict[str, Any], stage: str, ordinal: int) -> dict[str, Any]:
    surfaces = profile["scope"]["surface_limit"]
    examples = surfaces * profile["scope"]["examples_per_surface"]
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
            "examples_per_surface": profile["scope"]["examples_per_surface"],
            "total_examples": (
                profile["scope"]["surface_limit"]
                * profile["scope"]["examples_per_surface"]
            ),
            "candidate_cap_per_surface": profile["harvest"]["candidate_cap_per_surface"],
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
