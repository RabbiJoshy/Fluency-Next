"""Parallel-translation sparse leaf correction contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from fluency.wsd.menus import MenuAnalysis


@dataclass(frozen=True, slots=True)
class AlignmentCorrection:
    menu_analysis_id: str
    sense_id: str
    aligned_target: str
    aligned_translation: str


class AlignmentCorrector(Protocol):
    model_revision: str

    def correct(
        self,
        *,
        sentence: str,
        translation: str,
        surface_form: str,
        analyses: tuple[MenuAnalysis, ...],
        current_analysis_id: str,
        current_sense_id: str,
    ) -> AlignmentCorrection | None: ...
