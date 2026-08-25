import unittest

from fluency.core.identity import create_card_record
from fluency.wsd.disposition import DispositionPolicy
from fluency.wsd.features import SpecialistFeature
from fluency.wsd.languages.french import FrenchWSDAdapter
from fluency.wsd.menus import MenuAnalysis, SenseLeaf, build_analysis_id
from fluency.wsd.representations import RepresentationRef, plan_representations
from fluency.wsd.runner import (
    ClosedMenuWSDRunner,
    WSDComponents,
    WSDConfigurationError,
    WSDExecutionProfile,
)
from fluency.wsd.specialists import (
    CandidateRef,
    SpecialistAssessment,
    build_case,
    run_specialists,
)


def analysis() -> MenuAnalysis:
    card = create_card_record("fr", "suis")
    adapter = "wiktionary-sense-menu/v1"
    source_key = "être:verb"
    return MenuAnalysis(
        menu_analysis_id=build_analysis_id(
            card_id=card.card_id,
            source_adapter=adapter,
            source_analysis_key=source_key,
        ),
        card_id=card.card_id,
        surface_form="suis",
        headword="être",
        part_of_speech="verb",
        source_adapter=adapter,
        source_analysis_key=source_key,
        senses=(
            SenseLeaf(
                "medical",
                "to be under treatment",
                "medicine",
                "kaikki:medical",
                {"topics": ["medicine"]},
                (SpecialistFeature("domain", "topic", "medicine", "medicine"),),
            ),
            SenseLeaf(
                "clinical",
                "to receive care",
                "clinical",
                "kaikki:clinical",
                {"topics": ["medicine"]},
                (SpecialistFeature("domain", "topic", "medicine", "medicine"),),
            ),
            SenseLeaf("empty", "", "", "kaikki:empty", {}),
        ),
        provider_metadata={},
    )


class FixtureGloss:
    model_revision = "fixture-gloss/v1"

    def score(self, sentence, analyses):
        return ()


class ThreeWaySpecialist:
    specialist_id = "fixture-domain/v1"
    model_revision = "fixture-domain-model/v1"

    def assess(self, case, representations):
        first, second, third = (candidate.ref for candidate in case.candidates)
        required = RepresentationRef(
            first.menu_analysis_id,
            first.sense_id,
            "domain",
            "topic",
            "medicine",
        )
        representations[required]
        return (
            SpecialistAssessment(first, "support", 0.81, {"evidence_type": "domain"}),
            SpecialistAssessment(second, "reject", 0.72, {"evidence_type": "domain"}),
            SpecialistAssessment(third, "unknown", None, {"reason": "no_domain_tag"}),
        )


def profile(*, specialists: bool) -> WSDExecutionProfile:
    return WSDExecutionProfile(
        token_tuple_vote=False,
        tuple_vote_minimum_margin=0.0,
        calibration=False,
        alignment=False,
        generative_escalation=False,
        disposition=DispositionPolicy(None, "retain"),
        specialists=specialists,
    )


class RepresentationPlannerTests(unittest.TestCase):
    def test_full_gloss_is_dense_sparse_channels_are_tagged_and_texts_deduplicate(self):
        plan = plan_representations((analysis(),))
        full = [item for item in plan.requests if item.ref.channel == "full_gloss"]
        domains = [item for item in plan.requests if item.ref.channel == "domain"]

        self.assertEqual({item.ref.sense_id for item in full}, {"medical", "clinical"})
        self.assertEqual({item.ref.sense_id for item in domains}, {"medical", "clinical"})
        self.assertEqual([item.text for item in domains], ["medicine", "medicine"])
        self.assertEqual(plan.unique_texts.count("medicine"), 1)
        self.assertEqual(
            [(item.sense_id, item.channel, item.reason) for item in plan.unavailable],
            [("empty", "full_gloss", "empty_gloss")],
        )


class SpecialistContractTests(unittest.TestCase):
    def setUp(self):
        self.analysis = analysis()
        self.case = build_case(
            language="fr",
            sentence="Je suis ici.",
            target_span=(3, 7),
            surface_form="suis",
            observed_pos="AUX",
            analyses=(self.analysis,),
        )
        first = self.case.candidates[0].ref
        self.domain_ref = RepresentationRef(
            first.menu_analysis_id,
            first.sense_id,
            "domain",
            "topic",
            "medicine",
        )

    def test_support_reject_and_unknown_are_serialized_as_evidence_only(self):
        records = run_specialists(
            (ThreeWaySpecialist(),), self.case, {self.domain_ref: object()}
        )
        self.assertEqual(records[0]["policy"], "evidence_only")
        self.assertEqual(
            [item["assessment"] for item in records[0]["assessments"]],
            ["support", "reject", "unknown"],
        )

    def test_unknown_cannot_claim_confidence_and_decisions_require_it(self):
        candidate = CandidateRef("analysis_" + "a" * 32, "sense")
        with self.assertRaises(ValueError):
            SpecialistAssessment(candidate, "unknown", 0.5, {})
        with self.assertRaises(ValueError):
            SpecialistAssessment(candidate, "support", None, {})

    def test_missing_required_sparse_representation_fails_closed(self):
        with self.assertRaises(KeyError):
            run_specialists((ThreeWaySpecialist(),), self.case, {})

    def test_a_specialist_cannot_assess_a_leaf_outside_the_case(self):
        outsider = CandidateRef("analysis_" + "f" * 32, "outsider")

        class InvalidSpecialist:
            specialist_id = "invalid/v1"
            model_revision = "invalid-model/v1"

            def assess(self, case, representations):
                return (SpecialistAssessment(outsider, "unknown", None, {}),)

        with self.assertRaises(ValueError):
            run_specialists((InvalidSpecialist(),), self.case, {})

    def test_runner_requires_specialist_components_to_match_the_exact_profile(self):
        specialist = ThreeWaySpecialist()
        with self.assertRaises(WSDConfigurationError):
            ClosedMenuWSDRunner(
                profile(specialists=True),
                WSDComponents(FrenchWSDAdapter(), FixtureGloss()),
            )
        with self.assertRaises(WSDConfigurationError):
            ClosedMenuWSDRunner(
                profile(specialists=False),
                WSDComponents(
                    FrenchWSDAdapter(),
                    FixtureGloss(),
                    specialists=(specialist,),
                    representations={self.domain_ref: object()},
                ),
            )


if __name__ == "__main__":
    unittest.main()
