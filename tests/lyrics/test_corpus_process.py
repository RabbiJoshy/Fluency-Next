import json
from pathlib import Path
import tempfile
import unittest

from fluency.core.artifacts import artifact_directory, store_artifact_bytes, verify_artifact
from fluency.core.workspace import Workspace
from fluency.lyrics.corpus import build_lyrics_corpus_plan, ingest_lyrics_corpus_plan
from fluency.lyrics.corpus_process import (
    LyricsCorpusProcessingError,
    build_lyrics_corpus_processing_profile,
    process_lyrics_corpus_plan,
)
from fluency.lyrics.process import process_lyrics_run


class LyricsCorpusProcessingTests(unittest.TestCase):
    def test_processes_exact_profile_once_and_resumes_after_full_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = Workspace.initialize(root / "workspace")
            repository = root / "legacy"
            repository.mkdir()
            (repository / "songs.json").write_text(json.dumps([{
                "id": 1,
                "title": "One",
                "artist": "A",
                "lyrics": "[Verso]\nUna línea",
            }]))
            config = root / "corpus.json"
            config.write_text(json.dumps({
                "plan_version": "lyrics-corpus-plan/v1",
                "language": "es",
                "cross_source_duplicate_policy": "preserve_artist_scoped_song_sources",
                "included_sources": [{
                    "artist_slug": "a",
                    "artist_name": "A",
                    "adapter": "legacy_genius_batch_directory/v1",
                    "relative_path": ".",
                    "file_pattern": "songs.json",
                }],
                "excluded_sources": [],
            }))
            plan = build_lyrics_corpus_plan(
                workspace,
                config_path=config,
                source_repository=repository,
                plan_id="fixture-process-v1",
            )
            ingest_lyrics_corpus_plan(workspace, plan_path=plan)

            def artifact(value, filename, schema, media_type="application/json"):
                data = value.encode("utf-8") if isinstance(value, str) else json.dumps(value).encode("utf-8")
                return store_artifact_bytes(
                    workspace,
                    data,
                    filename=filename,
                    media_type=media_type,
                    schema=schema,
                    created_by_stage="fixture/v1",
                ).artifact_id

            inputs = {
                "elision_mapping": artifact([], "elision-mapping.json", "spanish-elision-mapping/v1"),
                "multi_word_elisions": artifact({"entries": {}}, "multi-word-elisions.json", "spanish-multi-word-elisions/v1"),
                "known_forms": artifact({"una": "det", "línea": "noun"}, "spanish-known-forms.json", "spanish-known-forms/v1"),
                "frequency_snapshot": artifact("una 10\nlínea 10\n", "spanish-surface-frequency.txt", "spanish-surface-frequency/v1", "text/plain"),
                "lexeme_register": artifact({"línea": {"word": "línea", "lemma": "línea"}}, "spanish-lexeme-register.json", "spanish-lexeme-register/v1"),
                "routing_snapshot": artifact({
                    "schema_version": 2,
                    "exclude": {},
                    "classifier": {"normal_vocab": ["una", "línea"]},
                    "derivation_map": {},
                    "sense_discovery": [],
                    "clitic_merge": {},
                }, "word-routing.json", "legacy-word-routing/v2"),
            }
            direct_plan = build_lyrics_corpus_plan(
                workspace,
                config_path=config,
                source_repository=repository,
                plan_id="fixture-process-direct-v1",
            )
            ingest_lyrics_corpus_plan(workspace, plan_path=direct_plan)
            direct_manifest = json.loads(direct_plan.read_text())
            direct_run = direct_manifest["included_sources"][0]["songs"][0]["planned_run_id"]

            def payload(name):
                metadata = verify_artifact(workspace, inputs[name])
                return artifact_directory(workspace, inputs[name]) / metadata.filename

            direct_output = process_lyrics_run(
                workspace,
                run_id=direct_run,
                language="es",
                elision_mapping=payload("elision_mapping"),
                multi_word_elisions=payload("multi_word_elisions"),
                known_forms=payload("known_forms"),
                frequency_snapshot=payload("frequency_snapshot"),
                lexeme_register=payload("lexeme_register"),
                routing_snapshot=payload("routing_snapshot"),
            )
            self.assertEqual(json.loads((direct_output / "report.json").read_text())["occurrence_count"], 2)

            profile_source = root / "profile-source.json"
            profile_source.write_text(json.dumps({
                "profile_source_version": "lyrics-corpus-processing-profile-source/v1",
                "language": "es",
                "routing_mode": "snapshot",
                "shared_inputs": inputs,
                "artist_sources": [{"artist_slug": "a", "inputs": {}}],
            }))
            profile = build_lyrics_corpus_processing_profile(
                workspace,
                plan_path=plan,
                config_path=profile_source,
                source_repository=repository,
                profile_id="fixture-snapshot-v1",
            )
            events = []
            first = process_lyrics_corpus_plan(
                workspace, plan_path=plan, profile_path=profile, progress=events.append,
            )
            self.assertEqual(first["created_this_invocation"], 1)
            self.assertEqual(first["skipped_this_invocation"], 0)
            self.assertEqual(len(events), 1)
            second = process_lyrics_corpus_plan(
                workspace, plan_path=plan, profile_path=profile,
            )
            self.assertEqual(second["created_this_invocation"], 0)
            self.assertEqual(second["skipped_this_invocation"], 1)

            manifest = json.loads(plan.read_text())
            run_id = manifest["included_sources"][0]["songs"][0]["planned_run_id"]
            output = workspace.root / "runs/es/lyrics" / run_id / "stages/02_process/output"
            report = json.loads((output / "report.json").read_text())
            self.assertEqual(report["occurrence_count"], 2)
            self.assertEqual(report["routing_provenance"], "materialized_snapshot")

            (output / "routes.jsonl").write_text("corrupt\n")
            with self.assertRaisesRegex(LyricsCorpusProcessingError, "corrupt"):
                process_lyrics_corpus_plan(
                    workspace, plan_path=plan, profile_path=profile,
                )


if __name__ == "__main__":
    unittest.main()
