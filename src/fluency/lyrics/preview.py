"""Compose an exact inactive one-song Lyrics release for learner-app review."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import os
from pathlib import Path
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


class LyricsPreviewReleaseError(ValueError):
    pass


def _object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LyricsPreviewReleaseError(f"required JSON is unavailable or invalid: {path}") from error
    if not isinstance(value, dict):
        raise LyricsPreviewReleaseError(f"required JSON must contain an object: {path}")
    return value


def _copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def _files(app_root: Path) -> list[dict[str, Any]]:
    return [{
        "path": path.relative_to(app_root.parent).as_posix(),
        "content_id": file_content_id(path), "bytes": path.stat().st_size,
    } for path in sorted(item for item in app_root.rglob("*") if item.is_file())]


def build_clean_lyrics_preview_release(
    workspace: Workspace,
    *,
    run_id: str,
    language: str,
    artist_slug: str,
    release_id: str,
    parity_release: Path,
    song_source_id: str,
) -> Path:
    if SAFE_RELEASE_ID.fullmatch(release_id) is None:
        raise LyricsPreviewReleaseError("unsafe Lyrics preview release ID")
    release = workspace.root / "releases/lyrics" / release_id
    if release.exists():
        raise LyricsPreviewReleaseError("preview release already exists; choose a new release ID")
    run = workspace.root / "runs" / language / "lyrics" / run_id
    run_manifest = _object(run / "manifest.json")
    if run_manifest.get("run_id") != run_id or run_manifest.get("language") != language:
        raise LyricsPreviewReleaseError("Lyrics run identity does not match preview release")
    assembly_relative = run_manifest.get("stages", {}).get("app_assembly", {}).get("path")
    if not isinstance(assembly_relative, str):
        raise LyricsPreviewReleaseError("preview release requires a complete app assembly stage")
    assembly = run / assembly_relative
    assembly_manifest = _object(assembly / "manifest.json")
    parity_release = parity_release.expanduser().resolve()
    parity_catalog = _object(parity_release / "config/artists.json")
    parity_artist = parity_catalog.get(artist_slug)
    if not isinstance(parity_artist, dict):
        raise LyricsPreviewReleaseError("parity release does not contain the requested artist")
    songs = _object(parity_release / parity_artist["songsPath"])
    matching = [song for song in songs.get("songs", []) if str(song.get("id")) == song_source_id]
    if len(matching) != 1:
        raise LyricsPreviewReleaseError("parity song catalog does not contain one exact source song")
    spotify_source = _object(parity_release / "Artists/spotify_tracks.json")
    spotify_track = spotify_source.get(parity_artist["name"], {}).get(matching[0]["title"])

    created_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    temporary_root = workspace.root / ".fluency/temporary"
    temporary = Path(tempfile.mkdtemp(prefix="lyrics-preview-release-", dir=temporary_root))
    try:
        app = temporary / "app"
        artist_root = app / f"Artists/{language}/{artist_slug}"
        _copy(assembly / "index.json", artist_root / "index.json")
        _copy(assembly / "examples.json", artist_root / "examples.json")
        _copy(assembly / "vocabulary_master.json", app / f"Artists/{language}/vocabulary_master.json")
        clean_ids = {item["id"] for item in json.loads((assembly / "index.json").read_text(encoding="utf-8"))}
        song_record = dict(matching[0])
        song_record["cardIds"] = sorted(clean_ids)
        song_catalog = {
            "schemaVersion": 1, "source": artist_slug, "name": parity_artist["name"],
            "songCount": 1, "cardCount": len(clean_ids), "songLinkedCardCount": len(clean_ids),
            "songs": [song_record],
        }
        (artist_root / "songs.json").write_bytes(json_bytes(song_catalog))
        (app / "Artists/spotify_tracks.json").write_bytes(json_bytes({
            parity_artist["name"]: ({matching[0]["title"]: spotify_track} if spotify_track else {})
        }))
        catalog = {artist_slug: {
            "name": parity_artist["name"], "language": parity_artist["language"],
            "masterPath": f"Artists/{language}/vocabulary_master.json",
            "indexPath": f"Artists/{language}/{artist_slug}/index.json",
            "examplesPath": f"Artists/{language}/{artist_slug}/examples.json",
            "songsPath": f"Artists/{language}/{artist_slug}/songs.json",
            "spotifyPath": "Artists/spotify_tracks.json",
            "colorTheme": parity_artist.get("colorTheme", {}), "maxLevel": len(clean_ids),
            "releaseId": release_id, "releaseManifestPath": "Artists/release-manifest.json",
            "releaseCompositionPath": "Artists/release-composition.json",
        }}
        (app / "config").mkdir(parents=True)
        (app / "config/artists.json").write_bytes(json_bytes(catalog))

        stage_layers = {}
        for name, reference in run_manifest.get("stages", {}).items():
            if name not in {"source_ingest", "process", "lexical_menu", "wsd_prepare", "wsd_results", "consolidation", "app_assembly"}:
                continue
            stage_layers[name] = {
                "source_type": "immutable_run_stage", "source_id": run_id,
                "artifact_ids": {"manifest": reference["manifest_content_id"]}, "requires": {},
            }
        composition = {
            "composition_version": LYRICS_COMPOSITION_VERSION, "release_id": release_id,
            "mode": "lyrics", "created_at": created_at,
            "publication_status": "inactive_clean_preview", "conflict_policy": "error",
            "fallback_policy": "none", "layers": stage_layers,
            "artists": [{
                "slug": artist_slug, "name": parity_artist["name"], "language": language,
                "card_count": len(clean_ids), "example_card_count": len(clean_ids), "song_count": 1,
                "index_content_id": file_content_id(assembly / "index.json"),
                "examples_content_id": file_content_id(assembly / "examples.json"),
                "master_content_id": file_content_id(assembly / "vocabulary_master.json"),
                "source_id": run_id, "migration_status": "clean_pipeline_preview",
                "provenance": {
                    "run_id": run_id,
                    "assembly_manifest_content_id": file_content_id(assembly / "manifest.json"),
                    "parity_song_catalog_content_id": file_content_id(parity_release / parity_artist["songsPath"]),
                    "parity_release_id": parity_artist["releaseId"],
                },
            }],
            "omitted_layers": [
                {"layer": "albums", "reason": "optional in one-song audit"},
                {"layer": "artwork", "reason": "optional in one-song audit"},
            ],
        }
        (temporary / "composition.json").write_bytes(json_bytes(composition))
        files = _files(app)
        manifest = {
            "manifest_version": LYRICS_MANIFEST_VERSION, "release_id": release_id,
            "mode": "lyrics", "created_at": created_at,
            "publication_status": "inactive_clean_preview",
            "catalog_path": "app/config/artists.json",
            "catalog_content_id": file_content_id(app / "config/artists.json"),
            "composition_path": "composition.json",
            "composition_content_id": file_content_id(temporary / "composition.json"),
            "artist_count": 1, "languages": [language], "card_count": len(clean_ids),
            "assignment_status": "clean_occurrence_wsd_assignments",
            "files": files,
        }
        (temporary / "manifest.json").write_bytes(json_bytes(manifest))
        comparison = _object(assembly / "report.json").get("comparison", {})
        (temporary / "comparison.json").write_bytes(json_bytes({
            "report_version": "lyrics-preview-comparison/v1", "release_id": release_id,
            "run_id": run_id, "assembly_comparison": comparison,
            "file_count": len(files), "payload_bytes": sum(item["bytes"] for item in files),
            "missing_optional_assets": ["albums", "artwork"], "activation_changed": False,
        }))
        release.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temporary, release)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    validate_lyrics_release(release)
    return release
