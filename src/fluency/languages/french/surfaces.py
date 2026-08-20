"""French surface normalization for stable card identity."""

from __future__ import annotations

import re
import unicodedata

from fluency.core.identity import CardRecord, create_card_record


_WHITESPACE = re.compile(r"\s+")
_TYPOGRAPHIC_TRANSLATION = str.maketrans(
    {
        "'": "’",       # ASCII apostrophe
        "‘": "’",       # left single quotation mark
        "ʼ": "’",       # modifier letter apostrophe
        "‐": "-",       # Unicode hyphen
        "‑": "-",       # non-breaking hyphen
    }
)


def canonicalize_typography(text: str) -> str:
    """Normalize Unicode and equivalent French word punctuation without casing."""

    if not isinstance(text, str):
        raise TypeError("text must be a string")
    return unicodedata.normalize("NFC", text).translate(_TYPOGRAPHIC_TRANSLATION)


def normalize_surface(surface: str) -> str:
    """Return the French identity key without lemmatizing or accent folding."""

    if not isinstance(surface, str):
        raise TypeError("surface must be a string")

    normalized = canonicalize_typography(surface)
    normalized = _WHITESPACE.sub(" ", normalized.strip())
    normalized = normalized.lower()
    if not normalized:
        raise ValueError("surface must not be empty after normalization")
    return normalized


def create_french_card(surface: str) -> CardRecord:
    """Create a French surface-card record from observed text."""

    surface_key = normalize_surface(surface)
    return create_card_record("fr", surface_key)
