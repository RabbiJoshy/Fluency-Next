"""v6 additions: multiword candidates and the commit role.

Two properties matter more than the features themselves.

First, **defaults must not move any pick.** v6 is a reorganisation, so a profile
that enables nothing has to behave exactly as before. The commit thresholds
default to zero and multiword candidates default to off.

Second, **a multiword sense must be indistinguishable from a menu leaf to the
scorer and completely distinguishable to an auditor.** If the scorer could tell
them apart the competition would be measuring the rendering rather than the
meaning; if the auditor could not, an inventory extension would masquerade as a
provider sense.
"""

from __future__ import annotations

import unittest

from fluency.wsd.commit import CommitPolicy, axis_margins, decide, published_fields
from fluency.wsd.contracts import DECISION_ORDER, DECISION_STAGES
from fluency.wsd.gloss_scoring import LeafScore
from fluency.wsd.languages.spanish import sense_compatible_bridged
from fluency.wsd.menus import MenuAnalysis, SenseLeaf, build_analysis_id
from fluency.wsd.multiword import (
    MULTIWORD_SOURCE_ADAPTER,
    index_multiword_senses,
    is_multiword_analysis,
    multiword_analyses,
)


CARD = "card_es_" + "a" * 32


def analysis(headword: str, pos: str, senses: tuple[tuple[str, str], ...]) -> MenuAnalysis:
    key = f"{headword}|{pos}"
    return MenuAnalysis(
        menu_analysis_id=build_analysis_id(
            card_id=CARD, source_adapter="spanishdict/v1", source_analysis_key=key
        ),
        card_id=CARD,
        surface_form="nuevo",
        headword=headword,
        part_of_speech=pos,
        source_adapter="spanishdict/v1",
        source_analysis_key=key,
        senses=tuple(
            SenseLeaf(
                sense_id=sense_id,
                translation=translation,
                definition="recently made",
                source_reference="spanishdict",
                provider_metadata={},
            )
            for sense_id, translation in senses
        ),
        provider_metadata={},
    )


NUEVO = (analysis("nuevo", "ADJ", (("n1", "new"), ("n2", "brand-new"))),)

INVENTORY = {
    "mwes": {
        "de nuevo": {
            "translations": ["again", "over again"],
            "attach_words": ["nuevo"],
            "corpus_freq": 9900,
            "sources": ["spanishdict", "wiktionary"],
            "id": "mwe_bbb",
        },
        "sin par": {
            "translations": ["unequalled"],
            "attach_words": ["par"],
            "corpus_freq": 0,
            "sources": ["wiktionary"],
            "id": "mwe_ccc",
        },
    }
}

SENTENCE = "Tengo miedo de perder el control de nuevo."


class MultiwordInventory(unittest.TestCase):
    def test_unattested_entries_are_never_indexed(self):
        # corpus_freq 0 means no sentence exists behind it, so it cannot be the
        # answer for an occurrence -- only reference content on a card.
        index = index_multiword_senses(INVENTORY)
        self.assertIn("nuevo", index)
        self.assertNotIn("par", index)

    def test_asking_for_unattested_candidates_is_refused(self):
        with self.assertRaises(ValueError):
            index_multiword_senses(INVENTORY, minimum_corpus_frequency=0)

    def test_candidate_only_when_the_expression_is_present(self):
        index = index_multiword_senses(INVENTORY)
        self.assertEqual(
            len(multiword_analyses(
                card_id=CARD, surface_form="nuevo", sentence=SENTENCE, index=index)),
            1,
        )
        self.assertEqual(
            multiword_analyses(
                card_id=CARD, surface_form="nuevo",
                sentence="Compré un coche nuevo.", index=index),
            (),
        )


class MultiwordIdentity(unittest.TestCase):
    def setUp(self):
        self.index = index_multiword_senses(INVENTORY)
        (self.analysis, self.entry, self.span), = multiword_analyses(
            card_id=CARD, surface_form="nuevo", sentence=SENTENCE, index=self.index
        )

    def test_it_lands_on_the_component_surface_card(self):
        self.assertEqual(self.analysis.card_id, CARD)
        self.assertEqual(self.analysis.surface_form, "nuevo")

    def test_its_analysis_id_cannot_collide_with_a_provider_analysis(self):
        provider_ids = {item.menu_analysis_id for item in NUEVO}
        self.assertNotIn(self.analysis.menu_analysis_id, provider_ids)
        self.assertEqual(self.analysis.source_adapter, MULTIWORD_SOURCE_ADAPTER)
        self.assertTrue(is_multiword_analysis(self.analysis))
        self.assertFalse(any(is_multiword_analysis(item) for item in NUEVO))

    def test_it_keeps_the_stable_inventory_id_as_its_sense_id(self):
        self.assertEqual(self.analysis.senses[0].sense_id, "mwe_bbb")

    def test_it_reports_its_span_in_the_sentence(self):
        start, end = self.span
        self.assertEqual(SENTENCE[start:end].casefold(), "de nuevo")

    def test_phrase_pos_is_orthogonal_so_no_special_case_is_needed(self):
        # The Spanish bridge exempts PHRASE, so an observed ADJ tag cannot
        # filter out a multiword candidate.
        self.assertTrue(sense_compatible_bridged("PHRASE", "ADJ"))
        self.assertTrue(sense_compatible_bridged("PHRASE", "AUX"))

    def test_it_renders_symmetrically_with_a_menu_leaf(self):
        # gloss_text is what the scorer sees. If these diverged in shape the
        # competition would measure the rendering, not the meaning.
        provider = NUEVO[0].senses[0].gloss_text
        multiword = self.analysis.senses[0].gloss_text
        for text in (provider, multiword):
            self.assertIn(" — ", text)
        self.assertEqual(multiword, "again — multiword expression")


class AuxBridge(unittest.TestCase):
    def test_verb_survives_an_aux_tag(self):
        # SpanishDict has no AUX category and files auxiliaries as VERB. Without
        # the bridge this rejected VERB *and* NOUN, so every analysis failed and
        # the filter silently became a no-op on haber/ser/estar/deber/saber.
        self.assertTrue(sense_compatible_bridged("VERB", "AUX"))
        self.assertFalse(sense_compatible_bridged("NOUN", "AUX"))


class Commit(unittest.TestCase):
    def scores(self, top=0.90, second=0.10):
        return (
            LeafScore(NUEVO[0].menu_analysis_id, "n1", top),
            LeafScore(NUEVO[0].menu_analysis_id, "n2", second),
        )

    def test_defaults_always_emit_a_leaf(self):
        decision = decide(self.scores(), NUEVO, CommitPolicy())
        self.assertEqual(decision.level, "leaf")
        self.assertEqual(decision.uncertain_axis, "none")
        self.assertFalse(decision.escalate)

    def test_defaults_are_not_enabled(self):
        self.assertFalse(CommitPolicy().enabled)
        self.assertTrue(CommitPolicy(glosskey_minimum=0.2).enabled)

    def test_a_weak_gloss_margin_publishes_less_without_escalating(self):
        decision = decide(self.scores(0.5, 0.5), NUEVO, CommitPolicy(leaf_minimum=0.9))
        self.assertEqual(decision.level, "glosskey")
        self.assertEqual(decision.uncertain_axis, "gloss")
        self.assertFalse(decision.escalate, "synonym confusion must not cost a model call")

    def test_a_weak_tuple_margin_escalates(self):
        # Two headwords in genuine contention -- the case that matters, because
        # a single-analysis menu has a tuple margin of exactly 1.0 and nothing
        # to be uncertain about.
        rival = analysis("nuevo", "NOUN", (("x1", "new one"),))
        candidates = (NUEVO[0], rival)
        scores = (
            LeafScore(NUEVO[0].menu_analysis_id, "n1", 0.50),
            LeafScore(NUEVO[0].menu_analysis_id, "n2", 0.10),
            LeafScore(rival.menu_analysis_id, "x1", 0.50),
        )
        decision = decide(scores, candidates, CommitPolicy(tuple_minimum=0.5))
        self.assertEqual(decision.uncertain_axis, "tuple")
        self.assertTrue(decision.escalate, "the wrong word is the unacceptable error")

    def test_a_confident_tuple_does_not_escalate(self):
        rival = analysis("nuevo", "NOUN", (("x1", "new one"),))
        scores = (
            LeafScore(NUEVO[0].menu_analysis_id, "n1", 0.95),
            LeafScore(NUEVO[0].menu_analysis_id, "n2", 0.10),
            LeafScore(rival.menu_analysis_id, "x1", 0.05),
        )
        decision = decide(scores, (NUEVO[0], rival), CommitPolicy(tuple_minimum=0.5))
        self.assertFalse(decision.escalate)

    def test_margins_never_move_the_selection(self):
        # Max aggregation reproduces the global argmax exactly, so margins add
        # confidence without changing any pick.
        margins = axis_margins(self.scores(), NUEVO)
        self.assertEqual(set(margins), {"leaf", "glosskey", "tuple"})
        self.assertGreater(margins["leaf"], 0.0)

    def test_a_single_candidate_has_no_margin_to_speak_of(self):
        solo = (analysis("nuevo", "ADJ", (("n1", "new"),)),)
        margins = axis_margins((LeafScore(solo[0].menu_analysis_id, "n1", 0.8),), solo)
        self.assertEqual(margins["tuple"], 1.0)

    def test_published_fields_narrow_but_never_change_the_answer(self):
        leaf = published_fields("leaf", NUEVO[0], "n1")
        glosskey = published_fields("glosskey", NUEVO[0], "n1")
        tuple_level = published_fields("tuple", NUEVO[0], "n1")
        self.assertEqual(leaf["translation"], glosskey["translation"])
        self.assertNotIn("definition", glosskey)
        self.assertNotIn("translation", tuple_level)
        for payload in (leaf, glosskey, tuple_level):
            self.assertEqual(payload["headword"], "nuevo")


class DecisionOrder(unittest.TestCase):
    def test_new_stages_exist_and_bracket_scoring(self):
        for stage in ("constrain", "multiword", "commit"):
            self.assertIn(stage, DECISION_STAGES)
        order = list(DECISION_ORDER)
        self.assertLess(order.index("multiword"), order.index("gloss"))
        self.assertGreater(order.index("commit"), order.index("gloss"))

    def test_the_v5_stage_names_still_validate(self):
        for stage in ("gloss", "token_tuple_vote", "leaf_repair", "calibration", "alignment"):
            self.assertIn(stage, DECISION_STAGES)


if __name__ == "__main__":
    unittest.main()


class MultiwordImportAdmission(unittest.TestCase):
    """A multiword selection is admitted only if its identity self-verifies.

    The importer's closed-menu rule is that a selected analysis must be in the
    card's provider menu. A multiword sense is a typed inventory extension and is
    legitimately absent from it, so the importer needs a second door -- and that
    door must not be openable with an arbitrary analysis ID.
    """

    def _assignment(self, *, analysis_id, expression, declared=True):
        from fluency.wsd.contracts import SelectedTuple, WSDAssignment

        evidence = {"selected_multiword": expression}
        if declared:
            evidence["multiword_candidates"] = [{
                "expression": expression,
                "expression_id": "mwe_bbb",
                "translation": "again",
                "inventory_content_id": "sha256:" + "a" * 64,
            }]
        return WSDAssignment(
            card_id=CARD,
            surface_form="nuevo",
            sentence_id="sentence_" + "d" * 32,
            status="assigned",
            sense_menu_content_id="sha256:" + "e" * 64,
            menu_analysis_id=analysis_id,
            selected_sense_id="mwe_bbb",
            selected_tuple=SelectedTuple(headword=expression, part_of_speech="PHRASE"),
            decision_path=("multiword", "gloss"),
            evidence=evidence,
            confidence=None,
            model_revisions={"gloss": "gemini-embedding-001"},
        )

    def test_a_genuine_multiword_selection_is_admitted(self):
        from fluency.wsd.importer import _validated_multiword_analysis
        from fluency.wsd.menus import build_analysis_id
        from fluency.wsd.multiword import MULTIWORD_SOURCE_ADAPTER

        analysis_id = build_analysis_id(
            card_id=CARD,
            source_adapter=MULTIWORD_SOURCE_ADAPTER,
            source_analysis_key="de nuevo",
        )
        result = _validated_multiword_analysis(
            self._assignment(analysis_id=analysis_id, expression="de nuevo"), "pair"
        )
        self.assertEqual(result[0], "de nuevo")
        self.assertEqual(result[1], "PHRASE")

    def test_a_forged_analysis_id_is_refused(self):
        from fluency.wsd.importer import WSDAssignmentImportError, _validated_multiword_analysis

        forged = "analysis_" + "f" * 32
        with self.assertRaises(WSDAssignmentImportError):
            _validated_multiword_analysis(
                self._assignment(analysis_id=forged, expression="de nuevo"), "pair"
            )

    def test_an_undeclared_expression_is_refused(self):
        from fluency.wsd.importer import WSDAssignmentImportError, _validated_multiword_analysis
        from fluency.wsd.menus import build_analysis_id
        from fluency.wsd.multiword import MULTIWORD_SOURCE_ADAPTER

        analysis_id = build_analysis_id(
            card_id=CARD,
            source_adapter=MULTIWORD_SOURCE_ADAPTER,
            source_analysis_key="de nuevo",
        )
        with self.assertRaises(WSDAssignmentImportError):
            _validated_multiword_analysis(
                self._assignment(
                    analysis_id=analysis_id, expression="de nuevo", declared=False
                ),
                "pair",
            )

    def test_an_ordinary_assignment_is_not_treated_as_multiword(self):
        from fluency.wsd.contracts import SelectedTuple, WSDAssignment
        from fluency.wsd.importer import _validated_multiword_analysis

        ordinary = WSDAssignment(
            card_id=CARD, surface_form="nuevo", sentence_id="sentence_" + "d" * 32,
            status="assigned", sense_menu_content_id="sha256:" + "e" * 64,
            menu_analysis_id=NUEVO[0].menu_analysis_id, selected_sense_id="n1",
            selected_tuple=SelectedTuple(headword="nuevo", part_of_speech="ADJ"),
            decision_path=("gloss",), evidence={"selected_multiword": None},
            confidence=None, model_revisions={"gloss": "gemini-embedding-001"},
        )
        self.assertIsNone(_validated_multiword_analysis(ordinary, "pair"))

    def test_a_sense_id_that_is_not_the_inventory_entry_is_refused(self):
        from fluency.wsd.importer import WSDAssignmentImportError, _validated_multiword_analysis
        from fluency.wsd.menus import build_analysis_id
        from fluency.wsd.multiword import MULTIWORD_SOURCE_ADAPTER

        assignment = self._assignment(
            analysis_id=build_analysis_id(
                card_id=CARD, source_adapter=MULTIWORD_SOURCE_ADAPTER,
                source_analysis_key="de nuevo",
            ),
            expression="de nuevo",
        )
        assignment.evidence["multiword_candidates"][0]["expression_id"] = "mwe_other"
        with self.assertRaises(WSDAssignmentImportError):
            _validated_multiword_analysis(assignment, "pair")

    def test_an_unpinned_inventory_is_refused(self):
        from fluency.wsd.importer import WSDAssignmentImportError, _validated_multiword_analysis
        from fluency.wsd.menus import build_analysis_id
        from fluency.wsd.multiword import MULTIWORD_SOURCE_ADAPTER

        assignment = self._assignment(
            analysis_id=build_analysis_id(
                card_id=CARD, source_adapter=MULTIWORD_SOURCE_ADAPTER,
                source_analysis_key="de nuevo",
            ),
            expression="de nuevo",
        )
        del assignment.evidence["multiword_candidates"][0]["inventory_content_id"]
        with self.assertRaises(WSDAssignmentImportError):
            _validated_multiword_analysis(assignment, "pair")

    def test_a_selection_with_no_renderable_translation_is_refused(self):
        from fluency.wsd.importer import WSDAssignmentImportError, _validated_multiword_analysis
        from fluency.wsd.menus import build_analysis_id
        from fluency.wsd.multiword import MULTIWORD_SOURCE_ADAPTER

        assignment = self._assignment(
            analysis_id=build_analysis_id(
                card_id=CARD, source_adapter=MULTIWORD_SOURCE_ADAPTER,
                source_analysis_key="de nuevo",
            ),
            expression="de nuevo",
        )
        assignment.evidence["multiword_candidates"][0]["translation"] = "  "
        with self.assertRaises(WSDAssignmentImportError):
            _validated_multiword_analysis(assignment, "pair")
