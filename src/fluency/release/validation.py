"""Strict validation for compact app release bundles."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fluency.core.hashing import file_content_id, validate_content_id
from fluency.core.identity import build_card_id
from fluency.languages.french.surfaces import normalize_surface


ACTIVE_RELEASE_VERSION = "active-release/v1"
RELEASE_MANIFEST_VERSION = "release-manifest/v1"
SPEECH_DECK_VERSION = "speech-deck/v1"
LAYER_SELECTION_VERSION = "layer-selection/v1"
RELEASE_COMPOSITION_VERSION = "release-composition/v1"
RELEASE_CATALOG_VERSION = "release-catalog/v1"
REQUIRED_SPEECH_LAYERS = {"inventory", "sense_menu", "sentences", "example_selection"}


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


def validate_composition(composition: dict[str, Any]) -> None:
    _require(
        composition.get("composition_version") == RELEASE_COMPOSITION_VERSION,
        "unsupported release composition version",
    )
    for field in ("release_id", "label", "language", "locale", "mode", "created_at", "publication_status", "progress_namespace"):
        _require(isinstance(composition.get(field), str) and composition[field], f"composition {field} is required")
    _require(composition.get("conflict_policy") == "error", "composition conflicts must fail")
    fallback_policy = composition.get("fallback_policy")
    _require(fallback_policy in {"none", "explicit_missing_only"}, "invalid fallback policy")
    layers = composition.get("layers")
    _require(isinstance(layers, dict), "composition layers are required")
    _require(REQUIRED_SPEECH_LAYERS.issubset(layers), "required Speech layers are missing")
    omitted = composition.get("omitted_layers")
    _require(isinstance(omitted, list), "omitted_layers must be a list")
    omitted_names: set[str] = set()
    fallback_count = 0
    for layer, selection in layers.items():
        _require(isinstance(layer, str) and layer, "layer name is invalid")
        _require(isinstance(selection, dict), f"layer {layer} selection must be an object")
        _require(selection.get("selection_version") == LAYER_SELECTION_VERSION, f"layer {layer} has an unsupported selection version")
        _require(selection.get("source_type") in {"run", "fixture", "manual"}, f"layer {layer} source type is invalid")
        _require(bool(selection.get("source_id")), f"layer {layer} source ID is required")
        artifact_id = selection.get("artifact_id")
        try:
            validate_content_id(artifact_id)
        except (TypeError, ValueError):
            raise ReleaseValidationError(f"layer {layer} artifact ID is invalid") from None
        _require(isinstance(selection.get("record_count"), int) and selection["record_count"] >= 0, f"layer {layer} record count is invalid")
        requirements = selection.get("requires")
        _require(isinstance(requirements, dict), f"layer {layer} requirements must be an object")
        fallback = selection.get("fallback")
        if fallback is not None:
            fallback_count += 1
            _require(fallback_policy == "explicit_missing_only", f"layer {layer} declares fallback while fallback policy is none")
            _require(isinstance(fallback, dict) and fallback.get("policy") == "missing_only", f"layer {layer} fallback must be explicit missing_only")
            _require(bool(fallback.get("source_id")) and bool(fallback.get("artifact_id")), f"layer {layer} fallback provenance is incomplete")
            try:
                validate_content_id(fallback["artifact_id"])
            except (TypeError, ValueError):
                raise ReleaseValidationError(f"layer {layer} fallback artifact ID is invalid") from None
        for dependency, expected_artifact in requirements.items():
            _require(dependency in layers, f"layer {layer} requires missing layer {dependency}")
            _require(layers[dependency].get("artifact_id") == expected_artifact, f"layer {layer} requires a different {dependency} artifact")
    _require(fallback_policy != "explicit_missing_only" or fallback_count > 0, "explicit fallback policy has no fallback layer")
    for item in omitted:
        _require(isinstance(item, dict) and bool(item.get("layer")) and bool(item.get("reason")), "omitted layer entry is invalid")
        omitted_names.add(item["layer"])
    _require(not (set(layers) & omitted_names), "a layer cannot be both selected and omitted")


def validate_manifest(
    manifest: dict[str, Any], deck_path: Path, composition_path: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
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
    _require(manifest.get("composition_path") == composition_path.name, "manifest composition path is invalid")
    _require(
        manifest.get("composition_content_id") == file_content_id(composition_path),
        "composition content hash does not match manifest",
    )
    wsd = manifest.get("wsd")
    _require(
        isinstance(wsd, dict)
        and wsd.get("enabled") is False
        and wsd.get("status") == "not_connected",
        "pilot must not claim WSD output",
    )

    deck = _load_object(deck_path)
    composition = _load_object(composition_path)
    validate_composition(composition)
    validate_deck(deck)
    _require(deck.get("release_id") == manifest.get("release_id"), "release IDs disagree")
    _require(composition.get("release_id") == manifest.get("release_id"), "composition and manifest release IDs disagree")
    for field in ("language", "locale", "mode", "created_at", "publication_status", "progress_namespace"):
        _require(composition.get(field) == manifest.get(field), f"composition and manifest {field} disagree")
    _require(len(deck["cards"]) == manifest.get("card_count"), "card count does not match manifest")
    wsd_selection = composition["layers"].get("wsd_assignments")
    if wsd_selection is None:
        _require(wsd.get("enabled") is False, "manifest cannot enable an omitted WSD layer")
        omitted = {item["layer"]: item["reason"] for item in composition["omitted_layers"]}
        _require(omitted.get("wsd_assignments") == wsd.get("status"), "WSD omission reason disagrees")
    else:
        _require(wsd.get("enabled") is True and wsd.get("source_id") == wsd_selection["source_id"], "WSD manifest provenance disagrees")
    return deck, composition


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
        and manifest_path == f"{active.get('release_id')}/manifest.json"
        and ".." not in Path(manifest_path).parts,
        "active manifest_path is unsafe",
    )


def validate_release_bundle(release_directory: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    manifest = _load_object(release_directory / "manifest.json")
    deck, composition = validate_manifest(
        manifest,
        release_directory / "deck.json",
        release_directory / "composition.json",
    )
    return manifest, deck, composition
