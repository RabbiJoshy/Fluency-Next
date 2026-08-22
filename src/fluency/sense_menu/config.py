"""Load explicit language policy for dictionary-menu normalization."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


POLICY_VERSION = "sense-menu-language-policy/v1"


class SenseMenuPolicyError(ValueError):
    """Raised when a dictionary-menu language policy is invalid."""


def load_sense_menu_language_policy(
    repository_root: Path,
    *,
    policy_id: str,
    language: str,
) -> dict[str, Any]:
    path = repository_root / "config" / "sense_menu" / "languages" / f"{policy_id}.json"
    try:
        policy = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise SenseMenuPolicyError(f"sense-menu language policy does not exist: {path}") from error
    except json.JSONDecodeError as error:
        raise SenseMenuPolicyError(f"sense-menu language policy is not valid JSON: {path}") from error
    if not isinstance(policy, dict) or policy.get("config_version") != POLICY_VERSION:
        raise SenseMenuPolicyError("unsupported sense-menu language policy")
    if policy.get("policy_id") != policy_id or policy.get("language") != language:
        raise SenseMenuPolicyError("sense-menu language policy identity does not match the run")
    redirects = policy.get("redirects")
    if not isinstance(redirects, dict):
        raise SenseMenuPolicyError("sense-menu redirect policy is required")
    if redirects.get("require_source_case_match") is not True:
        raise SenseMenuPolicyError("redirect source spelling must preserve case")
    for field in ("reject_tags", "allow_if_tags"):
        values = redirects.get(field)
        if not isinstance(values, list) or not all(isinstance(value, str) and value for value in values):
            raise SenseMenuPolicyError(f"redirect {field} must be a string list")
    mapping = redirects.get("target_pos_by_source_pos")
    if not isinstance(mapping, dict) or not mapping:
        raise SenseMenuPolicyError("redirect POS mapping is required")
    for source_pos, targets in mapping.items():
        if not isinstance(source_pos, str) or not source_pos:
            raise SenseMenuPolicyError("redirect source POS must be non-empty")
        if not isinstance(targets, list) or not targets or not all(
            isinstance(target, str) and target for target in targets
        ):
            raise SenseMenuPolicyError(f"redirect target POS list is invalid: {source_pos}")
    return policy
