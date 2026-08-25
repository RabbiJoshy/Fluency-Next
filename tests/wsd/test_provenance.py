"""A release must say what computed its decisions, not just what shape it speaks.

v7 was tuned on Rosalia, and Rosalia's release speaks the v7 contract while its
decisions were computed by v5 and migrated forward. Both facts are legitimate;
conflating them is not, because "the deck is on v7" and "the deck's decisions
are v7" sound identical.
"""

import unittest

from fluency.artist.wsd_bridge import ArtistWSDBridgeError, bridge_materialized_assignments
from fluency.wsd.provenance import describe_composition, method_composition


def _index(*methods):
    return [{"wsd_distribution": {"buckets": [
        ({} if m is None else {"provenance": {"assignment_method": m}}) for m in methods
    ]}}]


class MethodCompositionTests(unittest.TestCase):
    def test_fully_native_release(self) -> None:
        c = method_composition(_index("native-v7", "native-v7"))
        self.assertEqual(c["native_share"], 1.0)
        self.assertTrue(c["fully_native"])

    def test_fully_migrated_release_is_not_native(self) -> None:
        """The Rosalia case: v7 contract, v5 decisions."""

        c = method_composition(_index("materialized", "materialized"))
        self.assertEqual(c["native_share"], 0.0)
        self.assertFalse(c["fully_native"])

    def test_mixed_release_reports_the_split(self) -> None:
        c = method_composition(_index("native-v7", "materialized", "materialized", "materialized"))
        self.assertEqual(c["native_share"], 0.25)
        self.assertEqual(c["methods"], {"materialized": 3, "native-v7": 1})

    def test_missing_provenance_is_named_not_assumed(self) -> None:
        c = method_composition(_index(None, "native-v7"))
        self.assertEqual(c["methods"]["unrecorded"], 1)
        self.assertFalse(c["fully_native"])

    def test_empty_release_is_not_native(self) -> None:
        c = method_composition([])
        self.assertEqual(c["decision_count"], 0)
        self.assertFalse(c["fully_native"])

    def test_description_is_readable(self) -> None:
        text = describe_composition(method_composition(_index("native-v7", "materialized")))
        self.assertIn("50.0% native", text)


class MigrationGuardTests(unittest.TestCase):
    def test_migration_can_be_refused(self) -> None:
        """A run wanting real v7 decisions must not silently get migrated ones."""

        with self.assertRaises(ArtistWSDBridgeError) as caught:
            bridge_materialized_assignments(
                [], {}, {}, artist_slug="rosalia", allow_migration=False
            )
        self.assertIn("without being recomputed", str(caught.exception))

    def test_migration_is_allowed_by_default(self) -> None:
        index, evidence = bridge_materialized_assignments([], {}, {}, artist_slug="rosalia")
        self.assertEqual(index, [])
        self.assertIsNone(evidence)


if __name__ == "__main__":
    unittest.main()
