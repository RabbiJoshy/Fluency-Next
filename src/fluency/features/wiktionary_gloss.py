"""Conservative projections for metadata embedded inside Wiktionary glosses.

Most trailing parentheses explain meaning and must remain visible. This module
only removes notes whose wording identifies them as grammar or usage metadata;
semantic parentheticals continue to pass through byte-for-byte.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from fluency.features.contract import SpecialistFeature


@dataclass(frozen=True, slots=True)
class GlossReference:
    relation: str
    target: str


@dataclass(frozen=True, slots=True)
class GlossProjection:
    display_text: str
    specialist_features: tuple[SpecialistFeature, ...] = ()
    cross_references: tuple[GlossReference, ...] = ()


_TARGET = r"[\wÀ-ɏ-]+"
_OBJECT_PRONOUN_SEE = re.compile(
    rf"^(?P<display>.+?) \(as a direct object; as an indirect object, see "
    rf"(?P<indirect>{_TARGET}); after prepositions, see (?P<preposition>{_TARGET})\)$",
    re.IGNORECASE,
)
_OBJECT_PRONOUN_FORMS = re.compile(
    rf"^(?P<display>.+?) \(as a direct object; the corresponding indirect object is "
    rf"(?P<indirect>{_TARGET}); the form used after prepositions is "
    rf"(?P<preposition>{_TARGET})\)$",
    re.IGNORECASE,
)

_FUNCTIONAL_NOTE = re.compile(
    r"^(?:used to |indicat(?:e|es|ing) |express(?:es|ing) |denot(?:e|es|ing) "
    r"|mark(?:s|ing) |refer(?:s|ring) to |show(?:s|ing) )",
    re.IGNORECASE,
)
_CONSTRUCTION_NOTE = re.compile(
    r"^(?:after |before |connecting |followed by |only (?:in|with) |preceding "
    r"|takes? |used (?:before|in|with) |when referring to |with )",
    re.IGNORECASE,
)

# A trailing note is grammar only when every word belongs to this deliberately
# small vocabulary. Requiring a closed vocabulary prevents semantic phrases
# such as ``female partner`` and ``formal dance`` from being stripped merely
# because they contain one grammatical-looking word.
_GRAMMAR_NOTE_WORDS = frozenset({
    "1st", "2nd", "3rd", "a", "an", "and", "direct", "disjunctive",
    "female", "familiar", "feminine", "first", "formal", "informal",
    "indirect", "male", "masculine", "neuter", "object", "of", "only",
    "or", "person", "personal", "plural", "possessive", "pronoun",
    "reflexive", "second", "singular", "subject", "the", "third", "verb",
})
_GRAMMAR_NOTE_SIGNALS = frozenset({
    "1st", "2nd", "3rd", "direct", "first", "indirect", "personal",
    "plural", "possessive", "pronoun", "reflexive", "second", "singular",
    "third",
})
_GRAMMAR_GENDER_WORDS = frozenset({"female", "feminine", "male", "masculine", "neuter"})


def _is_grammar_note(note: str) -> bool:
    words = re.findall(r"[a-z0-9]+", note.casefold().replace("‑", "-"))
    if not words or not all(word in _GRAMMAR_NOTE_WORDS for word in words):
        return False
    # A lone gender label is conventional dictionary metadata. In a longer
    # phrase, however, ``female partner`` and ``male person`` describe the
    # referent and belong in the meaning text.
    if len(words) == 1 and words[0] in _GRAMMAR_GENDER_WORDS:
        return True
    return bool(set(words) & _GRAMMAR_NOTE_SIGNALS)


def _note_family(note: str) -> str | None:
    if _FUNCTIONAL_NOTE.match(note):
        return "functional"
    if _CONSTRUCTION_NOTE.match(note):
        return "construction"
    if _is_grammar_note(note):
        return "grammar"
    return None


def _note_feature(note: str) -> SpecialistFeature:
    family = _note_family(note)
    if family is None:  # Guarded by _trailing_parentheticals.
        raise ValueError("unrecognized Wiktionary gloss note")
    kind = "usage_note" if family == "functional" else (
        "gloss_note" if family == "grammar" else "gloss_phrase"
    )
    return SpecialistFeature(family, kind, note, note)


def _trailing_parentheticals(text: str) -> tuple[str, tuple[str, ...]]:
    """Split balanced trailing parentheticals without touching inner brackets."""

    remaining = text.rstrip()
    notes: list[str] = []
    while remaining.endswith(")"):
        depth = 0
        opening = None
        for index in range(len(remaining) - 1, -1, -1):
            character = remaining[index]
            if character == ")":
                depth += 1
            elif character == "(":
                depth -= 1
                if depth == 0:
                    opening = index
                    break
        if opening is None or opening == 0 or not remaining[opening - 1].isspace():
            break
        note = remaining[opening + 1:-1].strip()
        if not note or _note_family(note) is None:
            break
        notes.insert(0, note)
        remaining = remaining[:opening].rstrip()
    return remaining, tuple(notes)


def project_gloss(text: str) -> GlossProjection:
    """Separate clearly marked grammar/usage notes from a display gloss."""

    for pattern in (_OBJECT_PRONOUN_SEE, _OBJECT_PRONOUN_FORMS):
        match = pattern.fullmatch(text)
        if match is None:
            continue
        return GlossProjection(
            display_text=match.group("display"),
            specialist_features=(
                SpecialistFeature(
                    "construction",
                    "object_role",
                    "direct object",
                    "used as a direct object",
                ),
            ),
            cross_references=(
                GlossReference("indirect_object", match.group("indirect")),
                GlossReference("after_prepositions", match.group("preposition")),
            ),
        )
    display_text, notes = _trailing_parentheticals(text)
    if not notes:
        return GlossProjection(display_text=text)
    return GlossProjection(
        display_text=display_text,
        specialist_features=tuple(_note_feature(note) for note in notes),
    )
