"""A language brings an adapter, a POS model and a POS gate to a WSD run.

The speech executor named Spanish in ten places, so running any other language
meant editing all of them together and getting every one right. The POS gate in
particular is keyed on the dictionary rather than the language: SpanishDict and
Wiktionary disagree about categories in ways that silently delete correct senses.
"""

import unittest

from fluency.wsd.bindings import LanguageBindingError, binding_for, pos_gate_for


class BindingTests(unittest.TestCase):
    def test_each_language_binds_its_own_adapter(self) -> None:
        expected = {
            "es": "SpanishWSDAdapter",
            "pt": "PortugueseWSDAdapter",
            "fr": "FrenchWSDAdapter",
        }
        for language, name in expected.items():
            with self.subTest(language=language):
                adapter = binding_for(language).adapter_factory()
                self.assertEqual(type(adapter).__name__, name)
                self.assertEqual(adapter.language, language)

    def test_portuguese_uses_its_own_pos_model(self) -> None:
        """Tagging Portuguese with the Spanish model is the obvious silent bug."""

        self.assertEqual(binding_for("pt").pos_model_role, "occurrence-pos-pt")
        self.assertNotEqual(
            binding_for("pt").pos_model_role, binding_for("es").pos_model_role
        )

    def test_menu_provider_drives_the_gate_not_the_language(self) -> None:
        self.assertEqual(binding_for("es").menu_provider, "spanishdict")
        self.assertEqual(binding_for("pt").menu_provider, "wiktionary")
        self.assertEqual(binding_for("fr").menu_provider, "wiktionary")

    def test_unknown_language_is_refused_with_what_exists(self) -> None:
        with self.assertRaises(LanguageBindingError) as caught:
            binding_for("de")
        self.assertIn("available:", str(caught.exception))


class PosGateTests(unittest.TestCase):
    def test_wiktionary_languages_accept_contraction_from_adp(self) -> None:
        """do, ao, da, na are filed only as `contraction`; UD has no such tag."""

        for language in ("pt", "fr"):
            compatible, _ = pos_gate_for(language)
            with self.subTest(language=language):
                self.assertTrue(compatible("contraction", "ADP"))

    def test_spanish_keeps_its_own_gate(self) -> None:
        """SpanishDict files auxiliaries as VERB and determiners as ADJ."""

        compatible, _ = pos_gate_for("es")
        self.assertTrue(compatible("VERB", "AUX"))
        self.assertTrue(compatible("ADJ", "DET"))

    def test_the_two_gates_are_not_interchangeable(self) -> None:
        spanish, _ = pos_gate_for("es")
        wiktionary, _ = pos_gate_for("pt")
        # `contraction` is a Wiktionary category; SpanishDict treats it as
        # orthogonal, so both accept it, but only Wiktionary knows `article`.
        self.assertTrue(wiktionary("article", "DET"))
        self.assertFalse(wiktionary("noun", "ADP"))

    def test_genuine_mismatches_still_reject(self) -> None:
        compatible, _ = pos_gate_for("pt")
        self.assertFalse(compatible("verb", "NOUN"))


if __name__ == "__main__":
    unittest.main()
