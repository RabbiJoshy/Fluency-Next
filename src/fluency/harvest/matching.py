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


def example_identity(text: str) -> str:
    """What makes two sentences the same example.

    A corpus row is not an example. Subtitles carry the same line in many films
    and repeat it with a speaker dash, an ellipsis, or different terminal
    punctuation; those are one example seen several times, not several examples.
    Identity is the sequence of words, ignoring case, accent form, and
    everything that is not a word. Accents are preserved: pais and pais are
    distinct Portuguese words and must never merge.
    """

    return " ".join(
        re.findall(r"[^\W\d_]+", unicodedata.normalize("NFC", text).casefold(), re.UNICODE)
    )


def detect_variety(text: str, language_policy: dict[str, Any]) -> str | None:
    """Which regional variety a sentence announces, if any.

    A deck can be European or Brazilian Portuguese from ONE harvest only if the
    harvest records which each sentence is. Markers are lexical and structural,
    so a sentence carrying none is undetectable rather than neutral: 65.5% of
    the Portuguese bank is unmarked and some of it is quietly Brazilian.

    Recorded, never filtered. Which variety a learner is shown is a selection
    decision that can be retuned; what the pool contains cannot be, without
    harvesting again.
    """

    markers = language_policy.get("variety_markers") or {}
    hits = [
        name
        for name, patterns in markers.items()
        if any(re.search(p, text, re.IGNORECASE | re.UNICODE) for p in patterns)
    ]
    return hits[0] if len(hits) == 1 else None


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
    distinct_tokens = len(set(target_tokens))
    minimum_distinct = quality.get("minimum_distinct_tokens", 0)
    if minimum_distinct and distinct_tokens < minimum_distinct:
        return "insufficient_distinct_tokens"
    # A count alone cannot tell a short sentence from an echoed one: "Isso nao e
    # o que e." carries five distinct words in six, while "O que? O que e que
    # eu..." carries four in seven. Judge how much of the sentence is new.
    minimum_ratio = quality.get("minimum_distinct_ratio", 0.0)
    if minimum_ratio and target_tokens and distinct_tokens / len(target_tokens) < minimum_ratio:
        return "echoed_target"
    # A subtitle cut mid-thought is not an example. "Isso nao e o que eu..."
    # is grammatical, survives every other rule, and teaches nothing, because
    # the clause the target word belongs to was never finished. Leading and
    # trailing ellipsis are the marker OpenSubtitles uses for the cut.
    if quality.get("reject_truncated_fragments"):
        stripped = target.strip()
        if stripped.startswith(("...", "\u2026")) or stripped.endswith(("...", "\u2026")):
            return "truncated_fragment"
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
    # A subtitle row is a slice of a stream, so a row can begin partway through
    # a sentence and end partway through another. Both leave a fragment that
    # reads as broken language rather than as an example: "- zustal pres noc a
    # pak se vratil." starts mid-clause, and "...do sveho stareho zivota," stops
    # before the clause closes. Measured on Czech, 3.4% and 0.7% of displayed
    # examples; on Portuguese, 0.4% and 0.3%.
    stripped = target.strip().lstrip("\"'\u00ab([-\u2013\u2014 ")
    if quality.get("reject_lowercase_start") and stripped[:1].islower():
        return "starts_mid_sentence"
    if quality.get("reject_unterminated") and target.strip().endswith((",", ";", ":")):
        return "ends_mid_sentence"
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
    # Burden counts each distinct word once, so length must too. Measuring
    # length over raw tokens made repetition free AND rewarded: a repeated word
    # added nothing to burden while padding the sentence past the short-sentence
    # penalty, so "Nao, nao, nao, nao, nao, nao" scored a perfect 0.0 and won
    # every ranking. A sentence's substance is how many different words it uses.
    length = len(dict.fromkeys(tokens))
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
