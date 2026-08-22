"""Render immutable releases into the split JSON contract used by the Fluency app."""

from __future__ import annotations

from typing import Any


APP_CONTRACT_VERSION = "fluency-split-speech/v1"


def _app_card_id(card_id: str) -> str:
    prefix, language, digest = card_id.split("_", 2)
    if prefix != "card" or not language or len(digest) < 8:
        raise ValueError(f"invalid surface card ID: {card_id}")
    return digest[:8]


def build_app_compatibility_assets(
    deck: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Convert a clean deck without inventing lemma identity or source evidence."""

    index: list[dict[str, Any]] = []
    examples: dict[str, dict[str, Any]] = {}
    used_ids: set[str] = set()
    for card in deck["cards"]:
        app_id = _app_card_id(card["card_id"])
        if app_id in used_ids:
            raise ValueError(f"app compatibility ID collision: {app_id}")
        used_ids.add(app_id)

        grouped_examples: dict[str, list[dict[str, Any]]] = {
            meaning["sense_id"]: [] for meaning in card["meanings"]
        }
        for example in card["examples"]:
            record: dict[str, Any] = {
                "target": example["target"],
                "english": example["english"],
                "source": example.get("source", example["provenance"]),
                "assignment_method": example.get(
                    "assignment_method", example["provenance"]
                ),
                "example_id": example["example_id"],
            }
            if "easiness" in example:
                record["easiness"] = example["easiness"]
            grouped_examples[example["sense_id"]].append(record)

        total_examples = max(1, len(card["examples"]))
        meanings: list[dict[str, Any]] = []
        buckets: list[list[dict[str, Any]]] = []
        for meaning in card["meanings"]:
            bucket = grouped_examples[meaning["sense_id"]]
            old_meaning: dict[str, Any] = {
                "pos": meaning["part_of_speech"],
                "translation": meaning["translation"],
                "frequency": f"{len(bucket) / total_examples:.6f}",
                "source": meaning.get("source", "release"),
                "assignment_method": meaning["assignment_status"],
                "sense_id": meaning["sense_id"],
            }
            for field in ("context", "detail"):
                if meaning.get(field):
                    old_meaning[field] = meaning[field]
            meanings.append(old_meaning)
            buckets.append(bucket)

        old_card: dict[str, Any] = {
            "word": card["display_form"],
            "id": app_id,
            "rank": card["rank"],
            "meanings": meanings,
            "surface_card_id": card["card_id"],
        }
        frequency = card.get("frequency")
        if isinstance(frequency, dict) and isinstance(frequency.get("primary_count"), int):
            old_card["corpus_count"] = frequency["primary_count"]
        index.append(old_card)
        examples[app_id] = {"m": buckets}

    return index, examples
