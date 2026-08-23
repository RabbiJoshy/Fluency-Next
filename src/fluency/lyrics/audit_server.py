"""Read-only, lazy access to archived Bad Bunny lineage in the local auditor."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from fluency.lyrics.audit import build_bundle


SONG_PATH = re.compile(r"^/__lyrics_audit__/songs/([0-9]+)\.json$")
BASELINE_RUN = "run_1b1b2c53fdea8d865e3dd2d8"
CANDIDATE_RUN = "run_9b10a162edde17313dc83ff5"


class LyricsAuditServerError(ValueError):
    """Raised when an archived audit source cannot be resolved exactly."""


class LyricsAuditResolver:
    """Merge the static showcase catalog with lazily built archived song traces."""

    def __init__(self, *, project_root: Path, workspace_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.workspace_root = workspace_root.resolve()
        self.static_root = self.project_root / "app/lyrics-audit/data"
        self.legacy_repository = self.project_root.parent / "Fluency"
        archives = sorted(
            self.workspace_root.parent.glob("Fluency-Evidence-Archive-*/workspace-evidence"),
            reverse=True,
        )
        self.archive_root = archives[0].resolve() if archives else None
        self._catalog: dict[str, Any] | None = None
        self._entries: dict[str, dict[str, Any]] = {}
        self._bundle_cache: dict[str, bytes] = {}

    def _active_release_app(self) -> Path:
        release_root = self.workspace_root / "releases/lyrics"
        active = json.loads((release_root / "active.json").read_text(encoding="utf-8"))
        release_id = active.get("release_id")
        if not isinstance(release_id, str) or not release_id:
            raise LyricsAuditServerError("active Lyrics release has no release ID")
        app = (release_root / release_id / "app").resolve()
        app.relative_to(release_root.resolve())
        return app

    def catalog_bytes(self) -> bytes:
        if self._catalog is None:
            static = json.loads((self.static_root / "catalog.json").read_text(encoding="utf-8"))
            by_id = {str(item["song_id"]): dict(item) for item in static["songs"]}
            try:
                release_app = self._active_release_app()
                artists = json.loads((release_app / "config/artists.json").read_text(encoding="utf-8"))
                bad_bunny = artists["bad-bunny"]
                songs = json.loads((release_app / bad_bunny["songsPath"]).read_text(encoding="utf-8"))["songs"]
                for song in songs:
                    song_id = str(song["id"])
                    by_id.setdefault(song_id, {
                        "song_id": song_id,
                        "title": song["title"],
                        "artist": "Bad Bunny",
                        "language": "es",
                        "bundle": f"/__lyrics_audit__/songs/{song_id}.json",
                        "coverage": "clean routing + SpanishDict menu · WSD prepared",
                    })
            except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
                # The three repository-owned showcases remain usable without a
                # workspace, archive, or active retained release.
                pass
            ordered = sorted(by_id.values(), key=lambda item: (item["title"].casefold(), item["song_id"]))
            self._catalog = {**static, "songs": ordered}
            self._entries = {item["song_id"]: item for item in ordered}
        return (json.dumps(self._catalog, ensure_ascii=False, separators=(",", ":")) + "\n").encode()

    def matches_song_path(self, request_path: str) -> bool:
        return SONG_PATH.fullmatch(request_path) is not None

    def song_bytes(self, request_path: str) -> bytes:
        match = SONG_PATH.fullmatch(request_path)
        if match is None:
            raise LyricsAuditServerError("invalid archived song path")
        song_id = match.group(1)
        self.catalog_bytes()
        entry = self._entries.get(song_id)
        if entry is None or not str(entry.get("bundle", "")).startswith("/__lyrics_audit__/"):
            raise LyricsAuditServerError("song is not a lazy archived audit entry")
        if song_id in self._bundle_cache:
            return self._bundle_cache[song_id]
        if self.archive_root is None:
            raise LyricsAuditServerError("no dated Fluency evidence archive was found")

        run = (
            self.archive_root / "runs/es/lyrics"
            / f"bad-bunny-{song_id}-es-parity-source-plan-20260823-v2"
        )
        source = run / "stages/01_source_ingest/output"
        process = run / "stages/02_process/output"
        lexical = run / "stages/03_lexical_menu/output"
        prepared = run / "stages/04_wsd_prepare/output"
        required = (source, process, lexical, prepared)
        if not all(path.is_dir() for path in required):
            raise LyricsAuditServerError("archived clean lineage is incomplete for this song")

        bundle = build_bundle(
            legacy_artist_root=self.legacy_repository / "Artists/spanish/Bad Bunny",
            release_root=self._active_release_app(),
            song_id=song_id,
            baseline_run=BASELINE_RUN,
            candidate_run=CANDIDATE_RUN,
            source_ingest=source,
            process_output=process,
            lexical_output=lexical,
            wsd_prepare_output=prepared,
        )
        payload = (json.dumps(bundle, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
        self._bundle_cache[song_id] = payload
        return payload
