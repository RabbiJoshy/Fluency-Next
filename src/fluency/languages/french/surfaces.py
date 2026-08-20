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


def normalize_surface(surface: str) -> str:
    """Return the French identity key without lemmatizing or accent folding."""

    if not isinstance(surface, str):
        raise TypeError("surface must be a string")

    normalized = unicodedata.normalize("NFC", surface)
    normalized = _WHITESPACE.sub(" ", normalized.strip())
    normalized = normalized.translate(_TYPOGRAPHIC_TRANSLATION)
    normalized = normalized.lower()
    if not normalized:
        raise ValueError("surface must not be empty after normalization")
    return normalized


def create_french_card(surface: str) -> CardRecord:
    """Create a French surface-card record from observed text."""

    surface_key = normalize_surface(surface)
    return create_card_record("fr", surface_key)

