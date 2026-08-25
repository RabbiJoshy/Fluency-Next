"""Build the exact set of releases the app is allowed to select."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fluency.core.workspace import Workspace
from fluency.core.io import atomic_write
from fluency.release.validation import (
    RELEASE_CATALOG_VERSION,
    ReleaseValidationError,
    validate_release_bundle,
)


def build_catalog(workspace: Workspace, language: str, mode: str) -> dict[str, Any]:
    root = workspace.root / "releases" / language / mode
    active_path = root / "active.json"
    active_id = None
    if active_path.is_file():
        active_id = json.loads(active_path.read_text(encoding="utf-8")).get("release_id")
    candidates = []
    if root.is_dir():
        for directory in sorted(root.iterdir()):
            if not directory.is_dir() or not (directory / "composition.json").is_file():
                continue
            try:
                manifest, deck, composition = validate_release_bundle(directory)
            except ReleaseValidationError:
                if directory.name == active_id:
                    raise
                continue
            fallback_layers = sum("fallback" in selection for selection in composition["layers"].values())
            candidates.append({
                "release_id": manifest["release_id"],
                "label": composition["label"],
                "created_at": manifest["created_at"],
                "publication_status": manifest["publication_status"],
                "card_count": len(deck["cards"]),
                "manifest_path": f"{manifest['release_id']}/manifest.json",
                "deck_content_id": manifest["deck_content_id"],
                "composition_content_id": manifest["composition_content_id"],
                "active": manifest["release_id"] == active_id,
                "fallback_layers": fallback_layers,
                "wsd_status": manifest["wsd"]["status"],
            })
    candidates.sort(key=lambda item: (item["created_at"], item["release_id"]), reverse=True)
    return {
        "catalog_version": RELEASE_CATALOG_VERSION,
        "language": language,
        "mode": mode,
        "active_release_id": active_id,
        "candidates": candidates,
    }


def write_catalog(workspace: Workspace, language: str, mode: str) -> Path:
    root = workspace.root / "releases" / language / mode
    path = root / "catalog.json"
    atomic_write(path, build_catalog(workspace, language, mode), workspace.root / ".fluency" / "temporary")
    return path
