import json
from pathlib import Path
import tempfile
import unittest

from fluency.core.identity import build_card_id
from fluency.core.workspace import Workspace
from fluency.migration.legacy_identity import (
    build_legacy_crosswalk,
    write_legacy_crosswalk,
)


class LegacyIdentityCrosswalkTests(unittest.TestCase):
    def test_crosswalk_collapses_duplicates_and_keeps_collision_ambiguous(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inventory = root / "inventory.json"
            current = root / "current.json"
            older = root / "older.json"
            migration = root / "migration.json"
            inventory.write_text(
                json.dumps(
                    [
                        {"word": "una"},
                        {"word": "atrás"},
                        {"word": "sientes"},
                        {"word": "de"},
                        {"word": "dele"},
                    ]
                ),
                encoding="utf-8",
            )
            current.write_text(
                json.dumps(
                    [
                        {"id": "surface1", "word": "una"},
                        {"id": "lemma1", "word": "una"},
                        {"id": "collision", "word": "sientes"},
                        {
                            "id": "de1",
                            "word": "de",
                            "alias_ids": [
                                {"id": "dele1", "surface": "dele", "kind": "clitic"}
                            ],
                        },
                    ]
                ),
                encoding="utf-8",
            )
            older.write_text(
                json.dumps([{"id": "collision", "word": "atrás"}]),
                encoding="utf-8",
            )
            migration.write_text(
                json.dumps(
                    {
                        "lemma1": "surface1",
                        "surface1": "lemma1",
                        "unknown_collision": "collision",
                    }
                ),
                encoding="utf-8",
            )

            cards, registry, report = build_legacy_crosswalk(
                language="es",
                mode="speech",
                inventory_path=inventory,
                legacy_index_paths=[current, older],
                legacy_migration_path=migration,
            )
            aliases = registry.by_key()

            self.assertEqual(len(cards), 5)
            self.assertEqual(aliases["es0surface1"].surface_key, "una")
            self.assertEqual(aliases["es0lemma1"].surface_key, "una")
            self.assertEqual(aliases["es0dele1"].surface_key, "dele")
            self.assertEqual(
                aliases["es0dele1"].canonical_card_id,
                build_card_id("es", "dele"),
            )
            self.assertEqual(aliases["es0collision"].status, "ambiguous")
            self.assertEqual(
                aliases["es0collision"].candidate_surface_keys,
                ("atrás", "sientes"),
            )
            self.assertEqual(
                aliases["es0unknown_collision"].status, "ambiguous"
            )
            self.assertEqual(report["migration_traversal"]["cycle_keys"], 2)
            self.assertEqual(report["sheet_rows_modified"], 0)

    def test_missing_inventory_duplicates_fail_loudly(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inventory = root / "inventory.json"
            index = root / "index.json"
            migration = root / "migration.json"
            inventory.write_text(
                json.dumps([{"word": "UNA"}, {"word": "una"}]),
                encoding="utf-8",
            )
            index.write_text(json.dumps([]), encoding="utf-8")
            migration.write_text(json.dumps({}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate normalized"):
                build_legacy_crosswalk(
                    language="es",
                    mode="speech",
                    inventory_path=inventory,
                    legacy_index_paths=[index],
                    legacy_migration_path=migration,
                )

    def test_workspace_output_is_immutable_and_declares_no_remote_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = Workspace.initialize(root / "workspace")
            inventory = root / "inventory.json"
            index = root / "index.json"
            migration = root / "migration.json"
            inventory.write_text(json.dumps([{"word": "una"}]), encoding="utf-8")
            index.write_text(
                json.dumps([{"id": "legacy1", "word": "una"}]),
                encoding="utf-8",
            )
            migration.write_text(json.dumps({}), encoding="utf-8")

            output = write_legacy_crosswalk(
                workspace,
                migration_id="test-crosswalk-v1",
                language="es",
                mode="speech",
                inventory_path=inventory,
                legacy_index_paths=[index],
                legacy_migration_path=migration,
            )
            manifest = json.loads(
                (output / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                manifest["mutations"],
                {
                    "source_files": False,
                    "google_sheets": False,
                    "active_release": False,
                },
            )
            with self.assertRaises(FileExistsError):
                write_legacy_crosswalk(
                    workspace,
                    migration_id="test-crosswalk-v1",
                    language="es",
                    mode="speech",
                    inventory_path=inventory,
                    legacy_index_paths=[index],
                    legacy_migration_path=migration,
                )


if __name__ == "__main__":
    unittest.main()
