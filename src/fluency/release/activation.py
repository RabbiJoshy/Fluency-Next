"""Validated, atomic activation of an immutable release candidate."""

from __future__ import annotations

from fluency.core.workspace import Workspace
from fluency.release.catalog import write_catalog
from fluency.release.composition import SAFE_RELEASE_ID
from fluency.core.io import atomic_write
from fluency.release.validation import ACTIVE_RELEASE_VERSION, validate_active_release, validate_release_bundle


def activate_release(workspace: Workspace, language: str, mode: str, release_id: str):
    if not SAFE_RELEASE_ID.fullmatch(release_id):
        raise ValueError("unsafe release ID")
    root = workspace.root / "releases" / language / mode
    release_directory = root / release_id
    manifest, _, _ = validate_release_bundle(release_directory)
    if manifest["language"] != language or manifest["mode"] != mode:
        raise ValueError("release language or mode disagrees with activation target")
    active = {
        "manifest_version": ACTIVE_RELEASE_VERSION,
        "language": language,
        "mode": mode,
        "release_id": release_id,
        "manifest_path": f"{release_id}/manifest.json",
    }
    validate_active_release(active)
    atomic_write(root / "active.json", active, workspace.root / ".fluency" / "temporary")
    write_catalog(workspace, language, mode)
    return root / "active.json"
