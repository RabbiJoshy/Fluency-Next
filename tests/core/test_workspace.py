from pathlib import Path
import tempfile
import unittest

from fluency.core.workspace import REQUIRED_DIRECTORIES, Workspace


class WorkspaceTests(unittest.TestCase):
    def test_workspace_initialization_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "workspace"
            first = Workspace.initialize(root)
            second = Workspace.initialize(root)

            self.assertEqual(first.workspace_id, second.workspace_id)
            self.assertTrue((root / "workspace.json").is_file())
            self.assertTrue((root / "raw" / "README.md").is_file())
            for relative_path in REQUIRED_DIRECTORIES:
                self.assertTrue((root / relative_path).is_dir(), relative_path)

    def test_non_empty_unmarked_directory_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "workspace"
            root.mkdir()
            (root / "unexpected.txt").write_text("data", encoding="utf-8")
            with self.assertRaises(ValueError):
                Workspace.initialize(root)

    def test_doctor_checks_layout_and_code_separation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            workspace = Workspace.initialize(temporary_root / "workspace")
            code_root = temporary_root / "code"
            code_root.mkdir()

            diagnostics = workspace.doctor(code_root=code_root)
            self.assertTrue(all(item.ok for item in diagnostics), diagnostics)

            (code_root / "runs").mkdir()
            diagnostics = workspace.doctor(code_root=code_root)
            separation = next(
                item for item in diagnostics if item.name == "code/data separation"
            )
            self.assertFalse(separation.ok)


if __name__ == "__main__":
    unittest.main()

