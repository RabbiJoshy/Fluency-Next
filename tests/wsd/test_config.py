import copy
from pathlib import Path
import unittest

from fluency.pipeline.planning import load_pipeline_profile
from fluency.wsd.config import WSDProfileError, load_wsd_profiles


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_PROFILE = REPOSITORY_ROOT / "config/pipelines/fr/speech/rehearsal-20x3.json"


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


if __name__ == "__main__":
    unittest.main()
