"""Build the deterministic, hand-curated French Speech pilot release."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fluency.core.hashing import content_id
from fluency.core.workspace import Workspace
from fluency.languages.french.surfaces import create_french_card
from fluency.release.activation import activate_release
from fluency.release.composition import compose_release
from fluency.release.validation import (
    SPEECH_DECK_VERSION,
)


SEED_VERSION = "fr-speech-pilot-seed/v1"


def default_seed_path() -> Path:
    return Path(__file__).resolve().parents[3] / "fixtures" / "pilot" / "fr-speech-pilot.seed.json"


def _load_seed(path: Path) -> dict[str, Any]:
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("seed_version") != SEED_VERSION:
        raise ValueError(f"unsupported pilot seed: {path}")
    cards = record.get("cards")
    if not isinstance(cards, list) or len(cards) != 25:
        raise ValueError("the French Speech pilot seed must contain exactly 25 cards")
    return record


def build_pilot_deck(seed: dict[str, Any]) -> dict[str, Any]:
    cards: list[dict[str, Any]] = []
    sense_counter = 0
    example_counter = 0
    for rank, source_card in enumerate(seed["cards"], start=1):
        identity = create_french_card(source_card["surface"])
        meanings: list[dict[str, Any]] = []
        local_sense_ids: list[str] = []
        for source_meaning in source_card["meanings"]:
            sense_counter += 1
            sense_id = f"fixture_sense_fr_{sense_counter:03d}"
            local_sense_ids.append(sense_id)
            meaning = {
                "sense_id": sense_id,
                "part_of_speech": source_meaning["part_of_speech"],
                "translation": source_meaning["translation"],
                "assignment_status": "curated_fixture",
            }
            if source_meaning.get("context"):
                meaning["context"] = source_meaning["context"]
            meanings.append(meaning)

        examples: list[dict[str, Any]] = []
        for source_example in source_card["examples"]:
            meaning_index = int(source_example.get("meaning_index", 1)) - 1
            if meaning_index < 0 or meaning_index >= len(local_sense_ids):
                raise ValueError(f"invalid fixture meaning index for {identity.surface_key}")
            example_counter += 1
            examples.append(
                {
                    "example_id": f"fixture_example_fr_{example_counter:03d}",
                    "sense_id": local_sense_ids[meaning_index],
                    "target": source_example["target"],
                    "english": source_example["english"],
                    "provenance": "curated_fixture",
                }
            )

        cards.append(
            {
                "card_id": identity.card_id,
                "surface_key": identity.surface_key,
                "display_form": identity.display_form,
                "rank": rank,
                "meanings": meanings,
                "examples": examples,
            }
        )

    return {
        "deck_version": SPEECH_DECK_VERSION,
        "release_id": seed["release_id"],
        "language": seed["language"],
        "mode": seed["mode"],
        "cards": cards,
    }


def build_pilot_release(
    workspace: Workspace,
    *,
    seed_path: Path | None = None,
) -> Path:
    source_path = default_seed_path() if seed_path is None else seed_path
    seed = _load_seed(source_path)
    deck = build_pilot_deck(seed)
    fixture_artifact_id = content_id(source_path.read_bytes())
    selection = {
        "selection_version": "layer-selection/v1",
        "source_type": "fixture",
        "source_id": SEED_VERSION,
        "artifact_id": fixture_artifact_id,
        "record_count": len(deck["cards"]),
        "requires": {},
    }
    layers = {
        "inventory": dict(selection),
        "sense_menu": {**selection, "requires": {"inventory": fixture_artifact_id}},
        "sentences": {**selection, "requires": {"inventory": fixture_artifact_id}},
        "example_selection": {
            **selection,
            "requires": {
                "inventory": fixture_artifact_id,
                "sense_menu": fixture_artifact_id,
                "sentences": fixture_artifact_id,
            },
        },
    }
    composition = {
        "composition_version": "release-composition/v1",
        "release_id": seed["release_id"],
        "label": "French Speech · curated pilot 0002",
        "language": seed["language"],
        "locale": seed["locale"],
        "mode": seed["mode"],
        "created_at": seed["created_at"],
        "publication_status": "curated_fixture",
        "progress_namespace": "pilot",
        "conflict_policy": "error",
        "fallback_policy": "none",
        "layers": layers,
        "omitted_layers": [
            {"layer": "wsd_assignments", "reason": "not_connected"},
            {"layer": "manual_overrides", "reason": "not_applied"},
        ],
    }
    release_directory = compose_release(workspace, composition, deck)
    activate_release(workspace, seed["language"], seed["mode"], seed["release_id"])
    return release_directory
