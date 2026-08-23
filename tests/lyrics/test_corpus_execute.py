import json
from pathlib import Path
import tempfile
import unittest

from fluency.core.hashing import file_content_id
from fluency.core.workspace import Workspace
from fluency.lyrics.corpus_execute import execute_spanish_v5_corpus
from fluency.lyrics.wsd_execute import METHOD_PROFILE


class LyricsCorpusExecutionTests(unittest.TestCase):
    def test_complete_existing_bundles_resume_without_loading_models(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = Workspace.initialize(root / "workspace")
            plan_id = "plan-v1"
            plan_path = workspace.root / "raw/lyrics/corpus-plans" / plan_id / "manifest.json"
            plan_path.parent.mkdir(parents=True)
            songs = [{
                "source_record_id": str(number), "planned_run_id": f"run-{number}",
            } for number in (1, 2)]
            plan = {
                "plan_version": "lyrics-corpus-plan/v1", "plan_id": plan_id,
                "status": "planned_sources_only", "language": "es",
                "included_sources": [{
                    "artist_slug": "artist", "artist_name": "Artist", "songs": songs,
                }],
            }
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            preparation_path = workspace.root / "runs/es/lyrics-corpora" / plan_id / "wsd-preparation-report.json"
            preparation_path.parent.mkdir(parents=True)
            preparation_path.write_text(json.dumps({
                "status": "complete", "execution_status": "not_run", "plan_id": plan_id,
                "plan_content_id": file_content_id(plan_path), "song_run_count": 2,
            }), encoding="utf-8")
            bundle_root = workspace.root / "raw/wsd/results/es/lyrics/corpora" / plan_id / METHOD_PROFILE
            bundle_root.mkdir(parents=True)
            for song in songs:
                run_id = song["planned_run_id"]
                run = workspace.root / "runs/es/lyrics" / run_id
                prepare = run / "stages/04_wsd_prepare/output"
                menu = run / "stages/03_lexical_menu/output"
                prepare.mkdir(parents=True)
                menu.mkdir(parents=True)
                requests = prepare / "requests.jsonl"
                sense_menu = menu / "sense-menu.json"
                requests.write_text("", encoding="utf-8")
                sense_menu.write_text("{}", encoding="utf-8")
                (bundle_root / f"{run_id}.json").write_text(json.dumps({
                    "bundle_version": "lyrics-wsd-result-bundle/v1",
                    "run_id": run_id, "language": "es", "mode": "lyrics",
                    "coverage": "complete_request_pool",
                    "request_file_content_id": file_content_id(requests),
                    "sense_menu_content_id": file_content_id(sense_menu),
                    "method": {"profile_id": METHOD_PROFILE}, "results": [],
                }), encoding="utf-8")
            result = execute_spanish_v5_corpus(
                Path(__file__).resolve().parents[2], workspace,
                plan_path=plan_path, preparation_report_path=preparation_path,
            )
            self.assertEqual(result["created_this_invocation"], 0)
            self.assertEqual(result["skipped_this_invocation"], 2)
            catalog = json.loads(Path(result["catalog_path"]).read_text())
            self.assertEqual(set(catalog["bundles"]), {"run-1", "run-2"})
            self.assertEqual(catalog["method_profile_id"], METHOD_PROFILE)


if __name__ == "__main__":
    unittest.main()
