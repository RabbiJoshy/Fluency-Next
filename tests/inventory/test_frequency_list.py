"""Contract tests for the published two-column frequency-list adapter."""

from pathlib import Path
import tempfile
import unittest

from fluency.inventory.frequency_list import (
    FrequencyListError,
    ranked_surfaces,
    read_frequency_list,
)


class FrequencyListTests(unittest.TestCase):
    def _read(self, text: str):
        with tempfile.TemporaryDirectory() as raw_root:
            path = Path(raw_root) / "list.txt"
            path.write_text(text, encoding="utf-8")
            return read_frequency_list(path, language="pt")

    def test_reads_surface_and_count(self) -> None:
        result = self._read("que 15044152\nnão 12169729\n")
        self.assertEqual(result.frequencies, {"que": 15044152.0, "não": 12169729.0})
        self.assertEqual(result.source_rows, 2)

    def test_ranks_descending_then_alphabetically(self) -> None:
        result = self._read("b 5\na 5\nc 9\n")
        surfaces = [surface for surface, _ in ranked_surfaces(result.frequencies)]
        self.assertEqual(surfaces, ["c", "a", "b"])

    def test_accents_are_not_folded(self) -> None:
        """país/pais and é/e are distinct Portuguese cards, never merged."""

        result = self._read("país 100\npais 90\n")
        self.assertEqual(set(result.frequencies), {"país", "pais"})

    def test_case_variants_are_summed_not_maxed(self) -> None:
        """Each line is a distinct set of occurrences, unlike Lexique analysis rows."""

        result = self._read("Ok 10\nok 5\n")
        self.assertEqual(result.frequencies, {"ok": 15.0})
        self.assertEqual(result.duplicate_rows, 1)

    def test_rejects_malformed_rows(self) -> None:
        result = self._read("ok 5\nbad\nthree cols here\nx notanumber\n")
        self.assertEqual(result.frequencies, {"ok": 5.0})
        self.assertEqual(result.rejected_malformed, 3)

    def test_rejects_numeric_surfaces(self) -> None:
        result = self._read("ok 5\n123 7\n")
        self.assertEqual(result.rejected_surface_shape, 1)

    def test_rejects_zero_counts(self) -> None:
        result = self._read("ok 5\nzero 0\n")
        self.assertEqual(result.rejected_empty_or_zero, 1)

    def test_missing_file_raises(self) -> None:
        with tempfile.TemporaryDirectory() as raw_root:
            with self.assertRaises(FrequencyListError):
                read_frequency_list(Path(raw_root) / "absent.txt", language="pt")

    def test_empty_result_raises(self) -> None:
        with self.assertRaises(FrequencyListError):
            self._read("123 7\n")


if __name__ == "__main__":
    unittest.main()
