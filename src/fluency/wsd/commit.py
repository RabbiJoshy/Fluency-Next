"""Decide how SPECIFIC an answer to emit, rather than whether to emit one.

This is the only genuinely new idea in the v6 method, and it exists because of a
measured dead end: every attempt to decide *better* failed, and every attempt to
decide *offline which errors are harmless* failed for the same reason — whether a
mistake matters depends on the sentence, not on the pair of senses. Declining to
over-claim is the one move that is always available and never wrong.

A system that must always emit a leaf turns every uncertainty into a wrong card.
A system that can emit less turns it into a vaguer one:

    confident throughout       ->  leaf       "está — is (location)"
    unsure which context       ->  glosskey   "está — is"
    unsure which gloss too     ->  tuple      "estar — to be"
    unsure of the word itself  ->  escalate / redraw

The three levels are a lattice over the same selection, not different answers.
The selected sense never changes; only how much of it is published does.

## Why escalation keys on the tuple alone

Being torn between two synonyms is not worth a model call — once the answer is
published at glosskey level the learner never sees the difference. Being unsure
which *word* this is always is worth one, because that is the error a learner
does notice.

The two axes also want different remedies, and picking the wrong one does
nothing at all:

    gloss uncertain  ->  emit less        rejection does not help here; leaf
                                          accuracy is flat across the whole
                                          rejection curve
    tuple uncertain  ->  reject & redraw  this is what rejection actually buys
                                          (tuple accuracy 82% -> 98% at 50%
                                          rejection), and it is free wherever the
                                          corpus is harvestable
                     ->  escalate         where it is not: a user's fixed corpus
                                          cannot supply another sentence

`decide` reports which axis is weak and leaves the remedy to the caller, because
the remedy is a property of the corpus, not of the algorithm.

## Calibration status

The thresholds are UNMEASURED and default to zero, which means "always emit a
leaf" — exactly the behaviour of the stage this replaces. The gloss backoff has
been validated in the reference repository (backing off 28% of a hard panel
lifted glosskey precision from 78% to 85%); the tuple trigger has NOT — the tuple
margin proved non-monotonic against tuple correctness, confounded by
single-analysis items whose errors are inventory gaps rather than choice errors.
Method agreement is the measured alternative and is not implemented here.

Do not enable `tuple_minimum` on the strength of the margin alone.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import math
from typing import Literal, Mapping, Sequence

from fluency.wsd.gloss_scoring import LeafScore
from fluency.wsd.menus import MenuAnalysis, require_analysis


EmitLevel = Literal["leaf", "glosskey", "tuple"]
UncertainAxis = Literal["none", "gloss", "tuple"]

EMIT_LEVELS: tuple[EmitLevel, ...] = ("leaf", "glosskey", "tuple")


@dataclass(frozen=True, slots=True)
class CommitPolicy:
    """Thresholds on the top-two margin of each axis. Zero disables a level."""

    leaf_minimum: float = 0.0
    glosskey_minimum: float = 0.0
    tuple_minimum: float = 0.0
    temperature: float = 0.02

    def __post_init__(self) -> None:
        for name, value in (
            ("leaf_minimum", self.leaf_minimum),
            ("glosskey_minimum", self.glosskey_minimum),
            ("tuple_minimum", self.tuple_minimum),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be a margin between zero and one")
        if self.temperature <= 0:
            raise ValueError("temperature must be positive")

    @property
    def enabled(self) -> bool:
        return any(
            value > 0
            for value in (self.leaf_minimum, self.glosskey_minimum, self.tuple_minimum)
        )


@dataclass(frozen=True, slots=True)
class CommitDecision:
    level: EmitLevel
    uncertain_axis: UncertainAxis
    margins: Mapping[str, float]
    escalate: bool


def _probabilities(scores: Sequence[LeafScore], temperature: float) -> dict[tuple[str, str], float]:
    top = max(item.score for item in scores)
    weights = {
        (item.menu_analysis_id, item.sense_id): math.exp((item.score - top) / temperature)
        for item in scores
    }
    total = sum(weights.values()) or 1.0
    return {key: value / total for key, value in weights.items()}


def _margin(distribution: Mapping[object, float]) -> float:
    if not distribution:
        return 0.0
    ordered = sorted(distribution.values(), reverse=True)
    return ordered[0] - (ordered[1] if len(ordered) > 1 else 0.0)


def axis_margins(
    scores: Sequence[LeafScore],
    analyses: Sequence[MenuAnalysis],
    *,
    temperature: float = 0.02,
) -> dict[str, float]:
    """Top-two margin on each of the three axes.

    Aggregation is MAX, never sum. Max over per-key maxima reproduces the global
    argmax exactly, so these margins add confidence without moving any pick. Sum
    pools mass across leaves sharing a key and is a largest-analysis prior in
    disguise: it scored +8 items on a panel stratified toward large analyses, +1
    on an unstratified one, and -8 on a uniform-over-senses dictionary panel.
    """

    if not scores:
        return {"leaf": 0.0, "glosskey": 0.0, "tuple": 0.0}
    probabilities = _probabilities(scores, temperature)
    leaf: dict[tuple[str, str], float] = {}
    glosskey: dict[tuple[str, str, str], float] = defaultdict(float)
    tuples: dict[tuple[str, str], float] = defaultdict(float)
    for item in scores:
        key = (item.menu_analysis_id, item.sense_id)
        probability = probabilities[key]
        leaf[key] = max(leaf.get(key, 0.0), probability)
        analysis = require_analysis(analyses, item.menu_analysis_id)
        sense = analysis.sense(item.sense_id)
        gloss_key = (
            analysis.part_of_speech,
            sense.translation or "<EMPTY>",
            analysis.headword.casefold(),
        )
        tuple_key = (analysis.part_of_speech, analysis.headword.casefold())
        glosskey[gloss_key] = max(glosskey[gloss_key], probability)
        tuples[tuple_key] = max(tuples[tuple_key], probability)
    return {
        "leaf": _margin(leaf),
        "glosskey": _margin(glosskey),
        "tuple": _margin(tuples),
    }


def decide(
    scores: Sequence[LeafScore],
    analyses: Sequence[MenuAnalysis],
    policy: CommitPolicy,
) -> CommitDecision:
    """Most specific level the scores support, plus which axis is weak."""

    margins = axis_margins(scores, analyses, temperature=policy.temperature)
    if margins["tuple"] < policy.tuple_minimum:
        return CommitDecision(
            level="tuple", uncertain_axis="tuple", margins=margins, escalate=True
        )
    if margins["glosskey"] < policy.glosskey_minimum:
        return CommitDecision(
            level="tuple", uncertain_axis="gloss", margins=margins, escalate=False
        )
    if margins["leaf"] < policy.leaf_minimum:
        return CommitDecision(
            level="glosskey", uncertain_axis="gloss", margins=margins, escalate=False
        )
    return CommitDecision(
        level="leaf", uncertain_axis="none", margins=margins, escalate=False
    )


def published_fields(level: EmitLevel, analysis: MenuAnalysis, sense_id: str) -> dict[str, object]:
    """What a card may show at this level. The selection itself never changes."""

    leaf = analysis.sense(sense_id)
    if level == "tuple":
        return {"headword": analysis.headword, "part_of_speech": analysis.part_of_speech}
    payload: dict[str, object] = {
        "headword": analysis.headword,
        "part_of_speech": analysis.part_of_speech,
        "translation": leaf.translation,
    }
    if level == "leaf":
        payload["definition"] = leaf.definition
    return payload
