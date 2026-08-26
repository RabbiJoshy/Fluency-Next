"""Reject a sense whose required companion word is absent from the line.

Discrete and relational: it asks whether a specific word is present, not whether
a sentence resembles a topic. `wsd_open_threads.md` records that as the property
separating the signals that worked from the ones that did not -- and records this
gate as measured positive (+2 on a 200-item panel) but never built, because
SpanishDict buries the note in prose.

Both providers now emit it as a `companion` feature, so this reads neither.

Deliberately conservative in two ways. It only ever rejects when a companion is
declared AND absent -- a sense with no companion is untouched. And it never
rejects every candidate: if the gate would empty the set it declines instead,
because the empty-set fallback is what turned the POS filter into a silent
no-op on the commonest words.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable, Sequence


def _words(text: str) -> set[str]:
    folded = unicodedata.normalize("NFC", text or "").casefold()
    return set(re.findall(r"[^\W\d_]+", folded, flags=re.UNICODE))


def required_companions(features: Iterable[Any]) -> tuple[str, ...]:
    """Return the companion words a sense declares, if any."""

    found = []
    for feature in features or ():
        family = getattr(feature, "family", None) or (
            feature.get("family") if isinstance(feature, dict) else None
        )
        if family != "companion":
            continue
        value = getattr(feature, "value", None) or (
            feature.get("value") if isinstance(feature, dict) else None
        )
        if isinstance(value, str) and value.strip():
            found.append(value.strip().casefold())
    return tuple(dict.fromkeys(found))


def companion_satisfied(features: Iterable[Any], sentence: str) -> bool:
    """Return whether a sense's companion requirement is met by the line.

    True when no companion is declared: an absent requirement is not a failed
    one.
    """

    companions = required_companions(features)
    if not companions:
        return True
    present = _words(sentence)
    return any(companion in present for companion in companions)


def filter_by_companion(
    candidates: Sequence[Any],
    sentence: str,
    *,
    features_of,
) -> tuple[Sequence[Any], tuple[Any, ...]]:
    """Return (kept, rejected), declining to act if it would keep nothing."""

    kept, rejected = [], []
    for candidate in candidates:
        if companion_satisfied(features_of(candidate), sentence):
            kept.append(candidate)
        else:
            rejected.append(candidate)
    if not kept:
        return candidates, ()
    return kept, tuple(rejected)
