"""An example must show a word doing something.

Easiness counts how many UNFAMILIAR words a learner must get past, and skips the
target itself. So "Nao, nao, nao, nao, nao, nao" has zero unfamiliar words, six
tokens exactly meeting the preferred minimum, and therefore a perfect score of
0.0 -- it wins every ranking. On the first language to harvest raw OpenSubtitles
this filled entire candidate pools: all 60 candidates for `nao` were repetitions.

Two gates are needed, because a count alone cannot tell a short sentence from an
echoed one. "Isso nao e o que quero." carries six distinct words in six; "Eu nao
sei o que tu queres, eu nao sei." carries seven in ten. The second is longer and
clears any count worth setting, yet a third of it is echo.

Repetition is a property of the sentence, not of any one card, so both are judged
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
# Every word here is ranked: in a real run the commonest words always are, and
# leaving one out silently makes it look rare enough to dominate the score.
RANKS = {"não": 4, "e": 8, "sei": 300, "o": 2, "que": 1, "é": 6}

# Rejected by the count gate alone: five distinct tokens, none repeated.
TOO_FEW_WORDS = "Não sei o que é."
# Rejected by the ratio gate alone: seven distinct tokens, ten in total.
MOSTLY_ECHO = "Eu não sei o que tu queres, eu não sei."


def reject(sentence, translation=TRANSLATION, policy=None):
    matcher = SurfaceMatcher([{"card_id": "c", "display_form": "não"}], PT)
    return quality_rejection(
        sentence, translation, matcher=matcher, shared_policy=policy or SHARED
    )


def without(key):
    policy = json.loads(json.dumps(SHARED))
    policy["quality"][key] = 0
    return policy


class RepetitionGateTests(unittest.TestCase):
    def test_pure_repetition_is_rejected(self) -> None:
        self.assertEqual(
            reject("Não, não, não, não, não, não."), "insufficient_distinct_tokens"
        )

    def test_echoed_phrases_are_rejected(self) -> None:
        for sentence in ("Que bom, que bom, que bom!",
                         "A sério? A sério? A sério?",
                         "Um, dois, um, dois, um. Um, dois."):
            with self.subTest(sentence=sentence):
                self.assertEqual(reject(sentence), "insufficient_distinct_tokens")

    def test_natural_sentences_survive(self) -> None:
        for sentence in ("Não, isto é a minha casa.",
                         "O que estás a fazer na minha casa?",
                         "Bom, deixa-me tentar falar com ela.",
                         "Isso não é o que quero."):
            with self.subTest(sentence=sentence):
                self.assertIsNone(reject(sentence))

    def test_one_repeated_word_is_still_allowed(self) -> None:
        """Repetition is normal; a sentence made only of it is not."""

        self.assertIsNone(reject("Não, não sei o que ela disse."))

    def test_the_thresholds_are_declared_not_hardcoded(self) -> None:
        self.assertEqual(SHARED["quality"]["minimum_distinct_tokens"], 6)
        self.assertEqual(SHARED["quality"]["minimum_distinct_ratio"], 0.75)


class EchoRatioTests(unittest.TestCase):
    """The count and the ratio catch different sentences, so both must exist."""

    def test_an_echo_that_clears_the_count_is_still_rejected(self) -> None:
        self.assertEqual(reject(MOSTLY_ECHO), "echoed_target")

    def test_a_short_sentence_that_is_not_an_echo_is_judged_by_count_only(self) -> None:
        self.assertEqual(reject(TOO_FEW_WORDS), "insufficient_distinct_tokens")

    def test_each_gate_catches_what_the_other_misses(self) -> None:
        """Neither threshold is redundant: disabling one lets its probe through."""

        self.assertIsNone(reject(TOO_FEW_WORDS, policy=without("minimum_distinct_tokens")))
        self.assertIsNone(reject(MOSTLY_ECHO, policy=without("minimum_distinct_ratio")))

    def test_a_language_declaring_no_thresholds_keeps_everything(self) -> None:
        """Absence is declared, never inferred: zero means no gate."""

        policy = json.loads(json.dumps(SHARED))
        policy["quality"]["minimum_distinct_tokens"] = 0
        policy["quality"]["minimum_distinct_ratio"] = 0
        self.assertIsNone(reject("Não, não, não, não, não, não.", policy=policy))


class EasinessDegeneracyTests(unittest.TestCase):
    """Burden and length are measured on the same basis: distinct words.

    Burden always counted each distinct word once, but length counted raw
    tokens. Repetition therefore added nothing to burden while padding a
    sentence past the short-sentence penalty -- it was not merely free, it was
    rewarded, and "Nao, nao, nao, nao, nao, nao" scored a perfect 0.0 and won
    every ranking. This is the defect the gates were compensating for.
    """

    def _score(self, sentence: str) -> float:
        matcher = SurfaceMatcher([{"card_id": "c", "display_form": "não"}], PT)
        return easiness_metrics(
            sentence, {"display_form": "não", "rank": 4},
            matcher=matcher, frequency_ranks=RANKS,
            shared_policy=SHARED,
        )["score"]

    def test_repetition_no_longer_scores_perfectly(self) -> None:
        self.assertGreater(self._score("Não, não, não, não, não, não."), 0.0)

    def test_repetition_loses_to_a_real_sentence(self) -> None:
        """The ranking itself now prefers the example that teaches something."""

        self.assertGreater(
            self._score("Não, não, não, não, não, não."),
            self._score("E não sei o que é."),
        )

    def test_a_sentence_without_repetition_is_scored_as_before(self) -> None:
        """The fix must not re-rank the sentences that were already fine.

        Distinct and raw length are equal when nothing repeats, so a
        non-repetitive example keeps its exact previous score. That is what
        keeps an existing embedding cache valid: only repetitive sentences move.
        """

        matcher = SurfaceMatcher([{"card_id": "c", "display_form": "não"}], PT)
        sentence = "E não sei o que é."
        tokens = matcher.tokens(sentence)
        self.assertEqual(len(tokens), len(dict.fromkeys(tokens)))
        metrics = easiness_metrics(
            sentence, {"display_form": "não", "rank": 4},
            matcher=matcher, frequency_ranks=RANKS, shared_policy=SHARED,
        )
        # target_tokens is the length the penalty is computed from; for a
        # sentence with no repeats it still equals the raw token count.
        self.assertEqual(metrics["target_tokens"], len(tokens))


if __name__ == "__main__":
    unittest.main()


class TruncatedFragmentTests(unittest.TestCase):
    """A subtitle cut mid-thought is grammatical and teaches nothing."""

    def test_a_line_cut_mid_thought_is_rejected(self) -> None:
        self.assertEqual(reject("Isso não é o que eu..."), "truncated_fragment")

    def test_a_complete_sentence_survives(self) -> None:
        self.assertIsNone(reject("Não, isto é a minha casa."))

    def test_the_rule_is_declared_not_hardcoded(self) -> None:
        policy = json.loads(json.dumps(SHARED))
        policy["quality"]["reject_truncated_fragments"] = False
        self.assertIsNone(reject("Isso não é o que eu...", policy=policy))
