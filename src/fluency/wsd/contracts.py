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
        if not self.headword.strip() or not self.part_of_speech.strip():
            raise ValueError("selected tuple fields must not be empty")

    def to_dict(self) -> dict[str, str]:
        return {
            "headword": self.headword,
            "part_of_speech": self.part_of_speech,
        }


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
        if _CARD_ID.fullmatch(self.card_id) is None:
            raise ValueError("invalid card_id")
        if _SENTENCE_ID.fullmatch(self.sentence_id) is None:
            raise ValueError("invalid sentence_id")
        if not isinstance(self.surface_form, str) or not self.surface_form.strip():
            raise ValueError("surface_form must not be empty")
        if self.status not in WSD_STATUSES:
            raise ValueError("invalid WSD status")
        if len(self.decision_path) != len(set(self.decision_path)):
            raise ValueError("decision_path cannot repeat a stage")
        if any(stage not in DECISION_STAGES for stage in self.decision_path):
            raise ValueError("decision_path contains an unsupported stage")
        positions = [DECISION_ORDER.index(stage) for stage in self.decision_path]
        if positions != sorted(positions):
            raise ValueError("decision_path stages are out of canonical order")
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between zero and one")
        if any(not name or not revision for name, revision in self.model_revisions.items()):
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
