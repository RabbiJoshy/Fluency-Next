"""Compose one inactive clean corpus assembly with retained optional Artist media."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
from typing import Any

from fluency.artist.release import (
    LYRICS_COMPOSITION_VERSION,
    LYRICS_MANIFEST_VERSION,
    SAFE_RELEASE_ID,
    validate_lyrics_release,
)
from fluency.core.hashing import file_content_id
from fluency.core.workspace import Workspace
from fluency.release.io import json_bytes


COMPARISON_VERSION = "lyrics-clean-corpus-comparison/v1"


class LyricsCorpusReleaseError(ValueError):
    """Raised when clean data and retained media cannot form one exact release."""


def _object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LyricsCorpusReleaseError(f"{label} is unavailable or invalid: {path}") from error
    if not isinstance(value, dict):
        raise LyricsCorpusReleaseError(f"{label} must contain an object")
    return value


def _array(path: Path, label: str) -> list[Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LyricsCorpusReleaseError(f"{label} is unavailable or invalid: {path}") from error
    if not isinstance(value, list):
        raise LyricsCorpusReleaseError(f"{label} must contain an array")
    return value


def _relative_file(root: Path, value: Any, label: str) -> tuple[str, Path]:
    if not isinstance(value, str) or not value:
        raise LyricsCorpusReleaseError(f"{label} path is missing")
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise LyricsCorpusReleaseError(f"{label} path is unsafe: {value}")
    path = root.joinpath(*pure.parts).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as error:
        raise LyricsCorpusReleaseError(f"{label} path escapes its release") from error
    if not path.is_file():
        raise LyricsCorpusReleaseError(f"{label} asset is missing: {value}")
    return pure.as_posix(), path


def _copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def _copy_declared(root: Path, target_app: Path, value: Any, label: str) -> str:
    relative, source = _relative_file(root, value, label)
    _copy(source, target_app / relative)
    return relative


def _app_files(app: Path) -> list[dict[str, Any]]:
    return [{
        "path": path.relative_to(app.parent).as_posix(),
        "content_id": file_content_id(path), "bytes": path.stat().st_size,
    } for path in sorted(item for item in app.rglob("*") if item.is_file())]


def _example_keys(examples: dict[str, Any]) -> set[tuple[str, int, str, str, str]]:
    keys: set[tuple[str, int, str, str, str]] = set()
    for card_id, payload in examples.items():
        if not isinstance(payload, dict):
            continue
        for bucket_index, bucket in enumerate(payload.get("m", [])):
            if not isinstance(bucket, list):
                continue
            for example in bucket:
                if not isinstance(example, dict):
                    continue
                keys.add((
                    card_id, bucket_index, str(example.get("song", "")),
                    str(example.get("spanish", "")), str(example.get("english", "")),
                ))
    return keys


def _example_stats(examples: dict[str, Any]) -> dict[str, int]:
    total = missing_translation = 0
    for payload in examples.values():
        if not isinstance(payload, dict):
            continue
        for bucket in payload.get("m", []):
            if not isinstance(bucket, list):
                continue
            for example in bucket:
                if not isinstance(example, dict):
                    continue
                total += 1
                missing_translation += not bool(str(example.get("english", "")).strip())
    return {"selected": total, "missing_translation": missing_translation}


def _comparison(
    *, clean_app: Path, parity_app: Path, clean_catalog: dict[str, Any],
    parity_catalog: dict[str, Any], release_id: str, method_profile_id: str,
) -> dict[str, Any]:
    artists: dict[str, Any] = {}
    totals = {
        "cards_added": 0, "cards_removed": 0, "cards_shared": 0,
        "shared_cards_with_changed_senses_or_frequencies": 0,
        "examples_added": 0, "examples_removed": 0,
    }
    for slug, clean_config in clean_catalog.items():
        parity_config = parity_catalog[slug]
        clean_index = _array(clean_app / clean_config["indexPath"], "clean artist index")
        parity_index = _array(parity_app / parity_config["indexPath"], "parity artist index")
        clean_examples = _object(clean_app / clean_config["examplesPath"], "clean examples")
        parity_examples = _object(parity_app / parity_config["examplesPath"], "parity examples")
        clean_master = _object(clean_app / clean_config["masterPath"], "clean master")
        parity_master = _object(parity_app / parity_config["masterPath"], "parity master")
        clean_by_id = {item["id"]: item for item in clean_index}
        parity_by_id = {item["id"]: item for item in parity_index}
        clean_ids = set(clean_by_id)
        parity_ids = set(parity_by_id)
        shared = clean_ids & parity_ids
        changed = 0
        for card_id in shared:
            clean_signature = {
                "senses": clean_master.get(card_id, {}).get("senses", []),
                "frequencies": clean_by_id[card_id].get("sense_frequencies", []),
            }
            parity_signature = {
                "senses": parity_master.get(card_id, {}).get("senses", []),
                "frequencies": parity_by_id[card_id].get("sense_frequencies", []),
            }
            changed += clean_signature != parity_signature
        clean_example_keys = _example_keys(clean_examples)
        parity_example_keys = _example_keys(parity_examples)
        clean_example_stats = _example_stats(clean_examples)
        clean_songs = _object(clean_app / clean_config["songsPath"], "clean songs").get("songs", [])
        record = {
            "clean_card_count": len(clean_ids), "parity_card_count": len(parity_ids),
            "cards_added": len(clean_ids - parity_ids),
            "cards_removed": len(parity_ids - clean_ids),
            "cards_shared": len(shared),
            "shared_cards_with_changed_senses_or_frequencies": changed,
            "clean_selected_example_count": clean_example_stats["selected"],
            "clean_examples_missing_translation": clean_example_stats["missing_translation"],
            "parity_selected_example_count": len(parity_example_keys),
            "examples_added": len(clean_example_keys - parity_example_keys),
            "examples_removed": len(parity_example_keys - clean_example_keys),
            "clean_song_count": len(clean_songs),
            "clean_songs_without_study_cards": sum(
                not item.get("cardIds") for item in clean_songs if isinstance(item, dict)
            ),
            "optional_media": {
                field: "retained" if clean_config.get(field) else "absent"
                for field in ("albumsDictionary", "albumImageMap", "defaultAlbumArt", "pickerImage")
            },
        }
        artists[slug] = record
        for key in totals:
            totals[key] += record[key]
    clean_bytes = sum(path.stat().st_size for path in clean_app.rglob("*") if path.is_file())
    parity_bytes = sum(path.stat().st_size for path in parity_app.rglob("*") if path.is_file())
    return {
        "comparison_version": COMPARISON_VERSION, "release_id": release_id,
        "method_profile_id": method_profile_id,
        "baseline_release_id": parity_app.parent.name,
        "artists": artists, "totals": totals,
        "payload": {
            "clean_bytes": clean_bytes, "parity_bytes": parity_bytes,
            "delta_bytes": clean_bytes - parity_bytes,
        },
        "validation": {
            "index_example_mismatches": 0, "duplicate_card_ids": 0,
            "orphaned_declared_files": 0,
        },
        "activation_changed": False,
    }


def build_clean_lyrics_corpus_release(
    workspace: Workspace,
    *,
    assembly_path: Path,
    parity_release: Path,
    release_id: str,
) -> Path:
    """Build and validate an inactive release; never change active.json."""

    if SAFE_RELEASE_ID.fullmatch(release_id) is None:
        raise LyricsCorpusReleaseError("unsafe clean Lyrics release ID")
    assembly = assembly_path.expanduser().resolve()
    try:
        assembly.relative_to((workspace.root / "runs").resolve())
    except ValueError as error:
        raise LyricsCorpusReleaseError("clean corpus assembly must belong to this workspace") from error
    assembly_manifest = _object(assembly / "manifest.json", "corpus assembly manifest")
    assembly_report = _object(assembly / "report.json", "corpus assembly report")
    if assembly_manifest.get("status") != "complete" or assembly_report.get("status") != "complete":
        raise LyricsCorpusReleaseError("corpus assembly is incomplete")
    for relative, expected in assembly_manifest.get("outputs", {}).items():
        path = assembly / relative
        if not path.is_file() or file_content_id(path) != expected:
            raise LyricsCorpusReleaseError(f"corpus assembly output changed: {relative}")
    clean_source_app = assembly / "app"
    clean_source_catalog = _object(clean_source_app / "config/artists.json", "clean artist catalog")

    parity = parity_release.expanduser().resolve()
    parity_app = parity / "app" if (parity / "app/config/artists.json").is_file() else parity
    try:
        parity_app.relative_to((workspace.root / "releases/lyrics").resolve())
    except ValueError as error:
        raise LyricsCorpusReleaseError("parity release must belong to this workspace") from error
    parity_catalog = _object(parity_app / "config/artists.json", "parity artist catalog")
    if not clean_source_catalog or not set(clean_source_catalog).issubset(parity_catalog):
        raise LyricsCorpusReleaseError("parity release does not cover every clean artist")
    destination = workspace.root / "releases/lyrics" / release_id
    if destination.exists():
        raise LyricsCorpusReleaseError("clean Lyrics release already exists; choose a new release ID")

    temporary_root = workspace.root / ".fluency/temporary"
    temporary = Path(tempfile.mkdtemp(prefix="lyrics-clean-corpus-release-", dir=temporary_root))
    try:
        app = temporary / "app"
        language = assembly_report["language"]
        master_relative = f"Artists/{language}/vocabulary_master.json"
        _copy(clean_source_app / master_relative, app / master_relative)
        spotify_source = parity_app / "Artists/spotify_tracks.json"
        spotify = _object(spotify_source, "parity Spotify map") if spotify_source.is_file() else {}
        retained_spotify: dict[str, Any] = {}
        catalog: dict[str, Any] = {}
        artist_records: list[dict[str, Any]] = []
        for slug, clean_config in sorted(clean_source_catalog.items()):
            parity_config = parity_catalog[slug]
            root_relative = f"Artists/{language}/{slug}"
            index_relative = f"{root_relative}/index.json"
            examples_relative = f"{root_relative}/examples.json"
            songs_relative = f"{root_relative}/songs.json"
            _copy(clean_source_app / clean_config["indexPath"], app / index_relative)
            _copy(clean_source_app / clean_config["examplesPath"], app / examples_relative)
            clean_songs = _object(clean_source_app / clean_config["songsPath"], "clean song ledger")
            _parity_songs_relative, parity_songs_path = _relative_file(
                parity_app, parity_config.get("songsPath"), f"{slug} parity songs"
            )
            parity_songs = _object(parity_songs_path, "parity song catalog")
            parity_by_id = {
                str(item.get("id")): item for item in parity_songs.get("songs", []) if isinstance(item, dict)
            }
            if len(parity_by_id) != len(parity_songs.get("songs", [])):
                raise LyricsCorpusReleaseError(f"parity song catalog has duplicate or invalid IDs: {slug}")
            merged_songs = []
            for clean_song in clean_songs.get("songs", []):
                source_id = str(clean_song.get("id"))
                parity_song = parity_by_id.get(source_id)
                if parity_song is None:
                    raise LyricsCorpusReleaseError(f"clean song is absent from parity media catalog: {slug}/{source_id}")
                merged_songs.append({
                    **parity_song, "cardIds": clean_song["cardIds"],
                    "runId": clean_song["runId"],
                    "assignmentMethodProfileId": assembly_report["method_profile_id"],
                })
            song_catalog = {
                **{key: value for key, value in parity_songs.items() if key != "songs"},
                "songCount": len(merged_songs),
                "cardCount": len(_array(app / index_relative, "clean artist index")),
                "songLinkedCardCount": len({card for song in merged_songs for card in song["cardIds"]}),
                "songs": merged_songs,
            }
            (app / songs_relative).parent.mkdir(parents=True, exist_ok=True)
            (app / songs_relative).write_bytes(json_bytes(song_catalog))

            output = {
                "name": parity_config.get("name") or clean_config["name"],
                "language": parity_config["language"],
                "masterPath": master_relative, "indexPath": index_relative,
                "examplesPath": examples_relative, "songsPath": songs_relative,
                "colorTheme": parity_config.get("colorTheme") or {},
                "maxLevel": len(_array(app / index_relative, "clean artist index")),
                "releaseId": release_id,
                "releaseManifestPath": "Artists/release-manifest.json",
                "releaseCompositionPath": "Artists/release-composition.json",
            }
            for field in ("albumsDictionary", "defaultAlbumArt", "pickerImage"):
                if parity_config.get(field):
                    output[field] = _copy_declared(
                        parity_app, app, parity_config[field], f"{slug} {field}"
                    )
            image_map = parity_config.get("albumImageMap")
            if isinstance(image_map, dict):
                output["albumImageMap"] = {
                    str(key): _copy_declared(parity_app, app, value, f"{slug} album artwork")
                    for key, value in image_map.items()
                }
            artist_spotify = spotify.get(output["name"])
            if isinstance(artist_spotify, dict):
                selected_titles = {str(song.get("title")) for song in merged_songs}
                retained_spotify[output["name"]] = {
                    title: track for title, track in artist_spotify.items()
                    if title in selected_titles
                }
            catalog[slug] = output
            artist_records.append({
                "slug": slug, "name": output["name"], "language": language,
                "card_count": output["maxLevel"],
                "example_card_count": len(_object(app / examples_relative, "clean examples")),
                "song_count": len(merged_songs),
                "index_content_id": file_content_id(app / index_relative),
                "examples_content_id": file_content_id(app / examples_relative),
                "master_content_id": file_content_id(app / master_relative),
                "source_id": assembly_report["plan_id"],
                "migration_status": "clean_method_branch",
                "provenance": {
                    "method_profile_id": assembly_report["method_profile_id"],
                    "assembly_manifest_content_id": file_content_id(assembly / "manifest.json"),
                    "parity_catalog_content_id": file_content_id(parity_app / "config/artists.json"),
                },
            })
        if retained_spotify:
            spotify_relative = "Artists/spotify_tracks.json"
            (app / spotify_relative).parent.mkdir(parents=True, exist_ok=True)
            (app / spotify_relative).write_bytes(json_bytes(retained_spotify))
            for config in catalog.values():
                config["spotifyPath"] = spotify_relative
        (app / "config").mkdir(parents=True, exist_ok=True)
        (app / "config/artists.json").write_bytes(json_bytes(catalog))

        created_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        composition = {
            "composition_version": LYRICS_COMPOSITION_VERSION,
            "release_id": release_id, "mode": "lyrics", "created_at": created_at,
            "publication_status": "inactive_clean_corpus",
            "conflict_policy": "error", "fallback_policy": "none",
            "layers": {
                "clean_corpus_assembly": {
                    "source_type": "immutable_method_branch",
                    "source_id": assembly_report["method_profile_id"],
                    "artifact_ids": {
                        "assembly_manifest": file_content_id(assembly / "manifest.json"),
                        "assembly_report": file_content_id(assembly / "report.json"),
                    },
                    "requires": {
                        "plan": assembly_report["plan_content_id"],
                        "consolidation_report": assembly_report["consolidation_report_content_id"],
                    },
                },
                "retained_optional_media": {
                    "source_type": "exact_parity_release",
                    "source_id": parity_app.parent.name,
                    "artifact_ids": {"catalog": file_content_id(parity_app / "config/artists.json")},
                    "requires": {},
                },
            },
            "artists": artist_records, "omitted_layers": [],
        }
        (temporary / "composition.json").write_bytes(json_bytes(composition))
        files = _app_files(app)
        manifest = {
            "manifest_version": LYRICS_MANIFEST_VERSION, "release_id": release_id,
            "mode": "lyrics", "created_at": created_at,
            "publication_status": "inactive_clean_corpus",
            "catalog_path": "app/config/artists.json",
            "catalog_content_id": file_content_id(app / "config/artists.json"),
            "composition_path": "composition.json",
            "composition_content_id": file_content_id(temporary / "composition.json"),
            "artist_count": len(catalog), "languages": [language],
            "card_count": sum(item["card_count"] for item in artist_records),
            "assignment_status": f"clean_exact_method:{assembly_report['method_profile_id']}",
            "files": files,
        }
        (temporary / "manifest.json").write_bytes(json_bytes(manifest))
        comparison = _comparison(
            clean_app=app, parity_app=parity_app, clean_catalog=catalog,
            parity_catalog=parity_catalog, release_id=release_id,
            method_profile_id=assembly_report["method_profile_id"],
        )
        (temporary / "comparison.json").write_bytes(json_bytes(comparison))
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    validate_lyrics_release(destination)
    return destination
