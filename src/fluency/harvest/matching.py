"""Language-configured normalization, matching, gates, and easiness scoring."""

from __future__ import annotations

import math
import re
import unicodedata
from typing import Any


class SurfaceMatcher:
    def __init__(self, cards: list[dict[str, Any]], language_policy: dict[str, Any]):
        self.policy = language_policy
        self.token_re = re.compile(language_policy["matching"]["token_pattern"], re.UNICODE)
        normalized: dict[str, dict[str, Any]] = {}
        for card in cards:
            key = self.normalize(card["display_form"])
            if key in normalized:
                raise ValueError(f"surface normalization collision: {key!r}")
            normalized[key] = card
        self.cards_by_match = normalized
        alternatives = [self._literal_pattern(value) for value in sorted(normalized, key=len, reverse=True)]
        self.pattern = re.compile("|".join(f"(?:{value})" for value in alternatives), re.UNICODE)

    def normalize(self, text: str) -> str:
        policy = self.policy["normalization"]
        value = unicodedata.normalize(policy["unicode_form"], text)
        for apostrophe in policy["apostrophe_variants"]:
            value = value.replace(apostrophe, policy["canonical_apostrophe"])
        if policy["casefold"]:
            value = value.casefold()
        if policy["collapse_whitespace"]:
            value = " ".join(value.split())
        return value

    @staticmethod
    def _is_word_character(value: str) -> bool:
        return bool(value) and (value[-1].isalnum() or value[-1] == "_")

    def _literal_pattern(self, surface: str) -> str:
        escaped = re.escape(surface).replace(r"\ ", r"\s+")
        left = r"(?<!\w)" if self._is_word_character(surface[:1]) else ""
        right = r"(?!\w)" if self._is_word_character(surface[-1:]) else ""
        return f"{left}{escaped}{right}"

    def find_cards(self, text: str) -> list[dict[str, Any]]:
        normalized_text = self.normalize(text)
        found: dict[str, dict[str, Any]] = {}
        for match in self.pattern.finditer(normalized_text):
            key = " ".join(match.group(0).split())
            card = self.cards_by_match.get(key)
            if card is not None:
                found[card["card_id"]] = card
        return list(found.values())

    def tokens(self, text: str) -> list[str]:
        return [self.normalize(token) for token in self.token_re.findall(text)]


def quality_rejection(
    target: str,
    translation: str,
    *,
    matcher: SurfaceMatcher,
    shared_policy: dict[str, Any],
) -> str | None:
    quality = shared_policy["quality"]
    language_rules = matcher.policy["sentence_rules"]
    target_tokens = matcher.tokens(target)
    translation_tokens = re.findall(r"[^\W\d_]+(?:['’-][^\W\d_]+)*", translation, re.UNICODE)
    if len(target_tokens) < quality["minimum_target_tokens"]:
        return "target_too_short"
    if len(target_tokens) > quality["maximum_target_tokens"]:
        return "target_too_long"
    if len(translation_tokens) < quality["minimum_translation_tokens"]:
        return "translation_too_short"
    if len(translation_tokens) > quality["maximum_translation_tokens"]:
        return "translation_too_long"
    ratio = len(translation_tokens) / max(len(target_tokens), 1)
    if not quality["minimum_translation_ratio"] <= ratio <= quality["maximum_translation_ratio"]:
        return "translation_length_ratio"
    # An example has to show a word doing something. Easiness counts how many
    # UNFAMILIAR words a learner must get past and skips the target itself, so
    # "Nao, nao, nao, nao, nao, nao" scores a perfect 0.0 and wins every
    # ranking. Repetition is a property of the sentence rather than of any one
    # card, so it is judged here, before a card is known.
    minimum_distinct = quality.get("minimum_distinct_tokens", 0)
    if minimum_distinct and len(set(target_tokens)) < minimum_distinct:
        return "insufficient_distinct_tokens"
    if quality["reject_identical_sides"] and matcher.normalize(target) == matcher.normalize(translation):
        return "identical_sides"
    if quality["reject_all_caps"] and target.isupper() and any(char.isalpha() for char in target):
        return "target_all_caps"
    if quality["reject_markup"] and any(char in target or char in translation for char in "<>"):
        return "markup"
    if language_rules["reject_contains_apostrophe"] and any(char in target for char in "'’"):
        return "language_apostrophe_rule"
    if language_rules["reject_contains_hyphen"] and "-" in target:
        return "language_hyphen_rule"
    if any(value in target or value in translation for value in language_rules["forbidden_substrings"]):
        return "language_forbidden_text"
    return None


def easiness_metrics(
    target: str,
    card: dict[str, Any],
    *,
    matcher: SurfaceMatcher,
    frequency_ranks: dict[str, int],
    shared_policy: dict[str, Any],
) -> dict[str, float | int]:
    policy = shared_policy["easiness"]
    tokens = matcher.tokens(target)
    surface_tokens = set(matcher.tokens(card["display_form"]))
    target_rank = card["rank"]
    unranked = policy["unranked_assumed_rank"]
    costs: list[float] = []
    harder = 0
    for token in dict.fromkeys(tokens):
        if token in surface_tokens:
            continue
        rank = frequency_ranks.get(token, unranked)
        if rank > target_rank:
            harder += 1
            costs.append(math.log10(rank / max(target_rank, 1)))
    costs.sort(reverse=True)
    burden = 0.0
    if costs:
        burden = policy["first_new_word_discount"] * costs[0] + sum(costs[1:])
    length = len(tokens)
    length_penalty = (
        policy["short_penalty_weight"] * max(0, policy["preferred_minimum_tokens"] - length)
        + policy["long_penalty_weight"] * max(0, length - policy["preferred_maximum_tokens"])
    )
    return {
        "score": round(burden + length_penalty, 6),
        "frequency_burden": round(burden, 6),
        "length_penalty": round(length_penalty, 6),
        "target_tokens": length,
        "harder_tokens": harder,
    }
