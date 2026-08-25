"""Explicit registry of language-specific surface normalizers."""

from __future__ import annotations

from collections.abc import Callable


def normalizer_for_language(language: str) -> Callable[[str], str]:
    if language == "fr":
        from fluency.languages.french.surfaces import normalize_surface

        return normalize_surface
    if language == "pt":
        from fluency.languages.portuguese.surfaces import normalize_surface

        return normalize_surface
    if language == "es":
        from fluency.languages.spanish.surfaces import normalize_surface

        return normalize_surface
    raise ValueError(f"no surface normalizer is registered for language: {language}")


def typography_canonicalizer_for_language(language: str) -> Callable[[str], str]:
    """Return the language's case-preserving typography canonicalizer.

    Used where a raw dictionary headword must be compared against an observed
    surface without casefolding it first.
    """

    if language == "fr":
        from fluency.languages.french.surfaces import canonicalize_typography

        return canonicalize_typography
    if language == "pt":
        from fluency.languages.portuguese.surfaces import canonicalize_typography

        return canonicalize_typography
    raise ValueError(
        f"no typography canonicalizer is registered for language: {language}"
    )
