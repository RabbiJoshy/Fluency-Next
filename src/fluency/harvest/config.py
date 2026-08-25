"""Load and validate layered harvesting configuration."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from fluency.core.hashing import canonical_content_id
from fluency.pipeline.budget import wsd_budget_per_card


SHARED_CONFIG_VERSION = "harvest-shared-policy/v1"
LANGUAGE_CONFIG_VERSION = "harvest-language-policy/v1"
SOURCE_CONFIG_VERSION = "harvest-source-policy/v1"
_POLICY_ID = re.compile(r"^[a-z0-9-]+$")


class HarvestConfigurationError(ValueError):
    """Raised when harvesting policy could drift or select an implicit source."""


def _load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise HarvestConfigurationError(f"harvest configuration does not exist: {path}") from error
    except json.JSONDecodeError as error:
        raise HarvestConfigurationError(f"harvest configuration is not valid JSON: {path}") from error
    if not isinstance(value, dict):
        raise HarvestConfigurationError(f"harvest configuration must contain an object: {path}")
    return value


def _policy_path(root: Path, family: str, policy_id: str) -> Path:
    if not isinstance(policy_id, str) or _POLICY_ID.fullmatch(policy_id) is None:
        raise HarvestConfigurationError(f"invalid {family} policy ID: {policy_id!r}")
    return root / "config" / "harvest" / family / f"{policy_id}.json"


def load_harvest_policies(
    repository_root: Path,
    profile: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], str]:
    """Load the exact shared, language, and explicit source policies."""

    selection = profile["harvest"]
    shared = _load_object(
        _policy_path(repository_root, "shared", selection["shared_policy"])
    )
    language = _load_object(
        _policy_path(repository_root, "languages", selection["language_policy"])
    )
    sources = [
        _load_object(_policy_path(repository_root, "sources", f"{source}-v1"))
        for source in selection["sources"]
    ]

    if shared.get("config_version") != SHARED_CONFIG_VERSION:
        raise HarvestConfigurationError("unsupported shared harvest policy")
    if shared.get("policy_id") != selection["shared_policy"]:
        raise HarvestConfigurationError("shared harvest policy ID does not match its file")
    if language.get("config_version") != LANGUAGE_CONFIG_VERSION:
        raise HarvestConfigurationError("unsupported language harvest policy")
    if language.get("policy_id") != selection["language_policy"]:
        raise HarvestConfigurationError("language harvest policy ID does not match its file")
    if language.get("language") != profile["language"]:
        raise HarvestConfigurationError("language harvest policy does not match the run")
    if shared.get("candidate_cap_per_surface") != wsd_budget_per_card(selection):
        raise HarvestConfigurationError("profile and shared candidate caps disagree")

    expected_sources = selection["sources"]
    for expected, source in zip(expected_sources, sources, strict=True):
        if source.get("config_version") != SOURCE_CONFIG_VERSION:
            raise HarvestConfigurationError(f"unsupported source harvest policy: {expected}")
        if source.get("source") != expected:
            raise HarvestConfigurationError(f"source harvest policy does not match: {expected}")
        if not isinstance(source.get("adapter"), str) or not source["adapter"]:
            raise HarvestConfigurationError(f"source adapter is missing: {expected}")

    combined = {
        "selection": selection,
        "shared": shared,
        "language": language,
        "sources": sources,
    }
    return shared, language, sources, canonical_content_id(combined)
