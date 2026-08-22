"""Dependency-injected closed-menu WSD orchestration.

The runner owns decision order and trace semantics. Downloadable models remain
behind explicit interfaces, so importing this module never installs or loads ML.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fluency.core.hashing import validate_content_id
from fluency.wsd.alignment import AlignmentCorrector
from fluency.wsd.calibration import Calibrator
from fluency.wsd.contracts import SelectedTuple, WSDAssignment
from fluency.wsd.disposition import DispositionPolicy
from fluency.wsd.gloss_scoring import GlossScorer, LeafScore, validated_leaf_scores
from fluency.wsd.languages.base import LanguageAdapter
from fluency.wsd.menus import MenuAnalysis, require_analysis
from fluency.wsd.token_prototypes import TokenPrototypeReranker


@dataclass(frozen=True, slots=True)
class WSDExecutionProfile:
    token_tuple_vote: bool
    tuple_vote_minimum_margin: float
    calibration: bool
    alignment: bool
    generative_escalation: bool
    disposition: DispositionPolicy

    def __post_init__(self) -> None:
        if self.tuple_vote_minimum_margin < 0:
            raise ValueError("tuple vote margin must not be negative")
        if self.generative_escalation:
            raise ValueError("generative escalation is not implemented in the French audit profile")


@dataclass(frozen=True, slots=True)
class WSDComponents:
    language: LanguageAdapter
    gloss: GlossScorer
    token_reranker: TokenPrototypeReranker | None = None
    calibrator: Calibrator | None = None
    aligner: AlignmentCorrector | None = None


@dataclass(frozen=True, slots=True)
class WSDRequest:
    card_id: str
    surface_form: str
    sentence_id: str
    sentence: str
    translation: str
    sense_menu_content_id: str | None
    analyses: tuple[MenuAnalysis, ...]


class WSDConfigurationError(ValueError):
    """Raised when an execution profile could silently degrade."""


class ClosedMenuWSDRunner:
    def __init__(
        self,
        profile: WSDExecutionProfile,
        components: WSDComponents,
    ) -> None:
        self.profile = profile
        self.components = components
        required = (
            ("token reranker", profile.token_tuple_vote, components.token_reranker),
            ("calibrator", profile.calibration, components.calibrator),
            ("aligner", profile.alignment, components.aligner),
        )
        for name, enabled, component in required:
            if enabled and component is None:
                raise WSDConfigurationError(f"enabled {name} is unavailable")
            if not enabled and component is not None:
                raise WSDConfigurationError(
                    f"{name} was supplied but is not enabled by the exact profile"
                )
        if not components.gloss.model_revision:
            raise WSDConfigurationError("gloss model revision must be pinned")

    def _model_revisions(self) -> dict[str, str]:
        revisions = {"gloss": self.components.gloss.model_revision}
        if self.components.token_reranker is not None:
            revisions["token_reranker"] = self.components.token_reranker.model_revision
            revisions["token_prototypes"] = self.components.token_reranker.prototype_content_id
        if self.components.calibrator is not None:
            revisions["calibrator"] = self.components.calibrator.model_revision
            revisions["calibration_features"] = self.components.calibrator.feature_version
        if self.components.aligner is not None:
            revisions["alignment"] = self.components.aligner.model_revision
        return revisions

    def assign(self, request: WSDRequest) -> WSDAssignment:
        if not request.analyses:
            return WSDAssignment(
                card_id=request.card_id,
                surface_form=request.surface_form,
                sentence_id=request.sentence_id,
                status="no_menu",
                sense_menu_content_id=None,
                menu_analysis_id=None,
                selected_sense_id=None,
                selected_tuple=None,
                decision_path=(),
                evidence={"reason": "no_candidate_analysis"},
                confidence=None,
                model_revisions={},
            )
        if request.sense_menu_content_id is None:
            raise ValueError("menu-backed WSD requires a sense-menu content ID")
        validate_content_id(request.sense_menu_content_id)
        if any(analysis.card_id != request.card_id for analysis in request.analyses):
            raise ValueError("all candidate analyses must belong to the requested card")

        occurrences = self.components.language.locate(
            request.sentence, request.surface_form
        )
        if not occurrences:
            return WSDAssignment(
                card_id=request.card_id,
                surface_form=request.surface_form,
                sentence_id=request.sentence_id,
                status="abstained",
                sense_menu_content_id=request.sense_menu_content_id,
                menu_analysis_id=None,
                selected_sense_id=None,
                selected_tuple=None,
                decision_path=(),
                evidence={"reason": "surface_not_located"},
                confidence=None,
                model_revisions=self._model_revisions(),
            )

        ranked = validated_leaf_scores(
            self.components.gloss.score(request.sentence, request.analyses),
            request.analyses,
        )
        selected_score = ranked[0]
        decision_path = ["gloss"]
        evidence: dict[str, Any] = {
            "target_occurrences": [
                {"start": item.start, "end": item.end, "observed_text": item.observed_text}
                for item in occurrences
            ],
            "gloss_scores": [
                {
                    "menu_analysis_id": item.menu_analysis_id,
                    "sense_id": item.sense_id,
                    "score": item.score,
                }
                for item in ranked
            ],
        }

        if self.components.token_reranker is not None:
            vote = self.components.token_reranker.vote(
                request.sentence, request.surface_form, request.analyses
            )
            evidence["token_tuple_vote"] = (
                None
                if vote is None
                else {
                    "menu_analysis_id": vote.menu_analysis_id,
                    "score": vote.score,
                    "runner_up_score": vote.runner_up_score,
                    "margin": vote.margin,
                    "minimum_margin": self.profile.tuple_vote_minimum_margin,
                }
            )
            if vote is not None and vote.margin >= self.profile.tuple_vote_minimum_margin:
                require_analysis(request.analyses, vote.menu_analysis_id)
                selected_score = next(
                    score for score in ranked if score.menu_analysis_id == vote.menu_analysis_id
                )
                decision_path.append("token_tuple_vote")

        selected_analysis = require_analysis(
            request.analyses, selected_score.menu_analysis_id
        )
        selected_sense = selected_analysis.sense(selected_score.sense_id)
        confidence: float | None = None
        if self.components.calibrator is not None:
            calibration_path = tuple((*decision_path, "calibration"))
            confidence = self.components.calibrator.predict(
                sentence=request.sentence,
                analysis=selected_analysis,
                sense=selected_sense,
                scores=ranked,
                decision_path=calibration_path,
            )
            if not 0 <= confidence <= 1:
                raise ValueError("calibrator returned a value outside zero to one")
            decision_path.append("calibration")
            evidence["calibration"] = {"confidence": confidence}

        if self.components.aligner is not None:
            correction = self.components.aligner.correct(
                sentence=request.sentence,
                translation=request.translation,
                surface_form=request.surface_form,
                analyses=request.analyses,
                current_analysis_id=selected_analysis.menu_analysis_id,
                current_sense_id=selected_sense.sense_id,
            )
            evidence["alignment"] = None
            if correction is not None:
                corrected_analysis = require_analysis(
                    request.analyses, correction.menu_analysis_id
                )
                corrected_sense = corrected_analysis.sense(correction.sense_id)
                evidence["alignment"] = {
                    "from_menu_analysis_id": selected_analysis.menu_analysis_id,
                    "from_sense_id": selected_sense.sense_id,
                    "to_menu_analysis_id": correction.menu_analysis_id,
                    "to_sense_id": correction.sense_id,
                    "aligned_target": correction.aligned_target,
                    "aligned_translation": correction.aligned_translation,
                }
                if (
                    correction.menu_analysis_id != selected_analysis.menu_analysis_id
                    or correction.sense_id != selected_sense.sense_id
                ):
                    selected_analysis = corrected_analysis
                    selected_sense = corrected_sense
                    confidence = None
                    decision_path.append("alignment")

        status = self.profile.disposition.status(confidence)
        evidence["disposition"] = {
            "status": status,
            "minimum_confidence": self.profile.disposition.minimum_confidence,
            "weak": self.profile.disposition.weak,
        }
        if status != "assigned":
            return WSDAssignment(
                card_id=request.card_id,
                surface_form=request.surface_form,
                sentence_id=request.sentence_id,
                status=status,
                sense_menu_content_id=request.sense_menu_content_id,
                menu_analysis_id=None,
                selected_sense_id=None,
                selected_tuple=None,
                decision_path=tuple(decision_path),
                evidence=evidence,
                confidence=confidence,
                model_revisions=self._model_revisions(),
            )
        return WSDAssignment(
            card_id=request.card_id,
            surface_form=request.surface_form,
            sentence_id=request.sentence_id,
            status="assigned",
            sense_menu_content_id=request.sense_menu_content_id,
            menu_analysis_id=selected_analysis.menu_analysis_id,
            selected_sense_id=selected_sense.sense_id,
            selected_tuple=SelectedTuple(
                headword=selected_analysis.headword,
                part_of_speech=selected_analysis.part_of_speech,
            ),
            decision_path=tuple(decision_path),
            evidence=evidence,
            confidence=confidence,
            model_revisions=self._model_revisions(),
        )
