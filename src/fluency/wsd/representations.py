"""Sparse, typed representation requests for optional WSD specialists.

The baseline still embeds the complete gloss.  A specialist may additionally
request only the channel it understands.  Exact texts are exposed separately so
vector caches can deduplicate the same domain label across many leaves.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence

from fluency.wsd.menus import MenuAnalysis


REPRESENTATION_CHANNELS = frozenset(
    {"full_gloss", "domain", "register", "construction"}
)
RepresentationChannel = Literal["full_gloss", "domain", "register", "construction"]


@dataclass(frozen=True, slots=True)
class RepresentationRef:
    menu_analysis_id: str
    sense_id: str
    channel: RepresentationChannel
    feature_kind: str | None = None
    feature_value: str | None = None

    def __post_init__(self) -> None:
        if not self.menu_analysis_id or not self.sense_id:
            raise ValueError("representation reference requires exact leaf identity")
        if self.channel not in REPRESENTATION_CHANNELS:
            raise ValueError("unsupported representation channel")
        if self.channel == "full_gloss":
            if self.feature_kind is not None or self.feature_value is not None:
                raise ValueError("full-gloss references cannot claim a sparse feature")
        elif not self.feature_kind or not self.feature_value:
            raise ValueError("sparse representation requires feature identity")


@dataclass(frozen=True, slots=True)
class RepresentationRequest:
    ref: RepresentationRef
    text: str

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("representation text must not be empty")


@dataclass(frozen=True, slots=True)
class UnavailableRepresentation:
    menu_analysis_id: str
    sense_id: str
    channel: RepresentationChannel
    reason: str


@dataclass(frozen=True, slots=True)
class RepresentationPlan:
    requests: tuple[RepresentationRequest, ...]
    unavailable: tuple[UnavailableRepresentation, ...]

    @property
    def unique_texts(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(request.text for request in self.requests))


def plan_representations(analyses: Sequence[MenuAnalysis]) -> RepresentationPlan:
    requests: list[RepresentationRequest] = []
    unavailable: list[UnavailableRepresentation] = []
    for analysis in analyses:
        for leaf in analysis.senses:
            if leaf.gloss_text.strip():
                requests.append(
                    RepresentationRequest(
                        RepresentationRef(
                            analysis.menu_analysis_id, leaf.sense_id, "full_gloss"
                        ),
                        leaf.gloss_text,
                    )
                )
            else:
                unavailable.append(
                    UnavailableRepresentation(
                        analysis.menu_analysis_id,
                        leaf.sense_id,
                        "full_gloss",
                        "empty_gloss",
                    )
                )
            for feature in leaf.specialist_features:
                requests.append(
                    RepresentationRequest(
                        RepresentationRef(
                            analysis.menu_analysis_id,
                            leaf.sense_id,
                            feature.family,
                            feature.kind,
                            feature.value,
                        ),
                        feature.embedding_text,
                    )
                )
    return RepresentationPlan(tuple(requests), tuple(unavailable))
