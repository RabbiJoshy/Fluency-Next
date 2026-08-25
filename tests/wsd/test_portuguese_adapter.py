"""Portuguese surface location.

Follows the Spanish adapter rather than the French one: Portuguese has no
elision, so locating a surface needs a word scan and the shared normalizer, not
a tokenizer module.
"""

import unittest

from fluency.wsd.languages.portuguese import PortugueseWSDAdapter


class PortugueseLocateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = PortugueseWSDAdapter()

    def spans(self, sentence, surface):
        return [(o.observed_text, o.start, o.end) for o in self.adapter.locate(sentence, surface)]

    def test_language_code(self) -> None:
        self.assertEqual(self.adapter.language, "pt")

    def test_locates_a_plain_surface(self) -> None:
        self.assertEqual(self.spans("Esta é a minha casa.", "casa"), [("casa", 15, 19)])

    def test_hyphen_is_a_boundary_so_clitics_are_reachable(self) -> None:
        """The frequency list split on hyphens, so no `da-me` card exists."""

        self.assertEqual(self.spans("Dá-me o livro", "me"), [("me", 3, 5)])
        self.assertEqual(self.spans("Dá-me o livro", "dá"), [("Dá", 0, 2)])

    def test_accents_are_contrastive(self) -> None:
        """acao is not a spelling of ação; matching it would merge two cards."""

        self.assertEqual(self.spans("A ação e a acao", "ação"), [("ação", 2, 6)])

    def test_case_is_normalised_but_the_observed_text_is_kept(self) -> None:
        found = self.adapter.locate("Casa grande", "casa")
        self.assertEqual(found[0].observed_text, "Casa")
        self.assertEqual(found[0].surface_key, "casa")

    def test_every_occurrence_is_returned(self) -> None:
        self.assertEqual(len(self.adapter.locate("casa, casa e casa", "casa")), 3)

    def test_absent_surface_yields_nothing(self) -> None:
        self.assertEqual(self.adapter.locate("Esta é a minha casa.", "livro"), ())

    def test_empty_sentence_is_safe(self) -> None:
        self.assertEqual(self.adapter.locate("", "casa"), ())

    def test_substrings_are_not_matched(self) -> None:
        """casar contains casa but is a different card."""

        self.assertEqual(self.adapter.locate("Vamos casar", "casa"), ())


if __name__ == "__main__":
    unittest.main()
