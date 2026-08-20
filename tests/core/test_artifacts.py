from pathlib import Path
import tempfile
import unittest

from fluency.core.artifacts import (
    artifact_directory,
    store_artifact_bytes,
    verify_artifact,
)
from fluency.core.workspace import Workspace


class ArtifactTests(unittest.TestCase):
    def test_identical_bytes_are_stored_once(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Workspace.initialize(Path(temporary) / "workspace")
            arguments = {
                "filename": "data.parquet",
                "media_type": "application/vnd.apache.parquet",
                "schema": "occurrence/v1",
                "created_by_stage": "s10_occurrences",
                "row_count": 2,
            }
            first = store_artifact_bytes(workspace, b"same bytes", **arguments)
            second = store_artifact_bytes(workspace, b"same bytes", **arguments)

            self.assertEqual(first.artifact_id, second.artifact_id)
            directory = artifact_directory(workspace, first.artifact_id)
            self.assertEqual((directory / "data.parquet").read_bytes(), b"same bytes")
            self.assertEqual(verify_artifact(workspace, first.artifact_id), first)
            objects = list((workspace.root / "objects" / "sha256").glob("*/*"))
            self.assertEqual(len(objects), 1)

    def test_different_bytes_receive_different_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Workspace.initialize(Path(temporary) / "workspace")
            common = {
                "filename": "data.json",
                "media_type": "application/json",
                "schema": "test/v1",
                "created_by_stage": "test_stage",
            }
            first = store_artifact_bytes(workspace, b"one", **common)
            second = store_artifact_bytes(workspace, b"two", **common)
            self.assertNotEqual(first.artifact_id, second.artifact_id)

    def test_identical_bytes_with_conflicting_metadata_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Workspace.initialize(Path(temporary) / "workspace")
            common = {
                "filename": "data.json",
                "media_type": "application/json",
                "created_by_stage": "test_stage",
            }
            store_artifact_bytes(
                workspace,
                b"same bytes",
                schema="sentence/v1",
                **common,
            )
            with self.assertRaises(ValueError):
                store_artifact_bytes(
                    workspace,
                    b"same bytes",
                    schema="occurrence/v1",
                    **common,
                )

    def test_unsafe_filenames_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Workspace.initialize(Path(temporary) / "workspace")
            with self.assertRaises(ValueError):
                store_artifact_bytes(
                    workspace,
                    b"unsafe",
                    filename="../data.bin",
                    media_type="application/octet-stream",
                    schema="test/v1",
                    created_by_stage="test_stage",
                )


if __name__ == "__main__":
    unittest.main()
