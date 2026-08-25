"""Execute the immutable sentence-harvest stage for one planned run."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

from fluency.core.canonical_json import canonical_json
from fluency.core.hashing import canonical_content_id, file_content_id
from fluency.core.manifests import StageManifest, build_stage_cache_key
from fluency.core.workspace import Workspace
from fluency.pipeline.budget import display_examples_per_card, wsd_budget_per_card
from fluency.harvest.config import load_harvest_policies
from fluency.harvest.inventory import load_frequency_ranks, load_harvest_inventory
from fluency.harvest.matching import SurfaceMatcher, easiness_metrics, quality_rejection
from fluency.harvest.records import HarvestRecordError, validate_parallel_sentence
from fluency.harvest.sources import (
    CorpusAdapter,
    OpenSubtitlesAdapter,
    RetainedSentenceBankAdapter,
    TatoebaAdapter,
)
from fluency.pipeline.planning import load_pipeline_profile
from fluency.release.io import atomic_write, json_bytes


STAGE_VERSION = "sentence-harvest/v1"
CANDIDATES_VERSION = "harvest-candidates/v1"
REPORT_VERSION = "harvest-report/v1"
STAGE_RELATIVE = Path("stages/03_sentence_harvest")
INVENTORY_RELATIVE = Path("stages/01_inventory/output/inventory.json")
FREQUENCY_RELATIVE = Path("stages/01_inventory/output/frequency-ranks.json")


class HarvestRunError(ValueError):
    """Raised when a run cannot be harvested without ambiguity or fallback."""


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise HarvestRunError(f"required run artifact does not exist: {path}") from error
    except json.JSONDecodeError as error:
        raise HarvestRunError(f"run artifact is not valid JSON: {path}") from error
    if not isinstance(value, dict):
        raise HarvestRunError(f"run artifact must contain an object: {path}")
    return value


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _implementation_content_id() -> str:
    package = Path(__file__).resolve().parent
    paths = (
        Path(__file__).resolve(),
        package / "matching.py",
        package / "records.py",
        package / "sources" / "opensubtitles.py",
        package / "sources" / "retained.py",
        package / "sources" / "tatoeba.py",
    )
    return canonical_content_id(
        {str(path.relative_to(package)): file_content_id(path) for path in paths}
    )


def _trim_candidates(
    candidates: dict[str, dict[str, dict[str, Any]]],
    *,
    cap: int,
) -> None:
    for card_id, by_sentence in candidates.items():
        if len(by_sentence) <= cap:
            continue
        retained = sorted(
            by_sentence.values(),
            key=lambda item: (item["metrics"]["score"], item["sentence_id"]),
        )[:cap]
        candidates[card_id] = {item["sentence_id"]: item for item in retained}


def _adapter_for(
    source_policy: dict[str, Any],
    path: Path,
    *,
    language: str,
) -> CorpusAdapter:
    adapter = source_policy["adapter"]
    if adapter == "tatoeba-weekly/v1":
        return TatoebaAdapter(path=path, target_language=language, policy=source_policy)
    if adapter == "opensubtitles-aligned/v1":
        return OpenSubtitlesAdapter(
            path=path, target_language=language, policy=source_policy
        )
    if adapter == "retained-sentence-bank/v1":
        return RetainedSentenceBankAdapter(
            path=path, target_language=language, policy=source_policy
        )
    raise HarvestRunError(f"no installed harvesting adapter for {adapter!r}")


def harvest_run_stage(
    repository_root: Path,
    workspace: Workspace,
    *,
    run_id: str,
    language: str,
    mode: str,
    source_snapshots: dict[str, Path],
    started_at: datetime | None = None,
) -> Path:
    """Harvest explicit raw snapshots into a run-owned, content-hashed candidate pool."""

    started_at = datetime.now(UTC) if started_at is None else started_at
    run_directory = workspace.root / "runs" / language / mode / run_id
    manifest_path = run_directory / "manifest.json"
    run_manifest = _load_object(manifest_path)
    if (
        run_manifest.get("run_id") != run_id
        or run_manifest.get("language") != language
        or run_manifest.get("mode") != mode
    ):
        raise HarvestRunError("run identity does not match the requested harvest")
    profile = load_pipeline_profile(run_directory / "profile.json")
    if profile["language"] != language or profile["mode"] != mode:
        raise HarvestRunError("run profile language or mode does not match")

    shared, language_policy, source_policies, config_content_id = load_harvest_policies(
        repository_root, profile
    )
    selected_sources = profile["harvest"]["sources"]
    if set(source_snapshots) != set(selected_sources):
        raise HarvestRunError(
            "source snapshots must exactly match the profile; no fallback or implicit union is allowed"
        )
    raw_root = workspace.root / "raw"
    normalized_snapshots: dict[str, Path] = {}
    for source, path in source_snapshots.items():
        resolved = path.expanduser().resolve()
        if not _inside(resolved, raw_root):
            raise HarvestRunError(
                f"source snapshot must be inside the workspace raw directory: {resolved}"
            )
        normalized_snapshots[source] = resolved

    output_directory = run_directory / STAGE_RELATIVE / "output"
    if output_directory.exists():
        raise HarvestRunError(
            "sentence-harvest output already exists; create a new run instead of overwriting it"
        )
    cards, inventory_content_id = load_harvest_inventory(
        run_directory / INVENTORY_RELATIVE,
        expected_language=language,
        expected_count=profile["scope"]["surface_limit"],
    )
    raw_ranks, frequency_content_id = load_frequency_ranks(
        run_directory / FREQUENCY_RELATIVE
    )
    matcher = SurfaceMatcher(cards, language_policy)
    frequency_ranks: dict[str, int] = {}
    for token, rank in raw_ranks.items():
        normalized = matcher.normalize(token)
        frequency_ranks[normalized] = min(rank, frequency_ranks.get(normalized, rank))

    cap = wsd_budget_per_card(profile["harvest"])
    candidates: dict[str, dict[str, dict[str, Any]]] = {
        card["card_id"]: {} for card in cards
    }
    sentence_records: dict[str, dict[str, Any]] = {}
    # Every distinct sentence that ever matched a card, counted before the
    # budget trims it. Without this the funnel is unreadable per card: the
    # report only ever showed the number that SURVIVED the cut.
    matched_per_card: Counter[str] = Counter()
    rejections: Counter[str] = Counter()
    matched_records = 0
    accepted_matches = 0
    adapters: list[CorpusAdapter] = []

    policies_by_source = {policy["source"]: policy for policy in source_policies}
    for source in selected_sources:
        adapter = _adapter_for(
            policies_by_source[source],
            normalized_snapshots[source],
            language=language,
        )
        adapters.append(adapter)
        for record in adapter.iter_records():
            try:
                validate_parallel_sentence(
                    record,
                    target_language=language,
                    provenance_policy=shared["provenance"],
                )
            except HarvestRecordError as error:
                rejections[f"invalid_provenance:{error}"] += 1
                continue
            matched_cards = matcher.find_cards(record["target"]["text"])
            if not matched_cards:
                rejections["no_inventory_surface"] += 1
                continue
            matched_records += 1
            reason = quality_rejection(
                record["target"]["text"],
                record["translation"]["text"],
                matcher=matcher,
                shared_policy=shared,
            )
            if reason is not None:
                rejections[reason] += 1
                continue
            sentence_records[record["sentence_id"]] = record
            for card in matched_cards:
                metrics = easiness_metrics(
                    record["target"]["text"],
                    card,
                    matcher=matcher,
                    frequency_ranks=frequency_ranks,
                    shared_policy=shared,
                )
                candidate = {
                    "sentence_id": record["sentence_id"],
                    "metrics": metrics,
                }
                card_candidates = candidates[card["card_id"]]
                if record["sentence_id"] not in card_candidates:
                    card_candidates[record["sentence_id"]] = candidate
                    accepted_matches += 1
                    matched_per_card[card["card_id"]] += 1
                if len(card_candidates) > cap * 2:
                    _trim_candidates(candidates, cap=cap)

    _trim_candidates(candidates, cap=cap)
    live_sentence_ids = {
        sentence_id
        for by_sentence in candidates.values()
        for sentence_id in by_sentence
    }
    sentence_records = {
        sentence_id: sentence_records[sentence_id]
        for sentence_id in sorted(live_sentence_ids)
    }
    candidate_cards: list[dict[str, Any]] = []
    per_surface: list[dict[str, Any]] = []
    final_target = display_examples_per_card(profile["scope"])
    for card in cards:
        retained = sorted(
            candidates[card["card_id"]].values(),
            key=lambda item: (item["metrics"]["score"], item["sentence_id"]),
        )
        candidate_cards.append(
            {
                "card_id": card["card_id"],
                "surface_key": card["surface_key"],
                "display_form": card["display_form"],
                "rank": card["rank"],
                "candidates": retained,
            }
        )
        matched_before_budget = matched_per_card[card["card_id"]]
        per_surface.append(
            {
                "card_id": card["card_id"],
                "surface_key": card["surface_key"],
                "candidate_count": len(retained),
                "shortfall": max(0, final_target - len(retained)),
                # Funnel: how many sentences matched this card, how many the
                # per-card WSD budget discarded, and the rule that discarded them.
                "matched_before_budget": matched_before_budget,
                "discarded_by_budget": max(0, matched_before_budget - len(retained)),
                "budget_rule": f"wsd_budget_per_card={cap}",
                "display_rule": f"display_examples_per_card={final_target}",
            }
        )

    source_reports = [adapter.report() for adapter in adapters]
    candidate_payload = {
        "candidates_version": CANDIDATES_VERSION,
        "run_id": run_id,
        "language": language,
        "mode": mode,
        "source_policy": profile["harvest"]["source_policy"],
        "sources": selected_sources,
        "candidate_cap_per_surface": cap,
        "cards": candidate_cards,
    }
    report_payload = {
        "report_version": REPORT_VERSION,
        "run_id": run_id,
        "language": language,
        "source_policy": profile["harvest"]["source_policy"],
        "fallbacks": [],
        "sources": source_reports,
        "records_scanned": sum(report["rows_seen"] for report in source_reports),
        "records_with_inventory_match": matched_records,
        "accepted_matches_before_cap": accepted_matches,
        "retained_candidate_matches": sum(item["candidate_count"] for item in per_surface),
        "retained_sentences": len(sentence_records),
        "rejections": dict(sorted(rejections.items())),
        "surfaces_with_shortfall": sum(item["shortfall"] > 0 for item in per_surface),
        "release_blocked_by_shortfall": any(item["shortfall"] > 0 for item in per_surface),
        "per_surface": per_surface,
    }

    temporary_root = workspace.root / ".fluency" / "temporary"
    temporary = Path(tempfile.mkdtemp(prefix="sentence-harvest-", dir=temporary_root))
    try:
        (temporary / "candidates.json").write_bytes(json_bytes(candidate_payload))
        (temporary / "report.json").write_bytes(json_bytes(report_payload))
        with (temporary / "sentence-bank.jsonl").open("w", encoding="utf-8") as stream:
            for record in sentence_records.values():
                stream.write(canonical_json(record))
                stream.write("\n")

        inputs = {
            "inventory": inventory_content_id,
            "frequency_ranks": frequency_content_id,
            **{
                f"source_{source}": adapter.snapshot_content_id
                for source, adapter in zip(selected_sources, adapters, strict=True)
            },
        }
        implementation_content_id = _implementation_content_id()
        stage = StageManifest(
            stage_name="sentence_harvest",
            stage_version=STAGE_VERSION,
            cache_key=build_stage_cache_key(
                stage_name="sentence_harvest",
                stage_version=STAGE_VERSION,
                implementation_hash=implementation_content_id,
                config_hash=config_content_id,
                inputs=inputs,
                model_revisions={},
                random_seed=0,
            ),
            implementation_hash=implementation_content_id,
            config_hash=config_content_id,
            status="running",
            started_at=_timestamp(started_at),
            inputs=inputs,
            model_revisions={},
            random_seed=0,
            outputs={},
        ).complete(
            {
                "candidates": file_content_id(temporary / "candidates.json"),
                "report": file_content_id(temporary / "report.json"),
                "sentence_bank": file_content_id(temporary / "sentence-bank.jsonl"),
            }
        )
        stage_manifest = stage.to_dict()
        (temporary / "manifest.json").write_bytes(json_bytes(stage_manifest))
        output_directory.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temporary, output_directory)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)

    contract_path = run_directory / STAGE_RELATIVE / "contract.json"
    contract = _load_object(contract_path)
    contract["status"] = "complete"
    contract["completed_at"] = stage_manifest["completed_at"]
    contract["output_directory"] = "output"
    contract["manifest_content_id"] = file_content_id(output_directory / "manifest.json")
    atomic_write(contract_path, contract, temporary_root)

    run_manifest["status"] = "running"
    run_manifest["inputs"] = {
        **run_manifest.get("inputs", {}),
        **stage_manifest["inputs"],
    }
    atomic_write(manifest_path, run_manifest, temporary_root)
    return output_directory
