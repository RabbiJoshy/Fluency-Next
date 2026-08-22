from datetime import UTC, datetime
import json
from pathlib import Path
import tempfile
import unittest

from fluency.core.identity import build_card_id
from fluency.core.workspace import Workspace
from fluency.pipeline.planning import create_pipeline_plan, load_pipeline_profile
from fluency.sense_menu.runner import SenseMenuRunError, build_sense_menu_stage


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = REPOSITORY_ROOT / "config/pipelines/fr/speech/rehearsal-20x3.json"
SURFACES = (
    "amour", "avec", "bonjour", "chat", "dans", "encore", "femme", "grand",
    "homme", "ici", "jamais", "jour", "maison", "monde", "nuit", "petit",
    "prendre", "sans", "temps", "voir",
)


class SenseMenuRunnerTests(unittest.TestCase):
    def _build_run(self, root: Path):
        workspace = Workspace.initialize(root / "workspace")
        profile = load_pipeline_profile(PROFILE_PATH)
        run = create_pipeline_plan(
            workspace,
            profile,
            started_at=datetime(2026, 8, 22, 15, 0, tzinfo=UTC),
            suffix="5678abcd",
        )
        inventory_root = run / "stages/01_inventory/output"
        inventory_root.mkdir(parents=True)
        cards = [
            {
                "card_id": build_card_id("fr", surface),
                "surface_key": surface,
                "display_form": surface,
                "rank": rank,
            }
            for rank, surface in enumerate(SURFACES, start=1)
        ]
        (inventory_root / "inventory.json").write_text(
            json.dumps(
                {
                    "inventory_version": "surface-inventory/v1",
                    "language": "fr",
                    "cards": cards,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        snapshot = workspace.root / "raw/wiktionary/kaikki-french.jsonl"
        snapshot.parent.mkdir(parents=True)
        with snapshot.open("w", encoding="utf-8") as stream:
            for surface in SURFACES:
                stream.write(
                    json.dumps(
                        {
                            "word": surface,
                            "lang_code": "fr",
                            "pos": "noun",
                            "senses": [
                                {
                                    "id": f"en-{surface}-fr-noun-fixture",
                                    "glosses": [f"English gloss for {surface}"],
                                }
                            ],
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        return workspace, run, snapshot

    def test_builds_run_owned_menu_without_activating_anything(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, run, snapshot = self._build_run(Path(directory))
            output = build_sense_menu_stage(
                REPOSITORY_ROOT,
                workspace,
                run_id=run.name,
                language="fr",
                mode="speech",
                dictionary_snapshot=snapshot,
                snapshot_id="fixture-2026-08",
                started_at=datetime(2026, 8, 22, 15, 5, tzinfo=UTC),
            )
            menu = json.loads((output / "sense-menu.json").read_text(encoding="utf-8"))
            report = json.loads((output / "report.json").read_text(encoding="utf-8"))
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(len(menu["cards"]), 20)
            self.assertEqual(report["cards_ready"], 20)
            self.assertEqual(report["cards_without_menu"], 0)
            self.assertEqual(report["fallbacks"], [])
            self.assertIn("dictionary_snapshot", manifest["inputs"])
            contract = json.loads(
                (run / "stages/02_sense_menu/contract.json").read_text(encoding="utf-8")
            )
            self.assertEqual(contract["status"], "complete")
            self.assertFalse((workspace.root / "releases/fr/speech/active.json").exists())
            with self.assertRaises(SenseMenuRunError):
                build_sense_menu_stage(
                    REPOSITORY_ROOT,
                    workspace,
                    run_id=run.name,
                    language="fr",
                    mode="speech",
                    dictionary_snapshot=snapshot,
                    snapshot_id="fixture-2026-08",
                )

    def test_rejects_dictionary_snapshot_outside_workspace_raw(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace, run, snapshot = self._build_run(root)
            outside = root / "old-french-data.jsonl"
            outside.write_bytes(snapshot.read_bytes())
            with self.assertRaisesRegex(SenseMenuRunError, "workspace raw"):
                build_sense_menu_stage(
                    REPOSITORY_ROOT,
                    workspace,
                    run_id=run.name,
                    language="fr",
                    mode="speech",
                    dictionary_snapshot=outside,
                    snapshot_id="legacy-copy",
                )


if __name__ == "__main__":
    unittest.main()
