import unittest

from fluency.languages.spanish.surfaces import create_spanish_card, normalize_surface


class SpanishSurfaceTests(unittest.TestCase):
    def test_normalization_preserves_accents_and_surface_form(self) -> None:
        self.assertEqual(normalize_surface("  OÍR  "), "oír")
        self.assertNotEqual(normalize_surface("oír"), normalize_surface("oir"))
        self.assertNotEqual(
            create_spanish_card("para").card_id,
            create_spanish_card("párate").card_id,
        )

    def test_normalization_is_nfc_and_collapses_whitespace(self) -> None:
        self.assertEqual(normalize_surface("A\u0301  MÍ"), "á mí")


if __name__ == "__main__":
    unittest.main()
