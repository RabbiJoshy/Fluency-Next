"""Pin the small derived assets required to reproduce Spanish WSD v5."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

from fluency.core.hashing import file_content_id
from fluency.core.workspace import Workspace
from fluency.release.io import json_bytes


SOURCE_METHOD_COMMIT = "78506bf6ee785049393b2a760eceecd083c53495"
ASSET_CREATION_COMMIT = "69657291"
EXPECTED_HASHES = {
    "prototypes/proto.npy": "1ec0de1d85cdb608af3c8b579a90bbc4a1db8d62957c3d8a30e7d58456595777",
    "prototypes/proto_index.json": "146f2d9af3e34f2df4deaaab48df9588a0874405e016388ea45ea9659175500e",
    "prototypes/proto_counts.json": "b8e2224263604c74a767c59daf02925013ed5537e3f71def8d1ab9b55843c4aa",
    "prototypes/manifest.json": "cb1944ae304a38b31e8943e8bf511e8cb262ac56f32640628aaf8f717c20cdad",
    "calibrator/calibrator.joblib": "bf1ea4d6116dd7eeaf377428cf62deb2bce0c4af75d402764e698255e281dd55",
    "calibrator/manifest.json": "fab2ef1dc7553b597b4be26f663b4aadb0ed9c70a64d06659590a7d785ac1930",
}


class SpanishWSDAssetMigrationError(ValueError):
    pass


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _copy(source: Path, target: Path, digest: str) -> dict[str, Any]:
    if not source.is_file():
        raise SpanishWSDAssetMigrationError(f"required WSD asset is missing: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    if file_content_id(target) != f"sha256:{digest}":
        raise SpanishWSDAssetMigrationError(f"WSD asset hash changed: {source}")
    return {"path": target.name, "sha256": digest, "bytes": target.stat().st_size}


def migrate_spanish_wsd_assets(
    workspace: Workspace,
    *,
    source_repository: Path,
    recovered_at: datetime | None = None,
) -> dict[str, Path]:
    """Copy prototypes/calibrator only; assignments and old token caches stay out."""

    source = source_repository.expanduser().resolve() / "Data/Spanish/layers"
    targets = {
        "prototypes": workspace.root / "raw/wsd/assets/es/beto/prototypes-sd-beto-cal-v5-v1",
        "calibrator": workspace.root / "raw/wsd/assets/es/calibration/sd-beto-cal-v5-legacy-v1",
    }
    existing = [str(path) for path in targets.values() if path.exists()]
    if existing:
        raise SpanishWSDAssetMigrationError("WSD asset target already exists: " + ", ".join(existing))
    sources = {
        "prototypes": {
            name: source / "token_prototypes" / name
            for name in ("proto.npy", "proto_index.json", "proto_counts.json", "manifest.json")
        },
        "calibrator": {
            name: source / "wsd_calibrator" / name
            for name in ("calibrator.joblib", "manifest.json")
        },
    }
    recovered_at = datetime.now(UTC) if recovered_at is None else recovered_at
    temporary_root = workspace.root / ".fluency/temporary"
    temporary = Path(tempfile.mkdtemp(prefix="spanish-wsd-assets-", dir=temporary_root))
    promoted: list[Path] = []
    try:
        for family, files in sources.items():
            records = [
                _copy(path, temporary / family / name, EXPECTED_HASHES[f"{family}/{name}"])
                for name, path in files.items()
            ]
            historical = json.loads((temporary / family / "manifest.json").read_text(encoding="utf-8"))
            artifact = {
                "schema_version": "wsd-method-asset/v1",
                "artifact_kind": "token_tuple_prototypes" if family == "prototypes" else "confidence_calibrator",
                "language": "es",
                "method_id": "spanishdict-beto-cal-v5",
                "provenance_status": "reconstructed",
                "recovered_at": _timestamp(recovered_at),
                "recovered_from": {
                    "repository": str(source_repository.expanduser().resolve()),
                    "current_method_commit": SOURCE_METHOD_COMMIT,
                    "asset_creation_commit": ASSET_CREATION_COMMIT,
                },
                "content_files": records,
                "historical_manifest": historical,
                "release_role": "required_runtime_asset" if family == "prototypes" else "evidence_only_not_validated_for_speech",
                "mutations": {"source_files": False, "assignments": False, "active_release": False},
            }
            (temporary / family / "artifact.json").write_bytes(json_bytes(artifact))
        for family, target in targets.items():
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(temporary / family, target)
            promoted.append(target)
    except Exception:
        for path in reversed(promoted):
            shutil.rmtree(path, ignore_errors=True)
        raise
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return targets
