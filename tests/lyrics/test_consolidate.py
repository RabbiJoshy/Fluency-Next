import json
from pathlib import Path
import tempfile
import unittest

from fluency.core.hashing import file_content_id
from fluency.core.workspace import Workspace
from fluency.lyrics.consolidate import consolidate_lyrics_run


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def write_jsonl(path: Path, values: list[dict]) -> None:
    path.write_text("".join(json.dumps(value) + "\n" for value in values), encoding="utf-8")


class LyricsConsolidationTests(unittest.TestCase):
    def test_complete_pool_becomes_cards_examples_and_lossless_dispositions(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Workspace.initialize(Path(directory) / "workspace")
            run_id = "consolidation-fixture"
            run = workspace.root / "runs/es/lyrics" / run_id
            stages = {
                "source": run / "stages/01_source_ingest/output",
                "process": run / "stages/02_process/output",
                "lexical": run / "stages/03_lexical_menu/output",
                "prepare": run / "stages/04_wsd_prepare/output",
                "wsd": run / "stages/05_wsd_results/output",
            }
            for stage in stages.values():
                stage.mkdir(parents=True)
            write_json(run / "manifest.json", {
                "manifest_version": "lyrics-run/v1", "run_id": run_id,
                "language": "es", "mode": "lyrics", "status": "running", "stages": {},
            })
            song = {
                "song_id": "song_fixture", "language": "es", "title": "Fixture",
                "artist": {"id": "artist", "name": "Artist"},
                "source": {"name": "fixture", "snapshot_content_id": "sha256:" + "1" * 64},
            }
            lines = [{
                "line_id": "line_fixture", "song_id": "song_fixture", "language": "es",
                "source_position": 0, "text": "Casa ruido", "section": None,
            }]
            occurrences = [
                {"occurrence_id": "occurrence_a", "line_id": "line_fixture", "surface": "Casa", "span": [0, 4], "ordinal": 0},
                {"occurrence_id": "occurrence_b", "line_id": "line_fixture", "surface": "ruido", "span": [5, 10], "ordinal": 1},
            ]
            units = [
                {"analysis_unit_id": "unit_a", "occurrence_id": "occurrence_a", "normalized_form": "casa", "operation": "preserve", "slot": 0},
                {"analysis_unit_id": "unit_b", "occurrence_id": "occurrence_b", "normalized_form": "ruido", "operation": "preserve", "slot": 0},
            ]
            routes = [
                {"route_id": "route_a", "analysis_unit_id": "unit_a", "bucket": "lexical", "method_id": "router/v1"},
                {"route_id": "route_b", "analysis_unit_id": "unit_b", "bucket": "exclude.noise", "method_id": "router/v1"},
            ]
            card_a = "card_es_" + "a" * 32
            card_b = "card_es_" + "b" * 32
            candidates = [
                {
                    "lexical_candidate_id": "lexical_a", "analysis_unit_id": "unit_a",
                    "occurrence_id": "occurrence_a", "surface_card_id": card_a,
                    "provider": {"source_adapter": "fixture/v1"},
                    "status": "ready", "lookup_card_id": "lookup_casa",
                    "menu_analysis_ids": ["analysis_a"],
                    "menu_analysis_count": 1, "menu_sense_count": 1,
                },
                {
                    "lexical_candidate_id": "lexical_b", "analysis_unit_id": "unit_b",
                    "occurrence_id": "occurrence_b", "surface_card_id": card_b,
                    "provider": {"source_adapter": "fixture/v1"}, "status": "ineligible",
                    "lookup_card_id": None, "menu_analysis_ids": [],
                    "menu_analysis_count": 0, "menu_sense_count": 0,
                },
            ]
            sense_menu = {"cards": [{
                "card_id": "lookup_casa",
                "analyses": [{
                    "menu_analysis_id": "analysis_a", "headword": "casa", "lemma": None,
                    "part_of_speech": "NOUN", "senses": [{
                        "sense_id": "sense_a", "translation": "house", "definition": "a home",
                        "source_reference": "fixture:casa:a",
                    }],
                }],
            }]}
            requests = [
                {
                    "request_id": "request_a", "target": {"kind": "analysis_unit", "id": "unit_a"},
                    "occurrence_id": "occurrence_a", "lexical_candidate_id": "lexical_a",
                    "context": {"text": "Casa ruido"},
                },
                {
                    "request_id": "request_b", "target": {"kind": "analysis_unit", "id": "unit_b"},
                    "occurrence_id": "occurrence_b", "lexical_candidate_id": "lexical_b",
                    "context": {"text": "Casa ruido"},
                },
            ]
            results = [
                {
                    "request_id": "request_a", "result_id": "result_a", "occurrence_id": "occurrence_a",
                    "surface_card_id": card_a, "status": "assigned", "menu_content_id": "sha256:" + "2" * 64,
                    "menu_analysis_id": "analysis_a", "selected_sense_id": "sense_a",
                    "confidence": 0.8, "decision_path": ["gloss"], "evidence": {},
                },
                {
                    "request_id": "request_b", "result_id": "result_b", "occurrence_id": "occurrence_b",
                    "surface_card_id": card_b, "status": "ineligible", "menu_content_id": None,
                    "menu_analysis_id": None, "selected_sense_id": None,
                    "confidence": None, "decision_path": [], "evidence": {"reason_codes": ["noise"]},
                },
            ]
            files = {
                "source": {"song.json": song, "lines.jsonl": lines, "alignments.jsonl": []},
                "process": {"occurrences.jsonl": occurrences, "analysis-units.jsonl": units, "routes.jsonl": routes},
                "lexical": {"lexical-candidates.jsonl": candidates, "sense-menu.json": sense_menu},
                "prepare": {"requests.jsonl": requests},
                "wsd": {"results.jsonl": results, "method.json": {"profile_id": "fixture", "source_method_id": "fixture/v1"}},
            }
            for stage_name, stage_files in files.items():
                output_ids = {}
                for name, value in stage_files.items():
                    path = stages[stage_name] / name
                    if name.endswith(".jsonl"):
                        write_jsonl(path, value)
                    else:
                        write_json(path, value)
                    output_ids[name] = file_content_id(path)
                write_json(stages[stage_name] / "manifest.json", {"outputs": output_ids})

            output = consolidate_lyrics_run(
                Path(__file__).resolve().parents[2], workspace,
                run_id=run_id, language="es", example_cap_per_sense=1,
            )
            report = json.loads((output / "report.json").read_text())
            cards = [json.loads(line) for line in (output / "cards.jsonl").read_text().splitlines()]
            examples = [json.loads(line) for line in (output / "examples.jsonl").read_text().splitlines()]
            dispositions = [json.loads(line) for line in (output / "dispositions.jsonl").read_text().splitlines()]
            self.assertEqual(report["study_card_count"], 1)
            self.assertEqual(report["non_study_disposition_count"], 1)
            self.assertEqual(len(cards), 1)
            self.assertEqual(len(examples), 1)
            self.assertIsNone(examples[0]["translation"])
            self.assertEqual(examples[0]["translations"], [])
            self.assertTrue(examples[0]["selected_for_study"])
            self.assertEqual({item["wsd_status"] for item in dispositions}, {"assigned", "ineligible"})
            self.assertEqual(sum(item["example_id"] is not None for item in dispositions), 1)


if __name__ == "__main__":
    unittest.main()
