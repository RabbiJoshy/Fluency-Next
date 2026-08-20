import unittest

from fluency.languages.french.surfaces import create_french_card, normalize_surface


class FrenchSurfaceTests(unittest.TestCase):
    def assertSameCard(self, first: str, second: str) -> None:
        self.assertEqual(create_french_card(first).card_id, create_french_card(second).card_id)

    def assertDifferentCards(self, first: str, second: str) -> None:
        self.assertNotEqual(
            create_french_card(first).card_id,
            create_french_card(second).card_id,
        )

    def test_unicode_case_and_whitespace_are_normalized(self) -> None:
        self.assertEqual(normalize_surface("  E\u0301TE\u0301  "), "été")
        self.assertEqual(normalize_surface("de\u00a0  rien"), "de rien")

    def test_typographic_apostrophes_share_identity(self) -> None:
        variants = ["l'homme", "l’homme", "l‘homme", "lʼhomme"]
        expected_id = create_french_card(variants[0]).card_id
        self.assertTrue(
            all(create_french_card(variant).card_id == expected_id for variant in variants)
        )

    def test_typographic_hyphens_share_identity(self) -> None:
        variants = ["porte-monnaie", "porte‐monnaie", "porte‑monnaie"]
        expected_id = create_french_card(variants[0]).card_id
        self.assertTrue(
            all(create_french_card(variant).card_id == expected_id for variant in variants)
        )

    def test_identity_bearing_characters_are_preserved(self) -> None:
        pairs = [
            ("été", "ete"),
            ("l’homme", "lhomme"),
            ("porte-monnaie", "portemonnaie"),
            ("cœur", "coeur"),
            ("prendre", "prends"),
        ]
        for first, second in pairs:
            with self.subTest(first=first, second=second):
                self.assertDifferentCards(first, second)

    def test_arbitrary_punctuation_is_not_stripped(self) -> None:
        self.assertEqual(normalize_surface("Bonjour!"), "bonjour!")

    def test_empty_and_non_string_surfaces_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            normalize_surface(" \t\n ")
        with self.assertRaises(TypeError):
            normalize_surface(None)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()

