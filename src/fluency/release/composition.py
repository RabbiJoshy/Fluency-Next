"""Compose an immutable app release from an exact, reviewable layer selection."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any

from fluency.core.artifacts import artifact_directory, verify_artifact
from fluency.core.hashing import content_id
from fluency.core.workspace import Workspace
from fluency.release.app_compat import (
    APP_CONTRACT_VERSION,
    build_app_compatibility_assets,
    build_app_conjugations,
)
from fluency.release.io import json_bytes
from fluency.release.validation import (
    RELEASE_MANIFEST_VERSION,
    validate_composition,
    validate_deck,
    validate_release_bundle,
)


SAFE_RELEASE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def load_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON file must contain an object: {path}")
    return value


def compose_release(workspace: Workspace, composition: dict[str, Any], deck: dict[str, Any]) -> Path:
    """Publish a new immutable bundle; never activate it implicitly."""

    validate_composition(composition)
    validate_deck(deck)
    release_id = composition["release_id"]
    if not SAFE_RELEASE_ID.fullmatch(release_id):
        raise ValueError("unsafe release ID")
    for field in ("release_id", "language", "mode"):
        if deck.get(field) != composition.get(field):
            raise ValueError(f"deck and composition {field} disagree")

    deck_bytes = json_bytes(deck)
    composition_bytes = json_bytes(composition)
    app_index, app_examples = build_app_compatibility_assets(deck)
    app_index_bytes = json_bytes(app_index)
    app_examples_bytes = json_bytes(app_examples)
    study_structure_bytes = json_bytes(deck["study_structure"])
    optional_app_assets: dict[str, bytes] = {}
    conjugations_selection = composition["layers"].get("conjugations")
    if conjugations_selection is not None:
        metadata = verify_artifact(workspace, conjugations_selection["artifact_id"])
        if metadata.schema != "conjugation-layer/v1":
            raise ValueError("selected conjugations artifact has the wrong schema")
        conjugations_path = artifact_directory(workspace, metadata.artifact_id) / metadata.filename
        conjugations_layer = load_json_object(conjugations_path)
        if (
            conjugations_layer.get("language") != composition["language"]
            or conjugations_layer.get("locale") != composition["locale"]
        ):
            raise ValueError("selected conjugations artifact has the wrong language/locale")
        if conjugations_layer.get("inputs", {}).get("sense_menu_content_id") != composition["layers"]["sense_menu"]["artifact_id"]:
            raise ValueError("selected conjugations artifact was built from another sense menu")
        optional_app_assets["app/conjugations.json"] = json_bytes(
            build_app_conjugations(conjugations_layer)
        )
    wsd_selection = composition["layers"].get("wsd_assignments")
    if wsd_selection is None:
        omissions = {item["layer"]: item["reason"] for item in composition["omitted_layers"]}
        wsd = {"enabled": False, "status": omissions.get("wsd_assignments", "not_connected")}
    else:
        wsd = {"enabled": True, "status": "selected", "source_id": wsd_selection["source_id"]}
    app_contract = {
        "contract_version": APP_CONTRACT_VERSION,
        "index_path": "app/vocabulary.index.json",
        "index_content_id": content_id(app_index_bytes),
        "examples_path": "app/vocabulary.examples.json",
        "examples_content_id": content_id(app_examples_bytes),
        "study_structure_path": "app/study-structure.json",
        "study_structure_content_id": content_id(study_structure_bytes),
    }
    if "app/conjugations.json" in optional_app_assets:
        app_contract.update({
            "conjugations_path": "app/conjugations.json",
            "conjugations_content_id": content_id(optional_app_assets["app/conjugations.json"]),
        })
    manifest = {
        "manifest_version": RELEASE_MANIFEST_VERSION,
        "release_id": release_id,
        "language": composition["language"],
        "locale": composition["locale"],
        "mode": composition["mode"],
        "created_at": composition["created_at"],
        "publication_status": composition["publication_status"],
        "card_count": len(deck["cards"]),
        "deck_path": "deck.json",
        "deck_content_id": content_id(deck_bytes),
        "composition_path": "composition.json",
        "composition_content_id": content_id(composition_bytes),
        "progress_namespace": composition["progress_namespace"],
        "wsd": wsd,
        "app_contract": app_contract,
    }
    manifest_bytes = json_bytes(manifest)

    release_root = workspace.root / "releases" / composition["language"] / composition["mode"]
    release_directory = release_root / release_id
    temporary_root = workspace.root / ".fluency" / "temporary"
    release_root.mkdir(parents=True, exist_ok=True)
    temporary_root.mkdir(parents=True, exist_ok=True)
    expected = {
        "deck.json": deck_bytes,
        "composition.json": composition_bytes,
        "manifest.json": manifest_bytes,
        "app/vocabulary.index.json": app_index_bytes,
        "app/vocabulary.examples.json": app_examples_bytes,
        "app/study-structure.json": study_structure_bytes,
        **optional_app_assets,
    }
    if release_directory.exists():
        if any(not (release_directory / name).is_file() or (release_directory / name).read_bytes() != payload for name, payload in expected.items()):
            raise ValueError(f"immutable release already exists with different content: {release_directory}")
    else:
        temporary = Path(tempfile.mkdtemp(prefix="compose-release-", dir=temporary_root))
        try:
            for name, payload in expected.items():
                path = temporary / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(payload)
            os.replace(temporary, release_directory)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
    validate_release_bundle(release_directory)
    return release_directory
