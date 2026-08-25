import unittest

from fluency.core.hashing import content_id
from fluency.core.identity import create_card_record
from fluency.harvest.records import build_sentence_id
from fluency.wsd.contracts import (
    SelectedTuple,
    SelectionProjection,
    WSDAssignment,
)


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

    def test_unresolved_publication_retains_the_forced_exact_selection(self) -> None:
        record = WSDAssignment(
            card_id=self.card.card_id,
            surface_form="veux",
            sentence_id=self.sentence_id,
            status="assigned",
            sense_menu_content_id=content_id(b"menu"),
            menu_analysis_id="analysis_" + "a" * 32,
            selected_sense_id="sense-want",
            selected_tuple=SelectedTuple("vouloir", "verb"),
            decision_path=("gloss", "commit"),
            evidence={"commit": {"axis_confidences": {
                "leaf": None, "glosskey": None, "tuple": None,
            }}},
            confidence=None,
            model_revisions={"gloss": "fixture@1"},
            emitted_level="unresolved",
        )

        restored = WSDAssignment.from_dict(record.to_dict())
        self.assertEqual(restored.status, "assigned")
        self.assertEqual(restored.menu_analysis_id, "analysis_" + "a" * 32)
        self.assertEqual(restored.selected_sense_id, "sense-want")
        self.assertEqual(restored.selected_tuple, SelectedTuple("vouloir", "verb"))
        self.assertEqual(restored.supported_level, "unresolved")

    def test_selection_projection_round_trips_and_materializes_top_level(self) -> None:
        projection = SelectionProjection(
            menu_analysis_id="analysis_" + "a" * 32,
            selected_sense_id="sense-want",
            selected_tuple=SelectedTuple("vouloir", "verb"),
            source_kind="provider",
            selected_score=0.72,
            runner_up_score=0.70,
            raw_margin=0.02,
            rank=1,
            emitted_level="glosskey",
            raw_axis_margins={"leaf": 0.2, "glosskey": 0.4, "tuple": 0.8},
        )
        record = WSDAssignment(
            card_id=self.card.card_id,
            surface_form="veux",
            sentence_id=self.sentence_id,
            status="assigned",
            sense_menu_content_id=content_id(b"menu"),
            menu_analysis_id=projection.menu_analysis_id,
            selected_sense_id=projection.selected_sense_id,
            selected_tuple=projection.selected_tuple,
            decision_path=("gloss", "commit"),
            evidence={},
            confidence=None,
            model_revisions={"gloss": "fixture@1"},
            emitted_level=projection.emitted_level,
            selection_projections={"provider_only": projection},
            active_selection_projection="provider_only",
        )

        payload = record.to_dict()
        self.assertEqual(
            payload["menu_analysis_id"],
            payload["selection_projections"]["provider_only"]["menu_analysis_id"],
        )
        self.assertEqual(
            payload["selected_sense_id"],
            payload["selection_projections"]["provider_only"]["selected_sense_id"],
        )
        self.assertEqual(WSDAssignment.from_dict(payload), record)

        with self.assertRaisesRegex(ValueError, "top-level selection"):
            WSDAssignment(
                card_id=self.card.card_id,
                surface_form="veux",
                sentence_id=self.sentence_id,
                status="assigned",
                sense_menu_content_id=content_id(b"menu"),
                menu_analysis_id=projection.menu_analysis_id,
                selected_sense_id="different-sense",
                selected_tuple=projection.selected_tuple,
                decision_path=("gloss", "commit"),
                evidence={},
                confidence=None,
                model_revisions={"gloss": "fixture@1"},
                emitted_level=projection.emitted_level,
                selection_projections={"provider_only": projection},
                active_selection_projection="provider_only",
            )


if __name__ == "__main__":
    unittest.main()
