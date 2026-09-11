from pathlib import Path
import unittest

from fluency.sense_menu.config import (
    SenseMenuPolicyError,
    load_sense_menu_language_policy,
    load_sense_menu_registry,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class SenseMenuPolicyTests(unittest.TestCase):
    def test_spanishdict_policy_keeps_headwords_as_lookup_metadata(self):
        policy = load_sense_menu_language_policy(
            REPOSITORY_ROOT, policy_id="es-spanishdict-v1", language="es"
        )
        self.assertEqual(policy["provider"], "spanishdict")
        self.assertEqual(policy["card_binding"]["identity"], "surface-card/v1")
        self.assertFalse(policy["lookup_candidates"]["may_replace_surface_card"])
        self.assertEqual(policy["response_mismatch"]["fuzzy_correction"], "quarantine")

    def test_policy_identity_cannot_cross_languages(self):
        with self.assertRaises(SenseMenuPolicyError):
            load_sense_menu_language_policy(
                REPOSITORY_ROOT, policy_id="es-spanishdict-v1", language="fr"
            )

    def test_every_configured_language_has_a_loadable_metadata_policy(self):
        registry = load_sense_menu_registry(REPOSITORY_ROOT)
        self.assertEqual(
            set(registry["languages"]),
            {"cs", "es", "fr", "it", "nl", "pl", "pt", "ru", "sv"},
        )

    def test_scaffold_language_inherits_safe_wiktionary_adapter_defaults(self):
        policy = load_sense_menu_language_policy(
            REPOSITORY_ROOT, policy_id="it-v1", language="it"
        )
        self.assertEqual(policy["audit_status"], "scaffold")
        self.assertTrue(policy["redirects"]["require_source_case_match"])
        self.assertIn("abbreviation", policy["redirects"]["reject_tags"])
        self.assertEqual(
            policy["redirects"]["target_pos_by_source_pos"]["verb"], ["verb"]
        )

    def test_portuguese_policy_separates_region_and_register_labels(self):
        policy = load_sense_menu_language_policy(
            REPOSITORY_ROOT, policy_id="pt-v1", language="pt"
        )
        self.assertIn("Alentejo", policy["region_tags"])
        self.assertIn("nonstandard", policy["register_tags"])
        self.assertNotIn("Alentejo", policy["construction_tags"])

    def test_portuguese_audit_maps_ambiguous_provider_tags_by_evidence(self):
        policy = load_sense_menu_language_policy(
            REPOSITORY_ROOT, policy_id="pt-v1", language="pt"
        )
        self.assertIn("particle", policy["domain_tags"])
        self.assertIn("Northern", policy["region_tags"])
        self.assertIn("ergative", policy["construction_tags"])
        self.assertEqual(policy["grammar_tags"]["numeral"], "word-class=numeral")
        self.assertEqual(
            policy["grammar_tags"]["no-first-person-singular-present"],
            "inflection=no-first-person-singular-present",
        )


if __name__ == "__main__":
    unittest.main()
