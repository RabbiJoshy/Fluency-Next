import unittest

from fluency.languages.surfaces import normalizer_for_language, registered_languages


class MinimalLanguageScaffoldTests(unittest.TestCase):
    def test_remaining_app_languages_are_discoverable(self) -> None:
        self.assertTrue({"it", "ru", "sv"}.issubset(registered_languages()))

    def test_scaffolds_preserve_language_letters_and_normalize_typography(self) -> None:
        self.assertEqual(normalizer_for_language("it")("  L’ACQUA  "), "l'acqua")
        self.assertEqual(normalizer_for_language("ru")("  ЁЖ  "), "ёж")
        self.assertEqual(normalizer_for_language("sv")("  FÅR  "), "får")


if __name__ == "__main__":
    unittest.main()
