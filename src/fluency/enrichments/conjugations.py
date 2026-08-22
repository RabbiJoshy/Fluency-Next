"""Build a bounded, language-neutral conjugation layer from a pinned source."""

from __future__ import annotations

import csv
from datetime import UTC, datetime
import json
from pathlib import Path
import shutil
from typing import Any

from fluency.core.artifacts import ArtifactMetadata, store_artifact_bytes
from fluency.core.hashing import file_content_id
from fluency.core.workspace import Workspace
from fluency.release.io import json_bytes


LAYER_VERSION = "conjugation-layer/v1"
SOURCE_MANIFEST_VERSION = "retained-source-artifact/v1"
PERSON_FIELDS = (
    ("1s", "form_1s"),
    ("2s", "form_2s"),
    ("3s", "form_3s"),
    ("1p", "form_1p"),
    ("2p", "form_2p"),
    ("3p", "form_3p"),
)


class ConjugationLayerError(ValueError):
    """Raised when conjugation source or menu evidence is malformed."""


def _timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _safe_snapshot_id(value: str) -> str:
    if not value or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for character in value):
        raise ConjugationLayerError("snapshot ID contains unsafe characters")
    return value


def _csv_rows(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
    except (OSError, UnicodeError) as error:
        raise ConjugationLayerError(f"conjugation CSV is unavailable: {path}") from error
    required = {
        "infinitive", "infinitive_english", "mood", "tense",
        "form_1s", "form_2s", "form_3s", "form_1p", "form_2p", "form_3p",
        "gerund", "pastparticiple",
    }
    if not rows or not required.issubset(rows[0]):
        raise ConjugationLayerError("conjugation CSV does not match the required source columns")
    return rows


def pin_jehle_snapshot(
    workspace: Workspace,
    *,
    source: Path,
    snapshot_id: str,
) -> Path:
    """Pin one recovered Jehle CSV; never treat its old derived outputs as input."""

    snapshot_id = _safe_snapshot_id(snapshot_id)
    source = source.expanduser().resolve()
    rows = _csv_rows(source)
    target = workspace.root / "raw/conjugations/es/fred-jehle" / snapshot_id
    if target.exists():
        raise ConjugationLayerError(f"conjugation source snapshot already exists: {target}")
    target.mkdir(parents=True)
    payload = target / "jehle_verb_database.csv"
    shutil.copy2(source, payload)
    digest = file_content_id(payload)
    infinitives = {row["infinitive"].strip().casefold() for row in rows if row["infinitive"].strip()}
    manifest = {
        "schema_version": SOURCE_MANIFEST_VERSION,
        "artifact_kind": "conjugation_source",
        "language": "es",
        "mode_scope": None,
        "provider": "fred-jehle",
        "snapshot_id": snapshot_id,
        "provenance_status": "reconstructed",
        "license": "unknown",
        "source_uris": [],
        "recovered_at": _timestamp(),
        "recovered_from": str(source),
        "content_files": [{
            "path": payload.name,
            "sha256": digest.removeprefix("sha256:"),
            "bytes": payload.stat().st_size,
            "record_count": len(rows),
        }],
        "coverage": {"infinitives": len(infinitives), "paradigm_rows": len(rows)},
        "notes": [
            "The local source did not preserve its download URI or license metadata.",
            "The exact bytes are pinned as reconstructed source evidence.",
        ],
    }
    (target / "artifact.json").write_bytes(json_bytes(manifest))
    return target


def _load_source(snapshot: Path) -> tuple[dict[str, Any], list[dict[str, str]], Path]:
    snapshot = snapshot.expanduser().resolve()
    try:
        manifest = json.loads((snapshot / "artifact.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ConjugationLayerError("conjugation source manifest is unavailable") from error
    if (
        manifest.get("schema_version") != SOURCE_MANIFEST_VERSION
        or manifest.get("artifact_kind") != "conjugation_source"
        or manifest.get("language") != "es"
        or manifest.get("provider") != "fred-jehle"
    ):
        raise ConjugationLayerError("conjugation source manifest is incompatible")
    payload = snapshot / "jehle_verb_database.csv"
    rows = _csv_rows(payload)
    content = (manifest.get("content_files") or [{}])[0]
    if content.get("sha256") != file_content_id(payload).removeprefix("sha256:"):
        raise ConjugationLayerError("conjugation source bytes do not match the manifest")
    return manifest, rows, payload


def _requested_headwords(menu: dict[str, Any]) -> set[str]:
    if menu.get("menu_version") != "sense-menu/v1" or menu.get("language") != "es":
        raise ConjugationLayerError("sense menu is not a Spanish sense-menu/v1 artifact")
    requested: set[str] = set()
    for card in menu.get("cards", []):
        for analysis in card.get("analyses", []):
            if analysis.get("part_of_speech") not in {"VERB", "AUX"}:
                continue
            headword = str(analysis.get("headword", "")).strip().casefold()
            if headword:
                requested.add(headword)
    return requested


def _source_records(rows: list[dict[str, str]]) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    seen_paradigms: set[tuple[str, str, str]] = set()
    for row in rows:
        headword = row["infinitive"].strip().casefold()
        mood = row["mood"].strip()
        tense = row["tense"].strip()
        if not headword or not mood or not tense:
            continue
        key = (headword, mood.casefold(), tense.casefold())
        if key in seen_paradigms:
            raise ConjugationLayerError(f"duplicate conjugation paradigm: {headword} / {mood} / {tense}")
        seen_paradigms.add(key)
        record = records.setdefault(headword, {
            "headword": headword,
            "translation": row["infinitive_english"].strip() or None,
            "nonfinite": {
                "gerund": row["gerund"].strip() or None,
                "past_participle": row["pastparticiple"].strip() or None,
            },
            "paradigms": [],
        })
        forms = [
            {"person": person, "form": row[field].strip()}
            for person, field in PERSON_FIELDS
            if row[field].strip()
        ]
        if forms:
            record["paradigms"].append({"mood": mood, "tense": tense, "forms": forms})
    return records


def build_conjugation_layer(
    workspace: Workspace,
    *,
    sense_menu: Path,
    source_snapshot: Path,
    locale: str = "es-ES",
) -> tuple[ArtifactMetadata, dict[str, Any]]:
    """Build and store one exact layer for headwords requested by a clean menu."""

    try:
        menu_bytes = sense_menu.read_bytes()
        menu = json.loads(menu_bytes)
    except (OSError, json.JSONDecodeError) as error:
        raise ConjugationLayerError("sense menu is unavailable") from error
    if not isinstance(menu, dict):
        raise ConjugationLayerError("sense menu must contain an object")
    requested = _requested_headwords(menu)
    source_manifest, rows, source_payload = _load_source(source_snapshot)
    available = _source_records(rows)
    records = [available[headword] for headword in sorted(requested) if headword in available]
    missing = sorted(requested - available.keys())
    layer = {
        "layer_version": LAYER_VERSION,
        "language": "es",
        "locale": locale,
        "layer_kind": "conjugations",
        "join_key": "headword",
        "source": {
            "provider": source_manifest["provider"],
            "snapshot_id": source_manifest["snapshot_id"],
            "content_id": file_content_id(source_payload),
            "provenance_status": source_manifest["provenance_status"],
        },
        "inputs": {
            "sense_menu_content_id": file_content_id(sense_menu),
            "sense_menu_snapshot_id": menu.get("snapshot_id"),
        },
        "coverage": {
            "requested_headwords": len(requested),
            "covered_headwords": len(records),
            "missing_headwords": missing,
        },
        "records": records,
    }
    metadata = store_artifact_bytes(
        workspace,
        json_bytes(layer),
        filename="conjugations.json",
        media_type="application/json",
        schema=LAYER_VERSION,
        created_by_stage="enrichment_conjugations",
        row_count=len(records),
    )
    return metadata, layer["coverage"]
