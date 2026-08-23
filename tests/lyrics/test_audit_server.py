import json
from pathlib import Path
import tempfile
import unittest

from fluency.lyrics.audit_server import LyricsAuditResolver


class LyricsAuditResolverTests(unittest.TestCase):
    def test_catalog_merges_release_songs_without_replacing_showcases(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "Fluency-Next"
            static_root = project / "app/lyrics-audit/data"
            static_root.mkdir(parents=True)
            static = {
                "schema": "fluency.lyrics-audit-catalog/v1",
                "default_song_id": "1",
                "songs": [{
                    "song_id": "1", "title": "Showcase", "artist": "Bad Bunny",
                    "language": "es", "bundle": "showcase.json", "coverage": "complete WSD",
                }],
            }
            (static_root / "catalog.json").write_text(json.dumps(static), encoding="utf-8")

            workspace = root / "workspace"
            release = workspace / "releases/lyrics/retained/app"
            (release / "config").mkdir(parents=True)
            songs_path = release / "Artists/es/bad-bunny/songs.json"
            songs_path.parent.mkdir(parents=True)
            songs_path.write_text(json.dumps({"songs": [
                {"id": "1", "title": "Showcase"},
                {"id": "2", "title": "Another Song"},
            ]}), encoding="utf-8")
            (release / "config/artists.json").write_text(json.dumps({
                "bad-bunny": {"songsPath": "Artists/es/bad-bunny/songs.json"}
            }), encoding="utf-8")
            active = workspace / "releases/lyrics/active.json"
            active.parent.mkdir(parents=True, exist_ok=True)
            active.write_text(json.dumps({"release_id": "retained"}), encoding="utf-8")

            resolver = LyricsAuditResolver(project_root=project, workspace_root=workspace)
            catalog = json.loads(resolver.catalog_bytes())
            self.assertEqual(len(catalog["songs"]), 2)
            by_id = {song["song_id"]: song for song in catalog["songs"]}
            self.assertEqual(by_id["1"]["bundle"], "showcase.json")
            self.assertEqual(by_id["2"]["bundle"], "/__lyrics_audit__/songs/2.json")
            self.assertIn("WSD prepared", by_id["2"]["coverage"])


if __name__ == "__main__":
    unittest.main()
