import json
from pathlib import Path
import tempfile
import unittest

from fluency.core.workspace import Workspace
from fluency.lyrics.corpus import (
    LyricsCorpusPlanError,
    build_lyrics_corpus_plan,
    ingest_lyrics_corpus_plan,
)


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

    def test_ingests_and_resumes_only_exact_completed_song_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = Workspace.initialize(root / "workspace")
            repository = root / "legacy"
            batch = repository / "batch"
            translations = repository / "translations.json"
            batch.mkdir(parents=True)
            (batch / "one.json").write_text(json.dumps([
                {**song(1, "One"), "lyrics": "[Verso]\nUna línea"},
                {**song(2, "Two"), "lyrics": "[Verso]\nOtra línea"},
            ]))
            translations.write_text(json.dumps({
                "songs": {"1": {"lines": [{
                    "spanish": "Una línea", "english": "One line", "source": "fixture",
                }]}}
            }))
            config = root / "corpus.json"
            config.write_text(json.dumps({
                "plan_version": "lyrics-corpus-plan/v1", "language": "es",
                "cross_source_duplicate_policy": "preserve_artist_scoped_song_sources",
                "included_sources": [{
                    "artist_slug": "a", "artist_name": "A",
                    "adapter": "legacy_genius_batch_directory/v1",
                    "relative_path": "batch",
                    "translation_relative_path": "translations.json",
                }],
                "excluded_sources": [],
            }))
            plan = build_lyrics_corpus_plan(
                workspace, config_path=config, source_repository=repository, plan_id="fixture-v2",
            )
            events = []
            first = ingest_lyrics_corpus_plan(workspace, plan_path=plan, progress=events.append)
            self.assertEqual(first["created_this_invocation"], 2)
            self.assertEqual(first["skipped_this_invocation"], 0)
            self.assertEqual(len(events), 2)
            manifest = json.loads(plan.read_text())
            first_run = manifest["included_sources"][0]["songs"][0]["planned_run_id"]
            report_path = (
                workspace.root / "runs/es/lyrics" / first_run
                / "stages/01_source_ingest/output/report.json"
            )
            report = json.loads(report_path.read_text())
            self.assertEqual(report["alignment_count"], 1)
            self.assertTrue(report["translation_snapshot_content_id"].startswith("sha256:"))

            second = ingest_lyrics_corpus_plan(workspace, plan_path=plan)
            self.assertEqual(second["created_this_invocation"], 0)
            self.assertEqual(second["skipped_this_invocation"], 2)

            report["source_record_id"] = "wrong"
            report_path.write_text(json.dumps(report))
            with self.assertRaisesRegex(LyricsCorpusPlanError, "conflicts"):
                ingest_lyrics_corpus_plan(workspace, plan_path=plan)


if __name__ == "__main__":
    unittest.main()
