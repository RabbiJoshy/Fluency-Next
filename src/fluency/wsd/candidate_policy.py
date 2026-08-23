"""Deterministic candidate preparation and provider-specific leaf repair.

These seams keep measured language/provider rules out of the shared scorer.
They operate only on the closed menu supplied by the request and may never
invent an analysis, headword, or sense.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence

from fluency.wsd.gloss_scoring import LeafScore
from fluency.wsd.menus import MenuAnalysis


@dataclass(frozen=True, slots=True)
class CandidatePreparation:
    analyses: tuple[MenuAnalysis, ...]
    evidence: Mapping[str, Any]


class CandidatePolicy(Protocol):
    method_id: str

    def prepare(
        self,
        *,
        sentence: str,
        surface_form: str,
        observed_pos: str | None,
        analyses: tuple[MenuAnalysis, ...],
    ) -> CandidatePreparation: ...

    def adjust_scores(
        self,
        scores: Sequence[LeafScore],
        analyses: tuple[MenuAnalysis, ...],
    ) -> tuple[LeafScore, ...]: ...

    def repair_leaf(
        self,
        *,
        sentence: str,
        analyses: tuple[MenuAnalysis, ...],
        selected: LeafScore,
        ranked_scores: Sequence[LeafScore],
    ) -> LeafScore: ...
