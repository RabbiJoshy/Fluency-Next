"""Prepare exact, mode-neutral WSD requests from immutable Lyrics artifacts."""

from __future__ import annotations

from collections import Counter
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
from fluency.lyrics.lexical import index_menu_analyses, resolve_candidate_analyses
from fluency.release.io import atomic_write, json_bytes


STAGE_VERSION = "lyrics-wsd-preparation-stage/v1"
REQUEST_VERSION = "wsd-request/v2"


class LyricsWSDPreparationError(ValueError):
    """Raised when a WSD request cannot bind to exact upstream evidence."""


def wsd_preparation_implementation_content_id(repository_root: Path) -> str:
    return canonical_content_id({
        "implementation": file_content_id(Path(__file__)),
        "contract": file_content_id(repository_root / "schemas/wsd-request-v2.schema.json"),
    })


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LyricsWSDPreparationError(f"required JSON is unavailable or invalid: {path}") from error
    if not isinstance(value, dict):
        raise LyricsWSDPreparationError(f"required JSON must contain an object: {path}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    except (OSError, json.JSONDecodeError) as error:
        raise LyricsWSDPreparationError(f"required JSONL is unavailable or invalid: {path}") from error


def _jsonl_bytes(records: list[dict[str, Any]]) -> bytes:
    return b"".join(json_bytes(record) for record in records)


def validate_wsd_request(record: dict[str, Any]) -> None:
    required = {
        "request_version", "request_id", "run_id", "mode", "language", "target",
        "occurrence_id", "surface_card_id", "surface_form", "normalized_form",
        "eligibility", "lexical_candidate_id", "menu_reference", "context",
        "input_artifact_ids",
    }
    if set(record) != required or record["request_version"] != REQUEST_VERSION:
        raise LyricsWSDPreparationError("WSD request fields do not match the v2 contract")
    if record["mode"] != "lyrics" or record["target"].get("kind") != "analysis_unit":
        raise LyricsWSDPreparationError("Lyrics WSD must target an exact analysis unit")
    if record["eligibility"] not in {"ready", "no_menu", "ineligible", "review"}:
        raise LyricsWSDPreparationError("invalid WSD eligibility")
    context = record["context"]
    if not isinstance(context, dict) or not isinstance(context.get("text"), str) or not context["text"]:
        raise LyricsWSDPreparationError("WSD request context is incomplete")
    span = context.get("target_span")
    if not isinstance(span, list) or len(span) != 2 or not all(isinstance(value, int) for value in span):
        raise LyricsWSDPreparationError("WSD request target span is invalid")
    if not (0 <= span[0] < span[1] <= len(context["text"])):
        raise LyricsWSDPreparationError("WSD request target span falls outside its context")
    if context["text"][span[0]:span[1]] != record["surface_form"]:
        raise LyricsWSDPreparationError("WSD request span does not reproduce the source surface")
    menu = record["menu_reference"]
    if record["eligibility"] == "ready":
        if not isinstance(menu, dict) or menu.get("analysis_count", 0) < 1:
            raise LyricsWSDPreparationError("ready WSD requests require an exact non-empty menu reference")
    elif menu is not None:
        raise LyricsWSDPreparationError("non-ready WSD requests cannot claim an executable menu")


def build_wsd_request_records(
    *,
    run_id: str,
    language: str,
    lines: list[dict[str, Any]],
    alignments: list[dict[str, Any]],
    occurrences: list[dict[str, Any]],
    units: list[dict[str, Any]],
    lexical_candidates: list[dict[str, Any]],
    sense_menu: dict[str, Any],
    sense_menu_content_id: str,
    input_artifact_ids: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Materialize complete WSD eligibility and context without executing a model."""

    lines_by_id = {line["line_id"]: line for line in lines}
    alignments_by_line = {alignment["line_id"]: alignment for alignment in alignments}
    occurrences_by_id = {occurrence["occurrence_id"]: occurrence for occurrence in occurrences}
    units_by_id = {unit["analysis_unit_id"]: unit for unit in units}
    if any(len(index) != len(records) for index, records in (
        (lines_by_id, lines), (alignments_by_line, alignments),
        (occurrences_by_id, occurrences), (units_by_id, units),
    )):
        raise LyricsWSDPreparationError("WSD preparation inputs contain duplicate identities")

    requests: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    analyses_by_card = index_menu_analyses(sense_menu)
    for candidate in lexical_candidates:
        unit = units_by_id.get(candidate["analysis_unit_id"])
        if unit is None or unit["occurrence_id"] != candidate["occurrence_id"]:
            raise LyricsWSDPreparationError("lexical candidate does not bind to its analysis unit")
        occurrence = occurrences_by_id.get(candidate["occurrence_id"])
        if occurrence is None:
            raise LyricsWSDPreparationError("lexical candidate occurrence is unavailable")
        line = lines_by_id.get(occurrence["line_id"])
        if line is None:
            raise LyricsWSDPreparationError("WSD context line is unavailable")
        alignment = alignments_by_line.get(line["line_id"])
        translation = None if alignment is None else {
            "alignment_id": alignment["alignment_id"],
            "language": alignment["target"]["language"],
            "text": alignment["target"]["text"],
            "source_snapshot_content_id": alignment["source"]["snapshot_content_id"],
        }
        eligibility = candidate["status"]
        menu_reference = None
        if eligibility == "ready":
            analyses = resolve_candidate_analyses(candidate, analyses_by_card)
            menu_reference = {
                "content_id": sense_menu_content_id,
                "lexical_candidate_id": candidate["lexical_candidate_id"],
                "lookup_card_id": candidate["lookup_card_id"],
                "lookup_form": candidate["lookup_form"],
                "analysis_ids": candidate["menu_analysis_ids"],
                "analysis_count": len(analyses),
                "sense_count": sum(len(analysis.get("senses", [])) for analysis in analyses),
            }
        body = {
            "request_version": REQUEST_VERSION,
            "run_id": run_id,
            "mode": "lyrics",
            "language": language,
            "target": {"kind": "analysis_unit", "id": unit["analysis_unit_id"]},
            "occurrence_id": occurrence["occurrence_id"],
            "surface_card_id": candidate["surface_card_id"],
            "surface_form": occurrence["surface"],
            "normalized_form": unit["normalized_form"],
            "eligibility": eligibility,
            "lexical_candidate_id": candidate["lexical_candidate_id"],
            "menu_reference": menu_reference,
            "context": {
                "kind": "lyrics_line",
                "context_id": line["line_id"],
                "song_id": line["song_id"],
                "text": line["text"],
                "target_span": occurrence["span"],
                "translation": translation,
            },
            "input_artifact_ids": list(dict.fromkeys([
                *input_artifact_ids,
                *candidate.get("input_artifact_ids", []),
            ])),
        }
        request_id = "wsd_request_" + canonical_content_id(body).removeprefix("sha256:")[:32]
        record = {"request_id": request_id, **body}
        validate_wsd_request(record)
        requests.append(record)
        counts[eligibility] += 1
        events.append(build_lineage_event(
            subject={"kind": "analysis_unit", "id": unit["analysis_unit_id"]},
            phase="assign",
            operation="materialize",
            run_id=run_id,
            method_id=STAGE_VERSION,
            input_refs=[
                {"kind": "lexical_candidate", "id": candidate["lexical_candidate_id"]},
                {"kind": "lyrics_line", "id": line["line_id"]},
            ],
            output_refs=[{"kind": "wsd_request", "id": request_id}],
            evidence_kind="direct",
            decision={"eligibility": eligibility, "translation_available": translation is not None},
            reason_codes=[f"wsd_eligibility_{eligibility}"],
        ))
    report = {
        "report_version": "lyrics-wsd-preparation-report/v1",
        "language": language,
        "request_count": len(requests),
        "eligibility_counts": dict(sorted(counts.items())),
        "executable_request_count": counts["ready"],
        "translation_available_count": sum(
            request["context"]["translation"] is not None for request in requests
        ),
        "execution_status": "not_run",
    }
    return requests, events, report


def prepare_lyrics_wsd_stage(
    repository_root: Path,
    workspace: Workspace,
    *,
    run_id: str,
    language: str,
    started_at: datetime | None = None,
) -> Path:
    """Publish immutable WSD requests while leaving model execution external."""

    run = workspace.root / "runs" / language / "lyrics" / run_id
    run_manifest_path = run / "manifest.json"
    run_manifest = _read_json(run_manifest_path)
    if run_manifest.get("run_id") != run_id or run_manifest.get("language") != language or run_manifest.get("mode") != "lyrics":
        raise LyricsWSDPreparationError("Lyrics run identity does not match WSD preparation")
    source = run / "stages/01_source_ingest/output"
    process = run / "stages/02_process/output"
    lexical = run / "stages/03_lexical_menu/output"
    paths = {
        "lines": source / "lines.jsonl",
        "alignments": source / "alignments.jsonl",
        "occurrences": process / "occurrences.jsonl",
        "analysis_units": process / "analysis-units.jsonl",
        "lexical_candidates": lexical / "lexical-candidates.jsonl",
        "sense_menu": lexical / "sense-menu.json",
    }
    manifests = {
        "source": _read_json(source / "manifest.json"),
        "process": _read_json(process / "manifest.json"),
        "lexical": _read_json(lexical / "manifest.json"),
    }
    ownership = (("source", "lines", "lines.jsonl"), ("source", "alignments", "alignments.jsonl"),
                 ("process", "occurrences", "occurrences.jsonl"), ("process", "analysis_units", "analysis-units.jsonl"),
                 ("lexical", "lexical_candidates", "lexical-candidates.jsonl"), ("lexical", "sense_menu", "sense-menu.json"))
    inputs: dict[str, str] = {}
    for owner, key, output_name in ownership:
        actual = file_content_id(paths[key])
        if manifests[owner].get("outputs", {}).get(output_name) != actual:
            raise LyricsWSDPreparationError(f"upstream WSD input changed after completion: {key}")
        inputs[key] = actual
    output = run / "stages/04_wsd_prepare/output"
    if output.exists():
        raise LyricsWSDPreparationError("WSD preparation already exists; create a new run instead of overwriting it")
    requests, events, report = build_wsd_request_records(
        run_id=run_id,
        language=language,
        lines=_read_jsonl(paths["lines"]),
        alignments=_read_jsonl(paths["alignments"]),
        occurrences=_read_jsonl(paths["occurrences"]),
        units=_read_jsonl(paths["analysis_units"]),
        lexical_candidates=_read_jsonl(paths["lexical_candidates"]),
        sense_menu=_read_json(paths["sense_menu"]),
        sense_menu_content_id=inputs["sense_menu"],
        input_artifact_ids=list(inputs.values()),
    )
    started_at = datetime.now(UTC) if started_at is None else started_at.astimezone(UTC)
    temporary_root = workspace.root / ".fluency/temporary"
    temporary_root.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix="lyrics-wsd-prepare-", dir=temporary_root))
    try:
        (temporary / "requests.jsonl").write_bytes(_jsonl_bytes(requests))
        (temporary / "lineage.jsonl").write_bytes(_jsonl_bytes(events))
        (temporary / "report.json").write_bytes(json_bytes(report))
        outputs = {name: file_content_id(temporary / name) for name in ("requests.jsonl", "lineage.jsonl", "report.json")}
        manifest = {
            "manifest_version": STAGE_VERSION,
            "run_id": run_id,
            "stage": "wsd_prepare",
            "status": "complete",
            "started_at": started_at.isoformat().replace("+00:00", "Z"),
            "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "method_id": STAGE_VERSION,
            "implementation_content_id": wsd_preparation_implementation_content_id(repository_root),
            "inputs": inputs,
            "outputs": outputs,
            "execution_status": "not_run",
        }
        (temporary / "manifest.json").write_bytes(json_bytes(manifest))
        output.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    stages = dict(run_manifest.get("stages", {}))
    stages["wsd_prepare"] = {
        "path": "stages/04_wsd_prepare/output",
        "manifest_content_id": file_content_id(output / "manifest.json"),
    }
    run_manifest["stages"] = stages
    atomic_write(run_manifest_path, run_manifest, temporary_root)
    return output
