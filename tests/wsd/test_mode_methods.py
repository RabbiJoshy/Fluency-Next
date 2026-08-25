"""Every mode that runs WSD must declare which method it runs.

The declaration exists so that divergence is stated rather than discovered.
The test that matters is the last one: it fails when a mode gains a WSD
entrypoint without saying what method it uses.
"""

from pathlib import Path
import unittest

from fluency.wsd.mode_methods import ModeMethodError, diverging_modes, method_for_mode, mode_methods


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class ModeMethodTests(unittest.TestCase):
    def test_declared_methods_match_the_code(self) -> None:
        self.assertEqual(method_for_mode("speech"), "v7")
        self.assertEqual(method_for_mode("lyrics"), "v7")

    def test_undeclared_mode_is_an_error_not_a_default(self) -> None:
        with self.assertRaises(ModeMethodError):
            method_for_mode("artist")

    def test_divergence_is_reported_rather_than_hidden(self) -> None:
        """Both modes compute with v7 today, measured from release evidence.

        The check exists for when that stops being true: a mode advancing
        without the other should surface here rather than in a later review.
        """

        self.assertEqual(diverging_modes(), {})

    def test_each_declaration_names_its_entrypoint_and_status(self) -> None:
        for mode, spec in mode_methods().items():
            with self.subTest(mode=mode):
                self.assertTrue(spec.get("entrypoint"))
                self.assertIn(spec.get("status"), {"active", "unreviewed", "frozen"})
                self.assertTrue(spec.get("note"), "a declaration without a reason is not one")

    def test_every_wsd_entrypoint_in_the_tree_is_declared(self) -> None:
        """A mode cannot gain a WSD path without declaring its method."""

        declared = {spec["entrypoint"] for spec in mode_methods().values()}
        found = {
            f"fluency.{path.relative_to(REPOSITORY_ROOT / 'src' / 'fluency').with_suffix('')}"
            .replace("/", ".")
            for path in (REPOSITORY_ROOT / "src" / "fluency").rglob("wsd_execute.py")
        }
        self.assertEqual(found - declared, set(), "undeclared WSD entrypoint")


if __name__ == "__main__":
    unittest.main()
