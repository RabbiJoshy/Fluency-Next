from copy import deepcopy
from pathlib import Path
import unittest

from fluency.features.metadata import METADATA_CONTRACT_VERSION
from fluency.release.metadata_upgrade import canonicalize_meaning_metadata
from fluency.sense_menu.config import (
    load_sense_menu_language_policy,
    load_sense_menu_registry,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class MetadataUpgradeTests(unittest.TestCase):
    def policy(self, language: str) -> dict:
        registry = load_sense_menu_registry(REPOSITORY_ROOT)
        return load_sense_menu_language_policy(
            REPOSITORY_ROOT,
            policy_id=registry["languages"][language]["policy_id"],
            language=language,
        )

    def test_wiktionary_metadata_is_canonicalized_without_losing_unknowns(self) -> None:
        meaning = {
            "translation": "to finish",
            "metadata": {
                "source_adapter": "wiktionary-sense-menu/v1",
                "sense_provider_metadata": {
                    "tags": ["perfective", "form-of", "future-taxonomy-tag"],
                    "topics": ["computing"],
                    "raw_glosses": ["(computing) to finish"],
                    "opaque_provider_field": {"kept": True},
                },
                "specialist_features": [],
            },
        }

        canonicalize_meaning_metadata(meaning, policy=self.policy("pt"))

        metadata = meaning["metadata"]
        envelope = metadata["sense_metadata"]
        self.assertEqual(envelope["contract_version"], METADATA_CONTRACT_VERSION)
        self.assertEqual(
            envelope["source_metadata"]["opaque_provider_field"], {"kept": True}
        )
        self.assertTrue(
            any(feature["value"] == "aspect=perfective" for feature in envelope["features"])
        )
        self.assertTrue(
            any(item["value"] == "future-taxonomy-tag" for item in envelope["unclassified"])
        )
        self.assertTrue(any(item["value"] == "form-of" for item in envelope["ignored"]))
        self.assertEqual(metadata["language_policy_id"], "pt-v1")
        self.assertTrue(metadata["language_policy_content_id"].startswith("sha256:"))

    def test_spanishdict_metadata_uses_the_same_envelope(self) -> None:
        meaning = {
            "translation": "to depend",
            "context": 'used with "de"; informal',
            "metadata": {
                "source_adapter": "spanishdict-sense-menu/v1",
                "sense_provider_metadata": {
                    "context": 'used with "de"; informal',
                    "regions": [{"name": "Mexico"}],
                    "spanishdict": {
                        "examples": [{"original": "Depende de ti.", "translated": "It depends on you."}],
                        "future_provider_field": "kept",
                    },
                    "translation_status": "present",
                },
            },
        }

        canonicalize_meaning_metadata(meaning, policy=self.policy("es"))

        envelope = meaning["metadata"]["sense_metadata"]
        self.assertEqual(envelope["contract_version"], METADATA_CONTRACT_VERSION)
        self.assertTrue(
            any(feature["family"] == "companion" for feature in envelope["features"])
        )
        self.assertTrue(
            any(feature["kind"] == "region" for feature in envelope["features"])
        )
        self.assertEqual(envelope["source_metadata"]["future_provider_field"], "kept")
        self.assertTrue(
            any(
                item["source_field"] == "spanishdict.future_provider_field"
                for item in envelope["unclassified"]
            )
        )

    def test_upgrade_is_idempotent_for_existing_features(self) -> None:
        meaning = {
            "translation": "perfective action",
            "metadata": {
                "source_adapter": "wiktionary-sense-menu/v1",
                "sense_provider_metadata": {"tags": ["perfective"]},
                "specialist_features": [
                    {
                        "family": "grammar",
                        "kind": "sense_mark",
                        "value": "aspect=perfective",
                        "embedding_text": "perfective",
                    }
                ],
            },
        }

        first = deepcopy(meaning)
        canonicalize_meaning_metadata(first, policy=self.policy("pt"))
        canonicalize_meaning_metadata(first, policy=self.policy("pt"))

        features = first["metadata"]["sense_metadata"]["features"]
        self.assertEqual(
            [item["value"] for item in features].count("aspect=perfective"), 1
        )


if __name__ == "__main__":
    unittest.main()
