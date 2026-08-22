"""Optional language-scoped token-vector tuple voting contracts."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Protocol

from fluency.wsd.menus import MenuAnalysis


@dataclass(frozen=True, slots=True)
class TupleVote:
    menu_analysis_id: str
    score: float
    runner_up_score: float

    def __post_init__(self) -> None:
        if not self.menu_analysis_id:
            raise ValueError("tuple vote requires a menu analysis ID")
        if not math.isfinite(self.score) or not math.isfinite(self.runner_up_score):
            raise ValueError("tuple vote scores must be finite")

    @property
    def margin(self) -> float:
        return self.score - self.runner_up_score


class TokenPrototypeReranker(Protocol):
    model_revision: str
    prototype_content_id: str

    def vote(
        self,
        sentence: str,
        surface_form: str,
        analyses: tuple[MenuAnalysis, ...],
    ) -> TupleVote | None: ...
