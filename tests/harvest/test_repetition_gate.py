"""An example must show a word doing something.

Easiness counts how many UNFAMILIAR words a learner must get past, and skips the
target itself. So "Nao, nao, nao, nao, nao, nao" has zero unfamiliar words, six
tokens exactly meeting the preferred minimum, and therefore a perfect score of
0.0 -- it wins every ranking. On the first language to harvest raw OpenSubtitles
this filled entire candidate pools: all 60 candidates for `nao` were repetitions.

Repetition is a property of the sentence, not of any one card, so it is judged
before a card is known.
"""

import json
from pathlib import Path
import unittest

from fluency.harvest.matching import SurfaceMatcher, easiness_metrics, quality_rejection

ROOT = Path(__file__).resolve().parents[2]
SHARED = json.loads((ROOT / "config/harvest/shared/speech-v1.json").read_text())
PT = json.loads((ROOT / "config/harvest/languages/pt-v1.json").read_text())
TRANSLATION = "a translation long enough to pass the ratio gate"


def reject(sentence, translation=TRANSLATION):
    matcher = SurfaceMatcher([{"card_id": "c", "display_form": "não"}], PT)
    return quality_rejection(sentence, translation, matcher=matcher, shared_policy=SHARED)


class RepetitionGateTests(unittest.TestCase):
    def test_pure_repetition_is_rejected(self) -> None:
        self.assertEqual(reject("Não, não, não, não, não, não."),
                         "insufficient_distinct_tokens")

    def test_echoed_phrases_are_rejected(self) -> None:
        for sentence in ("Que bom, que bom, que bom!",
                         "A sério? A sério? A sério?",
                         "Um, dois, um, dois, um. Um, dois."):
            with self.subTest(sentence=sentence):
                self.assertEqual(reject(sentence), "insufficient_distinct_tokens")

    def test_natural_sentences_survive(self) -> None:
        for sentence in ("Não, isto é a minha casa.",
                         "O que estás a fazer na minha casa?",
                         "Bom, deixa-me tentar falar com ela."):
            with self.subTest(sentence=sentence):
                self.assertIsNone(reject(sentence))

    def test_one_repeated_word_is_still_allowed(self) -> None:
        """Repetition is normal; a sentence made only of it is not."""

        self.assertIsNone(reject("Não, não sei o que ela disse."))

    def test_the_threshold_is_declared_not_hardcoded(self) -> None:
        self.assertEqual(SHARED["quality"]["minimum_distinct_tokens"], 4)

    def test_a_language_declaring_no_threshold_keeps_everything(self) -> None:
        """Absence is declared, never inferred: zero means no gate."""

        policy = json.loads(json.dumps(SHARED))
        policy["quality"]["minimum_distinct_tokens"] = 0
        matcher = SurfaceMatcher([{"card_id": "c", "display_form": "não"}], PT)
        self.assertIsNone(quality_rejection(
            "Não, não, não, não, não, não.", TRANSLATION,
            matcher=matcher, shared_policy=policy))


class EasinessDegeneracyTests(unittest.TestCase):
    def test_pure_repetition_scores_perfectly(self) -> None:
        """The reason the gate is needed, pinned so it is not mistaken for a bug."""

        matcher = SurfaceMatcher([{"card_id": "c", "display_form": "não"}], PT)
        card = {"display_form": "não", "rank": 4}
        metrics = easiness_metrics(
            "Não, não, não, não, não, não.", card,
            matcher=matcher, frequency_ranks={"não": 4}, shared_policy=SHARED,
        )
        self.assertEqual(metrics["score"], 0.0)
        self.assertEqual(metrics["harder_tokens"], 0)


if __name__ == "__main__":
    unittest.main()
