from pathlib import Path
import sys
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
sys.path.insert(0, str(SOURCE_ROOT))

from fluency.cli import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    build_parser,
    project_root,
    resolve_active_app_asset,
)


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

    def test_pipeline_plan_requires_an_explicit_profile(self) -> None:
        args = build_parser().parse_args(
            [
                "pipeline",
                "plan",
                "--workspace",
                "/tmp/fluency-workspace",
                "--profile",
                "/tmp/profile.json",
            ]
        )
        self.assertEqual(args.command, "pipeline")
        self.assertEqual(args.pipeline_command, "plan")
        self.assertEqual(args.profile, Path("/tmp/profile.json"))

    def test_pipeline_harvest_requires_an_explicit_run_and_source(self) -> None:
        args = build_parser().parse_args(
            [
                "pipeline",
                "harvest",
                "--workspace",
                "/tmp/fluency-workspace",
                "--run-id",
                "20260822T130000Z-1234abcd",
                "--source",
                "tatoeba=/tmp/fluency-workspace/raw/tatoeba/fr-en/snapshot",
            ]
        )
        self.assertEqual(args.pipeline_command, "harvest")
        self.assertEqual(
            args.source,
            ["tatoeba=/tmp/fluency-workspace/raw/tatoeba/fr-en/snapshot"],
        )

    def test_pipeline_sense_menu_requires_explicit_snapshot_identity(self) -> None:
        args = build_parser().parse_args(
            [
                "pipeline",
                "sense-menu",
                "--workspace",
                "/tmp/fluency-workspace",
                "--run-id",
                "20260822T130000Z-1234abcd",
                "--snapshot",
                "/tmp/fluency-workspace/raw/wiktionary/kaikki-french.jsonl.gz",
                "--snapshot-id",
                "enwiktionary-2026-08-05",
            ]
        )
        self.assertEqual(args.pipeline_command, "sense-menu")
        self.assertEqual(args.snapshot_id, "enwiktionary-2026-08-05")

    def test_pipeline_inventory_requires_explicit_snapshot_identity(self) -> None:
        args = build_parser().parse_args(
            [
                "pipeline",
                "inventory",
                "--workspace",
                "/tmp/fluency-workspace",
                "--run-id",
                "20260822T130000Z-1234abcd",
                "--snapshot",
                "/tmp/fluency-workspace/raw/frequency/lexique4/Lexique400.tsv",
                "--snapshot-id",
                "lexique-4.00-2026-02-10",
            ]
        )
        self.assertEqual(args.pipeline_command, "inventory")
        self.assertEqual(args.snapshot_id, "lexique-4.00-2026-02-10")

    def test_pipeline_wsd_import_requires_an_explicit_bundle(self) -> None:
        args = build_parser().parse_args(
            [
                "pipeline",
                "wsd-import",
                "--workspace",
                "/tmp/fluency-workspace",
                "--run-id",
                "20260822T130000Z-1234abcd",
                "--bundle",
                "/tmp/fluency-workspace/raw/wsd/fr-audit/bundle.json",
            ]
        )
        self.assertEqual(args.pipeline_command, "wsd-import")
        self.assertEqual(
            args.bundle,
            Path("/tmp/fluency-workspace/raw/wsd/fr-audit/bundle.json"),
        )

    def test_pipeline_run_release_is_explicit_and_inactive(self) -> None:
        args = build_parser().parse_args(
            [
                "pipeline",
                "build-run-release",
                "--workspace",
                "/tmp/fluency-workspace",
                "--run-id",
                "20260822T172017Z-651bcd8e",
                "--release-id",
                "fr-speech-real-audit-0001",
            ]
        )
        self.assertEqual(args.pipeline_command, "build-run-release")
        self.assertEqual(args.release_id, "fr-speech-real-audit-0001")

    def test_existing_app_data_path_resolves_through_active_release(self) -> None:
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as temporary:
            releases = Path(temporary) / "releases"
            root = releases / "fr" / "speech"
            release = root / "fr-speech-test-0001"
            (release / "app").mkdir(parents=True)
            (root / "active.json").write_text(
                json.dumps({"release_id": release.name}), encoding="utf-8"
            )
            (release / "manifest.json").write_text(
                json.dumps(
                    {
                        "app_contract": {
                            "index_path": "app/vocabulary.index.json",
                            "examples_path": "app/vocabulary.examples.json",
                        }
                    }
                ),
                encoding="utf-8",
            )
            expected = release / "app" / "vocabulary.index.json"
            self.assertEqual(
                resolve_active_app_asset(
                    releases, "/Data/French/vocabulary.index.json"
                ).resolve(),
                expected.resolve(),
            )

    def test_active_app_data_path_rejects_release_traversal(self) -> None:
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as temporary:
            releases = Path(temporary) / "releases"
            root = releases / "fr" / "speech"
            root.mkdir(parents=True)
            (root / "active.json").write_text(
                json.dumps({"release_id": "../../outside"}), encoding="utf-8"
            )
            resolved = resolve_active_app_asset(
                releases, "/Data/French/vocabulary.index.json"
            )
            self.assertEqual(resolved, root / ".invalid-active-app-asset")


if __name__ == "__main__":
    unittest.main()
