"""Load explicit language policy for dictionary-menu normalization."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


POLICY_VERSION = "sense-menu-language-policy/v1"
PROVIDER_POLICY_VERSION = "sense-menu-provider-policy/v1"
REGISTRY_VERSION = "sense-menu-registry/v1"
AUDIT_STATUSES = frozenset({"scaffold", "partial", "audited"})


class SenseMenuPolicyError(ValueError):
    """Raised when a dictionary-menu language policy is invalid."""


def _load_json(path: Path, *, description: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise SenseMenuPolicyError(f"{description} does not exist: {path}") from error
    except json.JSONDecodeError as error:
        raise SenseMenuPolicyError(f"{description} is not valid JSON: {path}") from error
    if not isinstance(value, dict):
        raise SenseMenuPolicyError(f"{description} must contain an object")
    return value


def _inherit_provider_policy(repository_root: Path, policy: dict[str, Any]) -> dict[str, Any]:
    provider_policy_id = policy.get("provider_policy_id")
    if provider_policy_id is None:
        return policy
    if not isinstance(provider_policy_id, str) or not provider_policy_id:
        raise SenseMenuPolicyError("provider_policy_id must be a non-empty string")
    path = (
        repository_root / "config" / "sense_menu" / "providers"
        / f"{provider_policy_id}.json"
    )
    provider_policy = _load_json(path, description="sense-menu provider policy")
    if provider_policy.get("config_version") != PROVIDER_POLICY_VERSION:
        raise SenseMenuPolicyError("unsupported sense-menu provider policy")
    if provider_policy.get("provider_policy_id") != provider_policy_id:
        raise SenseMenuPolicyError("sense-menu provider policy identity does not match")
    if provider_policy.get("provider") != policy.get("provider"):
        raise SenseMenuPolicyError("language and provider policies name different providers")
    # Language policy wins at the top level. Nested structures are deliberately
    # replaced whole so an override can never inherit half of a safety rule.
    return {**provider_policy, **policy}


def load_sense_menu_language_policy(
    repository_root: Path,
    *,
    policy_id: str,
    language: str,
) -> dict[str, Any]:
    path = repository_root / "config" / "sense_menu" / "languages" / f"{policy_id}.json"
    policy = _load_json(path, description="sense-menu language policy")
    if policy.get("config_version") != POLICY_VERSION:
        raise SenseMenuPolicyError("unsupported sense-menu language policy")
    policy = _inherit_provider_policy(repository_root, policy)
    if policy.get("policy_id") != policy_id or policy.get("language") != language:
        raise SenseMenuPolicyError("sense-menu language policy identity does not match the run")
    if policy.get("audit_status") not in AUDIT_STATUSES:
        raise SenseMenuPolicyError("sense-menu language policy requires a valid audit_status")
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
    for field in (
        "construction_tags", "domain_tags", "ignored_tags", "region_tags", "register_tags"
    ):
        values = policy.get(field)
        if not isinstance(values, list) or not all(
            isinstance(value, str) and value for value in values
        ):
            raise SenseMenuPolicyError(f"Wiktionary {field} must be a string list")
    grammar_tags = policy.get("grammar_tags")
    if not isinstance(grammar_tags, dict) or not all(
        isinstance(tag, str) and tag and isinstance(value, str) and value
        for tag, value in grammar_tags.items()
    ):
        raise SenseMenuPolicyError("Wiktionary grammar_tags must map strings to strings")
    contextual = policy.get("contextual_grammar_tags")
    if not isinstance(contextual, dict):
        raise SenseMenuPolicyError("Wiktionary contextual_grammar_tags must be an object")
    for tag, rules in contextual.items():
        if not isinstance(tag, str) or not tag or not isinstance(rules, list) or not rules:
            raise SenseMenuPolicyError("contextual grammar tags require named rule lists")
        for rule in rules:
            if not isinstance(rule, dict):
                raise SenseMenuPolicyError(f"contextual grammar rule is invalid: {tag}")
            value = rule.get("value")
            positions = rule.get("parts_of_speech", [])
            required_tags = rule.get("requires_tags", [])
            if not isinstance(value, str) or not value:
                raise SenseMenuPolicyError(f"contextual grammar value is invalid: {tag}")
            if not all(
                isinstance(items, list)
                and all(isinstance(item, str) and item for item in items)
                for items in (positions, required_tags)
            ):
                raise SenseMenuPolicyError(f"contextual grammar conditions are invalid: {tag}")
            if not positions and not required_tags:
                raise SenseMenuPolicyError(f"contextual grammar rule has no conditions: {tag}")
    return policy


def load_sense_menu_registry(repository_root: Path) -> dict[str, Any]:
    """Load and validate the complete language-to-policy matrix."""

    path = repository_root / "config" / "sense_menu" / "registry.json"
    registry = _load_json(path, description="sense-menu registry")
    if registry.get("config_version") != REGISTRY_VERSION:
        raise SenseMenuPolicyError("unsupported sense-menu registry")
    if registry.get("metadata_contract") != "sense-metadata/v1":
        raise SenseMenuPolicyError("sense-menu registry has an unsupported metadata contract")
    languages = registry.get("languages")
    if not isinstance(languages, dict) or not languages:
        raise SenseMenuPolicyError("sense-menu registry requires languages")
    for language, entry in languages.items():
        if not isinstance(language, str) or not language or not isinstance(entry, dict):
            raise SenseMenuPolicyError("sense-menu registry contains an invalid language")
        policy_id = entry.get("policy_id")
        provider = entry.get("provider")
        status = entry.get("audit_status")
        app_key = entry.get("app_key")
        if not isinstance(app_key, str) or not app_key:
            raise SenseMenuPolicyError(f"registry app key is missing for {language}")
        if not isinstance(policy_id, str) or not policy_id:
            raise SenseMenuPolicyError(f"registry policy is missing for {language}")
        if status not in AUDIT_STATUSES:
            raise SenseMenuPolicyError(f"registry audit status is invalid for {language}")
        policy = load_sense_menu_language_policy(
            repository_root, policy_id=policy_id, language=language
        )
        if policy.get("provider") != provider:
            raise SenseMenuPolicyError(f"registry provider disagrees with {policy_id}")
        if policy.get("audit_status") != status:
            raise SenseMenuPolicyError(f"registry audit status disagrees with {policy_id}")
    return registry
