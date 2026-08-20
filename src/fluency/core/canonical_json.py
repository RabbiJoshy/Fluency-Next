"""Canonical JSON encoding used by hashes and immutable manifests."""

from __future__ import annotations

import json
from typing import Any


def canonical_json(value: Any) -> str:
    """Encode JSON deterministically and reject non-standard numeric values."""

    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def canonical_json_bytes(value: Any) -> bytes:
    return canonical_json(value).encode("utf-8")

