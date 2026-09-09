"""Three examples on a card should be three different sentences.

Two independent 100-card audits found the same defect from opposite ends:
43 of 100 French cards and 22 of 100 Portuguese showed a near-duplicate pair,
because Tatoeba's contributors deliberately write agreement families. And a
sentence built purely from the commonest words wins on every card those words
belong to, so 500 French display slots held only 304 distinct sentences.
"""

import unittest

from fluency.release.sentences import near_duplicate


class NearDuplicateTests(unittest.TestCase):
    def test_an_agreement_family_is_one_example(self) -> None:
        for a, b in (
            ("Vous êtes plus grand que moi.", "Vous êtes plus grande que moi."),
            ("Ce ne sont pas mes affaires !", "Ce ne sont pas tes affaires."),
            ("Ele não está com o bilhete.", "Ela não está com o bilhete."),
        ):
            with self.subTest(a=a):
                self.assertTrue(near_duplicate(a, b))

    def test_different_sentences_stay_different(self) -> None:
        for a, b in (
            ("Eso es todo lo que tengo.", "El dinero no lo es todo."),
            ("Está tudo bem, eu estou aqui.", "Como é que está tudo bem?"),
            ("Je ne sais pas qui il est.", "Je ne peux pas le faire."),
        ):
            with self.subTest(a=a):
                self.assertFalse(near_duplicate(a, b))

    def test_word_order_does_not_rescue_a_duplicate(self) -> None:
        """Similarity is over the token set, so reordering is still the same example."""

        self.assertTrue(near_duplicate("Eu não sei o que fazer.", "Não sei o que fazer eu."))

    def test_a_short_sentence_inside_a_longer_one_is_not_the_same(self) -> None:
        """Length is respected: containment is not identity."""

        self.assertFalse(
            near_duplicate(
                "Não sei.",
                "Não sei o que ele quer dizer com isso, e não quero saber.",
            )
        )

    def test_the_threshold_is_a_parameter(self) -> None:
        a, b = "Vous êtes plus grand que moi.", "Vous êtes plus grande que moi."
        self.assertTrue(near_duplicate(a, b, threshold=0.8))
        self.assertFalse(near_duplicate(a, b, threshold=0.95))

    def test_empty_text_is_never_a_duplicate(self) -> None:
        self.assertFalse(near_duplicate("", "Qualquer coisa."))


if __name__ == "__main__":
    unittest.main()
