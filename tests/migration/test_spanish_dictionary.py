from datetime import UTC, datetime
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fluency.core.hashing import file_content_id
from fluency.core.workspace import Workspace
from fluency.migration import spanish_dictionary
from fluency.migration.spanish_dictionary import migrate_spanish_dictionary_snapshot


def _source_repository(root: Path) -> tuple[Path, dict[str, str]]:
    repository = root / "old"
    cache = repository / "Data/Spanish/Senses/spanishdict"
    layers = repository / "Data/Spanish/layers"
    cache.mkdir(parents=True)
    layers.mkdir(parents=True)
    payloads = {
        cache / "surface_cache.json": {"hola": {"entry_lang": "es"}},
        cache / "headword_cache.json": {"hola": {"dictionary_analyses": []}},
        layers / "spanish_forms.json": {"hola": {}},
        layers / "conjugation_reverse.json": {"digo": [{"lemma": "decir"}]},
    }
    for path, payload in payloads.items():
        path.write_text(json.dumps(payload), encoding="utf-8")
    return repository, {
        path.name: file_content_id(path).removeprefix("sha256:")
        for path in payloads
    }


class SpanishDictionaryMigrationTests(unittest.TestCase):
    def test_pins_only_offline_inputs_with_exact_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository, hashes = _source_repository(root)
            workspace = Workspace.initialize(root / "workspace")
            with patch.object(spanish_dictionary, "EXPECTED_HASHES", hashes):
                target = migrate_spanish_dictionary_snapshot(
                    workspace,
                    source_repository=repository,
                    recovered_at=datetime(2026, 8, 22, 21, 40, tzinfo=UTC),
                )
            manifest = json.loads((target / "artifact.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["artifact_kind"], "dictionary_menu_source")
            self.assertEqual(manifest["provider"], "spanishdict")
            self.assertEqual(
                {item["path"] for item in manifest["content_files"]},
                set(hashes),
            )
            self.assertFalse(any(workspace.root.rglob("*assignment*")))
            self.assertFalse(any(workspace.root.rglob("sense-menu.json")))


if __name__ == "__main__":
    unittest.main()
