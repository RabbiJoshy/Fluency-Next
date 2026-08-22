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
SPANISH_PROFILE_PATH = REPOSITORY_ROOT / "config" / "pipelines" / "es" / "speech" / "audit-200x3.json"


class PipelinePlanningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = load_pipeline_profile(PROFILE_PATH)

    def test_profile_locks_fresh_surface_only_audit(self) -> None:
        self.assertEqual(self.profile["scope"]["surface_limit"], 200)
        self.assertEqual(self.profile["scope"]["examples_per_surface"], 3)
        self.assertEqual(self.profile["scope"]["shortfall_policy"], "publish_explicit")
        self.assertFalse(self.profile["identity"]["allow_lemma_identity"])
        self.assertFalse(self.profile["source_policy"]["allow_legacy_inputs"])
        self.assertEqual(
            self.profile["inventory"]["source_adapter"],
            "lexique4-surface-frequency/v1",
        )
        self.assertEqual(self.profile["inventory"]["lemma_role"], "excluded")
        self.assertEqual(self.profile["inventory"]["language_policy"], "fr-v1")
        self.assertEqual(self.profile["stage_order"], list(STAGE_ORDER))
        self.assertEqual(
            self.profile["sense_menu"]["source_adapter"],
            "wiktionary-sense-menu/v1",
        )
        self.assertEqual(self.profile["sense_menu"]["source_edition"], "enwiktionary")
        self.assertEqual(self.profile["sense_menu"]["gloss_language"], "en")
        self.assertEqual(self.profile["sense_menu"]["join_key"], "surface_card_id")
        self.assertEqual(self.profile["sense_menu"]["lemma_role"], "lookup_metadata_only")
        self.assertEqual(self.profile["harvest"]["source_policy"], "exclusive")
        self.assertEqual(self.profile["harvest"]["sources"], ["tatoeba"])
        self.assertEqual(self.profile["harvest"]["candidate_cap_per_surface"], 60)
        self.assertEqual(
            self.profile["wsd"]["strategy"],
            "language-adapted-closed-menu/v1",
        )
        self.assertEqual(self.profile["wsd"]["shared_profile"], "closed-menu-v1")
        self.assertEqual(self.profile["wsd"]["language_profile"], "fr-v1")
        self.assertEqual(self.profile["wsd"]["model_profile"], "fr-rehearsal-v1")
        self.assertEqual(
            self.profile["wsd"]["execution_status"],
            "blocked_pending_benchmark",
        )

    def test_profile_rejects_legacy_or_fallback_inputs(self) -> None:
        for field, value in (("allow_legacy_inputs", True), ("fallback_policy", "missing_only")):
            with self.subTest(field=field):
                changed = deepcopy(self.profile)
                changed["source_policy"][field] = value
                with self.assertRaises(PipelineProfileError):
                    validate_pipeline_profile(changed)

    def test_ready_wsd_requires_nonempty_model_pins(self) -> None:
        changed = deepcopy(self.profile)
        changed["wsd"]["execution_status"] = "ready"
        with self.assertRaises(PipelineProfileError):
            validate_pipeline_profile(changed)

    def test_spanish_profile_uses_shared_contracts_without_claiming_readiness(self) -> None:
        profile = load_pipeline_profile(SPANISH_PROFILE_PATH)
        self.assertEqual(profile["language"], "es")
        self.assertEqual(profile["identity"]["unit_type"], "surface")
        self.assertEqual(profile["inventory"]["source_adapter"], "recovered-surface-ranking/v1")
        self.assertEqual(
            profile["inventory"]["frequency_measure"],
            "recovered_corpus_count_upstream_unknown",
        )
        self.assertTrue(profile["source_policy"]["allow_recovered_inputs"])
        self.assertEqual(profile["sense_menu"]["source_adapter"], "spanishdict-sense-menu/v1")
        self.assertEqual(profile["sense_menu"]["source_edition"], "spanishdict-pinned-snapshot")
        self.assertEqual(profile["harvest"]["sources"], ["retained-opensubtitles"])
        self.assertEqual(profile["wsd"]["execution_status"], "blocked_pending_assets")
        self.assertEqual(profile["wsd"]["model_revisions"], {})

    def test_blocked_spanish_profile_cannot_claim_runnable_model_pins(self) -> None:
        changed = load_pipeline_profile(SPANISH_PROFILE_PATH)
        changed["wsd"]["model_revisions"] = {"gloss.model_revision": "unverified"}
        with self.assertRaises(PipelineProfileError):
            validate_pipeline_profile(changed)

    def test_recovered_permission_cannot_drift_from_inventory_adapter(self) -> None:
        changed = load_pipeline_profile(SPANISH_PROFILE_PATH)
        changed["source_policy"]["allow_recovered_inputs"] = False
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
            sense_contract = json.loads(
                (target / "stages/02_sense_menu/contract.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                sense_contract["source_adapter"]["output_schema"], "sense-menu/v1"
            )
            inventory_contract = json.loads(
                (target / "stages/01_inventory/contract.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                inventory_contract["source_adapter"]["source_adapter"],
                "lexique4-surface-frequency/v1",
            )
            harvest_contract = json.loads(
                (target / "stages/03_sentence_harvest/contract.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                harvest_contract["external_inputs"],
                ["fresh_tatoeba_source_snapshot"],
            )
            self.assertEqual(harvest_contract["method"]["source_policy"], "exclusive")
            selection_contract = json.loads(
                (target / "stages/05_example_selection/contract.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                selection_contract["requires_stage_outputs"],
                ["inventory", "sentence_harvest"],
            )


if __name__ == "__main__":
    unittest.main()
