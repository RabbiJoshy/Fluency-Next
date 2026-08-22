"""Language adapter protocol for locating an exact surface occurrence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class TargetOccurrence:
    observed_text: str
    surface_key: str
    start: int
    end: int


class LanguageAdapter(Protocol):
    language: str

    def locate(
        self,
        sentence: str,
        surface_form: str,
    ) -> tuple[TargetOccurrence, ...]: ...
