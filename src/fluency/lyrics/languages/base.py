"""Shared interface for language-specific Lyrics normalization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class NormalizedUnit:
    form: str
    operation: str
    reason_code: str


class LyricsLanguageAdapter(Protocol):
    language: str
    method_id: str

    def normalize(self, surface: str, *, previous: str | None, following: str | None) -> tuple[NormalizedUnit, ...]: ...

