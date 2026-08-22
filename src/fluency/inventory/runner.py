"""Execute the immutable surface-inventory stage for a planned run."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

from fluency.core.hashing import canonical_content_id, file_content_id
from fluency.core.identity import build_card_id
from fluency.core.manifests import StageManifest, build_stage_cache_key
from fluency.core.workspace import Workspace
from fluency.inventory.config import load_inventory_language_policy
from fluency.inventory.lexique import ADAPTER_ID, ranked_surfaces, read_lexique4
from fluency.pipeline.planning import load_pipeline_profile
from fluency.release.io import atomic_write, json_bytes


STAGE_VERSION = "inventory-stage/v1"
STAGE_RELATIVE = Path("stages/01_inventory")


class InventoryRunError(ValueError):
    """Raised when an inventory run would be mutable, implicit, or contaminated."""


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise InventoryRunError(f"required run artifact does not exist: {path}") from error
    except json.JSONDecodeError as error:
        raise InventoryRunError(f"run artifact is not valid JSON: {path}") from error
    if not isinstance(value, dict):
        raise InventoryRunError(f"run artifact must contain an object: {path}")
    return value


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _implementation_content_id() -> str:
    package = Path(__file__).resolve().parent
    paths = (Path(__file__).resolve(), package / "config.py", package / "lexique.py")
    return canonical_content_id(
        {str(path.relative_to(package.parent)): file_content_id(path) for path in paths}
    )


def build_inventory_stage(
    repository_root: Path,
    workspace: Workspace,
    *,
    run_id: str,
    language: str,
    mode: str,
    frequency_snapshot: Path,
    snapshot_id: str,
    started_at: datetime | None = None,
) -> Path:
    """Build a run-owned surface inventory from one explicit Lexique 4 snapshot."""

    if not snapshot_id.strip():
        raise InventoryRunError("snapshot_id must be explicit and non-empty")
    if language != "fr":
        raise InventoryRunError("the installed Lexique adapter supports French only")
    started_at = datetime.now(UTC) if started_at is None else started_at
    run_directory = workspace.root / "runs" / language / mode / run_id
    manifest_path = run_directory / "manifest.json"
    run_manifest = _load_object(manifest_path)
    if (
        run_manifest.get("run_id") != run_id
        or run_manifest.get("language") != language
        or run_manifest.get("mode") != mode
    ):
        raise InventoryRunError("run identity does not match the requested inventory")
    profile = load_pipeline_profile(run_directory / "profile.json")
    if profile["language"] != language or profile["mode"] != mode:
        raise InventoryRunError("run profile language or mode does not match")
    if profile["inventory"]["source_adapter"] != ADAPTER_ID:
        raise InventoryRunError("no installed inventory adapter matches the run profile")
    language_policy = load_inventory_language_policy(
        repository_root,
        policy_id=profile["inventory"]["language_policy"],
        language=language,
    )

    resolved_snapshot = frequency_snapshot.expanduser().resolve()
    if not _inside(resolved_snapshot, workspace.root / "raw"):
        raise InventoryRunError(
            f"frequency snapshot must be inside the workspace raw directory: {resolved_snapshot}"
        )
    output_directory = run_directory / STAGE_RELATIVE / "output"
    if output_directory.exists():
        raise InventoryRunError(
            "inventory output already exists; create a new run instead of overwriting it"
        )

    source_content_id = file_content_id(resolved_snapshot)
    result = read_lexique4(resolved_snapshot)
    source_ranked = list(ranked_surfaces(result.frequencies))
    exclusions = language_policy["surface_exclusions"]
    excluded = [
        {
            "surface": surface,
            "source_rank": rank,
            "frequency_per_million": frequency,
            **exclusions[surface],
        }
        for rank, (surface, frequency) in enumerate(source_ranked, start=1)
        if surface in exclusions
    ]
    ranked = [item for item in source_ranked if item[0] not in exclusions]
    surface_limit = profile["scope"]["surface_limit"]
    if len(ranked) < surface_limit:
        raise InventoryRunError(
            f"frequency snapshot has only {len(ranked)} accepted surfaces; {surface_limit} required"
        )
    inventory_cards = [
        {
            "card_id": build_card_id(language, surface),
            "surface_key": surface,
            "display_form": surface,
            "rank": rank,
        }
        for rank, (surface, _frequency) in enumerate(ranked[:surface_limit], start=1)
    ]
    inventory = {
        "inventory_version": "surface-inventory/v1",
        "language": language,
        "cards": inventory_cards,
    }
    frequency_ranks = {
        surface: rank for rank, (surface, _frequency) in enumerate(ranked, start=1)
    }
    report = {
        "report_version": "inventory-report/v1",
        "source_adapter": ADAPTER_ID,
        "snapshot_id": snapshot_id,
        "snapshot_content_id": source_content_id,
        "source_rows": result.source_rows,
        "accepted_unique_surfaces": len(ranked),
        "inventory_surfaces": len(inventory_cards),
        "rejected_empty_or_zero": result.rejected_empty_or_zero,
        "rejected_surface_shape": result.rejected_surface_shape,
        "duplicate_analysis_rows": result.duplicate_rows,
        "language_policy": language_policy["policy_id"],
        "excluded_surfaces": excluded,
        "identity_fields": ["language", "surface_key"],
        "forbidden_identity_fields": ["lemma", "part_of_speech"],
        "top_surfaces": [
            {"rank": rank, "surface": surface, "frequency_per_million": frequency}
            for rank, (surface, frequency) in enumerate(ranked[:surface_limit], start=1)
        ],
    }
    config = {
        "source_adapter": ADAPTER_ID,
        "language": language,
        "surface_limit": surface_limit,
        "card_identity": "surface-card/v1",
        "frequency_measure": "Lexique 4 FreqOrtho",
        "language_policy": language_policy,
        "fallback_policy": "none",
    }
    inputs = {"frequency_snapshot": source_content_id}
    implementation_content_id = _implementation_content_id()
    config_content_id = canonical_content_id(config)
    temporary_root = workspace.root / ".fluency" / "temporary"
    temporary = Path(tempfile.mkdtemp(prefix="inventory-", dir=temporary_root))
    try:
        (temporary / "inventory.json").write_bytes(json_bytes(inventory))
        (temporary / "frequency-ranks.json").write_bytes(json_bytes(frequency_ranks))
        (temporary / "report.json").write_bytes(json_bytes(report))
        stage = StageManifest(
            stage_name="inventory",
            stage_version=STAGE_VERSION,
            cache_key=build_stage_cache_key(
                stage_name="inventory",
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
                "inventory": file_content_id(temporary / "inventory.json"),
                "frequency_ranks": file_content_id(temporary / "frequency-ranks.json"),
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
