"""Read Lexique 4 without importing its lemma-oriented analysis fields."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterator

from fluency.languages.french.surfaces import normalize_surface


ADAPTER_ID = "lexique4-surface-frequency/v1"
SURFACE_COLUMN = "1_Mot"
FREQUENCY_COLUMN = "11_FreqOrtho"
_SURFACE_PATTERN = re.compile(r"^[^\W\d_]+(?:[’'-][^\W\d_]+)*$", re.UNICODE)


class LexiqueInventoryError(ValueError):
    """Raised when a Lexique snapshot cannot satisfy the pinned contract."""


@dataclass(frozen=True, slots=True)
class LexiqueReadResult:
    frequencies: dict[str, float]
    source_rows: int
    rejected_empty_or_zero: int
    rejected_surface_shape: int
    duplicate_rows: int


def read_lexique4(path: Path) -> LexiqueReadResult:
    """Return one FreqOrtho value per normalized French surface.

    Lexique repeats an orthographic form for different grammatical analyses.
    FreqOrtho is already the summed surface frequency on each repeated row, so
    duplicates use ``max`` and are never added together.
    """

    frequencies: dict[str, float] = {}
    source_rows = 0
    rejected_empty_or_zero = 0
    rejected_surface_shape = 0
    duplicate_rows = 0
    try:
        stream = path.open(encoding="utf-8-sig", newline="")
    except FileNotFoundError as error:
        raise LexiqueInventoryError(f"Lexique snapshot does not exist: {path}") from error
    with stream:
        reader = csv.DictReader(stream, delimiter="\t")
        fields = set(reader.fieldnames or ())
        required = {SURFACE_COLUMN, FREQUENCY_COLUMN}
        if not required.issubset(fields):
            missing = ", ".join(sorted(required - fields))
            raise LexiqueInventoryError(
                f"snapshot is not the expected Lexique 4 schema; missing: {missing}"
            )
        for row in reader:
            source_rows += 1
            raw_surface = (row.get(SURFACE_COLUMN) or "").strip()
            raw_frequency = (row.get(FREQUENCY_COLUMN) or "").strip()
            try:
                frequency = float(raw_frequency)
            except ValueError:
                frequency = 0.0
            if not raw_surface or frequency <= 0:
                rejected_empty_or_zero += 1
                continue
            surface = normalize_surface(raw_surface)
            if _SURFACE_PATTERN.fullmatch(surface) is None:
                rejected_surface_shape += 1
                continue
            if surface in frequencies:
                duplicate_rows += 1
                frequencies[surface] = max(frequencies[surface], frequency)
            else:
                frequencies[surface] = frequency
    if not frequencies:
        raise LexiqueInventoryError("Lexique snapshot yielded no usable surfaces")
    return LexiqueReadResult(
        frequencies=frequencies,
        source_rows=source_rows,
        rejected_empty_or_zero=rejected_empty_or_zero,
        rejected_surface_shape=rejected_surface_shape,
        duplicate_rows=duplicate_rows,
    )


def ranked_surfaces(frequencies: dict[str, float]) -> Iterator[tuple[str, float]]:
    """Yield deterministic surface ranks, descending by frequency."""

    yield from sorted(frequencies.items(), key=lambda item: (-item[1], item[0]))
