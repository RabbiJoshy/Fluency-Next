"""Build and validate self-contained, immutable Lyrics catalog releases."""

from __future__ import annotations

from datetime import UTC, datetime
from copy import deepcopy
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
from typing import Any

from fluency.artist.wsd_bridge import (
    bridge_materialized_assignments,
    overlay_native_assignments,
    validate_artist_wsd_evidence,
)
from fluency.core.hashing import canonical_content_id, file_content_id
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


def _aligned_materialized_master(
    index_source: Path,
    index: list[dict[str, Any]],
    examples: dict[str, dict[str, Any]],
    source_master: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Return the exact artist-specific menu aligned with its flattened buckets."""

    monolith_by_id: dict[str, dict[str, Any]] = {}
    suffix = ".index.json"
    if index_source.name.endswith(suffix):
        monolith_path = index_source.with_name(index_source.name.removesuffix(suffix) + ".json")
        if monolith_path.is_file():
            monolith = _load_json(monolith_path, list)
            monolith_by_id = {
                row["id"]: row
                for row in monolith
                if isinstance(row, dict) and isinstance(row.get("id"), str)
            }

    aligned: dict[str, dict[str, Any]] = {}

    def example_key(example: dict[str, Any]) -> tuple[Any, ...]:
        return (
            example.get("song"),
            example.get("spanish", example.get("target")),
            example.get("timestamp_ms"),
        )

    def sense_payload(meaning: dict[str, Any]) -> dict[str, Any]:
        payload = {
            key: deepcopy(meaning[key])
            for key in (
                "pos", "translation", "sense_id", "source", "headword",
                "context", "detail", "definition",
            )
            if key in meaning
        }
        if not payload.get("sense_id"):
            identity = {
                key: payload.get(key)
                for key in ("pos", "translation", "headword", "context", "definition")
            }
            payload["sense_id"] = (
                "generated:retained-materialized:"
                + canonical_content_id(identity).removeprefix("sha256:")[:12]
            )
        return payload

    def retained_prefix_is_proven(
        candidate: list[dict[str, Any]],
        meanings: list[dict[str, Any]],
        buckets: list[list[dict[str, Any]]],
    ) -> bool:
        meaning_examples = [
            {example_key(example) for example in (meaning.get("examples") or [])}
            for meaning in meanings
        ]
        for position, bucket in enumerate(buckets):
            bucket_keys = {example_key(example) for example in bucket}
            if not bucket_keys:
                continue
            matches = [
                meaning
                for meaning, keys in zip(meanings, meaning_examples, strict=True)
                if bucket_keys <= keys
            ]
            if len(matches) != 1:
                return False
            retained_ids = {
                candidate[position].get("sense_id"),
                *(candidate[position].get("sense_id_aliases") or []),
            }
            if matches[0].get("sense_id") not in retained_ids:
                return False
        return True

    def evidence_aligned_senses(
        card_id: str,
        meanings: list[dict[str, Any]],
        buckets: list[list[dict[str, Any]]],
    ) -> list[dict[str, Any]] | None:
        meaning_examples = [
            {example_key(example) for example in (meaning.get("examples") or [])}
            for meaning in meanings
        ]
        result: list[dict[str, Any]] = []
        used: set[int] = set()
        for position, bucket in enumerate(buckets):
            bucket_keys = {example_key(example) for example in bucket}
            if not bucket_keys:
                result.append({
                    "pos": "X",
                    "translation": "",
                    "sense_id": f"unresolved:materialized-menu:{card_id}:{position}",
                    "source": "retained-materialized-unresolved",
                    "context": "historical empty menu slot; identity not recoverable",
                })
                continue
            matches = [
                index
                for index, keys in enumerate(meaning_examples)
                if index not in used and bucket_keys <= keys
            ]
            if len(matches) != 1:
                return None
            match = matches[0]
            used.add(match)
            result.append(sense_payload(meanings[match]))
        return result

    for card in index:
        card_id = card.get("id") if isinstance(card, dict) else None
        if not isinstance(card_id, str):
            raise LyricsReleaseError("artist index contains an invalid card while aligning its master")
        source_row = source_master.get(card_id)
        materialized = monolith_by_id.get(card_id)
        if not isinstance(source_row, dict) and not isinstance(materialized, dict):
            raise LyricsReleaseError(f"artist master is missing card {card_id}")
        row = deepcopy(source_row if isinstance(source_row, dict) else {})
        if isinstance(materialized, dict):
            for field in (
                "word", "lemma", "is_english", "is_noise", "is_interjection",
                "is_propernoun", "is_transparent_cognate", "display_form",
            ):
                if field in materialized:
                    row[field] = deepcopy(materialized[field])
        buckets = (examples.get(card_id) or {}).get("m") or []
        materialized_meanings = (
            materialized.get("meanings") if isinstance(materialized, dict) else None
        )
        source_senses = row.get("senses") or []
        if isinstance(materialized_meanings, list) and len(materialized_meanings) == len(buckets):
            row["senses"] = [sense_payload(meaning) for meaning in materialized_meanings]
        elif isinstance(source_senses, list) and len(source_senses) == len(buckets):
            row["senses"] = deepcopy(source_senses)
        elif (
            isinstance(source_senses, list)
            and len(source_senses) > len(buckets)
            and isinstance(materialized_meanings, list)
        ):
            retained = deepcopy(source_senses[:len(buckets)])
            if retained_prefix_is_proven(retained, materialized_meanings, buckets):
                row["senses"] = retained
        senses = row.get("senses") or []
        if len(senses) != len(buckets) and isinstance(materialized_meanings, list):
            evidence_aligned = evidence_aligned_senses(
                card_id, materialized_meanings, buckets
            )
            if evidence_aligned is not None:
                row["senses"] = evidence_aligned
        senses = row.get("senses") or []
        if not isinstance(senses, list) or len(senses) != len(buckets):
            raise LyricsReleaseError(
                f"artist-specific sense menu is not aligned with examples for {card_id}"
            )
        for position, sense in enumerate(senses):
            if not isinstance(sense, dict):
                raise LyricsReleaseError(f"artist-specific sense is invalid for {card_id}")
            if not sense.get("sense_id"):
                identity = {
                    "card_id": card_id,
                    "position": position,
                    "pos": sense.get("pos"),
                    "translation": sense.get("translation"),
                    "context": sense.get("context", sense.get("definition")),
                }
                sense["sense_id"] = (
                    "generated:retained-materialized:"
                    + canonical_content_id(identity).removeprefix("sha256:")[:12]
                )
        aligned[card_id] = row
    return aligned


def _write_artist_master(
    master: dict[str, dict[str, Any]],
    app_root: Path,
    relative: str,
    copied: dict[str, Path],
) -> tuple[str, Path]:
    pure = PurePosixPath(relative)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise LyricsReleaseError(f"unsafe release asset path: {relative}")
    normalized = pure.as_posix()
    target = app_root.joinpath(*pure.parts)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(json_bytes(master))
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
    wsd_assignments_path: Path | None = None,
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
    examples_path = _copy_file(examples_source, app_root, f"{artist_base}/examples.json", copied)

    master_value = source.get("masterPath") or f"Artists/{language_name}/vocabulary_master.json"
    master_source = _source_path(source_root, master_value)
    index = _load_json(index_source, list)
    examples = _load_json(examples_source, dict)
    source_master = _load_json(master_source, dict)
    master = _aligned_materialized_master(
        index_source, index, examples, source_master
    )
    master_path, packaged_master = _write_artist_master(
        master, app_root, f"{artist_base}/vocabulary_master.json", copied
    )

    bridged_index, wsd_evidence = bridge_materialized_assignments(
        index, examples, master, artist_slug=slug
    )
    if wsd_assignments_path is not None:
        with wsd_assignments_path.open(encoding="utf-8") as assignment_file:
            records = (json.loads(line) for line in assignment_file if line.strip())
            bridged_index, wsd_evidence = overlay_native_assignments(
                bridged_index, wsd_evidence, master, records
            )
    index_relative = f"{artist_base}/index.json"
    index_target = app_root / index_relative
    index_target.parent.mkdir(parents=True, exist_ok=True)
    index_target.write_bytes(json_bytes(bridged_index))
    copied[index_relative] = index_target
    index_path = index_relative

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
    wsd_evidence_path = None
    if wsd_evidence is not None:
        wsd_evidence_path = f"{artist_base}/wsd-evidence.json"
        wsd_evidence_target = app_root / wsd_evidence_path
        wsd_evidence_target.write_bytes(json_bytes(wsd_evidence))
        copied[wsd_evidence_path] = wsd_evidence_target
        output["wsdEvidencePath"] = wsd_evidence_path
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
        "index_content_id": file_content_id(index_target),
        "examples_content_id": file_content_id(examples_source),
        "master_content_id": file_content_id(packaged_master),
        "source_master_content_id": file_content_id(master_source),
        "source_id": layer_source_id,
        "provenance": provenance,
        "migration_status": "retained_materialized_output_for_product_parity",
    }
    if wsd_evidence_path is not None:
        record["wsd_evidence_content_id"] = file_content_id(app_root / wsd_evidence_path)
        record["assignment_bridge_status"] = (
            "native_v7_forced_and_supported_available"
            if wsd_assignments_path is not None
            else "forced_leaf_preserved_supported_specificity_not_recorded"
        )
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
    wsd_assignment_overrides: dict[str, Path] | None = None,
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
        for slug, source in sorted(source_config.items()):
            if not isinstance(source, dict):
                raise LyricsReleaseError(f"artist config is not an object: {slug}")
            app_config, record = _artist_config(
                source_root, app_root, copied,
                slug=slug, source=source, release_id=release_id,
                wsd_assignments_path=(wsd_assignment_overrides or {}).get(slug),
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
                    **(
                        {"wsd_evidence": record["wsd_evidence_content_id"]}
                        if record.get("wsd_evidence_content_id")
                        else {}
                    ),
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
        has_native_v7 = any(
            record.get("assignment_bridge_status") == "native_v7_forced_and_supported_available"
            for record in artist_records
        )
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
            "assignment_status": (
                "native_v7_and_retained_forced_leaf_assignments"
                if has_native_v7 else "forced_leaf_assignments_preserved_in_dual_view_contract"
            ),
            "supported_specificity_status": (
                "available_for_native_v7_artists"
                if has_native_v7 else "not_recorded_in_materialized_sources"
            ),
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
        for field in ("indexPath", "examplesPath", "masterPath", "wsdEvidencePath", "songsPath", "spotifyPath", "albumsDictionary", "defaultAlbumArt", "pickerImage"):
            value = config.get(field)
            if value and f"app/{value}" not in declared:
                raise LyricsReleaseError(f"Lyrics artist {slug} references an undeclared {field}")
        for value in (config.get("albumImageMap") or {}).values():
            if f"app/{value}" not in declared:
                raise LyricsReleaseError(f"Lyrics artist {slug} references undeclared artwork")
        index_path = release_directory / "app" / config["indexPath"]
        examples_path = release_directory / "app" / config["examplesPath"]
        _validate_index_examples(index_path, examples_path)
        if config.get("wsdEvidencePath"):
            evidence = _load_json(
                release_directory / "app" / config["wsdEvidencePath"], dict
            )
            validate_artist_wsd_evidence(evidence)
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
