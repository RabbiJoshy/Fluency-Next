"""Both dictionary adapters must emit the same concept families."""

import unittest

from fluency.features.spanishdict import extract as spanishdict_extract
from fluency.features.wiktionary import extract as wiktionary_extract


def values(features, family):
    return {feature.value for feature in features if feature.family == family}


class ProviderParityTests(unittest.TestCase):
    def test_functional_notes_share_one_family(self) -> None:
        spanish = spanishdict_extract({"context": "used to indicate direction"})
        wiki = wiktionary_extract({"glosses": ["used to indicate direction"]})
        self.assertEqual(values(spanish, "functional"), values(wiki, "functional"))

    def test_grammar_marks_share_canonical_values(self) -> None:
        spanish = spanishdict_extract(
            {"context": "imperative; second person singular"}
        )
        wiki = wiktionary_extract(
            {}, tags=["imperative", "second-person", "singular"]
        )
        self.assertEqual(values(spanish, "grammar"), values(wiki, "grammar"))

    def test_plain_paraphrase_is_not_sent_to_the_domain_channel(self) -> None:
        features = spanishdict_extract({"context": "to be available"})
        self.assertFalse(any(feature.family == "domain" for feature in features))


if __name__ == "__main__":
    unittest.main()
