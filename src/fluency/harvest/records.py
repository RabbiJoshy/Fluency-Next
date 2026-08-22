"""Canonical parallel-sentence records shared by all corpus adapters."""

from __future__ import annotations

from typing import Any

from fluency.core.hashing import canonical_content_id


RECORD_VERSION = "parallel-sentence/v1"


class HarvestRecordError(ValueError):
    """Raised when a source adapter emits incomplete or ambiguous provenance."""


def build_sentence_id(
    *,
    adapter: str,
    snapshot_content_id: str,
    source_record_id: str,
    target_text: str,
    translation_text: str,
) -> str:
    identity = canonical_content_id(
        {
            "record_version": RECORD_VERSION,
            "adapter": adapter,
            "snapshot_content_id": snapshot_content_id,
            "source_record_id": source_record_id,
            "target_text": target_text,
            "translation_text": translation_text,
        }
    )
    return f"sentence_{identity.removeprefix('sha256:')[:32]}"


def validate_parallel_sentence(
    record: dict[str, Any],
    *,
    target_language: str,
    provenance_policy: dict[str, Any],
) -> None:
    if record.get("record_version") != RECORD_VERSION:
        raise HarvestRecordError("unsupported parallel-sentence record")
    sentence_id = record.get("sentence_id")
    if not isinstance(sentence_id, str) or not sentence_id.startswith("sentence_"):
        raise HarvestRecordError("sentence_id is missing")

    target = record.get("target")
    translation = record.get("translation")
    source = record.get("source")
    if not isinstance(target, dict) or target.get("language") != target_language:
        raise HarvestRecordError("target language does not match the run")
    if not isinstance(target.get("text"), str) or not target["text"].strip():
        raise HarvestRecordError("target text is missing")
    if not isinstance(translation, dict) or not isinstance(translation.get("language"), str):
        raise HarvestRecordError("translation language is missing")
    if not isinstance(translation.get("text"), str) or not translation["text"].strip():
        raise HarvestRecordError("translation text is missing")
    if not isinstance(source, dict):
        raise HarvestRecordError("source provenance is missing")
    for field in ("name", "adapter", "snapshot_id", "snapshot_content_id"):
        if not isinstance(source.get(field), str) or not source[field]:
            raise HarvestRecordError(f"source {field} is missing")
    required = {
        "attribution": provenance_policy["require_attribution"],
        "license": provenance_policy["require_license"],
        "source_record_id": provenance_policy["require_source_record_id"],
    }
    for field, enabled in required.items():
        if enabled and (not isinstance(source.get(field), str) or not source[field]):
            raise HarvestRecordError(f"source {field} is required")
