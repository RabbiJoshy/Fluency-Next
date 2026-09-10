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
from fluency.features.metadata import MetadataAccounting
from fluency.features.parenthetical import leading_parenthetical, split_top_level_commas


# "[with com 'with something']", "[with gerund (Brazil) ...]"
_WITH_HEAD = re.compile(r"^\[with\s+(?P<word>[^\W\d_]+)", re.UNICODE)

# Fallbacks used when a language policy declares no vocabulary of its own.
DEFAULT_REGISTER_TAGS = frozenset(
    {"archaic", "colloquial", "dated", "derogatory", "dialectal", "euphemistic",
     "familiar", "figuratively", "formal", "humorous", "informal", "ironic",
     "literary", "mildly", "obsolete", "offensive", "pejorative", "poetic",
     "rare", "regional", "slang", "vulgar"}
)
DEFAULT_CONSTRUCTION_TAGS = frozenset(
    {"ambitransitive", "auxiliary", "copulative", "ditransitive", "impersonal",
     "intransitive", "pronominal", "transitive"}
)
STRUCTURAL_TAGS = frozenset({"alt-of", "form-of"})
GRAMMAR_TAG_VALUES = {
    "first-person": "person=1",
    "second-person": "person=2",
    "third-person": "person=3",
    "singular": "number=singular",
    "plural": "number=plural",
    "dual": "number=dual",
    "plural-only": "number=plural-only",
    "in-plural": "number=plural-only",
    "masculine": "gender=masculine",
    "feminine": "gender=feminine",
    "neuter": "gender=neuter",
    "common-gender": "gender=common",
    "animate": "animacy=animate",
    "inanimate": "animacy=inanimate",
    "nominative": "case=nominative",
    "accusative": "case=accusative",
    "dative": "case=dative",
    "genitive": "case=genitive",
    "instrumental": "case=instrumental",
    "locative": "case=locative",
    "vocative": "case=vocative",
    "imperative": "mood=imperative",
    "indicative": "mood=indicative",
    "subjunctive": "mood=subjunctive",
    "conditional": "mood=conditional",
    "present": "tense=present",
    "past": "tense=past",
    "future": "tense=future",
    "preterite": "tense=preterite",
    "imperfect": "tense=imperfect",
    "pluperfect": "tense=pluperfect",
    "perfective": "aspect=perfective",
    "imperfective": "aspect=imperfective",
    "comparative": "degree=comparative",
    "superlative": "degree=superlative",
    "not-comparable": "degree=not-comparable",
    "comparable": "degree=comparable",
    "indeclinable": "declension=none",
    "possessive": "possessive=true",
    "reflexive": "reflexive=true",
    "participle": "form=participle",
    "infinitive": "form=infinitive",
    "gerund": "form=gerund",
    "countable": "countability=countable",
    "uncountable": "countability=uncountable",
    "invariable": "inflection=invariable",
    "definite": "definiteness=definite",
    "indefinite": "definiteness=indefinite",
    "by-personal-gender": "gender=variable-by-person",
    "relational": "adjective-class=relational",
    "virile": "gender=virile",
    "nonvirile": "gender=nonvirile",
    "active": "voice=active",
    "passive": "voice=passive",
    "adjectival": "form=adjectival",
    "adverbial": "form=adverbial",
    "partitive": "case=partitive",
    "diminutive": "derivation=diminutive",
    "augmentative": "derivation=augmentative",
    "collective": "noun-class=collective",
    "animal-not-person": "animacy=animal-not-person",
    "defective": "inflection=defective",
    "plural-normally": "number=usually-plural",
    "singular-only": "number=singular-only",
    "no-plural": "number=no-plural",
    "gender-neutral": "gender=gender-neutral",
    "reciprocal": "reciprocal=true",
    "emphatic": "emphasis=emphatic",
    "interrogative": "function=interrogative",
    "relative": "function=relative",
    "objective": "case=objective",
    "apocopic": "form=apocopic",
    "catenative": "verb-class=catenative",
    "demonstrative": "pronoun-class=demonstrative",
    "cardinal": "numeral-class=cardinal",
    "ordinal": "numeral-class=ordinal",
}
FUNCTIONAL = re.compile(
    r"^used to (?:denote|express|form|indicate|introduce|mark|refer to|show)\b",
    re.IGNORECASE,
)


def _vocabulary(policy: Mapping[str, Any] | None, key: str, fallback: frozenset[str]):
    declared = (policy or {}).get(key)
    # Kaikki's general labels are shared by languages. A language policy adds
    # local vocabulary; it must not accidentally switch off the shared set by
    # declaring only the labels observed in one early audit.
    values = set(fallback)
    if isinstance(declared, list):
        values.update(str(value) for value in declared if str(value).strip())
    return values


def _grammar_value(
    tag: str, policy: Mapping[str, Any] | None = None
) -> str | None:
    language_values = (policy or {}).get("grammar_tags")
    if isinstance(language_values, Mapping):
        declared = language_values.get(tag)
        if isinstance(declared, str) and declared.strip():
            return declared
    return GRAMMAR_TAG_VALUES.get(tag.casefold())


def _is_construction_tag(tag: str, declared: set[str]) -> bool:
    lowered = tag.casefold()
    return lowered in declared or lowered.startswith("with-")


def classify_tag(
    tag: str, *, policy: Mapping[str, Any] | None = None
) -> SpecialistFeature | None:
    """Classify one provider tag without pretending unknown tags are empty."""

    register = _vocabulary(policy, "register_tags", DEFAULT_REGISTER_TAGS)
    construction = _vocabulary(policy, "construction_tags", DEFAULT_CONSTRUCTION_TAGS)
    regions = _vocabulary(policy, "region_tags", frozenset())
    domains = _vocabulary(policy, "domain_tags", frozenset())
    if tag in regions:
        return SpecialistFeature("register", "region", tag, tag)
    if tag in domains:
        return SpecialistFeature("domain", "domain_tag", tag, tag)
    if tag in register:
        return SpecialistFeature("register", "usage_tag", tag, tag)
    if (grammar_value := _grammar_value(tag, policy)) is not None:
        return SpecialistFeature("grammar", "sense_mark", grammar_value, tag)
    if _is_construction_tag(tag, construction):
        return SpecialistFeature("construction", "grammar_tag", tag, tag)
    return None


def metadata_accounting(
    sense: Mapping[str, Any],
    *,
    tags: Sequence[str] = (),
    policy: Mapping[str, Any] | None = None,
) -> MetadataAccounting:
    """Account for provider metadata not yet represented by typed features."""

    unclassified: list[dict[str, Any]] = []
    ignored: list[dict[str, Any]] = []
    policy_ignored = _vocabulary(policy, "ignored_tags", frozenset())
    for tag in sorted(set(tags)):
        if tag in STRUCTURAL_TAGS or tag in policy_ignored:
            ignored.append({
                "source_field": "tags",
                "value": tag,
                "reason": (
                    "dictionary relation handled during sense resolution"
                    if tag in STRUCTURAL_TAGS
                    else "provider label intentionally excluded by language policy"
                ),
            })
            continue
        if classify_tag(tag, policy=policy) is None:
            unclassified.append({
                "source_field": "tags",
                "value": tag,
                "reason": "no canonical tag mapping",
            })
    for template in sense.get("info_templates", []) or []:
        if not isinstance(template, Mapping):
            unclassified.append({
                "source_field": "info_templates",
                "value": template,
                "reason": "template is not an object",
            })
            continue
        name = template.get("name")
        if name != "+obj":
            unclassified.append({
                "source_field": "info_templates",
                "value": dict(template),
                "reason": "no canonical template mapping",
            })
    return MetadataAccounting(
        coverage={
            "cross_references": "parsed",
            "etymology": "preserved",
            "examples": "preserved",
            "info_templates": "parsed",
            "raw_glosses": "parsed",
            "tags": "parsed",
            "topics": "parsed",
        },
        unclassified=tuple(unclassified),
        ignored=tuple(ignored),
    )


def _split_parenthetical(sense: Mapping[str, Any]) -> list[str]:
    """Return comma-separated parts of a leading raw-gloss parenthetical."""

    raw_glosses = sense.get("raw_glosses")
    if not isinstance(raw_glosses, Sequence) or isinstance(raw_glosses, (str, bytes)):
        return []
    for raw in raw_glosses:
        if not isinstance(raw, str):
            continue
        parenthetical = leading_parenthetical(raw)
        if parenthetical:
            return split_top_level_commas(parenthetical)
    return []


def extract_surface_grammar(
    tags: Sequence[str], *, policy: Mapping[str, Any] | None = None
) -> tuple[SpecialistFeature, ...]:
    """Normalize Wiktionary form-of tags into provider-neutral grammar marks."""

    return tuple(
        SpecialistFeature("grammar", "surface_mark", value, tag)
        for tag in sorted(set(tags))
        if (value := _grammar_value(tag, policy)) is not None
    )


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
    regions = _vocabulary(policy, "region_tags", frozenset())

    features: list[SpecialistFeature] = []
    seen: set[tuple[str, str]] = set()
    topic_labels: set[str] = set()

    def add(family: str, kind: str, value: str) -> None:
        key = (family, value.lower())
        if key in seen:
            return
        seen.add(key)
        features.append(SpecialistFeature(family, kind, value, value))

    for topic in sense.get("topics", []) or []:
        if isinstance(topic, str) and topic.strip():
            clean_topic = topic.strip()
            topic_labels.add(clean_topic.casefold().replace("-", " "))
            add("domain", "topic", clean_topic)

    for tag in sorted(tags):
        feature = classify_tag(tag, policy=policy)
        if feature is not None:
            add(feature.family, feature.kind, feature.value)

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
        if part in regions:
            add("register", "region", part)
        elif lowered.replace("-", " ") in topic_labels:
            # Kaikki repeats structured topics in the display parenthetical,
            # sometimes changing hyphens to spaces ("card-games" / "card games").
            # The structured field is authoritative; do not retype it as prose.
            continue
        elif lowered in register:
            add("register", "gloss_note", part)
        elif (grammar_value := _grammar_value(lowered, policy)) is not None:
            add("grammar", "sense_mark", grammar_value)
        elif _is_construction_tag(lowered, construction):
            add("construction", "gloss_note", part)
        else:
            # Construction and frame notes written as prose. They are absent
            # from `tags` entirely, so nothing else in the pipeline carries them.
            add("construction", "gloss_phrase", part)

    for field in ("glosses", "raw_glosses"):
        values = sense.get(field)
        if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
            continue
        for value in values:
            if isinstance(value, str) and FUNCTIONAL.match(value.strip()) is not None:
                add("functional", "usage_note", value.strip())

    return tuple(features)
