from pathlib import Path
import unittest

from fluency.sense_menu.config import (
    SenseMenuPolicyError,
    load_sense_menu_language_policy,
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


if __name__ == "__main__":
    unittest.main()
