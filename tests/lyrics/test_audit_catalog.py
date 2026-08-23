import json
from pathlib import Path
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = REPOSITORY_ROOT / "app" / "lyrics-audit" / "data"


class LyricsAuditCatalogTests(unittest.TestCase):
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

    def test_clean_lexical_references_cover_every_unit_without_claiming_wsd(self):
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
        self.assertIn("WSD has not run", bundle["evidence"]["lexical_menu"])
        self.assertEqual(bundle["comparison"]["wsd_request_count"], len(references))
        self.assertIn("not_run", bundle["evidence"]["wsd"])
        for reference in references:
            self.assertIn(reference["profile_id"], profiles)


if __name__ == "__main__":
    unittest.main()
