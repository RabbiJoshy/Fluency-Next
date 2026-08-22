from copy import deepcopy
from datetime import UTC, datetime
import json
from pathlib import Path
import tempfile
import unittest

from fluency.core.workspace import Workspace
from fluency.pipeline.planning import (
    PipelineProfileError,
    STAGE_ORDER,
    create_pipeline_plan,
    load_pipeline_profile,
    validate_pipeline_profile,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = REPOSITORY_ROOT / "config" / "pipelines" / "fr" / "speech" / "audit-200x3.json"


class PipelinePlanningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = load_pipeline_profile(PROFILE_PATH)

    def test_profile_locks_fresh_surface_only_audit(self) -> None:
        self.assertEqual(self.profile["scope"]["surface_limit"], 200)
        self.assertEqual(self.profile["scope"]["examples_per_surface"], 3)
        self.assertFalse(self.profile["identity"]["allow_lemma_identity"])
        self.assertFalse(self.profile["source_policy"]["allow_legacy_inputs"])
        self.assertEqual(self.profile["stage_order"], list(STAGE_ORDER))

    def test_profile_rejects_legacy_or_fallback_inputs(self) -> None:
        for field, value in (("allow_legacy_inputs", True), ("fallback_policy", "missing_only")):
            with self.subTest(field=field):
                changed = deepcopy(self.profile)
                changed["source_policy"][field] = value
                with self.assertRaises(PipelineProfileError):
                    validate_pipeline_profile(changed)

    def test_plan_creates_auditable_stage_folders_without_execution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Workspace.initialize(Path(directory) / "workspace")
            target = create_pipeline_plan(
                workspace,
                self.profile,
                started_at=datetime(2026, 8, 22, 12, 0, tzinfo=UTC),
                suffix="a91f23c4",
            )
            manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
            plan = json.loads((target / "plan.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "created")
            self.assertEqual(plan["execution_status"], "not_started")
            self.assertEqual(plan["targets"]["surface_cards"], 200)
            self.assertEqual(plan["targets"]["total_examples"], 600)
            self.assertEqual(len(manifest["stages"]), 6)
            for path in manifest["stages"]:
                contract = json.loads((target / path).read_text(encoding="utf-8"))
                self.assertEqual(contract["status"], "pending")


if __name__ == "__main__":
    unittest.main()
