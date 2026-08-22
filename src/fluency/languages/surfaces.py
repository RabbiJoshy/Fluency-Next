"""Explicit registry of language-specific surface normalizers."""

from __future__ import annotations

from collections.abc import Callable


def normalizer_for_language(language: str) -> Callable[[str], str]:
    if language == "fr":
        from fluency.languages.french.surfaces import normalize_surface

        return normalize_surface
    if language == "es":
        from fluency.languages.spanish.surfaces import normalize_surface

        return normalize_surface
    raise ValueError(f"no surface normalizer is registered for language: {language}")
