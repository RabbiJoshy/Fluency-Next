"""Stable, language-neutral records emitted by closed-menu WSD."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Literal, Mapping

from fluency.core.hashing import validate_content_id


WSD_ASSIGNMENT_VERSION = "wsd-assignment/v1"
WSD_STATUSES = frozenset({"assigned", "abstained", "rejected", "no_menu"})
DECISION_STAGES = frozenset(
    {"gloss", "token_tuple_vote", "leaf_repair", "calibration", "alignment"}
)
DECISION_ORDER = ("gloss", "token_tuple_vote", "leaf_repair", "calibration", "alignment")

AssignmentStatus = Literal["assigned", "abstained", "rejected", "no_menu"]
_CARD_ID = re.compile(r"^card_[a-z]{2,3}_[0-9a-f]{32}$")
_SENTENCE_ID = re.compile(r"^sentence_[0-9a-f]{32}$")
_ANALYSIS_ID = re.compile(r"^analysis_[0-9a-f]{32}$")


@dataclass(frozen=True, slots=True)
class SelectedTuple:
    headword: str
    part_of_speech: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.headword, str)
            or not self.headword.strip()
            or not isinstance(self.part_of_speech, str)
            or not self.part_of_speech.strip()
        ):
            raise ValueError("selected tuple fields must not be empty")

    def to_dict(self) -> dict[str, str]:
        return {
            "headword": self.headword,
            "part_of_speech": self.part_of_speech,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SelectedTuple":
        if not isinstance(value, Mapping):
            raise ValueError("selected_tuple must be an object")
        if set(value) != {"headword", "part_of_speech"}:
            raise ValueError("selected_tuple fields do not match the contract")
        return cls(
            headword=value["headword"],
            part_of_speech=value["part_of_speech"],
        )


@dataclass(frozen=True, slots=True)
class WSDAssignment:
    card_id: str
    surface_form: str
    sentence_id: str
    status: AssignmentStatus
    sense_menu_content_id: str | None
    menu_analysis_id: str | None
    selected_sense_id: str | None
    selected_tuple: SelectedTuple | None
    decision_path: tuple[str, ...]
    evidence: Mapping[str, Any]
    confidence: float | None
    model_revisions: Mapping[str, str]
    assignment_version: str = WSD_ASSIGNMENT_VERSION

    def __post_init__(self) -> None:
        if self.assignment_version != WSD_ASSIGNMENT_VERSION:
            raise ValueError("unsupported WSD assignment version")
        if not isinstance(self.card_id, str):
            raise ValueError("invalid card_id")
        if _CARD_ID.fullmatch(self.card_id) is None:
            raise ValueError("invalid card_id")
        if not isinstance(self.sentence_id, str):
            raise ValueError("invalid sentence_id")
        if _SENTENCE_ID.fullmatch(self.sentence_id) is None:
            raise ValueError("invalid sentence_id")
        if not isinstance(self.surface_form, str) or not self.surface_form.strip():
            raise ValueError("surface_form must not be empty")
        if self.status not in WSD_STATUSES:
            raise ValueError("invalid WSD status")
        if not isinstance(self.decision_path, tuple) or any(
            not isinstance(stage, str) for stage in self.decision_path
        ):
            raise ValueError("decision_path must contain strings")
        if len(self.decision_path) != len(set(self.decision_path)):
            raise ValueError("decision_path cannot repeat a stage")
        if any(stage not in DECISION_STAGES for stage in self.decision_path):
            raise ValueError("decision_path contains an unsupported stage")
        positions = [DECISION_ORDER.index(stage) for stage in self.decision_path]
        if positions != sorted(positions):
            raise ValueError("decision_path stages are out of canonical order")
        if self.confidence is not None and (
            not isinstance(self.confidence, (int, float))
            or isinstance(self.confidence, bool)
            or not 0.0 <= self.confidence <= 1.0
        ):
            raise ValueError("confidence must be between zero and one")
        if not isinstance(self.evidence, Mapping) or not isinstance(
            self.model_revisions, Mapping
        ):
            raise ValueError("evidence and model revisions must be objects")
        if any(
            not isinstance(name, str)
            or not name
            or not isinstance(revision, str)
            or not revision
            for name, revision in self.model_revisions.items()
        ):
            raise ValueError("model revision keys and values must not be empty")

        if self.status == "no_menu":
            if any(
                value is not None
                for value in (
                    self.sense_menu_content_id,
                    self.menu_analysis_id,
                    self.selected_sense_id,
                    self.selected_tuple,
                    self.confidence,
                )
            ):
                raise ValueError("no_menu assignments cannot claim menu or sense evidence")
            if self.decision_path:
                raise ValueError("no_menu assignments cannot have a decision path")
            return

        if self.sense_menu_content_id is None:
            raise ValueError("a menu-backed assignment requires sense_menu_content_id")
        validate_content_id(self.sense_menu_content_id)

        if self.status == "assigned":
            if self.menu_analysis_id is None or _ANALYSIS_ID.fullmatch(self.menu_analysis_id) is None:
                raise ValueError("assigned records require a valid menu_analysis_id")
            if not self.selected_sense_id or self.selected_tuple is None:
                raise ValueError("assigned records require an exact selected sense and tuple")
            if not self.decision_path:
                raise ValueError("assigned records require a decision path")
        elif any(
            value is not None
            for value in (self.menu_analysis_id, self.selected_sense_id, self.selected_tuple)
        ):
            raise ValueError("non-assigned records cannot claim a final sense")

    def to_dict(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            "assignment_version": self.assignment_version,
            "card_id": self.card_id,
            "surface_form": self.surface_form,
            "sentence_id": self.sentence_id,
            "status": self.status,
            "sense_menu_content_id": self.sense_menu_content_id,
            "menu_analysis_id": self.menu_analysis_id,
            "selected_sense_id": self.selected_sense_id,
            "selected_tuple": (
                None if self.selected_tuple is None else self.selected_tuple.to_dict()
            ),
            "decision_path": list(self.decision_path),
            "evidence": dict(self.evidence),
            "confidence": self.confidence,
            "model_revisions": dict(sorted(self.model_revisions.items())),
        }
        return record

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "WSDAssignment":
        if not isinstance(value, Mapping):
            raise ValueError("WSD assignment must be an object")
        expected = {
            "assignment_version",
            "card_id",
            "surface_form",
            "sentence_id",
            "status",
            "sense_menu_content_id",
            "menu_analysis_id",
            "selected_sense_id",
            "selected_tuple",
            "decision_path",
            "evidence",
            "confidence",
            "model_revisions",
        }
        if set(value) != expected:
            raise ValueError("WSD assignment fields do not match the contract")
        decision_path = value["decision_path"]
        evidence = value["evidence"]
        model_revisions = value["model_revisions"]
        if not isinstance(decision_path, list):
            raise ValueError("decision_path must be an array")
        if not isinstance(evidence, Mapping) or not isinstance(model_revisions, Mapping):
            raise ValueError("assignment evidence and model revisions must be objects")
        selected = value["selected_tuple"]
        return cls(
            assignment_version=value["assignment_version"],
            card_id=value["card_id"],
            surface_form=value["surface_form"],
            sentence_id=value["sentence_id"],
            status=value["status"],
            sense_menu_content_id=value["sense_menu_content_id"],
            menu_analysis_id=value["menu_analysis_id"],
            selected_sense_id=value["selected_sense_id"],
            selected_tuple=(None if selected is None else SelectedTuple.from_dict(selected)),
            decision_path=tuple(decision_path),
            evidence=dict(evidence),
            confidence=value["confidence"],
            model_revisions=dict(model_revisions),
        )
