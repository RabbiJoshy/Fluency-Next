"""Conservative surface normalization shared by minimally scaffolded languages."""

from __future__ import annotations

import re
import unicodedata


_WHITESPACE = re.compile(r"\s+")
_TYPOGRAPHIC_TRANSLATION = str.maketrans({
    "’": "'", "‘": "'", "ʼ": "'", "‛": "'", "＇": "'",
    "‐": "-", "‑": "-",
})


def canonicalize_word_typography(text: str) -> str:
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    return unicodedata.normalize("NFC", text).translate(_TYPOGRAPHIC_TRANSLATION)


def normalize_word_surface(surface: str) -> str:
    """Preserve letters and diacritics; normalize only equivalent typography."""

    normalized = canonicalize_word_typography(surface)
    normalized = _WHITESPACE.sub(" ", normalized.strip()).lower()
    if not normalized:
        raise ValueError("surface must not be empty after normalization")
    return normalized
