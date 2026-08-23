import json
from pathlib import Path
import tempfile
import unittest

from fluency.core.hashing import file_content_id
from fluency.core.workspace import Workspace
from fluency.lyrics.assemble import assemble_lyrics_app_stage


class LyricsAppAssemblyTests(unittest.TestCase):
    def test_clean_card_renders_to_exact_split_contract_with_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Workspace.initialize(Path(directory) / "workspace")
            run_id = "assembly-fixture"
            run = workspace.root / "runs/es/lyrics" / run_id
            consolidation = run / "stages/06_consolidation_v2/output"
            wsd = run / "stages/05_wsd_results/output"
            consolidation.mkdir(parents=True)
            wsd.mkdir(parents=True)
            card_id = "card_es_" + "a" * 32
            sense_assignment_id = "sense_assignment_" + "b" * 32
            example_id = "lyrics_example_" + "c" * 32
            card = {
                "record_version": "lyrics-consolidated-card/v1", "card_id": card_id,
                "rank": 1, "language": "es", "display_form": "casa", "surface_key": "casa",
                "occurrence_ids": ["occurrence_a"],
                "sense_groups": [{
                    "sense_assignment_id": sense_assignment_id,
                    "menu_content_id": "sha256:" + "1" * 64,
                    "menu_analysis_id": "analysis_a", "source_sense_id": "sense_a",
                    "headword": "casa", "lemma": None, "part_of_speech": "NOUN",
                    "translation": "house", "definition": "a home", "source_reference": "fixture:casa",
                    "provider": {"source_adapter": "fixture-menu/v1"},
                    "example_ids": [example_id], "occurrence_ids": ["occurrence_a"],
                }],
            }
            example = {
                "example_id": example_id, "card_id": card_id,
                "sense_assignment_id": sense_assignment_id, "selected_for_study": True,
                "line": {"source_position": 0, "text": "La casa", "section": {"performers": ["Artist"]}},
                "occurrence": {"occurrence_id": "occurrence_a", "span": [3, 7]},
                "analysis_unit": {"analysis_unit_id": "unit_a", "operation": "preserve"},
                "artist": {"id": "artist", "name": "Artist"},
                "song": {"song_id": "song_a", "title": "Song"},
                "source": {"source_record_id": "123", "snapshot_content_id": "sha256:" + "2" * 64},
                "translation": None,
                "route": {"route_id": "route_a"},
                "menu": {
                    "lexical_candidate_id": "lexical_a", "menu_content_id": "sha256:" + "1" * 64,
                    "menu_analysis_id": "analysis_a", "sense_id": "sense_a",
                },
                "wsd": {
                    "method_id": "fixture-wsd/v1", "confidence": 0.8,
                    "request_id": "request_a", "result_id": "result_a", "decision_path": ["gloss"],
                },
            }
            result = {
                "result_id": "result_a", "confidence": 0.8,
                "evidence": {"calibration": {"legacy_band": "medium"}},
            }
            cards_path = consolidation / "cards.jsonl"
            examples_path = consolidation / "examples.jsonl"
            results_path = wsd / "results.jsonl"
            cards_path.write_text(json.dumps(card) + "\n")
            examples_path.write_text(json.dumps(example) + "\n")
            results_path.write_text(json.dumps(result) + "\n")
            (consolidation / "manifest.json").write_text(json.dumps({"outputs": {
                "cards.jsonl": file_content_id(cards_path), "examples.jsonl": file_content_id(examples_path),
            }}))
            (wsd / "manifest.json").write_text(json.dumps({"outputs": {
                "results.jsonl": file_content_id(results_path),
            }}))
            (run / "manifest.json").write_text(json.dumps({
                "run_id": run_id, "language": "es", "mode": "lyrics", "stages": {
                    "consolidation": {"path": "stages/06_consolidation_v2/output"},
                    "wsd_results": {"path": "stages/05_wsd_results/output"},
                },
            }))
            output = assemble_lyrics_app_stage(
                Path(__file__).resolve().parents[2], workspace,
                run_id=run_id, language="es", artist_slug="artist",
            )
            index = json.loads((output / "index.json").read_text())
            examples = json.loads((output / "examples.json").read_text())
            master = json.loads((output / "vocabulary_master.json").read_text())
            self.assertEqual(index[0]["id"], "aaaaaaaa")
            self.assertEqual(set(examples), {"aaaaaaaa"})
            self.assertEqual(set(master), {"aaaaaaaa"})
            rendered = examples["aaaaaaaa"]["m"][0][0]
            self.assertEqual(rendered["run_id"], run_id)
            self.assertEqual(rendered["wsd_result_id"], "result_a")
            self.assertEqual(rendered["band"], "medium")
            self.assertEqual(rendered["english"], "")


if __name__ == "__main__":
    unittest.main()
