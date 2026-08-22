"""Canonical surface inventory input for harvesting."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fluency.core.hashing import file_content_id
from fluency.core.identity import build_card_id


INVENTORY_VERSION = "surface-inventory/v1"


class HarvestInventoryError(ValueError):
    """Raised when harvesting receives an ambiguous or lemma-keyed inventory."""


def load_harvest_inventory(
    path: Path,
    *,
    expected_language: str,
    expected_count: int,
) -> tuple[list[dict[str, Any]], str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise HarvestInventoryError(f"inventory does not exist: {path}") from error
    except json.JSONDecodeError as error:
        raise HarvestInventoryError(f"inventory is not valid JSON: {path}") from error
    if not isinstance(payload, dict) or payload.get("inventory_version") != INVENTORY_VERSION:
        raise HarvestInventoryError("unsupported surface inventory")
    if payload.get("language") != expected_language:
        raise HarvestInventoryError("inventory language does not match the run")
    cards = payload.get("cards")
    if not isinstance(cards, list) or len(cards) != expected_count:
        raise HarvestInventoryError(
            f"inventory must contain exactly {expected_count} surface cards"
        )

    card_ids: set[str] = set()
    surfaces: set[str] = set()
    for expected_rank, card in enumerate(cards, start=1):
        if not isinstance(card, dict):
            raise HarvestInventoryError("inventory cards must be objects")
        if "lemma" in card or "lemmas" in card or "known_lemmas" in card:
            raise HarvestInventoryError("lemma fields are forbidden in harvesting identity")
        surface_key = card.get("surface_key")
        display_form = card.get("display_form")
        card_id = card.get("card_id")
        if not isinstance(surface_key, str) or not surface_key:
            raise HarvestInventoryError("surface_key is required")
        if not isinstance(display_form, str) or not display_form:
            raise HarvestInventoryError("display_form is required")
        if card_id != build_card_id(expected_language, surface_key):
            raise HarvestInventoryError("inventory card ID does not match its surface")
        if card.get("rank") != expected_rank:
            raise HarvestInventoryError("inventory ranks must be sequential")
        if card_id in card_ids or surface_key in surfaces:
            raise HarvestInventoryError("inventory surfaces and card IDs must be unique")
        card_ids.add(card_id)
        surfaces.add(surface_key)
    return cards, file_content_id(path)


def load_frequency_ranks(path: Path) -> tuple[dict[str, int], str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise HarvestInventoryError(f"frequency ranks do not exist: {path}") from error
    except json.JSONDecodeError as error:
        raise HarvestInventoryError(f"frequency ranks are not valid JSON: {path}") from error
    if not isinstance(payload, dict):
        raise HarvestInventoryError("frequency ranks must contain an object")
    ranks: dict[str, int] = {}
    for token, rank in payload.items():
        if not isinstance(token, str) or not token:
            raise HarvestInventoryError("frequency-rank keys must be non-empty strings")
        if not isinstance(rank, int) or rank < 1:
            raise HarvestInventoryError(f"invalid frequency rank for {token!r}")
        ranks[token] = rank
    return ranks, file_content_id(path)
