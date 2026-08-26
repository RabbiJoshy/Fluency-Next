"""Extract provider-neutral features from Wiktionary sense records.

Separated from the sense-menu adapter so that adding or retyping a feature does
not mean editing the dictionary reader, and so the tag vocabulary can live in
language policy rather than in code. Which Portuguese tag counts as "register"
is language knowledge; the adapter should not be the place it is written down.

Wiktionary states the same thing in three places and they need different
handling:

* ``topics``    - domain labels, already discrete.
* ``tags``      - a flat list mixing register and grammatical marks.
* ``raw_glosses`` - a leading parenthetical carrying whichever of those the
  editor chose to write as prose, plus construction notes that appear nowhere
  else ("only in subordinate clauses", "followed by an infinitive").

The parenthetical is the reason this module exists: roughly 42% of what it
carries is absent from ``tags``, and it is construction material -- decidable
from a parse rather than from topical similarity.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from fluency.features.contract import GRAMMATICAL_FORMS, SpecialistFeature


PARENTHETICAL = re.compile(r"^\((?P<context>[^)]{2,60})\)\s*\S")
# "[with com 'with something']", "[with gerund (Brazil) ...]"
_WITH_HEAD = re.compile(r"^\[with\s+(?P<word>[^\W\d_]+)", re.UNICODE)

# Fallbacks used when a language policy declares no vocabulary of its own.
DEFAULT_REGISTER_TAGS = frozenset(
    {"archaic", "colloquial", "dated", "formal", "informal", "obsolete",
     "offensive", "poetic", "slang", "vulgar", "euphemistic"}
)
DEFAULT_CONSTRUCTION_TAGS = frozenset(
    {"auxiliary", "copulative", "ditransitive", "impersonal", "intransitive",
     "pronominal", "reflexive", "transitive"}
)


def _vocabulary(policy: Mapping[str, Any] | None, key: str, fallback: frozenset[str]):
    declared = (policy or {}).get(key)
    if isinstance(declared, list) and declared:
        return {str(value) for value in declared}
    return set(fallback)


def _split_parenthetical(sense: Mapping[str, Any]) -> list[str]:
    """Return comma-separated parts of a leading raw-gloss parenthetical."""

    raw_glosses = sense.get("raw_glosses")
    if not isinstance(raw_glosses, Sequence) or isinstance(raw_glosses, (str, bytes)):
        return []
    for raw in raw_glosses:
        if not isinstance(raw, str):
            continue
        match = PARENTHETICAL.match(raw)
        if match:
            return [part.strip() for part in match.group("context").split(",") if part.strip()]
    return []


def extract(
    sense: Mapping[str, Any],
    *,
    tags: Sequence[str] = (),
    policy: Mapping[str, Any] | None = None,
) -> tuple[SpecialistFeature, ...]:
    """Return typed features for one Wiktionary sense.

    Deduplicated by (family, value): the same mark routinely appears both as a
    tag and inside the parenthetical, and one sense should not be scored twice
    for saying a thing twice.
    """

    register = _vocabulary(policy, "register_tags", DEFAULT_REGISTER_TAGS)
    construction = _vocabulary(policy, "construction_tags", DEFAULT_CONSTRUCTION_TAGS)

    features: list[SpecialistFeature] = []
    seen: set[tuple[str, str]] = set()

    def add(family: str, kind: str, value: str) -> None:
        key = (family, value.lower())
        if key in seen:
            return
        seen.add(key)
        features.append(SpecialistFeature(family, kind, value, value))

    for topic in sense.get("topics", []) or []:
        if isinstance(topic, str) and topic.strip():
            add("domain", "topic", topic.strip())

    for tag in sorted(tags):
        if tag in register:
            add("register", "usage_tag", tag)
        elif tag in construction:
            add("construction", "grammar_tag", tag)

    # The companion note: SpanishDict writes this as prose in `context`,
    # Wiktionary as a structured +obj template. Both emit the same family so a
    # gate never has to know which provider it is reading.
    for template in sense.get("info_templates", []) or []:
        if not isinstance(template, dict) or template.get("name") != "+obj":
            continue
        # The expansion is structured -- "[with com 'with something']" -- while
        # extra_data.words is fragments of it, so the first alpha token there is
        # as likely to be "or" or "(Brazil)" as the companion.
        expansion = str(template.get("expansion") or "").strip()
        head = _WITH_HEAD.match(expansion)
        companion = head.group("word") if head else None
        if companion and companion.lower() in GRAMMATICAL_FORMS:
            companion = None
        if companion:
            add("companion", "required_word", companion.strip().lower())
        elif expansion:
            # "[with adjective]", "[with gerund]" -- a form, not a word to look
            # for, so it constrains construction rather than companionship.
            add("construction", "companion_form", expansion)

    for part in _split_parenthetical(sense):
        lowered = part.lower()
        if lowered in register:
            add("register", "gloss_note", part)
        elif lowered in construction:
            add("construction", "gloss_note", part)
        else:
            # Construction and frame notes written as prose. They are absent
            # from `tags` entirely, so nothing else in the pipeline carries them.
            add("construction", "gloss_phrase", part)

    return tuple(features)
