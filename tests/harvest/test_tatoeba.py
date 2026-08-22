import bz2
import json
from pathlib import Path
import tempfile
import unittest

from fluency.harvest.config import load_harvest_policies
from fluency.harvest.sources.tatoeba import TatoebaAdapter, TatoebaAdapterError
from fluency.pipeline.planning import load_pipeline_profile


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = REPOSITORY_ROOT / "config/pipelines/fr/speech/rehearsal-20x3.json"


def write_snapshot(directory: Path) -> Path:
    snapshot = directory / "tatoeba-2026-08-22-fr-en"
    snapshot.mkdir(parents=True)
    (snapshot / "snapshot.json").write_text(
        json.dumps(
            {
                "snapshot_version": "tatoeba-weekly-snapshot/v1",
                "snapshot_id": "tatoeba-2026-08-22-fr-en",
                "target_language": "fr",
                "target_code": "fra",
                "translation_language": "en",
                "translation_code": "eng",
                "license": "CC BY 2.0 FR",
                "license_url": "https://creativecommons.org/licenses/by/2.0/fr/",
                "attribution": "Tatoeba contributors",
                "source_url": "https://tatoeba.org/en/downloads",
                "source_files": {
                    "target_sentences": {
                        "filename": "fra_sentences_detailed.tsv.bz2",
                        "url": "https://downloads.tatoeba.org/exports/per_language/fra/fra_sentences_detailed.tsv.bz2",
                    },
                    "translation_sentences": {
                        "filename": "eng_sentences_detailed.tsv.bz2",
                        "url": "https://downloads.tatoeba.org/exports/per_language/eng/eng_sentences_detailed.tsv.bz2",
                    },
                    "links": {
                        "filename": "eng-fra_links.tsv.bz2",
                        "url": "https://downloads.tatoeba.org/exports/per_language/eng/eng-fra_links.tsv.bz2",
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    with bz2.open(snapshot / "fra_sentences_detailed.tsv.bz2", "wt", encoding="utf-8") as stream:
        stream.write("202\tfra\tJe vois bien la maison.\tÉmile\t2026-08-01 10:00:00\t\\N\n")
    with bz2.open(snapshot / "eng_sentences_detailed.tsv.bz2", "wt", encoding="utf-8") as stream:
        stream.write("101\teng\tI see the house.\tAlice\t2026-08-01 09:00:00\t\\N\n")
    with bz2.open(snapshot / "eng-fra_links.tsv.bz2", "wt", encoding="utf-8") as stream:
        stream.write("101\t202\n")
    return snapshot


class TatoebaAdapterTests(unittest.TestCase):
    def _policy(self) -> dict[str, object]:
        profile = load_pipeline_profile(PROFILE_PATH)
        _, _, sources, _ = load_harvest_policies(REPOSITORY_ROOT, profile)
        return sources[0]

    def test_streams_official_exports_with_complete_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            adapter = TatoebaAdapter(write_snapshot(Path(directory)), "fr", self._policy())
            records = list(adapter.iter_records())

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["record_version"], "parallel-sentence/v1")
        self.assertEqual(record["target"]["text"], "Je vois bien la maison.")
        self.assertEqual(record["translation"]["text"], "I see the house.")
        self.assertEqual(record["target"]["source_sentence_id"], "202")
        self.assertEqual(record["translation"]["source_sentence_id"], "101")
        self.assertEqual(record["target"]["contributor"], "Émile")
        self.assertEqual(record["translation"]["contributor"], "Alice")
        self.assertEqual(record["source"]["source_record_id"], "202:101")
        self.assertEqual(record["source"]["license"], "CC BY 2.0 FR")
        self.assertEqual(record["source"]["snapshot_id"], "tatoeba-2026-08-22-fr-en")
        self.assertIn("#202 by Émile", record["source"]["attribution"])
        self.assertEqual(adapter.report()["rows_seen"], 1)

    def test_rejects_missing_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(TatoebaAdapterError, "metadata does not exist"):
                TatoebaAdapter(Path(directory), "fr", self._policy())

    def test_rejects_language_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            snapshot = write_snapshot(Path(directory))
            metadata_path = snapshot / "snapshot.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["target_language"] = "es"
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
            with self.assertRaisesRegex(TatoebaAdapterError, "target language"):
                TatoebaAdapter(snapshot, "fr", self._policy())

    def test_reports_link_to_missing_sentence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            snapshot = write_snapshot(Path(directory))
            with bz2.open(snapshot / "eng-fra_links.tsv.bz2", "at", encoding="utf-8") as stream:
                stream.write("999\t888\n")
            adapter = TatoebaAdapter(snapshot, "fr", self._policy())
            self.assertEqual(len(list(adapter.iter_records())), 1)
            self.assertEqual(adapter.report()["adapter_rejections"], {"missing_target_sentence": 1})


if __name__ == "__main__":
    unittest.main()
