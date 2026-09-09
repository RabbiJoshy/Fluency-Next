"""Create a new immutable release with canonicalized sense metadata."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

from fluency.core.hashing import canonical_content_id, file_content_id
from fluency.core.workspace import Workspace
from fluency.features import MetadataAccounting, SpecialistFeature
from fluency.features.metadata import METADATA_CONTRACT_VERSION
from fluency.features.spanishdict import extract as extract_spanishdict
from fluency.features.spanishdict_metadata import metadata_accounting as account_spanishdict
from fluency.features.wiktionary import extract as extract_wiktionary
from fluency.features.wiktionary import metadata_accounting as account_wiktionary
from fluency.release.composition import compose_release
from fluency.release.validation import validate_release_bundle
from fluency.sense_menu.config import (
    load_sense_menu_language_policy,
    load_sense_menu_registry,
)


def _object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON file must contain an object: {path}")
    return value


def _deduplicate(features: list[SpecialistFeature]) -> tuple[SpecialistFeature, ...]:
    result: list[SpecialistFeature] = []
    seen: set[tuple[str, str, str]] = set()
    for feature in features:
        key = (feature.family, feature.kind, feature.value)
        if key not in seen:
            seen.add(key)
            result.append(feature)
    return tuple(result)


def canonicalize_meaning_metadata(
    meaning: dict[str, Any], *, policy: dict[str, Any]
) -> None:
    """Upgrade one meaning in place without changing its identity or gloss."""

    metadata = meaning.setdefault("metadata", {})
    if not isinstance(metadata, dict):
        raise ValueError("meaning metadata must be an object")
    provider = metadata.get("sense_provider_metadata") or {}
    if not isinstance(provider, dict):
        raise ValueError("sense provider metadata must be an object")
    existing = [
        SpecialistFeature.from_dict(item)
        for item in metadata.get("specialist_features", [])
    ]
    adapter = str(metadata.get("source_adapter") or "")
    if adapter.startswith("wiktionary-"):
        source = dict(provider)
        source.setdefault("glosses", [str(meaning.get("translation") or "")])
        tags = [tag for tag in source.get("tags", []) if isinstance(tag, str)]
        derived = list(extract_wiktionary(source, tags=tags, policy=policy))
        accounting = account_wiktionary(source, tags=tags, policy=policy)
    elif adapter.startswith("spanishdict-"):
        nested = provider.get("spanishdict") or {}
        source = dict(nested) if isinstance(nested, dict) else {}
        source["context"] = provider.get("context") or meaning.get("context") or ""
        source.setdefault("regions", provider.get("regions") or [])
        derived = list(extract_spanishdict(source))
        accounting = account_spanishdict(source)
    else:
        source = dict(provider)
        derived = []
        accounting = MetadataAccounting(coverage={"provider_metadata": "preserved"})
    features = _deduplicate([*existing, *derived])
    metadata["specialist_features"] = [item.to_dict() for item in features]
    metadata["sense_metadata"] = accounting.envelope(
        source_metadata=source, features=features
    )
    metadata["language_policy_id"] = policy["policy_id"]
    metadata["language_policy_content_id"] = canonical_content_id(policy)


def upgrade_release_metadata(
    repository_root: Path,
    workspace: Workspace,
    *,
    language: str,
    mode: str,
    source_release_id: str,
    target_release_id: str,
) -> Path:
    """Publish a new inactive release; the source release remains untouched."""

    source = workspace.root / "releases" / language / mode / source_release_id
    validate_release_bundle(source)
    registry = load_sense_menu_registry(repository_root)
    entry = registry["languages"].get(language)
    if not isinstance(entry, dict):
        raise ValueError(f"metadata policy is not registered for {language}")
    policy = load_sense_menu_language_policy(
        repository_root, policy_id=entry["policy_id"], language=language
    )
    deck = deepcopy(_object(source / "deck.json"))
    composition = deepcopy(_object(source / "composition.json"))
    sense_count = 0
    for card in deck.get("cards", []):
        for meaning in card.get("meanings", []):
            canonicalize_meaning_metadata(meaning, policy=policy)
            sense_count += 1
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    deck.update({
        "release_id": target_release_id,
        "metadata_contract": METADATA_CONTRACT_VERSION,
    })
    composition.update({
        "release_id": target_release_id,
        "created_at": now,
        "publication_status": "inactive_audit",
        "metadata_contract": METADATA_CONTRACT_VERSION,
        "label": f"{composition['label']} · canonical metadata",
    })
    composition["layers"]["metadata_normalization"] = {
        "selection_version": "layer-selection/v1",
        "source_type": "manual",
        "source_id": source_release_id,
        "artifact_id": file_content_id(source / "deck.json"),
        "record_count": sense_count,
        "requires": {
            "sense_menu": composition["layers"]["sense_menu"]["artifact_id"]
        },
    }
    return compose_release(workspace, composition, deck)
