from pathlib import Path
import unittest

from fluency.features.spanishdict import extract as extract_spanishdict
from fluency.features.spanishdict_metadata import metadata_accounting as spanishdict_accounting
from fluency.features.wiktionary import extract as extract_wiktionary
from fluency.features.wiktionary import metadata_accounting as wiktionary_accounting
from fluency.sense_menu.config import (
    load_sense_menu_language_policy,
    load_sense_menu_registry,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class CrossLanguageMetadataConformanceTests(unittest.TestCase):
    def test_every_wiktionary_policy_declares_the_same_adapter_slots(self) -> None:
        registry = load_sense_menu_registry(REPOSITORY_ROOT)
        list_slots = {
            "construction_tags", "domain_tags", "ignored_tags", "region_tags",
            "register_tags",
        }
        for language, entry in registry["languages"].items():
            if entry["provider"] != "wiktionary":
                continue
            with self.subTest(language=language):
                policy = load_sense_menu_language_policy(
                    REPOSITORY_ROOT,
                    policy_id=entry["policy_id"],
                    language=language,
                )
                for slot in list_slots:
                    self.assertIsInstance(policy[slot], list)
                self.assertIsInstance(policy["grammar_tags"], dict)

    def test_every_policy_emits_the_same_envelope_shape(self) -> None:
        registry = load_sense_menu_registry(REPOSITORY_ROOT)
        expected = {
            "contract_version", "features", "source_metadata", "coverage",
            "unclassified", "ignored",
        }
        for language, entry in registry["languages"].items():
            with self.subTest(language=language):
                policy = load_sense_menu_language_policy(
                    REPOSITORY_ROOT,
                    policy_id=entry["policy_id"],
                    language=language,
                )
                if entry["provider"] == "wiktionary":
                    source = {
                        "tags": ["perfective", "future-language-specific-mark"],
                        "topics": ["computing"],
                    }
                    features = extract_wiktionary(
                        source, tags=source["tags"], policy=policy
                    )
                    accounting = wiktionary_accounting(
                        source, tags=source["tags"], policy=policy
                    )
                else:
                    source = {"context": "used with de", "regions": ["Mexico"]}
                    features = extract_spanishdict(source)
                    accounting = spanishdict_accounting(source)
                envelope = accounting.envelope(
                    source_metadata=source, features=features
                )
                self.assertEqual(set(envelope), expected)
                self.assertEqual(envelope["contract_version"], "sense-metadata/v1")

    def test_language_specific_metadata_does_not_require_cross_language_equivalence(self) -> None:
        registry = load_sense_menu_registry(REPOSITORY_ROOT)
        for language, entry in registry["languages"].items():
            if entry["provider"] != "wiktionary":
                continue
            policy = load_sense_menu_language_policy(
                REPOSITORY_ROOT, policy_id=entry["policy_id"], language=language
            )
            features = extract_wiktionary(
                {}, tags=["perfective"], policy=policy
            )
            self.assertIn(
                ("grammar", "sense_mark", "aspect=perfective"),
                {(item.family, item.kind, item.value) for item in features},
            )


if __name__ == "__main__":
    unittest.main()
