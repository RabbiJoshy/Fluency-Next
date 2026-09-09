"""Wiktionary states the same thing in three places; each needs different handling."""

import unittest

from fluency.features.wiktionary import (
    extract,
    extract_surface_grammar,
    metadata_accounting,
)


PT = {
    "register_tags": ["informal", "poetic"],
    "construction_tags": ["intransitive", "transitive"],
    "region_tags": ["Brazil", "Portugal"],
    "domain_tags": [],
    "grammar_tags": {},
    "ignored_tags": [],
}


def families(feats):
    return [(f.family, f.kind, f.value) for f in feats]


class WiktionaryExtractorTests(unittest.TestCase):
    def test_surface_grammar_is_language_neutral_and_typed(self) -> None:
        out = extract_surface_grammar([
            "feminine", "singular", "nominative", "perfective", "future"
        ])
        self.assertEqual(families(out), [
            ("grammar", "surface_mark", "gender=feminine"),
            ("grammar", "surface_mark", "tense=future"),
            ("grammar", "surface_mark", "case=nominative"),
            ("grammar", "surface_mark", "aspect=perfective"),
            ("grammar", "surface_mark", "number=singular"),
        ])

    def test_topics_become_domain_features(self) -> None:
        out = extract({"topics": ["finance"]}, policy=PT)
        self.assertEqual(families(out), [("domain", "topic", "finance")])

    def test_topic_repeated_in_parenthetical_is_not_construction_prose(self) -> None:
        sense = {
            "topics": ["card-games"],
            "raw_glosses": ["(card games, transitive) to deal"],
        }
        self.assertEqual(families(extract(sense, policy=PT)), [
            ("domain", "topic", "card-games"),
            ("construction", "gloss_note", "transitive"),
        ])

    def test_tags_split_by_declared_vocabulary(self) -> None:
        out = extract({}, tags=["informal", "intransitive"], policy=PT)
        self.assertEqual(families(out), [
            ("register", "usage_tag", "informal"),
            ("construction", "grammar_tag", "intransitive"),
        ])

    def test_language_grammar_domain_and_ignored_tags_are_explicit(self) -> None:
        policy = {
            **PT,
            "grammar_tags": {"historic": "tense=past-historic"},
            "domain_tags": ["Internet"],
            "ignored_tags": ["no-diminutive"],
        }
        out = extract({}, tags=["historic", "Internet"], policy=policy)
        self.assertEqual(families(out), [
            ("domain", "domain_tag", "Internet"),
            ("grammar", "sense_mark", "tense=past-historic"),
        ])
        accounting = metadata_accounting(
            {}, tags=["historic", "Internet", "no-diminutive"], policy=policy
        )
        self.assertEqual(accounting.unclassified, ())
        self.assertEqual(
            [item["value"] for item in accounting.ignored], ["no-diminutive"]
        )

    def test_language_grammar_mapping_applies_to_surface_forms(self) -> None:
        policy = {**PT, "grammar_tags": {"historic": "tense=past-historic"}}
        self.assertEqual(
            families(extract_surface_grammar(["historic"], policy=policy)),
            [("grammar", "surface_mark", "tense=past-historic")],
        )

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

    def test_nested_parenthetical_keeps_regions_and_outer_labels_intact(self) -> None:
        sense = {
            "raw_glosses": [
                "(transitive (Portugal) or intransitive (Brazil), poetic) to score"
            ]
        }
        self.assertEqual(families(extract(sense, policy=PT)), [
            (
                "construction",
                "gloss_phrase",
                "transitive (Portugal) or intransitive (Brazil)",
            ),
            ("register", "gloss_note", "poetic"),
        ])

    def test_region_is_a_register_feature_not_construction_prose(self) -> None:
        sense = {"raw_glosses": ["(Brazil, transitive) to score"]}
        self.assertEqual(families(extract(sense, policy=PT)), [
            ("register", "region", "Brazil"),
            ("construction", "gloss_note", "transitive"),
        ])

    def test_region_tag_is_normalized_without_requiring_a_parenthetical(self) -> None:
        self.assertEqual(families(extract({}, tags=["Brazil"], policy=PT)), [
            ("register", "region", "Brazil"),
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
            ("grammar", "sense_mark", "reflexive=true"),
        ])

    def test_shared_tags_survive_a_language_specific_policy(self) -> None:
        out = extract(
            {},
            tags=["literary", "with-dative", "perfective", "feminine"],
            policy={"register_tags": ["local-only"], "construction_tags": []},
        )
        self.assertEqual(families(out), [
            ("grammar", "sense_mark", "gender=feminine"),
            ("register", "usage_tag", "literary"),
            ("grammar", "sense_mark", "aspect=perfective"),
            ("construction", "grammar_tag", "with-dative"),
        ])

    def test_functional_gloss_is_not_misfiled_as_construction(self) -> None:
        out = extract({"glosses": ["used to indicate direction"]}, policy=PT)
        self.assertEqual(
            families(out),
            [("functional", "usage_note", "used to indicate direction")],
        )

    def test_parenthetical_must_precede_real_text(self) -> None:
        self.assertEqual(extract({"raw_glosses": ["(alone)"]}, policy=PT), ())

    def test_no_signals_yields_no_features(self) -> None:
        self.assertEqual(extract({"glosses": ["a thing"]}, policy=PT), ())

    def test_unknown_tag_and_template_are_accounted_for_not_discarded(self) -> None:
        accounting = metadata_accounting(
            {"info_templates": [{"name": "language-specific-template", "args": {}}]},
            tags=["language-specific-tag", "perfective"],
            policy=PT,
        )
        self.assertEqual(accounting.coverage["info_templates"], "parsed")
        self.assertEqual(
            [item["source_field"] for item in accounting.unclassified],
            ["tags", "info_templates"],
        )
        self.assertNotIn("perfective", [item.get("value") for item in accounting.unclassified])

    def test_dictionary_relation_tags_are_explicitly_ignored_not_unclassified(self) -> None:
        accounting = metadata_accounting({}, tags=["form-of", "alt-of"], policy=PT)
        self.assertEqual(accounting.unclassified, ())
        self.assertEqual(
            [item["value"] for item in accounting.ignored], ["alt-of", "form-of"]
        )


if __name__ == "__main__":
    unittest.main()
