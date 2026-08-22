from copy import deepcopy
import json
from pathlib import Path
import unittest

from fluency.release.pilot import build_pilot_deck, default_seed_path
from fluency.release.validation import ReleaseValidationError, validate_deck


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
ERROR_FIXTURES = REPOSITORY_ROOT / "tests" / "fixtures" / "release-errors" / "invalid-decks.json"


class ReleaseValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        seed = json.loads(default_seed_path().read_text(encoding="utf-8"))
        self.deck = build_pilot_deck(seed)

    def test_valid_pilot_deck_passes(self) -> None:
        validate_deck(self.deck)

    def test_study_structure_must_cover_each_card_exactly_once(self) -> None:
        deck = deepcopy(self.deck)
        deck["study_structure"]["levels"][0]["sets"][0]["card_ids"].pop()
        with self.assertRaisesRegex(ReleaseValidationError, "structure and deck"):
            validate_deck(deck)

    def test_release_contract_schemas_are_valid_json(self) -> None:
        schema_root = REPOSITORY_ROOT / "schemas"
        for filename in (
            "active-release.schema.json",
            "release-manifest.schema.json",
            "layer-selection.schema.json",
            "release-composition.schema.json",
            "release-catalog.schema.json",
            "speech-deck.schema.json",
            "study-structure.schema.json",
        ):
            with self.subTest(filename=filename):
                schema = json.loads((schema_root / filename).read_text(encoding="utf-8"))
                self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")

    def test_declared_invalid_decks_are_rejected(self) -> None:
        cases = json.loads(ERROR_FIXTURES.read_text(encoding="utf-8"))
        for case in cases:
            with self.subTest(case=case["name"]):
                deck = deepcopy(self.deck)
                mutation = case["mutation"]
                if mutation == "duplicate_card":
                    deck["cards"][1]["card_id"] = deck["cards"][0]["card_id"]
                    deck["cards"][1]["surface_key"] = deck["cards"][0]["surface_key"]
                    deck["cards"][1]["display_form"] = deck["cards"][0]["display_form"]
                elif mutation == "coverage_claim":
                    deck["cards"][0]["coverage"] = 0.5
                elif mutation == "wrong_card_id":
                    deck["cards"][0]["card_id"] = "card_fr_00000000000000000000000000000000"
                elif mutation == "wrong_example_sense":
                    deck["cards"][0]["examples"][0]["sense_id"] = deck["cards"][1]["meanings"][0]["sense_id"]
                else:
                    self.fail(f"unknown fixture mutation: {mutation}")
                with self.assertRaises(ReleaseValidationError):
                    validate_deck(deck)


if __name__ == "__main__":
    unittest.main()
