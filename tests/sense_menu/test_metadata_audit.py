import json
from pathlib import Path
import tempfile
import unittest

from fluency.sense_menu.metadata_audit import (
    audit_wiktionary_snapshot,
    metadata_status,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class MetadataAuditTests(unittest.TestCase):
    def test_audit_separates_typed_features_from_the_classification_queue(self):
        with tempfile.TemporaryDirectory() as directory:
            snapshot = Path(directory) / "kaikki.org-dictionary-Portuguese.jsonl"
            rows = [{
                "lang_code": "pt",
                "senses": [{
                    "glosses": ["to test"],
                    "tags": ["perfective", "unmapped-local-tag"],
                    "topics": ["computing"],
                    "info_templates": [
                        {"name": "+obj", "expansion": "[with de 'of']"},
                        {"name": "unmapped-template", "args": {"1": "x"}},
                    ],
                }],
            }]
            snapshot.write_text(
                "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
            )
            report = audit_wiktionary_snapshot(
                REPOSITORY_ROOT,
                language="pt",
                policy_id="pt-v1",
                snapshot=snapshot,
            )

        self.assertEqual(report["sense_count"], 1)
        self.assertEqual(report["feature_families"]["grammar"], 1)
        self.assertEqual(report["feature_families"]["domain"], 1)
        self.assertEqual(report["feature_families"]["companion"], 1)
        self.assertEqual(
            {item["source_field"] for item in report["unclassified"]},
            {"tags", "info_templates"},
        )

    def test_status_is_generated_for_every_registered_language(self):
        report = metadata_status(REPOSITORY_ROOT)
        self.assertEqual(report["metadata_contract"], "sense-metadata/v1")
        self.assertEqual(len(report["languages"]), 9)
        self.assertTrue(all("snapshot" in row for row in report["languages"]))
        self.assertTrue(all(row["release_status"] == "not_checked" for row in report["languages"]))

    def test_status_detects_current_legacy_and_inactive_app_releases(self):
        with tempfile.TemporaryDirectory() as directory:
            app_root = Path(directory)
            (app_root / "config").mkdir()
            (app_root / "releases" / "pt").mkdir(parents=True)
            (app_root / "releases" / "fr").mkdir(parents=True)
            (app_root / "releases" / "pt" / "manifest.json").write_text(
                json.dumps({"metadata_contract": "sense-metadata/v1"}), encoding="utf-8"
            )
            (app_root / "releases" / "fr" / "manifest.json").write_text(
                json.dumps({"manifest_version": "release-manifest/v1"}), encoding="utf-8"
            )
            (app_root / "config" / "config.json").write_text(json.dumps({
                "languages": {
                    "portuguese": {"hasData": True, "releaseManifestPath": "releases/pt/manifest.json"},
                    "french": {"hasData": True, "releaseManifestPath": "releases/fr/manifest.json"},
                    "italian": {"hasData": False},
                }
            }), encoding="utf-8")
            rows = {
                row["language"]: row
                for row in metadata_status(REPOSITORY_ROOT, app_root=app_root)["languages"]
            }

        self.assertEqual(rows["pt"]["release_status"], "current")
        self.assertEqual(rows["fr"]["release_status"], "legacy")
        self.assertEqual(rows["it"]["release_status"], "inactive")
        self.assertEqual(rows["cs"]["release_status"], "missing")


if __name__ == "__main__":
    unittest.main()
