import unittest

from fluency.wsd.projection import materialize_selection, publishes_exact_leaf


class WSDProjectionTests(unittest.TestCase):
    def assignment(self):
        return {
            "status": "assigned",
            "menu_analysis_id": "analysis_" + "a" * 32,
            "selected_sense_id": "provider",
            "selected_tuple": {"headword": "nuevo", "part_of_speech": "ADJ"},
            "emitted_level": "leaf",
            "active_selection_projection": "provider_only",
            "selection_projections": {
                "provider_only": {
                    "menu_analysis_id": "analysis_" + "a" * 32,
                    "selected_sense_id": "provider",
                    "selected_tuple": {"headword": "nuevo", "part_of_speech": "ADJ"},
                    "source_kind": "provider",
                    "emitted_level": "leaf",
                },
                "mwe_augmented": {
                    "menu_analysis_id": "analysis_" + "b" * 32,
                    "selected_sense_id": "mwe_again",
                    "selected_tuple": {"headword": "de nuevo", "part_of_speech": "PHRASE"},
                    "source_kind": "multiword",
                    "emitted_level": "glosskey",
                },
            },
            "evidence": {
                "selected_multiword": None,
                "multiword_candidates": [{
                    "menu_analysis_id": "analysis_" + "b" * 32,
                    "expression_id": "mwe_again",
                    "expression": "de nuevo",
                }],
            },
        }

    def test_candidate_universe_switch_never_reruns_or_guesses(self):
        original = self.assignment()
        projected = materialize_selection(original, "mwe_augmented")
        self.assertEqual(projected["selected_sense_id"], "mwe_again")
        self.assertEqual(projected["evidence"]["selected_multiword"], "de nuevo")
        self.assertEqual(original["selected_sense_id"], "provider")

    def test_supported_projection_only_publishes_supported_leaves(self):
        projected = materialize_selection(self.assignment(), "mwe_augmented")
        self.assertTrue(publishes_exact_leaf(projected, "forced_leaf"))
        self.assertFalse(
            publishes_exact_leaf(projected, "supported_specificity")
        )

    def test_augmented_view_falls_back_to_provider_when_no_expression_was_present(self):
        assignment = self.assignment()
        assignment["selection_projections"].pop("mwe_augmented")

        projected = materialize_selection(assignment, "mwe_augmented")

        self.assertEqual(projected["selected_sense_id"], "provider")
        self.assertEqual(projected["active_selection_projection"], "mwe_augmented")
        self.assertIn("mwe_augmented", projected["selection_projections"])
        self.assertEqual(
            projected["evidence"]["release_selection_projection"],
            "mwe_augmented",
        )

    def test_legacy_assignment_is_forced_only_when_support_was_not_recorded(self):
        assignment = self.assignment()
        assignment.pop("emitted_level")
        assignment.pop("selection_projections")

        self.assertTrue(publishes_exact_leaf(assignment, "forced_leaf"))
        self.assertFalse(publishes_exact_leaf(assignment, "supported_specificity"))


if __name__ == "__main__":
    unittest.main()
