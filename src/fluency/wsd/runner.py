"""Dependency-injected closed-menu WSD orchestration.

The runner owns decision order and trace semantics. Downloadable models remain
behind explicit interfaces, so importing this module never installs or loads ML.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from fluency.core.hashing import validate_content_id
from fluency.wsd.alignment import AlignmentCorrector
from fluency.wsd.candidate_policy import CandidatePolicy
from fluency.wsd.calibration import Calibrator
from fluency.wsd.commit import CommitPolicy, decide as commit_decide
from fluency.wsd.contracts import (
    SelectedTuple,
    SelectionProjection,
    WSDAssignment,
)
from fluency.wsd.multiword import (
    MultiwordEntry,
    is_multiword_analysis,
    multiword_analyses,
    multiword_evidence,
)
from fluency.wsd.disposition import DispositionPolicy
from fluency.wsd.gloss_scoring import GlossScorer, LeafScore, validated_leaf_scores
from fluency.wsd.languages.base import LanguageAdapter
from fluency.wsd.menus import MenuAnalysis, require_analysis
from fluency.wsd.token_prototypes import TokenPrototypeReranker
from fluency.wsd.representations import RepresentationRef
from fluency.wsd.specialists import Specialist, build_case, run_specialists


@dataclass(frozen=True, slots=True)
class WSDExecutionProfile:
    token_tuple_vote: bool
    tuple_vote_minimum_margin: float
    calibration: bool
    alignment: bool
    generative_escalation: bool
    disposition: DispositionPolicy
    candidate_preparation: bool = False
    multiword_candidates: bool = False
    specialists: bool = False
    commit: CommitPolicy = CommitPolicy()

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
    candidate_policy: CandidatePolicy | None = None
    multiword_index: Mapping[str, Sequence[MultiwordEntry]] | None = None
    multiword_inventory_content_id: str | None = None
    specialists: tuple[Specialist, ...] = ()
    representations: Mapping[RepresentationRef, Any] | None = None
    context_model_revisions: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class WSDRequest:
    card_id: str
    surface_form: str
    sentence_id: str
    sentence: str
    translation: str
    sense_menu_content_id: str | None
    analyses: tuple[MenuAnalysis, ...]
    target_span: tuple[int, int] | None = None
    target_observed_form: str | None = None
    observed_pos: str | None = None
    observed_pos_evidence: Mapping[str, Any] | None = None


class WSDConfigurationError(ValueError):
    """Raised when an execution profile could silently degrade."""


def _score_for(
    scores: Sequence[LeafScore], menu_analysis_id: str, sense_id: str
) -> LeafScore:
    return next(
        item
        for item in scores
        if item.menu_analysis_id == menu_analysis_id and item.sense_id == sense_id
    )


def _selection_projection(
    *,
    selected: LeafScore,
    analysis: MenuAnalysis,
    ranked: Sequence[LeafScore],
    combined_ranked: Sequence[LeafScore],
    emitted_level: str,
    raw_axis_margins: Mapping[str, float],
) -> SelectionProjection:
    runner_up = next(
        (
            item
            for item in ranked
            if (item.menu_analysis_id, item.sense_id)
            != (selected.menu_analysis_id, selected.sense_id)
        ),
        None,
    )
    rank = next(
        index
        for index, item in enumerate(combined_ranked, start=1)
        if (item.menu_analysis_id, item.sense_id)
        == (selected.menu_analysis_id, selected.sense_id)
    )
    return SelectionProjection(
        menu_analysis_id=analysis.menu_analysis_id,
        selected_sense_id=selected.sense_id,
        selected_tuple=SelectedTuple(
            headword=analysis.headword,
            part_of_speech=analysis.part_of_speech,
        ),
        source_kind="multiword" if is_multiword_analysis(analysis) else "provider",
        selected_score=selected.score,
        runner_up_score=None if runner_up is None else runner_up.score,
        raw_margin=None if runner_up is None else selected.score - runner_up.score,
        rank=rank,
        emitted_level=emitted_level,
        raw_axis_margins=dict(raw_axis_margins),
    )


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
            ("candidate policy", profile.candidate_preparation, components.candidate_policy),
            ("multiword index", profile.multiword_candidates, components.multiword_index),
        )
        for name, enabled, component in required:
            if enabled and component is None:
                raise WSDConfigurationError(f"enabled {name} is unavailable")
            if not enabled and component is not None:
                raise WSDConfigurationError(
                    f"{name} was supplied but is not enabled by the exact profile"
                )
        if profile.specialists:
            if not components.specialists or components.representations is None:
                raise WSDConfigurationError(
                    "enabled specialists require pinned specialists and representations"
                )
        elif components.specialists or components.representations is not None:
            raise WSDConfigurationError(
                "specialist components were supplied but are not enabled by the exact profile"
            )
        if profile.multiword_candidates and (
            profile.token_tuple_vote or profile.calibration or profile.alignment
        ):
            raise WSDConfigurationError(
                "dual multiword projections are validated only for the gloss-only speech path"
            )
        if not components.gloss.model_revision:
            raise WSDConfigurationError("gloss model revision must be pinned")

    def _model_revisions(self) -> dict[str, str]:
        revisions = {
            "gloss": self.components.gloss.model_revision,
            **dict(self.components.context_model_revisions),
        }
        if self.components.token_reranker is not None:
            revisions["token_reranker"] = self.components.token_reranker.model_revision
            revisions["token_prototypes"] = self.components.token_reranker.prototype_content_id
        if self.components.calibrator is not None:
            revisions["calibrator"] = self.components.calibrator.model_revision
            revisions["calibration_features"] = self.components.calibrator.feature_version
        if self.components.aligner is not None:
            revisions["alignment"] = self.components.aligner.model_revision
        for specialist in self.components.specialists:
            revisions[f"specialist:{specialist.specialist_id}"] = specialist.model_revision
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

        if request.target_span is None:
            if request.target_observed_form is not None:
                raise ValueError("target observed form requires a persisted target span")
            occurrences = self.components.language.locate(request.sentence, request.surface_form)
        else:
            start, end = request.target_span
            if not (0 <= start < end <= len(request.sentence)):
                raise ValueError("target span falls outside the WSD context")
            observed = request.sentence[start:end]
            expected_observed = request.target_observed_form or request.surface_form
            if observed != expected_observed:
                raise ValueError("target span does not reproduce the persisted observed form")
            from fluency.wsd.languages.base import TargetOccurrence
            occurrences = (TargetOccurrence(observed, request.surface_form.casefold(), start, end),)
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

        provider_analyses = request.analyses
        preparation_evidence = None
        if self.components.candidate_policy is not None:
            prepared = self.components.candidate_policy.prepare(
                sentence=request.sentence,
                surface_form=request.surface_form,
                observed_pos=request.observed_pos,
                analyses=provider_analyses,
            )
            provider_analyses = prepared.analyses
            preparation_evidence = dict(prepared.evidence)
        if not provider_analyses:
            raise ValueError("candidate preparation cannot erase the complete provider menu")

        # Multiword senses join AFTER the constraint stage and BEFORE scoring.
        # After, because the POS and clitic rules were measured against the
        # provider menu alone and a synthetic PHRASE analysis is not what they
        # were calibrated on. Before, because the whole design is that a
        # multiword sense COMPETES on the same score rather than overriding one.
        multiword_records: list[dict[str, Any]] = []
        combined_analyses = provider_analyses
        if self.components.multiword_index is not None:
            for analysis, entry, span in multiword_analyses(
                card_id=request.card_id,
                surface_form=request.surface_form,
                sentence=request.sentence,
                index=self.components.multiword_index,
            ):
                combined_analyses = combined_analyses + (analysis,)
                multiword_records.append(
                    multiword_evidence(
                        analysis,
                        entry,
                        span,
                        inventory_content_id=self.components.multiword_inventory_content_id,
                    )
                )

        raw_combined_ranked = validated_leaf_scores(
            self.components.gloss.score(request.sentence, combined_analyses),
            combined_analyses,
        )
        combined_ranked = (
            raw_combined_ranked
            if self.components.candidate_policy is None
            else self.components.candidate_policy.adjust_scores(
                raw_combined_ranked, combined_analyses
            )
        )
        provider_ids = {analysis.menu_analysis_id for analysis in provider_analyses}
        provider_ranked = tuple(
            item for item in combined_ranked if item.menu_analysis_id in provider_ids
        )
        selected_score = provider_ranked[0]
        augmented_selected_score = combined_ranked[0]
        # `multiword` precedes `gloss` in DECISION_ORDER because the candidates
        # are added before scoring, so it is seeded rather than appended.
        decision_path = (
            (["constrain"] if preparation_evidence is not None else [])
            + (["multiword"] if multiword_records else [])
            + ["gloss"]
        )
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
                for item in combined_ranked
            ],
        }
        if request.observed_pos_evidence is not None:
            evidence["occurrence_pos"] = dict(request.observed_pos_evidence)
        if multiword_records:
            score_by_analysis = {
                item.menu_analysis_id: (rank, item.score)
                for rank, item in enumerate(combined_ranked, start=1)
            }
            provider_winner_score = provider_ranked[0].score
            for record in multiword_records:
                rank, score = score_by_analysis[record["menu_analysis_id"]]
                record.update(
                    {
                        "score": score,
                        "augmented_rank": rank,
                        "margin_over_provider_winner": score - provider_winner_score,
                    }
                )
            evidence["multiword_candidates"] = multiword_records
        if preparation_evidence is not None:
            evidence["candidate_preparation"] = preparation_evidence
            evidence["raw_gloss_scores"] = [
                {"menu_analysis_id": item.menu_analysis_id, "sense_id": item.sense_id, "score": item.score}
                for item in raw_combined_ranked
            ]
            constrained_ids = set(
                preparation_evidence.get("constraint_supported_analysis_ids") or ()
            )
            constrained = [
                item for item in provider_ranked if item.menu_analysis_id in constrained_ids
            ]
            evidence["constraint_aware_provider"] = (
                None
                if not constrained
                else {
                    "menu_analysis_id": constrained[0].menu_analysis_id,
                    "sense_id": constrained[0].sense_id,
                    "score": constrained[0].score,
                    "agrees_with_provider_only": constrained[0] == provider_ranked[0],
                }
            )

        if self.components.specialists:
            if len(occurrences) != 1:
                evidence["specialists"] = {
                    "status": "not_run_ambiguous_target_occurrence",
                    "occurrence_count": len(occurrences),
                }
            else:
                occurrence = occurrences[0]
                case = build_case(
                    language=self.components.language.language,
                    sentence=request.sentence,
                    target_span=(occurrence.start, occurrence.end),
                    surface_form=request.surface_form,
                    observed_pos=request.observed_pos,
                    analyses=combined_analyses,
                )
                evidence["specialists"] = {
                    "status": "evidence_only",
                    "results": run_specialists(
                        self.components.specialists,
                        case,
                        self.components.representations or {},
                    ),
                }

        if self.components.token_reranker is not None:
            vote = self.components.token_reranker.vote(
                request.sentence, request.surface_form, provider_analyses
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
                require_analysis(provider_analyses, vote.menu_analysis_id)
                selected_score = next(
                    score
                    for score in provider_ranked
                    if score.menu_analysis_id == vote.menu_analysis_id
                )
                decision_path.append("token_tuple_vote")

        selected_analysis = require_analysis(
            provider_analyses, selected_score.menu_analysis_id
        )
        if self.components.candidate_policy is not None:
            repaired = self.components.candidate_policy.repair_leaf(
                sentence=request.sentence,
                analyses=provider_analyses,
                selected=selected_score,
                ranked_scores=provider_ranked,
            )
            if repaired != selected_score:
                evidence["leaf_repair"] = {
                    "from_sense_id": selected_score.sense_id,
                    "to_sense_id": repaired.sense_id,
                    "menu_analysis_id": repaired.menu_analysis_id,
                }
                selected_score = repaired
                selected_analysis = require_analysis(
                    provider_analyses, repaired.menu_analysis_id
                )
                decision_path.append("leaf_repair")
            if multiword_records:
                augmented_selected_score = self.components.candidate_policy.repair_leaf(
                    sentence=request.sentence,
                    analyses=combined_analyses,
                    selected=augmented_selected_score,
                    ranked_scores=combined_ranked,
                )
        selected_sense = selected_analysis.sense(selected_score.sense_id)
        confidence: float | None = None
        if self.components.calibrator is not None:
            calibration_path = tuple((*decision_path, "calibration"))
            confidence = self.components.calibrator.predict(
                sentence=request.sentence,
                analysis=selected_analysis,
                sense=selected_sense,
                scores=provider_ranked,
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
                analyses=provider_analyses,
                current_analysis_id=selected_analysis.menu_analysis_id,
                current_sense_id=selected_sense.sense_id,
            )
            evidence["alignment"] = None
            if correction is not None:
                corrected_analysis = require_analysis(
                    provider_analyses, correction.menu_analysis_id
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
                    selected_score = _score_for(
                        provider_ranked,
                        corrected_analysis.menu_analysis_id,
                        corrected_sense.sense_id,
                    )
                    confidence = None
                    decision_path.append("alignment")

        # COMMIT. Decide how specific a claim to publish, and record whether a
        # choice was made at all. A single-candidate menu is a deterministic
        # default, not disambiguation, and must never be reported as though a
        # model chose between options.
        candidate_leaf_count = sum(
            len(analysis.senses) for analysis in provider_analyses
        )
        decision_kind = (
            "deterministic_default" if candidate_leaf_count <= 1 else "disambiguated"
        )
        commit_decision = commit_decide(
            provider_ranked, provider_analyses, self.profile.commit
        )
        emitted_level = commit_decision.level
        evidence["commit"] = {
            "selected_ref": {
                "menu_analysis_id": selected_analysis.menu_analysis_id,
                "sense_id": selected_sense.sense_id,
            },
            "emitted_level": emitted_level,
            "uncertain_axis": commit_decision.uncertain_axis,
            "raw_axis_margins": dict(commit_decision.margins),
            "axis_confidences": {"leaf": None, "glosskey": None, "tuple": None},
            "calibration": {"status": "unmeasured", "artifact_content_id": None},
            "escalate": commit_decision.escalate,
            "candidate_leaf_count": candidate_leaf_count,
            "decision_kind": decision_kind,
            "policy": {
                "leaf_minimum": self.profile.commit.leaf_minimum,
                "glosskey_minimum": self.profile.commit.glosskey_minimum,
                "tuple_minimum": self.profile.commit.tuple_minimum,
            },
        }
        if self.profile.commit.enabled:
            decision_path.append("commit")
        evidence["selected_multiword"] = None

        projections: dict[str, SelectionProjection] = {
            "provider_only": _selection_projection(
                selected=selected_score,
                analysis=selected_analysis,
                ranked=provider_ranked,
                combined_ranked=combined_ranked,
                emitted_level=emitted_level,
                raw_axis_margins=commit_decision.margins,
            )
        }
        if multiword_records:
            augmented_analysis = require_analysis(
                combined_analyses, augmented_selected_score.menu_analysis_id
            )
            augmented_commit = commit_decide(
                combined_ranked, combined_analyses, self.profile.commit
            )
            projections["mwe_augmented"] = _selection_projection(
                selected=augmented_selected_score,
                analysis=augmented_analysis,
                ranked=combined_ranked,
                combined_ranked=combined_ranked,
                emitted_level=augmented_commit.level,
                raw_axis_margins=augmented_commit.margins,
            )

        recommended_status = self.profile.disposition.status(confidence)
        evidence["disposition"] = {
            "status": "assigned",
            "recommended_publication_status": recommended_status,
            "minimum_confidence": self.profile.disposition.minimum_confidence,
            "weak": self.profile.disposition.weak,
        }
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
            emitted_level=emitted_level,
            decision_kind=decision_kind,
            selection_projections=projections,
            active_selection_projection="provider_only",
        )
