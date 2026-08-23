"""Build provider-neutral lexical candidates for routed Lyrics analysis units."""

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
from fluency.core.identity import build_card_id, create_card_record
from fluency.core.workspace import Workspace
from fluency.lyrics.lineage import build_lineage_event
from fluency.release.io import atomic_write, json_bytes
from fluency.sense_menu.config import load_sense_menu_language_policy
from fluency.sense_menu.kaikki import ADAPTER_ID as KAIKKI_ADAPTER_ID, KaikkiSenseMenuAdapter
from fluency.sense_menu.spanishdict import ADAPTER_ID as SPANISHDICT_ADAPTER_ID, SpanishDictSenseMenuAdapter


STAGE_VERSION = "lyrics-lexical-menu-stage/v1"
RECORD_VERSION = "lyrics-lexical-candidate/v1"


class LyricsLexicalMenuError(ValueError):
    """Raised when lexical-menu inputs are incomplete, mutable, or mismatched."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LyricsLexicalMenuError(f"required JSON is unavailable or invalid: {path}") from error
    if not isinstance(value, dict):
        raise LyricsLexicalMenuError(f"required JSON must contain an object: {path}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    except (OSError, json.JSONDecodeError) as error:
        raise LyricsLexicalMenuError(f"required JSONL is unavailable or invalid: {path}") from error


def _jsonl_bytes(records: list[dict[str, Any]]) -> bytes:
    return b"".join(json_bytes(record) for record in records)


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _lookup_disposition(route: dict[str, Any], normalized_form: str) -> tuple[str, str | None, str]:
    if route["status"] == "excluded":
        return "ineligible", None, "route_excluded"
    if route["bucket"] == "review.proper_noun_candidate":
        return "review", None, "proper_noun_review_required"
    if route["status"] == "unresolved":
        return "no_menu", normalized_form, "unresolved_route_lookup"
    target = route.get("target")
    if isinstance(target, str) and target:
        return "lookup", target, "route_target_lookup"
    return "lookup", normalized_form, "normalized_surface_lookup"


def validate_lexical_candidate(record: dict[str, Any]) -> None:
    required = {
        "record_version", "lexical_candidate_id", "analysis_unit_id", "occurrence_id",
        "language", "surface_form", "normalized_form", "surface_card_id", "route_id",
        "route_bucket", "status", "lookup_form", "lookup_card_id", "provider",
        "analyses", "reason_codes", "input_artifact_ids",
    }
    if set(record) != required:
        raise LyricsLexicalMenuError("lexical candidate fields do not match the v1 contract")
    if record["record_version"] != RECORD_VERSION:
        raise LyricsLexicalMenuError("unsupported lexical candidate version")
    if record["status"] not in {"ready", "no_menu", "ineligible", "review"}:
        raise LyricsLexicalMenuError("invalid lexical candidate status")
    provider_fields = {
        "source_adapter", "source_edition", "snapshot_id", "snapshot_content_id", "gloss_language",
    }
    if not isinstance(record["provider"], dict) or set(record["provider"]) != provider_fields:
        raise LyricsLexicalMenuError("lexical provider fields do not match the v1 contract")
    if record["surface_card_id"] != build_card_id(record["language"], record["normalized_form"]):
        raise LyricsLexicalMenuError("surface card identity must be derived from the normalized surface")
    if record["status"] in {"ineligible", "review"}:
        if record["lookup_form"] is not None or record["lookup_card_id"] is not None or record["analyses"]:
            raise LyricsLexicalMenuError("non-lookup candidates cannot contain invented menu data")
    if record["status"] == "ready" and not record["analyses"]:
        raise LyricsLexicalMenuError("ready lexical candidates require analyses")
    if record["status"] in {"ready", "no_menu"}:
        if not record["lookup_form"] or record["lookup_card_id"] != build_card_id(
            record["language"], record["lookup_form"]
        ):
            raise LyricsLexicalMenuError("lookup candidates require a valid, separate lookup identity")
    if record["status"] == "no_menu" and record["analyses"]:
        raise LyricsLexicalMenuError("no-menu candidates cannot contain analyses")
    for analysis in record["analyses"]:
        if not isinstance(analysis, dict):
            raise LyricsLexicalMenuError("lexical analyses must be objects")
        if not all(key in analysis for key in ("menu_analysis_id", "headword", "lemma", "part_of_speech", "senses")):
            raise LyricsLexicalMenuError("lexical analysis is incomplete")


def build_lexical_candidate_records(
    *,
    run_id: str,
    language: str,
    units: list[dict[str, Any]],
    routes: list[dict[str, Any]],
    menu: dict[str, Any],
    process_input_ids: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Join exact route records to a provider menu without WSD or guessing."""

    routes_by_unit = {route["analysis_unit_id"]: route for route in routes}
    if len(routes_by_unit) != len(routes):
        raise LyricsLexicalMenuError("route decisions must be unique by analysis unit")
    if menu.get("language") != language:
        raise LyricsLexicalMenuError("provider menu language does not match the Lyrics run")
    cards_by_surface = {card["surface_form"]: card for card in menu.get("cards", [])}
    provider = {
        "source_adapter": menu["source_adapter"],
        "source_edition": menu["source_edition"],
        "snapshot_id": menu["snapshot_id"],
        "snapshot_content_id": menu["snapshot_content_id"],
        "gloss_language": menu["gloss_language"],
    }
    records: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    statuses: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()

    for unit in units:
        route = routes_by_unit.get(unit["analysis_unit_id"])
        if route is None:
            raise LyricsLexicalMenuError(f"analysis unit has no exact route: {unit['analysis_unit_id']}")
        disposition, lookup_form, lookup_reason = _lookup_disposition(route, unit["normalized_form"])
        lookup_card_id = build_card_id(language, lookup_form) if lookup_form is not None else None
        card = cards_by_surface.get(lookup_form) if lookup_form is not None else None
        raw_analyses = card.get("analyses", []) if isinstance(card, dict) else []
        analyses = [
            {
                "menu_analysis_id": analysis["menu_analysis_id"],
                "headword": analysis.get("headword"),
                "lemma": None,
                "part_of_speech": analysis.get("part_of_speech"),
                "source_analysis_key": analysis.get("source_analysis_key"),
                "senses": analysis.get("senses", []),
                "provider_metadata": analysis.get("provider_metadata", {}),
            }
            for analysis in raw_analyses
        ]
        if disposition in {"ineligible", "review"}:
            status = disposition
            analyses = []
        elif analyses:
            status = "ready"
        else:
            status = "no_menu"
        reasons = [lookup_reason]
        if status == "no_menu":
            reasons.append("provider_menu_unavailable")
        candidate_id = "lexical_" + canonical_content_id(
            [RECORD_VERSION, run_id, unit["analysis_unit_id"], route["route_id"], menu["snapshot_content_id"]]
        ).removeprefix("sha256:")[:32]
        input_ids = list(dict.fromkeys([
            *process_input_ids,
            *route.get("input_artifact_ids", []),
            menu["snapshot_content_id"],
        ]))
        record = {
            "record_version": RECORD_VERSION,
            "lexical_candidate_id": candidate_id,
            "analysis_unit_id": unit["analysis_unit_id"],
            "occurrence_id": unit["occurrence_id"],
            "language": language,
            "surface_form": unit["source_surface"],
            "normalized_form": unit["normalized_form"],
            "surface_card_id": build_card_id(language, unit["normalized_form"]),
            "route_id": route["route_id"],
            "route_bucket": route["bucket"],
            "status": status,
            "lookup_form": lookup_form,
            "lookup_card_id": lookup_card_id,
            "provider": provider,
            "analyses": analyses,
            "reason_codes": reasons,
            "input_artifact_ids": input_ids,
        }
        validate_lexical_candidate(record)
        records.append(record)
        statuses[status] += 1
        reason_counts.update(reasons)
        events.append(
            build_lineage_event(
                subject={"kind": "analysis_unit", "id": unit["analysis_unit_id"]},
                phase="menu",
                operation="lookup" if lookup_form is not None else "abstain",
                run_id=run_id,
                method_id=menu["source_adapter"],
                input_refs=[
                    {"kind": "analysis_unit", "id": unit["analysis_unit_id"]},
                    {"kind": "route_decision", "id": route["route_id"]},
                    {"kind": "dictionary_snapshot", "id": menu["snapshot_content_id"], "content_id": menu["snapshot_content_id"]},
                ],
                output_refs=[{"kind": "lexical_candidate", "id": candidate_id}],
                evidence_kind="direct",
                decision={
                    "status": status,
                    "lookup_form": lookup_form,
                    "analysis_count": len(analyses),
                },
                reason_codes=reasons,
                language_adapter=menu["source_adapter"],
            )
        )
    report = {
        "report_version": "lyrics-lexical-menu-report/v1",
        "language": language,
        "analysis_unit_count": len(units),
        "candidate_count": len(records),
        "status_counts": dict(sorted(statuses.items())),
        "reason_counts": dict(sorted(reason_counts.items())),
        "ready_analysis_count": sum(len(record["analyses"]) for record in records),
        "ready_sense_count": sum(
            len(analysis["senses"])
            for record in records
            for analysis in record["analyses"]
        ),
        "provider": provider,
        "wsd_status": "not_run",
    }
    return records, events, report


def build_lyrics_lexical_menu_stage(
    repository_root: Path,
    workspace: Workspace,
    *,
    run_id: str,
    language: str,
    dictionary_snapshot: Path,
    snapshot_id: str,
    language_policy_id: str,
    started_at: datetime | None = None,
) -> Path:
    """Build an immutable lexical-menu layer after clean Lyrics routing."""

    run_directory = workspace.root / "runs" / language / "lyrics" / run_id
    run_manifest_path = run_directory / "manifest.json"
    run_manifest = _read_json(run_manifest_path)
    if run_manifest.get("run_id") != run_id or run_manifest.get("language") != language or run_manifest.get("mode") != "lyrics":
        raise LyricsLexicalMenuError("lyrics run identity does not match the requested lexical menu")
    process_output = run_directory / "stages" / "02_process" / "output"
    process_manifest = _read_json(process_output / "manifest.json")
    if process_manifest.get("run_id") != run_id or process_manifest.get("stage") != "process":
        raise LyricsLexicalMenuError("processing manifest does not belong to this Lyrics run")
    for name in ("analysis-units.jsonl", "routes.jsonl"):
        if file_content_id(process_output / name) != process_manifest.get("outputs", {}).get(name):
            raise LyricsLexicalMenuError(f"processing artifact changed after completion: {name}")
    output_directory = run_directory / "stages" / "03_lexical_menu" / "output"
    if output_directory.exists():
        raise LyricsLexicalMenuError("lexical-menu output already exists; create a new run instead of overwriting it")
    resolved_snapshot = dictionary_snapshot.expanduser().resolve()
    if not _inside(resolved_snapshot, workspace.root / "raw"):
        raise LyricsLexicalMenuError("dictionary snapshot must be inside the workspace raw directory")
    policy = load_sense_menu_language_policy(
        repository_root,
        policy_id=language_policy_id,
        language=language,
    )
    if policy["provider"] == "spanishdict":
        adapter = SpanishDictSenseMenuAdapter(
            resolved_snapshot,
            language_code=language,
            gloss_language="en",
            source_edition="spanishdict-pinned-snapshot",
            language_policy=policy,
        )
    elif policy["provider"] == "wiktionary":
        adapter = KaikkiSenseMenuAdapter(
            resolved_snapshot,
            language_code=language,
            gloss_language="en",
            source_edition="kaikki-pinned-snapshot",
            language_policy=policy,
        )
    else:
        raise LyricsLexicalMenuError(f"unsupported menu provider: {policy['provider']}")
    units = _read_jsonl(process_output / "analysis-units.jsonl")
    routes = _read_jsonl(process_output / "routes.jsonl")
    routes_by_unit = {route["analysis_unit_id"]: route for route in routes}
    if len(routes_by_unit) != len(routes):
        raise LyricsLexicalMenuError("route decisions must be unique by analysis unit")
    lookup_forms: set[str] = set()
    for unit in units:
        route = routes_by_unit.get(unit["analysis_unit_id"])
        if route is None:
            raise LyricsLexicalMenuError(f"analysis unit has no exact route: {unit['analysis_unit_id']}")
        disposition, lookup_form, _reason = _lookup_disposition(route, unit["normalized_form"])
        if disposition not in {"ineligible", "review"} and lookup_form is not None:
            lookup_forms.add(lookup_form)
    cards = [create_card_record(language, form).to_dict() for form in sorted(lookup_forms)]
    menu, provider_report = adapter.build(cards, snapshot_id=snapshot_id)
    process_input_ids = [
        process_manifest["outputs"]["analysis-units.jsonl"],
        process_manifest["outputs"]["routes.jsonl"],
    ]
    records, events, report = build_lexical_candidate_records(
        run_id=run_id,
        language=language,
        units=units,
        routes=routes,
        menu=menu,
        process_input_ids=process_input_ids,
    )
    report["provider_report"] = provider_report
    started_at = datetime.now(UTC) if started_at is None else started_at.astimezone(UTC)
    temporary_root = workspace.root / ".fluency" / "temporary"
    temporary_root.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix="lyrics-lexical-", dir=temporary_root))
    try:
        (temporary / "lexical-candidates.jsonl").write_bytes(_jsonl_bytes(records))
        (temporary / "sense-menu.json").write_bytes(json_bytes(menu))
        (temporary / "lineage.jsonl").write_bytes(_jsonl_bytes(events))
        (temporary / "report.json").write_bytes(json_bytes(report))
        output_names = ("lexical-candidates.jsonl", "sense-menu.json", "lineage.jsonl", "report.json")
        outputs = {name: file_content_id(temporary / name) for name in output_names}
        manifest = {
            "manifest_version": STAGE_VERSION,
            "run_id": run_id,
            "stage": "lexical_menu",
            "status": "complete",
            "started_at": started_at.isoformat().replace("+00:00", "Z"),
            "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "method_id": menu["source_adapter"],
            "implementation_content_id": canonical_content_id({
                "lexical": file_content_id(Path(__file__)),
                "menu_contract": file_content_id(repository_root / "src/fluency/wsd/menus.py"),
                "menu_adapter": file_content_id(
                    repository_root
                    / "src/fluency/sense_menu"
                    / ("spanishdict.py" if menu["source_adapter"] == SPANISHDICT_ADAPTER_ID else "kaikki.py")
                ),
                "language_policy": file_content_id(
                    repository_root / "config/sense_menu/languages" / f"{language_policy_id}.json"
                ),
            }),
            "inputs": {
                "analysis_units": process_input_ids[0],
                "routes": process_input_ids[1],
                "dictionary_snapshot": menu["snapshot_content_id"],
                "language_policy": canonical_content_id(policy),
            },
            "outputs": outputs,
        }
        (temporary / "manifest.json").write_bytes(json_bytes(manifest))
        output_directory.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temporary, output_directory)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    stages = dict(run_manifest.get("stages", {}))
    stages["lexical_menu"] = {
        "path": "stages/03_lexical_menu/output",
        "manifest_content_id": file_content_id(output_directory / "manifest.json"),
    }
    run_manifest["stages"] = stages
    atomic_write(run_manifest_path, run_manifest, temporary_root)
    return output_directory
