"""Only known grammatical tails may be projected out of visible glosses."""

import unittest

from fluency.features.wiktionary_gloss import project_gloss


class WiktionaryGlossProjectionTests(unittest.TestCase):
    def test_object_pronoun_note_becomes_a_role_and_typed_links(self) -> None:
        projection = project_gloss(
            "him, it (as a direct object; as an indirect object, see lhe; "
            "after prepositions, see ele)"
        )

        self.assertEqual(projection.display_text, "him, it")
        self.assertEqual(
            [(item.family, item.kind, item.value) for item in projection.specialist_features],
            [("construction", "object_role", "direct object")],
        )
        self.assertEqual(
            [(item.relation, item.target) for item in projection.cross_references],
            [("indirect_object", "lhe"), ("after_prepositions", "ele")],
        )

    def test_alternate_wording_is_supported_without_broadening_the_match(self) -> None:
        projection = project_gloss(
            "them (as a direct object; the corresponding indirect object is lhes; "
            "the form used after prepositions is elas)"
        )
        self.assertEqual(projection.display_text, "them")
        self.assertEqual(
            [item.target for item in projection.cross_references],
            ["lhes", "elas"],
        )

    def test_semantic_parenthetical_is_untouched(self) -> None:
        text = "to pass (to advance through the stages necessary to become valid)"
        self.assertEqual(project_gloss(text).display_text, text)
        self.assertEqual(project_gloss(text).specialist_features, ())
        self.assertEqual(project_gloss(text).cross_references, ())

    def test_functional_tail_becomes_typed_metadata(self) -> None:
        projection = project_gloss("from (used to indicate origin)")
        self.assertEqual(projection.display_text, "from")
        self.assertEqual(
            [(item.family, item.kind, item.value) for item in projection.specialist_features],
            [("functional", "usage_note", "used to indicate origin")],
        )

    def test_multiple_known_tails_are_projected_in_source_order(self) -> None:
        projection = project_gloss(
            "how (preceding adjectives) (indicates surprise or delight)"
        )
        self.assertEqual(projection.display_text, "how")
        self.assertEqual(
            [(item.family, item.value) for item in projection.specialist_features],
            [
                ("construction", "preceding adjectives"),
                ("functional", "indicates surprise or delight"),
            ],
        )

    def test_unrecognized_outer_tail_keeps_the_whole_gloss(self) -> None:
        text = "bank (used as a name for a financial institution)"
        self.assertEqual(project_gloss(text).display_text, text)

    def test_closed_vocabulary_grammar_tail_becomes_metadata(self) -> None:
        projection = project_gloss(
            "your, yours (2nd-person singular formal or 2nd-person plural)"
        )
        self.assertEqual(projection.display_text, "your, yours")
        self.assertEqual(
            [(item.family, item.kind, item.value) for item in projection.specialist_features],
            [("grammar", "gloss_note", "2nd-person singular formal or 2nd-person plural")],
        )

    def test_grammatical_word_inside_semantic_tail_is_untouched(self) -> None:
        for text in (
            "girlfriend (female partner in a romantic relationship)",
            "ball (formal dance)",
            "happy (of a person)",
            "guy; dude (male person)",
            "article (object)",
        ):
            with self.subTest(text=text):
                self.assertEqual(project_gloss(text).display_text, text)
                self.assertEqual(project_gloss(text).specialist_features, ())

    def test_reference_frame_is_construction_metadata(self) -> None:
        projection = project_gloss("their (when referring to a plural noun)")
        self.assertEqual(projection.display_text, "their")
        self.assertEqual(projection.specialist_features[0].family, "construction")
