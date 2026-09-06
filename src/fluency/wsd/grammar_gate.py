"""Provider-neutral filtering for explicit person, number, mood and reflexive marks."""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence


def grammar_constraints(features: Iterable[Any]) -> dict[str, set[str]]:
    constraints: dict[str, set[str]] = {}
    for feature in features or ():
        family = getattr(feature, "family", None) or (
            feature.get("family") if isinstance(feature, dict) else None
        )
        if family != "grammar":
            continue
        value = getattr(feature, "value", None) or (
            feature.get("value") if isinstance(feature, dict) else None
        )
        if not isinstance(value, str) or "=" not in value:
            continue
        axis, expected = value.split("=", 1)
        if axis and expected:
            constraints.setdefault(axis, set()).add(expected)
    return constraints


def grammar_compatible(features: Iterable[Any], observed: Mapping[str, str]) -> bool:
    """Unknown axes do not reject; an observed contradiction does."""

    for axis, expected in grammar_constraints(features).items():
        actual = observed.get(axis)
        if actual is not None and actual not in expected:
            return False
    return True


def filter_by_grammar(
    candidates: Sequence[Any],
    observed: Mapping[str, str],
    *,
    features_of,
) -> tuple[Sequence[Any], tuple[Any, ...]]:
    """Return (kept, rejected), declining to erase the whole candidate set."""

    if not observed:
        return candidates, ()
    kept, rejected = [], []
    for candidate in candidates:
        destination = kept if grammar_compatible(features_of(candidate), observed) else rejected
        destination.append(candidate)
    if not kept:
        return candidates, ()
    return kept, tuple(rejected)
