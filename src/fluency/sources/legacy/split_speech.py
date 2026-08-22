"""Strict reader for Fluency's historical split Speech deck format."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class LegacySplitSpeechSource:
    index_path: Path
    examples_path: Path
    index_bytes: bytes
    examples_bytes: bytes
    cards: tuple[dict[str, Any], ...]
    examples_by_legacy_id: dict[str, dict[str, Any]]


def _load_json(data: bytes, path: Path) -> object:
    try:
        return json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"legacy source is not valid UTF-8 JSON: {path}") from error


def load_legacy_split_speech(index_path: Path, examples_path: Path) -> LegacySplitSpeechSource:
    """Load and cross-check an immutable legacy index/examples pair."""

    index_path = index_path.expanduser().resolve()
    examples_path = examples_path.expanduser().resolve()
    index_bytes = index_path.read_bytes()
    examples_bytes = examples_path.read_bytes()
    raw_cards = _load_json(index_bytes, index_path)
    raw_examples = _load_json(examples_bytes, examples_path)
    if not isinstance(raw_cards, list) or not raw_cards:
        raise ValueError("legacy Speech index must contain a non-empty array")
    if not isinstance(raw_examples, dict):
        raise ValueError("legacy Speech examples must contain an object")

    cards: list[dict[str, Any]] = []
    ids: set[str] = set()
    for position, raw_card in enumerate(raw_cards, start=1):
        if not isinstance(raw_card, dict):
            raise ValueError(f"legacy card {position} must be an object")
        legacy_id = raw_card.get("id")
        word = raw_card.get("word")
        meanings = raw_card.get("meanings")
        if not isinstance(legacy_id, str) or not legacy_id:
            raise ValueError(f"legacy card {position} has no ID")
        if legacy_id in ids:
            raise ValueError(f"duplicate legacy card ID: {legacy_id}")
        if not isinstance(word, str) or not word.strip():
            raise ValueError(f"legacy card {legacy_id} has no surface")
        if not isinstance(meanings, list) or not meanings:
            raise ValueError(f"legacy card {legacy_id} has no meanings")
        ids.add(legacy_id)
        cards.append(raw_card)

        example_record = raw_examples.get(legacy_id)
        if example_record is None:
            continue
        if not isinstance(example_record, dict) or not isinstance(example_record.get("m"), list):
            raise ValueError(f"legacy examples for {legacy_id} are malformed")
        if len(example_record["m"]) != len(meanings):
            raise ValueError(f"legacy meanings/examples disagree for {legacy_id}")
        for bucket in example_record["m"]:
            if not isinstance(bucket, list) or any(not isinstance(item, dict) for item in bucket):
                raise ValueError(f"legacy example bucket for {legacy_id} is malformed")

    unknown_example_ids = set(raw_examples) - ids
    if unknown_example_ids:
        first = sorted(unknown_example_ids)[0]
        raise ValueError(f"legacy examples reference unknown card ID: {first}")

    return LegacySplitSpeechSource(
        index_path=index_path,
        examples_path=examples_path,
        index_bytes=index_bytes,
        examples_bytes=examples_bytes,
        cards=tuple(cards),
        examples_by_legacy_id=raw_examples,
    )
