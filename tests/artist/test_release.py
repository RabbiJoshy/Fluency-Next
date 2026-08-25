import json
from pathlib import Path
import tempfile
import unittest

from fluency.artist.release import (
    activate_lyrics_release,
    build_lyrics_catalog_release,
    resolve_active_lyrics_asset,
    validate_lyrics_release,
)
from fluency.core.workspace import Workspace


class LyricsReleaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.source = root / "source"
        artist = self.source / "Artists/spanish/Test Artist"
        artist.mkdir(parents=True)
        (self.source / "config").mkdir()
        (self.source / "Artists/spanish").mkdir(exist_ok=True)
        index = [{"id": "abc123", "word": "hola", "meanings": [], "sense_frequencies": [1.0]}]
        examples = {"abc123": {"m": [[{
            "spanish": "hola, amiga", "song": "song-1",
            "assignment_method": "gemini-quality", "prompt_id": "legacy-v7",
        }]]}}
        master = {"abc123": {"word": "hola", "lemma": "hola", "senses": [{
            "sense_id": "sense-1", "headword": "hola", "pos": "INTJ",
            "translation": "hello",
        }]}}
        master["unreachable"] = {"word": "adiós", "lemma": "adiós", "senses": []}
        songs = {"schemaVersion": 1, "source": "test", "songs": []}
        (artist / "index.json").write_text(json.dumps(index), encoding="utf-8")
        (artist / "examples.json").write_text(json.dumps(examples), encoding="utf-8")
        (artist / "songs.json").write_text(json.dumps(songs), encoding="utf-8")
        (self.source / "Artists/spanish/vocabulary_master.json").write_text(
            json.dumps(master), encoding="utf-8"
        )
        (self.source / "Artists/spotify_tracks.json").write_text("{}", encoding="utf-8")
        catalog = {
            "test-artist": {
                "name": "Test Artist",
                "language": "spanish",
                "masterPath": "Artists/spanish/vocabulary_master.json",
                "indexPath": "Artists/spanish/Test Artist/index.json",
                "examplesPath": "Artists/spanish/Test Artist/examples.json",
                "songsPath": "Artists/spanish/Test Artist/songs.json",
                "colorTheme": {"primary": "#000", "secondary": "#fff"},
            }
        }
        (self.source / "config/artists.json").write_text(json.dumps(catalog), encoding="utf-8")
        self.workspace = Workspace.initialize(root / "workspace")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_builds_valid_self_contained_catalog_and_active_aliases(self) -> None:
        release = build_lyrics_catalog_release(
            self.workspace,
            source_repository=self.source,
            release_id="lyrics-test-1",
            include_artists={"test-artist"},
        )
        manifest, composition = validate_lyrics_release(release)
        self.assertEqual(manifest["artist_count"], 1)
        self.assertEqual(
            manifest["assignment_status"],
            "forced_leaf_assignments_preserved_in_dual_view_contract",
        )
        self.assertEqual(
            manifest["supported_specificity_status"],
            "not_recorded_in_materialized_sources",
        )
        self.assertEqual(composition["fallback_policy"], "none")
        catalog = json.loads((release / "app/config/artists.json").read_text())
        self.assertEqual(catalog["test-artist"]["indexPath"], "Artists/es/test-artist/index.json")
        self.assertEqual(catalog["test-artist"]["spotifyPath"], "Artists/spotify_tracks.json")
        self.assertFalse(any("monolith" in item["path"] for item in manifest["files"]))
        packaged_master = json.loads(
            (release / "app/Artists/es/test-artist/vocabulary_master.json").read_text()
        )
        self.assertEqual(set(packaged_master), {"abc123"})
        self.assertEqual(
            catalog["test-artist"]["wsdEvidencePath"],
            "Artists/es/test-artist/wsd-evidence.json",
        )
        packaged_index = json.loads(
            (release / "app/Artists/es/test-artist/index.json").read_text()
        )
        distribution = packaged_index[0]["wsd_distribution"]
        self.assertEqual(distribution["forced_leaf_counts"], {"sense-1": 1})
        self.assertEqual(distribution["supported_unavailable_mass"], 1)
        evidence = json.loads(
            (release / "app/Artists/es/test-artist/wsd-evidence.json").read_text()
        )
        decision = evidence["cards"]["abc123"]["decisions"][0]
        self.assertEqual(decision["forced_selection"]["sense_id"], "sense-1")
        self.assertIsNone(decision["supported_selection"])
        self.assertEqual(decision["provenance"]["assignment_method"], "gemini-quality")

        activate_lyrics_release(self.workspace, "lyrics-test-1")
        resolved = resolve_active_lyrics_asset(
            self.workspace.root / "releases", "/config/artists.json"
        )
        self.assertEqual(resolved, release / "app/config/artists.json")
        self.assertEqual(
            resolve_active_lyrics_asset(
                self.workspace.root / "releases", "/Artists/es/test-artist/examples.json"
            ),
            release / "app/Artists/es/test-artist/examples.json",
        )

    def test_rejects_index_example_drift(self) -> None:
        path = self.source / "Artists/spanish/Test Artist/examples.json"
        path.write_text(json.dumps({"orphan": {"m": []}}), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "index/examples disagree"):
            build_lyrics_catalog_release(
                self.workspace,
                source_repository=self.source,
                release_id="lyrics-test-bad",
            )

    def test_rejects_unknown_selected_artist(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown requested artist sources"):
            build_lyrics_catalog_release(
                self.workspace,
                source_repository=self.source,
                release_id="lyrics-test-selected",
                include_artists={"not-in-catalog"},
            )
