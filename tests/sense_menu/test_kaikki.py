import json
from pathlib import Path
import tempfile
import unittest

from fluency.core.identity import create_card_record
from fluency.sense_menu.config import load_sense_menu_language_policy
from fluency.sense_menu.kaikki import ADAPTER_ID, KaikkiSenseMenuAdapter


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


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
        self.policy = load_sense_menu_language_policy(
            REPOSITORY_ROOT, policy_id="fr-v1", language="fr"
        )
        rows = [
            {
                "word": "être",
                "lang_code": "fr",
                "pos": "noun",
                "senses": [{"id": "en-etre-fr-noun-being", "glosses": ["a being"]}],
            },
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
                        "topics": ["movement", "transport"],
                        "tags": ["masculine", "slang", "transitive"],
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
                    }
                ],
            },
            {
                "word": "est",
                "lang_code": "fr",
                "pos": "verb",
                "senses": [form_sense("être", "en-est-fr-verb-form")],
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
            {
                "word": "de",
                "lang_code": "fr",
                "pos": "prep",
                "senses": [{"id": "en-de-fr-prep-of", "glosses": ["of"]}],
            },
            {
                "word": "de",
                "lang_code": "fr",
                "pos": "noun",
                "senses": [
                    {
                        "id": "en-de-fr-abbreviation-dame",
                        "glosses": ["abbreviation of dame"],
                        "tags": ["abbreviation", "alt-of"],
                        "alt_of": [{"word": "dame"}],
                    }
                ],
            },
            {
                "word": "dame",
                "lang_code": "fr",
                "pos": "noun",
                "senses": [{"id": "en-dame-fr-noun-lady", "glosses": ["lady"]}],
            },
            {
                "word": "cette",
                "lang_code": "fr",
                "pos": "det",
                "senses": [{"id": "en-cette-fr-det-this", "glosses": ["this"]}],
            },
            {
                "word": "Cette",
                "lang_code": "fr",
                "pos": "name",
                "senses": [
                    {
                        "id": "en-cette-fr-name-sete",
                        "glosses": ["former spelling of Sète"],
                        "tags": ["alt-of"],
                        "alt_of": [{"word": "Sète"}],
                    }
                ],
            },
            {
                "word": "Sète",
                "lang_code": "fr",
                "pos": "name",
                "senses": [{"id": "en-sete-fr-name-city", "glosses": ["a city in France"]}],
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
        menu, report = KaikkiSenseMenuAdapter(
            self.snapshot, language_policy=self.policy
        ).build(
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
        menu, _ = KaikkiSenseMenuAdapter(
            self.snapshot, language_policy=self.policy
        ).build(
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
        menu, _ = KaikkiSenseMenuAdapter(
            self.snapshot, language_policy=self.policy
        ).build(
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

    def test_topics_and_semantic_tags_become_normalized_specialist_features(self):
        cards = [{**create_card_record("fr", "suis").to_dict(), "rank": 1}]
        menu, _ = KaikkiSenseMenuAdapter(
            self.snapshot, language_policy=self.policy
        ).build(cards, snapshot_id="fixture-2026-08")
        leaf = next(
            sense
            for analysis in menu["cards"][0]["analyses"]
            if analysis["headword"] == "suivre"
            for sense in analysis["senses"]
        )
        features = {
            (item["family"], item["kind"], item["value"])
            for item in leaf["specialist_features"]
        }
        self.assertIn(("domain", "topic", "movement"), features)
        self.assertIn(("domain", "topic", "transport"), features)
        self.assertIn(("register", "usage_tag", "slang"), features)
        self.assertIn(("construction", "grammar_tag", "transitive"), features)
        self.assertFalse(any(value == "masculine" for _, _, value in features))

    def test_abbreviation_redirect_does_not_expand_an_unrelated_headword(self):
        cards = [{**create_card_record("fr", "de").to_dict(), "rank": 1}]
        menu, _ = KaikkiSenseMenuAdapter(
            self.snapshot, language_policy=self.policy
        ).build(cards, snapshot_id="fixture-2026-08")
        analyses = menu["cards"][0]["analyses"]
        self.assertEqual(
            {(item["headword"], item["part_of_speech"]) for item in analyses},
            {("de", "prep")},
        )

    def test_case_distinct_redirect_does_not_expand_a_proper_name(self):
        cards = [{**create_card_record("fr", "cette").to_dict(), "rank": 1}]
        menu, _ = KaikkiSenseMenuAdapter(
            self.snapshot, language_policy=self.policy
        ).build(cards, snapshot_id="fixture-2026-08")
        analyses = menu["cards"][0]["analyses"]
        self.assertEqual(
            {(item["headword"], item["part_of_speech"]) for item in analyses},
            {("cette", "det")},
        )


if __name__ == "__main__":
    unittest.main()
