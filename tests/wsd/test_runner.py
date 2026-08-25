import unittest

from fluency.core.hashing import content_id
from fluency.core.identity import create_card_record
from fluency.harvest.records import build_sentence_id
from fluency.wsd.alignment import AlignmentCorrection
from fluency.wsd.contracts import WSDAssignment
from fluency.wsd.disposition import DispositionPolicy
from fluency.wsd.gloss_scoring import LeafScore
from fluency.wsd.languages.french import FrenchWSDAdapter
from fluency.wsd.menus import MenuAnalysis, SenseLeaf, build_analysis_id
from fluency.wsd.multiword import index_multiword_senses
from fluency.wsd.runner import (
    ClosedMenuWSDRunner,
    WSDComponents,
    WSDConfigurationError,
    WSDExecutionProfile,
    WSDRequest,
)
from fluency.wsd.token_prototypes import TupleVote


class FakeGloss:
    model_revision = "fixture-gloss@abc123"

    def __init__(self, scores):
        self.scores = scores

    def score(self, sentence, analyses):
        return self.scores


class CountingMultiwordGloss:
    """Score provider and synthetic candidates in the one supplied pass."""

    model_revision = "fixture-gloss@dual-projection"

    def __init__(self):
        self.calls = 0

    def score(self, sentence, analyses):
        self.calls += 1
        scores = []
        for analysis in analyses:
            for sense in analysis.senses:
                value = {
                    "want": 0.80,
                    "try": 0.40,
                    "vow": 0.30,
                    "mwe-je-veux": 0.95,
                }[sense.sense_id]
                scores.append(LeafScore(analysis.menu_analysis_id, sense.sense_id, value))
        return tuple(scores)


class FakeReranker:
    model_revision = "fixture-token@abc123"
    prototype_content_id = content_id(b"prototypes")

    def __init__(self, analysis_id):
        self.analysis_id = analysis_id

    def vote(self, sentence, surface_form, analyses):
        return TupleVote(self.analysis_id, 0.81, 0.70)


class FakeCalibrator:
    model_revision = "fixture-calibrator@abc123"
    feature_version = "fixture-features/v1"

    def predict(self, **kwargs):
        return 0.9


class LowFakeCalibrator(FakeCalibrator):
    def predict(self, **kwargs):
        return 0.1


class FakeAligner:
    model_revision = "fixture-aligner@abc123"

    def __init__(self, analysis_id, sense_id):
        self.analysis_id = analysis_id
        self.sense_id = sense_id

    def correct(self, **kwargs):
        return AlignmentCorrection(
            menu_analysis_id=self.analysis_id,
            sense_id=self.sense_id,
            aligned_target="veux",
            aligned_translation="want",
        )


def make_analysis(card_id, source_key, headword, senses):
    return MenuAnalysis(
        menu_analysis_id=build_analysis_id(
            card_id=card_id,
            source_adapter="wiktionary-sense-menu/v1",
            source_analysis_key=source_key,
        ),
        card_id=card_id,
        surface_form="veux",
        headword=headword,
        part_of_speech="verb",
        source_adapter="wiktionary-sense-menu/v1",
        source_analysis_key=source_key,
        senses=tuple(
            SenseLeaf(sense_id, translation, definition, f"kaikki:{sense_id}", {})
            for sense_id, translation, definition in senses
        ),
        provider_metadata={},
    )


class WSDRunnerTests(unittest.TestCase):
    def setUp(self):
        self.card = create_card_record("fr", "veux")
        self.want = make_analysis(
            self.card.card_id,
            "vouloir:verb",
            "vouloir",
            (("want", "to want", "desire"), ("try", "to try", "attempt")),
        )
        self.vow = make_analysis(
            self.card.card_id,
            "vouer:verb",
            "vouer",
            (("vow", "to vow", "dedicate"),),
        )
        self.sentence_id = build_sentence_id(
            adapter="fixture/v1",
            snapshot_content_id=content_id(b"snapshot"),
            source_record_id="line-1",
            target_text="Je veux partir.",
            translation_text="I want to leave.",
        )
        self.request = WSDRequest(
            card_id=self.card.card_id,
            surface_form="veux",
            sentence_id=self.sentence_id,
            sentence="Je veux partir.",
            translation="I want to leave.",
            sense_menu_content_id=content_id(b"menu"),
            analyses=(self.want, self.vow),
        )
        self.scores = (
            LeafScore(self.want.menu_analysis_id, "want", 0.70),
            LeafScore(self.want.menu_analysis_id, "try", 0.60),
            LeafScore(self.vow.menu_analysis_id, "vow", 0.72),
        )

    def test_enabled_component_is_required_instead_of_silently_skipped(self):
        profile = WSDExecutionProfile(
            token_tuple_vote=False,
            tuple_vote_minimum_margin=0.02,
            calibration=False,
            alignment=True,
            generative_escalation=False,
            disposition=DispositionPolicy(None, "retain"),
        )
        with self.assertRaises(WSDConfigurationError):
            ClosedMenuWSDRunner(
                profile,
                WSDComponents(FrenchWSDAdapter(), FakeGloss(self.scores)),
            )

    def test_tuple_vote_selects_exact_analysis_and_leaf_inside_it(self):
        profile = WSDExecutionProfile(
            token_tuple_vote=True,
            tuple_vote_minimum_margin=0.02,
            calibration=True,
            alignment=False,
            generative_escalation=False,
            disposition=DispositionPolicy(0.5, "reject"),
        )
        runner = ClosedMenuWSDRunner(
            profile,
            WSDComponents(
                FrenchWSDAdapter(),
                FakeGloss(self.scores),
                token_reranker=FakeReranker(self.want.menu_analysis_id),
                calibrator=FakeCalibrator(),
            ),
        )
        assignment = runner.assign(self.request)
        self.assertEqual(assignment.status, "assigned")
        self.assertEqual(assignment.menu_analysis_id, self.want.menu_analysis_id)
        self.assertEqual(assignment.selected_sense_id, "want")
        self.assertEqual(
            assignment.decision_path,
            ("gloss", "token_tuple_vote", "calibration"),
        )

    def test_alignment_correction_clears_unrelated_calibrated_confidence(self):
        profile = WSDExecutionProfile(
            token_tuple_vote=False,
            tuple_vote_minimum_margin=0.02,
            calibration=True,
            alignment=True,
            generative_escalation=False,
            disposition=DispositionPolicy(0.5, "reject"),
        )
        runner = ClosedMenuWSDRunner(
            profile,
            WSDComponents(
                FrenchWSDAdapter(),
                FakeGloss(self.scores),
                calibrator=FakeCalibrator(),
                aligner=FakeAligner(self.want.menu_analysis_id, "want"),
            ),
        )
        assignment = runner.assign(self.request)
        self.assertEqual(assignment.selected_sense_id, "want")
        self.assertIsNone(assignment.confidence)
        self.assertEqual(assignment.decision_path[-1], "alignment")

    def test_multiword_and_provider_projections_share_one_scoring_pass(self):
        gloss = CountingMultiwordGloss()
        multiword_index = index_multiword_senses(
            {
                "mwes": {
                    "je veux": {
                        "translations": ["I want"],
                        "attach_words": ["veux"],
                        "corpus_freq": 12,
                        "sources": ["fixture"],
                        "id": "mwe-je-veux",
                    }
                }
            }
        )
        profile = WSDExecutionProfile(
            token_tuple_vote=False,
            tuple_vote_minimum_margin=0.0,
            calibration=False,
            alignment=False,
            generative_escalation=False,
            disposition=DispositionPolicy(None, "retain"),
            multiword_candidates=True,
        )
        runner = ClosedMenuWSDRunner(
            profile,
            WSDComponents(
                FrenchWSDAdapter(),
                gloss,
                multiword_index=multiword_index,
                multiword_inventory_content_id=content_id(b"multiword inventory"),
            ),
        )

        assignment = runner.assign(self.request)

        self.assertEqual(gloss.calls, 1)
        self.assertEqual(assignment.active_selection_projection, "provider_only")
        self.assertEqual(assignment.selected_sense_id, "want")
        provider = assignment.selection_projections["provider_only"]
        augmented = assignment.selection_projections["mwe_augmented"]
        self.assertEqual(provider.source_kind, "provider")
        self.assertEqual(provider.selected_sense_id, "want")
        self.assertEqual(provider.rank, 2)
        self.assertAlmostEqual(provider.selected_score, 0.80)
        self.assertAlmostEqual(provider.runner_up_score, 0.40)
        self.assertAlmostEqual(provider.raw_margin, 0.40)
        self.assertEqual(augmented.source_kind, "multiword")
        self.assertEqual(augmented.selected_sense_id, "mwe-je-veux")
        self.assertEqual(augmented.rank, 1)
        self.assertAlmostEqual(augmented.selected_score, 0.95)
        self.assertAlmostEqual(augmented.runner_up_score, 0.80)
        self.assertAlmostEqual(augmented.raw_margin, 0.15)
        candidate, = assignment.evidence["multiword_candidates"]
        self.assertEqual(candidate["augmented_rank"], 1)
        self.assertAlmostEqual(candidate["score"], 0.95)
        self.assertAlmostEqual(candidate["margin_over_provider_winner"], 0.15)
        self.assertEqual(
            WSDAssignment.from_dict(assignment.to_dict()).selection_projections,
            assignment.selection_projections,
        )

    def test_persisted_span_can_bind_an_elided_observed_form_to_canonical_surface(self):
        request = WSDRequest(
            card_id=self.card.card_id,
            surface_form="veux",
            sentence_id=self.sentence_id,
            sentence="Je v' partir.",
            translation="I want to leave.",
            sense_menu_content_id=content_id(b"menu"),
            analyses=(self.want, self.vow),
            target_span=(3, 4),
            target_observed_form="v",
        )
        profile = WSDExecutionProfile(
            token_tuple_vote=False,
            tuple_vote_minimum_margin=0.0,
            calibration=False,
            alignment=False,
            generative_escalation=False,
            disposition=DispositionPolicy(None, "retain"),
        )
        runner = ClosedMenuWSDRunner(
            profile,
            WSDComponents(FrenchWSDAdapter(), FakeGloss(self.scores)),
        )

        assignment = runner.assign(request)

        self.assertEqual(assignment.status, "assigned")
        self.assertEqual(
            assignment.evidence["target_occurrences"],
            [{"start": 3, "end": 4, "observed_text": "v"}],
        )

    def test_persisted_span_rejects_a_mismatched_observed_form(self):
        request = WSDRequest(
            card_id=self.card.card_id,
            surface_form="veux",
            sentence_id=self.sentence_id,
            sentence="Je v' partir.",
            translation="I want to leave.",
            sense_menu_content_id=content_id(b"menu"),
            analyses=(self.want, self.vow),
            target_span=(3, 4),
            target_observed_form="x",
        )
        profile = WSDExecutionProfile(
            token_tuple_vote=False,
            tuple_vote_minimum_margin=0.0,
            calibration=False,
            alignment=False,
            generative_escalation=False,
            disposition=DispositionPolicy(None, "retain"),
        )
        runner = ClosedMenuWSDRunner(
            profile,
            WSDComponents(FrenchWSDAdapter(), FakeGloss(self.scores)),
        )

        with self.assertRaisesRegex(ValueError, "persisted observed form"):
            runner.assign(request)

    def test_weak_disposition_retains_the_forced_exact_decision(self):
        profile = WSDExecutionProfile(
            token_tuple_vote=False,
            tuple_vote_minimum_margin=0.02,
            calibration=True,
            alignment=False,
            generative_escalation=False,
            disposition=DispositionPolicy(0.5, "reject"),
        )
        runner = ClosedMenuWSDRunner(
            profile,
            WSDComponents(
                FrenchWSDAdapter(),
                FakeGloss(self.scores),
                calibrator=LowFakeCalibrator(),
            ),
        )

        assignment = runner.assign(self.request)
        self.assertEqual(assignment.status, "assigned")
        self.assertEqual(assignment.menu_analysis_id, self.vow.menu_analysis_id)
        self.assertEqual(assignment.selected_sense_id, "vow")
        self.assertEqual(
            assignment.evidence["disposition"]["recommended_publication_status"],
            "rejected",
        )

    def test_raw_axis_margins_are_not_reported_as_confidence(self):
        profile = WSDExecutionProfile(
            token_tuple_vote=False,
            tuple_vote_minimum_margin=0.02,
            calibration=True,
            alignment=False,
            generative_escalation=False,
            disposition=DispositionPolicy(None, "retain"),
        )
        runner = ClosedMenuWSDRunner(
            profile,
            WSDComponents(
                FrenchWSDAdapter(),
                FakeGloss(self.scores),
                calibrator=FakeCalibrator(),
            ),
        )

        assignment = runner.assign(self.request)
        commit = assignment.evidence["commit"]
        self.assertEqual(assignment.confidence, 0.9)
        self.assertEqual(set(commit["raw_axis_margins"]), {"leaf", "glosskey", "tuple"})
        self.assertEqual(
            commit["axis_confidences"],
            {"leaf": None, "glosskey": None, "tuple": None},
        )
        self.assertNotIn("confidence", commit["raw_axis_margins"])


if __name__ == "__main__":
    unittest.main()
