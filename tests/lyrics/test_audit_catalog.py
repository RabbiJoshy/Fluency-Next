import json
from pathlib import Path
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = REPOSITORY_ROOT / "app" / "lyrics-audit" / "data"


class LyricsAuditCatalogTests(unittest.TestCase):
    def test_each_token_classification_exposes_clickable_preserved_history(self):
        audit_root = REPOSITORY_ROOT / "app" / "lyrics-audit"
        explorer = (audit_root / "explorer.js").read_text(encoding="utf-8")
        page = (audit_root / "index.html").read_text(encoding="utf-8")

        self.assertIn('data-decision="${escapeHtml(decision.id)}"', explorer)
        self.assertIn("function classificationDecisions(token, line)", explorer)
        self.assertIn("function decisionHistoryHtml(decision)", explorer)
        self.assertIn("No classification record preserved", explorer)
        self.assertIn("No earlier history is available", explorer)
        self.assertIn("function tokenDisplayHtml(token)", explorer)
        self.assertIn('class="token-change-arrow">→</span>', explorer)
        self.assertIn('class="decision-rule-group"', explorer)
        self.assertIn('class="audit-group pipeline-group"', explorer)
        self.assertIn('explorer.js?v=14', page)

    def test_catalog_points_to_distinct_matching_song_bundles(self):
        catalog = json.loads((DATA_ROOT / "catalog.json").read_text(encoding="utf-8"))
        self.assertEqual(catalog["schema"], "fluency.lyrics-audit-catalog/v1")
        self.assertGreaterEqual(len(catalog["songs"]), 2)
        song_ids = [song["song_id"] for song in catalog["songs"]]
        self.assertEqual(len(song_ids), len(set(song_ids)))
        self.assertIn(catalog["default_song_id"], song_ids)

        for song in catalog["songs"]:
            bundle = json.loads((DATA_ROOT / song["bundle"]).read_text(encoding="utf-8"))
            self.assertEqual(str(bundle["song"]["id"]), song["song_id"])
            self.assertEqual(bundle["song"]["title"], song["title"])
            self.assertEqual(bundle["artist"]["name"], song["artist"])
            self.assertEqual(bundle["language"], song["language"])

    def test_clean_route_references_resolve_to_deduplicated_profiles(self):
        bundle = json.loads((DATA_ROOT / "estamos-arriba.json").read_text(encoding="utf-8"))
        profiles = bundle["routing_profiles"]
        units = {
            unit["analysis_unit_id"]: unit
            for line in bundle["song"]["lines"]
            for occurrence in line["occurrences"]
            if occurrence.get("clean_processing")
            for unit in occurrence["clean_processing"]["units"]
        }
        references = [
            route
            for line in bundle["song"]["lines"]
            for occurrence in line["occurrences"]
            if occurrence.get("clean_processing")
            for route in occurrence["clean_processing"]["routes"]
        ]
        self.assertEqual(len(references), bundle["comparison"]["occurrence_count"])
        self.assertLess(len(profiles), len(references))
        for reference in references:
            profile = profiles[reference["profile_id"]]
            self.assertEqual(
                profile["decision"]["normalized_form"],
                units[reference["analysis_unit_id"]]["normalized_form"],
            )

    def test_clean_lexical_and_wsd_references_cover_every_unit_exactly(self):
        bundle = json.loads((DATA_ROOT / "estamos-arriba.json").read_text(encoding="utf-8"))
        profiles = bundle["lexical_profiles"]
        references = [
            candidate
            for line in bundle["song"]["lines"]
            for occurrence in line["occurrences"]
            if occurrence.get("clean_processing")
            for candidate in occurrence["clean_processing"]["lexical_candidates"]
        ]
        self.assertEqual(len(references), bundle["comparison"]["occurrence_count"])
        self.assertEqual(
            sum(bundle["comparison"]["lexical_status_counts"].values()),
            len(references),
        )
        self.assertEqual(bundle["comparison"]["wsd_request_count"], len(references))
        self.assertEqual(sum(bundle["comparison"]["wsd_result_counts"].values()), len(references))
        self.assertEqual(bundle["comparison"]["wsd_result_counts"]["assigned"], 463)
        self.assertEqual(bundle["comparison"]["wsd_method_id"], "spanishdict-beto-cal-v5")
        self.assertIn("no historical assignment fallback", bundle["evidence"]["wsd"])
        for reference in references:
            self.assertIn(reference["profile_id"], profiles)

        result_profiles = bundle["wsd_result_profiles"]
        result_references = [
            result
            for line in bundle["song"]["lines"]
            for occurrence in line["occurrences"]
            if occurrence.get("clean_processing")
            for result in occurrence["clean_processing"]["wsd_results"]
        ]
        self.assertEqual(len(result_references), len(references))
        for reference in result_references:
            result = result_profiles[reference["result_id"]]
            if result["status"] != "assigned":
                self.assertIsNone(result["selected_sense_id"])
                continue
            matching_lexical = next(
                candidate
                for line in bundle["song"]["lines"]
                for occurrence in line["occurrences"]
                if occurrence.get("clean_processing")
                for candidate in occurrence["clean_processing"]["lexical_candidates"]
                if candidate["analysis_unit_id"] == reference["analysis_unit_id"]
            )
            lexical = profiles[matching_lexical["profile_id"]]
            analysis = next(
                item for item in lexical["analyses"]
                if item["menu_analysis_id"] == result["menu_analysis_id"]
            )
            self.assertIn(result["selected_sense_id"], {sense["sense_id"] for sense in analysis["senses"]})

    def test_clean_consolidation_preserves_every_outcome_and_exact_example_links(self):
        bundle = json.loads((DATA_ROOT / "estamos-arriba.json").read_text(encoding="utf-8"))
        comparison = bundle["comparison"]
        self.assertEqual(comparison["consolidation_card_count"], 162)
        self.assertEqual(comparison["consolidation_example_count"], 463)
        self.assertEqual(comparison["consolidation_selected_example_count"], 349)
        self.assertEqual(comparison["consolidation_non_study_count"], 122)
        references = [
            reference
            for line in bundle["song"]["lines"]
            for occurrence in line["occurrences"]
            if occurrence.get("clean_processing")
            for reference in occurrence["clean_processing"]["consolidations"]
        ]
        self.assertEqual(len(references), comparison["occurrence_count"])
        self.assertEqual(len(bundle["consolidation_dispositions"]), len(references))
        for reference in references:
            disposition = bundle["consolidation_dispositions"][reference["disposition_id"]]
            if disposition["study_status"] == "included":
                self.assertIn(reference["card_id"], bundle["consolidated_cards"])
                example = bundle["consolidated_examples"][reference["example_id"]]
                self.assertEqual(example["occurrence"]["occurrence_id"], disposition["occurrence_id"])
                self.assertEqual(example["wsd"]["result_id"], disposition["wsd_result_id"])
            else:
                self.assertIsNone(reference["card_id"])
                self.assertIsNone(reference["example_id"])


if __name__ == "__main__":
    unittest.main()
