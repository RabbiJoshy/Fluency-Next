"""The expensive limit is a budget; the cheap one is not.

The exposure this guards is not the naming but the product: surface_limit x
wsd_budget_per_card was computed nowhere and bounded by nothing.
"""

import unittest

from fluency.pipeline.budget import (
    BudgetError,
    check_wsd_budget,
    display_examples_per_card,
    projected_wsd_units,
    wsd_budget_per_card,
)


def _profile(surfaces=200, budget=60, ceiling=None, legacy=False):
    harvest = {"candidate_cap_per_surface": budget} if legacy else {"wsd_budget_per_card": budget}
    scope = {"surface_limit": surfaces}
    scope["examples_per_surface" if legacy else "display_examples_per_card"] = 3
    profile = {"scope": scope, "harvest": harvest, "wsd": {}}
    if ceiling is not None:
        profile["wsd"]["max_wsd_units_per_run"] = ceiling
    return profile


class BudgetTests(unittest.TestCase):
    def test_reads_the_new_key(self) -> None:
        self.assertEqual(wsd_budget_per_card({"wsd_budget_per_card": 60}), 60)

    def test_reads_the_legacy_key_so_existing_profiles_keep_working(self) -> None:
        self.assertEqual(wsd_budget_per_card({"candidate_cap_per_surface": 60}), 60)

    def test_new_key_wins_when_both_present(self) -> None:
        harvest = {"wsd_budget_per_card": 10, "candidate_cap_per_surface": 60}
        self.assertEqual(wsd_budget_per_card(harvest), 10)

    def test_display_limit_reads_either_name(self) -> None:
        self.assertEqual(display_examples_per_card({"display_examples_per_card": 3}), 3)
        self.assertEqual(display_examples_per_card({"examples_per_surface": 3}), 3)

    def test_missing_budget_is_refused_rather_than_defaulted(self) -> None:
        """An unstated budget must never silently become unlimited."""

        with self.assertRaises(BudgetError):
            wsd_budget_per_card({})

    def test_projected_units_follows_the_execution_cap_not_the_harvest_budget(self) -> None:
        """Two caps narrow a run; only the executor's sampling cap is spent.

        Measured: a 200-card run with a harvest budget of 60 sampled 2,000
        occurrences, not 12,000. Reading the harvest budget over-estimated
        sixfold.
        """

        self.assertEqual(projected_wsd_units(_profile(200, 60)), 2000)
        self.assertEqual(projected_wsd_units(_profile(200, 60, legacy=True)), 2000)

    def test_the_harvest_budget_binds_when_it_is_the_smaller(self) -> None:
        """A card cannot have more scored than were retained for it."""

        self.assertEqual(projected_wsd_units(_profile(200, 3)), 600)

    def test_a_declared_execution_cap_wins(self) -> None:
        profile = _profile(200, 60)
        profile["wsd"]["execution_cap_per_card"] = 25
        self.assertEqual(projected_wsd_units(profile), 5000)

    def test_within_ceiling_passes_and_reports(self) -> None:
        result = check_wsd_budget(_profile(200, 60, ceiling=25000))
        self.assertEqual(result["projected_wsd_units"], 2000)
        self.assertEqual(result["max_wsd_units_per_run"], 25000)

    def test_over_ceiling_fails_before_anything_is_spent(self) -> None:
        profile = _profile(5000, 500, ceiling=25000)
        profile["wsd"]["execution_cap_per_card"] = 500
        with self.assertRaises(BudgetError) as caught:
            check_wsd_budget(profile)
        self.assertIn("2,500,000", str(caught.exception))

    def test_default_ceiling_applies_when_unstated(self) -> None:
        self.assertEqual(
            check_wsd_budget(_profile(200, 60))["max_wsd_units_per_run"], 250_000
        )
        huge = _profile(10_000, 1_000)
        huge["wsd"]["execution_cap_per_card"] = 1_000
        with self.assertRaises(BudgetError):
            check_wsd_budget(huge)

    def test_booleans_are_not_integers(self) -> None:
        with self.assertRaises(BudgetError):
            wsd_budget_per_card({"wsd_budget_per_card": True})


if __name__ == "__main__":
    unittest.main()
