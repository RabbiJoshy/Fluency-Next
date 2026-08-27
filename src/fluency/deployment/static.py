"""Build a self-contained, inactive static site from exact release selections."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
from typing import Any

from fluency.artist.release import validate_lyrics_release
from fluency.core.hashing import canonical_content_id, file_content_id
from fluency.core.workspace import Workspace
from fluency.core.languages import language_keys
from fluency.core.io import json_bytes
from fluency.release.validation import validate_release_bundle


MANIFEST_VERSION = "static-deployment/v1"
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
LANGUAGE_KEYS = language_keys()
EXCLUDED_APP_ROOTS = frozenset({"backend", "docs", "lyrics-audit"})


class StaticDeploymentError(ValueError):
    """Raised when a deployable site cannot be composed without mutable inputs."""


def _object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise StaticDeploymentError(f"required JSON is unavailable or invalid: {path}") from error
    if not isinstance(value, dict):
        raise StaticDeploymentError(f"required JSON must contain an object: {path}")
    return value


def _copy_tree(source: Path, target: Path, *, exclude_app_development: bool = False) -> None:
    def ignored(directory: str, names: list[str]) -> set[str]:
        if not exclude_app_development or Path(directory) != source:
            return set()
        return set(names) & EXCLUDED_APP_ROOTS

    shutil.copytree(source, target, ignore=ignored)


def _file_record(path: Path, root: Path, *, url_prefix: str = "/") -> dict[str, Any]:
    relative = path.relative_to(root).as_posix()
    return {
        "path": url_prefix.rstrip("/") + "/" + relative,
        "bytes": path.stat().st_size,
        "sha256": file_content_id(path).removeprefix("sha256:"),
    }


def _release_files(root: Path, base_url: str) -> list[dict[str, Any]]:
    return [
        _file_record(path, root, url_prefix=base_url)
        for path in sorted(item for item in root.rglob("*") if item.is_file())
    ]


def _validate_site(site: Path, manifest: dict[str, Any]) -> None:
    forbidden = [site / "backend", site / "lyrics-audit", site / "docs"]
    if any(path.exists() for path in forbidden):
        raise StaticDeploymentError("deployment contains development-only or backend files")
    if not (site / "index.html").is_file() or not (site / "service-worker.js").is_file():
        raise StaticDeploymentError("deployment app shell is incomplete")
    public_services = _object(site / "config/config.json").get("publicServices")
    spotify_client_id = (
        public_services.get("spotifyClientId") if isinstance(public_services, dict) else None
    )
    if (
        not isinstance(spotify_client_id, str)
        or re.fullmatch(r"[A-Za-z0-9]{16,128}", spotify_client_id) is None
    ):
        raise StaticDeploymentError("deployment has no valid public Spotify OAuth client ID")
    progress_sync_url = (
        public_services.get("progressSyncUrl") if isinstance(public_services, dict) else None
    )
    if (
        not isinstance(progress_sync_url, str)
        or re.fullmatch(r"https://script\.google\.com/macros/s/[A-Za-z0-9_-]+/exec", progress_sync_url)
        is None
    ):
        raise StaticDeploymentError("deployment has no valid public progress sync URL")
    for record in manifest.get("files", []):
        relative = record.get("path")
        if not isinstance(relative, str):
            raise StaticDeploymentError("deployment file ledger is invalid")
        pure = PurePosixPath(relative)
        if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
            raise StaticDeploymentError("deployment file path is unsafe")
        path = site.joinpath(*pure.parts)
        if (
            not path.is_file()
            or path.stat().st_size != record.get("bytes")
            or file_content_id(path) != record.get("content_id")
        ):
            raise StaticDeploymentError(f"deployment file ledger drifted: {relative}")


def build_static_deployment(
    repository_root: Path,
    workspace: Workspace,
    *,
    deployment_id: str,
    speech_releases: dict[str, str],
    lyrics_release_id: str,
) -> Path:
    """Compose exact releases into a static site without activating or deploying it."""

    if SAFE_ID.fullmatch(deployment_id) is None or SAFE_ID.fullmatch(lyrics_release_id) is None:
        raise StaticDeploymentError("unsafe deployment or Lyrics release ID")
    if not speech_releases:
        raise StaticDeploymentError("at least one explicit Speech release is required")
    if any(language not in LANGUAGE_KEYS or SAFE_ID.fullmatch(release_id) is None for language, release_id in speech_releases.items()):
        raise StaticDeploymentError("Speech release selections contain an unsupported language or unsafe ID")
    destination = workspace.root / "deployments" / deployment_id
    if destination.exists():
        manifest = _object(destination / "manifest.json")
        _validate_site(destination / "site", manifest)
        return destination

    selected_speech: dict[str, tuple[Path, dict[str, Any], dict[str, Any]]] = {}
    for language, release_id in sorted(speech_releases.items()):
        release = workspace.root / "releases" / language / "speech" / release_id
        manifest, _deck, composition = validate_release_bundle(release)
        if manifest.get("language") != language or manifest.get("mode") != "speech":
            raise StaticDeploymentError(f"Speech release identity mismatch: {language}/{release_id}")
        selected_speech[language] = (release, manifest, composition)
    lyrics_release = workspace.root / "releases/lyrics" / lyrics_release_id
    lyrics_manifest, _lyrics_composition = validate_lyrics_release(lyrics_release)

    temporary_root = workspace.root / ".fluency/temporary"
    temporary_root.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix="static-deployment-", dir=temporary_root))
    try:
        site = temporary / "site"
        _copy_tree(repository_root / "app", site, exclude_app_development=True)
        config_path = site / "config/config.json"
        config = _object(config_path)
        offline_sources: list[dict[str, Any]] = []
        selected: dict[str, Any] = {"speech": {}, "lyrics": {}}

        for language, (release, manifest, composition) in selected_speech.items():
            release_id = manifest["release_id"]
            target = site / "releases" / language / "speech" / release_id
            _copy_tree(release, target)
            base = f"/releases/{language}/speech/{release_id}"
            contract = manifest["app_contract"]
            language_config = config.get("languages", {}).get(LANGUAGE_KEYS[language])
            if not isinstance(language_config, dict):
                raise StaticDeploymentError(f"app config has no language entry for {language}")
            mapping = {
                "indexPath": contract.get("index_path"),
                "examplesPath": contract.get("examples_path"),
                "studyStructurePath": contract.get("study_structure_path"),
                "conjugationsPath": contract.get("conjugations_path"),
            }
            for field, relative in mapping.items():
                language_config[field] = f"{base}/{relative}" if relative else None
            language_config["releaseManifestPath"] = f"{base}/manifest.json"
            language_config["releaseCompositionPath"] = f"{base}/composition.json"
            files = _release_files(target, base)
            offline_sources.append({
                "id": f"speech-{language}",
                "name": f"{language_config.get('name', language.upper())} Speech",
                "scopeLabel": f"{manifest['card_count']} cards · {release_id}",
                "contentVersion": release_id,
                "storageBytes": sum(item["bytes"] for item in files),
                "transferBytes": sum(item["bytes"] for item in files),
                "files": files,
            })
            selected["speech"][language] = {
                "release_id": release_id,
                "manifest_content_id": file_content_id(release / "manifest.json"),
                "composition_content_id": file_content_id(release / "composition.json"),
            }

        lyrics_target = site / "releases/lyrics" / lyrics_release_id
        _copy_tree(lyrics_release, lyrics_target)
        lyrics_base = f"/releases/lyrics/{lyrics_release_id}"
        (site / "config/artists.json").write_bytes(
            (lyrics_release / lyrics_manifest["catalog_path"]).read_bytes()
        )
        lyrics_files = _release_files(lyrics_target, lyrics_base)
        offline_sources.append({
            "id": "lyrics-active",
            "name": "Lyrics",
            "scopeLabel": f"{lyrics_manifest['artist_count']} sources · {lyrics_release_id}",
            "contentVersion": lyrics_release_id,
            "storageBytes": sum(item["bytes"] for item in lyrics_files),
            "transferBytes": sum(item["bytes"] for item in lyrics_files),
            "files": lyrics_files,
        })
        selected["lyrics"] = {
            "release_id": lyrics_release_id,
            "manifest_content_id": file_content_id(lyrics_release / "manifest.json"),
            "composition_content_id": file_content_id(lyrics_release / "composition.json"),
        }
        config_path.write_bytes(json_bytes(config))
        offline = {
            "schemaVersion": 1,
            "contentVersion": deployment_id,
            "generatedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "sources": offline_sources,
        }
        (site / "config/offline-content-manifest.json").write_bytes(json_bytes(offline))

        site_files = [
            {
                "path": path.relative_to(site).as_posix(),
                "bytes": path.stat().st_size,
                "content_id": file_content_id(path),
            }
            for path in sorted(item for item in site.rglob("*") if item.is_file())
        ]
        deployment_manifest = {
            "manifest_version": MANIFEST_VERSION,
            "deployment_id": deployment_id,
            "status": "inactive_local_candidate",
            "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "implementation_content_id": canonical_content_id({
                "builder": file_content_id(Path(__file__)),
                "app_contract": file_content_id(repository_root / "app/js/data-contracts.js"),
            }),
            "selected_releases": selected,
            "excluded_app_roots": sorted(EXCLUDED_APP_ROOTS),
            "file_count": len(site_files),
            "total_bytes": sum(item["bytes"] for item in site_files),
            "files": site_files,
            "deployment_status": "not_deployed",
        }
        (temporary / "manifest.json").write_bytes(json_bytes(deployment_manifest))
        _validate_site(site, deployment_manifest)
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return destination
