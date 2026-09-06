"""Czech runs with no POS model, and says so.

spaCy publishes no Czech pipeline. A POS gate is only ever subtractive -- it
removes senses the observed tag rules out, while the embedding chooses among
what is left -- so an uncalibrated gate is not neutral but destructive:
unbridged filtering deleted every sense on 34% of real Portuguese occurrences.
Declaring the absence is therefore safer than approximating a tagger.
"""

import unittest

from fluency.wsd.bindings import binding_for, pos_gate_for


class CzechBindingTests(unittest.TestCase):
    def test_czech_declares_that_it_has_no_pos_model(self) -> None:
        self.assertIsNone(binding_for("cs").pos_model_role)

    def test_czech_reads_wiktionary_like_every_language_after_spanish(self) -> None:
        self.assertEqual(binding_for("cs").menu_provider, "wiktionary")

    def test_a_language_without_a_tagger_keeps_every_sense_eligible(self) -> None:
        compatible, orthogonal = pos_gate_for("cs")
        self.assertTrue(compatible("noun", "VERB"))
        self.assertTrue(compatible("verb", "NOUN"))
        self.assertFalse(orthogonal("noun"))

    def test_a_language_with_a_tagger_still_discriminates(self) -> None:
        """The absence must be scoped to Czech and not weaken anyone else."""

        compatible, _ = pos_gate_for("pt")
        self.assertFalse(compatible("noun", "VERB"))


class CzechAdapterTests(unittest.TestCase):
    def test_diacritics_are_matched_never_folded(self) -> None:
        from fluency.wsd.languages.czech import CzechWSDAdapter

        adapter = CzechWSDAdapter()
        self.assertEqual(len(adapter.locate("Musí to být pravda.", "být")), 1)
        # byt (flat) and byt (to be) are different Czech words.
        self.assertEqual(adapter.locate("Mám malý byt.", "být"), ())


if __name__ == "__main__":
    unittest.main()
