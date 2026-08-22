"""Build a prediction-blind, immutable French WSD benchmark from one run."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

from fluency.core.hashing import canonical_content_id, file_content_id
from fluency.core.workspace import Workspace
from fluency.release.io import json_bytes


BENCHMARK_VERSION = "wsd-gold-benchmark/v1"
MANIFEST_VERSION = "wsd-benchmark-manifest/v1"
SELECTION_VERSION = "fr-stratified-120/v1"
AUDIT_RELATIVE = Path("audits/wsd-benchmark-120")


class WSDBenchmarkError(ValueError):
    """Raised when a benchmark cannot be built without drift or prediction leakage."""


def _load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise WSDBenchmarkError(f"required benchmark input does not exist: {path}") from error
    except json.JSONDecodeError as error:
        raise WSDBenchmarkError(f"benchmark input is invalid JSON: {path}") from error
    if not isinstance(value, dict):
        raise WSDBenchmarkError(f"benchmark input must contain an object: {path}")
    return value


def _stable_key(*values: str) -> str:
    return hashlib.sha256("\0".join(values).encode("utf-8")).hexdigest()


def _stratum(card: dict[str, Any], rank: int) -> str | None:
    analyses = card.get("analyses")
    if not isinstance(analyses, list) or not analyses:
        return None
    leaf_count = sum(len(analysis.get("senses", [])) for analysis in analyses)
    if leaf_count < 2:
        return None
    if rank <= 60:
        return "function_homograph"
    headwords = {analysis.get("headword") for analysis in analyses}
    redirected = any(
        analysis.get("provider_metadata", {}).get("resolution") != "direct"
        for analysis in analyses
    )
    if redirected or len(headwords) > 1:
        return "inflected_multi_headword"
    return "ordinary_multi_sense"


def _review_analysis(analysis: dict[str, Any]) -> dict[str, Any]:
    provider = analysis.get("provider_metadata", {})
    senses: list[dict[str, Any]] = []
    for sense in analysis.get("senses", []):
        sense_provider = sense.get("provider_metadata", {})
        examples = []
        for example in sense_provider.get("examples", [])[:2]:
            if not isinstance(example, dict):
                continue
            examples.append(
                {
                    "text": example.get("text", ""),
                    "translation": example.get("translation") or example.get("english", ""),
                }
            )
        senses.append(
            {
                "sense_id": sense["sense_id"],
                "translation": sense.get("translation", ""),
                "definition": sense.get("definition", ""),
                "source_reference": sense.get("source_reference", ""),
                "tags": sense_provider.get("tags", []),
                "topics": sense_provider.get("topics", []),
                "examples": examples,
            }
        )
    return {
        "menu_analysis_id": analysis["menu_analysis_id"],
        "headword": analysis["headword"],
        "part_of_speech": analysis["part_of_speech"],
        "resolution": provider.get("resolution"),
        "resolution_path": provider.get("resolution_path", []),
        "senses": senses,
    }


def _pick_rows(
    inventory_cards: list[dict[str, Any]],
    menu_cards: list[dict[str, Any]],
    candidate_cards: list[dict[str, Any]],
    sentence_bank: dict[str, dict[str, Any]],
    *,
    per_stratum: int,
) -> list[dict[str, Any]]:
    inventory = {card["card_id"]: card for card in inventory_cards}
    candidates = {card["card_id"]: card for card in candidate_cards}
    pools: dict[str, list[dict[str, Any]]] = {
        "function_homograph": [],
        "inflected_multi_headword": [],
        "ordinary_multi_sense": [],
    }
    for menu_card in menu_cards:
        card_id = menu_card["card_id"]
        inventory_card = inventory.get(card_id)
        candidate_card = candidates.get(card_id)
        if inventory_card is None or candidate_card is None:
            raise WSDBenchmarkError(f"benchmark card is missing a joined layer: {card_id}")
        stratum = _stratum(menu_card, inventory_card["rank"])
        if stratum is None:
            continue
        choices = [
            candidate
            for candidate in candidate_card.get("candidates", [])
            if candidate.get("sentence_id") in sentence_bank
        ]
        if not choices:
            continue
        candidate = min(
            choices,
            key=lambda item: _stable_key(
                SELECTION_VERSION, card_id, item["sentence_id"]
            ),
        )
        sentence = sentence_bank[candidate["sentence_id"]]
        row_identity = canonical_content_id(
            {
                "selection_version": SELECTION_VERSION,
                "card_id": card_id,
                "sentence_id": sentence["sentence_id"],
            }
        ).removeprefix("sha256:")[:32]
        pools[stratum].append(
            {
                "benchmark_row_id": f"wsdrow_{row_identity}",
                "stratum": stratum,
                "card": {
                    "card_id": card_id,
                    "surface_form": menu_card["surface_form"],
                    "rank": inventory_card["rank"],
                },
                "sentence": sentence,
                "candidate_metrics": candidate["metrics"],
                "analyses": [
                    _review_analysis(analysis) for analysis in menu_card["analyses"]
                ],
            }
        )

    selected: list[dict[str, Any]] = []
    for stratum, pool in pools.items():
        if len(pool) < per_stratum:
            raise WSDBenchmarkError(
                f"benchmark stratum {stratum} has {len(pool)} eligible cards; "
                f"requires {per_stratum}"
            )
        chosen = sorted(
            pool,
            key=lambda row: _stable_key(
                SELECTION_VERSION, stratum, row["card"]["card_id"]
            ),
        )[:per_stratum]
        selected.extend(chosen)
    return sorted(
        selected,
        key=lambda row: _stable_key(SELECTION_VERSION, row["benchmark_row_id"]),
    )


def _render_review(template: str, benchmark: dict[str, Any]) -> str:
    embedded = json.dumps(benchmark, ensure_ascii=False, separators=(",", ":"))
    embedded = embedded.replace("</", "<\\/")
    marker = "__BENCHMARK_JSON__"
    if template.count(marker) != 1:
        raise WSDBenchmarkError("review template must contain exactly one benchmark marker")
    return template.replace(marker, embedded)


def build_wsd_benchmark(
    repository_root: Path,
    workspace: Workspace,
    *,
    run_id: str,
    language: str,
    mode: str,
    per_stratum: int = 40,
    created_at: datetime | None = None,
) -> Path:
    """Build the frozen gold-label pack without executing any WSD model."""

    if language != "fr" or mode != "speech" or per_stratum != 40:
        raise WSDBenchmarkError(
            "the approved benchmark contract is exactly French Speech 3x40"
        )
    run = workspace.root / "runs" / language / mode / run_id
    output = run / AUDIT_RELATIVE
    if output.exists():
        raise WSDBenchmarkError(
            "WSD benchmark already exists; immutable audits cannot be overwritten"
        )
    inventory_path = run / "stages/01_inventory/output/inventory.json"
    menu_path = run / "stages/02_sense_menu/output/sense-menu.json"
    candidates_path = run / "stages/03_sentence_harvest/output/candidates.json"
    bank_path = run / "stages/03_sentence_harvest/output/sentence-bank.jsonl"
    for stage in ("01_inventory", "02_sense_menu", "03_sentence_harvest"):
        manifest = _load_object(run / f"stages/{stage}/output/manifest.json")
        if manifest.get("status") != "complete":
            raise WSDBenchmarkError(f"required stage is not complete: {stage}")

    inventory_payload = _load_object(inventory_path)
    menu_payload = _load_object(menu_path)
    candidate_payload = _load_object(candidates_path)
    try:
        bank = {
            record["sentence_id"]: record
            for record in (
                json.loads(line)
                for line in bank_path.read_text(encoding="utf-8").splitlines()
            )
        }
    except (FileNotFoundError, json.JSONDecodeError, KeyError) as error:
        raise WSDBenchmarkError("sentence bank is missing or invalid") from error
    rows = _pick_rows(
        inventory_payload["cards"],
        menu_payload["cards"],
        candidate_payload["cards"],
        bank,
        per_stratum=per_stratum,
    )
    if len(rows) != 120 or len({row["card"]["card_id"] for row in rows}) != 120:
        raise WSDBenchmarkError("benchmark must contain 120 unique surface cards")
    inputs = {
        "inventory": file_content_id(inventory_path),
        "sense_menu": file_content_id(menu_path),
        "candidates": file_content_id(candidates_path),
        "sentence_bank": file_content_id(bank_path),
    }
    benchmark_body = {
        "benchmark_version": BENCHMARK_VERSION,
        "selection_version": SELECTION_VERSION,
        "run_id": run_id,
        "language": language,
        "mode": mode,
        "prediction_blind": True,
        "strata": {
            "function_homograph": per_stratum,
            "inflected_multi_headword": per_stratum,
            "ordinary_multi_sense": per_stratum,
        },
        "inputs": inputs,
        "rows": rows,
    }
    benchmark_id = canonical_content_id(benchmark_body)
    benchmark = {"benchmark_id": benchmark_id, **benchmark_body}
    created_at = datetime.now(UTC) if created_at is None else created_at.astimezone(UTC)
    template_path = repository_root / "src/fluency/wsd/review.template.html"
    template = template_path.read_text(encoding="utf-8")

    temporary_root = workspace.root / ".fluency/temporary"
    temporary = Path(tempfile.mkdtemp(prefix="wsd-benchmark-", dir=temporary_root))
    try:
        (temporary / "benchmark.json").write_bytes(json_bytes(benchmark))
        (temporary / "review.html").write_text(
            _render_review(template, benchmark), encoding="utf-8"
        )
        manifest = {
            "manifest_version": MANIFEST_VERSION,
            "benchmark_id": benchmark_id,
            "run_id": run_id,
            "created_at": created_at.isoformat().replace("+00:00", "Z"),
            "prediction_blind": True,
            "inputs": inputs,
            "outputs": {
                "benchmark": file_content_id(temporary / "benchmark.json"),
                "review": file_content_id(temporary / "review.html"),
            },
        }
        (temporary / "manifest.json").write_bytes(json_bytes(manifest))
        output.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return output
