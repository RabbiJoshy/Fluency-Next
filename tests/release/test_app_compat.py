import json
from pathlib import Path
import unittest

from fluency.release.app_compat import build_app_compatibility_assets, build_app_conjugations
from fluency.release.pilot import build_pilot_deck, default_seed_path


class AppCompatibilityTests(unittest.TestCase):
    def test_clean_deck_maps_to_existing_app_contract_without_lemmas(self) -> None:
        seed = json.loads(default_seed_path().read_text(encoding="utf-8"))
        deck = build_pilot_deck(seed)
        index, examples = build_app_compatibility_assets(deck)

        self.assertEqual(len(index), 25)
        self.assertEqual(len(examples), 25)
        self.assertNotIn("lemma", index[0])
        self.assertEqual(index[0]["surface_card_id"], deck["cards"][0]["card_id"])
        self.assertEqual(index[0]["meanings"][0]["sense_id"], deck["cards"][0]["meanings"][0]["sense_id"])
        self.assertEqual(len(examples[index[0]["id"]]["m"][0]), 3)

    def test_unassigned_examples_use_the_apps_existing_sense_cycle(self) -> None:
        seed = json.loads(default_seed_path().read_text(encoding="utf-8"))
        deck = build_pilot_deck(seed)
        card = deck["cards"][0]
        card["meanings"][0]["assignment_status"] = "unassigned"
        for example in card["examples"]:
            example["assignment_status"] = "unassigned"
            example["sense_id"] = None

        index, examples = build_app_compatibility_assets(deck)
        app_card = index[0]
        app_examples = examples[app_card["id"]]

        self.assertEqual(len(app_card["meanings"]), 1)
        self.assertTrue(app_card["meanings"][0]["unassigned"])
        self.assertEqual(
            app_card["meanings"][0]["allSenses"][0]["sense_id"],
            card["meanings"][0]["sense_id"],
        )
        self.assertEqual(len(app_examples["m"][0]), 3)
        self.assertNotIn("assignment_method", app_examples["m"][0][0])

    def test_meaning_provider_metadata_reaches_the_app_contract(self) -> None:
        seed = json.loads(default_seed_path().read_text(encoding="utf-8"))
        deck = build_pilot_deck(seed)
        deck["cards"][0]["meanings"][0]["metadata"] = {
            "source_adapter": "spanishdict-sense-menu/v1",
            "sense_provider_metadata": {"translation_status": "present"},
        }
        index, _ = build_app_compatibility_assets(deck)
        self.assertEqual(
            index[0]["meanings"][0]["metadata"]["source_adapter"],
            "spanishdict-sense-menu/v1",
        )

    def test_typed_conjugations_map_to_the_existing_optional_app_shape(self) -> None:
        result = build_app_conjugations({
            "layer_version": "conjugation-layer/v1",
            "records": [{
                "headword": "hablar",
                "translation": "to speak",
                "nonfinite": {"gerund": "hablando", "past_participle": "hablado"},
                "paradigms": [{
                    "mood": "Indicativo",
                    "tense": "Presente",
                    "forms": [
                        {"person": "1s", "form": "hablo"},
                        {"person": "2s", "form": "hablas"},
                        {"person": "3s", "form": "habla"},
                        {"person": "1p", "form": "hablamos"},
                        {"person": "2p", "form": "habláis"},
                        {"person": "3p", "form": "hablan"},
                    ],
                }],
            }],
        })
        self.assertEqual(result["hablar"]["tenses"]["Presente"], [
            "hablo", "hablas", "habla", "hablamos", "habláis", "hablan",
        ])
        self.assertEqual(result["hablar"]["gerund"], "hablando")


if __name__ == "__main__":
    unittest.main()
