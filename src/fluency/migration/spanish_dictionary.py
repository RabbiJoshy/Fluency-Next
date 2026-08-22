"""Pin the approved offline SpanishDict and morphology inputs."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any

from fluency.core.hashing import file_content_id
from fluency.core.workspace import Workspace
from fluency.release.io import json_bytes


MANIFEST_VERSION = "spanishdict-snapshot/v1"
SNAPSHOT_ID = "spanishdict-recovered-2026-08-22-v1"
AUDIT_COMMIT = "23f1ad4387feb4a599815eaa6846e1201b5f402a"
EXPECTED_HASHES = {
    "surface_cache.json": "f0198ff03c124590c5e2a12d8db1439c1cf22b2cf21b09ef10129217843e46ce",
    "headword_cache.json": "7c379cb2641416237b34a191b4f1b63f27acaef13a85cccdc84885795066e98f",
    "spanish_forms.json": "b03b768be013b70e80852a90e8818a37effc2dda50ec6df73e9724403c1535f2",
    "conjugation_reverse.json": "a73e8666f0117b677d5e48bac69089b0b3445e3301906a3639d3ad1b4a04665d",
}


class SpanishDictionaryMigrationError(ValueError):
    """Raised when a dictionary source differs from the approved audit."""


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _clone_or_copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["cp", "-c", "-p", str(source), str(target)],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        shutil.copy2(source, target)


def migrate_spanish_dictionary_snapshot(
    workspace: Workspace,
    *,
    source_repository: Path,
    recovered_at: datetime | None = None,
) -> Path:
    """Copy only offline menu inputs; never copy a built menu or assignments."""

    source_root = source_repository.expanduser().resolve()
    sources = {
        "surface_cache.json": source_root / "Data/Spanish/Senses/spanishdict/surface_cache.json",
        "headword_cache.json": source_root / "Data/Spanish/Senses/spanishdict/headword_cache.json",
        "spanish_forms.json": source_root / "Data/Spanish/layers/spanish_forms.json",
        "conjugation_reverse.json": source_root / "Data/Spanish/layers/conjugation_reverse.json",
    }
    target = workspace.root / f"raw/dictionaries/es/spanishdict/{SNAPSHOT_ID}"
    if target.exists():
        raise SpanishDictionaryMigrationError(
            f"SpanishDict snapshot already exists; refusing overwrite: {target}"
        )
    recovered_at = datetime.now(UTC) if recovered_at is None else recovered_at
    temporary_root = workspace.root / ".fluency/temporary"
    temporary = Path(tempfile.mkdtemp(prefix="spanishdict-snapshot-", dir=temporary_root))
    try:
        content_files: list[dict[str, Any]] = []
        for filename, source in sources.items():
            if not source.is_file():
                raise SpanishDictionaryMigrationError(f"dictionary source is missing: {source}")
            destination = temporary / filename
            _clone_or_copy(source, destination)
            digest = file_content_id(destination).removeprefix("sha256:")
            if digest != EXPECTED_HASHES[filename]:
                raise SpanishDictionaryMigrationError(
                    f"dictionary source hash changed: {source}"
                )
            content_files.append(
                {"path": filename, "sha256": digest, "bytes": destination.stat().st_size}
            )

        surface_cache = json.loads((temporary / "surface_cache.json").read_text(encoding="utf-8"))
        headword_cache = json.loads((temporary / "headword_cache.json").read_text(encoding="utf-8"))
        spanish_forms = json.loads((temporary / "spanish_forms.json").read_text(encoding="utf-8"))
        conjugation_reverse = json.loads(
            (temporary / "conjugation_reverse.json").read_text(encoding="utf-8")
        )
        if not all(
            isinstance(value, dict)
            for value in (surface_cache, headword_cache, spanish_forms, conjugation_reverse)
        ):
            raise SpanishDictionaryMigrationError("dictionary inputs must be JSON objects")
        manifest = {
            "schema_version": MANIFEST_VERSION,
            "artifact_kind": "dictionary_menu_source",
            "language": "es",
            "provider": "spanishdict",
            "snapshot_id": SNAPSHOT_ID,
            "provenance_status": "reconstructed",
            "recovered_at": _timestamp(recovered_at),
            "recovered_from": {
                "repository": str(source_root),
                "audit_commit": AUDIT_COMMIT,
            },
            "content_files": content_files,
            "coverage": {
                "surface_cache_entries": len(surface_cache),
                "headword_cache_entries": len(headword_cache),
                "spanish_form_entries": len(spanish_forms),
                "reverse_conjugation_entries": len(conjugation_reverse),
            },
            "notes": [
                "These are deterministic offline menu inputs, not a normalized menu.",
                "No HTTP client, WSD assignment, final example selection or release is included.",
            ],
        }
        (temporary / "artifact.json").write_bytes(json_bytes(manifest))
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return target
