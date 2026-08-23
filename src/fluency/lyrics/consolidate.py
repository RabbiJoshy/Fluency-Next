"""Consolidate immutable Lyrics occurrences into auditable surface-card candidates."""

from __future__ import annotations

from collections import Counter, defaultdict
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


STAGE_VERSION = "lyrics-consolidation-stage/v2"
CARD_VERSION = "lyrics-consolidated-card/v1"
EXAMPLE_VERSION = "lyrics-consolidated-example/v2"
DISPOSITION_VERSION = "lyrics-consolidation-disposition/v1"
POLICY_VERSION = "lyrics-consolidation-policy/v2"


class LyricsConsolidationError(ValueError):
    """Raised when exact upstream lineage cannot be consolidated safely."""


def consolidation_policy(
    *, example_cap_per_sense: int, translation_language: str
) -> dict[str, Any]:
    return {
        "policy_version": POLICY_VERSION,
        "card_identity": "surface_card_id",
        "sense_identity": "exact_menu_analysis_and_sense",
        "example_order": "source_position_then_token_span_then_analysis_slot",
        "duplicate_policy": "retain_all_lineage_select_first_occurrence_per_line",
        "example_cap_per_sense": example_cap_per_sense,
        "translation_language": translation_language,
        "translation_selection": "exact_target_language_or_null; duplicate_target_language_fails",
        "missing_translation": "nullable",
        "non_assigned_policy": "emit_disposition_without_study_card",
    }


def consolidation_implementation_content_id(repository_root: Path) -> str:
    return canonical_content_id({
        "implementation": file_content_id(Path(__file__)),
        "schemas": {
            name: file_content_id(repository_root / "schemas" / name)
            for name in (
                "lyrics-consolidated-card.schema.json",
                "lyrics-consolidated-example.schema.json",
                "lyrics-consolidation-disposition.schema.json",
            )
        },
    })


def _object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LyricsConsolidationError(f"required JSON is unavailable or invalid: {path}") from error
    if not isinstance(value, dict):
        raise LyricsConsolidationError(f"required JSON must contain an object: {path}")
    return value


def _jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        values = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    except (OSError, json.JSONDecodeError) as error:
        raise LyricsConsolidationError(f"required JSONL is unavailable or invalid: {path}") from error
    if not all(isinstance(value, dict) for value in values):
        raise LyricsConsolidationError(f"JSONL contains a non-object: {path}")
    return values


def _unique(records: list[dict[str, Any]], key: str, label: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for record in records:
        identity = record.get(key)
        if not isinstance(identity, str) or not identity or identity in result:
            raise LyricsConsolidationError(f"{label} contains a missing or duplicate {key}")
        result[identity] = record
    return result


def _stable_id(prefix: str, value: object) -> str:
    return prefix + "_" + canonical_content_id(value).removeprefix("sha256:")[:32]


def _verify_output(manifest: dict[str, Any], path: Path, name: str) -> str:
    content_id = file_content_id(path)
    if manifest.get("outputs", {}).get(name) != content_id:
        raise LyricsConsolidationError(f"upstream artifact changed after completion: {path}")
    return content_id


def _selected_menu_leaf(
    result: dict[str, Any], analyses: list[dict[str, Any]]
) -> tuple[dict[str, Any], dict[str, Any]]:
    analysis = next(
        (item for item in analyses if item.get("menu_analysis_id") == result["menu_analysis_id"]),
        None,
    )
    if analysis is None:
        raise LyricsConsolidationError("assigned result lost its exact menu analysis")
    sense = next(
        (item for item in analysis.get("senses", []) if item.get("sense_id") == result["selected_sense_id"]),
        None,
    )
    if sense is None:
        raise LyricsConsolidationError("assigned result lost its exact menu sense")
    return analysis, sense


def consolidate_lyrics_run(
    repository_root: Path,
    workspace: Workspace,
    *,
    run_id: str,
    language: str,
    example_cap_per_sense: int = 12,
    translation_language: str = "en",
    started_at: datetime | None = None,
) -> Path:
    """Create an inactive, lossless consolidation layer from one exact WSD run."""

    if example_cap_per_sense <= 0:
        raise LyricsConsolidationError("example cap per sense must be positive")
    if not translation_language:
        raise LyricsConsolidationError("translation language must be non-empty")
    run = workspace.root / "runs" / language / "lyrics" / run_id
    run_manifest_path = run / "manifest.json"
    run_manifest = _object(run_manifest_path)
    if (
        run_manifest.get("run_id") != run_id
        or run_manifest.get("language") != language
        or run_manifest.get("mode") != "lyrics"
    ):
        raise LyricsConsolidationError("Lyrics run identity does not match consolidation")

    source = run / "stages/01_source_ingest/output"
    process = run / "stages/02_process/output"
    lexical = run / "stages/03_lexical_menu/output"
    prepare = run / "stages/04_wsd_prepare/output"
    wsd = run / "stages/05_wsd_results/output"
    output = run / "stages/06_consolidation_v2/output"
    if output.exists():
        raise LyricsConsolidationError("consolidation output already exists; create a new run")

    manifests = {name: _object(path / "manifest.json") for name, path in {
        "source": source, "process": process, "lexical": lexical,
        "prepare": prepare, "wsd": wsd,
    }.items()}
    paths = {
        "song": source / "song.json",
        "lines": source / "lines.jsonl",
        "alignments": source / "alignments.jsonl",
        "occurrences": process / "occurrences.jsonl",
        "analysis_units": process / "analysis-units.jsonl",
        "routes": process / "routes.jsonl",
        "lexical_candidates": lexical / "lexical-candidates.jsonl",
        "sense_menu": lexical / "sense-menu.json",
        "requests": prepare / "requests.jsonl",
        "results": wsd / "results.jsonl",
        "wsd_method": wsd / "method.json",
    }
    inputs = {
        "song": _verify_output(manifests["source"], paths["song"], "song.json"),
        "lines": _verify_output(manifests["source"], paths["lines"], "lines.jsonl"),
        "alignments": _verify_output(manifests["source"], paths["alignments"], "alignments.jsonl"),
        "occurrences": _verify_output(manifests["process"], paths["occurrences"], "occurrences.jsonl"),
        "analysis_units": _verify_output(manifests["process"], paths["analysis_units"], "analysis-units.jsonl"),
        "routes": _verify_output(manifests["process"], paths["routes"], "routes.jsonl"),
        "lexical_candidates": _verify_output(manifests["lexical"], paths["lexical_candidates"], "lexical-candidates.jsonl"),
        "sense_menu": _verify_output(manifests["lexical"], paths["sense_menu"], "sense-menu.json"),
        "requests": _verify_output(manifests["prepare"], paths["requests"], "requests.jsonl"),
        "results": _verify_output(manifests["wsd"], paths["results"], "results.jsonl"),
        "wsd_method": _verify_output(manifests["wsd"], paths["wsd_method"], "method.json"),
    }
    song = _object(paths["song"])
    lines = _unique(_jsonl(paths["lines"]), "line_id", "source lines")
    alignment_records = _unique(_jsonl(paths["alignments"]), "alignment_id", "line alignments")
    alignments_by_line: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for alignment in alignment_records.values():
        if alignment.get("line_id") not in lines:
            raise LyricsConsolidationError("alignment refers to an unknown source line")
        alignments_by_line[alignment["line_id"]].append(alignment)
    occurrences = _unique(_jsonl(paths["occurrences"]), "occurrence_id", "occurrences")
    units = _unique(_jsonl(paths["analysis_units"]), "analysis_unit_id", "analysis units")
    routes = _unique(_jsonl(paths["routes"]), "analysis_unit_id", "routes")
    candidates = _unique(_jsonl(paths["lexical_candidates"]), "lexical_candidate_id", "lexical candidates")
    analyses_by_card = index_menu_analyses(_object(paths["sense_menu"]))
    requests = _unique(_jsonl(paths["requests"]), "request_id", "WSD requests")
    results = _unique(_jsonl(paths["results"]), "request_id", "WSD results")
    method = _object(paths["wsd_method"])
    if set(requests) != set(results) or len(units) != len(requests):
        raise LyricsConsolidationError("consolidation requires one complete WSD result per analysis unit")

    policy = consolidation_policy(
        example_cap_per_sense=example_cap_per_sense,
        translation_language=translation_language,
    )
    card_groups: dict[str, dict[str, Any]] = {}
    card_first_positions: dict[str, tuple[int, int, int]] = {}
    example_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    dispositions: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()

    for request in requests.values():
        result = results[request["request_id"]]
        unit_id = request["target"]["id"]
        unit = units.get(unit_id)
        occurrence = occurrences.get(request["occurrence_id"])
        candidate = candidates.get(request["lexical_candidate_id"])
        route = routes.get(unit_id)
        if unit is None or occurrence is None or candidate is None or route is None:
            raise LyricsConsolidationError("WSD result cannot be joined to exact processing inputs")
        line = lines.get(occurrence["line_id"])
        if line is None or line["text"] != request["context"]["text"]:
            raise LyricsConsolidationError("WSD context cannot be joined to its exact source line")
        if (
            unit.get("occurrence_id") != occurrence["occurrence_id"]
            or route.get("analysis_unit_id") != unit_id
            or candidate.get("analysis_unit_id") != unit_id
            or result.get("occurrence_id") != occurrence["occurrence_id"]
            or result.get("surface_card_id") != candidate.get("surface_card_id")
        ):
            raise LyricsConsolidationError("cross-stage Lyrics identities do not agree")

        status = result["status"]
        status_counts[status] += 1
        disposition_id = _stable_id("disposition", {
            "version": DISPOSITION_VERSION, "run_id": run_id,
            "analysis_unit_id": unit_id, "result_id": result["result_id"],
        })
        disposition: dict[str, Any] = {
            "record_version": DISPOSITION_VERSION,
            "disposition_id": disposition_id,
            "run_id": run_id,
            "language": language,
            "artist_id": song["artist"]["id"],
            "song_id": song["song_id"],
            "line_id": line["line_id"],
            "occurrence_id": occurrence["occurrence_id"],
            "analysis_unit_id": unit_id,
            "surface_card_id": candidate["surface_card_id"],
            "normalized_form": unit["normalized_form"],
            "route_id": route["route_id"],
            "route_bucket": route["bucket"],
            "lexical_candidate_id": candidate["lexical_candidate_id"],
            "wsd_request_id": request["request_id"],
            "wsd_result_id": result["result_id"],
            "wsd_status": status,
            "study_status": "included" if status == "assigned" else "not_included",
            "reason_codes": list(result.get("evidence", {}).get("reason_codes", [])),
            "example_id": None,
        }

        output_refs: list[dict[str, str]] = [{"kind": "consolidation_disposition", "id": disposition_id}]
        if status == "assigned":
            analysis, sense = _selected_menu_leaf(
                result, resolve_candidate_analyses(candidate, analyses_by_card)
            )
            sense_key = _stable_id("sense_assignment", {
                "menu_content_id": result["menu_content_id"],
                "menu_analysis_id": result["menu_analysis_id"],
                "sense_id": result["selected_sense_id"],
            })
            card_id = candidate["surface_card_id"]
            card = card_groups.setdefault(card_id, {
                "record_version": CARD_VERSION,
                "card_id": card_id,
                "identity_version": "surface-card/v1",
                "language": language,
                "unit_type": "surface",
                "surface_key": unit["normalized_form"],
                "display_form": unit["normalized_form"],
                "artist_id": song["artist"]["id"],
                "run_id": run_id,
                "sense_groups": {},
                "occurrence_ids": [],
            })
            if card["surface_key"] != unit["normalized_form"]:
                raise LyricsConsolidationError("one surface card ID resolved to multiple surface keys")
            group = card["sense_groups"].setdefault(sense_key, {
                "sense_assignment_id": sense_key,
                "menu_content_id": result["menu_content_id"],
                "menu_analysis_id": analysis["menu_analysis_id"],
                "source_sense_id": sense["sense_id"],
                "headword": analysis.get("headword"),
                "lemma": analysis.get("lemma"),
                "part_of_speech": analysis["part_of_speech"],
                "translation": sense.get("translation"),
                "definition": sense.get("definition"),
                "source_reference": sense.get("source_reference"),
                "provider": candidate["provider"],
                "example_ids": [],
                "occurrence_ids": [],
            })
            example_id = _stable_id("lyrics_example", {
                "version": EXAMPLE_VERSION, "card_id": card_id,
                "sense_assignment_id": sense_key, "occurrence_id": occurrence["occurrence_id"],
                "analysis_unit_id": unit_id, "wsd_result_id": result["result_id"],
            })
            line_alignments = sorted(
                alignments_by_line.get(line["line_id"], []), key=lambda item: item["alignment_id"]
            )
            target_alignments = [
                item for item in line_alignments
                if item.get("target", {}).get("language") == translation_language
            ]
            if len(target_alignments) > 1:
                raise LyricsConsolidationError(
                    "multiple translations for one line and target language require explicit review"
                )
            alignment = target_alignments[0] if target_alignments else None
            example = {
                "record_version": EXAMPLE_VERSION,
                "example_id": example_id,
                "run_id": run_id,
                "language": language,
                "artist": song["artist"],
                "song": {"song_id": song["song_id"], "title": song["title"]},
                "line": {
                    "line_id": line["line_id"], "source_position": line["source_position"],
                    "text": line["text"], "section": line.get("section"),
                },
                "translation": (
                    {"alignment_id": alignment["alignment_id"], **alignment["target"], "source": alignment["source"]}
                    if alignment is not None else None
                ),
                "translations": [
                    {
                        "alignment_id": item["alignment_id"], **item["target"],
                        "source": item["source"],
                    }
                    for item in line_alignments
                ],
                "occurrence": {
                    "occurrence_id": occurrence["occurrence_id"], "surface": occurrence["surface"],
                    "span": occurrence["span"], "ordinal": occurrence["ordinal"],
                },
                "analysis_unit": {
                    "analysis_unit_id": unit_id, "normalized_form": unit["normalized_form"],
                    "operation": unit["operation"], "slot": unit["slot"],
                },
                "card_id": card_id,
                "sense_assignment_id": sense_key,
                "route": {"route_id": route["route_id"], "bucket": route["bucket"], "method_id": route["method_id"]},
                "menu": {
                    "lexical_candidate_id": candidate["lexical_candidate_id"],
                    "menu_content_id": result["menu_content_id"],
                    "menu_analysis_id": result["menu_analysis_id"],
                    "sense_id": result["selected_sense_id"],
                },
                "wsd": {
                    "request_id": request["request_id"], "result_id": result["result_id"],
                    "method_profile_id": method["profile_id"], "method_id": method["source_method_id"],
                    "confidence": result["confidence"], "decision_path": result["decision_path"],
                },
                "source": song["source"],
                "selected_for_study": False,
                "selection_reason": None,
            }
            example_groups[(card_id, sense_key)].append(example)
            position = (line["source_position"], occurrence["span"][0], unit["slot"])
            card_first_positions[card_id] = min(position, card_first_positions.get(card_id, position))
            card["occurrence_ids"].append(occurrence["occurrence_id"])
            group["occurrence_ids"].append(occurrence["occurrence_id"])
            disposition["example_id"] = example_id
            output_refs.append({"kind": "lyrics_example", "id": example_id})

        dispositions.append(disposition)
        events.append(build_lineage_event(
            subject=request["target"], phase="consolidate",
            operation="materialize" if status == "assigned" else "exclude",
            run_id=run_id, method_id=POLICY_VERSION,
            input_refs=[{"kind": "wsd_result", "id": result["result_id"]}],
            output_refs=output_refs, evidence_kind="direct",
            decision={"wsd_status": status, "study_status": disposition["study_status"]},
            reason_codes=disposition["reason_codes"],
        ))

    examples: list[dict[str, Any]] = []
    selected_count = 0
    for group_key in sorted(example_groups):
        group_examples = sorted(
            example_groups[group_key],
            key=lambda item: (
                item["line"]["source_position"], item["occurrence"]["span"][0],
                item["analysis_unit"]["slot"], item["example_id"],
            ),
        )
        selected_lines: set[str] = set()
        for example in group_examples:
            line_id = example["line"]["line_id"]
            if line_id in selected_lines:
                example["selection_reason"] = "duplicate_line_for_card_sense"
            elif len(selected_lines) >= example_cap_per_sense:
                example["selection_reason"] = "example_cap_reached"
            else:
                example["selected_for_study"] = True
                example["selection_reason"] = "source_order_unique_line"
                selected_lines.add(line_id)
                selected_count += 1
            examples.append(example)
            card_groups[group_key[0]]["sense_groups"][group_key[1]]["example_ids"].append(example["example_id"])

    cards: list[dict[str, Any]] = []
    for rank, card_id in enumerate(
        sorted(card_groups, key=lambda identity: (card_first_positions[identity], identity)), start=1
    ):
        card = card_groups[card_id]
        card["rank"] = rank
        card["sense_groups"] = [card["sense_groups"][key] for key in sorted(card["sense_groups"])]
        card["occurrence_ids"] = sorted(set(card["occurrence_ids"]))
        for group in card["sense_groups"]:
            group["occurrence_ids"] = sorted(set(group["occurrence_ids"]))
        cards.append(card)

    started_at = datetime.now(UTC) if started_at is None else started_at.astimezone(UTC)
    temporary_root = workspace.root / ".fluency/temporary"
    temporary = Path(tempfile.mkdtemp(prefix="lyrics-consolidation-", dir=temporary_root))
    try:
        (temporary / "cards.jsonl").write_bytes(b"".join(json_bytes(item) for item in cards))
        (temporary / "examples.jsonl").write_bytes(b"".join(json_bytes(item) for item in examples))
        (temporary / "dispositions.jsonl").write_bytes(b"".join(json_bytes(item) for item in dispositions))
        (temporary / "lineage.jsonl").write_bytes(b"".join(json_bytes(item) for item in events))
        (temporary / "policy.json").write_bytes(json_bytes(policy))
        report = {
            "report_version": "lyrics-consolidation-report/v1", "run_id": run_id,
            "language": language, "analysis_unit_count": len(dispositions),
            "status_counts": dict(sorted(status_counts.items())),
            "study_card_count": len(cards), "assigned_example_count": len(examples),
            "selected_example_count": selected_count,
            "non_study_disposition_count": sum(1 for item in dispositions if item["study_status"] != "included"),
            "translation_available_count": sum(1 for item in examples if item["translation"] is not None),
            "policy": policy,
        }
        (temporary / "report.json").write_bytes(json_bytes(report))
        output_names = ("cards.jsonl", "examples.jsonl", "dispositions.jsonl", "lineage.jsonl", "policy.json", "report.json")
        outputs = {name: file_content_id(temporary / name) for name in output_names}
        manifest = {
            "manifest_version": STAGE_VERSION, "run_id": run_id, "stage": "consolidation",
            "status": "complete", "started_at": started_at.isoformat().replace("+00:00", "Z"),
            "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "method_id": POLICY_VERSION,
            "implementation_content_id": consolidation_implementation_content_id(repository_root),
            "inputs": inputs, "policy": policy, "outputs": outputs,
        }
        (temporary / "manifest.json").write_bytes(json_bytes(manifest))
        output.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)

    stages = dict(run_manifest.get("stages", {}))
    stages["consolidation"] = {
        "path": "stages/06_consolidation_v2/output",
        "manifest_content_id": file_content_id(output / "manifest.json"),
    }
    run_manifest["stages"] = stages
    atomic_write(run_manifest_path, run_manifest, temporary_root)
    return output
