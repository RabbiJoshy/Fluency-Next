"""Read an explicitly migrated historical surface ranking without lemma identity."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from fluency.core.hashing import file_content_id
from fluency.languages.surfaces import normalizer_for_language


ADAPTER_ID = "recovered-surface-ranking/v1"
ARTIFACT_VERSION = "retained-source-artifact/v1"


class RecoveredRankingError(ValueError):
    """Raised when a migrated ranking is incomplete or has drifted."""


@dataclass(frozen=True, slots=True)
class RecoveredRanking:
    ranked_surfaces: tuple[tuple[str, float], ...]
    manifest: dict[str, Any]
    ranking_content_id: str


def load_recovered_surface_ranking(
    path: Path,
    *,
    expected_language: str,
    expected_snapshot_id: str,
) -> RecoveredRanking:
    try:
        manifest = json.loads((path / "artifact.json").read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise RecoveredRankingError(f"recovered ranking manifest does not exist: {path}") from error
    except json.JSONDecodeError as error:
        raise RecoveredRankingError("recovered ranking manifest is invalid JSON") from error
    if not isinstance(manifest, dict) or manifest.get("schema_version") != ARTIFACT_VERSION:
        raise RecoveredRankingError("unsupported recovered ranking manifest")
    if manifest.get("artifact_kind") != "surface_inventory_source":
        raise RecoveredRankingError("recovered artifact is not a surface ranking")
    if manifest.get("language") != expected_language:
        raise RecoveredRankingError("recovered ranking language does not match the run")
    if manifest.get("snapshot_id") != expected_snapshot_id:
        raise RecoveredRankingError("recovered ranking snapshot ID does not match the run")
    if manifest.get("provenance_status") != "reconstructed":
        raise RecoveredRankingError("recovered ranking must expose reconstructed provenance")

    files = manifest.get("content_files")
    if not isinstance(files, list):
        raise RecoveredRankingError("recovered ranking content file list is missing")
    records = {
        item.get("path"): item
        for item in files
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    }
    record = records.get("word_inventory.json")
    if not isinstance(record, dict):
        raise RecoveredRankingError("recovered ranking payload is missing")
    ranking_path = path / "word_inventory.json"
    ranking_content_id = file_content_id(ranking_path)
    if ranking_content_id != f"sha256:{record.get('sha256')}":
        raise RecoveredRankingError("recovered ranking content hash does not match")
    try:
        payload = json.loads(ranking_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise RecoveredRankingError("recovered ranking payload is invalid JSON") from error
    if not isinstance(payload, list):
        raise RecoveredRankingError("recovered ranking payload must be an array")

    normalize = normalizer_for_language(expected_language)
    seen: set[str] = set()
    ranked: list[tuple[str, float]] = []
    for row in payload:
        if not isinstance(row, dict):
            raise RecoveredRankingError("recovered ranking rows must be objects")
        raw_surface = row.get("word")
        count = row.get("corpus_count")
        if not isinstance(raw_surface, str) or not raw_surface.strip():
            raise RecoveredRankingError("recovered ranking row lacks a surface")
        if not isinstance(count, (int, float)) or isinstance(count, bool) or count <= 0:
            raise RecoveredRankingError("recovered ranking row has an invalid corpus count")
        surface = normalize(raw_surface)
        if surface in seen:
            raise RecoveredRankingError(f"duplicate recovered surface: {surface}")
        seen.add(surface)
        ranked.append((surface, float(count)))
    if len(ranked) != manifest.get("coverage", {}).get("surface_records"):
        raise RecoveredRankingError("recovered ranking coverage does not match its manifest")
    return RecoveredRanking(tuple(ranked), manifest, ranking_content_id)
