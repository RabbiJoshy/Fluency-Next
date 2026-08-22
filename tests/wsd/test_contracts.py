import unittest

from fluency.core.hashing import content_id
from fluency.core.identity import create_card_record
from fluency.harvest.records import build_sentence_id
from fluency.wsd.contracts import SelectedTuple, WSDAssignment


class WSDAssignmentContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.card = create_card_record("fr", "veux")
        self.sentence_id = build_sentence_id(
            adapter="fixture/v1",
            snapshot_content_id=content_id(b"snapshot"),
            source_record_id="1",
            target_text="Je veux partir.",
            translation_text="I want to leave.",
        )

    def test_assigned_record_carries_exact_menu_analysis(self) -> None:
        record = WSDAssignment(
            card_id=self.card.card_id,
            surface_form="veux",
            sentence_id=self.sentence_id,
            status="assigned",
            sense_menu_content_id=content_id(b"menu"),
            menu_analysis_id="analysis_" + "a" * 32,
            selected_sense_id="sense-want",
            selected_tuple=SelectedTuple("vouloir", "verb"),
            decision_path=("gloss", "calibration"),
            evidence={"calibration": {"confidence": 0.91}},
            confidence=0.91,
            model_revisions={"gloss": "fixture@1"},
        )
        self.assertEqual(record.to_dict()["menu_analysis_id"], "analysis_" + "a" * 32)

    def test_no_menu_cannot_smuggle_in_a_selected_sense(self) -> None:
        with self.assertRaises(ValueError):
            WSDAssignment(
                card_id=self.card.card_id,
                surface_form="veux",
                sentence_id=self.sentence_id,
                status="no_menu",
                sense_menu_content_id=None,
                menu_analysis_id=None,
                selected_sense_id="legacy-sense",
                selected_tuple=None,
                decision_path=(),
                evidence={},
                confidence=None,
                model_revisions={},
            )


if __name__ == "__main__":
    unittest.main()
