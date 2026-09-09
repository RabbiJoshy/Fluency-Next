"""Minimal Russian surface identity support."""

from fluency.core.identity import CardRecord, create_card_record
from fluency.languages.common import canonicalize_word_typography, normalize_word_surface


canonicalize_typography = canonicalize_word_typography
normalize_surface = normalize_word_surface


def create_russian_card(surface: str) -> CardRecord:
    return create_card_record("ru", normalize_surface(surface))
