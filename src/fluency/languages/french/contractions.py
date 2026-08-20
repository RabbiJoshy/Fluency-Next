"""Structural French contraction metadata, separate from card identity."""

from __future__ import annotations

from dataclasses import dataclass

from fluency.languages.french.surfaces import normalize_surface
from fluency.languages.french.tokenization import load_tokenization_config


@dataclass(frozen=True, slots=True)
class ContractionAnalysis:
    surface_key: str
    components: tuple[str, ...]
    grammatical_roles: tuple[str, ...]


def analyze_contraction(surface: str) -> ContractionAnalysis | None:
    surface_key = normalize_surface(surface)
    specification = load_tokenization_config().contractions.get(surface_key)
    if specification is None:
        return None
    return ContractionAnalysis(
        surface_key=surface_key,
        components=tuple(specification["components"]),
        grammatical_roles=tuple(specification["grammatical_roles"]),
    )

