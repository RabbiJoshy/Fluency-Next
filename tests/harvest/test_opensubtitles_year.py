"""The release year is present in the OpenSubtitles document path.

It was previously discarded, which is why corpus recency was invisible without
a separate IMDb lookup. The year does not feed ``sentence_id``, so surfacing it
re-keys nothing.
"""

import unittest

from fluency.harvest.sources.opensubtitles import OpenSubtitlesAdapter


def _ids_line(pt_path: str) -> str:
    return f"en/2019/7286456/1.xml.gz\t{pt_path}\t4\t5\n"


class OpenSubtitlesYearTests(unittest.TestCase):
    def test_year_is_read_from_the_document_path(self) -> None:
        document = OpenSubtitlesAdapter._provenance(
            _ids_line("pt/2019/7286456/1954961715.xml.gz"), 7
        )
        self.assertEqual(document["year"], "2019")
        self.assertEqual(document["title_id"], "7286456")
        self.assertEqual(document["subtitle_id"], "1954961715")
        self.assertEqual(document["aligned_row"], 7)

    def test_unknown_year_placeholder_is_not_recorded(self) -> None:
        """OpenSubtitles writes 0 when the year is unknown."""

        document = OpenSubtitlesAdapter._provenance(
            _ids_line("pt/0/1740870/6750336.xml.gz"), 1
        )
        self.assertNotIn("year", document)
        self.assertEqual(document["title_id"], "1740870")

    def test_implausible_year_is_not_recorded(self) -> None:
        document = OpenSubtitlesAdapter._provenance(
            _ids_line("pt/99999/123/1.xml.gz"), 1
        )
        self.assertNotIn("year", document)

    def test_malformed_line_is_rejected(self) -> None:
        self.assertIsNone(OpenSubtitlesAdapter._provenance("nope\n", 1))


if __name__ == "__main__":
    unittest.main()
