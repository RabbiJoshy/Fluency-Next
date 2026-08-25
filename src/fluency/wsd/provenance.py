"""What computed each decision in a release, summarised and stated.

Three things are easy to conflate and mean different things:

``contract``
    the shape an artifact speaks -- the v7 dual view, with its
    leaf/glosskey/tuple/unresolved ladder.
``method``
    what actually chose each sense: the v7 classifier, or an older one whose
    decisions were migrated forward.
``provenance``
    per decision, whether it was computed natively in this run or carried over.

A release can speak v7 while most of its decisions were computed by v5. That is
a legitimate thing to ship -- hand-tuned decisions are worth preserving -- but it
must be legible, because "the deck is on v7" and "the deck's decisions are v7"
sound identical and are not.

This module derives the composition from provenance already recorded per
decision, so it states what is there rather than what was intended.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable, Mapping


COMPOSITION_VERSION = "wsd-method-composition/v1"
NATIVE_METHOD = "native-v7"
UNRECORDED = "unrecorded"


class MethodCompositionError(ValueError):
    """Raised when a release's decision provenance cannot be summarised."""


def _decisions(index: Iterable[Mapping[str, Any]]) -> Iterable[Mapping[str, Any]]:
    for card in index:
        distribution = card.get("wsd_distribution")
        if not isinstance(distribution, Mapping):
            continue
        for bucket in distribution.get("buckets", []) or []:
            if isinstance(bucket, Mapping):
                yield bucket


def _method_of(decision: Mapping[str, Any]) -> str:
    provenance = decision.get("provenance")
    if isinstance(provenance, Mapping):
        method = provenance.get("assignment_method")
        if isinstance(method, str) and method.strip():
            return method.strip()
    return UNRECORDED


def method_composition(index: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Return the mix of methods behind one release's decisions.

    ``native_share`` is the number that answers "is this deck actually v7?".
    A deck at 0.0 speaks the v7 contract over entirely migrated decisions.
    """

    counts: Counter[str] = Counter(_method_of(d) for d in _decisions(index))
    total = sum(counts.values())
    native = counts.get(NATIVE_METHOD, 0)
    return {
        "composition_version": COMPOSITION_VERSION,
        "decision_count": total,
        "methods": dict(sorted(counts.items())),
        "native_method": NATIVE_METHOD,
        "native_decisions": native,
        "native_share": round(native / total, 4) if total else 0.0,
        "fully_native": total > 0 and native == total,
    }


def describe_composition(composition: Mapping[str, Any]) -> str:
    """Return a one-line human summary, for release output and reviews."""

    total = composition.get("decision_count", 0)
    if not total:
        return "no WSD decisions recorded"
    parts = ", ".join(
        f"{method} {count}" for method, count in composition.get("methods", {}).items()
    )
    return f"{total} decisions: {parts} ({composition.get('native_share', 0.0):.1%} native)"
