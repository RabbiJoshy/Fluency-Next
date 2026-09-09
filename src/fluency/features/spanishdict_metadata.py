"""Accounting for SpanishDict fields alongside its feature extractor."""

from __future__ import annotations

from typing import Any, Mapping

from fluency.features.metadata import MetadataAccounting


STANDARD_FIELDS = frozenset({
    "_legacy_sense_id",
    "context",
    "examples",
    "headword",
    "pos",
    "regions",
    "source",
    "translation",
})


def metadata_accounting(sense: Mapping[str, Any]) -> MetadataAccounting:
    """Keep unfamiliar provider fields visible to the shared audit contract."""

    unclassified = tuple(
        {
            "source_field": f"spanishdict.{field}",
            "value": value,
            "reason": "no canonical SpanishDict mapping",
        }
        for field, value in sorted(sense.items())
        if field not in STANDARD_FIELDS
    )
    return MetadataAccounting(
        coverage={
            "context": "parsed",
            "dictionary_examples": "preserved",
            "regions": "parsed",
            "usage_and_construction_notes": "parsed",
        },
        unclassified=unclassified,
    )
