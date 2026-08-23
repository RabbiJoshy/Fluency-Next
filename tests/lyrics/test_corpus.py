import json
from pathlib import Path
import tempfile
import unittest

from fluency.core.workspace import Workspace
from fluency.lyrics.corpus import LyricsCorpusPlanError, build_lyrics_corpus_plan


def song(source_id: int, title: str) -> dict:
    return {"id": source_id, "title": title, "artist": "Artist", "lyrics": "Una línea"}


class LyricsCorpusPlanTests(unittest.TestCase):
    def test_pins_mixed_adapters_and_preserves_scoped_collisions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = Workspace.initialize(root / "workspace")
            repository = root / "legacy"
            batch = repository / "batch"
            files = repository / "songs"
            batch.mkdir(parents=True)
            files.mkdir(parents=True)
            (batch / "one.json").write_text(json.dumps([song(1, "One"), song(2, "Two")]))
            (files / "same.json").write_text(json.dumps([song(1, "Shared")]))
            config = root / "corpus.json"
            config.write_text(json.dumps({
                "plan_version": "lyrics-corpus-plan/v1", "language": "es",
                "cross_source_duplicate_policy": "preserve_artist_scoped_song_sources",
                "included_sources": [
                    {"artist_slug": "a", "artist_name": "A", "adapter": "legacy_genius_batch_directory/v1", "relative_path": "batch"},
                    {"artist_slug": "b", "artist_name": "B", "adapter": "legacy_genius_song_directory/v1", "relative_path": "songs"},
                ],
                "excluded_sources": [{"artist_slug": "c", "reason": "not selected"}],
            }))
            output = build_lyrics_corpus_plan(
                workspace, config_path=config, source_repository=repository, plan_id="fixture-v1",
            )
            manifest = json.loads(output.read_text())
            self.assertEqual(manifest["totals"]["songs"], 3)
            self.assertEqual(manifest["totals"]["source_files"], 2)
            self.assertEqual(manifest["totals"]["cross_source_collisions"], 1)
            self.assertEqual(manifest["executed_stages"], [])
            self.assertTrue(all(
                file["snapshot_content_id"].startswith("sha256:")
                for source in manifest["included_sources"] for file in source["files"]
            ))
            with self.assertRaisesRegex(LyricsCorpusPlanError, "already exists"):
                build_lyrics_corpus_plan(
                    workspace, config_path=config, source_repository=repository, plan_id="fixture-v1",
                )


if __name__ == "__main__":
    unittest.main()
