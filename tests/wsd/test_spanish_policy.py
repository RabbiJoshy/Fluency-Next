import unittest
from dataclasses import replace

from fluency.core.identity import create_card_record
from fluency.features import SpecialistFeature
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

    def test_tagset_bridge_preserves_spanishdict_contractions_for_adpositions(self):
        self.assertTrue(sense_compatible_bridged("CONTRACTION", "ADP"))
        self.assertTrue(sense_compatible_bridged("ADP", "ADP"))

    def test_se_only_gate_is_conservative(self):
        self.assertTrue(se_reflexive_evidence("casa", "Se casa hoy"))
        self.assertFalse(se_reflexive_evidence("casa", "Casa a la pareja"))
        self.assertIsNone(se_reflexive_evidence("casa", "Me casa hoy"))
        self.assertTrue(se_reflexive_evidence("diviértanse", "Diviértanse mucho"))
        self.assertFalse(se_reflexive_evidence("pensé", "Nunca pensé sobre ella"))
        self.assertFalse(
            se_reflexive_evidence(
                "quise", "No quise decir eso", {"mood": "indicative"}
            )
        )
        self.assertFalse(se_reflexive_evidence("diga", "Que se lo diga"))
        self.assertFalse(se_reflexive_evidence("tuvo", "Se tuvo que ir"))

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

    def test_non_spanish_profile_can_disable_the_legacy_se_gate(self):
        prepared = SpanishV5CandidatePolicy(
            constraint_mode="filter", clitic_gate=False
        ).prepare(
            sentence="Se casa hoje", surface_form="casa", observed_pos="VERB",
            analyses=(self.verb, self.reflexive),
        )
        self.assertEqual(prepared.analyses, (self.verb, self.reflexive))
        self.assertIsNone(prepared.evidence["se_reflexive_evidence"])

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

    def test_normalized_grammar_and_companion_features_filter_leaves(self):
        plain, needs_de = self.verb.senses
        marked = replace(
            self.verb,
            senses=(
                replace(
                    plain,
                    specialist_features=(
                        SpecialistFeature(
                            "grammar", "sense_mark", "mood=indicative", "indicative"
                        ),
                    ),
                ),
                replace(
                    needs_de,
                    translation="to marry off",
                    specialist_features=(
                        SpecialistFeature("companion", "required_word", "de", "de"),
                    ),
                ),
            ),
        )
        prepared = SpanishV5CandidatePolicy(
            constraint_mode="filter", normalized_leaf_gates=True
        ).prepare(
            sentence="Casa a la pareja",
            surface_form="casa",
            observed_pos="VERB",
            observed_grammar={"mood": "subjunctive"},
            analyses=(marked,),
        )

        self.assertEqual(len(prepared.analyses[0].senses), 1)
        # The companion leaf is rejected first; rejecting the remaining grammar
        # leaf would empty the set, so the conservative grammar gate declines.
        self.assertEqual(prepared.analyses[0].senses[0].sense_id, "marry")
        self.assertEqual(
            prepared.evidence["companion_rejected_leaf_refs"][0]["sense_id"],
            "empty",
        )

    def test_normalized_grammar_filters_when_a_compatible_sibling_survives(self):
        first, second = self.verb.senses
        marked = replace(
            self.verb,
            senses=(
                replace(
                    first,
                    specialist_features=(
                        SpecialistFeature(
                            "grammar", "sense_mark", "mood=indicative", "indicative"
                        ),
                    ),
                ),
                replace(
                    second,
                    translation="to wed",
                    specialist_features=(
                        SpecialistFeature(
                            "grammar", "sense_mark", "mood=subjunctive", "subjunctive"
                        ),
                    ),
                ),
            ),
        )
        prepared = SpanishV5CandidatePolicy(
            constraint_mode="filter", normalized_leaf_gates=True
        ).prepare(
            sentence="Quizá se case",
            surface_form="case",
            observed_pos="VERB",
            observed_grammar={"mood": "subjunctive"},
            analyses=(marked,),
        )

        self.assertEqual(
            [sense.sense_id for sense in prepared.analyses[0].senses],
            ["empty"],
        )
        self.assertEqual(
            prepared.evidence["grammar_rejected_leaf_refs"][0]["sense_id"],
            "marry",
        )

    def test_unvalidated_normalized_leaf_gates_are_evidence_only_by_default(self):
        plain, needs_de = self.verb.senses
        marked = replace(
            self.verb,
            senses=(
                plain,
                replace(
                    needs_de,
                    specialist_features=(
                        SpecialistFeature("companion", "required_word", "de", "de"),
                    ),
                ),
            ),
        )
        prepared = SpanishV5CandidatePolicy(constraint_mode="filter").prepare(
            sentence="Casa a la pareja",
            surface_form="casa",
            observed_pos="VERB",
            analyses=(marked,),
        )

        self.assertEqual(prepared.analyses, (marked,))
        self.assertEqual(
            prepared.evidence["normalized_leaf_gate_policy"], "evidence_only"
        )
        self.assertEqual(
            prepared.evidence["companion_rejected_leaf_refs"][0]["sense_id"],
            "empty",
        )

if __name__ == "__main__":
    unittest.main()
