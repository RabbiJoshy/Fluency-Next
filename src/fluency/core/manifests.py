"""Immutable run and stage manifest contracts."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
import re
import secrets
from typing import Mapping

from fluency.core.hashing import canonical_content_id, validate_content_id


RUN_MANIFEST_VERSION = "run/v1"
STAGE_MANIFEST_VERSION = "stage/v1"
RUN_STATUSES = frozenset({"created", "running", "complete", "failed", "interrupted"})
STAGE_STATUSES = frozenset({"running", "complete", "failed", "interrupted"})

_RUN_ID_PATTERN = re.compile(r"^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$")
_SLUG_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*$")
_LANGUAGE_PATTERN = re.compile(r"^[a-z]{2,3}$")


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def create_run_id(
    *,
    started_at: datetime | None = None,
    suffix: str | None = None,
) -> str:
    started_at = datetime.now(UTC) if started_at is None else started_at
    if started_at.tzinfo is None:
        raise ValueError("run start time must be timezone-aware")
    suffix = secrets.token_hex(4) if suffix is None else suffix
    if re.fullmatch(r"[0-9a-f]{8}", suffix) is None:
        raise ValueError("run suffix must contain eight lowercase hexadecimal digits")
    timestamp = started_at.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}-{suffix}"


def build_stage_cache_key(
    *,
    stage_name: str,
    stage_version: str,
    implementation_hash: str,
    config_hash: str,
    inputs: Mapping[str, str],
    model_revisions: Mapping[str, str],
    random_seed: int,
) -> str:
    for value in (implementation_hash, config_hash, *inputs.values()):
        validate_content_id(value)
    payload = {
        "stage_name": stage_name,
        "stage_version": stage_version,
        "implementation_hash": implementation_hash,
        "config_hash": config_hash,
        "inputs": dict(sorted(inputs.items())),
        "model_revisions": dict(sorted(model_revisions.items())),
        "random_seed": random_seed,
    }
    return canonical_content_id(payload)


@dataclass(frozen=True, slots=True)
class RunManifest:
    run_id: str
    language: str
    mode: str
    profile: str
    status: str
    created_at: str
    config_hash: str
    inputs: Mapping[str, str]
    stages: tuple[str, ...] = ()
    git_commit: str | None = None
    completed_at: str | None = None

    def __post_init__(self) -> None:
        if _RUN_ID_PATTERN.fullmatch(self.run_id) is None:
            raise ValueError("invalid run_id")
        if _LANGUAGE_PATTERN.fullmatch(self.language) is None:
            raise ValueError("invalid run language")
        for name, value in (("mode", self.mode), ("profile", self.profile)):
            if _SLUG_PATTERN.fullmatch(value) is None:
                raise ValueError(f"invalid run {name}")
        if self.status not in RUN_STATUSES:
            raise ValueError("invalid run status")
        validate_content_id(self.config_hash)
        for artifact_id in self.inputs.values():
            validate_content_id(artifact_id)
        if self.status == "complete" and self.completed_at is None:
            raise ValueError("a complete run requires completed_at")

    def to_dict(self) -> dict[str, object]:
        record: dict[str, object] = {
            "manifest_version": RUN_MANIFEST_VERSION,
            "run_id": self.run_id,
            "language": self.language,
            "mode": self.mode,
            "profile": self.profile,
            "status": self.status,
            "created_at": self.created_at,
            "config_hash": self.config_hash,
            "inputs": dict(sorted(self.inputs.items())),
            "stages": list(self.stages),
        }
        if self.git_commit is not None:
            record["git_commit"] = self.git_commit
        if self.completed_at is not None:
            record["completed_at"] = self.completed_at
        return record

    def with_status(self, status: str, *, at: datetime | None = None) -> "RunManifest":
        completed_at = self.completed_at
        if status in {"complete", "failed", "interrupted"}:
            completed_at = _utc_text(datetime.now(UTC) if at is None else at)
        return replace(self, status=status, completed_at=completed_at)


def create_run_manifest(
    *,
    language: str,
    mode: str,
    profile: str,
    config_hash: str,
    inputs: Mapping[str, str],
    git_commit: str | None = None,
    started_at: datetime | None = None,
    suffix: str | None = None,
) -> RunManifest:
    started_at = datetime.now(UTC) if started_at is None else started_at
    return RunManifest(
        run_id=create_run_id(started_at=started_at, suffix=suffix),
        language=language,
        mode=mode,
        profile=profile,
        status="created",
        created_at=_utc_text(started_at),
        config_hash=config_hash,
        inputs=dict(inputs),
        git_commit=git_commit,
    )


@dataclass(frozen=True, slots=True)
class StageManifest:
    stage_name: str
    stage_version: str
    cache_key: str
    implementation_hash: str
    config_hash: str
    status: str
    started_at: str
    inputs: Mapping[str, str]
    model_revisions: Mapping[str, str]
    random_seed: int
    outputs: Mapping[str, str]
    completed_at: str | None = None

    def __post_init__(self) -> None:
        if _SLUG_PATTERN.fullmatch(self.stage_name) is None:
            raise ValueError("invalid stage_name")
        if not self.stage_version:
            raise ValueError("stage_version must not be empty")
        for value in (
            self.cache_key,
            self.implementation_hash,
            self.config_hash,
            *self.inputs.values(),
            *self.outputs.values(),
        ):
            validate_content_id(value)
        if self.status not in STAGE_STATUSES:
            raise ValueError("invalid stage status")
        if self.status == "complete" and self.completed_at is None:
            raise ValueError("a complete stage requires completed_at")

    def to_dict(self) -> dict[str, object]:
        record: dict[str, object] = {
            "manifest_version": STAGE_MANIFEST_VERSION,
            "stage_name": self.stage_name,
            "stage_version": self.stage_version,
            "cache_key": self.cache_key,
            "implementation_hash": self.implementation_hash,
            "config_hash": self.config_hash,
            "status": self.status,
            "started_at": self.started_at,
            "inputs": dict(sorted(self.inputs.items())),
            "model_revisions": dict(sorted(self.model_revisions.items())),
            "random_seed": self.random_seed,
            "outputs": dict(sorted(self.outputs.items())),
        }
        if self.completed_at is not None:
            record["completed_at"] = self.completed_at
        return record

    def complete(
        self,
        outputs: Mapping[str, str],
        *,
        at: datetime | None = None,
    ) -> "StageManifest":
        return replace(
            self,
            status="complete",
            outputs=dict(outputs),
            completed_at=_utc_text(datetime.now(UTC) if at is None else at),
        )

