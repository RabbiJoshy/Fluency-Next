from datetime import UTC, datetime
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fluency.core.hashing import file_content_id
from fluency.core.workspace import Workspace
from fluency.migration import spanish_wsd_assets
from fluency.migration.spanish_wsd_assets import migrate_spanish_wsd_assets


class SpanishWSDAssetMigrationTests(unittest.TestCase):
    def test_pins_runtime_assets_without_assignments(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            layers = root / "old/Data/Spanish/layers"
            (layers / "token_prototypes").mkdir(parents=True)
            (layers / "wsd_calibrator").mkdir(parents=True)
            files = {
                "prototypes/proto.npy": b"prototype matrix",
                "prototypes/proto_index.json": b'{"x": 0}',
                "prototypes/proto_counts.json": b'{"x": 2}',
                "prototypes/manifest.json": b'{"model": "BETO"}',
                "calibrator/calibrator.joblib": b"calibrator",
                "calibrator/manifest.json": b'{"feature_version": 5}',
            }
            paths = {}
            for name, payload in files.items():
                family, filename = name.split("/")
                folder = "token_prototypes" if family == "prototypes" else "wsd_calibrator"
                path = layers / folder / filename
                path.write_bytes(payload)
                paths[name] = file_content_id(path).removeprefix("sha256:")
            workspace = Workspace.initialize(root / "workspace")
            with patch.object(spanish_wsd_assets, "EXPECTED_HASHES", paths):
                targets = migrate_spanish_wsd_assets(
                    workspace,
                    source_repository=root / "old",
                    recovered_at=datetime(2026, 8, 23, tzinfo=UTC),
                )
            self.assertEqual(set(targets), {"prototypes", "calibrator"})
            for target in targets.values():
                artifact = json.loads((target / "artifact.json").read_text())
                self.assertFalse(artifact["mutations"]["assignments"])
            self.assertFalse(any(workspace.root.rglob("*assignments*")))


if __name__ == "__main__":
    unittest.main()
