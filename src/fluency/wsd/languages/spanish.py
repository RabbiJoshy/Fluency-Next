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
from typing import Sequence

from fluency.wsd.candidate_policy import CandidatePreparation
from fluency.wsd.gloss_scoring import LeafScore
from fluency.wsd.languages.base import TargetOccurrence
from fluency.wsd.menus import MenuAnalysis, SenseLeaf, require_analysis


WORD_RE = re.compile(r"[a-záéíóúüñ0-9]+")
CLITICS = frozenset({"me", "te", "se", "nos", "os", "lo", "la", "le", "los", "las", "les"})
ORTHOGONAL_POS = frozenset({"PHRASE", "CONTRACTION"})
TRUSTED_POS = frozenset({"VERB", "NOUN", "ADJ", "ADV", "INTJ"})
POS_BRIDGE = {
    "DET": frozenset({"ADJ", "DET", "PRON"}),
    "PRON": frozenset({"PRON", "ADJ", "DET"}),
    "NUM": frozenset({"ADJ", "NOUN", "DET"}),
    "PART": frozenset({"ADV", "ADP", "PRON"}),
    "PROPN": frozenset({"PROPN", "NOUN"}),
    "ADV": frozenset({"ADV", "PRON", "ADJ"}),
    "AUX": frozenset({"VERB", "AUX", "PHRASE"}),
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
TOKEN_RE = re.compile(r"[a-záéíóúüñ0-9']+")
SOFT_COMPANION = re.compile(
    r"\b(?:often|sometimes|usually|frequently|typically|generally|normally|"
    r"commonly|may be|can be)\s+used with",
    re.I,
)
COMPANION = re.compile(r'used with\s+"([^"]+)"|used with\s+([a-záéíóúüñ]+)', re.I)
FUSED = {
    "al": ("a", "el"), "del": ("de", "el"), "conmigo": ("con",),
    "contigo": ("con",), "consigo": ("con",), "'e": ("de",),
    "e'": ("de",), "pa": ("para",), "pa'": ("para",),
    "p'": ("para",), "po'": ("por",),
}


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


def se_reflexive_evidence(surface_form: str, sentence: str) -> bool | None:
    """Return the exact conservative v5 ``se-only`` gate evidence."""

    surface = _deaccent(surface_form)
    # Speech inventories can contain an enclitic surface (``diviértanse``).
    # Looking only to the left mislabels it as non-reflexive even though the
    # clitic is fused into the observed token.
    if surface.endswith("se") and len(surface) > 2:
        return True
    tokens = WORD_RE.findall(_deaccent(sentence))
    try:
        index = tokens.index(surface)
    except ValueError:
        return None
    cluster: list[str] = []
    index -= 1
    while index >= 0 and tokens[index] in CLITICS:
        cluster.append(tokens[index])
        index -= 1
    if "se" in cluster:
        return True
    return False if not cluster else None


def _leaf_context(leaf: SenseLeaf) -> str:
    context = leaf.provider_metadata.get("context")
    return context if isinstance(context, str) else leaf.definition


def _hard_companion(leaf: SenseLeaf) -> str | None:
    context = _leaf_context(leaf)
    if SOFT_COMPANION.search(context):
        return None
    match = COMPANION.search(context)
    if match is None:
        return None
    value = (match.group(1) or match.group(2) or "").strip().casefold()
    return value or None


def leaf_renderable(leaf: SenseLeaf) -> bool:
    return bool(leaf.translation.strip())


def companion_satisfied(leaf: SenseLeaf, sentence: str) -> bool:
    companion = _hard_companion(leaf)
    if companion is None:
        return True
    tokens = TOKEN_RE.findall(sentence.casefold())
    expanded = set(tokens)
    for token in tokens:
        expanded.update(FUSED.get(token, ()))
    return all(part in expanded for part in companion.split())


class SpanishV5CandidatePolicy:
    method_id = "spanish-v5-candidate-policy/v1"

    def __init__(
        self,
        *,
        menu_prior: float = 0.02,
        menu_prior_decay: float = 0.5,
        constraint_mode: str = "filter",
    ) -> None:
        if menu_prior < 0 or not 0 < menu_prior_decay <= 1:
            raise ValueError("invalid Spanish menu-prior parameters")
        if constraint_mode not in {"filter", "evidence_only"}:
            raise ValueError("unsupported Spanish constraint mode")
        self.menu_prior = menu_prior
        self.menu_prior_decay = menu_prior_decay
        self.constraint_mode = constraint_mode

    def prepare(
        self,
        *,
        sentence: str,
        surface_form: str,
        observed_pos: str | None,
        analyses: tuple[MenuAnalysis, ...],
    ) -> CandidatePreparation:
        keep_ids = {analysis.menu_analysis_id for analysis in analyses}
        pos_removed: list[str] = []
        if observed_pos:
            compatible = {
                analysis.menu_analysis_id
                for analysis in analyses
                # Synthetic multiword PHRASE analyses are added only after this
                # provider gate. A SpanishDict PHRASE row is therefore not an
                # orthogonal MWE candidate: treating it as one is what allowed
                # renderings such as ``está`` -> "he's" to beat the verb menu.
                if analysis.part_of_speech.upper() not in ORTHOGONAL_POS
                and sense_compatible_bridged(analysis.part_of_speech, observed_pos)
            }
            if compatible:
                pos_removed = sorted(keep_ids - compatible)
                keep_ids &= compatible

        evidence = se_reflexive_evidence(surface_form, sentence)
        # In ``se ha ido`` / ``se está haciendo``, ``se`` belongs to the main
        # predicate, not to a lexical ``haberse`` / ``estarse`` reading of the
        # auxiliary. Once the occurrence tag says AUX, the non-reflexive
        # dictionary analysis is the only compatible side of that ambiguity.
        if str(observed_pos or "").upper() == "AUX":
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

        selected_analyses = (
            analyses
            if self.constraint_mode == "evidence_only"
            else tuple(
                analysis
                for analysis in analyses
                if analysis.menu_analysis_id in keep_ids
            )
        )
        return CandidatePreparation(
            analyses=selected_analyses,
            evidence={
                "method_id": self.method_id,
                "policy": self.constraint_mode,
                "observed_pos": observed_pos,
                "pos_removed_analysis_ids": pos_removed,
                "se_reflexive_evidence": evidence,
                "clitic_removed_analysis_ids": clitic_removed,
                "constraint_supported_analysis_ids": sorted(keep_ids),
                "constraint_rejected_analysis_ids": sorted(
                    {analysis.menu_analysis_id for analysis in analyses} - keep_ids
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
            replace(score, score=score.score + self.menu_prior * self.menu_prior_decay ** order[(score.menu_analysis_id, score.sense_id)])
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
