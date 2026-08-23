import copy
import json
from pathlib import Path
import tempfile
import unittest

from fluency.core.hashing import canonical_content_id, file_content_id
from fluency.core.workspace import Workspace
from fluency.lyrics.wsd_results import (
    BUNDLE_VERSION,
    LyricsWSDResultImportError,
    RESULT_VERSION,
    _validate_result,
    import_lyrics_wsd_results,
)
from fluency.lyrics.wsd_execute import dotenv_value


MENU_ID = "sha256:" + "a" * 64


def fixture():
    request = {
        "request_id": "wsd_request_" + "1" * 32,
        "run_id": "run-one", "language": "es", "mode": "lyrics",
        "target": {"kind": "analysis_unit", "id": "unit_" + "2" * 32},
        "occurrence_id": "occurrence_" + "3" * 32,
        "surface_card_id": "card_es_" + "4" * 32,
        "surface_form": "casa", "eligibility": "ready",
        "lexical_candidate_id": "lexical_" + "5" * 32,
    }
    analyses = [{
            "menu_analysis_id": "analysis_" + "6" * 32,
            "headword": "casar", "part_of_speech": "VERB",
            "senses": [{"sense_id": "marry"}],
        }]
    candidate = {
        "menu_analysis_ids": [analyses[0]["menu_analysis_id"]],
        "menu_analysis_count": 1,
        "menu_sense_count": 1,
    }
    result = {
        "result_version": RESULT_VERSION, "request_id": request["request_id"],
        "run_id": request["run_id"], "language": "es", "mode": "lyrics",
        "target": request["target"], "occurrence_id": request["occurrence_id"],
        "surface_card_id": request["surface_card_id"], "surface_form": "casa",
        "status": "assigned", "menu_content_id": MENU_ID,
        "menu_analysis_id": analyses[0]["menu_analysis_id"],
        "selected_sense_id": "marry",
        "selected_tuple": {"headword": "casar", "part_of_speech": "VERB"},
        "decision_path": ["candidate_preparation", "gloss", "token_tuple_vote", "calibration"],
        "evidence": {}, "confidence": 0.8, "input_artifact_ids": [MENU_ID],
    }
    result["result_id"] = "wsd_result_" + canonical_content_id(result).removeprefix("sha256:")[:32]
    return request, candidate, analyses, result


class LyricsWSDResultTests(unittest.TestCase):
    def test_dotenv_is_parsed_as_data_with_spaces_around_equals(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("# comment\nGEMINI_API_KEY = 'secret-value'\nOTHER = ignored\n")
            self.assertEqual(dotenv_value(path, "GEMINI_API_KEY"), "secret-value")

    def test_exact_assigned_result_is_accepted(self):
        request, candidate, analyses, result = fixture()
        _validate_result(result, request, candidate, menu_content_id=MENU_ID, analyses=analyses)

    def test_stale_or_out_of_menu_selection_fails(self):
        request, candidate, analyses, result = fixture()
        changed = copy.deepcopy(result)
        changed["selected_sense_id"] = "invented"
        body = {key: value for key, value in changed.items() if key != "result_id"}
        changed["result_id"] = "wsd_result_" + canonical_content_id(body).removeprefix("sha256:")[:32]
        with self.assertRaises(LyricsWSDResultImportError):
            _validate_result(changed, request, candidate, menu_content_id=MENU_ID, analyses=analyses)

    def test_non_executable_request_cannot_gain_an_assignment(self):
        request, candidate, analyses, result = fixture()
        request["eligibility"] = "review"
        with self.assertRaises(LyricsWSDResultImportError):
            _validate_result(result, request, candidate, menu_content_id=MENU_ID, analyses=analyses)

    def test_import_publishes_complete_pool_with_verified_asset(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = Workspace.initialize(root / "workspace")
            run_id = "lyrics-fixture"
            run = workspace.root / "runs/es/lyrics" / run_id
            prepare = run / "stages/04_wsd_prepare/output"
            lexical = run / "stages/03_lexical_menu/output"
            prepare.mkdir(parents=True)
            lexical.mkdir(parents=True)
            request, candidate, _analyses, _assigned = fixture()
            request.update({
                "run_id": run_id, "eligibility": "review",
                "input_artifact_ids": [MENU_ID],
            })
            candidate.update({"lexical_candidate_id": request["lexical_candidate_id"]})
            request_path = prepare / "requests.jsonl"
            candidate_path = lexical / "lexical-candidates.jsonl"
            menu_path = lexical / "sense-menu.json"
            request_path.write_text(json.dumps(request) + "\n")
            candidate_path.write_text(json.dumps(candidate) + "\n")
            menu_path.write_text(json.dumps({"cards": []}))
            (prepare / "manifest.json").write_text(json.dumps({
                "outputs": {"requests.jsonl": file_content_id(request_path)}
            }))
            (lexical / "manifest.json").write_text(json.dumps({"outputs": {
                "lexical-candidates.jsonl": file_content_id(candidate_path),
                "sense-menu.json": file_content_id(menu_path),
            }}))
            run_manifest = {"run_id": run_id, "language": "es", "mode": "lyrics", "stages": {}}
            (run / "manifest.json").write_text(json.dumps(run_manifest))
            asset = workspace.root / "raw/wsd/assets/model.bin"
            asset.parent.mkdir(parents=True)
            asset.write_bytes(b"model")
            body = {
                "result_version": RESULT_VERSION, "request_id": request["request_id"],
                "run_id": run_id, "language": "es", "mode": "lyrics",
                "target": request["target"], "occurrence_id": request["occurrence_id"],
                "surface_card_id": request["surface_card_id"], "surface_form": request["surface_form"],
                "status": "review", "menu_content_id": None, "menu_analysis_id": None,
                "selected_sense_id": None, "selected_tuple": None, "decision_path": [],
                "evidence": {"reason_codes": ["review"]}, "confidence": None,
                "input_artifact_ids": [MENU_ID],
            }
            body["result_id"] = "wsd_result_" + canonical_content_id(body).removeprefix("sha256:")[:32]
            method = {
                "profile_id": "fixture", "source_method_id": "fixture-v1",
                "source_repository_commit": "a" * 40, "implementation_version": "fixture/v1",
                "implementation_content_id": MENU_ID, "model_revisions": {"model": "fixture@1"},
                "asset_refs": {"model": {"path": asset.relative_to(workspace.root).as_posix(), "content_id": file_content_id(asset)}},
                "parameters": {}, "optional_methods": {}, "random_seed": 0,
            }
            bundle = {
                "bundle_version": BUNDLE_VERSION, "run_id": run_id, "language": "es", "mode": "lyrics",
                "coverage": "complete_request_pool", "request_file_content_id": file_content_id(request_path),
                "sense_menu_content_id": file_content_id(menu_path), "method": method, "results": [body],
            }
            bundle_path = workspace.root / "raw/wsd/results/fixture.json"
            bundle_path.parent.mkdir(parents=True)
            bundle_path.write_text(json.dumps(bundle))
            output = import_lyrics_wsd_results(
                Path(__file__).resolve().parents[2], workspace,
                run_id=run_id, language="es", bundle_path=bundle_path,
            )
            self.assertTrue((output / "results.jsonl").is_file())


if __name__ == "__main__":
    unittest.main()
