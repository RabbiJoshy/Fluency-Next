from datetime import UTC, datetime
import csv
import json
from pathlib import Path
import tempfile
import unittest

from fluency.core.workspace import Workspace
from fluency.inventory.runner import InventoryRunError, build_inventory_stage
from fluency.pipeline.planning import create_pipeline_plan, load_pipeline_profile


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = REPOSITORY_ROOT / "config/pipelines/fr/speech/rehearsal-20x3.json"


def _write_snapshot(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=["1_Mot", "4_Lemme", "5_Cgram", "11_FreqOrtho"],
            delimiter="\t",
        )
        writer.writeheader()
        writer.writerow(
            {"1_Mot": "ca", "4_Lemme": "ca", "5_Cgram": "NOM", "11_FreqOrtho": "2000"}
        )
        for index in range(30):
            writer.writerow(
                {
                    "1_Mot": f"mot{chr(97 + index // 26)}{chr(97 + index % 26)}",
                    "4_Lemme": f"ignored-{index}",
                    "5_Cgram": "NOM",
                    "11_FreqOrtho": str(1000 - index),
                }
            )
        writer.writerow(
            {"1_Mot": "motaa", "4_Lemme": "other-lemma", "5_Cgram": "VER", "11_FreqOrtho": "1000"}
        )
        writer.writerow(
            {"1_Mot": "two words", "4_Lemme": "ignored", "5_Cgram": "NOM", "11_FreqOrtho": "9999"}
        )


class InventoryRunnerTests(unittest.TestCase):
    def _build_run(self, root: Path):
        workspace = Workspace.initialize(root / "workspace")
        profile = load_pipeline_profile(PROFILE_PATH)
        run = create_pipeline_plan(
            workspace,
            profile,
            started_at=datetime(2026, 8, 22, 16, 0, tzinfo=UTC),
            suffix="89abcdef",
        )
        snapshot = workspace.root / "raw/frequency/lexique4/Lexique400.tsv"
        _write_snapshot(snapshot)
        return workspace, run, snapshot

    def test_builds_surface_only_inventory_and_never_imports_lemmas(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, run, snapshot = self._build_run(Path(directory))
            output = build_inventory_stage(
                REPOSITORY_ROOT,
                workspace,
                run_id=run.name,
                language="fr",
                mode="speech",
                frequency_snapshot=snapshot,
                snapshot_id="lexique-4.00-fixture",
                started_at=datetime(2026, 8, 22, 16, 5, tzinfo=UTC),
            )
            inventory = json.loads((output / "inventory.json").read_text(encoding="utf-8"))
            ranks = json.loads((output / "frequency-ranks.json").read_text(encoding="utf-8"))
            report = json.loads((output / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(len(inventory["cards"]), 20)
            self.assertEqual(inventory["cards"][0]["surface_key"], "motaa")
            self.assertNotIn("lemma", json.dumps(inventory))
            self.assertEqual(ranks["motaa"], 1)
            self.assertNotIn("ca", ranks)
            self.assertEqual(report["excluded_surfaces"][0]["surface"], "ca")
            self.assertEqual(
                report["excluded_surfaces"][0]["decision"],
                "exclude_without_redirect",
            )
            self.assertEqual(report["duplicate_analysis_rows"], 1)
            self.assertEqual(report["rejected_surface_shape"], 1)
            self.assertFalse((workspace.root / "releases/fr/speech/active.json").exists())
            with self.assertRaises(InventoryRunError):
                build_inventory_stage(
                    REPOSITORY_ROOT,
                    workspace,
                    run_id=run.name,
                    language="fr",
                    mode="speech",
                    frequency_snapshot=snapshot,
                    snapshot_id="lexique-4.00-fixture",
                )

    def test_rejects_frequency_snapshot_outside_workspace_raw(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace, run, _snapshot = self._build_run(root)
            outside = root / "legacy.tsv"
            _write_snapshot(outside)
            with self.assertRaisesRegex(InventoryRunError, "workspace raw"):
                build_inventory_stage(
                    REPOSITORY_ROOT,
                    workspace,
                    run_id=run.name,
                    language="fr",
                    mode="speech",
                    frequency_snapshot=outside,
                    snapshot_id="legacy",
                )


if __name__ == "__main__":
    unittest.main()
