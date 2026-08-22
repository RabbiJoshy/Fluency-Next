"""Adapter for a byte-verified retained parallel-sentence bank."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Iterator

from fluency.core.hashing import canonical_content_id, file_content_id
from fluency.harvest.records import RECORD_VERSION, build_sentence_id


class RetainedSentenceBankError(ValueError):
    """Raised when a retained bank differs from its immutable manifest."""


@dataclass(slots=True)
class RetainedSentenceBankAdapter:
    path: Path
    target_language: str
    policy: dict[str, Any]
    snapshot_content_id: str = field(init=False)
    snapshot_id: str = field(init=False)
    metadata: dict[str, Any] = field(init=False)
    bank_path: Path = field(init=False)
    rows_seen: int = field(init=False, default=0)
    rows_emitted: int = field(init=False, default=0)
    rejections: Counter[str] = field(init=False)

    def __post_init__(self) -> None:
        self.path = self.path.expanduser().resolve()
        try:
            metadata = json.loads((self.path / "artifact.json").read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise RetainedSentenceBankError(
                f"retained sentence-bank manifest does not exist: {self.path}"
            ) from error
        except json.JSONDecodeError as error:
            raise RetainedSentenceBankError("retained sentence-bank manifest is invalid JSON") from error
        if not isinstance(metadata, dict):
            raise RetainedSentenceBankError("retained sentence-bank manifest must be an object")
        if metadata.get("schema_version") != self.policy["snapshot_metadata_version"]:
            raise RetainedSentenceBankError("unsupported retained sentence-bank manifest")
        if metadata.get("artifact_kind") != "sentence_bank":
            raise RetainedSentenceBankError("retained artifact is not a sentence bank")
        if metadata.get("language") != self.target_language:
            raise RetainedSentenceBankError("retained sentence-bank language does not match the run")
        if metadata.get("provider") != self.policy["underlying_provider"]:
            raise RetainedSentenceBankError("retained sentence-bank provider does not match")
        if metadata.get("provenance_status") not in {"observed", "reconstructed"}:
            raise RetainedSentenceBankError("retained sentence-bank provenance is unusable")
        for field_name in ("snapshot_id", "license", "content_files"):
            if field_name not in metadata:
                raise RetainedSentenceBankError(
                    f"retained sentence-bank manifest requires {field_name}"
                )
        files = metadata["content_files"]
        if not isinstance(files, list):
            raise RetainedSentenceBankError("retained sentence-bank content list is invalid")
        records = {
            item.get("path"): item
            for item in files
            if isinstance(item, dict) and isinstance(item.get("path"), str)
        }
        required = {"sentence_bank.jsonl", "word_candidates.json", "harvest_manifest.json"}
        if not required.issubset(records):
            raise RetainedSentenceBankError("retained sentence-bank files are incomplete")
        content_ids: dict[str, str] = {}
        for filename in sorted(required):
            path = self.path / filename
            content_id = file_content_id(path)
            if content_id != f"sha256:{records[filename].get('sha256')}":
                raise RetainedSentenceBankError(
                    f"retained sentence-bank content hash changed: {filename}"
                )
            content_ids[filename] = content_id
        self.metadata = metadata
        self.snapshot_id = metadata["snapshot_id"]
        self.bank_path = self.path / "sentence_bank.jsonl"
        self.snapshot_content_id = canonical_content_id(
            {
                "manifest": file_content_id(self.path / "artifact.json"),
                "content_files": content_ids,
            }
        )
        self.rejections = Counter()

    def iter_records(self) -> Iterator[dict[str, Any]]:
        seen: set[str] = set()
        with self.bank_path.open(encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                self.rows_seen += 1
                try:
                    old = json.loads(line)
                except json.JSONDecodeError as error:
                    raise RetainedSentenceBankError(
                        f"retained sentence row is invalid JSON: {line_number}"
                    ) from error
                if not isinstance(old, dict):
                    raise RetainedSentenceBankError("retained sentence row must be an object")
                old_id = old.get("id")
                target_text = old.get("es")
                translation_text = old.get("en")
                provenance = old.get("provenance")
                if (
                    not isinstance(old_id, str)
                    or not old_id
                    or old_id in seen
                    or not isinstance(target_text, str)
                    or not target_text.strip()
                    or not isinstance(translation_text, str)
                    or not translation_text.strip()
                    or not isinstance(provenance, dict)
                ):
                    raise RetainedSentenceBankError("retained sentence row is incomplete or duplicated")
                seen.add(old_id)
                sentence_id = build_sentence_id(
                    adapter=self.policy["adapter"],
                    snapshot_content_id=self.snapshot_content_id,
                    source_record_id=old_id,
                    target_text=target_text,
                    translation_text=translation_text,
                )
                self.rows_emitted += 1
                yield {
                    "record_version": RECORD_VERSION,
                    "sentence_id": sentence_id,
                    "source": {
                        "name": self.policy["underlying_provider"],
                        "adapter": self.policy["adapter"],
                        "snapshot_id": self.snapshot_id,
                        "snapshot_content_id": self.snapshot_content_id,
                        "source_record_id": old_id,
                        "license": self.metadata["license"],
                        "attribution": "OpenSubtitles; recovered from verified Fluency harvest",
                        "url": None,
                        "document": provenance,
                        "provider_data": {
                            "legacy_harvest_run": old.get("harvest_run"),
                            "legacy_quality": {
                                field_name: old.get(field_name)
                                for field_name in (
                                    "score",
                                    "naturalness",
                                    "hard_words",
                                    "tokens",
                                    "gate",
                                )
                            },
                            "provenance_status": self.metadata["provenance_status"],
                        },
                    },
                    "target": {"language": self.target_language, "text": target_text},
                    "translation": {
                        "language": self.policy["translation_language"],
                        "text": translation_text,
                    },
                }

    def report(self) -> dict[str, Any]:
        return {
            "source": self.policy["source"],
            "underlying_provider": self.policy["underlying_provider"],
            "adapter": self.policy["adapter"],
            "snapshot_path": str(self.path),
            "snapshot_id": self.snapshot_id,
            "snapshot_content_id": self.snapshot_content_id,
            "provenance_status": self.metadata["provenance_status"],
            "rows_seen": self.rows_seen,
            "rows_emitted": self.rows_emitted,
            "adapter_rejections": dict(sorted(self.rejections.items())),
        }
