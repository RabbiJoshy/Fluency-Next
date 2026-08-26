"""The companion note is one concept with two encodings.

SpanishDict writes it as prose inside `context` ("used with \\"de\\""), Wiktionary
as a structured +obj template. 587 senses carry one in SpanishDict, 632 in
Portuguese Wiktionary, with near-identical companion distributions. Reading it as
a feature of either provider is what an adapter exists to prevent.
"""

import unittest

from fluency.features.contract import SpecialistFeature
from fluency.features.spanishdict import extract as spanishdict_extract
from fluency.features.wiktionary import extract as wiktionary_extract
from fluency.wsd.companion_gate import (
    companion_satisfied,
    filter_by_companion,
    required_companions,
)


def families(feats):
    return [(f.family, f.kind, f.value) for f in feats]


class BothProvidersEmitTheSameFamilyTests(unittest.TestCase):
    def test_spanishdict_prose_becomes_a_companion(self) -> None:
        got = spanishdict_extract({"context": 'to remove; used with "de"'})
        self.assertIn(("companion", "required_word", "de"), families(got))

    def test_wiktionary_template_becomes_the_same_family(self) -> None:
        sense = {"info_templates": [{
            "name": "+obj",
            "extra_data": {"words": ["com", "'with", "something'"]},
            "expansion": "[with com 'with something']",
        }]}
        self.assertIn(("companion", "required_word", "com"), families(wiktionary_extract(sense)))

    def test_the_two_providers_agree_on_shape(self) -> None:
        """A gate must not be able to tell which dictionary it is reading."""

        sd = [f for f in spanishdict_extract({"context": 'used with "con"'}) if f.family == "companion"]
        wk = [f for f in wiktionary_extract({"info_templates": [
            {"name": "+obj", "extra_data": {"words": ["con"]}, "expansion": "[with con]"}
        ]}) if f.family == "companion"]
        self.assertEqual(sd[0].family, wk[0].family)
        self.assertEqual(sd[0].kind, wk[0].kind)
        self.assertEqual(sd[0].value, wk[0].value)

    def test_a_grammatical_form_is_not_a_companion_word(self) -> None:
        """`used with an infinitive` names a form; there is no word to look for."""

        got = families(spanishdict_extract({"context": "used with an infinitive"}))
        self.assertEqual(got[0][0], "construction")

    def test_wiktionary_form_notes_are_construction_too(self) -> None:
        sense = {"info_templates": [{"name": "+obj", "expansion": "[with adjective]"}]}
        self.assertEqual(families(wiktionary_extract(sense))[0][0], "construction")


class GateTests(unittest.TestCase):
    DE = [SpecialistFeature("companion", "required_word", "de", "de")]

    def test_present_companion_is_satisfied(self) -> None:
        self.assertTrue(companion_satisfied(self.DE, "Vou afastar-me de aqui"))

    def test_absent_companion_is_not(self) -> None:
        self.assertFalse(companion_satisfied(self.DE, "Vou embora agora"))

    def test_no_declared_companion_is_not_a_failed_one(self) -> None:
        self.assertTrue(companion_satisfied([], "qualquer frase"))

    def test_matching_is_whole_word(self) -> None:
        """`de` must not be satisfied by `desde` or `cidade`."""

        self.assertFalse(companion_satisfied(self.DE, "Vim desde a cidade"))

    def test_accents_and_case_do_not_break_matching(self) -> None:
        feature = [SpecialistFeature("companion", "required_word", "à", "à")]
        self.assertTrue(companion_satisfied(feature, "Vou À praia"))

    def test_the_gate_never_empties_the_candidate_set(self) -> None:
        """An empty set is what turned the POS filter into a silent no-op."""

        only = [("a", self.DE)]
        kept, rejected = filter_by_companion(only, "sem nada", features_of=lambda c: c[1])
        self.assertEqual(kept, only)
        self.assertEqual(rejected, ())

    def test_it_rejects_when_something_survives(self) -> None:
        candidates = [("needs-de", self.DE), ("free", [])]
        kept, rejected = filter_by_companion(candidates, "sem nada", features_of=lambda c: c[1])
        self.assertEqual([c[0] for c in kept], ["free"])
        self.assertEqual([c[0] for c in rejected], ["needs-de"])

    def test_duplicate_companions_are_collapsed(self) -> None:
        doubled = [
            SpecialistFeature("companion", "required_word", "de", "de"),
            SpecialistFeature("companion", "required_word", "de", "de"),
        ]
        self.assertEqual(required_companions(doubled), ("de",))


if __name__ == "__main__":
    unittest.main()
