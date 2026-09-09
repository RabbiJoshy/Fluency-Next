"""One harvest, two decks.

A European and a Brazilian Portuguese deck can come from the same pool only if
the harvest records which variety each sentence announces. Measured on the
Portuguese bank: 28.4% Brazilian-marked, 6.4% European-marked, 65.5% unmarked --
so an unmarked sentence is undetectable, not neutral, and some of it is quietly
Brazilian. The tag is recorded, never used to reject.
"""

import json
from pathlib import Path
import unittest

from fluency.harvest.matching import detect_variety

ROOT = Path(__file__).resolve().parents[2]
PT = json.loads((ROOT / "config/harvest/languages/pt-v1.json").read_text())
ES = json.loads((ROOT / "config/harvest/languages/es-v1.json").read_text())
CS = json.loads((ROOT / "config/harvest/languages/cs-v1.json").read_text())


class PortugueseVarietyTests(unittest.TestCase):
    def test_brazilian_markers(self) -> None:
        for text in ("Por que você está no banheiro?",
                     "A gente tem que fazer o melhor com o que temos.",
                     "Ele está fazendo isto agora."):
            with self.subTest(text=text):
                self.assertEqual(detect_variety(text, PT), "br")

    def test_european_markers(self) -> None:
        for text in ("Porque é que estás a fazer essa cara?",
                     "Tu trabalhaste mais do que eu.",
                     "Apanhei o autocarro para casa."):
            with self.subTest(text=text):
                self.assertEqual(detect_variety(text, PT), "eu")

    def test_an_unmarked_sentence_is_not_guessed(self) -> None:
        """Undetectable is reported as unknown, not as the majority variety."""

        self.assertIsNone(detect_variety("O que eu preciso é de um amigo.", PT))

    def test_a_sentence_carrying_both_is_not_forced(self) -> None:
        """Mixed evidence is no evidence; better unknown than wrong."""

        self.assertIsNone(detect_variety("Você trabalhaste com o teu autocarro.", PT))


class SpanishVarietyTests(unittest.TestCase):
    def test_the_split_is_the_second_person_plural(self) -> None:
        self.assertEqual(detect_variety("¿Ustedes están a favor?", ES), "419")
        self.assertEqual(detect_variety("¿Vosotros venís conmigo?", ES), "es")


class LanguagesWithoutVarietiesTests(unittest.TestCase):
    def test_a_language_declaring_no_markers_tags_nothing(self) -> None:
        """Absence is declared: Czech has no variety split worth recording."""

        self.assertIsNone(detect_variety("Je to náš dům a mně se to líbí.", CS))


if __name__ == "__main__":
    unittest.main()
