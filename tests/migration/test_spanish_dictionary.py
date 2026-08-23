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
        layers / "sense_menu/spanishdict.json": {
            "hola": [
                {
                    "headword": "hola",
                    "senses": {
                        "abc": {"pos": "INTJ", "translation": "hello"}
                    },
                }
            ]
        },
    }
    for path, payload in payloads.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
    return repository, {
        "surface_cache.json": file_content_id(cache / "surface_cache.json").removeprefix("sha256:"),
        "headword_cache.json": file_content_id(cache / "headword_cache.json").removeprefix("sha256:"),
        "spanish_forms.json": file_content_id(layers / "spanish_forms.json").removeprefix("sha256:"),
        "conjugation_reverse.json": file_content_id(layers / "conjugation_reverse.json").removeprefix("sha256:"),
        "normalized_menu.json": file_content_id(
            layers / "sense_menu/spanishdict.json"
        ).removeprefix("sha256:"),
    }


class SpanishDictionaryMigrationTests(unittest.TestCase):
    def test_pins_complete_offline_menu_inputs_with_exact_hashes(self):
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
            self.assertEqual(manifest["coverage"]["normalized_menu_surfaces"], 1)
            self.assertFalse(any(workspace.root.rglob("*assignment*")))
            self.assertFalse(any(workspace.root.rglob("sense-menu.json")))


if __name__ == "__main__":
    unittest.main()
