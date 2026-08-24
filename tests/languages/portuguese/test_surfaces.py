"""Portuguese surface-identity contract."""

import unittest

from fluency.languages.portuguese.surfaces import (
    create_portuguese_card,
    normalize_surface,
)
from fluency.languages.surfaces import normalizer_for_language


class PortugueseSurfaceTests(unittest.TestCase):
    def test_registry_resolves_portuguese(self) -> None:
        self.assertIs(normalizer_for_language("pt"), normalize_surface)

    def test_lowercases_and_collapses_whitespace(self) -> None:
        self.assertEqual(normalize_surface("  Você   é  "), "você é")

    def test_accents_remain_contrastive(self) -> None:
        for left, right in (("país", "pais"), ("está", "esta"), ("é", "e")):
            with self.subTest(pair=(left, right)):
                self.assertNotEqual(normalize_surface(left), normalize_surface(right))

    def test_hyphenated_clitic_is_preserved_as_one_surface(self) -> None:
        self.assertEqual(normalize_surface("Dá-me"), "dá-me")
        self.assertEqual(normalize_surface("far-me-ia"), "far-me-ia")

    def test_card_id_is_language_scoped(self) -> None:
        self.assertTrue(create_portuguese_card("casa").card_id.startswith("card_pt_"))

    def test_empty_surface_rejected(self) -> None:
        with self.assertRaises(ValueError):
            normalize_surface("   ")


if __name__ == "__main__":
    unittest.main()
