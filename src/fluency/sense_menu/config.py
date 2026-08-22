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
    provider = policy.get("provider")
    if not isinstance(provider, str) or not provider:
        raise SenseMenuPolicyError("sense-menu provider is required")
    card_binding = policy.get("card_binding")
    if not isinstance(card_binding, dict):
        raise SenseMenuPolicyError("sense-menu card binding is required")
    if card_binding.get("identity") != "surface-card/v1":
        raise SenseMenuPolicyError("sense menus must bind to surface-card identity")
    if card_binding.get("headword_role") != "lookup_metadata_only":
        raise SenseMenuPolicyError("dictionary headwords cannot become card identity")
    if policy.get("menu_order_role") != "provider_prior":
        raise SenseMenuPolicyError("dictionary menu order must be labelled as a provider prior")
    if provider == "spanishdict":
        mismatch = policy.get("response_mismatch")
        if not isinstance(mismatch, dict):
            raise SenseMenuPolicyError("SpanishDict response-mismatch policy is required")
        if mismatch.get("preserve_query_and_response") is not True:
            raise SenseMenuPolicyError("SpanishDict query and response evidence must be preserved")
        if mismatch.get("fuzzy_correction") != "quarantine":
            raise SenseMenuPolicyError("SpanishDict fuzzy corrections must be quarantined")
        lookup = policy.get("lookup_candidates")
        if not isinstance(lookup, dict) or lookup.get("may_replace_surface_card") is not False:
            raise SenseMenuPolicyError("SpanishDict lookup candidates cannot replace a surface card")
        return policy
    if provider != "wiktionary":
        raise SenseMenuPolicyError(f"unsupported sense-menu provider: {provider}")
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
