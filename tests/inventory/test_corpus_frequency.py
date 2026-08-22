from datetime import UTC, datetime
import json
from pathlib import Path
import tempfile
import unittest

from fluency.core.workspace import Workspace
from fluency.inventory.corpus_frequency import (
    CorpusFrequencyError,
    compile_corpus_frequency_snapshot,
    load_corpus_frequency_snapshot,
)
from fluency.inventory.runner import build_inventory_stage
from fluency.pipeline.planning import create_pipeline_plan, load_pipeline_profile


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = REPOSITORY_ROOT / "config/pipelines/es/speech/rehearsal-20x3.json"


def _fixture_lines() -> list[str]:
    surfaces = [
        "qué", "de", "no", "a", "la", "el", "es", "y", "en", "lo",
        "un", "por", "me", "una", "te", "los", "se", "con", "para", "dámelo",
        "árbol", "pingüino", "corazón", "acción", "mañana",
    ]
    lines = []
    for index, surface in enumerate(surfaces):
        lines.append(" ".join([surface] * (len(surfaces) - index)))
    lines.append("QUÉ Qué qué")
    lines.append("<i>ruido invisible frecuencia falsa</i>")
    return lines


class CorpusFrequencyTests(unittest.TestCase):
    def _compile(self, root: Path):
        workspace = Workspace.initialize(root / "workspace")
        corpus = workspace.root / "raw/corpora/es/opensubtitles/es.txt"
        corpus.parent.mkdir(parents=True, exist_ok=True)
        corpus.write_text("\n".join(_fixture_lines()) + "\n", encoding="utf-8")
        snapshot = compile_corpus_frequency_snapshot(
            REPOSITORY_ROOT,
            workspace,
            language="es",
            corpus_path=corpus,
            snapshot_id="opensubtitles-es-fixture-v1",
            provider="opensubtitles",
            created_at=datetime(2026, 8, 22, 20, 0, tzinfo=UTC),
        )
        return workspace, corpus, snapshot

    def test_compiles_once_with_hashes_accents_and_line_rejections(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, corpus, snapshot = self._compile(Path(directory))
            manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
            compiled = load_corpus_frequency_snapshot(
                snapshot,
                expected_language="es",
                expected_snapshot_id="opensubtitles-es-fixture-v1",
            )
            self.assertEqual(manifest["source_lines"], len(_fixture_lines()))
            self.assertEqual(manifest["rejected_lines"], 1)
            self.assertEqual(manifest["source_bytes"], corpus.stat().st_size)
            self.assertTrue(manifest["source_content_id"].startswith("sha256:"))
            self.assertIn("dámelo", compiled.counts)
            self.assertIn("pingüino", compiled.counts)
            self.assertNotIn("ruido", compiled.counts)
            self.assertEqual(compiled.counts["qué"], 28)
            with self.assertRaises(CorpusFrequencyError):
                compile_corpus_frequency_snapshot(
                    REPOSITORY_ROOT,
                    workspace,
                    language="es",
                    corpus_path=corpus,
                    snapshot_id="opensubtitles-es-fixture-v1",
                    provider="opensubtitles",
                )

    def test_compiled_snapshot_feeds_quick_run_owned_surface_inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, _corpus, snapshot = self._compile(Path(directory))
            profile = load_pipeline_profile(PROFILE_PATH)
            run = create_pipeline_plan(
                workspace,
                profile,
                started_at=datetime(2026, 8, 22, 20, 5, tzinfo=UTC),
                suffix="11223344",
            )
            output = build_inventory_stage(
                REPOSITORY_ROOT,
                workspace,
                run_id=run.name,
                language="es",
                mode="speech",
                frequency_snapshot=snapshot,
                snapshot_id="opensubtitles-es-fixture-v1",
                started_at=datetime(2026, 8, 22, 20, 6, tzinfo=UTC),
            )
            inventory = json.loads((output / "inventory.json").read_text(encoding="utf-8"))
            report = json.loads((output / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(len(inventory["cards"]), 20)
            self.assertEqual(inventory["cards"][0]["surface_key"], "qué")
            self.assertNotIn("lemma", json.dumps(inventory))
            self.assertEqual(report["source_adapter"], "corpus-surface-frequency/v1")
            self.assertEqual(report["provenance_status"], "reconstructed")
            self.assertEqual(report["rejected_lines"], 1)
            self.assertFalse((workspace.root / "releases/es/speech/active.json").exists())

    def test_rejects_unpinned_corpus_outside_workspace_raw(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = Workspace.initialize(root / "workspace")
            corpus = root / "outside.txt"
            corpus.write_text("hola mundo\n", encoding="utf-8")
            with self.assertRaisesRegex(CorpusFrequencyError, "workspace raw"):
                compile_corpus_frequency_snapshot(
                    REPOSITORY_ROOT,
                    workspace,
                    language="es",
                    corpus_path=corpus,
                    snapshot_id="outside-v1",
                    provider="opensubtitles",
                )


if __name__ == "__main__":
    unittest.main()
