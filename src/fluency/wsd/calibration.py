"""Path-specific confidence calibration contracts."""

from __future__ import annotations

from typing import Protocol, Sequence

from fluency.wsd.gloss_scoring import LeafScore
from fluency.wsd.menus import MenuAnalysis, SenseLeaf


class Calibrator(Protocol):
    model_revision: str
    feature_version: str

    def predict(
        self,
        *,
        sentence: str,
        analysis: MenuAnalysis,
        sense: SenseLeaf,
        scores: Sequence[LeafScore],
        decision_path: tuple[str, ...],
    ) -> float: ...
