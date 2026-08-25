"""Wiktionary states the same thing in three places; each needs different handling."""

import unittest

from fluency.features.wiktionary import extract


PT = {
    "register_tags": ["informal", "poetic"],
    "construction_tags": ["intransitive", "transitive"],
}


def families(feats):
    return [(f.family, f.kind, f.value) for f in feats]


class WiktionaryExtractorTests(unittest.TestCase):
    def test_topics_become_domain_features(self) -> None:
        out = extract({"topics": ["finance"]}, policy=PT)
        self.assertEqual(families(out), [("domain", "topic", "finance")])

    def test_tags_split_by_declared_vocabulary(self) -> None:
        out = extract({}, tags=["informal", "intransitive"], policy=PT)
        self.assertEqual(families(out), [
            ("register", "usage_tag", "informal"),
            ("construction", "grammar_tag", "intransitive"),
        ])

    def test_parenthetical_prose_becomes_a_construction_feature(self) -> None:
        """Frame notes appear nowhere else in the pipeline."""

        sense = {"raw_glosses": ["(only in subordinate clauses) since"]}
        self.assertEqual(
            families(extract(sense, policy=PT)),
            [("construction", "gloss_phrase", "only in subordinate clauses")],
        )

    def test_parenthetical_is_split_on_commas(self) -> None:
        sense = {"raw_glosses": ["(intransitive, poetic) to wander"]}
        self.assertEqual(families(extract(sense, policy=PT)), [
            ("construction", "gloss_note", "intransitive"),
            ("register", "gloss_note", "poetic"),
        ])

    def test_a_mark_stated_twice_is_emitted_once(self) -> None:
        """The same mark routinely appears as a tag and in the parenthetical."""

        sense = {"raw_glosses": ["(intransitive) to go"]}
        out = extract(sense, tags=["intransitive"], policy=PT)
        self.assertEqual(families(out), [("construction", "grammar_tag", "intransitive")])

    def test_unknown_vocabulary_falls_back_to_provider_defaults(self) -> None:
        out = extract({}, tags=["archaic", "reflexive"], policy={})
        self.assertEqual(families(out), [
            ("register", "usage_tag", "archaic"),
            ("construction", "grammar_tag", "reflexive"),
        ])

    def test_parenthetical_must_precede_real_text(self) -> None:
        self.assertEqual(extract({"raw_glosses": ["(alone)"]}, policy=PT), ())

    def test_no_signals_yields_no_features(self) -> None:
        self.assertEqual(extract({"glosses": ["a thing"]}, policy=PT), ())


if __name__ == "__main__":
    unittest.main()
