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

from fluency.features.contract import SpecialistFeature


PARENTHETICAL = re.compile(r"^\((?P<context>[^)]{2,60})\)\s*\S")

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
