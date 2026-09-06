"""The commonest words earn more examples than the long tail.

A flat per-card number either starves the top of the deck, where a learner
spends most of their time, or pays for depth nobody reads at rank 2,900.
"""

import unittest

from fluency.pipeline.budget import (
    BudgetError,
    display_example_tiers,
    display_examples_for_rank,
    display_examples_per_card,
    projected_display_examples,
)

TIERED = {"display_examples_per_card": [
    {"through_rank": 1000, "examples": 5},
    {"through_rank": 3000, "examples": 3},
]}
FLAT = {"display_examples_per_card": 3}


class TieredDisplayTests(unittest.TestCase):
    def test_the_boundary_rank_belongs_to_the_tier_that_names_it(self) -> None:
        self.assertEqual(display_examples_for_rank(TIERED, 1000), 5)
        self.assertEqual(display_examples_for_rank(TIERED, 1001), 3)

    def test_the_deck_total_is_the_sum_of_its_tiers(self) -> None:
        self.assertEqual(projected_display_examples(TIERED, 3000), 1000 * 5 + 2000 * 3)

    def test_a_short_run_never_pays_for_ranks_it_does_not_reach(self) -> None:
        self.assertEqual(projected_display_examples(TIERED, 400), 400 * 5)

    def test_the_ceiling_is_the_largest_tier(self) -> None:
        self.assertEqual(display_examples_per_card(TIERED), 5)

    def test_tiers_are_read_in_rank_order_however_they_are_written(self) -> None:
        shuffled = {"display_examples_per_card": [
            {"through_rank": 3000, "examples": 3},
            {"through_rank": 1000, "examples": 5},
        ]}
        self.assertEqual(display_example_tiers(shuffled), [(1000, 5), (3000, 3)])


class BackwardCompatibilityTests(unittest.TestCase):
    """Every profile written before tiers existed must keep its exact meaning."""

    def test_a_plain_integer_still_means_every_card(self) -> None:
        self.assertEqual(display_examples_for_rank(FLAT, 1), 3)
        self.assertEqual(display_examples_for_rank(FLAT, 999_999), 3)

    def test_a_plain_integer_totals_as_before(self) -> None:
        self.assertEqual(projected_display_examples(FLAT, 3000), 9000)

    def test_the_legacy_key_name_is_still_read(self) -> None:
        self.assertEqual(display_examples_for_rank({"examples_per_surface": 4}, 7), 4)


class MalformedTierTests(unittest.TestCase):
    def test_a_tier_without_a_rank_is_refused(self) -> None:
        with self.assertRaises(BudgetError):
            display_example_tiers({"display_examples_per_card": [{"examples": 5}]})

    def test_a_repeated_rank_is_refused(self) -> None:
        with self.assertRaises(BudgetError):
            display_example_tiers({"display_examples_per_card": [
                {"through_rank": 1000, "examples": 5},
                {"through_rank": 1000, "examples": 3},
            ]})


if __name__ == "__main__":
    unittest.main()
