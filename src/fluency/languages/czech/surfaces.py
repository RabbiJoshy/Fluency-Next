"""Czech surface normalization for stable card identity."""

from __future__ import annotations

import re
import unicodedata

from fluency.core.identity import CardRecord, create_card_record


_WHITESPACE = re.compile(r"\s+")


def canonicalize_typography(text: str) -> str:
    """Normalize Unicode without casing or folding Czech word punctuation.

    Czech writes no elision, so the apostrophe appears only in loans and is
    left exactly as observed; only Unicode composition is normalized. NFC
    matters more here than in Portuguese because háček and čárka are very
    often supplied as combining marks.
    """

    if not isinstance(text, str):
        raise TypeError("text must be a string")
    return unicodedata.normalize("NFC", text)


def normalize_surface(surface: str) -> str:
    """Normalize typography without lemmatizing or folding Czech diacritics.

    Czech diacritics are contrastive at the surface and folding them would
    merge distinct cards: ``byt``/``být`` (flat/to be), ``mate``/``máte``
    (you confuse/you have), ``dela``/``dělá`` (does). The length marks are not
    decoration, so the complete observed surface is the identity and any base
    headword is lookup metadata only.

    Czech is heavily inflected, and each inflected form is its own observed
    surface. That is the same rule every other language here follows; it simply
    produces many more cards per lemma than Portuguese or Spanish does.
    """

    if not isinstance(surface, str):
        raise TypeError("surface must be a string")
    normalized = unicodedata.normalize("NFC", surface)
    normalized = _WHITESPACE.sub(" ", normalized.strip()).lower()
    if not normalized:
        raise ValueError("surface must not be empty after normalization")
    return normalized


def create_czech_card(surface: str) -> CardRecord:
    """Create a Czech surface-card record from observed text."""

    surface_key = normalize_surface(surface)
    return create_card_record("cs", surface_key)
