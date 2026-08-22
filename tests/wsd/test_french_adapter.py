import unittest

from fluency.wsd.languages.french import FrenchWSDAdapter


class FrenchWSDAdapterTests(unittest.TestCase):
    def test_locates_exact_surface_with_offsets(self) -> None:
        sentence = "Je veux partir, mais je veux comprendre."
        occurrences = FrenchWSDAdapter().locate(sentence, "veux")
        self.assertEqual(len(occurrences), 2)
        self.assertEqual(
            [sentence[item.start:item.end] for item in occurrences],
            ["veux", "veux"],
        )

    def test_does_not_lemma_expand_the_requested_surface(self) -> None:
        self.assertEqual(FrenchWSDAdapter().locate("Je voulais partir.", "veux"), ())


if __name__ == "__main__":
    unittest.main()
