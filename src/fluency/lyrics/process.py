"""Tokenize, normalize, and route one immutable Lyrics source run."""

from __future__ import annotations

from datetime import UTC, datetime
from collections import Counter
import json
import os
from pathlib import Path
import shutil
import tempfile
import unicodedata
from typing import Any

from fluency.core.artifacts import ArtifactMetadata, artifact_directory, store_artifact_bytes
from fluency.core.hashing import canonical_content_id, file_content_id
from fluency.core.workspace import Workspace
from fluency.lyrics.languages import load_live_lyrics_router, load_lyrics_adapter
from fluency.lyrics.lineage import build_lineage_event
from fluency.lyrics.routing import RoutingSnapshot
from fluency.release.io import atomic_write, json_bytes


STAGE_VERSION = "lyrics-processing-stage/v2"
TOKENIZER_ID = "unicode-lyrics-tokenizer/v1"


class LyricsProcessingError(ValueError):
    """Raised when a processing stage is incomplete, mutable, or mismatched."""


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LyricsProcessingError(f"required JSON is unavailable or invalid: {path}") from error


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    except (OSError, json.JSONDecodeError) as error:
        raise LyricsProcessingError(f"required JSONL is unavailable or invalid: {path}") from error


def _jsonl_bytes(records: list[dict[str, Any]]) -> bytes:
    return b"".join(json_bytes(record) for record in records)


def _is_letter(character: str) -> bool:
    return bool(character) and unicodedata.category(character).startswith("L")


def _scan_tokens(text: str) -> list[tuple[str, int, int]]:
    """Scan Unicode letter runs while retaining meaningful apostrophes."""

    apostrophes = {"'", "’"}
    output: list[tuple[str, int, int]] = []
    index = 0
    while index < len(text):
        leading_apostrophe = (
            text[index] in apostrophes
            and index + 1 < len(text)
            and _is_letter(text[index + 1])
            and (index == 0 or not _is_letter(text[index - 1]))
        )
        if not _is_letter(text[index]) and not leading_apostrophe:
            index += 1
            continue
        start = index
        index += 1
        while index < len(text):
            character = text[index]
            if _is_letter(character):
                index += 1
                continue
            if character in apostrophes and index > start:
                index += 1
                continue
            break
        output.append((text[start:index], start, index))
    return output


def _enclosed_ranges(text: str) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for opening, closing in (("(", ")"), ("[", "]")):
        start = None
        for index, character in enumerate(text):
            if character == opening and start is None:
                start = index
            elif character == closing and start is not None:
                ranges.append((start, index + 1))
                start = None
    return ranges


def _stable_id(prefix: str, value: object) -> str:
    return prefix + "_" + canonical_content_id(value).removeprefix("sha256:")[:32]


def _pin_json(workspace: Workspace, path: Path, *, filename: str, schema: str) -> ArtifactMetadata:
    return store_artifact_bytes(
        workspace,
        path.expanduser().resolve().read_bytes(),
        filename=filename,
        media_type="application/json",
        schema=schema,
        created_by_stage=STAGE_VERSION,
    )


def _pin_text(workspace: Workspace, path: Path, *, filename: str, schema: str) -> ArtifactMetadata:
    return store_artifact_bytes(
        workspace,
        path.expanduser().resolve().read_bytes(),
        filename=filename,
        media_type="text/plain",
        schema=schema,
        created_by_stage=STAGE_VERSION,
    )


def _payload_path(workspace: Workspace, metadata: ArtifactMetadata) -> Path:
    return artifact_directory(workspace, metadata.artifact_id) / metadata.filename


def _comparison_class(current: dict[str, Any], baseline: dict[str, Any]) -> str:
    if (current["bucket"], current.get("target")) == (baseline["bucket"], baseline.get("target")):
        return "match"
    if baseline["bucket"] == "exclude.low_frequency" and current["bucket"] == "sense_discovery":
        return "intended_policy_change"
    if baseline["bucket"] == "unresolved" and current["bucket"] != "unresolved":
        return "newly_resolved"
    if current["bucket"] == "unresolved" and baseline["bucket"] != "unresolved":
        return "regression_candidate"
    return "review_required"


def process_lyrics_run(
    workspace: Workspace,
    *,
    run_id: str,
    language: str,
    elision_mapping: Path,
    multi_word_elisions: Path,
    known_forms: Path,
    frequency_snapshot: Path,
    lexeme_register: Path,
    routing_snapshot: Path,
    routing_mode: str = "snapshot",
    english_frequency: Path | None = None,
    english_loanwords: Path | None = None,
    conjugation_reverse: Path | None = None,
    caps_stats: Path | None = None,
    routing_overrides: Path | None = None,
    started_at: datetime | None = None,
) -> Path:
    """Create occurrence, normalized-unit, route, and lineage artifacts once."""

    run_directory = workspace.root / "runs" / language / "lyrics" / run_id
    run_manifest_path = run_directory / "manifest.json"
    run_manifest = _read_json(run_manifest_path)
    if not isinstance(run_manifest, dict) or run_manifest.get("run_id") != run_id:
        raise LyricsProcessingError("lyrics run manifest does not match the requested run")
    if run_manifest.get("language") != language or run_manifest.get("mode") != "lyrics":
        raise LyricsProcessingError("lyrics run language or mode does not match")
    source_output = run_directory / "stages" / "01_source_ingest" / "output"
    source_manifest = _read_json(source_output / "manifest.json")
    source_song = _read_json(source_output / "song.json")
    lines = _read_jsonl(source_output / "lines.jsonl")
    output_directory = run_directory / "stages" / "02_process" / "output"
    if output_directory.exists():
        raise LyricsProcessingError("processing output already exists; create a new run instead of overwriting it")

    pinned: dict[str, ArtifactMetadata] = {
        "elision_mapping": _pin_json(workspace, elision_mapping, filename="elision-mapping.json", schema="spanish-elision-mapping/v1"),
        "multi_word_elisions": _pin_json(workspace, multi_word_elisions, filename="multi-word-elisions.json", schema="spanish-multi-word-elisions/v1"),
        "known_forms": _pin_json(workspace, known_forms, filename="spanish-known-forms.json", schema="spanish-known-forms/v1"),
        "frequency_snapshot": _pin_text(workspace, frequency_snapshot, filename="spanish-surface-frequency.txt", schema="spanish-surface-frequency/v1"),
        "lexeme_register": _pin_json(workspace, lexeme_register, filename="spanish-lexeme-register.json", schema="spanish-lexeme-register/v1"),
        "routing_snapshot": _pin_json(workspace, routing_snapshot, filename="word-routing.json", schema="legacy-word-routing/v2"),
    }
    if routing_mode not in {"snapshot", "live"}:
        raise LyricsProcessingError("routing mode must be 'snapshot' or 'live'")
    if routing_mode == "live":
        live_paths = {
            "english_frequency": english_frequency,
            "english_loanwords": english_loanwords,
            "conjugation_reverse": conjugation_reverse,
            "caps_stats": caps_stats,
        }
        missing = sorted(name for name, path in live_paths.items() if path is None)
        if missing:
            raise LyricsProcessingError("live routing is missing required inputs: " + ", ".join(missing))
        pinned.update(
            {
                "english_frequency": _pin_text(workspace, english_frequency, filename="english-surface-frequency.txt", schema="english-surface-frequency/v1"),
                "english_loanwords": _pin_json(workspace, english_loanwords, filename="spanish-english-loanwords.json", schema="spanish-english-loanwords/v1"),
                "conjugation_reverse": _pin_json(workspace, conjugation_reverse, filename="spanish-conjugation-reverse.json", schema="spanish-conjugation-reverse/v1"),
                "caps_stats": _pin_json(workspace, caps_stats, filename="artist-capitalization-stats.json", schema="artist-capitalization-stats/v1"),
            }
        )
        if routing_overrides is not None:
            pinned["routing_overrides"] = _pin_json(
                workspace,
                routing_overrides,
                filename="lyrics-routing-overrides.json",
                schema="lyrics-routing-overrides/v1",
            )
    inputs = {
        **{name: metadata.artifact_id for name, metadata in pinned.items()},
        "source_lines": source_manifest["outputs"]["lines.jsonl"],
    }
    adapter = load_lyrics_adapter(
        language,
        elision_mapping=_payload_path(workspace, pinned["elision_mapping"]),
        multi_word_elisions=_payload_path(workspace, pinned["multi_word_elisions"]),
        known_forms=_payload_path(workspace, pinned["known_forms"]),
        frequency_snapshot=_payload_path(workspace, pinned["frequency_snapshot"]),
        lexeme_register=_payload_path(workspace, pinned["lexeme_register"]),
    )
    comparison_router = RoutingSnapshot(_payload_path(workspace, pinned["routing_snapshot"]))
    if routing_mode == "live":
        router = load_live_lyrics_router(
            language,
            known_forms=_payload_path(workspace, pinned["known_forms"]),
            spanish_frequency=_payload_path(workspace, pinned["frequency_snapshot"]),
            english_frequency=_payload_path(workspace, pinned["english_frequency"]),
            english_loanwords=_payload_path(workspace, pinned["english_loanwords"]),
            conjugation_reverse=_payload_path(workspace, pinned["conjugation_reverse"]),
            caps_stats=_payload_path(workspace, pinned["caps_stats"]),
            elision_mapping=_payload_path(workspace, pinned["elision_mapping"]),
            routing_overrides=(
                _payload_path(workspace, pinned["routing_overrides"])
                if "routing_overrides" in pinned
                else None
            ),
            artist_id=source_song.get("artist", {}).get("id"),
            song_id=source_song.get("song_id"),
        )
    else:
        router = comparison_router
    started_at = datetime.now(UTC) if started_at is None else started_at.astimezone(UTC)

    occurrences: list[dict[str, Any]] = []
    units: list[dict[str, Any]] = []
    routes: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    normalization_reasons: dict[str, int] = {}
    route_counts: dict[str, int] = {}
    comparison_rows: dict[tuple[str, str, str | None, str, str | None], dict[str, Any]] = {}
    for line in lines:
        scanned = _scan_tokens(line["text"])
        enclosed = _enclosed_ranges(line["text"])
        surfaces = [surface for surface, _start, _end in scanned]
        for ordinal, (surface, start, end) in enumerate(scanned):
            occurrence_id = _stable_id(
                "occurrence",
                {
                    "version": "lyrics-occurrence/v1",
                    "line_id": line["line_id"],
                    "span": [start, end],
                    "surface": surface,
                },
            )
            context = "adlib" if any(left <= start and end <= right for left, right in enclosed) else "lyric"
            occurrence = {
                "record_version": "lyrics-occurrence/v1",
                "occurrence_id": occurrence_id,
                "line_id": line["line_id"],
                "language": language,
                "ordinal": ordinal,
                "span": [start, end],
                "source_span": [line["source_span"][0] + start, line["source_span"][0] + end],
                "surface": surface,
                "context": context,
            }
            occurrences.append(occurrence)
            events.append(
                build_lineage_event(
                    subject={"kind": "occurrence", "id": occurrence_id},
                    phase="extract",
                    operation="split",
                    run_id=run_id,
                    method_id=TOKENIZER_ID,
                    input_refs=[{"kind": "lyrics_line", "id": line["line_id"]}],
                    output_refs=[{"kind": "occurrence", "id": occurrence_id}],
                    evidence_kind="direct",
                    decision={"span": [start, end], "context": context},
                )
            )
            previous = surfaces[ordinal - 1] if ordinal else None
            following = surfaces[ordinal + 1] if ordinal + 1 < len(surfaces) else None
            normalized = adapter.normalize(surface, previous=previous, following=following)
            for slot, normalized_unit in enumerate(normalized):
                unit_id = _stable_id(
                    "unit",
                    {
                        "version": "lyrics-analysis-unit/v1",
                        "occurrence_id": occurrence_id,
                        "slot": slot,
                        "form": normalized_unit.form,
                    },
                )
                unit = {
                    "record_version": "lyrics-analysis-unit/v1",
                    "analysis_unit_id": unit_id,
                    "occurrence_id": occurrence_id,
                    "language": language,
                    "slot": slot,
                    "source_surface": surface,
                    "normalized_form": normalized_unit.form,
                    "operation": normalized_unit.operation,
                    "reason_code": normalized_unit.reason_code,
                }
                units.append(unit)
                normalization_reasons[normalized_unit.reason_code] = normalization_reasons.get(normalized_unit.reason_code, 0) + 1
                events.append(
                    build_lineage_event(
                        subject={"kind": "analysis_unit", "id": unit_id},
                        phase="normalize",
                        operation=normalized_unit.operation,
                        run_id=run_id,
                        method_id=adapter.method_id,
                        input_refs=[{"kind": "occurrence", "id": occurrence_id}],
                        output_refs=[{"kind": "analysis_unit", "id": unit_id}],
                        evidence_kind="direct",
                        decision={"before": surface, "after": normalized_unit.form, "slot": slot},
                        reason_codes=[normalized_unit.reason_code],
                        language_adapter=adapter.method_id,
                    )
                )
                route = router.route(normalized_unit.form)
                baseline_route = comparison_router.route(normalized_unit.form)
                comparison_class = _comparison_class(route, baseline_route)
                comparison_key = (
                    normalized_unit.form,
                    route["bucket"],
                    route.get("target"),
                    baseline_route["bucket"],
                    baseline_route.get("target"),
                )
                if comparison_key not in comparison_rows:
                    comparison_rows[comparison_key] = {
                        "record_version": "lyrics-route-comparison/v1",
                        "comparison_id": _stable_id(
                            "comparison",
                            {
                                "version": "lyrics-route-comparison/v1",
                                "run_id": run_id,
                                "normalized_form": normalized_unit.form,
                                "current": [route["bucket"], route.get("target")],
                                "baseline": [baseline_route["bucket"], baseline_route.get("target")],
                            },
                        ),
                        "run_id": run_id,
                        "normalized_form": normalized_unit.form,
                        "occurrence_count": 0,
                        "classification": comparison_class,
                        "baseline_snapshot_content_id": inputs["routing_snapshot"],
                        "baseline": {
                            "method_id": comparison_router.method_id,
                            "status": baseline_route["status"],
                            "bucket": baseline_route["bucket"],
                            "target": baseline_route.get("target"),
                        },
                        "current": {
                            "method_id": router.method_id,
                            "status": route["status"],
                            "bucket": route["bucket"],
                            "target": route.get("target"),
                            "reason_codes": route["reason_codes"],
                            "evidence_kind": route.get("evidence_kind", router.evidence_kind),
                            "input_artifact_ids": [
                                inputs[name] for name in route["consulted_inputs"]
                            ],
                        },
                    }
                comparison_rows[comparison_key]["occurrence_count"] += 1
                route_id = _stable_id(
                    "route",
                    {"version": "lyrics-route-decision/v2", "analysis_unit_id": unit_id, **route},
                )
                route_record = {
                    "record_version": "lyrics-route-decision/v2",
                    "route_id": route_id,
                    "analysis_unit_id": unit_id,
                    "normalized_form": normalized_unit.form,
                    **route,
                    "method_id": router.method_id,
                    "evidence_kind": route.get("evidence_kind", router.evidence_kind),
                    "input_artifact_ids": [
                        inputs[name] for name in route["consulted_inputs"]
                    ],
                    "comparison_snapshot_content_id": inputs["routing_snapshot"],
                }
                routes.append(route_record)
                route_counts[route["bucket"]] = route_counts.get(route["bucket"], 0) + 1
                events.append(
                    build_lineage_event(
                        subject={"kind": "analysis_unit", "id": unit_id},
                        phase="route",
                        operation="exclude" if route["status"] == "excluded" else "route",
                        run_id=run_id,
                        method_id=router.method_id,
                        input_refs=[{"kind": "analysis_unit", "id": unit_id}] + [
                            {"kind": "routing_input", "id": inputs[name], "content_id": inputs[name]}
                            for name in route["consulted_inputs"]
                        ],
                        output_refs=[{"kind": "route_decision", "id": route_id}],
                        evidence_kind=route.get("evidence_kind", router.evidence_kind),
                        decision=route,
                        reason_codes=route["reason_codes"],
                        language_adapter=router.method_id if routing_mode == "live" else None,
                    )
                )

    temporary_root = workspace.root / ".fluency" / "temporary"
    temporary = Path(tempfile.mkdtemp(prefix="lyrics-process-", dir=temporary_root))
    try:
        (temporary / "occurrences.jsonl").write_bytes(_jsonl_bytes(occurrences))
        (temporary / "analysis-units.jsonl").write_bytes(_jsonl_bytes(units))
        (temporary / "routes.jsonl").write_bytes(_jsonl_bytes(routes))
        comparisons = sorted(comparison_rows.values(), key=lambda item: item["normalized_form"])
        (temporary / "route-comparison.jsonl").write_bytes(_jsonl_bytes(comparisons))
        (temporary / "lineage.jsonl").write_bytes(_jsonl_bytes(events))
        units_per_occurrence = Counter(unit["occurrence_id"] for unit in units)
        report = {
            "report_version": "lyrics-processing-report/v1",
            "language": language,
            "line_count": len(lines),
            "occurrence_count": len(occurrences),
            "analysis_unit_count": len(units),
            "split_occurrence_count": sum(
                count > 1 for count in units_per_occurrence.values()
            ),
            "normalization_reasons": dict(sorted(normalization_reasons.items())),
            "route_counts": dict(sorted(route_counts.items())),
            "route_comparison": dict(sorted(Counter(row["classification"] for row in comparisons).items())),
            "route_comparison_form_count": len(comparisons),
            "lineage_event_count": len(events),
            "routing_provenance": router.evidence_kind,
        }
        (temporary / "report.json").write_bytes(json_bytes(report))
        output_names = ("occurrences.jsonl", "analysis-units.jsonl", "routes.jsonl", "route-comparison.jsonl", "lineage.jsonl", "report.json")
        outputs = {name: file_content_id(temporary / name) for name in output_names}
        manifest = {
            "manifest_version": STAGE_VERSION,
            "run_id": run_id,
            "stage": "process",
            "status": "complete",
            "started_at": started_at.isoformat().replace("+00:00", "Z"),
            "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "methods": {"tokenize": TOKENIZER_ID, "normalize": adapter.method_id, "route": router.method_id},
            "implementation_content_id": canonical_content_id(
                {
                    "process": file_content_id(Path(__file__)),
                    "adapter": file_content_id(Path(__file__).parent / "languages" / "spanish.py"),
                    "routing": file_content_id(Path(__file__).with_name("routing.py")),
                    "spanish_routing": file_content_id(Path(__file__).parent / "languages" / "spanish_routing.py"),
                }
            ),
            "inputs": inputs,
            "outputs": outputs,
        }
        (temporary / "manifest.json").write_bytes(json_bytes(manifest))
        output_directory.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temporary, output_directory)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)

    stages = dict(run_manifest.get("stages", {}))
    stages["process"] = {
        "path": "stages/02_process/output",
        "manifest_content_id": file_content_id(output_directory / "manifest.json"),
    }
    run_manifest["stages"] = stages
    atomic_write(run_manifest_path, run_manifest, temporary_root)
    return output_directory
