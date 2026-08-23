"""Render clean Lyrics consolidation records into the existing split app contract."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

from fluency.core.hashing import canonical_content_id, file_content_id
from fluency.core.workspace import Workspace
from fluency.lyrics.lineage import build_lineage_event
from fluency.release.io import atomic_write, json_bytes


STAGE_VERSION = "lyrics-app-assembly-stage/v1"
METHOD_ID = "lyrics-split-app-assembler/v1"


class LyricsAppAssemblyError(ValueError):
    pass


def _object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LyricsAppAssemblyError(f"required JSON is unavailable or invalid: {path}") from error
    if not isinstance(value, dict):
        raise LyricsAppAssemblyError(f"required JSON must contain an object: {path}")
    return value


def _array(path: Path) -> list[Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LyricsAppAssemblyError(f"required JSON is unavailable or invalid: {path}") from error
    if not isinstance(value, list):
        raise LyricsAppAssemblyError(f"required JSON must contain an array: {path}")
    return value


def _jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        values = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    except (OSError, json.JSONDecodeError) as error:
        raise LyricsAppAssemblyError(f"required JSONL is unavailable or invalid: {path}") from error
    if not all(isinstance(value, dict) for value in values):
        raise LyricsAppAssemblyError(f"JSONL contains a non-object: {path}")
    return values


def _app_id(card_id: str) -> str:
    parts = card_id.split("_", 2)
    if len(parts) != 3 or parts[0] != "card" or len(parts[2]) < 8:
        raise LyricsAppAssemblyError(f"invalid surface card identity: {card_id}")
    return parts[2][:8]


def _validate_split(
    index: list[dict[str, Any]], examples: dict[str, Any], master: dict[str, Any]
) -> None:
    ids = [card.get("id") for card in index]
    if not ids or any(not isinstance(card_id, str) or not card_id for card_id in ids):
        raise LyricsAppAssemblyError("assembled index contains an invalid card ID")
    if len(ids) != len(set(ids)):
        raise LyricsAppAssemblyError("assembled index contains an app-ID collision")
    if set(ids) != set(examples) or set(ids) != set(master):
        raise LyricsAppAssemblyError("assembled index, examples, and master ID sets disagree")
    for card in index:
        entry = master[card["id"]]
        senses = entry.get("senses")
        buckets = examples[card["id"]].get("m")
        if not isinstance(senses, list) or not senses or len(senses) != len(card.get("sense_frequencies", [])):
            raise LyricsAppAssemblyError("master senses and index frequencies disagree")
        if not isinstance(buckets, list) or len(buckets) != len(senses):
            raise LyricsAppAssemblyError("example buckets and master senses disagree")
        if any(not bucket for bucket in buckets):
            raise LyricsAppAssemblyError("an assembled assigned sense has no selected example")


def _comparison(
    *, clean_index: list[dict[str, Any]], clean_master: dict[str, Any],
    clean_examples: dict[str, Any], comparison_release: Path | None,
    artist_slug: str, language: str, source_record_id: str,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "status": "not_requested", "comparison_release": None,
        "clean_card_count": len(clean_index),
        "clean_selected_example_count": sum(
            len(bucket) for payload in clean_examples.values() for bucket in payload["m"]
        ),
    }
    if comparison_release is None:
        return report
    comparison_release = comparison_release.expanduser().resolve()
    parity_index = _array(comparison_release / f"Artists/{language}/{artist_slug}/index.json")
    parity_examples = _object(comparison_release / f"Artists/{language}/{artist_slug}/examples.json")
    parity_master = _object(comparison_release / f"Artists/{language}/vocabulary_master.json")
    parity_words = {
        str(parity_master.get(card.get("id"), {}).get("word", "")).casefold()
        for card in parity_index if isinstance(card, dict)
    }
    clean_words = {str(item.get("word", "")).casefold() for item in clean_master.values()}
    parity_song_examples = 0
    for payload in parity_examples.values():
        if not isinstance(payload, dict):
            continue
        for bucket_name in ("m", "s", "r"):
            for bucket in payload.get(bucket_name, []):
                if isinstance(bucket, list):
                    parity_song_examples += sum(
                        str(example.get("song", "")) == source_record_id
                        for example in bucket if isinstance(example, dict)
                    )
    report.update({
        "status": "compared", "comparison_release": comparison_release.as_posix(),
        "surface_words_already_in_parity": len(clean_words & parity_words),
        "surface_words_absent_from_parity": sorted(clean_words - parity_words),
        "parity_examples_for_song": parity_song_examples,
        "selected_example_delta": report["clean_selected_example_count"] - parity_song_examples,
    })
    return report


def assemble_lyrics_app_stage(
    repository_root: Path,
    workspace: Workspace,
    *,
    run_id: str,
    language: str,
    artist_slug: str,
    comparison_release: Path | None = None,
    consolidation_output_path: Path | None = None,
    wsd_output_path: Path | None = None,
    output_path: Path | None = None,
    publish_run_stage: bool = True,
    started_at: datetime | None = None,
) -> Path:
    """Build inactive split app files without composing or activating a release."""

    run = workspace.root / "runs" / language / "lyrics" / run_id
    run_manifest_path = run / "manifest.json"
    run_manifest = _object(run_manifest_path)
    if run_manifest.get("run_id") != run_id or run_manifest.get("language") != language:
        raise LyricsAppAssemblyError("Lyrics run identity does not match app assembly")
    consolidation = (
        run / run_manifest.get("stages", {}).get("consolidation", {}).get("path", "")
        if consolidation_output_path is None else consolidation_output_path.resolve()
    )
    wsd = (
        run / run_manifest.get("stages", {}).get("wsd_results", {}).get("path", "")
        if wsd_output_path is None else wsd_output_path.resolve()
    )
    if not consolidation.is_dir() or not wsd.is_dir():
        raise LyricsAppAssemblyError("app assembly requires exact consolidation and WSD stages")
    output = run / "stages/07_app_assembly/output" if output_path is None else output_path.resolve()
    runs_root = (workspace.root / "runs").resolve()
    for branch_path, label in (
        (consolidation, "consolidation"), (wsd, "WSD"), (output, "assembly")
    ):
        try:
            branch_path.relative_to(runs_root)
        except ValueError as error:
            raise LyricsAppAssemblyError(
                f"external {label} path must be inside workspace/runs"
            ) from error
    if output_path is not None and publish_run_stage:
        raise LyricsAppAssemblyError(
            "an external assembly branch cannot replace the source run's canonical stage reference"
        )
    if output.exists():
        raise LyricsAppAssemblyError("app assembly output already exists; create a new run")
    consolidation_manifest = _object(consolidation / "manifest.json")
    wsd_manifest = _object(wsd / "manifest.json")
    cards_path = consolidation / "cards.jsonl"
    examples_path = consolidation / "examples.jsonl"
    results_path = wsd / "results.jsonl"
    inputs = {
        "cards": file_content_id(cards_path), "examples": file_content_id(examples_path),
        "wsd_results": file_content_id(results_path),
    }
    if consolidation_manifest.get("outputs", {}).get("cards.jsonl") != inputs["cards"] or consolidation_manifest.get("outputs", {}).get("examples.jsonl") != inputs["examples"]:
        raise LyricsAppAssemblyError("consolidation inputs changed after completion")
    if wsd_manifest.get("outputs", {}).get("results.jsonl") != inputs["wsd_results"]:
        raise LyricsAppAssemblyError("WSD results changed after completion")

    cards = _jsonl(cards_path)
    consolidated_examples = _jsonl(examples_path)
    result_by_id = {item["result_id"]: item for item in _jsonl(results_path)}
    examples_by_group: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for example in consolidated_examples:
        if example.get("selected_for_study"):
            examples_by_group[(example["card_id"], example["sense_assignment_id"])].append(example)

    index: list[dict[str, Any]] = []
    split_examples: dict[str, dict[str, Any]] = {}
    master: dict[str, dict[str, Any]] = {}
    used_app_ids: set[str] = set()
    lineage: list[dict[str, Any]] = []
    for card in sorted(cards, key=lambda item: item["rank"]):
        app_id = _app_id(card["card_id"])
        if app_id in used_app_ids:
            raise LyricsAppAssemblyError(f"app compatibility ID collision: {app_id}")
        used_app_ids.add(app_id)
        total_occurrences = max(1, len(card["occurrence_ids"]))
        senses: list[dict[str, Any]] = []
        frequencies: list[float] = []
        methods: list[str] = []
        confidences: list[float | None] = []
        bands: list[str | None] = []
        buckets: list[list[dict[str, Any]]] = []
        for sense_group in card["sense_groups"]:
            group_examples = sorted(
                examples_by_group[(card["card_id"], sense_group["sense_assignment_id"])],
                key=lambda item: (item["line"]["source_position"], item["occurrence"]["span"][0]),
            )
            if not group_examples:
                raise LyricsAppAssemblyError("a consolidated sense has no selected app example")
            senses.append({
                "pos": sense_group["part_of_speech"],
                "translation": sense_group["translation"] or "",
                "context": sense_group["definition"] or "",
                "source": sense_group["provider"].get("source_adapter", "dictionary"),
                "sense_id": sense_group["source_sense_id"],
                "headword": sense_group["headword"],
                "source_reference": sense_group["source_reference"],
            })
            frequencies.append(len(sense_group["occurrence_ids"]) / total_occurrences)
            methods.append(group_examples[0]["wsd"]["method_id"])
            group_results = [result_by_id[item["wsd"]["result_id"]] for item in group_examples]
            scores = [item["confidence"] for item in group_results if item.get("confidence") is not None]
            confidences.append(sum(scores) / len(scores) if scores else None)
            legacy_bands = [item.get("evidence", {}).get("calibration", {}).get("legacy_band") for item in group_results]
            bands.append(next((item for item in legacy_bands if item), None))
            app_bucket: list[dict[str, Any]] = []
            for example, result in zip(group_examples, group_results, strict=True):
                performers = (example["line"].get("section") or {}).get("performers", [])
                translation = example.get("translation")
                app_bucket.append({
                    "song": example["source"].get("source_record_id", example["song"]["song_id"]),
                    "song_name": example["song"]["title"],
                    "spanish": example["line"]["text"],
                    "english": translation["text"] if translation else "",
                    "translation_source": (translation or {}).get("source", {}).get("provider"),
                    "assignment_method": example["wsd"]["method_id"],
                    "confidence": example["wsd"]["confidence"],
                    "band": result.get("evidence", {}).get("calibration", {}).get("legacy_band"),
                    "vocalists": performers,
                    "sung_by_primary_artist": example["artist"]["name"] in performers,
                    "spotify_available": False,
                    "is_variant": example["analysis_unit"]["operation"] != "preserve",
                    "example_id": example["example_id"],
                    "source_record_id": example["occurrence"]["occurrence_id"],
                    "run_id": run_id,
                    "occurrence_id": example["occurrence"]["occurrence_id"],
                    "analysis_unit_id": example["analysis_unit"]["analysis_unit_id"],
                    "route_id": example["route"]["route_id"],
                    "lexical_candidate_id": example["menu"]["lexical_candidate_id"],
                    "menu_content_id": example["menu"]["menu_content_id"],
                    "menu_analysis_id": example["menu"]["menu_analysis_id"],
                    "sense_id": example["menu"]["sense_id"],
                    "sense_assignment_id": example["sense_assignment_id"],
                    "wsd_request_id": example["wsd"]["request_id"],
                    "wsd_result_id": example["wsd"]["result_id"],
                    "decision_path": example["wsd"]["decision_path"],
                    "wsd_evidence": result.get("evidence", {}),
                    "source_snapshot_content_id": example["source"].get("snapshot_content_id"),
                    "alignment_id": translation.get("alignment_id") if translation else None,
                    "alignment_snapshot_content_id": (translation or {}).get("source", {}).get("snapshot_content_id"),
                })
            buckets.append(app_bucket)
        index.append({
            "id": app_id, "rank": card["rank"], "corpus_count": len(card["occurrence_ids"]),
            "lemma_example_count": len(card["occurrence_ids"]),
            "most_frequent_lemma_instance": True, "sense_frequencies": frequencies,
            "sense_methods": methods, "sense_confidence": confidences, "sense_band": bands,
            "surface_card_id": card["card_id"], "extra_category": "core",
        })
        split_examples[app_id] = {"m": buckets}
        master[app_id] = {
            "word": card["display_form"], "lemma": None, "senses": senses,
            "is_english": False, "is_noise": False, "is_interjection": False,
            "is_propernoun": False, "is_transparent_cognate": False,
            "display_form": card["display_form"], "extra_category": "core",
            "surface_card_id": card["card_id"],
        }
        lineage.append(build_lineage_event(
            subject={"kind": "surface_card", "id": card["card_id"]},
            phase="assemble", operation="materialize", run_id=run_id,
            method_id=METHOD_ID,
            input_refs=[{"kind": "consolidated_card", "id": card["card_id"]}],
            output_refs=[{"kind": "app_card", "id": app_id}],
            evidence_kind="direct", decision={"sense_count": len(senses)},
        ))

    _validate_split(index, split_examples, master)
    source_record_id = next(iter(consolidated_examples))["source"].get("source_record_id", "") if consolidated_examples else ""
    comparison = _comparison(
        clean_index=index, clean_master=master, clean_examples=split_examples,
        comparison_release=comparison_release, artist_slug=artist_slug,
        language=language, source_record_id=source_record_id,
    )
    started_at = datetime.now(UTC) if started_at is None else started_at.astimezone(UTC)
    temporary_root = workspace.root / ".fluency/temporary"
    temporary = Path(tempfile.mkdtemp(prefix="lyrics-app-assembly-", dir=temporary_root))
    try:
        (temporary / "index.json").write_bytes(json_bytes(index))
        (temporary / "examples.json").write_bytes(json_bytes(split_examples))
        (temporary / "vocabulary_master.json").write_bytes(json_bytes(master))
        (temporary / "lineage.jsonl").write_bytes(b"".join(json_bytes(item) for item in lineage))
        payload_bytes = sum((temporary / name).stat().st_size for name in ("index.json", "examples.json", "vocabulary_master.json"))
        report = {
            "report_version": "lyrics-app-assembly-report/v1", "run_id": run_id,
            "language": language, "artist_slug": artist_slug, "card_count": len(index),
            "example_count": sum(len(bucket) for payload in split_examples.values() for bucket in payload["m"]),
            "payload_bytes": payload_bytes, "comparison": comparison,
            "optional_assets": {"songs": "absent", "albums": "absent", "artwork": "absent", "spotify": "absent"},
        }
        (temporary / "report.json").write_bytes(json_bytes(report))
        output_names = ("index.json", "examples.json", "vocabulary_master.json", "lineage.jsonl", "report.json")
        outputs = {name: file_content_id(temporary / name) for name in output_names}
        manifest = {
            "manifest_version": STAGE_VERSION, "run_id": run_id, "stage": "app_assembly",
            "status": "complete", "started_at": started_at.isoformat().replace("+00:00", "Z"),
            "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "method_id": METHOD_ID,
            "implementation_content_id": canonical_content_id({
                "implementation": file_content_id(Path(__file__)),
                "app_contract": file_content_id(repository_root / "app/js/data-contracts.js"),
            }),
            "inputs": inputs, "outputs": outputs,
        }
        (temporary / "manifest.json").write_bytes(json_bytes(manifest))
        output.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    if publish_run_stage:
        stages = dict(run_manifest.get("stages", {}))
        stages["app_assembly"] = {
            "path": "stages/07_app_assembly/output",
            "manifest_content_id": file_content_id(output / "manifest.json"),
        }
        run_manifest["stages"] = stages
        atomic_write(run_manifest_path, run_manifest, temporary_root)
    return output
