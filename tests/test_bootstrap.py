from pathlib import Path
import sys
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
sys.path.insert(0, str(SOURCE_ROOT))

from fluency.cli import DEFAULT_HOST, DEFAULT_PORT, build_parser, project_root


class BootstrapTests(unittest.TestCase):
    def test_project_root_contains_app(self) -> None:
        self.assertEqual(project_root(), REPOSITORY_ROOT)
        self.assertTrue((project_root() / "app" / "index.html").is_file())

    def test_dev_defaults_are_local_only(self) -> None:
        args = build_parser().parse_args(["dev"])
        self.assertEqual(args.host, DEFAULT_HOST)
        self.assertEqual(args.port, DEFAULT_PORT)

    def test_dev_options_can_be_overridden(self) -> None:
        args = build_parser().parse_args(
            ["dev", "--host", "127.0.0.2", "--port", "5000"]
        )
        self.assertEqual(args.host, "127.0.0.2")
        self.assertEqual(args.port, 5000)

    def test_workspace_command_accepts_explicit_path(self) -> None:
        args = build_parser().parse_args(
            ["workspace", "doctor", "--path", "/tmp/fluency-workspace"]
        )
        self.assertEqual(args.command, "workspace")
        self.assertEqual(args.workspace_command, "doctor")
        self.assertEqual(args.path, "/tmp/fluency-workspace")

    def test_pilot_build_accepts_explicit_workspace(self) -> None:
        args = build_parser().parse_args(
            ["pilot", "build", "--workspace", "/tmp/fluency-workspace"]
        )
        self.assertEqual(args.command, "pilot")
        self.assertEqual(args.pilot_command, "build")
        self.assertEqual(args.workspace, "/tmp/fluency-workspace")


if __name__ == "__main__":
    unittest.main()
