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
