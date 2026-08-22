"""Typed, language-agnostic records for raw lyrics and line alignments."""

from __future__ import annotations

from typing import Any

from fluency.core.hashing import canonical_content_id


RAW_SONG_VERSION = "raw-lyrics-song/v1"
LINE_VERSION = "lyrics-line/v1"
ALIGNMENT_VERSION = "lyrics-line-alignment/v1"


class LyricsRecordError(ValueError):
    """Raised when a source adapter emits an ambiguous lyrics record."""


def _stable_id(prefix: str, value: object) -> str:
    digest = canonical_content_id(value).removeprefix("sha256:")
    return f"{prefix}_{digest[:32]}"


def build_song_id(*, adapter: str, snapshot_content_id: str, source_record_id: str) -> str:
    return _stable_id(
        "song",
        {
            "record_version": RAW_SONG_VERSION,
            "adapter": adapter,
            "snapshot_content_id": snapshot_content_id,
            "source_record_id": source_record_id,
        },
    )


def build_section_id(*, song_id: str, ordinal: int, label: str) -> str:
    return _stable_id(
        "section",
        {"record_version": LINE_VERSION, "song_id": song_id, "ordinal": ordinal, "label": label},
    )


def build_line_id(*, song_id: str, source_position: int, text: str) -> str:
    return _stable_id(
        "line",
        {
            "record_version": LINE_VERSION,
            "song_id": song_id,
            "source_position": source_position,
            "text": text,
        },
    )


def build_alignment_id(
    *, line_id: str, language: str, text: str, snapshot_content_id: str
) -> str:
    return _stable_id(
        "alignment",
        {
            "record_version": ALIGNMENT_VERSION,
            "line_id": line_id,
            "language": language,
            "text": text,
            "snapshot_content_id": snapshot_content_id,
        },
    )


def validate_raw_song(record: dict[str, Any]) -> None:
    if record.get("record_version") != RAW_SONG_VERSION:
        raise LyricsRecordError("unsupported raw lyrics song record")
    for field in ("song_id", "language", "title", "raw_text"):
        if not isinstance(record.get(field), str) or not record[field]:
            raise LyricsRecordError(f"raw song {field} is missing")
    if not record["song_id"].startswith("song_"):
        raise LyricsRecordError("raw song identity is invalid")
    artist = record.get("artist")
    if not isinstance(artist, dict) or not all(
        isinstance(artist.get(field), str) and artist[field] for field in ("id", "name")
    ):
        raise LyricsRecordError("raw song artist identity is incomplete")
    source = record.get("source")
    if not isinstance(source, dict):
        raise LyricsRecordError("raw song source provenance is missing")
    for field in (
        "name",
        "adapter",
        "snapshot_id",
        "snapshot_content_id",
        "source_record_id",
        "license",
        "attribution",
    ):
        if not isinstance(source.get(field), str) or not source[field]:
            raise LyricsRecordError(f"raw song source {field} is missing")


def validate_lyrics_line(record: dict[str, Any], *, song_id: str, language: str) -> None:
    if record.get("record_version") != LINE_VERSION:
        raise LyricsRecordError("unsupported lyrics line record")
    if record.get("song_id") != song_id or record.get("language") != language:
        raise LyricsRecordError("lyrics line scope does not match its song")
    if not isinstance(record.get("line_id"), str) or not record["line_id"].startswith("line_"):
        raise LyricsRecordError("lyrics line identity is invalid")
    if not isinstance(record.get("text"), str) or not record["text"].strip():
        raise LyricsRecordError("lyrics line text is missing")
    span = record.get("source_span")
    if (
        not isinstance(span, list)
        or len(span) != 2
        or not all(isinstance(value, int) for value in span)
        or span[0] < 0
        or span[1] <= span[0]
    ):
        raise LyricsRecordError("lyrics line source span is invalid")


def validate_line_alignment(record: dict[str, Any], *, line_ids: set[str]) -> None:
    if record.get("record_version") != ALIGNMENT_VERSION:
        raise LyricsRecordError("unsupported lyrics alignment record")
    if record.get("line_id") not in line_ids:
        raise LyricsRecordError("alignment refers to an unknown lyrics line")
    target = record.get("target")
    if not isinstance(target, dict):
        raise LyricsRecordError("alignment target is missing")
    for field in ("language", "text"):
        if not isinstance(target.get(field), str) or not target[field].strip():
            raise LyricsRecordError(f"alignment target {field} is missing")
    source = record.get("source")
    if not isinstance(source, dict):
        raise LyricsRecordError("alignment provenance is missing")
    for field in ("adapter", "snapshot_content_id", "method"):
        if not isinstance(source.get(field), str) or not source[field]:
            raise LyricsRecordError(f"alignment source {field} is missing")

