"""How much of a corpus each deck surface accounts for.

The inventory keeps a rank per surface and discards the count it was ranked by,
so nothing downstream can say what a level is worth — only what order it sits
in. "Rank 801–1000" tells a learner nothing; "this level is 2.3% of everything
said" tells them whether to study it.

Shares are a property of ``(surface, corpus)``, not of a deck, so this travels
beside a release rather than inside one, exactly as cognate scores do. A deck
that grows or is recut does not invalidate them, and a surface the corpus never
saw is absent rather than zero — absence being a fact about the corpus, while a
zero would claim the word is never spoken.

Two figures come out of the same data, and they answer different questions:

    share  what fraction of the corpus this band of cards accounts for
    gain   what fraction of what you have NOT yet covered it accounts for

Share decays hard — a fifteenth level of a Czech deck is 0.6% — because that is
the shape of a power law. Gain stays legible to the end (3.0% for the same
band), because the denominator shrinks as the learner advances.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


COVERAGE_SCHEMA = "surface-coverage/v1"


class CoverageError(ValueError):
    """The inputs cannot produce shares that would mean anything."""


def read_frequency_counts(path: Path) -> tuple[dict[str, int], int]:
    """Read a ``surface count`` list into counts and their total.

    The total is over the whole list, not just the deck: a share has to be a
    fraction of everything said, not of the part we happened to select.
    """

    counts: dict[str, int] = {}
    total = 0
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        try:
            count = int(parts[1])
        except ValueError:
            continue
        if count <= 0:
            continue
        surface = parts[0].lower()
        counts[surface] = counts.get(surface, 0) + count
        total += count
    if total <= 0:
        raise CoverageError(f"no usable surface counts in {path}")
    return counts, total


def deck_shares(
    surfaces: Iterable[str], counts: Mapping[str, int], total: int
) -> dict[str, float]:
    """Share of the corpus held by each deck surface it appears in."""

    shares: dict[str, float] = {}
    for surface in surfaces:
        key = str(surface or "").strip().lower()
        if not key:
            continue
        count = counts.get(key)
        if count:
            shares[key] = count / total
    return shares


def band_share(surfaces: Sequence[str], shares: Mapping[str, float]) -> float:
    """The corpus fraction one band of cards accounts for."""

    return sum(shares.get(str(s or "").strip().lower(), 0.0) for s in surfaces)


def band_gain(band: float, covered_before: float) -> float:
    """The same band as a fraction of what remains uncovered.

    Answers "how much of what is left does this buy me", which stays a
    meaningful percentage after share has decayed into noise. Once nothing
    remains there is no gain to report.
    """

    remaining = 1.0 - covered_before
    if remaining <= 0.0:
        return 0.0
    return band / remaining


def build_coverage_layer(
    *,
    language: str,
    release_index: Path,
    frequency_source: Path,
    provider: str,
    release_id: str,
) -> dict[str, Any]:
    rows = json.loads(Path(release_index).read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise CoverageError("release index must be a list of deck rows")
    counts, total = read_frequency_counts(frequency_source)
    surfaces = [str(row.get("word") or "") for row in rows if isinstance(row, dict)]
    shares = deck_shares(surfaces, counts, total)
    return {
        "schema": COVERAGE_SCHEMA,
        "language": language,
        "corpus": {
            "provider": provider,
            "distinct_surfaces": len(counts),
            "total_occurrences": total,
        },
        # Provenance, not a key: the shares are keyed by surface and stay valid
        # when the deck is recut.
        "built_from": {"release_id": release_id},
        "covered_surfaces": len(shares),
        "deck_surfaces": len(surfaces),
        "shares": {surface: round(share, 8) for surface, share in sorted(shares.items())},
    }
