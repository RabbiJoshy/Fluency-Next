"""Streaming adapter for line-aligned OpenSubtitles text and provenance files."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from itertools import zip_longest
import json
from pathlib import Path
from typing import Any, Iterator

from fluency.core.hashing import canonical_content_id, file_content_id
from fluency.harvest.records import RECORD_VERSION, build_sentence_id


class OpenSubtitlesAdapterError(ValueError):
    """Raised when an aligned snapshot is incomplete or loses line provenance."""


@dataclass(slots=True)
class OpenSubtitlesAdapter:
    path: Path
    target_language: str
    policy: dict[str, Any]
    snapshot_content_id: str = field(init=False)
    snapshot_id: str = field(init=False)
    metadata: dict[str, Any] = field(init=False)
    files: dict[str, Path] = field(init=False)
    rejections: Counter[str] = field(init=False)
    rows_seen: int = field(init=False, default=0)
    rows_emitted: int = field(init=False, default=0)

    def __post_init__(self) -> None:
        self.path = self.path.expanduser().resolve()
        if not self.path.is_dir():
            raise OpenSubtitlesAdapterError(
                f"OpenSubtitles snapshot must be an aligned directory: {self.path}"
            )
        metadata_path = self.path / "snapshot.json"
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise OpenSubtitlesAdapterError(
                f"OpenSubtitles snapshot metadata does not exist: {metadata_path}"
            ) from error
        except json.JSONDecodeError as error:
            raise OpenSubtitlesAdapterError("OpenSubtitles snapshot metadata is invalid JSON") from error
        if not isinstance(metadata, dict):
            raise OpenSubtitlesAdapterError("OpenSubtitles snapshot metadata must be an object")
        if metadata.get("snapshot_version") != self.policy["snapshot_metadata_version"]:
            raise OpenSubtitlesAdapterError("unsupported OpenSubtitles snapshot metadata")
        if metadata.get("target_language") != self.target_language:
            raise OpenSubtitlesAdapterError("OpenSubtitles target language does not match the run")
        if metadata.get("translation_language") != self.policy["translation_language"]:
            raise OpenSubtitlesAdapterError("OpenSubtitles translation language does not match")
        for field_name in ("snapshot_id", "license", "attribution", "source_url"):
            if not isinstance(metadata.get(field_name), str) or not metadata[field_name]:
                raise OpenSubtitlesAdapterError(
                    f"OpenSubtitles snapshot metadata requires {field_name}"
                )
        self.metadata = metadata
        self.snapshot_id = metadata["snapshot_id"]
        self.files = {
            role: self.path / template.format(language=self.target_language)
            for role, template in self.policy["file_templates"].items()
        }
        missing = [str(path) for path in self.files.values() if not path.is_file()]
        if missing:
            raise OpenSubtitlesAdapterError(
                f"OpenSubtitles aligned snapshot is missing files: {', '.join(missing)}"
            )
        self.snapshot_content_id = canonical_content_id(
            {
                "metadata": file_content_id(metadata_path),
                "files": {
                    role: file_content_id(path)
                    for role, path in sorted(self.files.items())
                },
            }
        )
        self.rejections = Counter()

    @staticmethod
    def _provenance(raw: str, row_number: int) -> dict[str, str | int] | None:
        parts = raw.rstrip("\n").split("\t")
        if len(parts) < 4:
            return None
        segments = parts[1].split("/")
        if len(segments) < 4 or not parts[3]:
            return None
        return {
            "title_id": segments[2],
            "subtitle_id": segments[3].split(".")[0],
            "line": parts[3],
            "aligned_row": row_number,
        }

    def iter_records(self) -> Iterator[dict[str, Any]]:
        with (
            self.files["target_text"].open(encoding="utf-8", errors="strict") as target_stream,
            self.files["translation_text"].open(encoding="utf-8", errors="strict") as translation_stream,
            self.files["provenance_ids"].open(encoding="utf-8", errors="strict") as ids_stream,
        ):
            for row_number, rows in enumerate(
                zip_longest(target_stream, translation_stream, ids_stream), start=1
            ):
                if any(row is None for row in rows):
                    raise OpenSubtitlesAdapterError(
                        "OpenSubtitles target, translation, and provenance files are not line-aligned"
                    )
                self.rows_seen += 1
                target_text = rows[0].strip()
                translation_text = rows[1].strip()
                if not target_text or not translation_text:
                    self.rejections["empty_text"] += 1
                    continue
                document = self._provenance(rows[2], row_number)
                if document is None:
                    self.rejections["unparsed_provenance"] += 1
                    continue
                source_record_id = (
                    f"{document['title_id']}:{document['subtitle_id']}:"
                    f"{document['line']}:{row_number}"
                )
                sentence_id = build_sentence_id(
                    adapter=self.policy["adapter"],
                    snapshot_content_id=self.snapshot_content_id,
                    source_record_id=source_record_id,
                    target_text=target_text,
                    translation_text=translation_text,
                )
                self.rows_emitted += 1
                yield {
                    "record_version": RECORD_VERSION,
                    "sentence_id": sentence_id,
                    "source": {
                        "name": self.policy["source"],
                        "adapter": self.policy["adapter"],
                        "snapshot_id": self.snapshot_id,
                        "snapshot_content_id": self.snapshot_content_id,
                        "source_record_id": source_record_id,
                        "license": self.metadata["license"],
                        "attribution": self.metadata["attribution"],
                        "url": self.metadata["source_url"],
                        "document": document,
                    },
                    "target": {
                        "language": self.target_language,
                        "text": target_text,
                    },
                    "translation": {
                        "language": self.policy["translation_language"],
                        "text": translation_text,
                    },
                }

    def report(self) -> dict[str, Any]:
        return {
            "source": self.policy["source"],
            "adapter": self.policy["adapter"],
            "snapshot_path": str(self.path),
            "snapshot_id": self.snapshot_id,
            "snapshot_content_id": self.snapshot_content_id,
            "rows_seen": self.rows_seen,
            "rows_emitted": self.rows_emitted,
            "adapter_rejections": dict(sorted(self.rejections.items())),
        }
