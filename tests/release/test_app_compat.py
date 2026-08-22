import json
from pathlib import Path
import unittest

from fluency.release.app_compat import build_app_compatibility_assets
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


if __name__ == "__main__":
    unittest.main()
