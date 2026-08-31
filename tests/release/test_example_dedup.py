"""Three variants of one subtitle line are one example, not three.

Subtitles repeat a line with a speaker dash, an ellipsis, or different terminal
punctuation. Easiness scores those variants almost identically, so they sort
adjacent and fill every display slot on exactly the cards a learner opens first.
"""

import unittest

from fluency.release.run_candidate import _example_identity


class ExampleIdentityTests(unittest.TestCase):
    def test_speaker_dashes_and_punctuation_do_not_make_a_new_example(self) -> None:
        variants = [
            "- Não, o que está a fazer?",
            "Não. O que está a fazer...",
            "Não o que está a fazer?",
            "não o QUE está a fazer",
        ]
        self.assertEqual(len({_example_identity(v) for v in variants}), 1)

    def test_a_leading_dash_alone_does_not_make_a_new_example(self) -> None:
        self.assertEqual(
            _example_identity("Está bem. O que é isso?"),
            _example_identity("- Está bem. O que é isso?"),
        )

    def test_different_sentences_stay_different(self) -> None:
        self.assertNotEqual(
            _example_identity("Está tudo bem, eu estou aqui."),
            _example_identity("Como é que está tudo bem?"),
        )

    def test_accents_are_not_stripped(self) -> None:
        """país and pais are distinct Portuguese words, never merged."""

        self.assertNotEqual(_example_identity("o país"), _example_identity("o pais"))


if __name__ == "__main__":
    unittest.main()
