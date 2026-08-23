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


if __name__ == "__main__":
    unittest.main()
