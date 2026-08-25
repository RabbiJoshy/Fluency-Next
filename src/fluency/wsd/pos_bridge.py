"""Reconciling a tagger's Universal Dependencies tags with a dictionary's tagset.

A POS filter is only as good as the correspondence between what the tagger emits
and what the dictionary publishes, and the two never agree. The failure is
silent and lands on the commonest words: when no dictionary POS is acceptable
for an observed tag, every analysis is rejected, the caller's empty-set fallback
fires, and the filter becomes a no-op precisely where it was meant to help.

The bridge therefore belongs to the *provider*, not the language -- French and
Portuguese both read Wiktionary and share its categories, while SpanishDict has
its own.

Measured mismatches this exists to absorb:

SpanishDict
    No ``AUX`` category: auxiliaries and modals are filed as ``VERB``, so
    ``haber, ser, estar, deber, saber`` fail unbridged. Determiners and
    possessives are filed as ``ADJ``.

Wiktionary
    Has a ``contraction`` category that Universal Dependencies does not.
    Portuguese ``do``, ``ao``, ``da``, ``na``, ``pelo`` are filed as
    ``contraction`` and nothing else; a tagger calls them ``ADP`` or ``DET``.
    These are top-fifty words. Like SpanishDict it has no ``aux``.
"""

from __future__ import annotations


# Dictionary categories that say nothing about part of speech, so a mismatch
# against them is not evidence of a wrong sense.
WIKTIONARY_ORTHOGONAL = frozenset(
    {"phrase", "proverb", "prep_phrase", "character", "symbol", "punct",
     "suffix", "prefix", "interfix"}
)

# Universal Dependencies tag -> acceptable Wiktionary categories.
WIKTIONARY_BRIDGE = {
    "NOUN": frozenset({"noun", "name"}),
    "PROPN": frozenset({"name", "noun"}),
    "VERB": frozenset({"verb"}),
    # Wiktionary has no `aux`; auxiliaries and copulas are plain verbs.
    "AUX": frozenset({"verb"}),
    "ADJ": frozenset({"adj", "det", "num", "pron"}),
    "ADV": frozenset({"adv", "particle", "prep_phrase"}),
    # `contraction` appears wherever a preposition has fused with an article,
    # which Universal Dependencies expresses as ADP or DET on the fused token.
    "ADP": frozenset({"prep", "contraction"}),
    "DET": frozenset({"det", "article", "contraction", "adj", "pron"}),
    "PRON": frozenset({"pron", "det", "article", "contraction"}),
    "NUM": frozenset({"num", "adj", "det"}),
    "PART": frozenset({"particle", "adv", "prep"}),
    "CCONJ": frozenset({"conj"}),
    "SCONJ": frozenset({"conj"}),
    "INTJ": frozenset({"intj"}),
    "SYM": frozenset({"symbol", "character"}),
    "PUNCT": frozenset({"punct", "character", "symbol"}),
    "X": frozenset(),
}

BRIDGES = {"wiktionary": (WIKTIONARY_BRIDGE, WIKTIONARY_ORTHOGONAL)}


class PosBridgeError(ValueError):
    """Raised when no bridge is defined for a dictionary provider."""


def acceptable_categories(provider: str, observed_pos: str) -> frozenset[str]:
    """Return the dictionary categories compatible with an observed UD tag.

    An empty set means the tag carries no usable constraint. Callers must treat
    that as "no evidence" and keep every analysis, never as "reject everything";
    the difference between those two readings is the whole bug.
    """

    bridge = BRIDGES.get(provider)
    if bridge is None:
        raise PosBridgeError(
            f"no POS bridge for provider {provider!r}; available: "
            f"{', '.join(sorted(BRIDGES))}"
        )
    mapping, _orthogonal = bridge
    return mapping.get((observed_pos or "").upper(), frozenset())


def is_orthogonal(provider: str, dictionary_pos: str) -> bool:
    """Return whether a dictionary category makes no part-of-speech claim."""

    bridge = BRIDGES.get(provider)
    if bridge is None:
        raise PosBridgeError(f"no POS bridge for provider {provider!r}")
    _mapping, orthogonal = bridge
    return (dictionary_pos or "").lower() in orthogonal


def compatible(provider: str, observed_pos: str | None, dictionary_pos: str) -> bool:
    """Return whether a dictionary category may stand for an observed tag.

    Unknown tags, unmapped tags and orthogonal categories all resolve to True.
    Refusing to guess keeps the filter from deleting correct senses, which is
    the more expensive of the two possible errors.
    """

    if not observed_pos:
        return True
    if is_orthogonal(provider, dictionary_pos):
        return True
    allowed = acceptable_categories(provider, observed_pos)
    if not allowed:
        return True
    return (dictionary_pos or "").lower() in allowed
