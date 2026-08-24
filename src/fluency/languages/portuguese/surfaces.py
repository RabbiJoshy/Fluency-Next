"""Portuguese surface normalization for stable card identity."""

from __future__ import annotations

import re
import unicodedata

from fluency.core.identity import CardRecord, create_card_record


_WHITESPACE = re.compile(r"\s+")


def canonicalize_typography(text: str) -> str:
    """Normalize Unicode without casing or folding Portuguese word punctuation.

    Portuguese has no French-style elision, so the apostrophe is rare and is
    left exactly as observed; only Unicode composition is normalized.
    """

    if not isinstance(text, str):
        raise TypeError("text must be a string")
    return unicodedata.normalize("NFC", text)


def normalize_surface(surface: str) -> str:
    """Normalize typography without lemmatizing or folding Portuguese accents.

    Portuguese accents are contrastive at the surface (``e``/``é``, ``pais``/
    ``país``, ``esta``/``está``), so folding them would merge distinct cards.
    Hyphenated clitics (``dá-me``, ``vê-lo``) and mesoclisis (``far-me-ia``)
    are preserved verbatim: the complete observed surface is the identity, and
    any base headword is lookup metadata only.
    """

    if not isinstance(surface, str):
        raise TypeError("surface must be a string")
    normalized = unicodedata.normalize("NFC", surface)
    normalized = _WHITESPACE.sub(" ", normalized.strip()).lower()
    if not normalized:
        raise ValueError("surface must not be empty after normalization")
    return normalized


def create_portuguese_card(surface: str) -> CardRecord:
    """Create a Portuguese surface-card record from observed text."""

    surface_key = normalize_surface(surface)
    return create_card_record("pt", surface_key)
