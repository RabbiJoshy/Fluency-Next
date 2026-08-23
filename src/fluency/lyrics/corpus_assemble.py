"""Assemble one explicit WSD-method branch into clean multi-artist app data."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Callable

from fluency.core.hashing import canonical_content_id, file_content_id
from fluency.core.workspace import Workspace
from fluency.lyrics.assemble import METHOD_ID, assemble_lyrics_app_stage
from fluency.lyrics.corpus import PLAN_VERSION
from fluency.release.io import atomic_write, json_bytes


REPORT_VERSION = "lyrics-corpus-app-assembly-report/v1"
MANIFEST_VERSION = "lyrics-corpus-app-assembly/v1"
POLICY = {
    "policy_version": "lyrics-corpus-app-policy/v1",
    "card_identity": "surface_card_id",
    "sense_identity": "sense_assignment_id",
    "language_master": "union_of_selected_method_senses",
    "artist_frequency": "assigned_occurrence_count",
    "artist_order": "descending_occurrence_count_then_display_form_then_app_id",
    "sense_order": "sense_assignment_id",
    "example_order": "corpus_plan_song_order_then_source_position_and_token_span",
    "missing_artist_sense": "zero_frequency_and_empty_example_bucket",
    "song_card_membership": "selected_study_examples",
}


class LyricsCorpusAssemblyError(ValueError):
    """Raised when a method branch cannot become one exact artist dataset."""


def _object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LyricsCorpusAssemblyError(f"{label} is unavailable or invalid: {path}") from error
    if not isinstance(value, dict):
        raise LyricsCorpusAssemblyError(f"{label} must contain an object")
    return value


def _array(path: Path, label: str) -> list[Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LyricsCorpusAssemblyError(f"{label} is unavailable or invalid: {path}") from error
    if not isinstance(value, list):
        raise LyricsCorpusAssemblyError(f"{label} must contain an array")
    return value


def _verify_files(root: Path, manifest: dict[str, Any], label: str) -> None:
    outputs = manifest.get("outputs")
    if not isinstance(outputs, dict):
        raise LyricsCorpusAssemblyError(f"{label} has no output ledger")
    for name, expected in outputs.items():
        path = root / name
        if Path(name).name != name or not path.is_file() or file_content_id(path) != expected:
            raise LyricsCorpusAssemblyError(f"{label} output is missing or corrupt: {name}")


def _completed_song_assembly(
    output: Path, *, run_id: str, artist_slug: str, consolidation: Path, wsd: Path
) -> bool:
    if not output.exists():
        return False
    manifest = _object(output / "manifest.json", "song app assembly manifest")
    report = _object(output / "report.json", "song app assembly report")
    expected_inputs = {
        "cards": file_content_id(consolidation / "cards.jsonl"),
        "examples": file_content_id(consolidation / "examples.jsonl"),
        "wsd_results": file_content_id(wsd / "results.jsonl"),
    }
    if (
        manifest.get("run_id") != run_id
        or manifest.get("stage") != "app_assembly"
        or manifest.get("status") != "complete"
        or manifest.get("inputs") != expected_inputs
        or report.get("run_id") != run_id
        or report.get("artist_slug") != artist_slug
    ):
        raise LyricsCorpusAssemblyError(f"existing song assembly conflicts: {run_id}")
    _verify_files(output, manifest, f"song assembly {run_id}")
    return True


def _sense_key(example_bucket: list[dict[str, Any]], run_id: str) -> str:
    keys = {item.get("sense_assignment_id") for item in example_bucket if isinstance(item, dict)}
    if len(keys) != 1 or not isinstance(next(iter(keys), None), str):
        raise LyricsCorpusAssemblyError(f"song assembly lost exact sense identity: {run_id}")
    return next(iter(keys))


def _merge_song(
    *,
    assembly: Path,
    run_id: str,
    artist_slug: str,
    source_record_id: str,
    global_cards: dict[str, dict[str, Any]],
    artist_cards: dict[str, dict[str, dict[str, Any]]],
    song_cards: dict[tuple[str, str], set[str]],
) -> tuple[int, int]:
    index = _array(assembly / "index.json", "song index")
    examples = _object(assembly / "examples.json", "song examples")
    master = _object(assembly / "vocabulary_master.json", "song vocabulary master")
    ids = [item.get("id") for item in index if isinstance(item, dict)]
    if len(ids) != len(index) or set(ids) != set(examples) or set(ids) != set(master):
        raise LyricsCorpusAssemblyError(f"song split contract disagrees: {run_id}")
    example_count = 0
    for card in index:
        app_id = card["id"]
        card_master = master[app_id]
        surface_card_id = card.get("surface_card_id")
        existing = global_cards.get(app_id)
        stable = {
            "word": card_master.get("word"),
            "display_form": card_master.get("display_form"),
            "surface_card_id": surface_card_id,
        }
        if existing is None:
            existing = {**stable, "template": {key: value for key, value in card_master.items() if key != "senses"}, "senses": {}}
            global_cards[app_id] = existing
        elif any(existing.get(key) != value for key, value in stable.items()):
            raise LyricsCorpusAssemblyError(f"app ID collision or surface drift: {app_id}")

        payload = examples[app_id]
        senses = card_master.get("senses")
        buckets = payload.get("m") if isinstance(payload, dict) else None
        if not isinstance(senses, list) or not isinstance(buckets, list) or len(senses) != len(buckets):
            raise LyricsCorpusAssemblyError(f"song sense/example alignment drift: {run_id}/{app_id}")
        artist_card = artist_cards[artist_slug].setdefault(app_id, {
            "surface_card_id": surface_card_id,
            "display_form": card_master.get("display_form") or card_master.get("word"),
            "occurrence_count": 0,
            "senses": {},
        })
        card_count = card.get("corpus_count")
        if not isinstance(card_count, int) or card_count <= 0:
            raise LyricsCorpusAssemblyError(f"song card has invalid occurrence count: {run_id}/{app_id}")
        artist_card["occurrence_count"] += card_count
        frequencies = card.get("sense_frequencies")
        methods = card.get("sense_methods")
        confidences = card.get("sense_confidence")
        bands = card.get("sense_band")
        if not all(isinstance(value, list) and len(value) == len(senses) for value in (frequencies, methods, confidences, bands)):
            raise LyricsCorpusAssemblyError(f"song index sense metadata drift: {run_id}/{app_id}")
        for position, (sense, bucket) in enumerate(zip(senses, buckets, strict=True)):
            if not isinstance(sense, dict) or not isinstance(bucket, list) or not bucket:
                raise LyricsCorpusAssemblyError(f"song assigned sense has no example: {run_id}/{app_id}")
            sense_id = _sense_key(bucket, run_id)
            known_sense = existing["senses"].get(sense_id)
            if known_sense is None:
                existing["senses"][sense_id] = sense
            elif known_sense != sense:
                raise LyricsCorpusAssemblyError(f"one sense identity has conflicting metadata: {sense_id}")
            occurrence_count = round(float(frequencies[position]) * card_count)
            state = artist_card["senses"].setdefault(sense_id, {
                "occurrence_count": 0, "examples": [], "methods": set(),
                "confidence_sum": 0.0, "confidence_weight": 0, "bands": set(),
            })
            state["occurrence_count"] += occurrence_count
            state["examples"].extend(bucket)
            state["methods"].add(methods[position])
            confidence = confidences[position]
            if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
                weight = max(1, occurrence_count)
                state["confidence_sum"] += float(confidence) * weight
                state["confidence_weight"] += weight
            if bands[position] is not None:
                state["bands"].add(bands[position])
            example_count += len(bucket)
            song_cards[(artist_slug, source_record_id)].add(app_id)
    return len(index), example_count


def assemble_lyrics_corpus(
    repository_root: Path,
    workspace: Workspace,
    *,
    plan_path: Path,
    consolidation_report_path: Path,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Materialize clean artist app data from one named method branch."""

    plan_path = plan_path.expanduser().resolve()
    consolidation_report_path = consolidation_report_path.expanduser().resolve()
    plan = _object(plan_path, "Lyrics corpus plan")
    report = _object(consolidation_report_path, "Lyrics corpus consolidation report")
    if plan.get("plan_version") != PLAN_VERSION or plan.get("status") != "planned_sources_only":
        raise LyricsCorpusAssemblyError("unsupported Lyrics corpus plan")
    language = plan.get("language")
    plan_id = plan.get("plan_id")
    method_profile_id = report.get("method_profile_id")
    if (
        report.get("status") != "complete"
        or report.get("plan_id") != plan_id
        or report.get("plan_content_id") != file_content_id(plan_path)
        or report.get("song_run_count") != plan.get("totals", {}).get("songs")
        or not isinstance(method_profile_id, str)
    ):
        raise LyricsCorpusAssemblyError("consolidation does not cover this exact corpus")
    branch_root = (
        workspace.root / "runs" / language / "lyrics-corpora" / plan_id
        / "methods" / method_profile_id / "songs"
    )
    if report.get("method_branch") != branch_root.relative_to(workspace.root).as_posix():
        raise LyricsCorpusAssemblyError("consolidation report names an unexpected method branch")

    global_cards: dict[str, dict[str, Any]] = {}
    artist_cards: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    song_cards: dict[tuple[str, str], set[str]] = defaultdict(set)
    created = skipped = song_card_references = selected_examples = 0
    songs = [
        (source, song)
        for source in plan.get("included_sources", []) if isinstance(source, dict)
        for song in source.get("songs", []) if isinstance(song, dict)
    ]
    for position, (source, song) in enumerate(songs, start=1):
        run_id = song["planned_run_id"]
        artist_slug = source["artist_slug"]
        branch = branch_root / run_id
        wsd = branch / "wsd_results"
        consolidation = branch / "consolidation"
        assembly = branch / "app_assembly"
        if _completed_song_assembly(
            assembly, run_id=run_id, artist_slug=artist_slug,
            consolidation=consolidation, wsd=wsd,
        ):
            skipped += 1
            action = "skipped"
        else:
            assemble_lyrics_app_stage(
                repository_root, workspace, run_id=run_id, language=language,
                artist_slug=artist_slug, consolidation_output_path=consolidation,
                wsd_output_path=wsd, output_path=assembly, publish_run_stage=False,
            )
            created += 1
            action = "created"
        cards, examples = _merge_song(
            assembly=assembly, run_id=run_id, artist_slug=artist_slug,
            source_record_id=song["source_record_id"], global_cards=global_cards,
            artist_cards=artist_cards, song_cards=song_cards,
        )
        song_card_references += cards
        selected_examples += examples
        if progress is not None:
            progress({
                "completed": position, "planned": len(songs), "action": action,
                "artist_slug": artist_slug, "source_record_id": song["source_record_id"],
                "run_id": run_id,
            })

    master: dict[str, Any] = {}
    sense_orders: dict[str, list[str]] = {}
    for app_id in sorted(global_cards):
        card = global_cards[app_id]
        order = sorted(card["senses"])
        sense_orders[app_id] = order
        master[app_id] = {**card["template"], "senses": [card["senses"][key] for key in order]}

    rendered_artists: dict[str, dict[str, Any]] = {}
    for source in plan.get("included_sources", []):
        slug = source["artist_slug"]
        rows: list[dict[str, Any]] = []
        examples_map: dict[str, Any] = {}
        ordered_cards = sorted(
            artist_cards[slug].items(),
            key=lambda item: (-item[1]["occurrence_count"], str(item[1]["display_form"]).casefold(), item[0]),
        )
        for rank, (app_id, card) in enumerate(ordered_cards, start=1):
            order = sense_orders[app_id]
            total = card["occurrence_count"]
            frequencies: list[float] = []
            methods: list[str | None] = []
            confidences: list[float | None] = []
            bands: list[str | None] = []
            buckets: list[list[dict[str, Any]]] = []
            for sense_id in order:
                state = card["senses"].get(sense_id)
                if state is None:
                    frequencies.append(0.0); methods.append(None); confidences.append(None); bands.append(None); buckets.append([])
                    continue
                frequencies.append(state["occurrence_count"] / total)
                methods.append("+".join(sorted(str(value) for value in state["methods"])))
                confidences.append(
                    state["confidence_sum"] / state["confidence_weight"]
                    if state["confidence_weight"] else None
                )
                bands.append("+".join(sorted(str(value) for value in state["bands"])) or None)
                seen_examples: set[str] = set()
                ordered_examples: list[dict[str, Any]] = []
                for example in state["examples"]:
                    example_id = example["example_id"]
                    if example_id not in seen_examples:
                        seen_examples.add(example_id)
                        ordered_examples.append(example)
                buckets.append(ordered_examples)
            rows.append({
                "id": app_id, "rank": rank, "corpus_count": total,
                "lemma_example_count": total, "most_frequent_lemma_instance": True,
                "sense_frequencies": frequencies, "sense_methods": methods,
                "sense_confidence": confidences, "sense_band": bands,
                "surface_card_id": card["surface_card_id"], "extra_category": "core",
            })
            examples_map[app_id] = {"m": buckets}
        clean_songs = [{
            "id": str(song["source_record_id"]), "title": song["title"],
            "creditedArtist": song["credited_artist"],
            "cardIds": sorted(song_cards[(slug, song["source_record_id"])]),
            "runId": song["planned_run_id"],
        } for song in source["songs"]]
        rendered_artists[slug] = {
            "name": source["artist_name"], "index": rows, "examples": examples_map,
            "songs": {
                "schemaVersion": 1, "source": slug, "name": source["artist_name"],
                "songCount": len(clean_songs), "cardCount": len(rows),
                "songLinkedCardCount": len({card for song in clean_songs for card in song["cardIds"]}),
                "songs": clean_songs,
            },
        }

    output = (
        workspace.root / "runs" / language / "lyrics-corpora" / plan_id
        / "methods" / method_profile_id / "corpus_app_assembly"
    )
    if output.exists():
        raise LyricsCorpusAssemblyError("corpus app assembly already exists; select a new method branch")
    temporary_root = workspace.root / ".fluency/temporary"
    temporary = Path(tempfile.mkdtemp(prefix="lyrics-corpus-assembly-", dir=temporary_root))
    try:
        app = temporary / "app"
        language_root = app / "Artists" / language
        language_root.mkdir(parents=True)
        (language_root / "vocabulary_master.json").write_bytes(json_bytes(master))
        catalog: dict[str, Any] = {}
        for slug, artist in rendered_artists.items():
            root = language_root / slug
            root.mkdir()
            (root / "index.json").write_bytes(json_bytes(artist["index"]))
            (root / "examples.json").write_bytes(json_bytes(artist["examples"]))
            (root / "songs.json").write_bytes(json_bytes(artist["songs"]))
            catalog[slug] = {
                "name": artist["name"], "language": language,
                "masterPath": f"Artists/{language}/vocabulary_master.json",
                "indexPath": f"Artists/{language}/{slug}/index.json",
                "examplesPath": f"Artists/{language}/{slug}/examples.json",
                "songsPath": f"Artists/{language}/{slug}/songs.json",
                "maxLevel": len(artist["index"]), "colorTheme": {},
            }
        (app / "config").mkdir()
        (app / "config/artists.json").write_bytes(json_bytes(catalog))
        files = [{
            "path": path.relative_to(temporary).as_posix(),
            "content_id": file_content_id(path), "bytes": path.stat().st_size,
        } for path in sorted(item for item in app.rglob("*") if item.is_file())]
        summary = {
            "report_version": REPORT_VERSION, "status": "complete",
            "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "plan_id": plan_id, "plan_content_id": file_content_id(plan_path),
            "consolidation_report_content_id": file_content_id(consolidation_report_path),
            "language": language, "method_profile_id": method_profile_id,
            "policy": POLICY, "song_run_count": len(songs),
            "artist_count": len(rendered_artists), "language_card_count": len(master),
            "artist_card_count": sum(len(value["index"]) for value in rendered_artists.values()),
            "song_card_reference_count": song_card_references,
            "selected_example_count": selected_examples,
            "files": files,
        }
        (temporary / "report.json").write_bytes(json_bytes(summary))
        manifest = {
            "manifest_version": MANIFEST_VERSION, "status": "complete",
            "plan_id": plan_id, "language": language,
            "method_profile_id": method_profile_id, "method_id": METHOD_ID,
            "implementation_content_id": canonical_content_id({
                "implementation": file_content_id(Path(__file__)),
                "song_assembler": file_content_id(Path(__file__).with_name("assemble.py")),
                "app_contract": file_content_id(repository_root / "app/js/data-contracts.js"),
            }),
            "inputs": {
                "plan": file_content_id(plan_path),
                "consolidation_report": file_content_id(consolidation_report_path),
            },
            "outputs": {
                "report.json": file_content_id(temporary / "report.json"),
                **{item["path"]: item["content_id"] for item in files},
            },
        }
        (temporary / "manifest.json").write_bytes(json_bytes(manifest))
        output.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    report_path = output / "report.json"
    pointer = output.parent.parent.parent / f"assembly-report-{method_profile_id}.json"
    atomic_write(pointer, {**summary, "assembly_path": output.relative_to(workspace.root).as_posix(), "assembly_manifest_content_id": file_content_id(output / "manifest.json")}, temporary_root)
    return {
        **summary, "created_this_invocation": created,
        "skipped_this_invocation": skipped, "report_path": str(report_path),
        "assembly_path": str(output), "corpus_report_path": str(pointer),
    }
