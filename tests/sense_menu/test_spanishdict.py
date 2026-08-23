import json
from pathlib import Path
import tempfile
import unittest

from fluency.core.hashing import file_content_id
from fluency.core.identity import create_card_record
from fluency.sense_menu.config import load_sense_menu_language_policy
from fluency.sense_menu.spanishdict import (
    ADAPTER_ID,
    SpanishDictMenuError,
    SpanishDictSenseMenuAdapter,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def sense(pos: str, translation: str, context: str = "") -> dict:
    return {
        "pos": pos,
        "translation": translation,
        "context": context,
        "source": "spanishdict",
    }


class SpanishDictSenseMenuTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.snapshot = Path(self.temporary.name) / "snapshot"
        self.snapshot.mkdir()
        surface_cache = {
            "está": {
                "query": "está",
                "entry_lang": "es",
                "dictionary_analyses": [
                    {"headword": "está", "senses": [sense("PHRASE", "he's")]}
                ],
                "possible_results": [
                    {"headword": "estar", "heuristic": "conjugation"}
                ],
            },
            "usted": {
                "query": "usted",
                "entry_lang": "es",
                "dictionary_analyses": [
                    {"headword": "usted", "senses": [sense("PRON", "you", "singular")]},
                    {"headword": "ustedes", "senses": [sense("PRON", "you", "plural")]},
                ],
                "possible_results": [],
            },
            "sr": {
                "query": "sr",
                "dictionary_analyses": [
                    {"headword": "Sr.", "senses": [sense("NOUN", "Mr.")]}
                ],
                "possible_results": [],
            },
        }
        headword_cache = {
            "estar": {
                "dictionary_analyses": [
                    {
                        "headword": "estar",
                        "senses": [
                            sense("VERB", "to be", "used to express a quality"),
                            sense("VERB", "to stay", "to remain"),
                        ],
                    }
                ]
            }
        }
        payloads = {
            "surface_cache.json": surface_cache,
            "headword_cache.json": headword_cache,
            "spanish_forms.json": {"estar": {}, "usted": {}, "ustedes": {}},
            "conjugation_reverse.json": {
                "está": [{"lemma": "estar"}],
            },
        }
        content_files = []
        for filename, payload in payloads.items():
            path = self.snapshot / filename
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            content_files.append(
                {
                    "path": filename,
                    "sha256": file_content_id(path).removeprefix("sha256:"),
                    "bytes": path.stat().st_size,
                }
            )
        (self.snapshot / "artifact.json").write_text(
            json.dumps(
                {
                    "schema_version": "spanishdict-snapshot/v1",
                    "artifact_kind": "dictionary_menu_source",
                    "language": "es",
                    "provider": "spanishdict",
                    "snapshot_id": "fixture-2026-08",
                    "content_files": content_files,
                }
            ),
            encoding="utf-8",
        )
        self.policy = load_sense_menu_language_policy(
            REPOSITORY_ROOT, policy_id="es-spanishdict-v1", language="es"
        )

    def tearDown(self):
        self.temporary.cleanup()

    def adapter(self) -> SpanishDictSenseMenuAdapter:
        return SpanishDictSenseMenuAdapter(
            self.snapshot,
            language_policy=self.policy,
        )

    def test_latest_morphology_rules_remove_phrase_and_plural_twins(self):
        cards = [
            {**create_card_record("es", "está").to_dict(), "rank": 1},
            {**create_card_record("es", "usted").to_dict(), "rank": 2},
        ]
        menu, report = self.adapter().build(cards, snapshot_id="fixture-2026-08")
        by_surface = {item["surface_form"]: item for item in menu["cards"]}
        self.assertEqual(
            {(item["headword"], item["part_of_speech"]) for item in by_surface["está"]["analyses"]},
            {("estar", "VERB")},
        )
        self.assertEqual(
            {item["headword"] for item in by_surface["usted"]["analyses"]},
            {"usted"},
        )
        self.assertEqual(
            report["quarantine_reasons"],
            {"plural_analysis_conflicts_with_exact_surface": 1},
        )

    def test_missing_abbreviation_is_an_explicit_no_menu_without_fallback(self):
        cards = [{**create_card_record("es", "sr").to_dict(), "rank": 1}]
        menu, report = self.adapter().build(cards, snapshot_id="fixture-2026-08")
        self.assertEqual(menu["source_adapter"], ADAPTER_ID)
        self.assertEqual(menu["cards"][0]["analyses"], [])
        self.assertEqual(report["cards_without_menu"], 1)
        self.assertEqual(report["fallbacks"], [])

    def test_legacy_leaf_ids_and_provider_metadata_survive_normalization(self):
        cards = [{**create_card_record("es", "está").to_dict(), "rank": 1}]
        menu, _ = self.adapter().build(cards, snapshot_id="fixture-2026-08")
        leaves = menu["cards"][0]["analyses"][0]["senses"]
        self.assertEqual([item["sense_id"] for item in leaves], ["913", "953"])
        self.assertEqual(leaves[0]["definition"], "used to express a quality")
        self.assertEqual(leaves[0]["provider_metadata"]["legacy_menu_sense_id"], "913")

    def test_complete_normalized_menu_fills_surfaces_absent_from_raw_cache(self):
        retained_path = self.snapshot / "normalized_menu.json"
        retained_path.write_text(
            json.dumps(
                {
                    "salvar": [
                        {
                            "headword": "salvar",
                            "senses": {
                                "kept7": {
                                    "pos": "VERB",
                                    "translation": "to save",
                                    "context": "to rescue",
                                }
                            },
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        manifest_path = self.snapshot / "artifact.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["content_files"].append(
            {
                "path": "normalized_menu.json",
                "sha256": file_content_id(retained_path).removeprefix("sha256:"),
                "bytes": retained_path.stat().st_size,
            }
        )
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        cards = [{**create_card_record("es", "salvar").to_dict(), "rank": 1}]
        menu, report = self.adapter().build(cards, snapshot_id="fixture-2026-08")
        analysis = menu["cards"][0]["analyses"][0]
        self.assertEqual(analysis["senses"][0]["sense_id"], "kept7")
        self.assertEqual(
            analysis["provider_metadata"]["spanishdict"]["resolution"],
            "retained_normalized_menu",
        )
        self.assertEqual(report["cards_ready"], 1)
        self.assertEqual(report["cards_without_menu"], 0)

    def test_snapshot_hash_change_is_rejected(self):
        (self.snapshot / "surface_cache.json").write_text("{}", encoding="utf-8")
        with self.assertRaises(SpanishDictMenuError):
            self.adapter()


if __name__ == "__main__":
    unittest.main()
