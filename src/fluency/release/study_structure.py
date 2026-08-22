"""Build release-owned adaptive levels and stable 20-position study sets."""

from __future__ import annotations

import math
from typing import Any, Callable, Sequence


STUDY_STRUCTURE_VERSION = "study-structure/v1"


def _js_round(value: float) -> int:
    """Match JavaScript Math.round for the positive values used here."""

    return math.floor(value + 0.5)


def build_study_structure(
    cards: Sequence[dict[str, Any]],
    *,
    frequency_of: Callable[[dict[str, Any]], int | float],
    target_cards_per_level: int = 200,
    minimum_levels: int = 10,
    maximum_levels: int = 80,
    set_size: int = 20,
) -> dict[str, Any]:
    """Port the existing smart-level algorithm into immutable release metadata."""

    if not cards:
        raise ValueError("cannot build study structure for an empty deck")
    if min(target_cards_per_level, minimum_levels, maximum_levels, set_size) <= 0:
        raise ValueError("study structure sizes must be positive")
    total = len(cards)
    frequencies = [max(0, float(frequency_of(card))) for card in cards]
    segment_count = min(
        total,
        maximum_levels,
        max(minimum_levels, math.ceil(total / target_cards_per_level)),
    )
    ideal_size = total / segment_count
    snap_window = max(2, _js_round(ideal_size * 0.25))
    minimum_size = max(1, _js_round(ideal_size * 0.5))
    cliffs = [index for index in range(1, total) if frequencies[index - 1] != frequencies[index]]

    boundaries: list[int] = []
    previous = 0
    for segment in range(1, segment_count):
        remaining = segment_count - segment
        minimum = previous + minimum_size
        maximum = total - remaining * minimum_size
        ideal = _js_round(total * segment / segment_count)
        target = max(minimum, min(maximum, ideal))
        nearby = [
            count for count in cliffs
            if minimum <= count <= maximum and abs(count - target) <= snap_window
        ]
        boundary = min(nearby, key=lambda count: (abs(count - target), count)) if nearby else target
        boundaries.append(boundary)
        previous = boundary
    boundaries.append(total)

    levels: list[dict[str, Any]] = []
    start = 0
    for level_number, end in enumerate(boundaries, start=1):
        level_id = f"level-{level_number:03d}"
        sets: list[dict[str, Any]] = []
        level_cards = cards[start:end]
        for set_offset in range(0, len(level_cards), set_size):
            set_number = len(sets) + 1
            members = level_cards[set_offset:set_offset + set_size]
            first_rank = start + set_offset + 1
            last_rank = first_rank + len(members) - 1
            sets.append(
                {
                    "set_id": f"{level_id}-set-{set_number:02d}",
                    "label": f"Set {set_number}",
                    "start_rank": first_rank,
                    "end_rank": last_rank,
                    "card_ids": [card["card_id"] for card in members],
                }
            )
        levels.append(
            {
                "level_id": level_id,
                "label": f"Level {level_number}",
                "start_rank": start + 1,
                "end_rank": end,
                "card_count": end - start,
                "sets": sets,
            }
        )
        start = end
    return {"structure_version": STUDY_STRUCTURE_VERSION, "levels": levels}
