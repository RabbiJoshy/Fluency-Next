import unittest

from fluency.release.study_structure import build_study_structure


class StudyStructureTests(unittest.TestCase):
    def test_levels_and_sets_cover_ordered_cards_once(self) -> None:
        cards = [
            {"card_id": f"card_fr_{index:032x}", "frequency": 1000 - index}
            for index in range(425)
        ]
        structure = build_study_structure(cards, frequency_of=lambda card: card["frequency"])
        ids = [
            card_id
            for level in structure["levels"]
            for study_set in level["sets"]
            for card_id in study_set["card_ids"]
        ]
        self.assertEqual(ids, [card["card_id"] for card in cards])
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(len(study_set["card_ids"]) <= 20 for level in structure["levels"] for study_set in level["sets"]))
        self.assertEqual(structure["levels"][0]["start_rank"], 1)
        self.assertEqual(structure["levels"][-1]["end_rank"], 425)


if __name__ == "__main__":
    unittest.main()
