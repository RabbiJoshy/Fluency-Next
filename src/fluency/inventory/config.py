"""Load explicit language policy for surface-inventory construction."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fluency.languages.surfaces import normalizer_for_language


POLICY_VERSION = "inventory-language-policy/v1"


class InventoryPolicyError(ValueError):
    """Raised when an inventory language policy is missing or ambiguous."""


def load_inventory_language_policy(
    repository_root: Path,
    *,
    policy_id: str,
    language: str,
) -> dict[str, Any]:
    path = repository_root / "config" / "inventory" / "languages" / f"{policy_id}.json"
    try:
        policy = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise InventoryPolicyError(f"inventory language policy does not exist: {path}") from error
    except json.JSONDecodeError as error:
        raise InventoryPolicyError(f"inventory language policy is not valid JSON: {path}") from error
    if not isinstance(policy, dict) or policy.get("config_version") != POLICY_VERSION:
        raise InventoryPolicyError("unsupported inventory language policy")
    if policy.get("policy_id") != policy_id or policy.get("language") != language:
        raise InventoryPolicyError("inventory language policy identity does not match the run")
    normalize_surface = normalizer_for_language(language)
    raw_exclusions = policy.get("surface_exclusions")
    if not isinstance(raw_exclusions, dict):
        raise InventoryPolicyError("surface_exclusions must be an object")
    for surface, evidence in raw_exclusions.items():
        if not isinstance(surface, str) or normalize_surface(surface) != surface:
            raise InventoryPolicyError("excluded surfaces must be canonically normalized")
        if not isinstance(evidence, dict):
            raise InventoryPolicyError(f"exclusion evidence must be an object: {surface}")
        if evidence.get("decision") != "exclude_without_redirect":
            raise InventoryPolicyError(f"unsupported exclusion decision for {surface}")
        if not isinstance(evidence.get("reason"), str) or not evidence["reason"].strip():
            raise InventoryPolicyError(f"exclusion reason is required for {surface}")
    return policy
