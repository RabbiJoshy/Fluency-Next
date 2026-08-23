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
RECORD_VERSION = "lyrics-lexical-candidate/v2"


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


def lexical_lookup_forms(
    units: list[dict[str, Any]], routes: list[dict[str, Any]]
) -> set[str]:
    """Return the exact provider lookup union implied by completed routes."""

    routes_by_unit = {route["analysis_unit_id"]: route for route in routes}
    if len(routes_by_unit) != len(routes):
        raise LyricsLexicalMenuError("route decisions must be unique by analysis unit")
    forms: set[str] = set()
    for unit in units:
        route = routes_by_unit.get(unit["analysis_unit_id"])
        if route is None:
            raise LyricsLexicalMenuError(
                f"analysis unit has no exact route: {unit['analysis_unit_id']}"
            )
        disposition, lookup_form, _reason = _lookup_disposition(
            route, unit["normalized_form"]
        )
        if disposition not in {"ineligible", "review"} and lookup_form is not None:
            forms.add(lookup_form)
    return forms


def build_provider_menu(
    repository_root: Path,
    *,
    language: str,
    dictionary_snapshot: Path,
    snapshot_id: str,
    language_policy_id: str,
    lookup_forms: set[str],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Load one provider snapshot and build a menu for an exact form union."""

    policy = load_sense_menu_language_policy(
        repository_root,
        policy_id=language_policy_id,
        language=language,
    )
    if policy["provider"] == "spanishdict":
        adapter = SpanishDictSenseMenuAdapter(
            dictionary_snapshot,
            language_code=language,
            gloss_language="en",
            source_edition="spanishdict-pinned-snapshot",
            language_policy=policy,
        )
    elif policy["provider"] == "wiktionary":
        adapter = KaikkiSenseMenuAdapter(
            dictionary_snapshot,
            language_code=language,
            gloss_language="en",
            source_edition="kaikki-pinned-snapshot",
            language_policy=policy,
        )
    else:
        raise LyricsLexicalMenuError(f"unsupported menu provider: {policy['provider']}")
    cards = [create_card_record(language, form).to_dict() for form in sorted(lookup_forms)]
    menu, report = adapter.build(cards, snapshot_id=snapshot_id)
    return menu, report, policy


def subset_provider_menu(
    menu: dict[str, Any],
    lookup_forms: set[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Create a compact per-song menu without rerunning the provider adapter."""

    cards_by_surface = {card.get("surface_form"): card for card in menu.get("cards", [])}
    missing = sorted(form for form in lookup_forms if form not in cards_by_surface)
    if missing:
        raise LyricsLexicalMenuError(
            f"prepared corpus menu is missing {len(missing)} requested forms; first={missing[0]!r}"
        )
    cards = [cards_by_surface[form] for form in sorted(lookup_forms)]
    subset = {key: value for key, value in menu.items() if key != "cards"}
    subset["cards"] = cards
    analysis_count = sum(len(card.get("analyses", [])) for card in cards)
    sense_count = sum(
        len(analysis.get("senses", []))
        for card in cards
        for analysis in card.get("analyses", [])
    )
    report = {
        "report_version": "sense-menu-subset-report/v1",
        "scope": "song_subset_from_corpus_menu",
        "inventory_cards": len(cards),
        "cards_ready": sum(bool(card.get("analyses")) for card in cards),
        "cards_without_menu": sum(not card.get("analyses") for card in cards),
        "analysis_count": analysis_count,
        "sense_count": sense_count,
        "snapshot_id": subset.get("snapshot_id"),
        "snapshot_content_id": subset.get("snapshot_content_id"),
        "source_adapter": subset.get("source_adapter"),
    }
    return subset, report


def lexical_implementation_content_id(
    repository_root: Path,
    *,
    language_policy_id: str,
    source_adapter: str,
) -> str:
    adapter_name = "spanishdict.py" if source_adapter == SPANISHDICT_ADAPTER_ID else "kaikki.py"
    return canonical_content_id({
        "lexical": file_content_id(Path(__file__)),
        "lineage": file_content_id(Path(__file__).with_name("lineage.py")),
        "identity": file_content_id(repository_root / "src/fluency/core/identity.py"),
        "menu_contract": file_content_id(repository_root / "src/fluency/wsd/menus.py"),
        "candidate_contract": file_content_id(
            repository_root / "schemas/lyrics-lexical-candidate.schema.json"
        ),
        "menu_adapter": file_content_id(
            repository_root / "src/fluency/sense_menu" / adapter_name
        ),
        "language_policy": file_content_id(
            repository_root / "config/sense_menu/languages" / f"{language_policy_id}.json"
        ),
    })


def index_menu_analyses(menu: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Index the authoritative menu once by stable lookup-card identity."""

    result: dict[str, list[dict[str, Any]]] = {}
    for card in menu.get("cards", []):
        card_id = card.get("card_id")
        analyses = card.get("analyses")
        if not isinstance(card_id, str) or not isinstance(analyses, list) or card_id in result:
            raise LyricsLexicalMenuError("sense menu contains an invalid or duplicate card")
        result[card_id] = analyses
    return result


def resolve_candidate_analyses(
    candidate: dict[str, Any], analyses_by_card: dict[str, list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    """Resolve and verify a compact candidate against its exact authoritative menu."""

    if candidate.get("status") != "ready":
        return []
    analyses = analyses_by_card.get(candidate.get("lookup_card_id"))
    if analyses is None:
        raise LyricsLexicalMenuError("ready lexical candidate lost its lookup menu")
    analysis_ids = [analysis.get("menu_analysis_id") for analysis in analyses]
    sense_count = sum(len(analysis.get("senses", [])) for analysis in analyses)
    if (
        analysis_ids != candidate.get("menu_analysis_ids")
        or len(analyses) != candidate.get("menu_analysis_count")
        or sense_count != candidate.get("menu_sense_count")
    ):
        raise LyricsLexicalMenuError("lexical candidate menu reference no longer matches its menu")
    return analyses


def validate_lexical_candidate(record: dict[str, Any]) -> None:
    required = {
        "record_version", "lexical_candidate_id", "analysis_unit_id", "occurrence_id",
        "language", "surface_form", "normalized_form", "surface_card_id", "route_id",
        "route_bucket", "status", "lookup_form", "lookup_card_id", "provider",
        "menu_analysis_ids", "menu_analysis_count", "menu_sense_count",
        "reason_codes", "input_artifact_ids",
    }
    if set(record) != required:
        raise LyricsLexicalMenuError("lexical candidate fields do not match the v2 contract")
    if record["record_version"] != RECORD_VERSION:
        raise LyricsLexicalMenuError("unsupported lexical candidate version")
    if record["status"] not in {"ready", "no_menu", "ineligible", "review"}:
        raise LyricsLexicalMenuError("invalid lexical candidate status")
    provider_fields = {
        "source_adapter", "source_edition", "snapshot_id", "snapshot_content_id", "gloss_language",
    }
    if not isinstance(record["provider"], dict) or set(record["provider"]) != provider_fields:
        raise LyricsLexicalMenuError("lexical provider fields do not match the v2 contract")
    if record["surface_card_id"] != build_card_id(record["language"], record["normalized_form"]):
        raise LyricsLexicalMenuError("surface card identity must be derived from the normalized surface")
    if record["status"] in {"ineligible", "review"}:
        if (
            record["lookup_form"] is not None
            or record["lookup_card_id"] is not None
            or record["menu_analysis_ids"]
            or record["menu_analysis_count"]
            or record["menu_sense_count"]
        ):
            raise LyricsLexicalMenuError("non-lookup candidates cannot contain invented menu data")
    if record["status"] == "ready" and not record["menu_analysis_ids"]:
        raise LyricsLexicalMenuError("ready lexical candidates require analyses")
    if record["status"] in {"ready", "no_menu"}:
        if not record["lookup_form"] or record["lookup_card_id"] != build_card_id(
            record["language"], record["lookup_form"]
        ):
            raise LyricsLexicalMenuError("lookup candidates require a valid, separate lookup identity")
    if record["status"] == "no_menu" and (
        record["menu_analysis_ids"] or record["menu_analysis_count"] or record["menu_sense_count"]
    ):
        raise LyricsLexicalMenuError("no-menu candidates cannot contain analyses")
    if (
        not isinstance(record["menu_analysis_ids"], list)
        or not all(isinstance(value, str) and value for value in record["menu_analysis_ids"])
        or record["menu_analysis_count"] != len(record["menu_analysis_ids"])
        or not isinstance(record["menu_sense_count"], int)
        or record["menu_sense_count"] < 0
    ):
        raise LyricsLexicalMenuError("lexical menu reference counts are invalid")


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
        analyses = raw_analyses
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
            "menu_analysis_ids": [analysis["menu_analysis_id"] for analysis in analyses],
            "menu_analysis_count": len(analyses),
            "menu_sense_count": sum(len(analysis.get("senses", [])) for analysis in analyses),
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
        "ready_analysis_count": sum(record["menu_analysis_count"] for record in records),
        "ready_sense_count": sum(record["menu_sense_count"] for record in records),
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
    _prepared_menu: dict[str, Any] | None = None,
    _prepared_policy: dict[str, Any] | None = None,
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
    units = _read_jsonl(process_output / "analysis-units.jsonl")
    routes = _read_jsonl(process_output / "routes.jsonl")
    lookup_forms = lexical_lookup_forms(units, routes)
    if _prepared_menu is None:
        menu, provider_report, policy = build_provider_menu(
            repository_root,
            language=language,
            dictionary_snapshot=resolved_snapshot,
            snapshot_id=snapshot_id,
            language_policy_id=language_policy_id,
            lookup_forms=lookup_forms,
        )
    else:
        menu, provider_report = subset_provider_menu(_prepared_menu, lookup_forms)
        policy = _prepared_policy
        if (
            not isinstance(policy, dict)
            or menu.get("language") != language
            or menu.get("snapshot_id") != snapshot_id
        ):
            raise LyricsLexicalMenuError("prepared corpus menu does not match this run")
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
            "implementation_content_id": lexical_implementation_content_id(
                repository_root,
                language_policy_id=language_policy_id,
                source_adapter=menu["source_adapter"],
            ),
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
