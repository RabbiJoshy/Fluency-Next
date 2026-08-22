"""Small plug-in contract implemented by every corpus adapter."""

from __future__ import annotations

from typing import Any, Iterator, Protocol


class CorpusAdapter(Protocol):
    snapshot_content_id: str

    def iter_records(self) -> Iterator[dict[str, Any]]: ...

    def report(self) -> dict[str, Any]: ...
