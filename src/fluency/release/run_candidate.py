"""Build an inactive real-data Speech candidate, using WSD assignments if present.

WSD remains optional: the French demonstration has no assignment stage and must
still build, so a missing stage 04 leaves every example explicitly `unassigned`
rather than failing. Where stage 04 exists, its assignments are attached here.

A multiword sense is not in the provider menu, so a card whose example was
assigned to one gains a meaning row for it, marked with its own source. That is
the intended placement: the expression lands on the component word's card via
the occurrence that was selected as evidence, and card identity is untouched.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

from fluency.core.artifacts import verify_artifact
from fluency.core.hashing import canonical_content_id, file_content_id
from fluency.core.manifests import StageManifest, build_stage_cache_key
from fluency.core.workspace import Workspace
from fluency.pipeline.planning import load_pipeline_profile
from fluency.release.composition import compose_release
from fluency.release.io import atomic_write, json_bytes
from fluency.release.study_structure import build_study_structure
from fluency.release.validation import SPEECH_DECK_VERSION


SELECTION_VERSION = "example-selection/v1"
POLICY_VERSION = "harvest-easiness-order/v1"


class RunCandidateError(ValueError):
    """Raised when an exact real-data candidate cannot be assembled."""


def _object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as error:
        raise RunCandidateError(f"invalid or missing run artifact: {path}") from error
    if not isinstance(value, dict):
        raise RunCandidateError(f"run artifact must be an object: {path}")
    return value


def _sentence_bank(path: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as error:
        raise RunCandidateError(f"missing sentence bank: {path}") from error
    for number, line in enumerate(lines, start=1):
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise RunCandidateError(f"invalid sentence-bank row {number}") from error
        sentence_id = record.get("sentence_id")
        if not isinstance(sentence_id, str) or sentence_id in records:
            raise RunCandidateError(f"invalid sentence identity at row {number}")
        records[sentence_id] = record
    return records


def _load_assignments(run: Path) -> dict[tuple[str, str], dict[str, Any]]:
    """Stage 04 keyed by (card_id, sentence_id); empty when WSD did not run."""

    path = run / "stages/04_wsd_assignments/output/assignments.jsonl"
    if not path.exists():
        return {}
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise RunCandidateError(f"invalid WSD assignment row {number}") from error
        card_id, sentence_id = row.get("card_id"), row.get("sentence_id")
        if not card_id or not sentence_id:
            raise RunCandidateError(f"WSD assignment row {number} lacks identity")
        rows[(card_id, sentence_id)] = row
    return rows


def _scoped_sense_id(card_id: str, analysis_id: str, source_sense_id: str) -> str:
    digest = canonical_content_id(
        {"card_id": card_id, "analysis_id": analysis_id, "source_sense_id": source_sense_id}
    ).removeprefix("sha256:")
    return f"sense_{digest[:32]}"


def _example_id(card_id: str, sentence_id: str) -> str:
    digest = canonical_content_id(
        {"card_id": card_id, "sentence_id": sentence_id}
    ).removeprefix("sha256:")
    return f"example_{digest[:32]}"


def build_inactive_run_candidate(
    workspace: Workspace,
    *,
    run_id: str,
    release_id: str,
    language: str = "fr",
    mode: str = "speech",
    created_at: datetime | None = None,
    conjugations_artifact_id: str | None = None,
) -> Path:
    """Select harvested examples and compose a non-activated release."""

    created_at = datetime.now(UTC) if created_at is None else created_at
    existing_composition = (
        workspace.root / "releases" / language / mode / release_id / "composition.json"
    )
    if existing_composition.is_file():
        created_at = datetime.fromisoformat(
            _object(existing_composition)["created_at"].replace("Z", "+00:00")
        )
    run = workspace.root / "runs" / language / mode / run_id
    profile = load_pipeline_profile(run / "profile.json")
    if profile["language"] != language or profile["mode"] != mode:
        raise RunCandidateError("run profile identity mismatch")
    manifest = _object(run / "manifest.json")
    if manifest.get("run_id") != run_id:
        raise RunCandidateError("run manifest identity mismatch")

    paths = {
        "inventory": run / "stages/01_inventory/output/inventory.json",
        "sense_menu": run / "stages/02_sense_menu/output/sense-menu.json",
        "candidates": run / "stages/03_sentence_harvest/output/candidates.json",
        "sentence_bank": run / "stages/03_sentence_harvest/output/sentence-bank.jsonl",
    }
    inputs = {name: file_content_id(path) for name, path in paths.items()}
    inventory = _object(paths["inventory"])
    menus = _object(paths["sense_menu"])
    candidates = _object(paths["candidates"])
    sentences = _sentence_bank(paths["sentence_bank"])
    assignments = _load_assignments(run)
    if assignments:
        # Stage 04 becomes an input to the release, so a deck can be traced back
        # to the exact assignment set that produced it.
        inputs["wsd_assignments"] = file_content_id(
            run / "stages/04_wsd_assignments/output/assignments.jsonl"
        )
    menu_by_card = {card["card_id"]: card for card in menus.get("cards", [])}
    candidates_by_card = {card["card_id"]: card for card in candidates.get("cards", [])}
    limit = profile["scope"]["examples_per_surface"]
    menu_adapter = str(menus.get("source_adapter", ""))
    menu_provider = "spanishdict" if menu_adapter.startswith("spanishdict-") else "wiktionary"

    selection_cards: list[dict[str, Any]] = []
    cards: list[dict[str, Any]] = []
    selected_count = 0
    for card in inventory.get("cards", []):
        card_id = card["card_id"]
        candidate_card = candidates_by_card.get(card_id)
        menu_card = menu_by_card.get(card_id)
        if candidate_card is None or menu_card is None:
            raise RunCandidateError(f"run layers do not cover card {card_id}")
        selected = sorted(
            candidate_card.get("candidates", []),
            key=lambda item: (item["metrics"]["score"], item["sentence_id"]),
        )[:limit]
        selected_count += len(selected)
        selection_cards.append(
            {
                "card_id": card_id,
                "selected": [
                    {
                        "sentence_id": item["sentence_id"],
                        "selection_rank": rank,
                        "metrics": item["metrics"],
                    }
                    for rank, item in enumerate(selected, start=1)
                ],
            }
        )

        assigned_here = {
            key[1]: row
            for key, row in assignments.items()
            if key[0] == card_id and row.get("status") == "assigned"
        }
        assigned_scoped: set[str] = set()
        multiword_meanings: dict[str, dict[str, Any]] = {}

        meanings: list[dict[str, Any]] = []
        for analysis in menu_card.get("analyses", []):
            for sense in analysis.get("senses", []):
                source_sense_id = sense["sense_id"]
                meaning: dict[str, Any] = {
                    "sense_id": _scoped_sense_id(
                        card_id, analysis["menu_analysis_id"], source_sense_id
                    ),
                    "source_sense_id": source_sense_id,
                    "menu_analysis_id": analysis["menu_analysis_id"],
                    "headword": analysis["headword"],
                    "part_of_speech": analysis["part_of_speech"],
                    "translation": sense["translation"],
                    "source_reference": sense["source_reference"],
                    "source": menu_provider,
                    "assignment_status": "unassigned",
                    "metadata": {
                        "source_adapter": menu_adapter,
                        "source_edition": menus.get("source_edition"),
                        "source_analysis_key": analysis.get("source_analysis_key"),
                        "analysis_provider_metadata": analysis.get("provider_metadata", {}),
                        "sense_provider_metadata": sense.get("provider_metadata", {}),
                    },
                }
                if sense.get("definition"):
                    meaning["context"] = sense["definition"]
                meanings.append(meaning)

        # A meaning is "assigned" when at least one selected example was assigned
        # to it. Meanings nothing landed on stay explicitly unassigned rather
        # than being dropped -- the menu is what was offered, not what won.
        for sentence_id, row in assigned_here.items():
            scoped = _scoped_sense_id(
                card_id, row["menu_analysis_id"], row["selected_sense_id"]
            )
            assigned_scoped.add(scoped)
            if (row.get("evidence") or {}).get("selected_multiword") and scoped not in {
                item["sense_id"] for item in meanings
            }:
                expression = row["evidence"]["selected_multiword"]
                declared = next(
                    (
                        item
                        for item in (row.get("evidence") or {}).get("multiword_candidates", [])
                        if item.get("expression") == expression
                    ),
                    {},
                )
                multiword_meanings[scoped] = {
                    "sense_id": scoped,
                    "source_sense_id": row["selected_sense_id"],
                    "menu_analysis_id": row["menu_analysis_id"],
                    "headword": expression,
                    "part_of_speech": "PHRASE",
                    "translation": declared.get("translation") or expression,
                    "source_reference": "mwe-merged/v1",
                    "source": "mwe-merged",
                    "assignment_status": "assigned",
                    "context": "multiword expression",
                    "metadata": {
                        "source_adapter": "mwe-merged/v1",
                        "multiword_expression": expression,
                        "multiword_evidence": [
                            item
                            for item in (row.get("evidence") or {}).get("multiword_candidates", [])
                            if item.get("expression") == expression
                        ],
                    },
                }
        meanings.extend(multiword_meanings.values())
        for meaning in meanings:
            if meaning["sense_id"] in assigned_scoped:
                meaning["assignment_status"] = "assigned"

        examples: list[dict[str, Any]] = []
        for item in selected:
            sentence_id = item["sentence_id"]
            sentence = sentences.get(sentence_id)
            if sentence is None:
                raise RunCandidateError(f"selected sentence is absent: {sentence_id}")
            row = assigned_here.get(sentence_id)
            scoped_sense = (
                _scoped_sense_id(card_id, row["menu_analysis_id"], row["selected_sense_id"])
                if row
                else None
            )
            examples.append(
                {
                    "example_id": _example_id(card_id, sentence_id),
                    "sense_id": scoped_sense,
                    "assignment_status": "assigned" if row else "unassigned",
                    "target": sentence["target"]["text"],
                    "english": sentence["translation"]["text"],
                    "provenance": sentence["source"]["name"],
                    "source": sentence["source"]["name"],
                    "easiness": item["metrics"]["score"],
                    "metadata": {
                        "sentence_id": sentence_id,
                        "selection_policy": POLICY_VERSION,
                        "selection_metrics": item["metrics"],
                        "source": sentence["source"],
                        "target": sentence["target"],
                        "translation": sentence["translation"],
                    },
                }
            )
        cards.append({**card, "meanings": meanings, "examples": examples})

    selection = {
        "selection_version": SELECTION_VERSION,
        "policy": POLICY_VERSION,
        "run_id": run_id,
        "language": language,
        "mode": mode,
        "max_examples_per_surface": limit,
        "inputs": inputs,
        "cards": selection_cards,
    }
    selection_output = run / "stages/05_example_selection/output"
    selection_path = selection_output / "selection.json"
    temporary_root = workspace.root / ".fluency/temporary"
    if selection_path.exists():
        if selection_path.read_bytes() != json_bytes(selection):
            raise RunCandidateError("immutable example selection already differs")
    else:
        selection_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(selection_path, selection, temporary_root)
    report = {
        "report_version": "example-selection-report/v1",
        "run_id": run_id,
        "policy": POLICY_VERSION,
        "card_count": len(cards),
        "selected_example_count": selected_count,
        "cards_below_maximum": sum(
            len(item["selected"]) < limit for item in selection_cards
        ),
        "wsd_required": False,
        "fallbacks": [],
    }
    report_path = selection_output / "report.json"
    stage_manifest_path = selection_output / "manifest.json"
    if not report_path.exists():
        atomic_write(report_path, report, temporary_root)
    if not stage_manifest_path.exists():
        implementation_hash = canonical_content_id(
            {"run_candidate": file_content_id(Path(__file__).resolve())}
        )
        config_hash = canonical_content_id(
            {"policy": POLICY_VERSION, "max_examples_per_surface": limit}
        )
        stage = StageManifest(
            stage_name="example_selection",
            stage_version=SELECTION_VERSION,
            cache_key=build_stage_cache_key(
                stage_name="example_selection",
                stage_version=SELECTION_VERSION,
                implementation_hash=implementation_hash,
                config_hash=config_hash,
                inputs=inputs,
                model_revisions={},
                random_seed=0,
            ),
            implementation_hash=implementation_hash,
            config_hash=config_hash,
            status="running",
            started_at=created_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            inputs=inputs,
            model_revisions={},
            random_seed=0,
            outputs={},
        ).complete(
            {
                "selection": file_content_id(selection_path),
                "report": file_content_id(report_path),
            }
        )
        atomic_write(stage_manifest_path, stage.to_dict(), temporary_root)
        contract_path = run / "stages/05_example_selection/contract.json"
        contract = _object(contract_path)
        contract.update(
            {
                "status": "complete",
                "requires_stage_outputs": ["inventory", "sentence_harvest"],
                "acceptance": [
                    "up to three harvested examples selected per surface without requiring WSD",
                    "selection remains stable when optional WSD assignments are attached later",
                    "no fallback examples from another run",
                ],
                "decision_amendment": "wsd-optional-examples/v1",
                "manifest_content_id": file_content_id(stage_manifest_path),
            }
        )
        atomic_write(contract_path, contract, temporary_root)

    deck = {
        "deck_version": SPEECH_DECK_VERSION,
        "release_id": release_id,
        "language": language,
        "mode": mode,
        "study_structure": build_study_structure(
            cards, frequency_of=lambda item: 1_000_000 - item["rank"]
        ),
        "cards": cards,
    }
    selection_id = file_content_id(selection_path)
    layer = lambda name, count, requires: {
        "selection_version": "layer-selection/v1",
        "source_type": "run",
        "source_id": run_id,
        "artifact_id": inputs[name] if name in inputs else selection_id,
        "record_count": count,
        "requires": requires,
    }
    layers = {
        "inventory": layer("inventory", len(cards), {}),
        "sense_menu": layer("sense_menu", len(cards), {"inventory": inputs["inventory"]}),
        "sentences": layer("sentence_bank", len(sentences), {"inventory": inputs["inventory"]}),
        "example_selection": layer(
            "selection", selected_count,
            {"inventory": inputs["inventory"], "sentences": inputs["sentence_bank"]},
        ),
    }
    omitted_layers = [
        {"layer": "wsd_assignments", "reason": "not_connected_examples_explicitly_unassigned"},
        {"layer": "manual_overrides", "reason": "not_applied"},
    ]
    if conjugations_artifact_id is None:
        omitted_layers.append({"layer": "conjugations", "reason": "not_selected"})
    else:
        metadata = verify_artifact(workspace, conjugations_artifact_id)
        if metadata.schema != "conjugation-layer/v1":
            raise RunCandidateError("selected conjugations artifact has the wrong schema")
        layers["conjugations"] = {
            "selection_version": "layer-selection/v1",
            "source_type": "run",
            "source_id": run_id,
            "artifact_id": metadata.artifact_id,
            "record_count": metadata.row_count or 0,
            "requires": {"sense_menu": inputs["sense_menu"]},
        }
    composition = {
        "composition_version": "release-composition/v1",
        "release_id": release_id,
        "label": f"{profile['locale']} Speech · real-data audit · unassigned",
        "language": language,
        "locale": profile["locale"],
        "mode": mode,
        "created_at": created_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "publication_status": "inactive_audit",
        "progress_namespace": f"{language}-{mode}-next",
        "conflict_policy": "error",
        "fallback_policy": "none",
        "layers": layers,
        "omitted_layers": omitted_layers,
    }
    return compose_release(workspace, composition, deck)
