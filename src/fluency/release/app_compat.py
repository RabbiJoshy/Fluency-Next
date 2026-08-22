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
        unassigned_examples: list[dict[str, Any]] = []
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
            if "metadata" in example:
                record["metadata"] = example["metadata"]
            if example["assignment_status"] == "assigned":
                grouped_examples[example["sense_id"]].append(record)
            else:
                record.pop("assignment_method", None)
                unassigned_examples.append(record)

        total_examples = max(1, len(card["examples"]))
        meanings: list[dict[str, Any]] = []
        buckets: list[list[dict[str, Any]]] = []
        unassigned_senses: list[dict[str, Any]] = []
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
            for field in ("headword", "menu_analysis_id", "source_sense_id", "source_reference"):
                if meaning.get(field):
                    old_meaning[field] = meaning[field]
            if meaning["assignment_status"] == "unassigned":
                old_meaning["unassigned"] = True
                unassigned_senses.append(old_meaning)
            else:
                meanings.append(old_meaning)
                buckets.append(bucket)

        old_card: dict[str, Any] = {
            "word": card["display_form"],
            "id": app_id,
            "rank": card["rank"],
            "meanings": meanings,
            "surface_card_id": card["card_id"],
        }
        split_examples: dict[str, Any] = {"m": buckets}
        if unassigned_senses or unassigned_examples:
            # Normal-mode setup intentionally rejects cards with no primary
            # meaning. Represent the app's existing unassigned cycle as that
            # primary meaning, not as the secondary artist-only `sense_cycles`
            # field, so an entirely unassigned Speech deck remains teachable.
            # The renderer still sees `unassigned: true` and never presents the
            # pooled examples as evidence for a particular dictionary leaf.
            first = unassigned_senses[0] if unassigned_senses else {}
            meanings.append(
                {
                    "pos": "SENSE_CYCLE",
                    "translation": first.get("translation", "Unassigned examples"),
                    "frequency": "1.000000",
                    "source": "release",
                    "assignment_method": "unassigned",
                    "unassigned": True,
                    "cycle_pos": first.get("pos", "X"),
                    "allSenses": unassigned_senses,
                }
            )
            buckets.append(unassigned_examples)
        frequency = card.get("frequency")
        if isinstance(frequency, dict) and isinstance(frequency.get("primary_count"), int):
            old_card["corpus_count"] = frequency["primary_count"]
        index.append(old_card)
        examples[app_id] = split_examples

    return index, examples
