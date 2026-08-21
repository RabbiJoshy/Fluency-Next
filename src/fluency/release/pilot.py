"""Build the deterministic, hand-curated French Speech pilot release."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

from fluency.core.canonical_json import canonical_json
from fluency.core.hashing import content_id
from fluency.core.workspace import Workspace
from fluency.languages.french.surfaces import create_french_card
from fluency.release.validation import (
    ACTIVE_RELEASE_VERSION,
    RELEASE_MANIFEST_VERSION,
    SPEECH_DECK_VERSION,
    validate_active_release,
    validate_release_bundle,
)


SEED_VERSION = "fr-speech-pilot-seed/v1"


def default_seed_path() -> Path:
    return Path(__file__).resolve().parents[3] / "fixtures" / "pilot" / "fr-speech-pilot.seed.json"


def _json_bytes(value: object) -> bytes:
    return (canonical_json(value) + "\n").encode("utf-8")


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


def _write_active_pointer(path: Path, active: dict[str, Any], temporary_root: Path) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        dir=temporary_root,
        prefix="active-release-",
        suffix=".json",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(_json_bytes(active))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def build_pilot_release(
    workspace: Workspace,
    *,
    seed_path: Path | None = None,
) -> Path:
    seed = _load_seed(default_seed_path() if seed_path is None else seed_path)
    deck = build_pilot_deck(seed)
    deck_bytes = _json_bytes(deck)
    manifest = {
        "manifest_version": RELEASE_MANIFEST_VERSION,
        "release_id": seed["release_id"],
        "language": seed["language"],
        "locale": seed["locale"],
        "mode": seed["mode"],
        "created_at": seed["created_at"],
        "publication_status": "curated_fixture",
        "card_count": len(deck["cards"]),
        "deck_path": "deck.json",
        "deck_content_id": content_id(deck_bytes),
        "progress_namespace": "pilot",
        "wsd": {"enabled": False, "status": "not_connected"},
    }
    manifest_bytes = _json_bytes(manifest)

    speech_root = workspace.root / "releases" / "fr" / "speech"
    release_directory = speech_root / seed["release_id"]
    temporary_root = workspace.root / ".fluency" / "temporary"
    speech_root.mkdir(parents=True, exist_ok=True)

    if release_directory.exists():
        existing_deck = (release_directory / "deck.json").read_bytes()
        existing_manifest = (release_directory / "manifest.json").read_bytes()
        if existing_deck != deck_bytes or existing_manifest != manifest_bytes:
            raise ValueError(
                f"immutable release already exists with different content: {release_directory}"
            )
    else:
        temporary = Path(tempfile.mkdtemp(prefix="pilot-release-", dir=temporary_root))
        try:
            (temporary / "deck.json").write_bytes(deck_bytes)
            (temporary / "manifest.json").write_bytes(manifest_bytes)
            os.replace(temporary, release_directory)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)

    validate_release_bundle(release_directory)
    active = {
        "manifest_version": ACTIVE_RELEASE_VERSION,
        "language": "fr",
        "mode": "speech",
        "release_id": seed["release_id"],
        "manifest_path": f"{seed['release_id']}/manifest.json",
    }
    validate_active_release(active)
    _write_active_pointer(speech_root / "active.json", active, temporary_root)
    return release_directory
