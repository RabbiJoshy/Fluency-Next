"""Fail-closed contracts for evidence-only WSD specialists."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping, Protocol, Sequence

from fluency.wsd.features import SpecialistFeature
from fluency.wsd.menus import MenuAnalysis
from fluency.wsd.representations import RepresentationRef


ASSESSMENTS = frozenset({"support", "reject", "unknown"})
Assessment = Literal["support", "reject", "unknown"]


@dataclass(frozen=True, slots=True)
class CandidateRef:
    menu_analysis_id: str
    sense_id: str

    def __post_init__(self) -> None:
        if not self.menu_analysis_id or not self.sense_id:
            raise ValueError("candidate reference requires exact leaf identity")

    def to_dict(self) -> dict[str, str]:
        return {
            "menu_analysis_id": self.menu_analysis_id,
            "sense_id": self.sense_id,
        }


@dataclass(frozen=True, slots=True)
class SpecialistCandidate:
    ref: CandidateRef
    part_of_speech: str
    features: tuple[SpecialistFeature, ...]


@dataclass(frozen=True, slots=True)
class SpecialistCase:
    language: str
    sentence: str
    target_span: tuple[int, int]
    surface_form: str
    observed_pos: str | None
    candidates: tuple[SpecialistCandidate, ...]


@dataclass(frozen=True, slots=True)
class SpecialistAssessment:
    candidate: CandidateRef
    assessment: Assessment
    confidence: float | None
    evidence: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.assessment not in ASSESSMENTS:
            raise ValueError("unsupported specialist assessment")
        if self.assessment == "unknown":
            if self.confidence is not None:
                raise ValueError("unknown specialist result cannot claim confidence")
        elif (
            not isinstance(self.confidence, (int, float))
            or isinstance(self.confidence, bool)
            or not 0.0 <= self.confidence <= 1.0
        ):
            raise ValueError("specialist support/reject requires confidence")
        if not isinstance(self.evidence, Mapping):
            raise ValueError("specialist evidence must be an object")

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate": self.candidate.to_dict(),
            "assessment": self.assessment,
            "confidence": self.confidence,
            "evidence": dict(self.evidence),
        }


class Specialist(Protocol):
    specialist_id: str
    model_revision: str

    def assess(
        self,
        case: SpecialistCase,
        representations: Mapping[RepresentationRef, Any],
    ) -> Sequence[SpecialistAssessment]: ...


def build_case(
    *,
    language: str,
    sentence: str,
    target_span: tuple[int, int],
    surface_form: str,
    observed_pos: str | None,
    analyses: Sequence[MenuAnalysis],
) -> SpecialistCase:
    return SpecialistCase(
        language=language,
        sentence=sentence,
        target_span=target_span,
        surface_form=surface_form,
        observed_pos=observed_pos,
        candidates=tuple(
            SpecialistCandidate(
                CandidateRef(analysis.menu_analysis_id, leaf.sense_id),
                analysis.part_of_speech,
                leaf.specialist_features,
            )
            for analysis in analyses
            for leaf in analysis.senses
        ),
    )


def run_specialists(
    specialists: Sequence[Specialist],
    case: SpecialistCase,
    representations: Mapping[RepresentationRef, Any],
) -> list[dict[str, Any]]:
    allowed = {candidate.ref for candidate in case.candidates}
    records: list[dict[str, Any]] = []
    for specialist in specialists:
        if not specialist.specialist_id or not specialist.model_revision:
            raise ValueError("specialist identity and revision must be pinned")
        results = tuple(specialist.assess(case, representations))
        if any(item.candidate not in allowed for item in results):
            raise ValueError("specialist assessed a candidate outside the case")
        records.append(
            {
                "specialist_id": specialist.specialist_id,
                "model_revision": specialist.model_revision,
                "policy": "evidence_only",
                "assessments": [item.to_dict() for item in results],
            }
        )
    return records
