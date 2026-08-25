"""Render immutable releases into the split JSON contract used by the Fluency app."""

from __future__ import annotations

from typing import Any


APP_CONTRACT_VERSION = "fluency-split-speech/v1"

APP_TENSE_LABELS = {
    ("indicativo", "presente"): "Presente",
    ("indicativo", "pretérito"): "Pretérito",
    ("indicativo", "imperfecto"): "Imperfecto",
    ("indicativo", "futuro"): "Futuro",
    ("indicativo", "condicional"): "Condicional",
    ("subjuntivo", "presente"): "Subj. Presente",
    ("subjuntivo", "imperfecto"): "Subj. Imperfecto",
}
APP_PERSON_ORDER = ("1s", "2s", "3s", "1p", "2p", "3p")


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
                source = example["metadata"].get("source") or {}
                document = source.get("document") or {}
                if document:
                    # The learner app historically reads a compact provenance
                    # object. Keep the complete typed metadata as the source of
                    # truth while exposing that compatibility view explicitly.
                    record["provenance"] = {
                        "corpus": source.get("name", record["source"]),
                        **document,
                    }
                if example["metadata"].get("source_title"):
                    record["source_title"] = example["metadata"]["source_title"]
            if example["assignment_status"] == "assigned":
                grouped_examples[example["sense_id"]].append(record)
            else:
                record.pop("assignment_method", None)
                unassigned_examples.append(record)

        distribution = card.get("wsd_distribution")
        distribution_counts = (
            distribution.get("published_leaf_counts")
            if isinstance(distribution, dict)
            else None
        )
        total_examples = max(
            1,
            distribution.get("denominator", 0)
            if isinstance(distribution, dict)
            else len(card["examples"]),
        )
        meanings: list[dict[str, Any]] = []
        buckets: list[list[dict[str, Any]]] = []
        unassigned_senses: list[dict[str, Any]] = []
        for meaning in card["meanings"]:
            bucket = grouped_examples[meaning["sense_id"]]
            old_meaning: dict[str, Any] = {
                "pos": meaning["part_of_speech"],
                "translation": meaning["translation"],
                "frequency": f"{(
                    distribution_counts.get(meaning['sense_id'], 0)
                    if isinstance(distribution_counts, dict)
                    else len(bucket)
                ) / total_examples:.6f}",
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
            if "metadata" in meaning:
                old_meaning["metadata"] = meaning["metadata"]
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
        if isinstance(distribution, dict):
            old_card["wsd_distribution"] = distribution
        split_examples: dict[str, Any] = {"m": buckets}
        if not meanings and (unassigned_senses or unassigned_examples):
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
        else:
            # A partially assigned card is already teachable. Keep unused menu
            # leaves and any unassigned examples as audit evidence without
            # manufacturing a learner-facing remainder sense. Giving that
            # remainder frequency 1.0 made the app renormalize valid assigned
            # senses to a misleading combined 50%.
            if unassigned_senses:
                old_card["unused_menu_senses"] = unassigned_senses
            if unassigned_examples:
                split_examples["u"] = unassigned_examples
        frequency = card.get("frequency")
        if isinstance(frequency, dict) and isinstance(frequency.get("primary_count"), int):
            old_card["corpus_count"] = frequency["primary_count"]
        index.append(old_card)
        examples[app_id] = split_examples

    return index, examples


def build_app_conjugations(layer: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Render a typed optional layer into the existing app's table shape."""

    if layer.get("layer_version") != "conjugation-layer/v1":
        raise ValueError("unsupported conjugation layer")
    result: dict[str, dict[str, Any]] = {}
    for record in layer.get("records", []):
        headword = record.get("headword")
        if not isinstance(headword, str) or not headword or headword in result:
            raise ValueError("conjugation layer contains an invalid/duplicate headword")
        entry: dict[str, Any] = {"tenses": {}}
        if record.get("translation"):
            entry["translation"] = record["translation"]
        nonfinite = record.get("nonfinite") or {}
        if nonfinite.get("gerund"):
            entry["gerund"] = nonfinite["gerund"]
        if nonfinite.get("past_participle"):
            entry["past_participle"] = nonfinite["past_participle"]
        for paradigm in record.get("paradigms", []):
            key = (
                str(paradigm.get("mood", "")).casefold(),
                str(paradigm.get("tense", "")).casefold(),
            )
            label = APP_TENSE_LABELS.get(key)
            if label is None:
                continue
            by_person = {
                item.get("person"): item.get("form")
                for item in paradigm.get("forms", [])
            }
            entry["tenses"][label] = [by_person.get(person, "—") for person in APP_PERSON_ORDER]
        result[headword] = entry
    return result
