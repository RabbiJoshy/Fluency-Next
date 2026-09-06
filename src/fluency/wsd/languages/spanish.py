"""Measured SpanishDict candidate policy used by ``sd-beto-cal-v5``.

This is a clean port of the deterministic parts of the current Spanish v5
method: bridged occurrence POS filtering, the conservative ``se`` gate, the
SpanishDict menu-order prior, and renderable-leaf repair. Surface-card identity
is never replaced by a lemma or dictionary headword.
"""

from __future__ import annotations

from dataclasses import replace
import re
import unicodedata
from typing import Callable, Sequence

from fluency.wsd.companion_gate import (
    companion_satisfied as normalized_companion_satisfied,
    filter_by_companion,
    required_companions,
)
from fluency.wsd.candidate_policy import CandidatePreparation
from fluency.wsd.grammar_gate import filter_by_grammar
from fluency.wsd.gloss_scoring import LeafScore
from fluency.wsd.languages.base import TargetOccurrence
from fluency.wsd.menus import MenuAnalysis, SenseLeaf, require_analysis


WORD_RE = re.compile(r"[a-záéíóúüñ0-9]+")
CLITICS = frozenset({"me", "te", "se", "nos", "os", "lo", "la", "le", "los", "las", "les"})
ORTHOGONAL_POS = frozenset({"PHRASE"})
TRUSTED_POS = frozenset({"VERB", "NOUN", "ADJ", "ADV", "INTJ"})
POS_BRIDGE = {
    "DET": frozenset({"ADJ", "DET", "PRON"}),
    "PRON": frozenset({"PRON", "ADJ", "DET"}),
    "NUM": frozenset({"ADJ", "NOUN", "DET"}),
    "PART": frozenset({"ADV", "ADP", "PRON"}),
    "PROPN": frozenset({"PROPN", "NOUN"}),
    "ADV": frozenset({"ADV", "PRON", "ADJ"}),
    "AUX": frozenset({"VERB", "AUX", "PHRASE"}),
    # spaCy tags Spanish contractions such as ``al`` and ``del`` as ADP while
    # SpanishDict files their ordinary analyses as CONTRACTION.
    "ADP": frozenset({"ADP", "CONTRACTION"}),
}
# AUX is the same UD/SpanishDict mismatch as DET and was missed when DET was
# bridged. SpanishDict has no AUX category and files every auxiliary and modal
# as VERB, while the tagger emits AUX. Unbridged, this function rejects VERB
# *and* NOUN for an AUX token, so every analysis fails, the caller's
# empty-set fallback fires, and the filter becomes a silent no-op on
# `haber, ser, estar, deber, saber` -- the commonest verbs in speech.
#
# Measured in the reference repository on a 200-item panel stratified for hard
# words: adding this entry took the POS filter over the menu prior from 67.3%
# to 74.4%, +14 items of 199. That panel is 35% AUX by construction, so the
# deck-wide value is proportionally smaller; the bug is real, its headline size
# is inflated. It measures -1 on the older, easier 144-item panel, which is why
# it read as noise there.
def _deaccent(value: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFD", value.casefold())
        if unicodedata.category(character) != "Mn"
    )


def sense_compatible_bridged(sense_pos: str, observed_pos: str) -> bool:
    sense_pos = str(sense_pos or "").upper()
    observed_pos = str(observed_pos or "").upper()
    if sense_pos in ORTHOGONAL_POS:
        return True
    bridged = POS_BRIDGE.get(observed_pos)
    if bridged is not None:
        return sense_pos in bridged
    if sense_pos == observed_pos:
        return True
    if observed_pos in TRUSTED_POS:
        return False
    return sense_pos not in TRUSTED_POS


def _feature_signature(leaf: SenseLeaf) -> tuple[tuple[str, str, str], ...]:
    return tuple(sorted(
        (str(feature.family), str(feature.kind), str(feature.value))
        for feature in leaf.specialist_features
    ))


def _indistinguishable_leaf_refs(
    analyses: Sequence[MenuAnalysis],
) -> list[dict[str, str]]:
    """Leaves whose Spanish-side descriptions provide no way to separate them."""

    refs: list[dict[str, str]] = []
    for analysis in analyses:
        groups: dict[tuple[str, tuple[tuple[str, str, str], ...]], list[SenseLeaf]] = {}
        for leaf in analysis.senses:
            signature = (leaf.definition.casefold().strip(), _feature_signature(leaf))
            groups.setdefault(signature, []).append(leaf)
        for siblings in groups.values():
            translations = {leaf.translation.casefold().strip() for leaf in siblings}
            if len(siblings) < 2 or len(translations) < 2:
                continue
            refs.extend(
                {
                    "menu_analysis_id": analysis.menu_analysis_id,
                    "sense_id": leaf.sense_id,
                }
                for leaf in siblings
            )
    return refs


def se_reflexive_evidence(
    surface_form: str,
    sentence: str,
    observed_grammar: dict[str, str] | None = None,
) -> bool | None:
    """Return the exact conservative v5 ``se-only`` gate evidence."""

    raw_surface = surface_form.casefold()
    surface = _deaccent(surface_form)
    # Speech inventories can contain an enclitic surface (``diviértanse``).
    # Looking only to the left mislabels it as non-reflexive even though the
    # clitic is fused into the observed token.
    # Check before removing accents. ``pensé`` becomes ``pense`` after accent
    # removal and was therefore mistaken for an enclitic reflexive.
    if (
        raw_surface.endswith("se")
        and len(raw_surface) > 2
        and (observed_grammar or {}).get("mood") not in {"indicative", "subjunctive"}
    ):
        return True
    tokens = WORD_RE.findall(_deaccent(sentence))
    try:
        target_index = tokens.index(surface)
    except ValueError:
        return None
    index = target_index
    cluster: list[str] = []
    index -= 1
    while index >= 0 and tokens[index] in CLITICS:
        cluster.append(tokens[index])
        index -= 1
    if "se" in cluster:
        if any(item in cluster for item in ("lo", "la", "los", "las")):
            return False
        if target_index + 1 < len(tokens) and tokens[target_index + 1] == "que":
            return False
        return True
    return False if not cluster else None


def leaf_renderable(leaf: SenseLeaf) -> bool:
    return bool(leaf.translation.strip())


def companion_satisfied(leaf: SenseLeaf, sentence: str) -> bool:
    return normalized_companion_satisfied(leaf.specialist_features, sentence)


class SpanishV5CandidatePolicy:
    method_id = "spanish-v5-candidate-policy/v1"

    def __init__(
        self,
        *,
        menu_prior: float = 0.02,
        menu_prior_decay: float = 0.5,
        constraint_mode: str = "filter",
        sense_compatible: Callable[[str, str], bool] | None = None,
        pos_is_orthogonal: Callable[[str], bool] | None = None,
        clitic_gate: bool = True,
        normalized_leaf_gates: bool = False,
    ) -> None:
        # The POS gate is a property of the DICTIONARY, not the language: the
        # bridge below reconciles a tagger's UD tags with SpanishDict's tagset.
        # A Wiktionary-backed language must supply its own, or the filter
        # deletes correct senses on the commonest words -- measured at 12 of the
        # 13 most frequent Portuguese surfaces.
        self._sense_compatible = sense_compatible or sense_compatible_bridged
        self._pos_is_orthogonal = pos_is_orthogonal or (
            lambda value: str(value or "").upper() in ORTHOGONAL_POS
        )
        if menu_prior < 0 or not 0 < menu_prior_decay <= 1:
            raise ValueError("invalid Spanish menu-prior parameters")
        if constraint_mode not in {"filter", "evidence_only"}:
            raise ValueError("unsupported Spanish constraint mode")
        self.menu_prior = menu_prior
        self.menu_prior_decay = menu_prior_decay
        self.constraint_mode = constraint_mode
        self.clitic_gate = clitic_gate
        self.normalized_leaf_gates = normalized_leaf_gates

    def prepare(
        self,
        *,
        sentence: str,
        surface_form: str,
        observed_pos: str | None,
        observed_grammar: dict[str, str] | None = None,
        analyses: tuple[MenuAnalysis, ...],
    ) -> CandidatePreparation:
        keep_ids = {analysis.menu_analysis_id for analysis in analyses}
        pos_removed: list[str] = []
        pos_match_status = "not_observed"
        pos_match_kind = "not_observed"
        if observed_pos:
            def phrase_matches_imperative(analysis: MenuAnalysis) -> bool:
                return (
                    analysis.part_of_speech == "PHRASE"
                    and observed_pos == "VERB"
                    and (observed_grammar or {}).get("mood") == "imperative"
                    and any(
                        feature.family == "grammar"
                        and feature.value == "mood=imperative"
                        for leaf in analysis.senses
                        for feature in leaf.specialist_features
                    )
                )

            compatible = {
                analysis.menu_analysis_id
                for analysis in analyses
                # Synthetic multiword PHRASE analyses are added only after this
                # provider gate. A SpanishDict PHRASE row is therefore not an
                # orthogonal MWE candidate: treating it as one is what allowed
                # renderings such as ``está`` -> "he's" to beat the verb menu.
                if phrase_matches_imperative(analysis)
                or (
                    not self._pos_is_orthogonal(analysis.part_of_speech)
                    and self._sense_compatible(analysis.part_of_speech, observed_pos)
                )
            }
            if compatible:
                pos_match_status = "matched"
                exact = {
                    analysis.menu_analysis_id
                    for analysis in analyses
                    if str(analysis.part_of_speech or "").upper()
                    == str(observed_pos).upper()
                }
                pos_match_kind = "exact" if compatible & exact else "bridged_only"
                pos_removed = sorted(keep_ids - compatible)
                keep_ids &= compatible
            else:
                pos_match_status = "no_compatible_analysis"
                pos_match_kind = "none"

        evidence = (
            se_reflexive_evidence(surface_form, sentence, observed_grammar)
            if self.clitic_gate
            else None
        )
        # In ``se ha ido`` / ``se está haciendo``, ``se`` belongs to the main
        # predicate, not to a lexical ``haberse`` / ``estarse`` reading of the
        # auxiliary. Once the occurrence tag says AUX, the non-reflexive
        # dictionary analysis is the only compatible side of that ambiguity.
        if self.clitic_gate and str(observed_pos or "").upper() == "AUX":
            evidence = False
        headwords = {analysis.headword.casefold() for analysis in analyses}
        reflexive_ambiguous = any(
            not headword.endswith("se") and headword + "se" in headwords
            for headword in headwords
        )
        clitic_removed: list[str] = []
        if reflexive_ambiguous and evidence is not None:
            compatible = {
                analysis.menu_analysis_id
                for analysis in analyses
                if analysis.headword.casefold().endswith("se") is evidence
            }
            compatible &= keep_ids
            if compatible:
                clitic_removed = sorted(keep_ids - compatible)
                keep_ids &= compatible

        structurally_kept = tuple(
            analysis for analysis in analyses if analysis.menu_analysis_id in keep_ids
        )
        leaf_candidates = tuple(
            (analysis, leaf)
            for analysis in structurally_kept
            for leaf in analysis.senses
        )
        attached_value = (observed_grammar or {}).get("attached_companions")
        attached_companions = (
            None
            if attached_value is None
            else tuple(value for value in str(attached_value).split(",") if value)
        )
        companion_kept, companion_rejected = filter_by_companion(
            leaf_candidates,
            sentence,
            features_of=lambda item: item[1].specialist_features,
            attached_companions=attached_companions,
        )
        companion_rejected_evidence = tuple(
            (analysis, leaf)
            for analysis, leaf in leaf_candidates
            if required_companions(leaf.specialist_features)
            and not normalized_companion_satisfied(
                leaf.specialist_features,
                sentence,
                attached_companions=attached_companions,
            )
        )
        companion_matched = tuple(
            (analysis, leaf)
            for analysis, leaf in leaf_candidates
            if required_companions(leaf.specialist_features)
            and normalized_companion_satisfied(
                leaf.specialist_features,
                sentence,
                attached_companions=attached_companions,
            )
        )
        grammar_kept, grammar_rejected = filter_by_grammar(
            companion_kept,
            observed_grammar or {},
            features_of=lambda item: item[1].specialist_features,
        )
        kept_leaf_refs = {
            (analysis.menu_analysis_id, leaf.sense_id)
            for analysis, leaf in grammar_kept
        }
        filtered_analyses = tuple(
            replace(
                analysis,
                senses=tuple(
                    leaf
                    for leaf in analysis.senses
                    if (analysis.menu_analysis_id, leaf.sense_id) in kept_leaf_refs
                ),
            )
            for analysis in structurally_kept
            if any(
                ref[0] == analysis.menu_analysis_id for ref in kept_leaf_refs
            )
        )
        selected_analyses = (
            analyses
            if self.constraint_mode == "evidence_only"
            else filtered_analyses
            if self.normalized_leaf_gates
            else structurally_kept
        )

        def refs(items):
            return [
                {"menu_analysis_id": analysis.menu_analysis_id, "sense_id": leaf.sense_id}
                for analysis, leaf in items
            ]
        return CandidatePreparation(
            analyses=selected_analyses,
            evidence={
                "method_id": self.method_id,
                "policy": self.constraint_mode,
                "normalized_leaf_gate_policy": (
                    "filter" if self.normalized_leaf_gates else "evidence_only"
                ),
                "observed_pos": observed_pos,
                "pos_match_status": pos_match_status,
                "pos_match_kind": pos_match_kind,
                "observed_grammar": dict(observed_grammar or {}),
                "pos_removed_analysis_ids": pos_removed,
                "se_reflexive_evidence": evidence,
                "clitic_removed_analysis_ids": clitic_removed,
                "constraint_supported_analysis_ids": sorted(keep_ids),
                "constraint_rejected_analysis_ids": sorted(
                    {analysis.menu_analysis_id for analysis in analyses} - keep_ids
                ),
                "companion_rejected_leaf_refs": refs(companion_rejected_evidence),
                "companion_matched_leaf_refs": refs(companion_matched),
                "grammar_rejected_leaf_refs": refs(grammar_rejected),
                "constraint_supported_leaf_refs": refs(grammar_kept),
                "indistinguishable_leaf_refs": _indistinguishable_leaf_refs(
                    structurally_kept
                ),
            },
        )

    def adjust_scores(
        self,
        scores: Sequence[LeafScore],
        analyses: tuple[MenuAnalysis, ...],
    ) -> tuple[LeafScore, ...]:
        order = {
            (analysis.menu_analysis_id, leaf.sense_id): rank
            for rank, (analysis, leaf) in enumerate(
                (item for analysis in analyses for item in ((analysis, leaf) for leaf in analysis.senses))
            )
        }
        adjusted = [
            replace(
                score,
                score=score.score
                + self.menu_prior
                * self.menu_prior_decay
                ** order[(score.menu_analysis_id, score.sense_id)],
            )
            for score in scores
        ]
        return tuple(sorted(adjusted, key=lambda item: (-item.score, item.menu_analysis_id, item.sense_id)))

    def repair_leaf(
        self,
        *,
        sentence: str,
        analyses: tuple[MenuAnalysis, ...],
        selected: LeafScore,
        ranked_scores: Sequence[LeafScore],
    ) -> LeafScore:
        analysis = require_analysis(analyses, selected.menu_analysis_id)
        leaf = analysis.sense(selected.sense_id)
        if leaf_renderable(leaf) and companion_satisfied(leaf, sentence):
            return selected
        eligible = {
            candidate.sense_id
            for candidate in analysis.senses
            if leaf_renderable(candidate) and companion_satisfied(candidate, sentence)
        }
        if not eligible:
            return selected
        return next(
            score
            for score in ranked_scores
            if score.menu_analysis_id == analysis.menu_analysis_id and score.sense_id in eligible
        )


class SpanishWSDAdapter:
    """Locate every eligible occurrence of a surface inside one sentence.

    Spanish has no tokenizer module here yet, so this walks word-shaped runs and
    compares NORMALIZED forms rather than raw text: the harvested surface key and
    the sentence must agree on accent and case handling or a legitimate
    occurrence silently fails to locate and the assignment abstains for the wrong
    reason.
    """

    language = "es"

    _WORD = re.compile(r"[0-9A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+")

    def locate(self, sentence: str, surface_form: str) -> tuple[TargetOccurrence, ...]:
        from fluency.languages.spanish.surfaces import normalize_surface

        surface_key = normalize_surface(surface_form)
        found: list[TargetOccurrence] = []
        for match in self._WORD.finditer(sentence or ""):
            observed = match.group(0)
            if normalize_surface(observed) != surface_key:
                continue
            found.append(
                TargetOccurrence(
                    observed_text=observed,
                    surface_key=surface_key,
                    start=match.start(),
                    end=match.end(),
                )
            )
        return tuple(found)
