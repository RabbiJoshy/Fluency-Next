"""A flat harvest budget spends the same on every card; the cards differ.

A rank-2,900 card shows 3 examples and sends 10 occurrences to WSD, so 50 of
its 60 candidates are never used. Those rare cards are also the last to fill,
so a flat budget is what forces a deep corpus scan.
"""

import unittest

from fluency.pipeline.budget import (
    BudgetError,
    wsd_budget_for_rank,
    wsd_budget_per_card,
    wsd_budget_tiers,
)

TIERED = {"wsd_budget_per_card": [
    {"through_rank": 1000, "budget": 60},
    {"through_rank": 2000, "budget": 30},
    {"through_rank": 3000, "budget": 20},
]}
FLAT = {"wsd_budget_per_card": 60}


class TaperedBudgetTests(unittest.TestCase):
    def test_the_boundary_rank_belongs_to_the_tier_that_names_it(self) -> None:
        self.assertEqual(wsd_budget_for_rank(TIERED, 1000), 60)
        self.assertEqual(wsd_budget_for_rank(TIERED, 1001), 30)
        self.assertEqual(wsd_budget_for_rank(TIERED, 2001), 20)

    def test_a_rank_past_every_tier_keeps_the_last(self) -> None:
        self.assertEqual(wsd_budget_for_rank(TIERED, 99_999), 20)

    def test_the_ceiling_is_the_largest_tier(self) -> None:
        self.assertEqual(wsd_budget_per_card(TIERED), 60)

    def test_tiers_are_read_in_rank_order_however_written(self) -> None:
        shuffled = {"wsd_budget_per_card": [
            {"through_rank": 3000, "budget": 20},
            {"through_rank": 1000, "budget": 60},
        ]}
        self.assertEqual(wsd_budget_tiers(shuffled), [(1000, 60), (3000, 20)])


class BackwardCompatibilityTests(unittest.TestCase):
    def test_a_plain_integer_still_means_every_card(self) -> None:
        self.assertEqual(wsd_budget_for_rank(FLAT, 1), 60)
        self.assertEqual(wsd_budget_for_rank(FLAT, 2900), 60)

    def test_the_legacy_key_name_is_still_read(self) -> None:
        self.assertEqual(wsd_budget_for_rank({"candidate_cap_per_surface": 40}, 7), 40)


class MalformedTierTests(unittest.TestCase):
    def test_a_tier_without_a_budget_is_refused(self) -> None:
        with self.assertRaises(BudgetError):
            wsd_budget_tiers({"wsd_budget_per_card": [{"through_rank": 1000}]})

    def test_a_repeated_rank_is_refused(self) -> None:
        with self.assertRaises(BudgetError):
            wsd_budget_tiers({"wsd_budget_per_card": [
                {"through_rank": 1000, "budget": 60},
                {"through_rank": 1000, "budget": 30},
            ]})


if __name__ == "__main__":
    unittest.main()
