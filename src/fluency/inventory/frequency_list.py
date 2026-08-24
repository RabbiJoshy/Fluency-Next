"""Read a published two-column surface frequency list without lemma identity.

Many languages have an authoritative, already-counted frequency list rather
than an analysed lexicon like Lexique. Those lists carry one line per surface
form and no grammatical analysis, which matches the surface-card contract
directly: there are no lemma columns to drop, because the source never had any.

The pinned shape is ``{surface}{space}{count}``, one record per line, as
published by the FrequencyWords OpenSubtitles lists. Counts are integers and
are read as raw occurrence counts, not per-million rates; only the induced
ranking is consumed downstream.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterator

from fluency.languages.surfaces import normalizer_for_language


ADAPTER_ID = "published-surface-frequency-list/v1"
_SURFACE_PATTERN = re.compile(r"^[^\W\d_]+(?:[’'-][^\W\d_]+)*$", re.UNICODE)


class FrequencyListError(ValueError):
    """Raised when a frequency list cannot satisfy the pinned contract."""


@dataclass(frozen=True, slots=True)
class FrequencyListReadResult:
    frequencies: dict[str, float]
    source_rows: int
    rejected_malformed: int
    rejected_empty_or_zero: int
    rejected_surface_shape: int
    duplicate_rows: int


def read_frequency_list(path: Path, *, language: str) -> FrequencyListReadResult:
    """Return one count per normalized surface from a published frequency list.

    Normalization can map two published rows onto one card (most often by
    case). Those are summed rather than maxed: unlike Lexique's repeated
    analysis rows, each line here is a distinct set of corpus occurrences.
    """

    normalize_surface = normalizer_for_language(language)
    frequencies: dict[str, float] = {}
    source_rows = 0
    rejected_malformed = 0
    rejected_empty_or_zero = 0
    rejected_surface_shape = 0
    duplicate_rows = 0

    try:
        stream = path.open(encoding="utf-8-sig")
    except FileNotFoundError as error:
        raise FrequencyListError(f"frequency list does not exist: {path}") from error

    with stream:
        for line in stream:
            line = line.strip()
            if not line:
                continue
            source_rows += 1
            parts = line.split()
            if len(parts) != 2:
                rejected_malformed += 1
                continue
            raw_surface, raw_count = parts
            try:
                count = float(raw_count)
            except ValueError:
                rejected_malformed += 1
                continue
            if not raw_surface or count <= 0:
                rejected_empty_or_zero += 1
                continue
            surface = normalize_surface(raw_surface)
            if _SURFACE_PATTERN.fullmatch(surface) is None:
                rejected_surface_shape += 1
                continue
            if surface in frequencies:
                duplicate_rows += 1
                frequencies[surface] += count
            else:
                frequencies[surface] = count

    if not frequencies:
        raise FrequencyListError("frequency list yielded no usable surfaces")

    return FrequencyListReadResult(
        frequencies=frequencies,
        source_rows=source_rows,
        rejected_malformed=rejected_malformed,
        rejected_empty_or_zero=rejected_empty_or_zero,
        rejected_surface_shape=rejected_surface_shape,
        duplicate_rows=duplicate_rows,
    )


def ranked_surfaces(frequencies: dict[str, float]) -> Iterator[tuple[str, float]]:
    """Yield deterministic surface ranks, descending by frequency."""

    yield from sorted(frequencies.items(), key=lambda item: (-item[1], item[0]))
