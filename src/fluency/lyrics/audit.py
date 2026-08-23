"""Build a compact, inspectable song-lineage bundle from legacy artist evidence.

The adapter is intentionally explicit about reconstructed evidence. Preserved claims
remain direct evidence; current routing and final-deck records are labelled as
materialized snapshots rather than being presented as events from an old run.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from fluency.core.hashing import canonical_content_id
from fluency.lyrics.lexical import index_menu_analyses, resolve_candidate_analyses


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def _route_for(form: str, routing: dict[str, Any]) -> dict[str, str]:
    needle = form.casefold()
    for label, values in routing.get("exclude", {}).items():
        if needle in {str(value).casefold() for value in values}:
            return {"status": "excluded", "label": label.replace("_", " ")}
    for label, values in routing.get("classifier", {}).items():
        if isinstance(values, dict) and needle in {str(key).casefold() for key in values}:
            return {"status": "classified", "label": label.replace("_", " ")}
        if isinstance(values, list) and needle in {str(value).casefold() for value in values}:
            return {"status": "classified", "label": label.replace("_", " ")}
    if needle in {str(key).casefold() for key in routing.get("derivation_map", {})}:
        return {"status": "derived", "label": "derivation map"}
    if needle in {str(value).casefold() for value in routing.get("sense_discovery", [])}:
        return {"status": "review", "label": "sense discovery"}
    if needle in {str(key).casefold() for key in routing.get("clitic_merge", {})}:
        return {"status": "classified", "label": "clitic merge"}
    return {"status": "unresolved", "label": "no preserved route"}


def _normalization_claims(path: Path, wanted: set[str]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for claim in _read_jsonl(path):
        occurrence_id = claim.get("subject", {}).get("id")
        if occurrence_id in wanted:
            result[occurrence_id] = claim
    return result


def _normalized_form(claim: dict[str, Any] | None, fallback: str) -> str:
    units = (claim or {}).get("value", {}).get("analysis_units", [])
    return " + ".join(str(unit.get("normalized_form", "")) for unit in units) or fallback.casefold()


def _song_examples(
    examples_path: Path,
    vocabulary_path: Path,
    song_id: str,
) -> tuple[dict[str, list[dict[str, Any]]], int]:
    examples = _read_json(examples_path)
    vocabulary = _read_json(vocabulary_path)
    by_line: dict[str, list[dict[str, Any]]] = defaultdict(list)
    count = 0
    for card_id, menus in examples.items():
        card = vocabulary.get(card_id, {})
        for menu_key, groups in menus.items():
            if not isinstance(groups, list):
                continue
            for sense_index, group in enumerate(groups):
                if not isinstance(group, list):
                    continue
                senses = card.get("senses", [])
                sense = senses[sense_index] if sense_index < len(senses) else {}
                for example in group:
                    if str(example.get("song")) != song_id:
                        continue
                    by_line[str(example.get("spanish", ""))].append(
                        {
                            "card_id": card_id,
                            "word": card.get("word", card_id),
                            "lemma": card.get("lemma"),
                            "menu": menu_key,
                            "sense_index": sense_index,
                            "sense": {
                                key: sense.get(key)
                                for key in ("headword", "pos", "translation", "context", "source", "sense_id")
                                if sense.get(key) is not None
                            },
                            "assignment_method": example.get("assignment_method"),
                            "prompt_id": example.get("prompt_id"),
                            "run_ts": example.get("run_ts"),
                            "translation_source": example.get("translation_source"),
                        }
                    )
                    count += 1
    return dict(by_line), count


def build_bundle(
    *,
    legacy_artist_root: Path,
    release_root: Path,
    song_id: str,
    baseline_run: str,
    candidate_run: str,
    source_ingest: Path | None = None,
    process_output: Path | None = None,
    lexical_output: Path | None = None,
    wsd_prepare_output: Path | None = None,
    wsd_results_output: Path | None = None,
    consolidation_output: Path | None = None,
) -> dict[str, Any]:
    evidence = legacy_artist_root / "data" / "evidence"
    candidate_ledger = evidence / "ledger" / "runs" / candidate_run
    segments = [
        item
        for item in _read_jsonl(candidate_ledger / "segments.jsonl")
        if str(item.get("source", {}).get("song_id")) == song_id
    ]
    segments.sort(key=lambda item: item.get("source", {}).get("positions", [999999])[0])
    segment_ids = {item["segment_id"] for item in segments}
    occurrences = [
        item
        for item in _read_jsonl(candidate_ledger / "occurrences.jsonl")
        if item.get("segment_id") in segment_ids
    ]
    occurrences_by_segment: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for occurrence in occurrences:
        occurrences_by_segment[occurrence["segment_id"]].append(occurrence)
    for values in occurrences_by_segment.values():
        values.sort(key=lambda item: (item.get("ordinal", 0), item.get("span", [0])[0]))

    occurrence_ids = {item["occurrence_id"] for item in occurrences}
    normalization_dir = evidence / "overlays" / "normalization"
    baseline_claims = _normalization_claims(normalization_dir / f"{baseline_run}.jsonl", occurrence_ids)
    candidate_claims = _normalization_claims(normalization_dir / f"{candidate_run}.jsonl", occurrence_ids)
    baseline_manifest = _read_json(normalization_dir / f"{baseline_run}.manifest.json")
    candidate_manifest = _read_json(normalization_dir / f"{candidate_run}.manifest.json")
    routing = _read_json(legacy_artist_root / "data" / "known_vocab" / "word_routing.json")
    examples_by_line, assignment_count = _song_examples(
        release_root / "Artists" / "es" / "bad-bunny" / "examples.json",
        release_root / "Artists" / "es" / "vocabulary_master.json",
        song_id,
    )
    translations = _read_json(legacy_artist_root / "data" / "layers" / "example_translations.json")
    ingested_song: dict[str, Any] | None = None
    ingested_by_text: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
    alignments_by_line: dict[str, dict[str, Any]] = {}
    source_lineage_event_count = 0
    process_manifest: dict[str, Any] | None = None
    processed_by_line: dict[str, list[dict[str, Any]]] = defaultdict(list)
    processed_units: dict[str, list[dict[str, Any]]] = defaultdict(list)
    processed_routes: dict[str, dict[str, Any]] = {}
    route_comparisons: dict[str, dict[str, Any]] = {}
    route_profile_ids: dict[str, str] = {}
    routing_profiles: dict[str, dict[str, Any]] = {}
    process_lineage_event_count = 0
    lexical_by_unit: dict[str, dict[str, Any]] = {}
    lexical_profile_ids: dict[str, str] = {}
    lexical_profiles: dict[str, dict[str, Any]] = {}
    lexical_report: dict[str, Any] | None = None
    lexical_lineage_event_count = 0
    wsd_requests_by_unit: dict[str, dict[str, Any]] = {}
    wsd_prepare_report: dict[str, Any] | None = None
    wsd_result_refs_by_unit: dict[str, dict[str, Any]] = {}
    wsd_result_profiles: dict[str, dict[str, Any]] = {}
    wsd_results_report: dict[str, Any] | None = None
    wsd_method: dict[str, Any] | None = None
    consolidation_refs_by_unit: dict[str, dict[str, Any]] = {}
    consolidation_dispositions: dict[str, dict[str, Any]] = {}
    consolidated_examples: dict[str, dict[str, Any]] = {}
    consolidated_cards: dict[str, dict[str, Any]] = {}
    consolidation_report: dict[str, Any] | None = None
    if source_ingest is not None:
        source_ingest = source_ingest.expanduser().resolve()
        ingested_song = _read_json(source_ingest / "song.json")
        for source_line in _read_jsonl(source_ingest / "lines.jsonl"):
            ingested_by_text[source_line["text"]].append(source_line)
        alignments_by_line = {
            alignment["line_id"]: alignment
            for alignment in _read_jsonl(source_ingest / "alignments.jsonl")
        }
        source_lineage_event_count = sum(1 for _ in _read_jsonl(source_ingest / "lineage.jsonl"))
    if process_output is not None:
        if source_ingest is None:
            raise ValueError("process output requires its matching source ingest")
        process_output = process_output.expanduser().resolve()
        process_manifest = _read_json(process_output / "manifest.json")
        for processed in _read_jsonl(process_output / "occurrences.jsonl"):
            processed_by_line[processed["line_id"]].append(processed)
        for values in processed_by_line.values():
            values.sort(key=lambda item: item["ordinal"])
        for unit in _read_jsonl(process_output / "analysis-units.jsonl"):
            processed_units[unit["occurrence_id"]].append(unit)
        for values in processed_units.values():
            values.sort(key=lambda item: item["slot"])
        processed_routes = {
            route["analysis_unit_id"]: route
            for route in _read_jsonl(process_output / "routes.jsonl")
        }
        comparison_path = process_output / "route-comparison.jsonl"
        if comparison_path.exists():
            route_comparisons = {
                comparison["normalized_form"]: comparison
                for comparison in _read_jsonl(comparison_path)
            }
        for analysis_unit_id, route in processed_routes.items():
            decision = {
                key: value
                for key, value in route.items()
                if key not in {"route_id", "analysis_unit_id"}
            }
            profile_id = "route_profile_" + canonical_content_id(decision).removeprefix("sha256:")[:32]
            route_profile_ids[analysis_unit_id] = profile_id
            routing_profiles[profile_id] = {
                "decision": decision,
                "comparison": route_comparisons.get(route["normalized_form"]),
            }
        process_lineage_event_count = sum(1 for _ in _read_jsonl(process_output / "lineage.jsonl"))
    if lexical_output is not None:
        if process_output is None:
            raise ValueError("lexical output requires its matching process output")
        lexical_output = lexical_output.expanduser().resolve()
        lexical_report = _read_json(lexical_output / "report.json")
        analyses_by_card = index_menu_analyses(_read_json(lexical_output / "sense-menu.json"))
        lexical_by_unit = {
            candidate["analysis_unit_id"]: candidate
            for candidate in _read_jsonl(lexical_output / "lexical-candidates.jsonl")
        }
        for analysis_unit_id, candidate in lexical_by_unit.items():
            profile = {
                key: candidate[key]
                for key in (
                    "status", "lookup_form", "lookup_card_id", "provider",
                    "menu_analysis_ids", "menu_analysis_count", "menu_sense_count", "reason_codes"
                )
            }
            profile["analyses"] = resolve_candidate_analyses(candidate, analyses_by_card)
            profile_id = "lexical_profile_" + canonical_content_id(profile).removeprefix("sha256:")[:32]
            lexical_profile_ids[analysis_unit_id] = profile_id
            lexical_profiles[profile_id] = profile
        lexical_lineage_event_count = sum(1 for _ in _read_jsonl(lexical_output / "lineage.jsonl"))
    if wsd_prepare_output is not None:
        if lexical_output is None:
            raise ValueError("WSD preparation output requires its matching lexical output")
        wsd_prepare_output = wsd_prepare_output.expanduser().resolve()
        wsd_prepare_report = _read_json(wsd_prepare_output / "report.json")
        wsd_requests_by_unit = {
            request["target"]["id"]: {
                "request_id": request["request_id"],
                "eligibility": request["eligibility"],
                "translation_available": request["context"]["translation"] is not None,
                "execution_status": "not_run",
            }
            for request in _read_jsonl(wsd_prepare_output / "requests.jsonl")
        }
    if wsd_results_output is not None:
        if wsd_prepare_output is None:
            raise ValueError("WSD results require their matching preparation output")
        wsd_results_output = wsd_results_output.expanduser().resolve()
        wsd_results_report = _read_json(wsd_results_output / "report.json")
        wsd_method = _read_json(wsd_results_output / "method.json")
        for result in _read_jsonl(wsd_results_output / "results.jsonl"):
            analysis_unit_id = result["target"]["id"]
            result_id = result["result_id"]
            if analysis_unit_id in wsd_result_refs_by_unit or result_id in wsd_result_profiles:
                raise ValueError("WSD audit results contain duplicate identities")
            wsd_result_refs_by_unit[analysis_unit_id] = {
                "result_id": result_id,
                "analysis_unit_id": analysis_unit_id,
            }
            wsd_result_profiles[result_id] = {
                key: value
                for key, value in result.items()
                if key not in {"result_id", "target", "occurrence_id", "surface_card_id", "surface_form"}
            }
    if consolidation_output is not None:
        if wsd_results_output is None:
            raise ValueError("consolidation output requires its matching WSD results")
        consolidation_output = consolidation_output.expanduser().resolve()
        consolidation_report = _read_json(consolidation_output / "report.json")
        consolidated_cards = {
            card["card_id"]: card
            for card in _read_jsonl(consolidation_output / "cards.jsonl")
        }
        consolidated_examples = {
            example["example_id"]: example
            for example in _read_jsonl(consolidation_output / "examples.jsonl")
        }
        for disposition in _read_jsonl(consolidation_output / "dispositions.jsonl"):
            analysis_unit_id = disposition["analysis_unit_id"]
            disposition_id = disposition["disposition_id"]
            if analysis_unit_id in consolidation_refs_by_unit or disposition_id in consolidation_dispositions:
                raise ValueError("consolidation audit records contain duplicate identities")
            consolidation_refs_by_unit[analysis_unit_id] = {
                "analysis_unit_id": analysis_unit_id,
                "disposition_id": disposition_id,
                "card_id": disposition["surface_card_id"] if disposition["study_status"] == "included" else None,
                "example_id": disposition["example_id"],
            }
            consolidation_dispositions[disposition_id] = disposition

    changed_count = 0
    restored_count = 0
    lines: list[dict[str, Any]] = []
    for line_index, segment in enumerate(segments):
        text = segment["text"]
        source_line = ingested_by_text[text].popleft() if ingested_by_text.get(text) else None
        alignment = alignments_by_line.get(source_line["line_id"]) if source_line else None
        clean_occurrences = processed_by_line.get(source_line["line_id"], []) if source_line else []
        line_occurrences: list[dict[str, Any]] = []
        for occurrence_index, occurrence in enumerate(occurrences_by_segment.get(segment["segment_id"], [])):
            occurrence_id = occurrence["occurrence_id"]
            baseline_claim = baseline_claims.get(occurrence_id)
            candidate_claim = candidate_claims.get(occurrence_id)
            baseline_form = _normalized_form(baseline_claim, occurrence["surface"])
            candidate_form = _normalized_form(candidate_claim, occurrence["surface"])
            changed = baseline_form != candidate_form
            if changed:
                changed_count += 1
            restored = "'" in baseline_form and "'" not in candidate_form
            if restored:
                restored_count += 1
            clean_occurrence = clean_occurrences[occurrence_index] if occurrence_index < len(clean_occurrences) else None
            clean_units = processed_units.get(clean_occurrence["occurrence_id"], []) if clean_occurrence else []
            clean_route_records = [
                processed_routes[unit["analysis_unit_id"]]
                for unit in clean_units
                if unit["analysis_unit_id"] in processed_routes
            ]
            clean_route_refs = [
                {
                    "route_id": processed_routes[unit["analysis_unit_id"]]["route_id"],
                    "analysis_unit_id": unit["analysis_unit_id"],
                    "profile_id": route_profile_ids[unit["analysis_unit_id"]],
                }
                for unit in clean_units
                if unit["analysis_unit_id"] in processed_routes
            ]
            clean_route = clean_route_records[0] if len(clean_route_records) == 1 else None
            clean_lexical_refs = [
                {
                    "lexical_candidate_id": lexical_by_unit[unit["analysis_unit_id"]]["lexical_candidate_id"],
                    "analysis_unit_id": unit["analysis_unit_id"],
                    "profile_id": lexical_profile_ids[unit["analysis_unit_id"]],
                }
                for unit in clean_units
                if unit["analysis_unit_id"] in lexical_by_unit
            ]
            current_route = (
                {
                    "status": clean_route["status"],
                    "label": clean_route["bucket"].replace(".", " · ").replace("_", " "),
                    "evidence_kind": clean_route.get("evidence_kind"),
                }
                if clean_route
                else _route_for(candidate_form, routing)
            )
            line_occurrences.append(
                {
                    "occurrence_id": occurrence_id,
                    "surface": occurrence["surface"],
                    "span": occurrence.get("span"),
                    "ordinal": occurrence.get("ordinal"),
                    "changed": changed,
                    "restored": restored,
                    "first_divergence": "normalize" if changed else None,
                    "states": {
                        baseline_run: {
                            "normalized_form": baseline_form,
                            "claim_id": (baseline_claim or {}).get("claim_id"),
                            "input_fingerprint": (baseline_claim or {}).get("input_fingerprint"),
                            "method_id": (baseline_claim or {}).get("method", {}).get("method_id"),
                        },
                        candidate_run: {
                            "normalized_form": candidate_form,
                            "claim_id": (candidate_claim or {}).get("claim_id"),
                            "input_fingerprint": (candidate_claim or {}).get("input_fingerprint"),
                            "method_id": (candidate_claim or {}).get("method", {}).get("method_id"),
                        },
                    },
                    "current_route": current_route,
                    "clean_processing": (
                        {
                            "occurrence_id": clean_occurrence["occurrence_id"],
                            "surface": clean_occurrence["surface"],
                            "span": clean_occurrence["span"],
                            "normalized_form": " + ".join(unit["normalized_form"] for unit in clean_units),
                            "units": clean_units,
                            "routes": clean_route_refs,
                            "lexical_candidates": clean_lexical_refs,
                            "wsd_requests": [
                                wsd_requests_by_unit[unit["analysis_unit_id"]]
                                for unit in clean_units
                                if unit["analysis_unit_id"] in wsd_requests_by_unit
                            ],
                            "wsd_results": [
                                wsd_result_refs_by_unit[unit["analysis_unit_id"]]
                                for unit in clean_units
                                if unit["analysis_unit_id"] in wsd_result_refs_by_unit
                            ],
                            "consolidations": [
                                consolidation_refs_by_unit[unit["analysis_unit_id"]]
                                for unit in clean_units
                                if unit["analysis_unit_id"] in consolidation_refs_by_unit
                            ],
                            "tokenizer_method": (process_manifest or {}).get("methods", {}).get("tokenize"),
                            "normalizer_method": (process_manifest or {}).get("methods", {}).get("normalize"),
                            "router_method": (process_manifest or {}).get("methods", {}).get("route"),
                        }
                        if clean_occurrence
                        else None
                    ),
                }
            )
        lines.append(
            {
                "segment_id": segment["segment_id"],
                "ordinal": line_index,
                "source_position": segment.get("source", {}).get("positions", [line_index])[0],
                "text": text,
                "translation": alignment["target"] if alignment else (None if source_ingest else translations.get(text)),
                "vocalists": segment.get("metadata", {}).get("vocalists", []),
                "occurrences": line_occurrences,
                "app_assignments": examples_by_line.get(text, []),
                "source_ingest": (
                    {
                        "line_id": source_line["line_id"],
                        "source_span": source_line["source_span"],
                        "section": source_line["section"],
                        "alignment": alignment,
                    }
                    if source_line
                    else None
                ),
            }
        )

    title = segments[0].get("source", {}).get("title", song_id) if segments else song_id
    direct_routing = bool(
        process_manifest
        and process_manifest.get("methods", {}).get("route") != "legacy-word-routing-snapshot/v1"
    )
    limitations = [
        "The legacy ledger recorded language as 'und'; this adapter supplies 'es' from the selected artist release.",
        "The two legacy normalization runs remain the historical comparison; clean processing is a new directly reproducible run.",
        "App assignments are current materialized release records, not invented historical run events.",
    ]
    if process_output and not direct_routing:
        limitations.insert(2, "Routing uses a pinned materialized migration snapshot until the shared router itself is ported.")
    if lexical_output:
        limitations.insert(
            3,
            (
                "The clean lexical layer exposes complete provider menus and explicit abstentions; the selected sense is shown only where the imported WSD result binds to that exact menu."
                if wsd_results_output
                else "The clean lexical layer exposes complete provider menus and explicit abstentions; WSD has not selected a sense."
            ),
        )
    return {
        "schema": "fluency.lyrics-audit-bundle/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "language": "es",
        "artist": {"id": "bad-bunny", "name": "Bad Bunny"},
        "song": {"id": song_id, "title": title, "source": "genius", "lines": lines},
        "runs": [
            {
                "run_id": baseline_run,
                "label": "Tokenizer v1",
                "role": "baseline",
                "artifact_sha256": baseline_manifest.get("artifact", {}).get("sha256"),
            },
            {
                "run_id": candidate_run,
                "label": "Tokenizer v3",
                "role": "candidate",
                "artifact_sha256": candidate_manifest.get("artifact", {}).get("sha256"),
            },
        ],
        "routing_profiles": routing_profiles,
        "lexical_profiles": lexical_profiles,
        "wsd_result_profiles": wsd_result_profiles,
        "consolidation_dispositions": consolidation_dispositions,
        "consolidated_examples": consolidated_examples,
        "consolidated_cards": consolidated_cards,
        "comparison": {
            "baseline_run_id": baseline_run,
            "candidate_run_id": candidate_run,
            "line_count": len(lines),
            "occurrence_count": len(occurrences),
            "changed_occurrence_count": changed_count,
            "restored_occurrence_count": restored_count,
            "app_assignment_count": assignment_count,
            "aligned_line_count": len(alignments_by_line),
            "source_lineage_event_count": source_lineage_event_count,
            "process_lineage_event_count": process_lineage_event_count,
            "lexical_lineage_event_count": lexical_lineage_event_count,
            "lexical_status_counts": (lexical_report or {}).get("status_counts", {}),
            "wsd_request_count": (wsd_prepare_report or {}).get("request_count", 0),
            "wsd_executable_request_count": (wsd_prepare_report or {}).get("executable_request_count", 0),
            "wsd_result_counts": (wsd_results_report or {}).get("result_counts", {}),
            "wsd_method_id": (wsd_method or {}).get("source_method_id"),
            "consolidation_card_count": (consolidation_report or {}).get("study_card_count", 0),
            "consolidation_example_count": (consolidation_report or {}).get("assigned_example_count", 0),
            "consolidation_selected_example_count": (consolidation_report or {}).get("selected_example_count", 0),
            "consolidation_non_study_count": (consolidation_report or {}).get("non_study_disposition_count", 0),
        },
        "evidence": {
            "source_ingest": (
                "direct immutable source, line-extraction, and optional alignment records"
                if source_ingest
                else "not included in this audit bundle"
            ),
            "normalization": "preserved claims from two immutable legacy evidence runs",
            "clean_processing": (
                "direct immutable tokenization and language-adapter normalization lineage"
                if process_output
                else "not included in this audit bundle"
            ),
            "routing": (
                "direct policy evaluation with a per-word trace and pinned legacy snapshot comparison"
                if direct_routing
                else "route records against an explicitly pinned migration snapshot"
                if process_output
                else "reconstructed lookup against the current materialized word_routing.json"
            ),
            "lexical_menu": (
                "direct provider-neutral menu candidates; lookup identity remains separate from surface identity"
                if lexical_output
                else "not included in this audit bundle"
            ),
            "wsd": (
                "complete imported occurrence-level results from one exact method and asset set; no historical assignment fallback"
                if wsd_results_output
                else "complete immutable request coverage; execution status is not_run and no sense assignments exist"
                if wsd_prepare_output
                else "not included in this audit bundle"
            ),
            "consolidation": (
                "direct lossless surface-card grouping with explicit study selection and non-study dispositions"
                if consolidation_output
                else "not included in this audit bundle"
            ),
            "app_assignments": "current materialized immutable Artist release",
        },
        "limitations": limitations,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legacy-artist-root", type=Path, required=True)
    parser.add_argument("--release-root", type=Path, required=True)
    parser.add_argument("--song-id", required=True)
    parser.add_argument("--baseline-run", required=True)
    parser.add_argument("--candidate-run", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-ingest", type=Path)
    parser.add_argument("--process-output", type=Path)
    parser.add_argument("--lexical-output", type=Path)
    parser.add_argument("--wsd-prepare-output", type=Path)
    parser.add_argument("--wsd-results-output", type=Path)
    parser.add_argument("--consolidation-output", type=Path)
    args = parser.parse_args()
    bundle = build_bundle(
        legacy_artist_root=args.legacy_artist_root,
        release_root=args.release_root,
        song_id=args.song_id,
        baseline_run=args.baseline_run,
        candidate_run=args.candidate_run,
        source_ingest=args.source_ingest,
        process_output=args.process_output,
        lexical_output=args.lexical_output,
        wsd_prepare_output=args.wsd_prepare_output,
        wsd_results_output=args.wsd_results_output,
        consolidation_output=args.consolidation_output,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(bundle, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    print(f"Built lyrics audit bundle: {args.output}")


if __name__ == "__main__":
    main()
