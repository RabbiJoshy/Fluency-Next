"""External workspace layout, initialization, and diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import tempfile
import uuid

from fluency.core.canonical_json import canonical_json


WORKSPACE_SCHEMA_VERSION = "workspace/v1"
WORKSPACE_MARKER = "workspace.json"
REQUIRED_DIRECTORIES = (
    "raw",
    "objects/sha256",
    "cache/downloads",
    "cache/models",
    "cache/derived",
    "runs",
    "registries",
    "releases",
    "trash",
    ".fluency/locks",
    ".fluency/temporary",
)
GENERATED_CODE_ROOT_NAMES = frozenset(
    {"objects", "runs", "registries", "releases", "raw"}
)

RAW_README = """# Raw source snapshots

Raw inputs are append-only. Never overwrite a downloaded or imported snapshot.
Source-specific subfolders are introduced only when their ingestion layer is
approved.
"""


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class Diagnostic:
    name: str
    ok: bool
    detail: str


@dataclass(frozen=True, slots=True)
class Workspace:
    root: Path
    workspace_id: str
    created_at: str

    @property
    def marker_path(self) -> Path:
        return self.root / WORKSPACE_MARKER

    def to_dict(self) -> dict[str, str]:
        return {
            "schema_version": WORKSPACE_SCHEMA_VERSION,
            "workspace_id": self.workspace_id,
            "created_at": self.created_at,
        }

    @classmethod
    def initialize(cls, root: Path) -> "Workspace":
        root = root.expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        marker_path = root / WORKSPACE_MARKER

        if marker_path.exists():
            workspace = cls.load(root)
            workspace._ensure_directories()
            workspace._ensure_raw_readme()
            return workspace

        unexpected = [
            entry.name for entry in root.iterdir() if entry.name not in {".DS_Store"}
        ]
        if unexpected:
            names = ", ".join(sorted(unexpected))
            raise ValueError(
                f"refusing to initialize a non-empty workspace without a marker: {names}"
            )

        workspace = cls(
            root=root,
            workspace_id=f"workspace_{uuid.uuid4().hex}",
            created_at=utc_now(),
        )
        workspace._ensure_directories()
        workspace._ensure_raw_readme()
        workspace._write_marker_atomically()
        return workspace

    @classmethod
    def load(cls, root: Path) -> "Workspace":
        root = root.expanduser().resolve()
        marker_path = root / WORKSPACE_MARKER
        try:
            record = json.loads(marker_path.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise ValueError(f"workspace marker does not exist: {marker_path}") from error
        except json.JSONDecodeError as error:
            raise ValueError(f"workspace marker is not valid JSON: {marker_path}") from error

        if record.get("schema_version") != WORKSPACE_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported workspace schema: {record.get('schema_version')!r}"
            )
        workspace_id = record.get("workspace_id")
        created_at = record.get("created_at")
        if not isinstance(workspace_id, str) or not workspace_id.startswith("workspace_"):
            raise ValueError("workspace marker has an invalid workspace_id")
        if not isinstance(created_at, str) or not created_at:
            raise ValueError("workspace marker has an invalid created_at")
        return cls(root=root, workspace_id=workspace_id, created_at=created_at)

    def _ensure_directories(self) -> None:
        for relative_path in REQUIRED_DIRECTORIES:
            (self.root / relative_path).mkdir(parents=True, exist_ok=True)

    def _ensure_raw_readme(self) -> None:
        readme = self.root / "raw" / "README.md"
        if not readme.exists():
            readme.write_text(RAW_README, encoding="utf-8")

    def _write_marker_atomically(self) -> None:
        temporary_root = self.root / ".fluency" / "temporary"
        descriptor, temporary_name = tempfile.mkstemp(
            dir=temporary_root,
            prefix="workspace-",
            suffix=".json",
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(canonical_json(self.to_dict()))
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, self.marker_path)
        finally:
            temporary_path.unlink(missing_ok=True)

    def doctor(self, *, code_root: Path | None = None) -> tuple[Diagnostic, ...]:
        diagnostics: list[Diagnostic] = []

        try:
            loaded = self.load(self.root)
            marker_ok = loaded.workspace_id == self.workspace_id
            marker_detail = (
                f"schema {WORKSPACE_SCHEMA_VERSION}, ID {loaded.workspace_id}"
                if marker_ok
                else "loaded workspace ID does not match"
            )
        except ValueError as error:
            marker_ok = False
            marker_detail = str(error)
        diagnostics.append(Diagnostic("workspace marker", marker_ok, marker_detail))

        missing = [
            relative
            for relative in REQUIRED_DIRECTORIES
            if not (self.root / relative).is_dir()
        ]
        diagnostics.append(
            Diagnostic(
                "required directories",
                not missing,
                "all required directories exist"
                if not missing
                else f"missing: {', '.join(missing)}",
            )
        )

        readable = os.access(self.root, os.R_OK)
        writable = os.access(self.root, os.W_OK)
        diagnostics.append(
            Diagnostic(
                "workspace access",
                readable and writable,
                f"readable={readable}, writable={writable}",
            )
        )

        temporary_root = self.root / ".fluency" / "temporary"
        object_root = self.root / "objects" / "sha256"
        try:
            same_device = temporary_root.stat().st_dev == object_root.stat().st_dev
            device_detail = (
                "temporary and object directories share a filesystem"
                if same_device
                else "temporary and object directories are on different filesystems"
            )
        except FileNotFoundError:
            same_device = False
            device_detail = "cannot inspect filesystem compatibility"
        diagnostics.append(Diagnostic("atomic promotion", same_device, device_detail))

        if code_root is not None:
            resolved_code_root = code_root.expanduser().resolve()
            generated = sorted(
                name
                for name in GENERATED_CODE_ROOT_NAMES
                if (resolved_code_root / name).exists()
            )
            separate = (
                resolved_code_root != self.root
                and resolved_code_root not in self.root.parents
                and self.root not in resolved_code_root.parents
            )
            ok = separate and not generated
            details: list[str] = []
            if not separate:
                details.append("code and workspace roots overlap")
            if generated:
                details.append(f"generated roots in code repository: {', '.join(generated)}")
            diagnostics.append(
                Diagnostic(
                    "code/data separation",
                    ok,
                    "; ".join(details) if details else "code and generated data are separate",
                )
            )

        return tuple(diagnostics)

