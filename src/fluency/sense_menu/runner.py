"""Execute the immutable dictionary sense-menu stage for one planned run."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

from fluency.core.hashing import canonical_content_id, file_content_id
from fluency.core.manifests import StageManifest, build_stage_cache_key
from fluency.core.workspace import Workspace
from fluency.harvest.inventory import load_harvest_inventory
from fluency.pipeline.planning import load_pipeline_profile
from fluency.core.io import atomic_write, json_bytes
from fluency.sense_menu.config import load_sense_menu_language_policy
from fluency.sense_menu.kaikki import ADAPTER_ID as KAIKKI_ADAPTER_ID, KaikkiSenseMenuAdapter
from fluency.sense_menu.spanishdict import (
    ADAPTER_ID as SPANISHDICT_ADAPTER_ID,
    SpanishDictSenseMenuAdapter,
)


STAGE_VERSION = "sense-menu-stage/v1"
STAGE_RELATIVE = Path("stages/02_sense_menu")
INVENTORY_RELATIVE = Path("stages/01_inventory/output/inventory.json")


class SenseMenuRunError(ValueError):
    """Raised when a sense-menu run would be ambiguous, mutable, or implicit."""


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise SenseMenuRunError(f"required run artifact does not exist: {path}") from error
    except json.JSONDecodeError as error:
        raise SenseMenuRunError(f"run artifact is not valid JSON: {path}") from error
    if not isinstance(value, dict):
        raise SenseMenuRunError(f"run artifact must contain an object: {path}")
    return value


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _implementation_content_id() -> str:
    package = Path(__file__).resolve().parent
    paths = (
        Path(__file__).resolve(),
        package / "config.py",
        package / "kaikki.py",
        package / "spanishdict.py",
        package.parent / "wsd" / "menus.py",
    )
    return canonical_content_id(
        {str(path.relative_to(package.parent)): file_content_id(path) for path in paths}
    )


def build_sense_menu_stage(
    repository_root: Path,
    workspace: Workspace,
    *,
    run_id: str,
    language: str,
    mode: str,
    dictionary_snapshot: Path,
    snapshot_id: str,
    started_at: datetime | None = None,
) -> Path:
    """Normalize one explicit provider snapshot into a run-owned closed menu."""

    if not snapshot_id.strip():
        raise SenseMenuRunError("snapshot_id must be explicit and non-empty")
    started_at = datetime.now(UTC) if started_at is None else started_at
    run_directory = workspace.root / "runs" / language / mode / run_id
    manifest_path = run_directory / "manifest.json"
    run_manifest = _load_object(manifest_path)
    if (
        run_manifest.get("run_id") != run_id
        or run_manifest.get("language") != language
        or run_manifest.get("mode") != mode
    ):
        raise SenseMenuRunError("run identity does not match the requested sense menu")
    profile = load_pipeline_profile(run_directory / "profile.json")
    if profile["language"] != language or profile["mode"] != mode:
        raise SenseMenuRunError("run profile language or mode does not match")
    source_adapter = profile["sense_menu"]["source_adapter"]
    language_policy = load_sense_menu_language_policy(
        repository_root,
        policy_id=profile["sense_menu"]["language_policy"],
        language=language,
    )

    resolved_snapshot = dictionary_snapshot.expanduser().resolve()
    if not _inside(resolved_snapshot, workspace.root / "raw"):
        raise SenseMenuRunError(
            f"dictionary snapshot must be inside the workspace raw directory: {resolved_snapshot}"
        )
    output_directory = run_directory / STAGE_RELATIVE / "output"
    if output_directory.exists():
        raise SenseMenuRunError(
            "sense-menu output already exists; create a new run instead of overwriting it"
        )
    cards, inventory_content_id = load_harvest_inventory(
        run_directory / INVENTORY_RELATIVE,
        expected_language=language,
        expected_count=profile["scope"]["surface_limit"],
    )
    adapter: KaikkiSenseMenuAdapter | SpanishDictSenseMenuAdapter
    if source_adapter == KAIKKI_ADAPTER_ID:
        adapter = KaikkiSenseMenuAdapter(
            resolved_snapshot,
            language_code=language,
            gloss_language=profile["sense_menu"]["gloss_language"],
            source_edition=profile["sense_menu"]["source_edition"],
            language_policy=language_policy,
        )
    elif source_adapter == SPANISHDICT_ADAPTER_ID:
        adapter = SpanishDictSenseMenuAdapter(
            resolved_snapshot,
            language_code=language,
            gloss_language=profile["sense_menu"]["gloss_language"],
            source_edition=profile["sense_menu"]["source_edition"],
            language_policy=language_policy,
        )
    else:
        raise SenseMenuRunError("no installed sense-menu adapter matches the run profile")
    menu, report = adapter.build(cards, snapshot_id=snapshot_id)
    inventory_cards = int(report.get("inventory_cards", 0))
    cards_ready = int(report.get("cards_ready", 0))
    coverage = cards_ready / inventory_cards if inventory_cards else 0.0
    report["card_coverage"] = coverage
    minimum_coverage = profile["sense_menu"].get("minimum_card_coverage")
    if minimum_coverage is not None and coverage < float(minimum_coverage):
        raise SenseMenuRunError(
            "sense-menu coverage is below the profile minimum: "
            f"{cards_ready}/{inventory_cards} ({coverage:.2%}) < {float(minimum_coverage):.2%}"
        )

    config = {
        "source_adapter": source_adapter,
        "language": language,
        "gloss_language": adapter.gloss_language,
        "source_edition": adapter.source_edition,
        "language_policy": language_policy,
        "card_identity": "surface-card/v1",
        "fallback_policy": "none",
    }
    if isinstance(adapter, KaikkiSenseMenuAdapter):
        config["max_redirect_hops"] = adapter.max_redirect_hops
    inputs = {
        "inventory": inventory_content_id,
        "dictionary_snapshot": adapter.snapshot_content_id,
    }
    implementation_content_id = _implementation_content_id()
    config_content_id = canonical_content_id(config)
    temporary_root = workspace.root / ".fluency" / "temporary"
    temporary = Path(tempfile.mkdtemp(prefix="sense-menu-", dir=temporary_root))
    try:
        (temporary / "sense-menu.json").write_bytes(json_bytes(menu))
        (temporary / "report.json").write_bytes(json_bytes(report))
        stage = StageManifest(
            stage_name="sense_menu",
            stage_version=STAGE_VERSION,
            cache_key=build_stage_cache_key(
                stage_name="sense_menu",
                stage_version=STAGE_VERSION,
                implementation_hash=implementation_content_id,
                config_hash=config_content_id,
                inputs=inputs,
                model_revisions={},
                random_seed=0,
            ),
            implementation_hash=implementation_content_id,
            config_hash=config_content_id,
            status="running",
            started_at=_timestamp(started_at),
            inputs=inputs,
            model_revisions={},
            random_seed=0,
            outputs={},
        ).complete(
            {
                "sense_menu": file_content_id(temporary / "sense-menu.json"),
                "report": file_content_id(temporary / "report.json"),
            }
        )
        stage_manifest = stage.to_dict()
        (temporary / "manifest.json").write_bytes(json_bytes(stage_manifest))
        output_directory.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temporary, output_directory)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)

    contract_path = run_directory / STAGE_RELATIVE / "contract.json"
    contract = _load_object(contract_path)
    contract["status"] = "complete"
    contract["completed_at"] = stage_manifest["completed_at"]
    contract["output_directory"] = "output"
    contract["manifest_content_id"] = file_content_id(output_directory / "manifest.json")
    atomic_write(contract_path, contract, temporary_root)

    run_manifest["status"] = "running"
    run_manifest["inputs"] = {**run_manifest.get("inputs", {}), **inputs}
    atomic_write(manifest_path, run_manifest, temporary_root)
    return output_directory
