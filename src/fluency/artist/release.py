"""Build and validate self-contained, immutable Lyrics catalog releases."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
from typing import Any

from fluency.core.hashing import file_content_id
from fluency.core.workspace import Workspace
from fluency.release.io import atomic_write, json_bytes


LYRICS_MANIFEST_VERSION = "lyrics-release-manifest/v1"
LYRICS_COMPOSITION_VERSION = "lyrics-release-composition/v1"
ACTIVE_LYRICS_VERSION = "active-lyrics-release/v1"
SAFE_RELEASE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
SAFE_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")
LANGUAGE_CODES = {"spanish": "es", "french": "fr", "dutch": "nl", "portuguese": "pt"}


class LyricsReleaseError(ValueError):
    """Raised when a Lyrics source or release violates the migration contract."""


def _timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _load_json(path: Path, expected: type | tuple[type, ...]) -> Any:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LyricsReleaseError(f"JSON source is unavailable or invalid: {path}") from error
    if not isinstance(value, expected):
        raise LyricsReleaseError(f"JSON source has the wrong top-level shape: {path}")
    return value


def _source_path(root: Path, relative: str) -> Path:
    """Resolve a legacy path safely, tolerating historical case-only drift."""

    pure = PurePosixPath(relative)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise LyricsReleaseError(f"unsafe source path: {relative}")
    candidate = root.joinpath(*pure.parts)
    if candidate.is_file():
        return candidate
    current = root
    for part in pure.parts:
        if not current.is_dir():
            raise LyricsReleaseError(f"source path does not exist: {relative}")
        matches = [child for child in current.iterdir() if child.name.casefold() == part.casefold()]
        if len(matches) != 1:
            raise LyricsReleaseError(f"source path does not resolve uniquely: {relative}")
        current = matches[0]
    if not current.is_file():
        raise LyricsReleaseError(f"source path is not a file: {relative}")
    return current


def _split_paths(source_root: Path, config: dict[str, Any]) -> tuple[Path, Path]:
    index_value = config.get("indexPath")
    examples_value = config.get("examplesPath")
    if not index_value and config.get("dataPath"):
        # Some old configs still name a deleted debugging monolith. Derive the
        # split paths from that declared location without requiring the dead
        # file itself to exist.
        stem = str(config["dataPath"]).removesuffix(".json")
        try:
            index_candidate = _source_path(source_root, stem + ".index.json")
            examples_candidate = _source_path(source_root, stem + ".examples.json")
            return index_candidate, examples_candidate
        except LyricsReleaseError:
            pass
        raise LyricsReleaseError(
            f"artist {config.get('name', '')} has no split index/examples assets"
        )
    if not isinstance(index_value, str) or not isinstance(examples_value, str):
        raise LyricsReleaseError(f"artist {config.get('name', '')} needs split app assets")
    return _source_path(source_root, index_value), _source_path(source_root, examples_value)


def _copy_file(source: Path, app_root: Path, relative: str, copied: dict[str, Path]) -> str:
    pure = PurePosixPath(relative)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise LyricsReleaseError(f"unsafe release asset path: {relative}")
    normalized = pure.as_posix()
    existing = copied.get(normalized)
    if existing is not None:
        if file_content_id(existing) != file_content_id(source):
            raise LyricsReleaseError(f"two assets disagree at release path: {normalized}")
        return normalized
    target = app_root.joinpath(*pure.parts)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    copied[normalized] = target
    return normalized


def _copy_filtered_master(
    source: Path,
    app_root: Path,
    relative: str,
    copied: dict[str, Path],
    allowed_card_ids: set[str],
) -> tuple[str, Path]:
    """Package only master rows reachable from the selected artist indexes."""

    pure = PurePosixPath(relative)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise LyricsReleaseError(f"unsafe release asset path: {relative}")
    normalized = pure.as_posix()
    existing = copied.get(normalized)
    if existing is not None:
        return normalized, existing
    master = _load_json(source, dict)
    missing = allowed_card_ids - set(master)
    if missing:
        raise LyricsReleaseError(
            f"selected artist indexes reference {len(missing)} absent master cards: {source}"
        )
    filtered = {card_id: value for card_id, value in master.items() if card_id in allowed_card_ids}
    target = app_root.joinpath(*pure.parts)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(json_bytes(filtered))
    copied[normalized] = target
    return normalized, target


def _sidecar_provenance(path: Path) -> dict[str, Any]:
    sidecar = Path(str(path) + ".meta.json")
    metadata = _load_json(sidecar, dict) if sidecar.is_file() else {}
    return {
        "provenance_status": "observed_sidecar" if metadata else "reconstructed_from_materialized_asset",
        "source_content_id": file_content_id(path),
        "sidecar_content_id": file_content_id(sidecar) if sidecar.is_file() else None,
        "step_name": metadata.get("step_name"),
        "step_version": metadata.get("step_version"),
        "generated_at": metadata.get("generated_at"),
        "ledger_run": metadata.get("ledger_run"),
        "corpus_profile_hash": metadata.get("corpus_profile_hash"),
    }


def _validate_index_examples(index_path: Path, examples_path: Path) -> tuple[int, int]:
    index = _load_json(index_path, list)
    examples = _load_json(examples_path, dict)
    if not index:
        raise LyricsReleaseError(f"artist index is empty: {index_path}")
    ids = [card.get("id") for card in index if isinstance(card, dict)]
    if len(ids) != len(index) or any(not isinstance(card_id, str) or not card_id for card_id in ids):
        raise LyricsReleaseError(f"artist index contains an invalid card ID: {index_path}")
    if len(set(ids)) != len(ids):
        raise LyricsReleaseError(f"artist index repeats a card ID: {index_path}")
    if set(examples) != set(ids):
        missing = len(set(ids) - set(examples))
        orphaned = len(set(examples) - set(ids))
        raise LyricsReleaseError(
            f"artist index/examples disagree ({missing} missing; {orphaned} orphaned): {index_path}"
        )
    return len(index), len(examples)


def _artist_config(
    source_root: Path,
    app_root: Path,
    copied: dict[str, Path],
    *,
    slug: str,
    source: dict[str, Any],
    release_id: str,
    master_card_ids: dict[Path, set[str]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if SAFE_SLUG.fullmatch(slug) is None:
        raise LyricsReleaseError(f"unsafe artist slug: {slug}")
    language_name = str(source.get("language", "spanish"))
    language = LANGUAGE_CODES.get(language_name)
    if language is None:
        raise LyricsReleaseError(f"unsupported artist language: {language_name}")
    index_source, examples_source = _split_paths(source_root, source)
    card_count, example_card_count = _validate_index_examples(index_source, examples_source)
    artist_base = f"Artists/{language}/{slug}"
    index_path = _copy_file(index_source, app_root, f"{artist_base}/index.json", copied)
    examples_path = _copy_file(examples_source, app_root, f"{artist_base}/examples.json", copied)

    master_value = source.get("masterPath") or f"Artists/{language_name}/vocabulary_master.json"
    master_source = _source_path(source_root, master_value)
    master_path, packaged_master = _copy_filtered_master(
        master_source,
        app_root,
        f"Artists/{language}/vocabulary_master.json",
        copied,
        master_card_ids[master_source.resolve()],
    )

    output: dict[str, Any] = {
        "name": source.get("name") or slug,
        "language": language_name,
        "masterPath": master_path,
        "indexPath": index_path,
        "examplesPath": examples_path,
        "colorTheme": source.get("colorTheme") or {},
        "maxLevel": source.get("maxLevel") or card_count,
        "releaseId": release_id,
        "releaseManifestPath": "Artists/release-manifest.json",
        "releaseCompositionPath": "Artists/release-composition.json",
    }
    songs_count = 0
    songs_value = source.get("songsPath")
    if isinstance(songs_value, str):
        songs_source = _source_path(source_root, songs_value)
        songs = _load_json(songs_source, dict)
        if songs.get("schemaVersion") != 1 or not isinstance(songs.get("songs"), list):
            raise LyricsReleaseError(f"unsupported song catalog: {songs_source}")
        songs_count = len(songs["songs"])
        output["songsPath"] = _copy_file(songs_source, app_root, f"{artist_base}/songs.json", copied)

    albums_value = source.get("albumsDictionary")
    if isinstance(albums_value, str):
        albums_source = _source_path(source_root, albums_value)
        output["albumsDictionary"] = _copy_file(
            albums_source, app_root, f"{artist_base}/albums.json", copied
        )

    copied_images: dict[str, str] = {}

    def migrate_image(value: Any) -> str:
        if not isinstance(value, str) or not value:
            return ""
        if value in copied_images:
            return copied_images[value]
        image_source = _source_path(source_root, value)
        image_path = _copy_file(
            image_source, app_root, f"{artist_base}/Images/{image_source.name}", copied
        )
        copied_images[value] = image_path
        return image_path

    image_map = source.get("albumImageMap")
    if isinstance(image_map, dict):
        output["albumImageMap"] = {
            str(album): migrate_image(path) for album, path in image_map.items()
        }
    for field in ("defaultAlbumArt", "pickerImage"):
        migrated = migrate_image(source.get(field))
        if migrated:
            output[field] = migrated

    provenance = _sidecar_provenance(index_source)
    layer_source_id = provenance.get("ledger_run") or provenance["source_content_id"]
    record = {
        "slug": slug,
        "name": output["name"],
        "language": language,
        "card_count": card_count,
        "example_card_count": example_card_count,
        "song_count": songs_count,
        "index_content_id": file_content_id(index_source),
        "examples_content_id": file_content_id(examples_source),
        "master_content_id": file_content_id(packaged_master),
        "source_master_content_id": file_content_id(master_source),
        "source_id": layer_source_id,
        "provenance": provenance,
        "migration_status": "retained_materialized_output_for_product_parity",
    }
    return output, record


def _release_file_records(app_root: Path) -> list[dict[str, Any]]:
    records = []
    for path in sorted(item for item in app_root.rglob("*") if item.is_file()):
        records.append({
            "path": path.relative_to(app_root.parent).as_posix(),
            "content_id": file_content_id(path),
            "bytes": path.stat().st_size,
        })
    return records


def build_lyrics_catalog_release(
    workspace: Workspace,
    *,
    source_repository: Path,
    release_id: str,
    include_artists: set[str] | None = None,
) -> Path:
    """Freeze every configured Artist app asset into one exact catalog release."""

    if SAFE_RELEASE_ID.fullmatch(release_id) is None:
        raise LyricsReleaseError("unsafe Lyrics release ID")
    source_root = source_repository.expanduser().resolve()
    source_config_path = source_root / "config/artists.json"
    source_config = _load_json(source_config_path, dict)
    if not source_config:
        raise LyricsReleaseError("source artist catalog is empty")
    if include_artists is not None:
        unknown = include_artists - set(source_config)
        if unknown:
            raise LyricsReleaseError(
                "unknown requested artist sources: " + ", ".join(sorted(unknown))
            )
        source_config = {
            slug: source for slug, source in source_config.items() if slug in include_artists
        }
        if not source_config:
            raise LyricsReleaseError("selected artist catalog is empty")
    release_root = workspace.root / "releases/lyrics"
    release_directory = release_root / release_id
    if release_directory.exists():
        validate_lyrics_release(release_directory)
        return release_directory

    temporary_root = workspace.root / ".fluency/temporary"
    temporary_root.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix="lyrics-release-", dir=temporary_root))
    try:
        app_root = temporary / "app"
        copied: dict[str, Path] = {}
        app_catalog: dict[str, Any] = {}
        artist_records: list[dict[str, Any]] = []
        master_card_ids: dict[Path, set[str]] = {}
        for slug, source in sorted(source_config.items()):
            if not isinstance(source, dict):
                raise LyricsReleaseError(f"artist config is not an object: {slug}")
            index_source, _ = _split_paths(source_root, source)
            index = _load_json(index_source, list)
            card_ids = {
                card.get("id") for card in index
                if isinstance(card, dict) and isinstance(card.get("id"), str)
            }
            language_name = str(source.get("language", "spanish"))
            master_value = source.get("masterPath") or f"Artists/{language_name}/vocabulary_master.json"
            master_source = _source_path(source_root, master_value).resolve()
            master_card_ids.setdefault(master_source, set()).update(card_ids)
        for slug, source in sorted(source_config.items()):
            if not isinstance(source, dict):
                raise LyricsReleaseError(f"artist config is not an object: {slug}")
            app_config, record = _artist_config(
                source_root, app_root, copied,
                slug=slug, source=source, release_id=release_id,
                master_card_ids=master_card_ids,
            )
            app_catalog[slug] = app_config
            artist_records.append(record)

        spotify_source = source_root / "Artists/spotify_tracks.json"
        if spotify_source.is_file():
            _copy_file(spotify_source, app_root, "Artists/spotify_tracks.json", copied)
            for artist in app_catalog.values():
                artist["spotifyPath"] = "Artists/spotify_tracks.json"

        catalog_path = app_root / "config/artists.json"
        catalog_path.parent.mkdir(parents=True, exist_ok=True)
        catalog_path.write_bytes(json_bytes(app_catalog))
        copied["config/artists.json"] = catalog_path

        created_at = _timestamp()
        layers = {
            f"artist:{record['slug']}": {
                "source_type": "retained_materialized_output",
                "source_id": record["source_id"],
                "artifact_ids": {
                    "index": record["index_content_id"],
                    "examples": record["examples_content_id"],
                    "master": record["master_content_id"],
                },
                "requires": {},
            }
            for record in artist_records
        }
        composition = {
            "composition_version": LYRICS_COMPOSITION_VERSION,
            "release_id": release_id,
            "mode": "lyrics",
            "created_at": created_at,
            "publication_status": "inactive_migration_audit",
            "conflict_policy": "error",
            "fallback_policy": "none",
            "layers": layers,
            "artists": artist_records,
            "omitted_layers": [
                {
                    "layer": "clean_artist_pipeline_rebuild",
                    "reason": "materialized parity assets retained; assignments were not recomputed",
                }
            ],
        }
        composition_path = temporary / "composition.json"
        composition_path.write_bytes(json_bytes(composition))
        composition_content_id = file_content_id(composition_path)
        manifest = {
            "manifest_version": LYRICS_MANIFEST_VERSION,
            "release_id": release_id,
            "mode": "lyrics",
            "created_at": created_at,
            "publication_status": "inactive_migration_audit",
            "catalog_path": "app/config/artists.json",
            "catalog_content_id": file_content_id(catalog_path),
            "composition_path": "composition.json",
            "composition_content_id": composition_content_id,
            "artist_count": len(artist_records),
            "languages": sorted({record["language"] for record in artist_records}),
            "card_count": sum(record["card_count"] for record in artist_records),
            "assignment_status": "historical_materialized_assignments_preserved_for_product_parity",
            "files": _release_file_records(app_root),
        }
        (temporary / "manifest.json").write_bytes(json_bytes(manifest))

        release_root.mkdir(parents=True, exist_ok=True)
        os.replace(temporary, release_directory)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    validate_lyrics_release(release_directory)
    return release_directory


def validate_lyrics_release(release_directory: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = _load_json(release_directory / "manifest.json", dict)
    composition = _load_json(release_directory / "composition.json", dict)
    if manifest.get("manifest_version") != LYRICS_MANIFEST_VERSION:
        raise LyricsReleaseError("unsupported Lyrics release manifest")
    if composition.get("composition_version") != LYRICS_COMPOSITION_VERSION:
        raise LyricsReleaseError("unsupported Lyrics release composition")
    release_id = manifest.get("release_id")
    if release_id != composition.get("release_id") or release_id != release_directory.name:
        raise LyricsReleaseError("Lyrics release IDs disagree")
    if manifest.get("mode") != "lyrics" or composition.get("mode") != "lyrics":
        raise LyricsReleaseError("Lyrics release mode is invalid")
    if manifest.get("composition_content_id") != file_content_id(release_directory / "composition.json"):
        raise LyricsReleaseError("Lyrics composition hash disagrees")
    catalog_path = release_directory / manifest.get("catalog_path", "")
    if not catalog_path.is_file() or manifest.get("catalog_content_id") != file_content_id(catalog_path):
        raise LyricsReleaseError("Lyrics catalog hash disagrees")
    catalog = _load_json(catalog_path, dict)
    if len(catalog) != manifest.get("artist_count") or not catalog:
        raise LyricsReleaseError("Lyrics artist count disagrees")

    declared: set[str] = set()
    for file_record in manifest.get("files", []):
        if not isinstance(file_record, dict):
            raise LyricsReleaseError("Lyrics file record is invalid")
        relative = file_record.get("path")
        if not isinstance(relative, str) or relative in declared:
            raise LyricsReleaseError("Lyrics file path is invalid or repeated")
        pure = PurePosixPath(relative)
        if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
            raise LyricsReleaseError("Lyrics file path is unsafe")
        path = release_directory.joinpath(*pure.parts)
        if not path.is_file():
            raise LyricsReleaseError(f"Lyrics release asset is missing: {relative}")
        if file_record.get("bytes") != path.stat().st_size or file_record.get("content_id") != file_content_id(path):
            raise LyricsReleaseError(f"Lyrics release asset hash disagrees: {relative}")
        declared.add(relative)

    for slug, config in catalog.items():
        if SAFE_SLUG.fullmatch(slug) is None or not isinstance(config, dict):
            raise LyricsReleaseError("Lyrics app catalog contains an invalid artist")
        for field in ("name", "language", "indexPath", "examplesPath", "masterPath", "releaseId"):
            if not isinstance(config.get(field), str) or not config[field]:
                raise LyricsReleaseError(f"Lyrics artist {slug} is missing {field}")
        if config["releaseId"] != release_id:
            raise LyricsReleaseError(f"Lyrics artist {slug} points at another release")
        for field in ("indexPath", "examplesPath", "masterPath", "songsPath", "spotifyPath", "albumsDictionary", "defaultAlbumArt", "pickerImage"):
            value = config.get(field)
            if value and f"app/{value}" not in declared:
                raise LyricsReleaseError(f"Lyrics artist {slug} references an undeclared {field}")
        for value in (config.get("albumImageMap") or {}).values():
            if f"app/{value}" not in declared:
                raise LyricsReleaseError(f"Lyrics artist {slug} references undeclared artwork")
        index_path = release_directory / "app" / config["indexPath"]
        examples_path = release_directory / "app" / config["examplesPath"]
        _validate_index_examples(index_path, examples_path)
    return manifest, composition


def activate_lyrics_release(workspace: Workspace, release_id: str) -> Path:
    if SAFE_RELEASE_ID.fullmatch(release_id) is None:
        raise LyricsReleaseError("unsafe Lyrics release ID")
    release_root = workspace.root / "releases/lyrics"
    validate_lyrics_release(release_root / release_id)
    active = {
        "manifest_version": ACTIVE_LYRICS_VERSION,
        "mode": "lyrics",
        "release_id": release_id,
        "manifest_path": f"{release_id}/manifest.json",
    }
    active_path = release_root / "active.json"
    atomic_write(active_path, active, workspace.root / ".fluency/temporary")
    return active_path


def resolve_active_lyrics_asset(releases_directory: Path, request_path: str) -> Path | None:
    """Resolve stable app aliases into the exact active Lyrics catalog."""

    if request_path != "/config/artists.json" and not request_path.startswith("/Artists/"):
        return None
    release_root = releases_directory / "lyrics"
    try:
        active = _load_json(release_root / "active.json", dict)
        release_id = active["release_id"]
    except (LyricsReleaseError, KeyError):
        return None if request_path == "/config/artists.json" else release_root / ".missing-active-lyrics-asset"
    if active.get("manifest_version") != ACTIVE_LYRICS_VERSION or not isinstance(release_id, str) or SAFE_RELEASE_ID.fullmatch(release_id) is None:
        return release_root / ".invalid-active-lyrics-asset"
    release_directory = (release_root / release_id).resolve()
    if request_path == "/Artists/release-manifest.json":
        return release_directory / "manifest.json"
    if request_path == "/Artists/release-composition.json":
        return release_directory / "composition.json"
    relative = PurePosixPath(request_path.removeprefix("/"))
    candidate = (release_directory / "app").joinpath(*relative.parts).resolve()
    try:
        candidate.relative_to((release_directory / "app").resolve())
    except ValueError:
        return release_root / ".invalid-active-lyrics-asset"
    return candidate
