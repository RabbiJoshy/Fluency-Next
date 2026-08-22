"""Interfaces and validation for sentence-to-gloss retrieval."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Protocol, Sequence

from fluency.wsd.menus import MenuAnalysis


@dataclass(frozen=True, slots=True)
class LeafScore:
    menu_analysis_id: str
    sense_id: str
    score: float

    def __post_init__(self) -> None:
        if not self.menu_analysis_id or not self.sense_id:
            raise ValueError("leaf score identity must not be empty")
        if not math.isfinite(self.score):
            raise ValueError("leaf score must be finite")


class GlossScorer(Protocol):
    model_revision: str

    def score(
        self,
        sentence: str,
        analyses: tuple[MenuAnalysis, ...],
    ) -> Sequence[LeafScore]: ...


def validated_leaf_scores(
    scores: Sequence[LeafScore],
    analyses: tuple[MenuAnalysis, ...],
) -> tuple[LeafScore, ...]:
    expected = {
        (analysis.menu_analysis_id, sense.sense_id)
        for analysis in analyses
        for sense in analysis.senses
    }
    actual = [(score.menu_analysis_id, score.sense_id) for score in scores]
    if len(actual) != len(set(actual)):
        raise ValueError("gloss scorer returned duplicate leaf scores")
    if set(actual) != expected:
        raise ValueError("gloss scorer must score every and only candidate leaf")
    return tuple(sorted(scores, key=lambda item: (-item.score, item.menu_analysis_id, item.sense_id)))
