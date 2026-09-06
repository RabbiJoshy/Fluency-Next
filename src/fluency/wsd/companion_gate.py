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


CONTRACTION_PARTS = {
    # Spanish
    "al": ("a", "el"), "del": ("de", "el"),
    "conmigo": ("con",), "contigo": ("con",), "consigo": ("con",),
    "pa": ("para",), "po": ("por",),
    # Portuguese
    "ao": ("a", "o"), "aos": ("a", "os"),
    "à": ("a", "a"), "às": ("a", "as"),
    "do": ("de", "o"), "da": ("de", "a"), "dos": ("de", "os"), "das": ("de", "as"),
    "dum": ("de", "um"), "duma": ("de", "uma"),
    "duns": ("de", "uns"), "dumas": ("de", "umas"),
    "dele": ("de", "ele"), "dela": ("de", "ela"),
    "deles": ("de", "eles"), "delas": ("de", "elas"),
    "no": ("em", "o"), "na": ("em", "a"), "nos": ("em", "os"), "nas": ("em", "as"),
    "num": ("em", "um"), "numa": ("em", "uma"),
    "nuns": ("em", "uns"), "numas": ("em", "umas"),
    "nele": ("em", "ele"), "nela": ("em", "ela"),
    "neles": ("em", "eles"), "nelas": ("em", "elas"),
    "pelo": ("por", "o"), "pela": ("por", "a"),
    "pelos": ("por", "os"), "pelas": ("por", "as"),
    "comigo": ("com",), "pra": ("para",), "pro": ("para",),
}


def _words(text: str) -> set[str]:
    folded = unicodedata.normalize("NFC", text or "").casefold()
    words = set(re.findall(r"[^\W\d_]+", folded, flags=re.UNICODE))
    for word in tuple(words):
        words.update(CONTRACTION_PARTS.get(word, ()))
    return words


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


def companion_satisfied(
    features: Iterable[Any],
    sentence: str,
    *,
    attached_companions: Iterable[str] | None = None,
) -> bool:
    """Return whether a sense's companion requirement is met by the line.

    True when no companion is declared: an absent requirement is not a failed
    one.
    """

    companions = required_companions(features)
    if not companions:
        return True
    present = (
        {str(value).casefold() for value in attached_companions}
        if attached_companions is not None
        else _words(sentence)
    )
    return any(companion in present for companion in companions)


def filter_by_companion(
    candidates: Sequence[Any],
    sentence: str,
    *,
    features_of,
    attached_companions: Iterable[str] | None = None,
) -> tuple[Sequence[Any], tuple[Any, ...]]:
    """Return (kept, rejected), declining to act if it would keep nothing."""

    kept, rejected = [], []
    for candidate in candidates:
        if companion_satisfied(
            features_of(candidate),
            sentence,
            attached_companions=attached_companions,
        ):
            kept.append(candidate)
        else:
            rejected.append(candidate)
    if not kept:
        return candidates, ()
    return kept, tuple(rejected)
