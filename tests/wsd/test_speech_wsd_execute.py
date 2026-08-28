import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fluency.speech.wsd_execute import SPACY_POS_MODEL, occurrence_pos_tags


class FakeToken:
    def __init__(self, text, idx, pos):
        self.text = text
        self.idx = idx
        self.pos_ = pos


class FakeModel:
    def __init__(self, documents):
        self.documents = documents
        self.batch_sizes = []

    def pipe(self, texts, batch_size):
        self.batch_sizes.append(batch_size)
        for text in texts:
            yield self.documents[text]


def work_item(
    card_id,
    surface,
    sentence_id,
    sentence,
    *,
    target_span=None,
    target_observed_form=None,
):
    card = {"card_id": card_id, "display_form": surface}
    if target_span is not None:
        card["target_span"] = target_span
    if target_observed_form is not None:
        card["target_observed_form"] = target_observed_form
    return (
        card,
        {},
        sentence_id,
        sentence,
        "",
    )


class SpeechOccurrencePOSTests(unittest.TestCase):
    def test_unpinned_installed_model_revision_is_rejected(self):
        model = FakeModel({})
        model.meta = {"version": "9.9.9"}
        fake_spacy = SimpleNamespace(load=lambda _name: model)

        with patch.dict(sys.modules, {"spacy": fake_spacy}):
            with self.assertRaisesRegex(RuntimeError, "pinned revision"):
                occurrence_pos_tags(())

    def test_unique_occurrence_supplies_observed_pos_and_pinned_evidence(self):
        sentence = "Yo quiero ir."
        model = FakeModel(
            {
                sentence: (
                    FakeToken("Yo", 0, "PRON"),
                    FakeToken("quiero", 3, "VERB"),
                    FakeToken("ir", 10, "VERB"),
                )
            }
        )
        key = ("card_es_" + "a" * 32, "sentence_" + "1" * 32)

        observed, evidence = occurrence_pos_tags(
            (work_item(key[0], "quiero", key[1], sentence),), model=model
        )

        self.assertEqual(observed[key], "VERB")
        self.assertEqual(evidence[key]["status"], "observed")
        self.assertEqual(evidence[key]["occurrence_tags"], ["VERB"])
        self.assertEqual(evidence[key]["model_revision"], SPACY_POS_MODEL)
        self.assertEqual(model.batch_sizes, [1], "v7 pinned batch size 1; keep it the default")

    def test_repeated_occurrences_with_conflicting_pos_do_not_guess(self):
        sentence = "Como pan como siempre."
        model = FakeModel(
            {
                sentence: (
                    FakeToken("Como", 0, "SCONJ"),
                    FakeToken("pan", 5, "NOUN"),
                    FakeToken("como", 9, "VERB"),
                    FakeToken("siempre", 14, "ADV"),
                )
            }
        )
        key = ("card_es_" + "b" * 32, "sentence_" + "2" * 32)

        observed, evidence = occurrence_pos_tags(
            (work_item(key[0], "como", key[1], sentence),), model=model
        )

        self.assertIsNone(observed[key])
        self.assertEqual(evidence[key]["status"], "ambiguous_repeated_occurrence")
        self.assertEqual(evidence[key]["occurrence_tags"], ["SCONJ", "VERB"])

    def test_persisted_span_tags_an_elision_under_its_canonical_surface(self):
        sentence = "Voy pa' casa."
        model_sentence = "Voy para' casa."
        model = FakeModel(
            {
                model_sentence: (
                    FakeToken("Voy", 0, "AUX"),
                    FakeToken("para", 4, "ADP"),
                    FakeToken("casa", 10, "NOUN"),
                )
            }
        )
        key = ("card_es_" + "c" * 32, "sentence_" + "3" * 32)

        observed, evidence = occurrence_pos_tags(
            (
                work_item(
                    key[0],
                    "para",
                    key[1],
                    sentence,
                    target_span=(4, 6),
                    target_observed_form="pa",
                ),
            ),
            model=model,
        )

        self.assertEqual(observed[key], "ADP")
        self.assertEqual(evidence[key]["status"], "observed")
        self.assertEqual(evidence[key]["occurrence_tags"], ["ADP"])
        self.assertTrue(evidence[key]["canonicalized_target_for_model"])

    def test_apostrophe_elision_does_not_take_the_punctuation_pos(self):
        sentence = "'Toy lista."
        model_sentence = "estoy lista."
        model = FakeModel(
            {
                model_sentence: (
                    FakeToken("estoy", 0, "AUX"),
                    FakeToken("lista", 6, "ADJ"),
                )
            }
        )
        key = ("card_es_" + "d" * 32, "sentence_" + "4" * 32)

        observed, evidence = occurrence_pos_tags(
            (
                work_item(
                    key[0],
                    "estoy",
                    key[1],
                    sentence,
                    target_span=(0, 4),
                    target_observed_form="'Toy",
                ),
            ),
            model=model,
        )

        self.assertEqual(observed[key], "AUX")
        self.assertEqual(evidence[key]["occurrence_tags"], ["AUX"])
        self.assertTrue(evidence[key]["canonicalized_target_for_model"])


if __name__ == "__main__":
    unittest.main()
