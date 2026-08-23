import json
from pathlib import Path
import tempfile
import unittest

from fluency.core.hashing import file_content_id
from fluency.core.workspace import Workspace
from fluency.lyrics.corpus_assemble import assemble_lyrics_corpus


class LyricsCorpusAssemblyTests(unittest.TestCase):
    def test_merges_artist_decks_against_one_shared_exact_sense_master(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = Workspace.initialize(root / "workspace")
            plan_id = "fixture-plan"
            method = "fixture-method"
            plan_path = workspace.root / "raw/lyrics/corpus-plans" / plan_id / "manifest.json"
            plan_path.parent.mkdir(parents=True)
            sources = []
            for number, slug in enumerate(("artist-a", "artist-b"), start=1):
                sources.append({
                    "artist_slug": slug, "artist_name": slug.title(),
                    "songs": [{
                        "source_record_id": str(number), "title": f"Song {number}",
                        "credited_artist": slug.title(), "planned_run_id": f"run-{number}",
                    }],
                })
            plan = {
                "plan_version": "lyrics-corpus-plan/v1", "plan_id": plan_id,
                "status": "planned_sources_only", "language": "es",
                "included_sources": sources, "totals": {"songs": 2},
            }
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            corpus = workspace.root / "runs/es/lyrics-corpora" / plan_id
            branch = corpus / "methods" / method / "songs"
            report_path = corpus / "consolidation-report.json"
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps({
                "status": "complete", "plan_id": plan_id,
                "plan_content_id": file_content_id(plan_path), "song_run_count": 2,
                "method_profile_id": method,
                "method_branch": branch.relative_to(workspace.root).as_posix(),
            }), encoding="utf-8")

            app_id = "aaaaaaaa"
            card_id = "card_es_" + "a" * 32
            for number, slug in enumerate(("artist-a", "artist-b"), start=1):
                run_id = f"run-{number}"
                song_branch = branch / run_id
                consolidation = song_branch / "consolidation"
                wsd = song_branch / "wsd_results"
                assembly = song_branch / "app_assembly"
                consolidation.mkdir(parents=True)
                wsd.mkdir()
                assembly.mkdir()
                (consolidation / "cards.jsonl").write_text("{}\n", encoding="utf-8")
                (consolidation / "examples.jsonl").write_text("{}\n", encoding="utf-8")
                (wsd / "results.jsonl").write_text("{}\n", encoding="utf-8")
                sense_assignment = f"sense_assignment_{number}"
                index = [{
                    "id": app_id, "surface_card_id": card_id, "corpus_count": 2,
                    "sense_frequencies": [1.0], "sense_methods": [method],
                    "sense_confidence": [0.8], "sense_band": ["medium"],
                }]
                example = {
                    "example_id": f"example-{number}", "sense_assignment_id": sense_assignment,
                    "run_id": run_id, "song": str(number),
                }
                examples = {app_id: {"m": [[example]]}}
                master = {app_id: {
                    "word": "casa", "display_form": "casa", "surface_card_id": card_id,
                    "lemma": None, "senses": [{
                        "sense_id": f"sense-{number}", "translation": f"meaning-{number}",
                    }],
                }}
                for name, value in (
                    ("index.json", index), ("examples.json", examples),
                    ("vocabulary_master.json", master), ("lineage.jsonl", {}),
                ):
                    (assembly / name).write_text(json.dumps(value) + ("\n" if name.endswith(".jsonl") else ""), encoding="utf-8")
                assembly_report = {"run_id": run_id, "artist_slug": slug}
                (assembly / "report.json").write_text(json.dumps(assembly_report), encoding="utf-8")
                outputs = {
                    name: file_content_id(assembly / name)
                    for name in ("index.json", "examples.json", "vocabulary_master.json", "lineage.jsonl", "report.json")
                }
                (assembly / "manifest.json").write_text(json.dumps({
                    "run_id": run_id, "stage": "app_assembly", "status": "complete",
                    "inputs": {
                        "cards": file_content_id(consolidation / "cards.jsonl"),
                        "examples": file_content_id(consolidation / "examples.jsonl"),
                        "wsd_results": file_content_id(wsd / "results.jsonl"),
                    },
                    "outputs": outputs,
                }), encoding="utf-8")

            result = assemble_lyrics_corpus(
                Path(__file__).resolve().parents[2], workspace,
                plan_path=plan_path, consolidation_report_path=report_path,
            )
            output = Path(result["assembly_path"])
            master = json.loads((output / "app/Artists/es/vocabulary_master.json").read_text())
            self.assertEqual([sense["translation"] for sense in master[app_id]["senses"]], ["meaning-1", "meaning-2"])
            first_index = json.loads((output / "app/Artists/es/artist-a/index.json").read_text())
            first_examples = json.loads((output / "app/Artists/es/artist-a/examples.json").read_text())
            self.assertEqual(first_index[0]["sense_frequencies"], [1.0, 0.0])
            self.assertEqual([len(bucket) for bucket in first_examples[app_id]["m"]], [1, 0])
            self.assertEqual(result["artist_count"], 2)
            self.assertEqual(result["skipped_this_invocation"], 2)


if __name__ == "__main__":
    unittest.main()
