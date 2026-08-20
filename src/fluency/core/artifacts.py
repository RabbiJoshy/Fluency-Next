"""Immutable, content-addressed artifact storage."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Iterator

from fluency.core.canonical_json import canonical_json
from fluency.core.hashing import content_id, file_content_id, validate_content_id
from fluency.core.workspace import Workspace


ARTIFACT_MANIFEST_VERSION = "artifact/v1"


def _validate_filename(filename: str) -> None:
    if not isinstance(filename, str) or not filename:
        raise ValueError("artifact filename must be a non-empty string")
    if Path(filename).name != filename or filename in {".", "..", "artifact.json"}:
        raise ValueError("artifact filename must be a safe basename")


@dataclass(frozen=True, slots=True)
class ArtifactMetadata:
    artifact_id: str
    media_type: str
    schema: str
    filename: str
    byte_size: int
    created_by_stage: str
    row_count: int | None = None

    def __post_init__(self) -> None:
        validate_content_id(self.artifact_id)
        _validate_filename(self.filename)
        if not self.media_type:
            raise ValueError("media_type must not be empty")
        if not self.schema:
            raise ValueError("schema must not be empty")
        if not self.created_by_stage:
            raise ValueError("created_by_stage must not be empty")
        if self.byte_size < 0:
            raise ValueError("byte_size must not be negative")
        if self.row_count is not None and self.row_count < 0:
            raise ValueError("row_count must not be negative")

    def to_dict(self) -> dict[str, str | int]:
        record: dict[str, str | int] = {
            "manifest_version": ARTIFACT_MANIFEST_VERSION,
            "artifact_id": self.artifact_id,
            "media_type": self.media_type,
            "schema": self.schema,
            "filename": self.filename,
            "byte_size": self.byte_size,
            "created_by_stage": self.created_by_stage,
        }
        if self.row_count is not None:
            record["row_count"] = self.row_count
        return record

    @classmethod
    def from_dict(cls, record: dict[str, object]) -> "ArtifactMetadata":
        if record.get("manifest_version") != ARTIFACT_MANIFEST_VERSION:
            raise ValueError("unsupported artifact manifest version")
        try:
            return cls(
                artifact_id=str(record["artifact_id"]),
                media_type=str(record["media_type"]),
                schema=str(record["schema"]),
                filename=str(record["filename"]),
                byte_size=int(record["byte_size"]),
                created_by_stage=str(record["created_by_stage"]),
                row_count=(
                    None if "row_count" not in record else int(record["row_count"])
                ),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("invalid artifact manifest") from error


def artifact_directory(workspace: Workspace, artifact_id: str) -> Path:
    digest = validate_content_id(artifact_id)
    return workspace.root / "objects" / "sha256" / digest[:2] / digest[2:]


def load_artifact(workspace: Workspace, artifact_id: str) -> ArtifactMetadata:
    directory = artifact_directory(workspace, artifact_id)
    manifest_path = directory / "artifact.json"
    try:
        record = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as error:
        raise ValueError(f"artifact manifest is unavailable: {artifact_id}") from error
    metadata = ArtifactMetadata.from_dict(record)
    if metadata.artifact_id != artifact_id:
        raise ValueError("artifact manifest ID does not match its object path")
    return metadata


def verify_artifact(workspace: Workspace, artifact_id: str) -> ArtifactMetadata:
    metadata = load_artifact(workspace, artifact_id)
    payload = artifact_directory(workspace, artifact_id) / metadata.filename
    if not payload.is_file():
        raise ValueError(f"artifact payload is unavailable: {artifact_id}")
    if payload.stat().st_size != metadata.byte_size:
        raise ValueError(f"artifact byte size does not match: {artifact_id}")
    if file_content_id(payload) != artifact_id:
        raise ValueError(f"artifact content hash does not match: {artifact_id}")
    return metadata


def _require_compatible_metadata(
    existing: ArtifactMetadata,
    *,
    filename: str,
    media_type: str,
    schema: str,
    row_count: int | None,
) -> None:
    requested = {
        "filename": filename,
        "media_type": media_type,
        "schema": schema,
        "row_count": row_count,
    }
    actual = {
        "filename": existing.filename,
        "media_type": existing.media_type,
        "schema": existing.schema,
        "row_count": existing.row_count,
    }
    if requested != actual:
        raise ValueError(
            "identical artifact bytes were requested with incompatible metadata: "
            f"existing={actual!r}, requested={requested!r}"
        )


@contextmanager
def _artifact_lock(workspace: Workspace, digest: str) -> Iterator[None]:
    lock_path = workspace.root / ".fluency" / "locks" / f"artifact-{digest}.lock"
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError as error:
        raise RuntimeError(f"artifact is locked by another writer: sha256:{digest}") from error
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(f"pid={os.getpid()}\n")
        yield
    finally:
        lock_path.unlink(missing_ok=True)


def store_artifact_bytes(
    workspace: Workspace,
    data: bytes,
    *,
    filename: str,
    media_type: str,
    schema: str,
    created_by_stage: str,
    row_count: int | None = None,
) -> ArtifactMetadata:
    """Atomically store bytes once and return their immutable metadata."""

    if not isinstance(data, bytes):
        raise TypeError("artifact data must be bytes")
    _validate_filename(filename)
    artifact_id = content_id(data)
    digest = validate_content_id(artifact_id)
    target = artifact_directory(workspace, artifact_id)

    if target.exists():
        existing = verify_artifact(workspace, artifact_id)
        _require_compatible_metadata(
            existing,
            filename=filename,
            media_type=media_type,
            schema=schema,
            row_count=row_count,
        )
        return existing

    metadata = ArtifactMetadata(
        artifact_id=artifact_id,
        media_type=media_type,
        schema=schema,
        filename=filename,
        byte_size=len(data),
        created_by_stage=created_by_stage,
        row_count=row_count,
    )

    with _artifact_lock(workspace, digest):
        if target.exists():
            existing = verify_artifact(workspace, artifact_id)
            _require_compatible_metadata(
                existing,
                filename=filename,
                media_type=media_type,
                schema=schema,
                row_count=row_count,
            )
            return existing

        target.parent.mkdir(parents=True, exist_ok=True)
        temporary_parent = workspace.root / ".fluency" / "temporary"
        temporary = Path(tempfile.mkdtemp(prefix="artifact-", dir=temporary_parent))
        try:
            payload_path = temporary / filename
            payload_path.write_bytes(data)
            manifest_path = temporary / "artifact.json"
            manifest_path.write_text(
                canonical_json(metadata.to_dict()) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)

    return verify_artifact(workspace, artifact_id)
