"""Atomic canonical-JSON writes for release control files."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile

from fluency.core.canonical_json import canonical_json


def json_bytes(value: object) -> bytes:
    return (canonical_json(value) + "\n").encode("utf-8")


def atomic_write(path: Path, value: object, temporary_root: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_root.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(dir=temporary_root, prefix=f"{path.stem}-", suffix=".json")
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(json_bytes(value))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)
