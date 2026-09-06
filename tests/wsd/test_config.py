import copy
import json
from pathlib import Path
import unittest

from fluency.pipeline.planning import load_pipeline_profile
from fluency.wsd.config import WSDProfileError, load_wsd_profiles, model_revisions


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_PROFILE = REPOSITORY_ROOT / "config/pipelines/fr/speech/rehearsal-20x3.json"
SPANISH_PIPELINE_PROFILE = REPOSITORY_ROOT / "config/pipelines/es/speech/rehearsal-20x3.json"


class WSDProfileTests(unittest.TestCase):
    def setUp(self):
        self.pipeline = load_pipeline_profile(PIPELINE_PROFILE)

    def test_selected_profiles_load_but_truthfully_remain_blocked(self):
        shared, language, model, config_id = load_wsd_profiles(
            REPOSITORY_ROOT, self.pipeline
        )
        self.assertEqual(shared["fallback_policy"], "none")
        self.assertEqual(language["language"], "fr")
        self.assertEqual(model["execution_status"], "blocked_pending_benchmark")
        self.assertTrue(config_id.startswith("sha256:"))
        with self.assertRaises(WSDProfileError):
            load_wsd_profiles(REPOSITORY_ROOT, self.pipeline, require_ready=True)

    def test_profile_selection_cannot_drift_from_model_status(self):
        changed = copy.deepcopy(self.pipeline)
        changed["wsd"]["execution_status"] = "ready"
        with self.assertRaises(WSDProfileError):
            load_wsd_profiles(REPOSITORY_ROOT, changed)

    def test_spanish_method_snapshot_loads_but_waits_for_migrated_assets(self):
        pipeline = load_pipeline_profile(SPANISH_PIPELINE_PROFILE)
        shared, language, model, config_id = load_wsd_profiles(
            REPOSITORY_ROOT, pipeline
        )
        self.assertIn("provider_prior", shared["decision_order"])
        self.assertEqual(language["clitic_gate"]["method"], "spanish-se-only/v1")
        self.assertEqual(model["source_method_id"], "spanishdict-beto-cal-v5")
        self.assertEqual(model["execution_status"], "blocked_pending_assets")
        self.assertFalse(model["alignment"]["enabled"])
        self.assertTrue(config_id.startswith("sha256:"))
        with self.assertRaises(WSDProfileError):
            load_wsd_profiles(REPOSITORY_ROOT, pipeline, require_ready=True)

    def test_v8_supplied_english_profiles_pin_the_local_aligner(self):
        for language in ("es", "pt"):
            with self.subTest(language=language):
                path = (
                    REPOSITORY_ROOT
                    / "config"
                    / "wsd"
                    / "models"
                    / f"{language}-v8-english-1.json"
                )
                profile = json.loads(path.read_text(encoding="utf-8"))
                revisions = model_revisions(profile)
                self.assertEqual(profile["language"], language)
                self.assertEqual(profile["execution_status"], "ready")
                self.assertIn("alignment.model_revision", revisions)
                self.assertEqual(
                    profile["alignment"]["network_policy"], "local_files_only"
                )

    def test_v9_profiles_use_the_same_rank_agreement_commit_for_both_providers(self):
        for language in ("es", "pt"):
            with self.subTest(language=language):
                path = (
                    REPOSITORY_ROOT
                    / "config"
                    / "wsd"
                    / "models"
                    / f"{language}-v9-1.json"
                )
                profile = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(profile["source_method_id"], "provider-neutral-v9-rank-agreement")
                self.assertEqual(profile["commit"]["strategy"], "rank_agreement")
                self.assertFalse(profile["alignment"]["enabled"])
                self.assertNotIn("alignment.model_revision", model_revisions(profile))

    def test_v10_profiles_use_machine_readable_guards_for_both_providers(self):
        for language in ("es", "pt"):
            with self.subTest(language=language):
                path = (
                    REPOSITORY_ROOT
                    / "config"
                    / "wsd"
                    / "models"
                    / f"{language}-v10-1.json"
                )
                profile = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(
                    profile["source_method_id"],
                    "provider-neutral-v10-pedagogy-guards",
                )
                self.assertEqual(
                    profile["commit"]["strategy"],
                    "rank_agreement_with_machine_readable_guards",
                )
                self.assertFalse(profile["alignment"]["enabled"])
                self.assertNotIn("alignment.model_revision", model_revisions(profile))


if __name__ == "__main__":
    unittest.main()
