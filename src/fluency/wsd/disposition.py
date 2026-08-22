"""Explicit retain/reject/abstain policy; never inferred from mode."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


WeakDisposition = Literal["retain", "reject", "abstain"]


@dataclass(frozen=True, slots=True)
class DispositionPolicy:
    minimum_confidence: float | None
    weak: WeakDisposition

    def __post_init__(self) -> None:
        if self.weak not in {"retain", "reject", "abstain"}:
            raise ValueError("unsupported weak-score disposition")
        if self.minimum_confidence is not None and not 0 <= self.minimum_confidence <= 1:
            raise ValueError("minimum_confidence must be between zero and one")

    def status(self, confidence: float | None) -> str:
        if self.minimum_confidence is None or confidence is None:
            return "assigned"
        if confidence >= self.minimum_confidence or self.weak == "retain":
            return "assigned"
        return "rejected" if self.weak == "reject" else "abstained"
