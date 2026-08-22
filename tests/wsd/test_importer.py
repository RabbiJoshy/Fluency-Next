from datetime import UTC, datetime
import json
from pathlib import Path
import tempfile
import unittest

from fluency.core.hashing import content_id, file_content_id
from fluency.core.identity import create_card_record
from fluency.core.workspace import Workspace
from fluency.pipeline.planning import create_pipeline_plan, load_pipeline_profile
from fluency.release.io import json_bytes
from fluency.wsd.contracts import SelectedTuple, WSDAssignment
from fluency.wsd.importer import WSDAssignmentImportError, import_wsd_assignments
from fluency.wsd.menus import build_analysis_id


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = REPOSITORY_ROOT / "config/pipelines/fr/speech/rehearsal-20x3.json"


class WSDImporterTests(unittest.TestCase):
    def _fixture(self, root: Path):
        workspace = Workspace.initialize(root / "workspace")
        run = create_pipeline_plan(
            workspace,
            load_pipeline_profile(PROFILE_PATH),
            started_at=datetime(2026, 8, 22, 19, 0, tzinfo=UTC),
            suffix="1234abcd",
        )
        card = create_card_record("fr", "veux")
        sentence_id = "sentence_" + "1" * 32
        analysis_id = build_analysis_id(
            card_id=card.card_id,
            source_adapter="wiktionary-sense-menu/v1",
            source_analysis_key="fr:vouloir:verb",
        )
        outputs = {
            "inventory": run / "stages/01_inventory/output/inventory.json",
            "sense_menu": run / "stages/02_sense_menu/output/sense-menu.json",
            "candidates": run / "stages/03_sentence_harvest/output/candidates.json",
            "sentence_bank": run / "stages/03_sentence_harvest/output/sentence-bank.jsonl",
        }
        for stage in ("01_inventory", "02_sense_menu", "03_sentence_harvest"):
            stage_root = run / f"stages/{stage}/output"
            stage_root.mkdir(parents=True)
            (stage_root / "manifest.json").write_text(
                json.dumps({"status": "complete"}), encoding="utf-8"
            )
        outputs["inventory"].write_bytes(
            json_bytes({"cards": [{"card_id": card.card_id, "display_form": "veux", "rank": 1}]})
        )
        outputs["sense_menu"].write_bytes(
            json_bytes(
                {
                    "cards": [
                        {
                            "card_id": card.card_id,
                            "surface_form": "veux",
                            "analyses": [
                                {
                                    "menu_analysis_id": analysis_id,
                                    "headword": "vouloir",
                                    "part_of_speech": "verb",
                                    "senses": [{"sense_id": "sense-want"}],
                                }
                            ],
                        }
                    ]
                }
            )
        )
        outputs["candidates"].write_bytes(
            json_bytes(
                {
                    "cards": [
                        {
                            "card_id": card.card_id,
                            "display_form": "veux",
                            "candidates": [{"sentence_id": sentence_id, "metrics": {"score": 0}}],
                        }
                    ]
                }
            )
        )
        outputs["sentence_bank"].write_text(
            json.dumps({"sentence_id": sentence_id}) + "\n", encoding="utf-8"
        )
        model_revisions = {"gloss": "fixture-gloss@1"}
        assignment = WSDAssignment(
            card_id=card.card_id,
            surface_form="veux",
            sentence_id=sentence_id,
            status="assigned",
            sense_menu_content_id=file_content_id(outputs["sense_menu"]),
            menu_analysis_id=analysis_id,
            selected_sense_id="sense-want",
            selected_tuple=SelectedTuple("vouloir", "verb"),
            decision_path=("gloss",),
            evidence={"score": 0.9},
            confidence=0.9,
            model_revisions=model_revisions,
        )
        bundle = {
            "bundle_version": "wsd-assignment-bundle/v1",
            "run_id": run.name,
            "language": "fr",
            "mode": "speech",
            "coverage": "complete_candidate_pool",
            "method": {
                "profile_id": "fixture-wsd-v1",
                "implementation_version": "fixture/v1",
                "implementation_content_id": content_id(b"fixture implementation"),
                "model_revisions": model_revisions,
                "random_seed": 7,
            },
            "inputs": {name: file_content_id(path) for name, path in outputs.items()},
            "assignments": [assignment.to_dict()],
        }
        bundle_path = workspace.root / "raw/wsd/fixture/bundle.json"
        bundle_path.parent.mkdir(parents=True)
        bundle_path.write_bytes(json_bytes(bundle))
        return workspace, run, bundle_path, bundle

    def test_publishes_only_exact_complete_external_assignments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace, run, bundle_path, _ = self._fixture(Path(directory))
            output = import_wsd_assignments(
                workspace,
                run_id=run.name,
                language="fr",
                mode="speech",
                bundle_path=bundle_path,
                started_at=datetime(2026, 8, 22, 19, 5, tzinfo=UTC),
            )
            report = json.loads((output / "report.json").read_text(encoding="utf-8"))
            method = json.loads((output / "method.json").read_text(encoding="utf-8"))
            records = [
                json.loads(line)
                for line in (output / "assignments.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(report["assignment_counts"]["assigned"], 1)
            self.assertEqual(report["fallbacks"], [])
            self.assertEqual(method["method"]["profile_id"], "fixture-wsd-v1")
            self.assertEqual(records[0]["selected_sense_id"], "sense-want")
            contract = json.loads(
                (run / "stages/04_wsd_assignments/contract.json").read_text(encoding="utf-8")
            )
            self.assertEqual(contract["status"], "complete")
            with self.assertRaisesRegex(WSDAssignmentImportError, "already exists"):
                import_wsd_assignments(
                    workspace,
                    run_id=run.name,
                    language="fr",
                    mode="speech",
                    bundle_path=bundle_path,
                )

    def test_rejects_incomplete_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace, run, bundle_path, bundle = self._fixture(Path(directory))
            bundle["assignments"] = []
            bundle_path.write_bytes(json_bytes(bundle))
            with self.assertRaisesRegex(WSDAssignmentImportError, "coverage is incomplete"):
                import_wsd_assignments(
                    workspace,
                    run_id=run.name,
                    language="fr",
                    mode="speech",
                    bundle_path=bundle_path,
                )

    def test_rejects_stale_upstream_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace, run, bundle_path, bundle = self._fixture(Path(directory))
            bundle["inputs"]["sense_menu"] = content_id(b"old menu")
            bundle_path.write_bytes(json_bytes(bundle))
            with self.assertRaisesRegex(WSDAssignmentImportError, "input hashes"):
                import_wsd_assignments(
                    workspace,
                    run_id=run.name,
                    language="fr",
                    mode="speech",
                    bundle_path=bundle_path,
                )

    def test_rejects_bundle_outside_workspace_raw_wsd(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace, run, _, bundle = self._fixture(root)
            outside = root / "old-repo-assignment.json"
            outside.write_bytes(json_bytes(bundle))
            with self.assertRaisesRegex(WSDAssignmentImportError, "raw/wsd"):
                import_wsd_assignments(
                    workspace,
                    run_id=run.name,
                    language="fr",
                    mode="speech",
                    bundle_path=outside,
                )

    def test_rejects_malformed_assignment_types_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace, run, bundle_path, bundle = self._fixture(Path(directory))
            bundle["assignments"][0]["card_id"] = 7
            bundle_path.write_bytes(json_bytes(bundle))
            with self.assertRaisesRegex(
                WSDAssignmentImportError, "invalid WSD assignment at index 0"
            ):
                import_wsd_assignments(
                    workspace,
                    run_id=run.name,
                    language="fr",
                    mode="speech",
                    bundle_path=bundle_path,
                )


if __name__ == "__main__":
    unittest.main()
