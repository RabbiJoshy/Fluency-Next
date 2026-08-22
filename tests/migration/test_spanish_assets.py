from datetime import UTC, datetime
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from fluency.core.hashing import file_content_id
from fluency.core.workspace import Workspace
from fluency.inventory.runner import build_inventory_stage
from fluency.harvest.runner import harvest_run_stage
from fluency.migration import spanish_assets
from fluency.migration.spanish_assets import migrate_spanish_retained_assets
from fluency.pipeline.planning import create_pipeline_plan, load_pipeline_profile


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = REPOSITORY_ROOT / "config/pipelines/es/speech/rehearsal-20x3.json"


def _write_npy(path: Path, rows: int, columns: int) -> None:
    header = repr(
        {"descr": "<f2", "fortran_order": False, "shape": (rows, columns)}
    ).encode("latin1")
    prefix = b"\x93NUMPY\x01\x00"
    padding = (16 - ((len(prefix) + 2 + len(header) + 1) % 16)) % 16
    header = header + b" " * padding + b"\n"
    path.write_bytes(prefix + struct.pack("<H", len(header)) + header + b"\x00\x00" * rows * columns)


def _build_source(root: Path) -> tuple[Path, dict[str, str]]:
    source = root / "old"
    layers = source / "Data/Spanish/layers"
    (layers / "subtitles").mkdir(parents=True)
    (layers / "sense_vectors").mkdir(parents=True)
    inventory = [
        {
            "word": f"palabra{chr(97 + index // 26)}{chr(97 + index % 26)}",
            "corpus_count": 1_000 - index,
            "known_lemmas": ["ignored"],
        }
        for index in range(25)
    ]
    (layers / "word_inventory.json").write_text(json.dumps(inventory), encoding="utf-8")
    (layers / "word_inventory.json.meta.json").write_text(
        json.dumps({"step_name": "fixture"}), encoding="utf-8"
    )
    sentences = [
        {
            "id": "sentence-a",
            "es": "Palabraaa aparece en esta frase.",
            "en": "The first word appears in this sentence.",
            "provenance": {"corpus": "opensubtitles"},
        },
        {
            "id": "sentence-b",
            "es": "Palabraab también aparece aquí ahora.",
            "en": "The second word also appears here now.",
            "provenance": {"corpus": "opensubtitles"},
        },
    ]
    (layers / "subtitles/sentence_bank.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in sentences), encoding="utf-8"
    )
    (layers / "subtitles/word_candidates.json").write_text(
        json.dumps(
            {
                "palabraaa": {"clean": ["sentence-a"], "held": ["sentence-b"]},
                "palabraab": {"clean": ["sentence-b"], "held": []},
            }
        ),
        encoding="utf-8",
    )
    (layers / "subtitles/harvest_manifest.json").write_text(
        json.dumps({"run_id": "fixture"}), encoding="utf-8"
    )
    _write_npy(layers / "sense_vectors/vec.npy", 2, 3)
    (layers / "sense_vectors/vec_index.json").write_text(
        json.dumps({"first": 0, "second": 1}), encoding="utf-8"
    )
    (layers / "sense_vectors/manifest.json").write_text(
        json.dumps({"model": "gemini-embedding-001"}), encoding="utf-8"
    )
    mapping = {
        "inventory/word_inventory.json": layers / "word_inventory.json",
        "inventory/word_inventory.json.meta.json": layers / "word_inventory.json.meta.json",
        "sentences/sentence_bank.jsonl": layers / "subtitles/sentence_bank.jsonl",
        "sentences/word_candidates.json": layers / "subtitles/word_candidates.json",
        "sentences/harvest_manifest.json": layers / "subtitles/harvest_manifest.json",
        "embeddings/vec.npy": layers / "sense_vectors/vec.npy",
        "embeddings/vec_index.json": layers / "sense_vectors/vec_index.json",
        "embeddings/manifest.json": layers / "sense_vectors/manifest.json",
    }
    hashes = {
        name: file_content_id(path).removeprefix("sha256:")
        for name, path in mapping.items()
    }
    return source, hashes


class SpanishAssetMigrationTests(unittest.TestCase):
    def test_migrates_only_approved_sources_and_builds_quick_surface_inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, hashes = _build_source(root)
            workspace = Workspace.initialize(root / "workspace")
            with (
                patch.object(spanish_assets, "EXPECTED_HASHES", hashes),
                patch.object(spanish_assets, "EXPECTED_SURFACE_COUNT", 25),
                patch.object(spanish_assets, "EXPECTED_SENTENCE_COUNT", 2),
                patch.object(spanish_assets, "EXPECTED_CANDIDATE_SURFACE_COUNT", 2),
                patch.object(spanish_assets, "EXPECTED_EMBEDDING_COUNT", 2),
                patch.object(spanish_assets, "EXPECTED_EMBEDDING_DIMENSIONS", 3),
            ):
                targets = migrate_spanish_retained_assets(
                    workspace,
                    source_repository=source,
                    recovered_at=datetime(2026, 8, 22, 21, 0, tzinfo=UTC),
                )
            self.assertEqual(set(targets), {"inventory", "sentences", "embeddings"})
            for target in targets.values():
                self.assertTrue((target / "artifact.json").is_file())
            self.assertFalse(any(workspace.root.rglob("*assignment*")))

            profile = load_pipeline_profile(PROFILE_PATH)
            run = create_pipeline_plan(
                workspace,
                profile,
                started_at=datetime(2026, 8, 22, 21, 5, tzinfo=UTC),
                suffix="55667788",
            )
            output = build_inventory_stage(
                REPOSITORY_ROOT,
                workspace,
                run_id=run.name,
                language="es",
                mode="speech",
                frequency_snapshot=targets["inventory"],
                snapshot_id="fluency-2026-07-28-surface-ranking-v1",
                started_at=datetime(2026, 8, 22, 21, 6, tzinfo=UTC),
            )
            inventory = json.loads((output / "inventory.json").read_text(encoding="utf-8"))
            report = json.loads((output / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(len(inventory["cards"]), 20)
            self.assertEqual(inventory["cards"][0]["surface_key"], "palabraaa")
            self.assertNotIn("lemma", json.dumps(inventory))
            self.assertEqual(report["provenance_status"], "reconstructed")
            self.assertFalse((workspace.root / "releases/es/speech/active.json").exists())

            harvest_output = harvest_run_stage(
                REPOSITORY_ROOT,
                workspace,
                run_id=run.name,
                language="es",
                mode="speech",
                source_snapshots={"retained-opensubtitles": targets["sentences"]},
                started_at=datetime(2026, 8, 22, 21, 7, tzinfo=UTC),
            )
            harvest_report = json.loads(
                (harvest_output / "report.json").read_text(encoding="utf-8")
            )
            self.assertEqual(harvest_report["records_scanned"], 2)
            self.assertEqual(
                harvest_report["sources"][0]["adapter"],
                "retained-sentence-bank/v1",
            )
            self.assertEqual(harvest_report["records_with_inventory_match"], 2)
            self.assertFalse((workspace.root / "releases/es/speech/active.json").exists())


if __name__ == "__main__":
    unittest.main()
