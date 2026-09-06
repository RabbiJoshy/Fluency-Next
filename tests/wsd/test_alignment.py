import unittest

from fluency.core.identity import create_card_record
from fluency.wsd.alignment import LiteralGlossAlignmentCorrector, literal_cues
from fluency.wsd.menus import MenuAnalysis, SenseLeaf, build_analysis_id


class FakeWordAligner:
    model_revision = "fixture-word-aligner/v1"

    def __init__(self, pairs):
        self.pairs = pairs
        self.calls = 0

    def align(self, source_tokens, translation_tokens):
        self.calls += 1
        return {"inter": self.pairs}


def analysis(card_id, adapter, key, headword, senses):
    return MenuAnalysis(
        menu_analysis_id=build_analysis_id(
            card_id=card_id, source_adapter=adapter, source_analysis_key=key
        ),
        card_id=card_id,
        surface_form="hizo",
        headword=headword,
        part_of_speech="verb",
        source_adapter=adapter,
        source_analysis_key=key,
        senses=tuple(
            SenseLeaf(sense_id, gloss, "", f"fixture:{sense_id}", {})
            for sense_id, gloss in senses
        ),
        provider_metadata={},
    )


class LiteralGlossAlignmentTests(unittest.TestCase):
    def setUp(self):
        self.card = create_card_record("es", "hizo")
        self.menu = (
            analysis(
                self.card.card_id,
                "spanishdict-sense-menu/v1",
                "hacer:verb",
                "hacer",
                (("make", "to make"), ("do", "to do")),
            ),
        )

    def test_irregular_literal_cue_corrects_one_exact_leaf(self):
        word_aligner = FakeWordAligner(((0, 1),))
        corrector = LiteralGlossAlignmentCorrector(word_aligner)
        result = corrector.correct(
            sentence="Hizo eso.",
            translation="He made that.",
            surface_form="hizo",
            analyses=self.menu,
            current_analysis_id=self.menu[0].menu_analysis_id,
            current_sense_id="do",
            target_span=(0, 4),
        )

        self.assertEqual(result.sense_id, "make")
        self.assertEqual(result.cue, "made")
        self.assertEqual(result.aligned_translation, "made")

    def test_no_supplied_translation_abstains_without_loading_the_aligner(self):
        word_aligner = FakeWordAligner(())
        corrector = LiteralGlossAlignmentCorrector(word_aligner)
        result = corrector.correct(
            sentence="Hizo eso.", translation="", surface_form="hizo",
            analyses=self.menu, current_analysis_id=self.menu[0].menu_analysis_id,
            current_sense_id="do", target_span=(0, 4),
        )
        self.assertIsNone(result)
        self.assertEqual(word_aligner.calls, 0)

    def test_cue_owned_by_two_leaves_is_inseparable(self):
        duplicated = (
            analysis(
                self.card.card_id, "wiktionary-sense-menu/v1", "a", "fazer",
                (("one", "to make"), ("two", "to make")),
            ),
        )
        result = LiteralGlossAlignmentCorrector(FakeWordAligner(((0, 1),))).correct(
            sentence="Hizo eso.", translation="He made that.", surface_form="hizo",
            analyses=duplicated, current_analysis_id=duplicated[0].menu_analysis_id,
            current_sense_id="one", target_span=(0, 4),
        )
        self.assertIsNone(result)

    def test_unmarked_repeated_surface_abstains(self):
        result = LiteralGlossAlignmentCorrector(FakeWordAligner(((0, 0),))).correct(
            sentence="Hizo y luego hizo.", translation="Made and then did.",
            surface_form="hizo", analyses=self.menu,
            current_analysis_id=self.menu[0].menu_analysis_id,
            current_sense_id="do",
        )
        self.assertIsNone(result)

    def test_cue_generation_is_provider_independent(self):
        menus = (
            self.menu,
            (
                analysis(
                    self.card.card_id,
                    "wiktionary-sense-menu/v1",
                    "fazer:verb",
                    "fazer",
                    (("make", "to make"), ("do", "to do")),
                ),
            ),
        )
        for menu in menus:
            with self.subTest(adapter=menu[0].source_adapter):
                result = LiteralGlossAlignmentCorrector(
                    FakeWordAligner(((0, 1),))
                ).correct(
                    sentence="Hizo eso.",
                    translation="He made that.",
                    surface_form="hizo",
                    analyses=menu,
                    current_analysis_id=menu[0].menu_analysis_id,
                    current_sense_id="do",
                    target_span=(0, 4),
                )
                self.assertEqual(result.sense_id, "make")
                self.assertIn(("made",), literal_cues("to make"))


if __name__ == "__main__":
    unittest.main()
