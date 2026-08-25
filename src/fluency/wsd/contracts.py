"""Stable, language-neutral records emitted by closed-menu WSD."""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any, Literal, Mapping

from fluency.core.hashing import validate_content_id


WSD_ASSIGNMENT_VERSION = "wsd-assignment/v1"
# `not_evaluated_example_cap` means no model looked at this occurrence, because
# its surface card had already reached the per-surface WSD execution cap. It is
# categorically different from `abstained`, which means a model looked and could
# not decide -- they say opposite things about the sense inventory, so an auditor
# must never see them merged.
WSD_STATUSES = frozenset(
    {"assigned", "abstained", "rejected", "no_menu", "not_evaluated_example_cap"}
)
# v6 reorganises the stages into three roles. `constrain` and `multiword` run
# before scoring, `commit` after it. The v5 names are retained so existing
# French and lyrics records keep validating -- this is additive.
DECISION_STAGES = frozenset(
    {
        "constrain",
        "multiword",
        "gloss",
        "token_tuple_vote",
        "leaf_repair",
        "calibration",
        "alignment",
        "commit",
    }
)
DECISION_ORDER = (
    "constrain",
    "multiword",
    "gloss",
    "token_tuple_vote",
    "leaf_repair",
    "calibration",
    "alignment",
    "commit",
)

AssignmentStatus = Literal[
    "assigned", "abstained", "rejected", "no_menu", "not_evaluated_example_cap"
]

# How much of the selected sense the card may publish. The selection is the same
# either way; a lower level is a narrower claim, not a different answer.
EMIT_LEVELS = frozenset({"leaf", "glosskey", "tuple", "unresolved"})
EmitLevel = Literal["leaf", "glosskey", "tuple", "unresolved"]

SELECTION_PROJECTION_NAMES = frozenset({"provider_only", "mwe_augmented"})
SelectionProjectionName = Literal["provider_only", "mwe_augmented"]
SELECTION_SOURCE_KINDS = frozenset({"provider", "multiword"})
SelectionSourceKind = Literal["provider", "multiword"]

# Requirement: a single-option menu is not disambiguation and must never be
# reported as though a model chose. The auditor already draws this line app-side
# for lyrics; this puts it in the contract so speech cannot lose it.
DECISION_KINDS = frozenset({"deterministic_default", "disambiguated"})
DecisionKind = Literal["deterministic_default", "disambiguated"]
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
class SelectionProjection:
    """One exact decision over a declared candidate universe.

    The raw scores and margins are diagnostic evidence, not calibrated
    confidence. ``emitted_level`` says how specific a claim this branch can
    publish while the exact IDs remain available for forced-leaf operation.
    """

    menu_analysis_id: str
    selected_sense_id: str
    selected_tuple: SelectedTuple
    source_kind: SelectionSourceKind
    selected_score: float
    runner_up_score: float | None
    raw_margin: float | None
    rank: int
    emitted_level: EmitLevel
    raw_axis_margins: Mapping[str, float]

    def __post_init__(self) -> None:
        if _ANALYSIS_ID.fullmatch(self.menu_analysis_id) is None:
            raise ValueError("selection projection requires a valid analysis ID")
        if not isinstance(self.selected_sense_id, str) or not self.selected_sense_id:
            raise ValueError("selection projection requires a sense ID")
        if self.source_kind not in SELECTION_SOURCE_KINDS:
            raise ValueError("selection projection source kind is invalid")
        for name, value in (
            ("selected_score", self.selected_score),
            ("runner_up_score", self.runner_up_score),
            ("raw_margin", self.raw_margin),
        ):
            if value is not None and (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(value)
            ):
                raise ValueError(f"selection projection {name} must be finite")
        if not isinstance(self.rank, int) or isinstance(self.rank, bool) or self.rank < 1:
            raise ValueError("selection projection rank must be positive")
        if self.emitted_level not in EMIT_LEVELS:
            raise ValueError("selection projection emitted level is invalid")
        if set(self.raw_axis_margins) != {"leaf", "glosskey", "tuple"} or any(
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
            or not 0.0 <= value <= 1.0
            for value in self.raw_axis_margins.values()
        ):
            raise ValueError("selection projection axis margins are invalid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "menu_analysis_id": self.menu_analysis_id,
            "selected_sense_id": self.selected_sense_id,
            "selected_tuple": self.selected_tuple.to_dict(),
            "source_kind": self.source_kind,
            "selected_score": self.selected_score,
            "runner_up_score": self.runner_up_score,
            "raw_margin": self.raw_margin,
            "rank": self.rank,
            "emitted_level": self.emitted_level,
            "raw_axis_margins": dict(self.raw_axis_margins),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SelectionProjection":
        if not isinstance(value, Mapping):
            raise ValueError("selection projection must be an object")
        expected = {
            "menu_analysis_id", "selected_sense_id", "selected_tuple", "source_kind",
            "selected_score", "runner_up_score", "raw_margin", "rank",
            "emitted_level", "raw_axis_margins",
        }
        if set(value) != expected:
            raise ValueError("selection projection fields do not match the contract")
        margins = value["raw_axis_margins"]
        if not isinstance(margins, Mapping):
            raise ValueError("selection projection margins must be an object")
        return cls(
            menu_analysis_id=value["menu_analysis_id"],
            selected_sense_id=value["selected_sense_id"],
            selected_tuple=SelectedTuple.from_dict(value["selected_tuple"]),
            source_kind=value["source_kind"],
            selected_score=value["selected_score"],
            runner_up_score=value["runner_up_score"],
            raw_margin=value["raw_margin"],
            rank=value["rank"],
            emitted_level=value["emitted_level"],
            raw_axis_margins=dict(margins),
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
    emitted_level: EmitLevel | None = None
    decision_kind: DecisionKind | None = None
    selection_projections: Mapping[SelectionProjectionName, SelectionProjection] | None = None
    active_selection_projection: SelectionProjectionName | None = None
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
            if self.emitted_level is not None or self.selection_projections is not None:
                raise ValueError("no_menu assignments cannot claim a publication decision")
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
            if self.emitted_level is not None and self.emitted_level not in EMIT_LEVELS:
                raise ValueError("unsupported emitted level")
            if self.decision_kind is not None and self.decision_kind not in DECISION_KINDS:
                raise ValueError("unsupported decision kind")
            if self.selection_projections is not None:
                if not isinstance(self.selection_projections, Mapping):
                    raise ValueError("selection projections must be an object")
                keys = set(self.selection_projections)
                if (
                    not keys
                    or "provider_only" not in keys
                    or not keys <= SELECTION_PROJECTION_NAMES
                    or any(not isinstance(item, SelectionProjection) for item in self.selection_projections.values())
                ):
                    raise ValueError("selection projections do not match the contract")
                if self.active_selection_projection not in keys:
                    raise ValueError("active selection projection is unavailable")
                active = self.selection_projections[self.active_selection_projection]
                if (
                    active.menu_analysis_id != self.menu_analysis_id
                    or active.selected_sense_id != self.selected_sense_id
                    or active.selected_tuple != self.selected_tuple
                    or active.emitted_level != (self.emitted_level or "leaf")
                ):
                    raise ValueError("top-level selection must materialize the active projection")
            elif self.active_selection_projection is not None:
                raise ValueError("active projection requires selection projections")
        elif any(
            value is not None
            for value in (self.menu_analysis_id, self.selected_sense_id, self.selected_tuple)
        ):
            raise ValueError("non-assigned records cannot claim a final sense")
        elif any(
            value is not None
            for value in (self.emitted_level, self.decision_kind, self.selection_projections, self.active_selection_projection)
        ):
            raise ValueError("non-assigned records cannot claim a publication decision")

    @property
    def supported_level(self) -> EmitLevel | None:
        """Clear Python name for the backwards-compatible wire field."""

        return self.emitted_level

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
        # Emitted only when set, so records written before v6 -- the French and
        # lyrics demonstrations -- keep round-tripping through the exact-key
        # check in from_dict.
        if self.emitted_level is not None:
            record["emitted_level"] = self.emitted_level
        if self.decision_kind is not None:
            record["decision_kind"] = self.decision_kind
        if self.selection_projections is not None:
            record["selection_projections"] = {
                name: projection.to_dict()
                for name, projection in sorted(self.selection_projections.items())
            }
            record["active_selection_projection"] = self.active_selection_projection
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
        optional = {
            "emitted_level", "decision_kind", "selection_projections",
            "active_selection_projection",
        }
        keys = set(value)
        if not expected <= keys or not keys <= expected | optional:
            raise ValueError("WSD assignment fields do not match the contract")
        decision_path = value["decision_path"]
        evidence = value["evidence"]
        model_revisions = value["model_revisions"]
        if not isinstance(decision_path, list):
            raise ValueError("decision_path must be an array")
        if not isinstance(evidence, Mapping) or not isinstance(model_revisions, Mapping):
            raise ValueError("assignment evidence and model revisions must be objects")
        selected = value["selected_tuple"]
        raw_projections = value.get("selection_projections")
        if raw_projections is not None and not isinstance(raw_projections, Mapping):
            raise ValueError("selection_projections must be an object")
        return cls(
            emitted_level=value.get("emitted_level"),
            decision_kind=value.get("decision_kind"),
            selection_projections=(
                None
                if raw_projections is None
                else {
                    name: SelectionProjection.from_dict(projection)
                    for name, projection in raw_projections.items()
                }
            ),
            active_selection_projection=value.get("active_selection_projection"),
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
