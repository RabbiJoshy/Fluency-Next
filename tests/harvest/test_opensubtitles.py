from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from fluency.harvest.config import load_harvest_policies
from fluency.harvest.sources.opensubtitles import (
    OpenSubtitlesAdapter,
    OpenSubtitlesAdapterError,
)
from fluency.pipeline.planning import load_pipeline_profile


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = REPOSITORY_ROOT / "config/pipelines/fr/speech/rehearsal-20x3.json"


class OpenSubtitlesAdapterTests(unittest.TestCase):
    def _build_snapshot(self, root: Path) -> Path:
        snapshot = root / "opensubtitles-fr"
        snapshot.mkdir()
        (snapshot / "snapshot.json").write_text(
            json.dumps(
                {
                    "snapshot_version": "opensubtitles-aligned-snapshot/v1",
                    "snapshot_id": "opensubtitles-en-fr-2026-08-test",
                    "target_language": "fr",
                    "translation_language": "en",
                    "license": "Synthetic test terms",
                    "attribution": "Synthetic OpenSubtitles fixture",
                    "source_url": "https://opus.nlpl.eu/OpenSubtitles/",
                }
            ),
            encoding="utf-8",
        )
        (snapshot / "OpenSubtitles.en-fr.fr").write_text(
            "Je vois vraiment cette maison.\n", encoding="utf-8"
        )
        (snapshot / "OpenSubtitles.en-fr.en").write_text(
            "I can really see this house.\n", encoding="utf-8"
        )
        (snapshot / "OpenSubtitles.en-fr.ids").write_text(
            "x\tfr/0/7654321/987654.xml.gz\tx\t42\n", encoding="utf-8"
        )
        return snapshot

    def _policy(self) -> dict:
        profile = deepcopy(load_pipeline_profile(PROFILE_PATH))
        profile["harvest"]["sources"] = ["opensubtitles"]
        _, _, sources, _ = load_harvest_policies(REPOSITORY_ROOT, profile)
        return sources[0]

    def test_streams_movie_provenance_into_shared_record(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            adapter = OpenSubtitlesAdapter(
                self._build_snapshot(Path(directory)), "fr", self._policy()
            )
            records = list(adapter.iter_records())

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["record_version"], "parallel-sentence/v1")
        self.assertEqual(record["source"]["document"]["title_id"], "7654321")
        self.assertEqual(record["source"]["document"]["subtitle_id"], "987654")
        self.assertEqual(record["source"]["document"]["line"], "42")
        self.assertEqual(record["source"]["license"], "Synthetic test terms")
        self.assertEqual(record["translation"]["language"], "en")

    def test_fails_when_aligned_files_have_different_line_counts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            snapshot = self._build_snapshot(Path(directory))
            with (snapshot / "OpenSubtitles.en-fr.en").open("a", encoding="utf-8") as stream:
                stream.write("An extra translation line.\n")
            adapter = OpenSubtitlesAdapter(snapshot, "fr", self._policy())
            with self.assertRaisesRegex(OpenSubtitlesAdapterError, "line-aligned"):
                list(adapter.iter_records())


if __name__ == "__main__":
    unittest.main()
