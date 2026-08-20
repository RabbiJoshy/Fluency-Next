"""Content hashes for artifacts, configurations, and stage cache keys."""

from __future__ import annotations

import hashlib
from pathlib import Path
import re
from typing import Any, BinaryIO

from fluency.core.canonical_json import canonical_json_bytes


HASH_ALGORITHM = "sha256"
_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_CONTENT_ID_PATTERN = re.compile(r"^sha256:([0-9a-f]{64})$")


def sha256_digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def content_id(data: bytes) -> str:
    return f"{HASH_ALGORITHM}:{sha256_digest(data)}"


def canonical_content_id(value: Any) -> str:
    return content_id(canonical_json_bytes(value))


def validate_content_id(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("content ID must be a string")
    match = _CONTENT_ID_PATTERN.fullmatch(value)
    if match is None:
        raise ValueError("content ID must have the form sha256:<64 lowercase hex digits>")
    return match.group(1)


def hash_stream(stream: BinaryIO, *, chunk_size: int = 1024 * 1024) -> str:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    digest = hashlib.sha256()
    while chunk := stream.read(chunk_size):
        digest.update(chunk)
    return digest.hexdigest()


def file_content_id(path: Path) -> str:
    with path.open("rb") as stream:
        digest = hash_stream(stream)
    if not _DIGEST_PATTERN.fullmatch(digest):
        raise AssertionError("SHA-256 returned an invalid digest")
    return f"{HASH_ALGORITHM}:{digest}"

