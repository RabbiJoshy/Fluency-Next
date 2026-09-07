"""Conservative projections for metadata embedded inside Wiktionary glosses.

Most trailing parentheses explain meaning and must remain visible.  This module
recognizes only the two object-pronoun templates observed in the source data;
everything else passes through byte-for-byte.
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


def project_gloss(text: str) -> GlossProjection:
    """Separate only known grammatical routing notes from a display gloss."""

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
    return GlossProjection(display_text=text)
