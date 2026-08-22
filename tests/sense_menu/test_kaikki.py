import json
from pathlib import Path
import tempfile
import unittest

from fluency.core.identity import create_card_record
from fluency.sense_menu.kaikki import ADAPTER_ID, KaikkiSenseMenuAdapter


def form_sense(base, sense_id):
    return {
        "id": sense_id,
        "glosses": [f"inflection of {base}"],
        "tags": ["form-of", "present"],
        "form_of": [{"word": base}],
    }


class KaikkiSenseMenuTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.snapshot = Path(self.temporary.name) / "kaikki-french.jsonl"
        rows = [
            {
                "word": "être",
                "lang_code": "fr",
                "pos": "verb",
                "senses": [
                    {
                        "id": "en-etre-fr-verb-be",
                        "glosses": ["to be", "exist or have identity"],
                        "raw_glosses": ["to be"],
                        "tags": [],
                    }
                ],
            },
            {
                "word": "suivre",
                "lang_code": "fr",
                "pos": "verb",
                "senses": [
                    {
                        "id": "en-suivre-fr-verb-follow",
                        "glosses": ["to follow"],
                        "topics": ["movement"],
                    }
                ],
            },
            {
                "word": "est",
                "lang_code": "fr",
                "pos": "noun",
                "senses": [
                    {
                        "id": "en-est-fr-noun-east",
                        "glosses": ["east"],
                        "tags": ["masculine"],
                    },
                    form_sense("être", "en-est-fr-verb-form"),
                ],
            },
            {
                "word": "suis",
                "lang_code": "fr",
                "pos": "verb",
                "senses": [
                    form_sense("être", "en-suis-fr-etre-form"),
                    form_sense("suivre", "en-suis-fr-suivre-form"),
                ],
            },
            {
                "word": "suis",
                "lang_code": "es",
                "pos": "noun",
                "senses": [{"id": "wrong-language", "glosses": ["noise"]}],
            },
        ]
        with self.snapshot.open("w", encoding="utf-8") as stream:
            for row in rows:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")

    def tearDown(self):
        self.temporary.cleanup()

    def test_form_of_targets_become_explicit_headword_pos_tuples(self):
        cards = [
            {**create_card_record("fr", "suis").to_dict(), "rank": 1},
            {**create_card_record("fr", "est").to_dict(), "rank": 2},
        ]
        menu, report = KaikkiSenseMenuAdapter(self.snapshot).build(
            cards, snapshot_id="fixture-2026-08"
        )
        by_surface = {card["surface_form"]: card for card in menu["cards"]}
        suis = by_surface["suis"]["analyses"]
        self.assertEqual(
            {(item["headword"], item["part_of_speech"]) for item in suis},
            {("être", "verb"), ("suivre", "verb")},
        )
        self.assertEqual(
            {item["senses"][0]["translation"] for item in suis},
            {"to be", "to follow"},
        )
        self.assertTrue(
            all(item["provider_metadata"]["resolution"] == "structured_form_of" for item in suis)
        )
        self.assertEqual(report["fallbacks"], [])
        self.assertEqual(report["cards_without_menu"], 0)

    def test_direct_homograph_and_form_of_headword_both_survive(self):
        cards = [{**create_card_record("fr", "est").to_dict(), "rank": 1}]
        menu, _ = KaikkiSenseMenuAdapter(self.snapshot).build(
            cards, snapshot_id="fixture-2026-08"
        )
        analyses = menu["cards"][0]["analyses"]
        self.assertEqual(
            {(item["headword"], item["part_of_speech"]) for item in analyses},
            {("est", "noun"), ("être", "verb")},
        )
        translations = {
            sense["translation"]
            for analysis in analyses
            for sense in analysis["senses"]
        }
        self.assertEqual(translations, {"east", "to be"})
        self.assertNotIn("inflection of être", translations)

    def test_output_exposes_provider_ids_metadata_and_snapshot_hash(self):
        cards = [{**create_card_record("fr", "est").to_dict(), "rank": 1}]
        menu, _ = KaikkiSenseMenuAdapter(self.snapshot).build(
            cards, snapshot_id="fixture-2026-08"
        )
        self.assertEqual(menu["source_adapter"], ADAPTER_ID)
        self.assertTrue(menu["snapshot_content_id"].startswith("sha256:"))
        leaf = next(
            sense
            for analysis in menu["cards"][0]["analyses"]
            if analysis["headword"] == "est"
            for sense in analysis["senses"]
        )
        self.assertEqual(leaf["sense_id"], "en-est-fr-noun-east")
        self.assertEqual(leaf["source_reference"], "kaikki:en-est-fr-noun-east")
        self.assertEqual(leaf["provider_metadata"]["tags"], ["masculine"])


if __name__ == "__main__":
    unittest.main()
