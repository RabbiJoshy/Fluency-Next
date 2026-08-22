"""Adapter for pinned official Tatoeba per-language weekly exports."""

from __future__ import annotations

import bz2
from collections import Counter
import csv
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Iterator

from fluency.core.hashing import canonical_content_id, file_content_id
from fluency.harvest.records import RECORD_VERSION, build_sentence_id


class TatoebaAdapterError(ValueError):
    """Raised when an official Tatoeba snapshot is incomplete or ambiguous."""


@dataclass(frozen=True, slots=True)
class _Sentence:
    sentence_id: str
    language_code: str
    text: str
    contributor: str
    created_at: str
    modified_at: str


@dataclass(slots=True)
class TatoebaAdapter:
    path: Path
    target_language: str
    policy: dict[str, Any]
    snapshot_content_id: str = field(init=False)
    snapshot_id: str = field(init=False)
    metadata: dict[str, Any] = field(init=False)
    files: dict[str, Path] = field(init=False)
    target_code: str = field(init=False)
    translation_code: str = field(init=False)
    rejections: Counter[str] = field(init=False)
    rows_seen: int = field(init=False, default=0)
    rows_emitted: int = field(init=False, default=0)
    target_rows_scanned: int = field(init=False, default=0)
    translation_rows_scanned: int = field(init=False, default=0)

    def __post_init__(self) -> None:
        self.path = self.path.expanduser().resolve()
        if not self.path.is_dir():
            raise TatoebaAdapterError(
                f"Tatoeba snapshot must be a pinned directory: {self.path}"
            )
        metadata_path = self.path / "snapshot.json"
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise TatoebaAdapterError(
                f"Tatoeba snapshot metadata does not exist: {metadata_path}"
            ) from error
        except json.JSONDecodeError as error:
            raise TatoebaAdapterError("Tatoeba snapshot metadata is invalid JSON") from error
        if not isinstance(metadata, dict):
            raise TatoebaAdapterError("Tatoeba snapshot metadata must be an object")
        if metadata.get("snapshot_version") != self.policy["snapshot_metadata_version"]:
            raise TatoebaAdapterError("unsupported Tatoeba snapshot metadata")
        if metadata.get("target_language") != self.target_language:
            raise TatoebaAdapterError("Tatoeba target language does not match the run")
        if metadata.get("translation_language") != self.policy["translation_language"]:
            raise TatoebaAdapterError("Tatoeba translation language does not match")
        for name in (
            "snapshot_id",
            "target_code",
            "translation_code",
            "license",
            "license_url",
            "attribution",
            "source_url",
        ):
            if not isinstance(metadata.get(name), str) or not metadata[name]:
                raise TatoebaAdapterError(f"Tatoeba snapshot metadata requires {name}")

        language_codes = self.policy["language_codes"]
        if metadata["target_code"] != language_codes.get(self.target_language):
            raise TatoebaAdapterError("Tatoeba target export code does not match policy")
        translation_language = self.policy["translation_language"]
        if metadata["translation_code"] != language_codes.get(translation_language):
            raise TatoebaAdapterError("Tatoeba translation export code does not match policy")
        if metadata["license"] != self.policy["license"]:
            raise TatoebaAdapterError("Tatoeba snapshot license does not match policy")

        self.metadata = metadata
        self.snapshot_id = metadata["snapshot_id"]
        self.target_code = metadata["target_code"]
        self.translation_code = metadata["translation_code"]
        values = {
            "target_code": self.target_code,
            "translation_code": self.translation_code,
        }
        self.files = {
            role: self.path / template.format(**values)
            for role, template in self.policy["file_templates"].items()
        }
        source_files = metadata.get("source_files")
        if not isinstance(source_files, dict) or set(source_files) != set(self.files):
            raise TatoebaAdapterError(
                "Tatoeba snapshot metadata must pin every official source file"
            )
        for role, path in self.files.items():
            source_file = source_files[role]
            if (
                not isinstance(source_file, dict)
                or source_file.get("filename") != path.name
                or not isinstance(source_file.get("url"), str)
                or not source_file["url"].startswith(
                    "https://downloads.tatoeba.org/exports/per_language/"
                )
            ):
                raise TatoebaAdapterError(
                    f"Tatoeba snapshot metadata does not pin {role} correctly"
                )
        missing = [str(path) for path in self.files.values() if not path.is_file()]
        if missing:
            raise TatoebaAdapterError(
                f"Tatoeba snapshot is missing official exports: {', '.join(missing)}"
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
    def _open_tsv(path: Path) -> Iterator[list[str]]:
        with bz2.open(path, "rt", encoding="utf-8", errors="strict", newline="") as stream:
            yield from csv.reader(stream, delimiter="\t")

    def _iter_links(self, *, count: bool) -> Iterator[tuple[str, str]]:
        for row in self._open_tsv(self.files["links"]):
            if count:
                self.rows_seen += 1
            if len(row) != 2 or not row[0].isdigit() or not row[1].isdigit():
                if count:
                    self.rejections["malformed_link"] += 1
                continue
            # The configured official file is translation-target, for example
            # eng-fra_links.tsv.bz2.
            yield row[1], row[0]

    def _load_sentences(
        self,
        path: Path,
        *,
        expected_code: str,
        wanted_ids: set[str],
        target_side: bool,
    ) -> dict[str, _Sentence]:
        records: dict[str, _Sentence] = {}
        side = "target" if target_side else "translation"
        for row in self._open_tsv(path):
            if target_side:
                self.target_rows_scanned += 1
            else:
                self.translation_rows_scanned += 1
            if len(row) != 6:
                self.rejections[f"malformed_{side}_sentence"] += 1
                continue
            sentence_id, language_code, text, contributor, created_at, modified_at = row
            if sentence_id not in wanted_ids:
                continue
            if language_code != expected_code:
                self.rejections[f"wrong_{side}_language"] += 1
                continue
            if not text.strip() or not contributor.strip():
                self.rejections[f"incomplete_{side}_provenance"] += 1
                continue
            records[sentence_id] = _Sentence(
                sentence_id=sentence_id,
                language_code=language_code,
                text=text.strip(),
                contributor=contributor.strip(),
                created_at=created_at,
                modified_at=modified_at,
            )
        return records

    def iter_records(self) -> Iterator[dict[str, Any]]:
        target_ids: set[str] = set()
        translation_ids: set[str] = set()
        for target_id, translation_id in self._iter_links(count=False):
            target_ids.add(target_id)
            translation_ids.add(translation_id)

        targets = self._load_sentences(
            self.files["target_sentences"],
            expected_code=self.target_code,
            wanted_ids=target_ids,
            target_side=True,
        )
        translations = self._load_sentences(
            self.files["translation_sentences"],
            expected_code=self.translation_code,
            wanted_ids=translation_ids,
            target_side=False,
        )
        url_template = self.policy["sentence_url_template"]
        for target_id, translation_id in self._iter_links(count=True):
            target = targets.get(target_id)
            translation = translations.get(translation_id)
            if target is None:
                self.rejections["missing_target_sentence"] += 1
                continue
            if translation is None:
                self.rejections["missing_translation_sentence"] += 1
                continue
            source_record_id = f"{target_id}:{translation_id}"
            sentence_id = build_sentence_id(
                adapter=self.policy["adapter"],
                snapshot_content_id=self.snapshot_content_id,
                source_record_id=source_record_id,
                target_text=target.text,
                translation_text=translation.text,
            )
            target_url = url_template.format(sentence_id=target_id)
            translation_url = url_template.format(sentence_id=translation_id)
            attribution = (
                f"Tatoeba sentence #{target_id} by {target.contributor}; "
                f"English translation #{translation_id} by {translation.contributor}"
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
                    "license_url": self.metadata["license_url"],
                    "attribution": attribution,
                    "url": target_url,
                },
                "target": {
                    "language": self.target_language,
                    "text": target.text,
                    "source_sentence_id": target_id,
                    "contributor": target.contributor,
                    "created_at": target.created_at,
                    "modified_at": target.modified_at,
                    "url": target_url,
                },
                "translation": {
                    "language": self.policy["translation_language"],
                    "text": translation.text,
                    "source_sentence_id": translation_id,
                    "contributor": translation.contributor,
                    "created_at": translation.created_at,
                    "modified_at": translation.modified_at,
                    "url": translation_url,
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
            "target_rows_scanned": self.target_rows_scanned,
            "translation_rows_scanned": self.translation_rows_scanned,
            "adapter_rejections": dict(sorted(self.rejections.items())),
        }
