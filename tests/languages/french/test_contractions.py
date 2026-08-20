import unittest

from fluency.languages.french.contractions import analyze_contraction


class FrenchContractionTests(unittest.TestCase):
    def test_contraction_components_are_structural_metadata(self) -> None:
        expected = {
            "au": ("à", "le"),
            "aux": ("à", "les"),
            "du": ("de", "le"),
            "des": ("de", "les"),
        }
        for surface, components in expected.items():
            with self.subTest(surface=surface):
                analysis = analyze_contraction(surface)
                self.assertIsNotNone(analysis)
                assert analysis is not None
                self.assertEqual(analysis.surface_key, surface)
                self.assertEqual(analysis.components, components)

    def test_non_contraction_has_no_analysis(self) -> None:
        self.assertIsNone(analyze_contraction("prendre"))


if __name__ == "__main__":
    unittest.main()

