"""Multiword senses offered as ordinary closed-menu candidates.

A multiword expression is not primarily a disambiguation aid. `así que` = "so",
`tal vez` = "maybe", `de vez en cuando` = "once in a while" are vocabulary a
learner needs in their own right; helping the classifier is the side effect.

## Why they compete rather than veto

The obvious shape is a veto — the line contains `junto a`, so drop every leaf
incompatible with "next to". That shape is wrong and was measured wrong:

  - only 9% of multiword hits map cleanly onto an existing leaf, and the
    classifier already gets those right;
  - roughly a quarter of hits are compositional strings (`no tiene`, `si puedo`)
    where a veto would delete the correct answer.

Competing instead, a junk entry costs one mediocre card meaning while a veto
costs a correct one. Those are not symmetric, so the inventory is deliberately
kept inclusive and the competition sorts it out.

Measured on 29 panel occurrences carrying a multiword expression, the multiword
candidate beat every menu leaf on 15 — hand-graded 12 good, 5 compositional
false positives. The wins include `a menos que` = unless (previously scored as
"minus sign"), `por qué` = why (previously "by"), `sitio web`, `da igual`,
`en todas partes`, and `dar cuenta de`, which a frontier model also missed.

## Two tiers, which must never be collapsed

A card shows EXAMPLES, and examples are sampled from a corpus:

  - ``corpus_freq > 0``  has sentences behind it, can be assigned to an
    occurrence, can carry an example;
  - ``corpus_freq == 0`` is teachable reference content with no sentence to
    attach. It can never be an occurrence outcome and is never offered here.

`index_multiword_senses` enforces that boundary. Loosening it would let an
assignment claim evidence that does not exist.

## Identity

A multiword candidate is a synthetic `MenuAnalysis` on the *component surface's*
card, so it lands on whichever card that occurrence was selected as evidence
for, and card identity is untouched. Its analysis ID is minted through the same
`build_analysis_id` as any provider analysis, from a distinct source adapter, so
it can never collide with or masquerade as a SpanishDict analysis.

This is an inventory extension, and it is typed as one: the assignment carries a
`multiword` evidence block naming the expression, its span, its corpus frequency
and the inventory snapshot it came from, so an auditor can always tell a
multiword outcome from a provider-menu outcome.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable, Mapping, Sequence

from fluency.wsd.menus import MenuAnalysis, SenseLeaf, build_analysis_id


MULTIWORD_SOURCE_ADAPTER = "mwe-merged/v1"
MULTIWORD_POS = "PHRASE"
MULTIWORD_DEFINITION = "multiword expression"

_PUNCTUATION = re.compile(r"[^\w\sáéíóúüñÁÉÍÓÚÜÑ]+")


def _flatten(text: str) -> str:
    return " " + _PUNCTUATION.sub(" ", (text or "").casefold()) + " "


@dataclass(frozen=True, slots=True)
class MultiwordEntry:
    expression: str
    translations: tuple[str, ...]
    corpus_frequency: int
    sources: tuple[str, ...]
    entry_id: str

    def __post_init__(self) -> None:
        if not self.expression.strip():
            raise ValueError("multiword expression must not be empty")
        if not self.translations:
            raise ValueError("multiword entry requires at least one translation")
        if self.corpus_frequency < 0:
            raise ValueError("corpus frequency must not be negative")


def index_multiword_senses(
    payload: Mapping[str, Any],
    *,
    minimum_corpus_frequency: int = 1,
) -> dict[str, tuple[MultiwordEntry, ...]]:
    """Attach-word index over tier-1 entries only.

    `minimum_corpus_frequency` defaults to 1 rather than 0 deliberately: a tier-2
    entry has no sentence behind it and therefore cannot be the answer for any
    occurrence. Setting it to 0 would offer candidates that no evidence supports.
    """

    if minimum_corpus_frequency < 1:
        raise ValueError(
            "multiword candidates require attested entries; tier-2 content "
            "has no sentence and must not be offered as a candidate"
        )
    grouped: dict[str, list[MultiwordEntry]] = {}
    for expression, row in (payload.get("mwes") or {}).items():
        frequency = int(row.get("corpus_freq", 0) or 0)
        if frequency < minimum_corpus_frequency:
            continue
        translations = tuple(
            value for value in (row.get("translations") or []) if str(value).strip()
        )
        if not translations:
            continue
        entry = MultiwordEntry(
            expression=str(expression).casefold(),
            translations=translations,
            corpus_frequency=frequency,
            sources=tuple(row.get("sources") or ()),
            entry_id=str(row.get("id") or f"mwe:{expression}"),
        )
        for word in row.get("attach_words") or ():
            grouped.setdefault(str(word).casefold(), []).append(entry)
    return {word: tuple(items) for word, items in grouped.items()}


def multiword_matches(
    *,
    surface_form: str,
    sentence: str,
    index: Mapping[str, Sequence[MultiwordEntry]],
) -> tuple[tuple[MultiwordEntry, tuple[int, int]], ...]:
    """Entries whose expression is literally present, with their character span."""

    flattened = _flatten(sentence)
    lowered = sentence.casefold()
    found: list[tuple[MultiwordEntry, tuple[int, int]]] = []
    for entry in index.get((surface_form or "").casefold(), ()):
        if f" {entry.expression} " not in flattened:
            continue
        start = lowered.find(entry.expression)
        span = (start, start + len(entry.expression)) if start >= 0 else (0, len(sentence))
        found.append((entry, span))
    return tuple(found)


def multiword_analyses(
    *,
    card_id: str,
    surface_form: str,
    sentence: str,
    index: Mapping[str, Sequence[MultiwordEntry]],
) -> tuple[tuple[MenuAnalysis, MultiwordEntry, tuple[int, int]], ...]:
    """Synthetic analyses for every multiword sense the line contains.

    POS is PHRASE, which the Spanish POS bridge already treats as orthogonal, so
    a multiword candidate is never filtered out by an observed tag and needs no
    special case in the constraint stage.
    """

    built: list[tuple[MenuAnalysis, MultiwordEntry, tuple[int, int]]] = []
    for entry, span in multiword_matches(
        surface_form=surface_form, sentence=sentence, index=index
    ):
        analysis_id = build_analysis_id(
            card_id=card_id,
            source_adapter=MULTIWORD_SOURCE_ADAPTER,
            source_analysis_key=entry.expression,
        )
        leaf = SenseLeaf(
            sense_id=entry.entry_id,
            translation=entry.translations[0],
            definition=MULTIWORD_DEFINITION,
            source_reference=MULTIWORD_SOURCE_ADAPTER,
            provider_metadata={
                "expression": entry.expression,
                "corpus_frequency": entry.corpus_frequency,
                "sources": list(entry.sources),
                "additional_translations": list(entry.translations[1:]),
            },
        )
        built.append((
            MenuAnalysis(
                menu_analysis_id=analysis_id,
                card_id=card_id,
                surface_form=surface_form,
                headword=entry.expression,
                part_of_speech=MULTIWORD_POS,
                source_adapter=MULTIWORD_SOURCE_ADAPTER,
                source_analysis_key=entry.expression,
                senses=(leaf,),
                provider_metadata={"expression": entry.expression},
            ),
            entry,
            span,
        ))
    return tuple(built)


def is_multiword_analysis(analysis: MenuAnalysis) -> bool:
    return analysis.source_adapter == MULTIWORD_SOURCE_ADAPTER


def multiword_evidence(
    analysis: MenuAnalysis,
    entry: MultiwordEntry,
    span: tuple[int, int],
    *,
    inventory_content_id: str | None,
) -> dict[str, Any]:
    return {
        "expression": entry.expression,
        "expression_id": entry.entry_id,
        "menu_analysis_id": analysis.menu_analysis_id,
        "span": [span[0], span[1]],
        "corpus_frequency": entry.corpus_frequency,
        "sources": list(entry.sources),
        "component_surface_form": analysis.surface_form,
        "inventory_content_id": inventory_content_id,
    }


def entries_by_expression(
    index: Mapping[str, Sequence[MultiwordEntry]],
) -> dict[str, MultiwordEntry]:
    out: dict[str, MultiwordEntry] = {}
    for entries in index.values():
        for entry in entries:
            out[entry.expression] = entry
    return out


def iter_entries(index: Mapping[str, Sequence[MultiwordEntry]]) -> Iterable[MultiwordEntry]:
    return entries_by_expression(index).values()
