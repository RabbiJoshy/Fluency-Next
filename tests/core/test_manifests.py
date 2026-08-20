from datetime import UTC, datetime
import unittest

from fluency.core.hashing import content_id
from fluency.core.manifests import (
    StageManifest,
    build_stage_cache_key,
    create_run_manifest,
    create_run_id,
)


class ManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.implementation_hash = content_id(b"implementation")
        self.config_hash = content_id(b"configuration")
        self.input_hash = content_id(b"input")
        self.started_at = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)

    def test_run_id_has_timestamp_and_unique_execution_suffix(self) -> None:
        self.assertEqual(
            create_run_id(started_at=self.started_at, suffix="a91f23c4"),
            "20260820T120000Z-a91f23c4",
        )

    def test_run_manifest_can_be_completed_immutably(self) -> None:
        run = create_run_manifest(
            language="fr",
            mode="speech",
            profile="speech-v1",
            config_hash=self.config_hash,
            inputs={"source": self.input_hash},
            started_at=self.started_at,
            suffix="a91f23c4",
        )
        completed = run.with_status("complete", at=self.started_at)
        self.assertEqual(run.status, "created")
        self.assertEqual(completed.status, "complete")
        self.assertIsNotNone(completed.completed_at)

    def test_stage_cache_key_is_deterministic_and_sensitive(self) -> None:
        arguments = {
            "stage_name": "s10_occurrences",
            "stage_version": "1.0.0",
            "implementation_hash": self.implementation_hash,
            "config_hash": self.config_hash,
            "inputs": {"source": self.input_hash},
            "model_revisions": {},
            "random_seed": 1729,
        }
        first = build_stage_cache_key(**arguments)
        second = build_stage_cache_key(**arguments)
        changed = build_stage_cache_key(**{**arguments, "random_seed": 1730})
        self.assertEqual(first, second)
        self.assertNotEqual(first, changed)

    def test_stage_completion_preserves_running_manifest(self) -> None:
        cache_key = build_stage_cache_key(
            stage_name="s10_occurrences",
            stage_version="1.0.0",
            implementation_hash=self.implementation_hash,
            config_hash=self.config_hash,
            inputs={"source": self.input_hash},
            model_revisions={},
            random_seed=1729,
        )
        running = StageManifest(
            stage_name="s10_occurrences",
            stage_version="1.0.0",
            cache_key=cache_key,
            implementation_hash=self.implementation_hash,
            config_hash=self.config_hash,
            status="running",
            started_at="2026-08-20T12:00:00Z",
            inputs={"source": self.input_hash},
            model_revisions={},
            random_seed=1729,
            outputs={},
        )
        output = content_id(b"output")
        completed = running.complete({"occurrences": output}, at=self.started_at)
        self.assertEqual(running.outputs, {})
        self.assertEqual(completed.outputs, {"occurrences": output})
        self.assertEqual(completed.status, "complete")


if __name__ == "__main__":
    unittest.main()

