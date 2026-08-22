"""Streaming adapter for the bilingual Tatoeba archive distributed by ManyThings."""

from __future__ import annotations

from collections import Counter
import csv
from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Any, Iterator
from zipfile import BadZipFile, ZipFile

from fluency.core.hashing import file_content_id
from fluency.harvest.records import RECORD_VERSION, build_sentence_id


ATTRIBUTION_PATTERN = re.compile(
    r"tatoeba\.org\s+#(?P<translation_id>\d+)\s+\((?P<translation_contributor>[^)]*)\)"
    r"\s*&\s*#(?P<target_id>\d+)\s+\((?P<target_contributor>[^)]*)\)"
)
DATE_PATTERN = re.compile(r"Date of this file:\s*(\d{4}-\d{2}-\d{2})")


class TatoebaAdapterError(ValueError):
    """Raised when a Tatoeba snapshot cannot satisfy its pinned adapter policy."""


@dataclass(slots=True)
class TatoebaAdapter:
    path: Path
    target_language: str
    policy: dict[str, Any]
    snapshot_content_id: str = field(init=False)
    rejections: Counter[str] = field(init=False)
    rows_seen: int = field(init=False, default=0)
    rows_emitted: int = field(init=False, default=0)
    snapshot_date: str | None = field(init=False, default=None)
    snapshot_id: str = field(init=False)

    def __post_init__(self) -> None:
        self.path = self.path.expanduser().resolve()
        if not self.path.is_file():
            raise TatoebaAdapterError(f"Tatoeba snapshot does not exist: {self.path}")
        self.snapshot_content_id = file_content_id(self.path)
        self.rejections: Counter[str] = Counter()
        self.rows_seen = 0
        self.rows_emitted = 0
        self.snapshot_date: str | None = None
        self.snapshot_id = f"tatoeba-unknown-{self.snapshot_content_id[-8:]}"

    def _member_name(self) -> str:
        try:
            return self.policy["archive_member_by_language"][self.target_language]
        except KeyError as error:
            raise TatoebaAdapterError(
                f"Tatoeba policy has no member for language {self.target_language!r}"
            ) from error

    def _read_snapshot_date(self, archive: ZipFile) -> None:
        about = next((name for name in archive.namelist() if name.endswith("_about.txt")), None)
        if about is None:
            return
        text = archive.read(about).decode("utf-8", errors="replace")
        match = DATE_PATTERN.search(text)
        if match is not None:
            self.snapshot_date = match.group(1)
            self.snapshot_id = f"tatoeba-{self.snapshot_date}-{self.snapshot_content_id[-8:]}"

    def iter_records(self) -> Iterator[dict[str, Any]]:
        member = self._member_name()
        try:
            archive = ZipFile(self.path)
        except BadZipFile as error:
            raise TatoebaAdapterError(f"Tatoeba snapshot is not a valid ZIP: {self.path}") from error
        with archive:
            self._read_snapshot_date(archive)
            try:
                raw_stream = archive.open(member)
            except KeyError as error:
                raise TatoebaAdapterError(
                    f"Tatoeba snapshot does not contain configured member {member!r}"
                ) from error
            with raw_stream:
                rows = csv.reader(
                    (line.decode("utf-8", errors="strict") for line in raw_stream),
                    delimiter="\t",
                )
                for row in rows:
                    self.rows_seen += 1
                    record = self._parse_row(row)
                    if record is not None:
                        self.rows_emitted += 1
                        yield record

    def _parse_row(self, row: list[str]) -> dict[str, Any] | None:
        columns = self.policy["columns"]
        required_index = max(columns.values())
        if len(row) <= required_index:
            self.rejections["missing_columns"] += 1
            return None
        translation_text = row[columns["translation_text"]].strip()
        target_text = row[columns["target_text"]].strip()
        attribution = row[columns["attribution"]].strip()
        if not target_text or not translation_text:
            self.rejections["empty_text"] += 1
            return None
        attribution_match = ATTRIBUTION_PATTERN.search(attribution)
        if attribution_match is None:
            self.rejections["unparsed_attribution"] += 1
            return None
        license_name = self.policy["license_prefix"]
        if not attribution.startswith(license_name):
            self.rejections["unexpected_license"] += 1
            return None

        fields = attribution_match.groupdict()
        source_record_id = f"{fields['target_id']}:{fields['translation_id']}"
        sentence_id = build_sentence_id(
            adapter=self.policy["adapter"],
            snapshot_content_id=self.snapshot_content_id,
            source_record_id=source_record_id,
            target_text=target_text,
            translation_text=translation_text,
        )
        url_template = self.policy["sentence_url_template"]
        return {
            "record_version": RECORD_VERSION,
            "sentence_id": sentence_id,
            "source": {
                "name": self.policy["source"],
                "adapter": self.policy["adapter"],
                "snapshot_id": self.snapshot_id,
                "snapshot_content_id": self.snapshot_content_id,
                "source_record_id": source_record_id,
                "license": license_name,
                "attribution": attribution,
                "url": url_template.format(sentence_id=fields["target_id"]),
            },
            "target": {
                "language": self.target_language,
                "text": target_text,
                "source_sentence_id": fields["target_id"],
                "contributor": fields["target_contributor"],
                "url": url_template.format(sentence_id=fields["target_id"]),
            },
            "translation": {
                "language": self.policy["translation_language"],
                "text": translation_text,
                "source_sentence_id": fields["translation_id"],
                "contributor": fields["translation_contributor"],
                "url": url_template.format(sentence_id=fields["translation_id"]),
            },
        }

    def report(self) -> dict[str, Any]:
        return {
            "source": self.policy["source"],
            "adapter": self.policy["adapter"],
            "snapshot_path": str(self.path),
            "snapshot_id": self.snapshot_id,
            "snapshot_content_id": self.snapshot_content_id,
            "snapshot_date": self.snapshot_date,
            "rows_seen": self.rows_seen,
            "rows_emitted": self.rows_emitted,
            "adapter_rejections": dict(sorted(self.rejections.items())),
        }
