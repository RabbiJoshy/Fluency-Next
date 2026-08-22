"""Strict validation for compact app release bundles."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from fluency.core.hashing import file_content_id, validate_content_id
from fluency.core.identity import build_card_id
from fluency.languages.french.surfaces import normalize_surface
from fluency.release.app_compat import APP_CONTRACT_VERSION


ACTIVE_RELEASE_VERSION = "active-release/v1"
RELEASE_MANIFEST_VERSION = "release-manifest/v1"
SPEECH_DECK_VERSION = "speech-deck/v1"
LAYER_SELECTION_VERSION = "layer-selection/v1"
RELEASE_COMPOSITION_VERSION = "release-composition/v1"
RELEASE_CATALOG_VERSION = "release-catalog/v1"
REQUIRED_SPEECH_LAYERS = {"inventory", "sense_menu", "sentences", "example_selection"}
_LANGUAGE_PATTERN = re.compile(r"^[a-z]{2,3}$")


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
    language = deck.get("language")
    _require(isinstance(language, str) and _LANGUAGE_PATTERN.fullmatch(language) is not None, "deck language is invalid")
    _require(deck.get("mode") == "speech", "deck mode must be speech")
    cards = deck.get("cards")
    _require(isinstance(cards, list) and cards, "deck cards must be a non-empty list")
    study_structure = deck.get("study_structure")
    _require(isinstance(study_structure, dict), "deck study_structure is required")
    _require(study_structure.get("structure_version") == "study-structure/v1", "unsupported study structure")
    levels = study_structure.get("levels")
    _require(isinstance(levels, list) and levels, "study structure needs levels")

    card_ids: set[str] = set()
    sense_ids: set[str] = set()
    example_ids: set[str] = set()
    for expected_rank, card in enumerate(cards, start=1):
        _require(isinstance(card, dict), f"card {expected_rank} must be an object")
        for forbidden in ("coverage", "percentage", "corpus_count"):
            _require(forbidden not in card, f"pilot card cannot claim {forbidden}")

        surface_key = card.get("surface_key")
        display_form = card.get("display_form")
        card_id = card.get("card_id")
        _require(isinstance(surface_key, str) and surface_key, "card surface_key is required")
        _require(isinstance(display_form, str) and display_form, "card display_form is required")
        if language == "fr":
            _require(normalize_surface(display_form) == surface_key, "display form and surface key disagree")
        _require(card_id == build_card_id(language, surface_key), "card ID does not match its surface")
        _require(card_id not in card_ids, f"duplicate card ID: {card_id}")
        card_ids.add(card_id)
        _require(card.get("rank") == expected_rank, "deck card ranks must be sequential")
        frequency = card.get("frequency")
        if frequency is not None:
            _require(isinstance(frequency, dict) and bool(frequency.get("basis")), "card frequency metadata is invalid")
            for field in ("primary_count", "aggregate_count"):
                value = frequency.get(field)
                _require(isinstance(value, int) and value >= 0, f"card frequency {field} is invalid")
        _require("legacy_aliases" not in card, "legacy aliases are not allowed in clean releases")

        meanings = card.get("meanings")
        _require(isinstance(meanings, list) and meanings, f"card {surface_key} needs a meaning")
        local_sense_ids: set[str] = set()
        local_sense_statuses: dict[str, str] = {}
        for meaning in meanings:
            _require(isinstance(meaning, dict), "meaning must be an object")
            sense_id = meaning.get("sense_id")
            _require(isinstance(sense_id, str) and sense_id, "sense ID is required")
            _require(sense_id not in sense_ids, f"duplicate sense ID: {sense_id}")
            sense_ids.add(sense_id)
            local_sense_ids.add(sense_id)
            assignment_status = meaning.get("assignment_status")
            _require(bool(assignment_status), "meaning assignment status is invalid")
            local_sense_statuses[sense_id] = assignment_status
            _require(bool(meaning.get("part_of_speech")), "meaning part_of_speech is required")
            _require(bool(meaning.get("translation")), "meaning translation is required")
            _require("legacy_sources" not in meaning, "legacy meaning sources are not allowed")

        examples = card.get("examples")
        _require(isinstance(examples, list), f"card {surface_key} examples must be a list")
        for example in examples:
            _require(isinstance(example, dict), "example must be an object")
            example_id = example.get("example_id")
            _require(isinstance(example_id, str) and example_id, "example ID is required")
            _require(example_id not in example_ids, f"duplicate example ID: {example_id}")
            example_ids.add(example_id)
            assignment_status = example.get("assignment_status")
            _require(
                assignment_status in {"assigned", "unassigned"},
                "example assignment status is invalid",
            )
            if assignment_status == "assigned":
                _require(
                    example.get("sense_id") in local_sense_ids,
                    "assigned example must reference this card's sense",
                )
                _require(
                    local_sense_statuses[example["sense_id"]] != "unassigned",
                    "assigned example cannot target an unassigned meaning",
                )
            else:
                _require(
                    example.get("sense_id") is None,
                    "unassigned example cannot claim a sense",
                )
            _require(bool(example.get("provenance")), "example provenance is invalid")
            _require(bool(example.get("target")), "example target text is required")
            _require(bool(example.get("english")), "example English text is required")
            _require("legacy_sources" not in example, "legacy example sources are not allowed")

    structured_card_ids: list[str] = []
    level_ids: set[str] = set()
    set_ids: set[str] = set()
    for level in levels:
        _require(isinstance(level, dict) and bool(level.get("level_id")) and bool(level.get("label")), "study level is invalid")
        _require(level["level_id"] not in level_ids, f"duplicate level ID: {level['level_id']}")
        level_ids.add(level["level_id"])
        sets = level.get("sets")
        _require(isinstance(sets, list) and sets, f"level {level['level_id']} needs sets")
        for study_set in sets:
            _require(isinstance(study_set, dict) and bool(study_set.get("set_id")) and bool(study_set.get("label")), "study set is invalid")
            _require(study_set["set_id"] not in set_ids, f"duplicate set ID: {study_set['set_id']}")
            set_ids.add(study_set["set_id"])
            ids = study_set.get("card_ids")
            _require(isinstance(ids, list) and ids, f"set {study_set['set_id']} needs card IDs")
            _require(len(ids) == len(set(ids)), f"set {study_set['set_id']} repeats a card")
            structured_card_ids.extend(ids)
    _require(len(structured_card_ids) == len(set(structured_card_ids)), "a card appears in more than one study set")
    _require(set(structured_card_ids) == card_ids, "study structure and deck cards disagree")


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
    language = manifest.get("language")
    _require(isinstance(language, str) and _LANGUAGE_PATTERN.fullmatch(language) is not None, "release language is invalid")
    _require(isinstance(manifest.get("locale"), str) and manifest["locale"], "release locale is required")
    _require(manifest.get("mode") == "speech", "release mode must be speech")
    _require(isinstance(manifest.get("publication_status"), str) and manifest["publication_status"], "release publication status is required")
    _require(isinstance(manifest.get("progress_namespace"), str) and manifest["progress_namespace"], "release progress namespace is required")
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
    _require(isinstance(wsd, dict) and isinstance(wsd.get("enabled"), bool) and bool(wsd.get("status")), "release WSD metadata is invalid")
    app_contract = manifest.get("app_contract")
    _require(isinstance(app_contract, dict), "release app contract is required")
    _require(app_contract.get("contract_version") == APP_CONTRACT_VERSION, "unsupported app contract")
    for path_field, hash_field, expected_path in (
        ("index_path", "index_content_id", "app/vocabulary.index.json"),
        ("examples_path", "examples_content_id", "app/vocabulary.examples.json"),
    ):
        _require(app_contract.get(path_field) == expected_path, f"app contract {path_field} is invalid")
        asset_path = deck_path.parent / expected_path
        _require(asset_path.is_file(), f"app contract asset is missing: {expected_path}")
        _require(app_contract.get(hash_field) == file_content_id(asset_path), f"app contract {hash_field} disagrees")

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
    language = active.get("language")
    _require(isinstance(language, str) and _LANGUAGE_PATTERN.fullmatch(language) is not None, "active release language is invalid")
    _require(isinstance(active.get("mode"), str) and active["mode"], "active release mode is invalid")
    _require(bool(active.get("release_id")), "active release_id is required")
    manifest_path = active.get("manifest_path")
    _require(
        isinstance(manifest_path, str)
        and manifest_path == f"{active.get('release_id')}/manifest.json"
        and ".." not in Path(manifest_path).parts,
        "active manifest_path is unsafe",
    )


def validate_release_bundle(
    release_directory: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    manifest = _load_object(release_directory / "manifest.json")
    deck, composition = validate_manifest(
        manifest,
        release_directory / "deck.json",
        release_directory / "composition.json",
    )
    return manifest, deck, composition
