"""A subtitle row is a unit of display, not a unit of language.

One row often carries a whole exchange. Measured on the live Portuguese deck,
660 of 11,000 displayed examples held more than one sentence, and in 93% of
those the target word appeared in only one of them -- so the rest is text the
learner reads past to find the word being taught.
"""

import unittest

from fluency.release.sentences import sentence_count


class SentenceCountTests(unittest.TestCase):
    def test_an_exchange_is_more_than_one_sentence(self) -> None:
        self.assertEqual(sentence_count("- O que está a fazer? Não."), 2)
        self.assertEqual(sentence_count("Não. De que está a falar?"), 2)

    def test_an_ordinary_sentence_is_one(self) -> None:
        for text in ("Está tudo bem, eu estou aqui.",
                     "Je to náš dům a mně se to líbí.",
                     "O que estás a fazer na minha casa?"):
            with self.subTest(text=text):
                self.assertEqual(sentence_count(text), 1)

    def test_trailing_off_is_not_a_boundary(self) -> None:
        """An ellipsis is one speaker tailing off inside a single line."""

        self.assertEqual(sentence_count("Isso não é o que eu..."), 1)

    def test_a_title_does_not_end_a_sentence(self) -> None:
        for text in ("A Sra. Silva chegou.", "O Dr. Costa não veio."):
            with self.subTest(text=text):
                self.assertEqual(sentence_count(text), 1)

    def test_initials_do_not_end_a_sentence(self) -> None:
        self.assertEqual(sentence_count("J. R. Silva ligou."), 1)

    def test_czech_abbreviations_are_handled_too(self) -> None:
        """The rule is provider- and language-agnostic, so Czech titles count."""

        self.assertEqual(sentence_count("Byl tam p. Novák. Pak odešel."), 2)
        self.assertEqual(sentence_count("Přišel p. Novák."), 1)

    def test_empty_text_has_no_sentences(self) -> None:
        self.assertEqual(sentence_count("   "), 0)


if __name__ == "__main__":
    unittest.main()
