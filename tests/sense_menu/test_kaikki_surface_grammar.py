"""Wiktionary's grammatical analysis of a surface is kept, not discarded.

`_semantic_senses` drops form-of senses because they carry no meaning. The
analysis inside them -- diz is the third-person singular present indicative of
dizer -- is a fact about the surface, not about any sense, so it belongs on the
MenuAnalysis rather than on a leaf.
"""

import unittest

from fluency.sense_menu.kaikki import _surface_grammar


def _normalize(value: str) -> str:
    return value.strip().lower()


class SurfaceGrammarTests(unittest.TestCase):
    def test_extracts_target_and_tags(self) -> None:
        row = {"senses": [{
            "tags": ["form-of", "indicative", "present", "singular", "third-person"],
            "form_of": [{"word": "dizer"}],
        }]}
        self.assertEqual(
            _surface_grammar(row, _normalize),
            {"dizer": ["indicative", "present", "singular", "third-person"]},
        )

    def test_form_of_marker_itself_is_not_a_tag(self) -> None:
        row = {"senses": [{"tags": ["form-of", "plural"], "form_of": [{"word": "o"}]}]}
        self.assertEqual(_surface_grammar(row, _normalize), {"o": ["plural"]})

    def test_alt_of_is_read_too(self) -> None:
        row = {"senses": [{"tags": ["alt-of", "archaic"], "alt_of": [{"word": "porquê"}]}]}
        self.assertEqual(_surface_grammar(row, _normalize), {"porquê": ["archaic"]})

    def test_tags_from_several_senses_merge_for_one_target(self) -> None:
        """era is both first- and third-person imperfect of ser."""

        row = {"senses": [
            {"tags": ["form-of", "first-person", "imperfect"], "form_of": [{"word": "ser"}]},
            {"tags": ["form-of", "third-person", "imperfect"], "form_of": [{"word": "ser"}]},
        ]}
        self.assertEqual(
            _surface_grammar(row, _normalize),
            {"ser": ["first-person", "imperfect", "third-person"]},
        )

    def test_semantic_senses_are_ignored(self) -> None:
        row = {"senses": [{"tags": ["masculine"], "glosses": ["a thing"]}]}
        self.assertEqual(_surface_grammar(row, _normalize), {})

    def test_form_of_without_tags_yields_nothing(self) -> None:
        row = {"senses": [{"tags": ["form-of"], "form_of": [{"word": "x"}]}]}
        self.assertEqual(_surface_grammar(row, _normalize), {})

    def test_malformed_targets_are_skipped(self) -> None:
        row = {"senses": [{"tags": ["form-of", "plural"], "form_of": [{"word": ""}, {}, 3]}]}
        self.assertEqual(_surface_grammar(row, _normalize), {})


if __name__ == "__main__":
    unittest.main()
