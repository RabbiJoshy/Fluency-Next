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

    def __init__(self, *, menu_prior: float = 0.02, menu_prior_decay: float = 0.5) -> None:
        if menu_prior < 0 or not 0 < menu_prior_decay <= 1:
            raise ValueError("invalid Spanish menu-prior parameters")
        self.menu_prior = menu_prior
        self.menu_prior_decay = menu_prior_decay

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
                if sense_compatible_bridged(analysis.part_of_speech, observed_pos)
            }
            if compatible:
                pos_removed = sorted(keep_ids - compatible)
                keep_ids &= compatible

        evidence = se_reflexive_evidence(surface_form, sentence)
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

        prepared = tuple(analysis for analysis in analyses if analysis.menu_analysis_id in keep_ids)
        if not prepared:
            prepared = analyses
        return CandidatePreparation(
            analyses=prepared,
            evidence={
                "method_id": self.method_id,
                "observed_pos": observed_pos,
                "pos_removed_analysis_ids": pos_removed,
                "se_reflexive_evidence": evidence,
                "clitic_removed_analysis_ids": clitic_removed,
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
