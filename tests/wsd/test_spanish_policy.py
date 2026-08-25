import unittest

from fluency.core.identity import create_card_record
from fluency.wsd.gloss_scoring import LeafScore
from fluency.wsd.languages.spanish import (
    SpanishV5CandidatePolicy,
    se_reflexive_evidence,
    sense_compatible_bridged,
)
from fluency.wsd.menus import MenuAnalysis, SenseLeaf, build_analysis_id


def analysis(card_id, key, headword, pos, senses):
    adapter = "spanishdict-sense-menu/v1"
    return MenuAnalysis(
        menu_analysis_id=build_analysis_id(
            card_id=card_id, source_adapter=adapter, source_analysis_key=key
        ),
        card_id=card_id,
        surface_form="casa",
        headword=headword,
        part_of_speech=pos,
        source_adapter=adapter,
        source_analysis_key=key,
        senses=tuple(
            SenseLeaf(sense_id, translation, context, f"sd:{sense_id}", {"context": context})
            for sense_id, translation, context in senses
        ),
        provider_metadata={},
    )


class SpanishV5CandidatePolicyTests(unittest.TestCase):
    def setUp(self):
        card = create_card_record("es", "casa")
        self.noun = analysis(
            card.card_id, "casa:noun", "casa", "NOUN",
            (("home", "house", "building"),),
        )
        self.verb = analysis(
            card.card_id, "casar:verb", "casar", "VERB",
            (("marry", "to marry", ""), ("empty", "", "used with de")),
        )
        self.reflexive = analysis(
            card.card_id, "casarse:verb", "casarse", "VERB",
            (("get-married", "to get married", ""),),
        )
        self.phrase = analysis(
            card.card_id, "casa:phrase", "casa", "PHRASE",
            (("phrase", "at home", "provider phrase rendering"),),
        )
        self.policy = SpanishV5CandidatePolicy(constraint_mode="evidence_only")

    def test_tagset_bridge_preserves_spanishdict_determiner_categories(self):
        self.assertTrue(sense_compatible_bridged("ADJ", "DET"))
        self.assertFalse(sense_compatible_bridged("VERB", "DET"))

    def test_se_only_gate_is_conservative(self):
        self.assertTrue(se_reflexive_evidence("casa", "Se casa hoy"))
        self.assertFalse(se_reflexive_evidence("casa", "Casa a la pareja"))
        self.assertIsNone(se_reflexive_evidence("casa", "Me casa hoy"))

    def test_pos_and_clitic_constraints_are_evidence_not_destructive_filters(self):
        prepared = self.policy.prepare(
            sentence="Se casa hoy", surface_form="casa", observed_pos="VERB",
            analyses=(self.noun, self.verb, self.reflexive),
        )
        self.assertEqual(prepared.analyses, (self.noun, self.verb, self.reflexive))
        self.assertEqual(prepared.evidence["policy"], "evidence_only")
        self.assertEqual(
            prepared.evidence["pos_removed_analysis_ids"],
            [self.noun.menu_analysis_id],
        )
        self.assertEqual(
            prepared.evidence["clitic_removed_analysis_ids"],
            [self.verb.menu_analysis_id],
        )
        self.assertEqual(
            prepared.evidence["constraint_supported_analysis_ids"],
            [self.reflexive.menu_analysis_id],
        )
        self.assertEqual(
            prepared.evidence["constraint_rejected_analysis_ids"],
            sorted((self.noun.menu_analysis_id, self.verb.menu_analysis_id)),
        )

    def test_filter_mode_restores_the_v6_active_candidate_set(self):
        prepared = SpanishV5CandidatePolicy(constraint_mode="filter").prepare(
            sentence="Se casa hoy", surface_form="casa", observed_pos="VERB",
            analyses=(self.noun, self.verb, self.reflexive, self.phrase),
        )
        self.assertEqual(prepared.analyses, (self.reflexive,))
        self.assertEqual(prepared.evidence["policy"], "filter")
        self.assertEqual(
            prepared.evidence["constraint_rejected_analysis_ids"],
            sorted((
                self.noun.menu_analysis_id,
                self.verb.menu_analysis_id,
                self.phrase.menu_analysis_id,
            )),
        )

    def test_constraint_mode_must_be_explicitly_supported(self):
        with self.assertRaisesRegex(ValueError, "constraint mode"):
            SpanishV5CandidatePolicy(constraint_mode="guess")

    def test_auxiliary_se_does_not_select_a_lexical_reflexive_headword(self):
        card = create_card_record("es", "ha")
        haber = analysis(
            card.card_id, "haber:verb", "haber", "VERB",
            (("aux", "to have", "auxiliary"),),
        )
        haberse = analysis(
            card.card_id, "haberse:verb", "haberse", "VERB",
            (("confront", "to have it out", "to confront"),),
        )

        prepared = SpanishV5CandidatePolicy(constraint_mode="filter").prepare(
            sentence="Se ha ido", surface_form="ha", observed_pos="AUX",
            analyses=(haber, haberse),
        )

        self.assertEqual(prepared.analyses, (haber,))
        self.assertFalse(prepared.evidence["se_reflexive_evidence"])

    def test_menu_prior_and_leaf_repair_match_v5_order(self):
        scores = (
            LeafScore(self.verb.menu_analysis_id, "marry", 0.50),
            LeafScore(self.verb.menu_analysis_id, "empty", 0.509),
        )
        adjusted = self.policy.adjust_scores(scores, (self.verb,))
        self.assertEqual(adjusted[0].sense_id, "marry")
        repaired = self.policy.repair_leaf(
            sentence="Casa a la pareja", analyses=(self.verb,),
            selected=next(score for score in adjusted if score.sense_id == "empty"),
            ranked_scores=adjusted,
        )
        self.assertEqual(repaired.sense_id, "marry")


if __name__ == "__main__":
    unittest.main()
