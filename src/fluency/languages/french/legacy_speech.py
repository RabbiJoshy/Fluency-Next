"""Import the frozen legacy French Speech deck into surface-card releases."""

from __future__ import annotations

from collections import OrderedDict
from datetime import UTC, datetime
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

from fluency.core.artifacts import store_artifact_bytes
from fluency.core.canonical_json import canonical_json, canonical_json_bytes
from fluency.core.hashing import canonical_content_id, content_id
from fluency.core.manifests import (
    StageManifest,
    build_stage_cache_key,
    create_run_manifest,
)
from fluency.core.workspace import Workspace
from fluency.languages.french.surfaces import create_french_card
from fluency.release.catalog import write_catalog
from fluency.release.composition import compose_release
from fluency.release.io import json_bytes
from fluency.release.study_structure import build_study_structure
from fluency.release.validation import SPEECH_DECK_VERSION
from fluency.sources.legacy.split_speech import LegacySplitSpeechSource, load_legacy_split_speech


LEGACY_IMPORT_VERSION = "legacy-split-speech-import/v1"
DEFAULT_RELEASE_ID = "fr-speech-legacy-0001"
DEFAULT_PROGRESS_NAMESPACE = "fr-speech-surface-v1"
_MEANING_FIELDS = ("pos", "translation", "detail", "context", "source")


def _trimmed(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _stable_local_id(prefix: str, payload: object) -> str:
    digest = hashlib.sha256(canonical_json_bytes(payload)).digest()[:16].hex()
    return f"{prefix}_{digest}"


def _source_created_at(index_path: Path) -> datetime:
    metadata_path = index_path.with_name(f"{index_path.name}.meta.json")
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        generated_at = metadata.get("generated_at")
        if not isinstance(generated_at, (int, float)) or not math.isfinite(generated_at):
            raise ValueError
        return datetime.fromtimestamp(generated_at, UTC)
    except (FileNotFoundError, json.JSONDecodeError, ValueError, OSError):
        return datetime.fromtimestamp(index_path.stat().st_mtime, UTC)


def _meaning_key(meaning: dict[str, Any]) -> tuple[str, ...]:
    return tuple(_trimmed(meaning.get(field)) for field in _MEANING_FIELDS)


def _meaning_record(surface_key: str, key: tuple[str, ...]) -> dict[str, Any]:
    pos, translation, detail, context, source = key
    if not pos or not translation:
        raise ValueError(f"legacy meaning for {surface_key} is missing POS or translation")
    sense_id = _stable_local_id("sense_fr_legacy", [LEGACY_IMPORT_VERSION, surface_key, key])
    record: dict[str, Any] = {
        "sense_id": sense_id,
        "part_of_speech": pos,
        "translation": translation,
        "assignment_status": "legacy_compiled",
        "legacy_sources": [],
    }
    if detail:
        record["detail"] = detail
    if context:
        record["context"] = context
    if source:
        record["source"] = source
    return record


def build_legacy_french_deck(
    source: LegacySplitSpeechSource,
    *,
    release_id: str = DEFAULT_RELEASE_ID,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    """Merge lemma-split legacy rows into one deterministic card per surface."""

    groups: OrderedDict[str, dict[str, Any]] = OrderedDict()
    raw_meaning_count = 0
    teachable_meaning_count = 0
    raw_example_count = 0
    teachable_row_count = 0
    rejected: list[dict[str, Any]] = []
    for source_position, source_card in enumerate(source.cards, start=1):
        source_meanings = source_card["meanings"]
        raw_meaning_count += len(source_meanings)
        teachable_indexes = [
            index for index, meaning in enumerate(source_meanings)
            if isinstance(meaning, dict) and _trimmed(meaning.get("translation"))
        ]
        if not teachable_indexes:
            rejected.append(
                {
                    "legacy_card_id": source_card["id"],
                    "surface": source_card["word"],
                    "source_position": source_position,
                    "reason": "no_teachable_translation",
                    "meanings": source_meanings,
                }
            )
            continue
        teachable_row_count += 1
        teachable_meaning_count += len(teachable_indexes)
        identity = create_french_card(source_card["word"])
        group = groups.setdefault(
            identity.surface_key,
            {
                "identity": identity,
                "aliases": [],
                "meanings": OrderedDict(),
                "examples": OrderedDict(),
                "primary_count": max(0, int(source_card.get("corpus_count") or 0)),
                "aggregate_count": 0,
            },
        )
        alias = {
            "legacy_card_id": source_card["id"],
            "legacy_lemma": _trimmed(source_card.get("lemma")) or identity.surface_key,
            "source_position": source_position,
            "corpus_count": max(0, int(source_card.get("corpus_count") or 0)),
        }
        group["aliases"].append(alias)
        group["aggregate_count"] += alias["corpus_count"]
        example_buckets = source.examples_by_legacy_id.get(source_card["id"], {}).get("m", [])

        for meaning_index in teachable_indexes:
            source_meaning = source_meanings[meaning_index]
            if not isinstance(source_meaning, dict):
                raise ValueError(f"legacy meaning for {source_card['id']} is malformed")
            key = _meaning_key(source_meaning)
            meaning = group["meanings"].setdefault(key, _meaning_record(identity.surface_key, key))
            meaning_source: dict[str, Any] = {
                "legacy_card_id": source_card["id"],
                "legacy_lemma": alias["legacy_lemma"],
                "meaning_index": meaning_index,
            }
            for field in ("frequency", "assignment_method"):
                value = source_meaning.get(field)
                if value is not None:
                    meaning_source[field] = value
            if meaning_source not in meaning["legacy_sources"]:
                meaning["legacy_sources"].append(meaning_source)

            bucket = example_buckets[meaning_index] if example_buckets else []
            for example_index, source_example in enumerate(bucket):
                target = _trimmed(source_example.get("target"))
                english = _trimmed(source_example.get("english"))
                if not target or not english:
                    raise ValueError(f"legacy example for {source_card['id']} is missing text")
                raw_example_count += 1
                example_key = (meaning["sense_id"], target, english)
                example = group["examples"].get(example_key)
                if example is None:
                    example = {
                        "example_id": _stable_local_id(
                            "example_fr_legacy",
                            [LEGACY_IMPORT_VERSION, identity.surface_key, *example_key],
                        ),
                        "sense_id": meaning["sense_id"],
                        "target": target,
                        "english": english,
                        "provenance": "legacy_compiled",
                        "assignment_method": source_example.get("assignment_method", "not_recorded"),
                        "legacy_sources": [],
                    }
                    if source_example.get("source") is not None:
                        example["source"] = source_example["source"]
                    if source_example.get("easiness") is not None:
                        example["easiness"] = source_example["easiness"]
                    group["examples"][example_key] = example
                example_source: dict[str, Any] = {
                    "legacy_card_id": source_card["id"],
                    "meaning_index": meaning_index,
                    "example_index": example_index,
                    "assignment_method": source_example.get("assignment_method", "not_recorded"),
                }
                for field in ("source", "easiness"):
                    if source_example.get(field) is not None:
                        example_source[field] = source_example[field]
                if example_source not in example["legacy_sources"]:
                    example["legacy_sources"].append(example_source)

    cards: list[dict[str, Any]] = []
    for rank, group in enumerate(groups.values(), start=1):
        identity = group["identity"]
        cards.append(
            {
                "card_id": identity.card_id,
                "surface_key": identity.surface_key,
                "display_form": identity.display_form,
                "rank": rank,
                "frequency": {
                    "basis": "legacy_first_position",
                    "primary_count": group["primary_count"],
                    "aggregate_count": group["aggregate_count"],
                },
                "legacy_aliases": group["aliases"],
                "meanings": list(group["meanings"].values()),
                "examples": list(group["examples"].values()),
            }
        )

    study_structure = build_study_structure(
        cards,
        frequency_of=lambda card: card["frequency"]["primary_count"],
    )
    deck = {
        "deck_version": SPEECH_DECK_VERSION,
        "release_id": release_id,
        "language": "fr",
        "mode": "speech",
        "study_structure": study_structure,
        "cards": cards,
    }
    unique_meanings = sum(len(card["meanings"]) for card in cards)
    unique_examples = sum(len(card["examples"]) for card in cards)
    summary = {
        "summary_version": "legacy-speech-import-summary/v1",
        "release_id": release_id,
        "legacy_rows": len(source.cards),
        "teachable_legacy_rows": teachable_row_count,
        "rejected_legacy_rows": len(rejected),
        "surface_cards": len(cards),
        "merged_lemma_rows": teachable_row_count - len(cards),
        "raw_meanings": raw_meaning_count,
        "teachable_meanings": teachable_meaning_count,
        "surface_meanings": unique_meanings,
        "rejected_meanings": sum(len(item["meanings"]) for item in rejected),
        "deduplicated_meanings": teachable_meaning_count - unique_meanings,
        "raw_examples": raw_example_count,
        "surface_examples": unique_examples,
        "deduplicated_examples": raw_example_count - unique_examples,
        "cards_without_examples": sum(not card["examples"] for card in cards),
        "levels": len(study_structure["levels"]),
        "sets": sum(len(level["sets"]) for level in study_structure["levels"]),
        "ranking_policy": "first legacy position; no frequency rerank",
        "wsd_policy": "preserve frozen legacy example-to-sense attachments only",
    }
    return deck, summary, rejected


def _complete_stage(
    *,
    name: str,
    version: str,
    implementation_hash: str,
    config_hash: str,
    inputs: dict[str, str],
    outputs: dict[str, str],
    timestamp: str,
) -> StageManifest:
    cache_key = build_stage_cache_key(
        stage_name=name,
        stage_version=version,
        implementation_hash=implementation_hash,
        config_hash=config_hash,
        inputs=inputs,
        model_revisions={},
        random_seed=0,
    )
    return StageManifest(
        stage_name=name,
        stage_version=version,
        cache_key=cache_key,
        implementation_hash=implementation_hash,
        config_hash=config_hash,
        status="running",
        started_at=timestamp,
        inputs=inputs,
        model_revisions={},
        random_seed=0,
        outputs={},
    ).complete(outputs, at=datetime.fromisoformat(timestamp.replace("Z", "+00:00")))


def _write_run_directory(
    workspace: Workspace,
    *,
    run_record: dict[str, Any],
    stages: dict[str, dict[str, Any]],
    summary: dict[str, Any],
    rejections: list[dict[str, Any]],
) -> Path:
    run_id = str(run_record["run_id"])
    target = workspace.root / "runs" / "fr" / "speech" / run_id
    files = {
        "manifest.json": json_bytes(run_record),
        "diagnostics/summary.json": json_bytes(summary),
        "diagnostics/rejections.jsonl": (
            "".join(f"{canonical_json(record)}\n" for record in rejections).encode("utf-8")
        ),
        **{f"stages/{name}.json": json_bytes(record) for name, record in stages.items()},
    }
    if target.exists():
        if any(not (target / name).is_file() or (target / name).read_bytes() != data for name, data in files.items()):
            raise ValueError(f"immutable run already exists with different content: {target}")
        return target
    temporary_root = workspace.root / ".fluency" / "temporary"
    temporary = Path(tempfile.mkdtemp(prefix="legacy-run-", dir=temporary_root))
    try:
        for name, data in files.items():
            path = temporary / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return target


def build_legacy_french_release(
    workspace: Workspace,
    *,
    index_path: Path,
    examples_path: Path,
    release_id: str = DEFAULT_RELEASE_ID,
) -> tuple[Path, Path, dict[str, Any]]:
    """Build and catalogue a legacy candidate without activating it."""

    source = load_legacy_split_speech(index_path, examples_path)
    index_artifact = store_artifact_bytes(
        workspace,
        source.index_bytes,
        filename="vocabulary.index.json",
        media_type="application/json",
        schema="legacy-speech-index/v1",
        created_by_stage="legacy_import",
        row_count=len(source.cards),
    )
    examples_artifact = store_artifact_bytes(
        workspace,
        source.examples_bytes,
        filename="vocabulary.examples.json",
        media_type="application/json",
        schema="legacy-speech-examples/v1",
        created_by_stage="legacy_import",
        row_count=len(source.examples_by_legacy_id),
    )
    deck, summary, rejections = build_legacy_french_deck(source, release_id=release_id)
    deck_artifact = store_artifact_bytes(
        workspace,
        json_bytes(deck),
        filename="deck.json",
        media_type="application/json",
        schema=SPEECH_DECK_VERSION,
        created_by_stage="surface_merge",
        row_count=len(deck["cards"]),
    )

    source_time = _source_created_at(source.index_path)
    timestamp = source_time.isoformat().replace("+00:00", "Z")
    config = {
        "import_version": LEGACY_IMPORT_VERSION,
        "release_id": release_id,
        "language": "fr",
        "locale": "fr-FR",
        "mode": "speech",
        "identity": "surface-card/v1",
        "ranking_policy": summary["ranking_policy"],
        "set_size": 20,
    }
    config_hash = canonical_content_id(config)
    inputs = {
        "legacy_index": index_artifact.artifact_id,
        "legacy_examples": examples_artifact.artifact_id,
    }
    run_suffix = canonical_content_id(inputs).removeprefix("sha256:")[:8]
    run = create_run_manifest(
        language="fr",
        mode="speech",
        profile="legacy_import",
        config_hash=config_hash,
        inputs=inputs,
        started_at=source_time,
        suffix=run_suffix,
    )
    implementation_hash = content_id(Path(__file__).read_bytes())
    stages = {
        "legacy_import": _complete_stage(
            name="legacy_import",
            version=LEGACY_IMPORT_VERSION,
            implementation_hash=implementation_hash,
            config_hash=config_hash,
            inputs=inputs,
            outputs=inputs,
            timestamp=timestamp,
        ),
        "surface_merge": _complete_stage(
            name="surface_merge",
            version="surface-merge/v1",
            implementation_hash=implementation_hash,
            config_hash=config_hash,
            inputs=inputs,
            outputs={"speech_deck": deck_artifact.artifact_id},
            timestamp=timestamp,
        ),
        "release_build": _complete_stage(
            name="release_build",
            version="legacy-release-build/v1",
            implementation_hash=implementation_hash,
            config_hash=config_hash,
            inputs={"speech_deck": deck_artifact.artifact_id},
            outputs={"speech_deck": deck_artifact.artifact_id},
            timestamp=timestamp,
        ),
    }
    run = run.with_status("complete", at=source_time)
    run_record = run.to_dict()
    run_record["stages"] = [f"stages/{name}.json" for name in stages]
    run_directory = _write_run_directory(
        workspace,
        run_record=run_record,
        stages={name: stage.to_dict() for name, stage in stages.items()},
        summary=summary,
        rejections=rejections,
    )

    def selection(artifact_id: str, record_count: int, requires: dict[str, str]) -> dict[str, Any]:
        return {
            "selection_version": "layer-selection/v1",
            "source_type": "run",
            "source_id": run.run_id,
            "artifact_id": artifact_id,
            "record_count": record_count,
            "requires": requires,
        }

    layers = {
        "inventory": selection(index_artifact.artifact_id, len(source.cards), {}),
        "sense_menu": selection(
            index_artifact.artifact_id,
            summary["surface_meanings"],
            {"inventory": index_artifact.artifact_id},
        ),
        "sentences": selection(
            examples_artifact.artifact_id,
            summary["surface_examples"],
            {"inventory": index_artifact.artifact_id},
        ),
        "wsd_assignments": selection(
            examples_artifact.artifact_id,
            summary["surface_examples"],
            {
                "inventory": index_artifact.artifact_id,
                "sense_menu": index_artifact.artifact_id,
                "sentences": examples_artifact.artifact_id,
            },
        ),
        "example_selection": selection(
            examples_artifact.artifact_id,
            summary["surface_examples"],
            {
                "inventory": index_artifact.artifact_id,
                "sense_menu": index_artifact.artifact_id,
                "sentences": examples_artifact.artifact_id,
                "wsd_assignments": examples_artifact.artifact_id,
            },
        ),
    }
    composition = {
        "composition_version": "release-composition/v1",
        "release_id": release_id,
        "label": "French Speech · legacy surface import 0001",
        "language": "fr",
        "locale": "fr-FR",
        "mode": "speech",
        "created_at": timestamp,
        "publication_status": "legacy_snapshot",
        "progress_namespace": DEFAULT_PROGRESS_NAMESPACE,
        "conflict_policy": "error",
        "fallback_policy": "none",
        "layers": layers,
        "omitted_layers": [{"layer": "manual_overrides", "reason": "not_applied"}],
    }
    release_directory = compose_release(workspace, composition, deck)
    write_catalog(workspace, "fr", "speech")
    return release_directory, run_directory, summary
