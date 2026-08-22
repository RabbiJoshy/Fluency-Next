from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from fluency.harvest.sources.tatoeba import TatoebaAdapter
from fluency.pipeline.planning import load_pipeline_profile
from fluency.harvest.config import load_harvest_policies


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = (
    REPOSITORY_ROOT
    / "config/pipelines/fr/speech/rehearsal-20x3.json"
)


class TatoebaAdapterTests(unittest.TestCase):
    def test_streams_translation_and_complete_provenance(self) -> None:
        profile = load_pipeline_profile(PROFILE_PATH)
        _, _, sources, _ = load_harvest_policies(REPOSITORY_ROOT, profile)
        with tempfile.TemporaryDirectory() as directory:
            archive_path = Path(directory) / "fra-eng.zip"
            with ZipFile(archive_path, "w") as archive:
                archive.writestr("_about.txt", "Date of this file:\n2026-08-20\n")
                archive.writestr(
                    "fra.txt",
                    "I see the house.\tJe vois bien la maison.\t"
                    "CC-BY 2.0 (France) Attribution: tatoeba.org #101 (Alice) & #202 (Émile)\n",
                )

            adapter = TatoebaAdapter(archive_path, "fr", sources[0])
            records = list(adapter.iter_records())

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["record_version"], "parallel-sentence/v1")
        self.assertEqual(record["target"]["text"], "Je vois bien la maison.")
        self.assertEqual(record["translation"]["text"], "I see the house.")
        self.assertEqual(record["target"]["source_sentence_id"], "202")
        self.assertEqual(record["translation"]["source_sentence_id"], "101")
        self.assertEqual(record["source"]["source_record_id"], "202:101")
        self.assertEqual(record["source"]["license"], "CC-BY 2.0 (France)")
        self.assertTrue(record["source"]["snapshot_id"].startswith("tatoeba-2026-08-20-"))
        self.assertIn("#101 (Alice) & #202 (Émile)", record["source"]["attribution"])

    def test_rejects_rows_without_parseable_attribution(self) -> None:
        profile = load_pipeline_profile(PROFILE_PATH)
        _, _, sources, _ = load_harvest_policies(REPOSITORY_ROOT, profile)
        with tempfile.TemporaryDirectory() as directory:
            archive_path = Path(directory) / "fra-eng.zip"
            with ZipFile(archive_path, "w") as archive:
                archive.writestr(
                    "fra.txt",
                    "I see the house.\tJe vois bien la maison.\tunknown provenance\n",
                )
            adapter = TatoebaAdapter(archive_path, "fr", sources[0])
            self.assertEqual(list(adapter.iter_records()), [])
            self.assertEqual(adapter.report()["adapter_rejections"], {"unparsed_attribution": 1})


if __name__ == "__main__":
    unittest.main()
