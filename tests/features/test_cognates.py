"""Cognate transparency scoring.

Several of these cases are regressions from measurements taken against the
3000-word Czech speech deck; where a test encodes a real observation the word
pair and the number it produced are named, so a future change that moves them
has to argue with evidence rather than taste.
"""

import json
import tempfile
import unittest
from pathlib import Path

from fluency.enrichments.cognates import build_app_cognates
from fluency.features.cognates import (
    CognateMatch,
    CognatePolicy,
    CognatePolicyError,
    KnownLanguageIndex,
    available_known_languages,
    best_match,
    build_known_index,
    combine,
    form_score,
    gloss_tokens,
    live_glosses,
    load_policy,
    meaning_score,
    score_deck,
    similarity,
    skeleton,
    strip_accents,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CONFIG_ROOT = REPOSITORY_ROOT / "config"


def entry(word, glosses, pos="noun", tags_per_gloss=None):
    senses = []
    for index, gloss in enumerate(glosses):
        sense = {"glosses": [gloss]}
        if tags_per_gloss and index < len(tags_per_gloss) and tags_per_gloss[index]:
            sense["tags"] = list(tags_per_gloss[index])
        senses.append(sense)
    return {"word": word, "pos": pos, "senses": senses}


class PolicyTests(unittest.TestCase):
    def test_the_shipped_czech_pairs_load(self) -> None:
        for known in ("pl", "en"):
            policy = load_policy(CONFIG_ROOT, "cs", known)
            self.assertEqual(policy.target_language, "cs")
            self.assertEqual(policy.known_language, known)

    def test_a_pair_without_a_policy_is_refused_rather_than_defaulted(self) -> None:
        # Invariant 2: absence is declared. Falling back to some other pair's
        # orthography would silently score Greek with Czech rules.
        with self.assertRaises(CognatePolicyError):
            load_policy(CONFIG_ROOT, "cs", "el")

    def test_known_languages_are_discovered_from_files_not_a_list(self) -> None:
        # Invariant 5: a pair is added by creating a file.
        self.assertEqual(available_known_languages(CONFIG_ROOT, "cs"), ("en", "pl"))
        self.assertEqual(available_known_languages(CONFIG_ROOT, "zz"), ())

    def test_a_policy_file_declaring_another_pair_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "cognates").mkdir()
            (root / "cognates" / "cs-pl.json").write_text(
                json.dumps({"target_language": "cs", "known_language": "sk"}),
                encoding="utf-8",
            )
            with self.assertRaises(CognatePolicyError):
                load_policy(root, "cs", "pl")

    def test_the_weighting_must_let_a_perfect_pair_reach_one(self) -> None:
        with self.assertRaises(CognatePolicyError):
            CognatePolicy(
                target_language="cs",
                known_language="pl",
                meaning_floor=0.5,
                meaning_weight=0.2,
            )

    def test_a_pair_of_one_language_with_itself_is_refused(self) -> None:
        with self.assertRaises(CognatePolicyError):
            CognatePolicy(target_language="cs", known_language="cs")


class FormTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = load_policy(CONFIG_ROOT, "cs", "pl")

    def test_normalised_distance_punishes_a_short_word_matching_a_long_one(self) -> None:
        # A subsequence matcher scores stan/statni around 0.8 and let a whole
        # class of junk through (stan/statni, opak/naopak, stac/stacit).
        self.assertLess(similarity("statni", "stan"), 0.7)

    def test_the_skeleton_recovers_the_regular_correspondences(self) -> None:
        # Measured on the deck: spelling alone gives 0.17 for this pair.
        raw = similarity(strip_accents("hlavní"), strip_accents("główny"))
        mapped = form_score("hlavní", "główny", self.policy)
        self.assertLess(raw, 0.3)
        self.assertGreater(mapped, 0.8)

    def test_h_answers_g_and_l_answers_polish_l(self) -> None:
        for target, known in (("hlava", "głowa"), ("hlad", "głód"), ("dlouhý", "długi")):
            with self.subTest(pair=(target, known)):
                self.assertGreater(form_score(target, known, self.policy), 0.7)

    def test_digraph_rules_run_before_their_component_letters(self) -> None:
        # If h->g ran before ch->x, "chyba" would become "cgyba".
        self.assertEqual(skeleton("chyba", self.policy.target_skeleton), "xiba")

    def test_form_takes_the_better_of_raw_and_skeleton(self) -> None:
        # An identical borrowing needs no rewriting and must not be harmed by it.
        self.assertEqual(form_score("telefon", "telefon", self.policy), 1.0)


class MeaningTests(unittest.TestCase):
    def test_dead_senses_never_satisfy_the_meaning_axis(self) -> None:
        # Polish "chyba" is the particle "probably"; its "error, mistake" noun
        # senses are tagged obsolete. Pooling them matched Czech "chyba"
        # (mistake) at full confidence and hid a word the learner meets often.
        polish = entry(
            "chyba",
            ["probably", "error mistake", "falsehood trick"],
            pos="particle",
            tags_per_gloss=[None, ["obsolete"], ["Middle"]],
        )
        live = live_glosses(polish, 6)
        self.assertIn("probably", live)
        self.assertNotIn("error mistake", live)

    def test_a_definition_is_not_a_translation(self) -> None:
        wordy = entry("x", ["a small container used for holding liquids at table"])
        self.assertEqual(live_glosses(wordy, 6), frozenset())

    def test_overlap_is_damped_so_one_token_is_not_total_agreement(self) -> None:
        # The denominator is the smaller sense set, so overlap measures how
        # fully the narrower word is covered. Damping keeps a lone shared token
        # short of certainty; more shared meaning still scores higher.
        one_token = meaning_score(frozenset({"write"}), frozenset({"write"}))
        self.assertLess(one_token, 1.0)
        two_tokens = meaning_score(
            frozenset({"write", "inscribe"}), frozenset({"write", "inscribe"})
        )
        self.assertGreater(two_tokens, one_token)

    def test_a_polysemous_partner_does_not_dilute_a_narrow_word(self) -> None:
        # Coverage of the smaller side is deliberate: a Czech word with one
        # sense is fully recognisable through a Polish word that has that sense
        # among many others.
        narrow = meaning_score(
            frozenset({"write"}), frozenset({"write", "paint", "enrol", "ascribe"})
        )
        self.assertGreater(narrow, 0.0)

    def test_no_shared_meaning_scores_zero(self) -> None:
        self.assertEqual(meaning_score(frozenset({"fresh"}), frozenset({"stale"})), 0.0)


class CombinedScoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = load_policy(CONFIG_ROOT, "cs", "pl")

    def test_a_perfect_pair_scores_one(self) -> None:
        self.assertAlmostEqual(combine(1.0, 1.0, self.policy), 1.0)

    def test_form_leads_and_meaning_discounts(self) -> None:
        # An identical-looking word with no shared meaning sinks rather than
        # being kept or dropped outright. The exact floor is per-pair
        # calibration, so this asserts the shape rather than a shipped number.
        self.assertAlmostEqual(combine(1.0, 0.0, self.policy), self.policy.meaning_floor)
        self.assertGreater(combine(1.0, 1.0, self.policy), combine(1.0, 0.5, self.policy))
        self.assertLess(combine(1.0, 0.0, self.policy), combine(1.0, 1.0, self.policy))

    def test_meaning_alone_cannot_carry_a_dissimilar_pair(self) -> None:
        # Full agreement on meaning with almost no shared form must still rank
        # far below a look-alike that shares some meaning.
        self.assertLess(combine(0.2, 1.0, self.policy), combine(0.8, 0.2, self.policy))


class MatchingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = load_policy(CONFIG_ROOT, "cs", "pl")

    def index_of(self, entries):
        return build_known_index(entries, self.policy)

    def test_a_true_cognate_is_found_through_a_shared_gloss(self) -> None:
        index = self.index_of([entry("głowa", ["head"]), entry("noga", ["leg"])])
        match = best_match("hlava", frozenset({"head"}), index)
        self.assertIsNotNone(match)
        self.assertEqual(match.known_word, "głowa")
        self.assertGreater(match.score, 0.6)

    def test_a_false_friend_sharing_no_meaning_is_never_matched(self) -> None:
        # czerstwy is stale, čerstvý is fresh. Identical shape, opposite sense.
        index = self.index_of([entry("czerstwy", ["stale"])])
        self.assertIsNone(best_match("čerstvý", frozenset({"fresh"}), index))

    def test_a_short_word_is_not_scored_at_all(self) -> None:
        index = self.index_of([entry("ten", ["that"])])
        self.assertIsNone(best_match("ten", frozenset({"that"}), index))

    def test_the_length_guard_rejects_a_stem_match(self) -> None:
        index = self.index_of([entry("stan", ["state"])])
        self.assertIsNone(best_match("státní", frozenset({"state"}), index))

    def test_names_and_affixes_never_enter_the_index(self) -> None:
        index = self.index_of(
            [entry("paryż", ["paris"], pos="name"), entry("nie", ["not"], pos="prefix")]
        )
        self.assertEqual(index.words, {})

    def test_a_rare_gloss_word_is_preferred_over_a_common_one(self) -> None:
        crowd = [entry(f"slowo{i}", ["way"]) for i in range(300)]
        crowd.append(entry("sposób", ["way trick technique"]))
        index = self.index_of(crowd)
        # "technique" identifies one word and "way" three hundred, so the rare
        # token is spent first. The common one may still widen the search while
        # the budget allows, which is what keeps způsob/sposób reachable.
        candidates = index.candidates(frozenset({"way technique"}))
        self.assertIn("sposób", candidates)
        self.assertLessEqual(len(candidates), self.policy.candidate_budget)

    def test_a_common_gloss_word_is_still_used_when_it_is_all_there_is(self) -> None:
        # Capping by document frequency lost real cognates: způsob and sposób
        # share only "way", so discarding common tokens made the pair
        # unreachable at any threshold.
        index = self.index_of([entry("sposób", ["way manner"])])
        match = best_match("způsob", frozenset({"way", "manner"}), index)
        self.assertIsNotNone(match)
        self.assertEqual(match.known_word, "sposób")

    def test_the_budget_bounds_widening_but_never_the_best_evidence(self) -> None:
        # A single huge bucket is still spent in full — it is the only evidence
        # the pair has — but a second, commoner token may not widen past the
        # budget on top of it.
        crowd = [entry(f"slowo{i}", ["thing"]) for i in range(900)]
        crowd += [entry(f"inne{i}", ["stuff"]) for i in range(900)]
        index = self.index_of(crowd)
        only_one = index.candidates(frozenset({"thing"}))
        self.assertEqual(len(only_one), 900)
        both = index.candidates(frozenset({"thing stuff"}))
        self.assertEqual(len(both), 900)

    def test_a_match_that_scores_nothing_is_not_recorded(self) -> None:
        # A zero is a claim, and "no shared form at all" is not one worth
        # storing against a word.
        index = self.index_of([entry("zupelnie", ["manner"])])
        match = best_match("způsob", frozenset({"manner"}), index)
        if match is not None:
            self.assertGreater(match.score, 0.0)

    def test_a_deck_word_with_no_counterpart_is_absent_not_zero(self) -> None:
        # Invariant 3: a run must not record what it did not verify. A zero
        # would claim the word was checked and found unrelated.
        index = self.index_of([entry("głowa", ["head"])])
        scored = score_deck({"palivo": frozenset({"fuel"})}, index)
        self.assertEqual(scored, {})

    def test_the_best_of_several_candidates_wins(self) -> None:
        index = self.index_of([entry("głowa", ["head"]), entry("czaszka", ["head skull"])])
        match = best_match("hlava", frozenset({"head"}), index)
        self.assertEqual(match.known_word, "głowa")

    def test_scoring_a_deck_returns_one_match_per_reachable_word(self) -> None:
        index = self.index_of([entry("telefon", ["telephone"]), entry("głowa", ["head"])])
        scored = score_deck(
            {
                "telefon": frozenset({"telephone"}),
                "hlava": frozenset({"head"}),
                "nedostupný": frozenset({"unreachable"}),
            },
            index,
        )
        self.assertEqual(sorted(scored), ["hlava", "telefon"])
        self.assertIsInstance(scored["telefon"], CognateMatch)
        self.assertEqual(scored["telefon"].known_word, "telefon")


class SerialisationTests(unittest.TestCase):
    def test_a_match_round_trips_through_its_dict_form(self) -> None:
        match = CognateMatch(known_word="głowa", form=0.8125, meaning=0.6667, score=0.6875)
        self.assertEqual(
            match.to_dict(),
            {"known_word": "głowa", "form": 0.812, "meaning": 0.667, "score": 0.688},
        )

    def test_a_policy_round_trips(self) -> None:
        policy = load_policy(CONFIG_ROOT, "cs", "pl")
        self.assertEqual(CognatePolicy.from_dict(policy.to_dict()), policy)


if __name__ == "__main__":
    unittest.main()


class DefaultThresholdTests(unittest.TestCase):
    """Each pair carries its own auto cutoff, and nothing compares one pair's
    score with another's."""

    def test_every_shipped_pair_declares_a_cutoff(self) -> None:
        for known in ("pl", "en"):
            policy = load_policy(CONFIG_ROOT, "cs", known)
            self.assertGreater(policy.default_threshold, 0.0)
            self.assertLessEqual(policy.default_threshold, 1.0)

    def test_the_standard_pairs_share_one_weighting(self) -> None:
        # The weighting is the method, not a per-pair knob; tuning belongs in
        # default_threshold. Two pairs weighted differently would mean their
        # numbers described different quantities.
        polish = load_policy(CONFIG_ROOT, "cs", "pl")
        english = load_policy(CONFIG_ROOT, "cs", "en")
        self.assertEqual(polish.meaning_floor, english.meaning_floor)
        self.assertEqual(polish.meaning_weight, english.meaning_weight)

    def test_a_cutoff_outside_the_score_range_is_refused(self) -> None:
        with self.assertRaises(CognatePolicyError):
            CognatePolicy(target_language="cs", known_language="pl", default_threshold=1.4)


class AppLayerTests(unittest.TestCase):
    def test_the_app_file_ships_each_language_its_own_cutoff(self) -> None:
        # Without this the app would have to invent a threshold, or reuse a
        # slider calibrated for a different scale entirely.
        layer = {
            "language": "cs",
            "known_languages": ["en", "pl"],
            "built_from": {"release_id": "r1"},
            "policies": {
                "en": load_policy(CONFIG_ROOT, "cs", "en").to_dict(),
                "pl": load_policy(CONFIG_ROOT, "cs", "pl").to_dict(),
            },
            "scores": {"telefon": {"pl": {"score": 0.9, "known_word": "telefon",
                                          "form": 1.0, "meaning": 0.6}}},
        }
        published = build_app_cognates(layer)
        self.assertEqual(set(published["thresholds"]), {"en", "pl"})
        self.assertEqual(published["thresholds"]["pl"], 0.70)
        self.assertEqual(published["scores"]["telefon"]["pl"], 0.9)
