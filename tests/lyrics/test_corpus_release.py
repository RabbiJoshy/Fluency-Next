import json
from pathlib import Path
import tempfile
import unittest

from fluency.core.hashing import file_content_id
from fluency.core.workspace import Workspace
from fluency.lyrics.corpus_release import build_clean_lyrics_corpus_release


class LyricsCorpusReleaseTests(unittest.TestCase):
    def test_composes_clean_assignments_with_retained_media_without_activation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = Workspace.initialize(root / "workspace")
            assembly = workspace.root / "runs/es/lyrics-corpora/plan/methods/method/corpus_app_assembly"
            clean_app = assembly / "app"
            artist = clean_app / "Artists/es/artist"
            artist.mkdir(parents=True)
            (clean_app / "config").mkdir()
            app_id = "aaaaaaaa"
            index = [{"id": app_id, "sense_frequencies": [1.0]}]
            examples = {app_id: {"m": [[{"song": "1", "spanish": "La casa", "english": "The house"}]]}}
            master = {app_id: {"word": "casa", "senses": [{"translation": "house"}]}}
            songs = {"schemaVersion": 1, "songs": [{
                "id": "1", "title": "Song", "creditedArtist": "Artist",
                "cardIds": [app_id], "runId": "run-1",
            }]}
            for path, value in (
                (artist / "index.json", index), (artist / "examples.json", examples),
                (artist / "songs.json", songs),
            ):
                path.write_text(json.dumps(value), encoding="utf-8")
            (clean_app / "Artists/es/vocabulary_master.json").write_text(json.dumps(master), encoding="utf-8")
            catalog = {"artist": {
                "name": "Artist", "language": "es",
                "masterPath": "Artists/es/vocabulary_master.json",
                "indexPath": "Artists/es/artist/index.json",
                "examplesPath": "Artists/es/artist/examples.json",
                "songsPath": "Artists/es/artist/songs.json",
            }}
            (clean_app / "config/artists.json").write_text(json.dumps(catalog), encoding="utf-8")
            report = {
                "status": "complete", "language": "es", "method_profile_id": "method-v1",
                "plan_id": "plan-v1", "plan_content_id": "sha256:" + "1" * 64,
                "consolidation_report_content_id": "sha256:" + "2" * 64,
            }
            (assembly / "report.json").write_text(json.dumps(report), encoding="utf-8")
            outputs = {
                path.relative_to(assembly).as_posix(): file_content_id(path)
                for path in [assembly / "report.json", *[item for item in clean_app.rglob("*") if item.is_file()]]
            }
            (assembly / "manifest.json").write_text(json.dumps({
                "status": "complete", "outputs": outputs,
            }), encoding="utf-8")

            parity = workspace.root / "releases/lyrics/parity"
            parity_app = parity / "app"
            parity_artist = parity_app / "Artists/es/artist"
            parity_artist.mkdir(parents=True)
            (parity_app / "config").mkdir()
            (parity_app / "Artists/es/artist/Images").mkdir()
            parity_index = [{"id": app_id, "sense_frequencies": [0.5]}]
            parity_examples = {app_id: {"m": [[{"song": "1", "spanish": "Una casa", "english": "A house"}]]}}
            parity_master = {app_id: {"word": "casa", "senses": [{"translation": "home"}]}}
            parity_songs = {"schemaVersion": 1, "source": "artist", "songs": [{
                "id": "1", "title": "Song", "album": "Album", "cardIds": ["old"],
            }]}
            for path, value in (
                (parity_artist / "index.json", parity_index),
                (parity_artist / "examples.json", parity_examples),
                (parity_artist / "songs.json", parity_songs),
            ):
                path.write_text(json.dumps(value), encoding="utf-8")
            (parity_app / "Artists/es/vocabulary_master.json").write_text(json.dumps(parity_master), encoding="utf-8")
            (parity_artist / "albums.json").write_text(json.dumps({"Album": 1}), encoding="utf-8")
            (parity_artist / "Images/album.jpg").write_bytes(b"image")
            (parity_app / "Artists/spotify_tracks.json").write_text(json.dumps({"Artist": {"Song": "track"}}), encoding="utf-8")
            parity_catalog = {"artist": {
                "name": "Artist", "language": "spanish",
                "masterPath": "Artists/es/vocabulary_master.json",
                "indexPath": "Artists/es/artist/index.json",
                "examplesPath": "Artists/es/artist/examples.json",
                "songsPath": "Artists/es/artist/songs.json",
                "albumsDictionary": "Artists/es/artist/albums.json",
                "albumImageMap": {"Album": "Artists/es/artist/Images/album.jpg"},
                "colorTheme": {"primary": "#000"}, "releaseId": "parity",
            }}
            (parity_app / "config/artists.json").write_text(json.dumps(parity_catalog), encoding="utf-8")

            release = build_clean_lyrics_corpus_release(
                workspace, assembly_path=assembly, parity_release=parity,
                release_id="clean-v1",
            )
            output_catalog = json.loads((release / "app/config/artists.json").read_text())
            output_songs = json.loads((release / "app" / output_catalog["artist"]["songsPath"]).read_text())
            self.assertEqual(output_songs["songs"][0]["cardIds"], [app_id])
            self.assertEqual(output_songs["songs"][0]["album"], "Album")
            self.assertEqual(output_songs["songs"][0]["assignmentMethodProfileId"], "method-v1")
            self.assertTrue((release / "app/Artists/es/artist/Images/album.jpg").is_file())
            self.assertFalse((workspace.root / "releases/lyrics/active.json").exists())
            comparison = json.loads((release / "comparison.json").read_text())
            self.assertEqual(comparison["totals"]["shared_cards_with_changed_senses_or_frequencies"], 1)
            self.assertFalse(comparison["activation_changed"])


if __name__ == "__main__":
    unittest.main()
