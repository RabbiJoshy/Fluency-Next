"""A subtitle row is a slice of a stream, not a sentence.

A row can begin partway through one sentence and end partway through the next.
Both leave a fragment that reads as broken language rather than as an example.
Measured on the shipped decks: 3.4% of Czech displayed examples began lowercase
and 0.7% ended on a comma; Portuguese 0.4% and 0.3%.
"""

import json
from pathlib import Path
import unittest

from fluency.harvest.matching import SurfaceMatcher, quality_rejection

ROOT = Path(__file__).resolve().parents[2]
SHARED = json.loads((ROOT / "config/harvest/shared/speech-v1.json").read_text())
CS = json.loads((ROOT / "config/harvest/languages/cs-v1.json").read_text())
PT = json.loads((ROOT / "config/harvest/languages/pt-v1.json").read_text())
TRANSLATION = "a translation long enough to clear every ratio gate in the policy"


def reject(sentence, policy=None, language=CS):
    matcher = SurfaceMatcher([{"card_id": "c", "display_form": "to"}], language)
    return quality_rejection(
        sentence, TRANSLATION, matcher=matcher, shared_policy=policy or SHARED
    )


class FragmentTests(unittest.TestCase):
    def test_a_row_beginning_mid_sentence_is_rejected(self) -> None:
        self.assertEqual(reject("- zůstal přes noc a pak se vrátil."), "starts_mid_sentence")

    def test_a_row_stopping_mid_clause_is_rejected(self) -> None:
        self.assertEqual(
            reject("Takže slyšel jsem, že jdeš zpět do svého starého života,"),
            "ends_mid_sentence",
        )

    def test_an_opening_quote_or_bracket_does_not_count_as_lowercase(self) -> None:
        """The first letter is what matters, not the punctuation before it."""

        self.assertIsNone(reject('"Ale to je jedno," řekl mi tehdy Pavel.'))
        self.assertIsNone(reject("(Ale co budeme dělat teď a zítra?)"))

    def test_ordinary_sentences_survive(self) -> None:
        for text in ("Je to náš dům a mně se to líbí.",
                     "Bez vody by na Zemi nemohlo nic žít."):
            with self.subTest(text=text):
                self.assertIsNone(reject(text))

    def test_a_terminated_sentence_is_not_a_fragment(self) -> None:
        self.assertIsNone(reject("Myslím, že jsi ušel pořádný kus cesty."))


class DeclaredNotHardcodedTests(unittest.TestCase):
    def test_each_rule_is_off_when_its_key_is_absent(self) -> None:
        policy = json.loads(json.dumps(SHARED))
        policy["quality"]["reject_lowercase_start"] = False
        policy["quality"]["reject_unterminated"] = False
        self.assertIsNone(reject("- zůstal přes noc a pak se vrátil.", policy))
        self.assertIsNone(
            reject("Takže slyšel jsem, že jdeš zpět do svého starého života,", policy)
        )

    def test_the_rules_are_language_agnostic(self) -> None:
        """Same defect, different language: the corpus shape causes it, not Czech."""

        self.assertEqual(
            reject("- e depois voltou para casa dele.", language=PT),
            "starts_mid_sentence",
        )


if __name__ == "__main__":
    unittest.main()
