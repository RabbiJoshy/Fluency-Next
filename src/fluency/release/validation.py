"""Strict validation for compact app release bundles."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fluency.core.hashing import file_content_id
from fluency.core.identity import build_card_id
from fluency.languages.french.surfaces import normalize_surface


ACTIVE_RELEASE_VERSION = "active-release/v1"
RELEASE_MANIFEST_VERSION = "release-manifest/v1"
SPEECH_DECK_VERSION = "speech-deck/v1"


class ReleaseValidationError(ValueError):
    """Raised when a release bundle violates a published contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ReleaseValidationError(message)


def _load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ReleaseValidationError(f"release file does not exist: {path}") from error
    except json.JSONDecodeError as error:
        raise ReleaseValidationError(f"release file is not valid JSON: {path}") from error
    _require(isinstance(value, dict), f"release file must contain an object: {path}")
    return value


def validate_deck(deck: dict[str, Any]) -> None:
    _require(deck.get("deck_version") == SPEECH_DECK_VERSION, "unsupported deck version")
    _require(isinstance(deck.get("release_id"), str), "deck release_id is required")
    _require(deck.get("language") == "fr", "pilot deck language must be fr")
    _require(deck.get("mode") == "speech", "pilot deck mode must be speech")
    cards = deck.get("cards")
    _require(isinstance(cards, list) and cards, "deck cards must be a non-empty list")

    card_ids: set[str] = set()
    sense_ids: set[str] = set()
    example_ids: set[str] = set()
    for expected_rank, card in enumerate(cards, start=1):
        _require(isinstance(card, dict), f"card {expected_rank} must be an object")
        for forbidden in ("coverage", "percentage", "frequency", "corpus_count"):
            _require(forbidden not in card, f"pilot card cannot claim {forbidden}")

        surface_key = card.get("surface_key")
        display_form = card.get("display_form")
        card_id = card.get("card_id")
        _require(isinstance(surface_key, str) and surface_key, "card surface_key is required")
        _require(isinstance(display_form, str) and display_form, "card display_form is required")
        _require(normalize_surface(display_form) == surface_key, "display form and surface key disagree")
        _require(card_id == build_card_id("fr", surface_key), "card ID does not match its surface")
        _require(card_id not in card_ids, f"duplicate card ID: {card_id}")
        card_ids.add(card_id)
        _require(card.get("rank") == expected_rank, "pilot card ranks must be sequential")

        meanings = card.get("meanings")
        _require(isinstance(meanings, list) and meanings, f"card {surface_key} needs a meaning")
        local_sense_ids: set[str] = set()
        for meaning in meanings:
            _require(isinstance(meaning, dict), "meaning must be an object")
            sense_id = meaning.get("sense_id")
            _require(
                isinstance(sense_id, str) and sense_id.startswith("fixture_sense_fr_"),
                "pilot senses must use the fixture namespace",
            )
            _require(sense_id not in sense_ids, f"duplicate sense ID: {sense_id}")
            sense_ids.add(sense_id)
            local_sense_ids.add(sense_id)
            _require(meaning.get("assignment_status") == "curated_fixture", "pilot meaning status is invalid")
            _require(bool(meaning.get("part_of_speech")), "meaning part_of_speech is required")
            _require(bool(meaning.get("translation")), "meaning translation is required")

        examples = card.get("examples")
        _require(isinstance(examples, list) and examples, f"card {surface_key} needs an example")
        for example in examples:
            _require(isinstance(example, dict), "example must be an object")
            example_id = example.get("example_id")
            _require(
                isinstance(example_id, str) and example_id.startswith("fixture_example_fr_"),
                "pilot examples must use the fixture namespace",
            )
            _require(example_id not in example_ids, f"duplicate example ID: {example_id}")
            example_ids.add(example_id)
            _require(example.get("sense_id") in local_sense_ids, "example references another card's sense")
            _require(example.get("provenance") == "curated_fixture", "pilot example provenance is invalid")
            _require(bool(example.get("target")), "example target text is required")
            _require(bool(example.get("english")), "example English text is required")


def validate_manifest(manifest: dict[str, Any], deck_path: Path) -> dict[str, Any]:
    _require(
        manifest.get("manifest_version") == RELEASE_MANIFEST_VERSION,
        "unsupported release manifest version",
    )
    _require(manifest.get("language") == "fr", "pilot release language must be fr")
    _require(manifest.get("locale") == "fr-FR", "pilot release locale must be fr-FR")
    _require(manifest.get("mode") == "speech", "pilot release mode must be speech")
    _require(
        manifest.get("publication_status") == "curated_fixture",
        "pilot release must be visibly marked as a curated fixture",
    )
    _require(manifest.get("progress_namespace") == "pilot", "pilot progress must be isolated")
    _require(manifest.get("deck_path") == deck_path.name, "manifest deck path is invalid")
    _require(
        manifest.get("deck_content_id") == file_content_id(deck_path),
        "deck content hash does not match manifest",
    )
    wsd = manifest.get("wsd")
    _require(
        isinstance(wsd, dict)
        and wsd.get("enabled") is False
        and wsd.get("status") == "not_connected",
        "pilot must not claim WSD output",
    )

    deck = _load_object(deck_path)
    validate_deck(deck)
    _require(deck.get("release_id") == manifest.get("release_id"), "release IDs disagree")
    _require(len(deck["cards"]) == manifest.get("card_count"), "card count does not match manifest")
    return deck


def validate_active_release(active: dict[str, Any]) -> None:
    _require(
        active.get("manifest_version") == ACTIVE_RELEASE_VERSION,
        "unsupported active release version",
    )
    _require(active.get("language") == "fr", "active release language must be fr")
    _require(active.get("mode") == "speech", "active release mode must be speech")
    _require(bool(active.get("release_id")), "active release_id is required")
    manifest_path = active.get("manifest_path")
    _require(
        isinstance(manifest_path, str)
        and manifest_path.endswith("/manifest.json")
        and ".." not in Path(manifest_path).parts,
        "active manifest_path is unsafe",
    )


def validate_release_bundle(release_directory: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = _load_object(release_directory / "manifest.json")
    deck = validate_manifest(manifest, release_directory / "deck.json")
    return manifest, deck
