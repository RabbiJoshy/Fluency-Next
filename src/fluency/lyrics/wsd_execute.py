"""Execute the pinned Spanish v5 method and emit an importable raw bundle.

Heavy packages are imported only inside the command. The immutable retained
Gemini cache is read-only; API misses are written to a run-scoped delta cache.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import time
from typing import Any

from fluency.core.hashing import canonical_content_id, file_content_id
from fluency.core.workspace import Workspace
from fluency.lyrics.lexical import index_menu_analyses, resolve_candidate_analyses
from fluency.lyrics.wsd_results import BUNDLE_VERSION, RESULT_VERSION
from fluency.release.io import atomic_write
from fluency.wsd.spanish_v5_features import build_features, companion_features, structural_features


METHOD_PROFILE = "es-sd-beto-cal-v5-migration-v1"
SOURCE_METHOD = "spanishdict-beto-cal-v5"
SOURCE_COMMIT = "78506bf6ee785049393b2a760eceecd083c53495"
BETO_MODEL = "dccuchile/bert-base-spanish-wwm-cased"
BETO_REVISION = "c4d86612f51b4f46759c8390d1798c2febe71b93"
SPACY_POS_MODEL = "es_dep_news_trf@3.8.0"


class LyricsWSDExecutionError(ValueError):
    pass


@dataclass
class SpanishV5Runtime:
    vector: Any
    spacy_model: Any
    tokenizer: Any
    token_model: Any
    token_device: str
    prototype_matrix: Any
    prototype_index: dict[str, int]
    calibrator: Any
    high_cut: float
    medium_cut: float
    base_embeddings: Path
    prototypes: Path
    calibrator_root: Path
    delta: Path


def dotenv_value(path: Path, name: str) -> str | None:
    """Read one dotenv assignment as data; never execute the file as shell code."""

    try:
        lines = path.expanduser().read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise LyricsWSDExecutionError(f"dotenv file is unavailable: {path}") from error
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.strip() != name:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        return value or None
    return None


def _records(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _gloss(word: str, analysis: dict[str, Any], sense: dict[str, Any]) -> str:
    translation = (sense.get("translation") or "").strip() or "(sin traduccion)"
    metadata = sense.get("provider_metadata") or {}
    context = (metadata.get("context") or sense.get("definition") or "").strip()
    return f'"{word}" ({analysis.get("part_of_speech", "")}): {translation}' + (f" — {context}" if context else "")


def _normalize_translation(value: str) -> str:
    import re
    value = (value or "").lower().strip()
    value = re.sub(r"^(to |a |an |the )", "", value)
    return re.sub(r"[^a-z0-9 ]", "", value).strip()


def _load_vectors(base: Path, delta: Path, required: list[str], api_key: str | None):
    import numpy as np
    index = json.loads((base / "vec_index.json").read_text(encoding="utf-8"))
    matrix = np.load(base / "vec.npy", mmap_mode="r")
    delta_index: dict[str, int] = {}
    delta_matrix = np.zeros((0, matrix.shape[1]), dtype=np.float16)
    if (delta / "index.json").exists() and (delta / "vec.npy").exists():
        delta_index = json.loads((delta / "index.json").read_text(encoding="utf-8"))
        delta_matrix = np.load(delta / "vec.npy")
        positions = sorted(delta_index.values())
        if positions != list(range(len(delta_index))) or len(delta_matrix) < len(delta_index):
            raise LyricsWSDExecutionError("run-scoped Gemini delta index/vector pair is corrupt")
        # The vector is replaced before the index at checkpoints. If a process
        # dies between those two atomic replacements, discard only the
        # uncommitted tail and resume from the last complete index.
        if len(delta_matrix) > len(delta_index):
            delta_matrix = delta_matrix[:len(delta_index)]
    missing = [text for text in dict.fromkeys(required) if text not in index and text not in delta_index]
    if missing:
        if not api_key:
            raise LyricsWSDExecutionError(
                f"{len(missing)} exact Gemini embeddings are missing; set GEMINI_API_KEY and rerun"
            )
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=api_key)
        print(f"Embedding {len(missing)} exact cache misses into a run-scoped delta...", flush=True)

        def checkpoint() -> None:
            delta.mkdir(parents=True, exist_ok=True)
            vector_temporary = delta / "vec.npy.partial"
            index_temporary = delta / "index.json.partial"
            with vector_temporary.open("wb") as handle:
                np.save(handle, delta_matrix)
            index_temporary.write_text(
                json.dumps(delta_index, ensure_ascii=False), encoding="utf-8"
            )
            os.replace(vector_temporary, delta / "vec.npy")
            os.replace(index_temporary, delta / "index.json")

        since_checkpoint = 0
        for offset in range(0, len(missing), 100):
            batch = missing[offset:offset + 100]
            attempts = 0
            while True:
                started = time.monotonic()
                try:
                    response = client.models.embed_content(
                        model="gemini-embedding-001", contents=batch,
                        config=types.EmbedContentConfig(task_type="SEMANTIC_SIMILARITY"),
                    )
                    break
                except Exception as error:
                    status = getattr(error, "status_code", None) or getattr(error, "code", None)
                    if status != 429 and "429" not in str(error):
                        checkpoint()
                        raise
                    attempts += 1
                    checkpoint()
                    if attempts > 12:
                        raise LyricsWSDExecutionError(
                            "Gemini embedding quota remained unavailable after 12 resumable retries"
                        ) from error
                    match = re.search(r"retry in ([0-9.]+)s", str(error), flags=re.IGNORECASE)
                    delay = min(60.0, (float(match.group(1)) + 2.0) if match else 20.0)
                    print(
                        f"  Gemini quota pause; checkpointed {len(delta_index)} delta vectors "
                        f"and retrying this batch in {delay:.1f}s...",
                        flush=True,
                    )
                    time.sleep(delay)
            values = np.asarray([item.values for item in response.embeddings], dtype=np.float32)
            if len(values) != len(batch):
                checkpoint()
                raise LyricsWSDExecutionError("Gemini returned an incomplete embedding batch")
            values /= np.linalg.norm(values, axis=1, keepdims=True) + 1e-9
            new = values.astype(np.float16)
            start = len(delta_matrix)
            delta_matrix = np.vstack([delta_matrix, new]) if len(delta_matrix) else new
            for position, text_value in enumerate(batch, start=start):
                delta_index[text_value] = position
            since_checkpoint += len(batch)
            if since_checkpoint >= 1000 or offset + len(batch) == len(missing):
                checkpoint()
                since_checkpoint = 0
            print(f"  embedded {min(offset + len(batch), len(missing))}/{len(missing)}", flush=True)
            # Stay below the paid-tier 3,000 embedded-content/minute ceiling.
            elapsed = time.monotonic() - started
            if offset + len(batch) < len(missing) and elapsed < 2.2:
                time.sleep(2.2 - elapsed)
    def vector(text: str):
        value = matrix[index[text]] if text in index else delta_matrix[delta_index[text]]
        return value.astype(np.float32)
    return vector


def _pos_tags(requests: list[dict[str, Any]], model: Any | None = None) -> dict[str, str | None]:
    import spacy
    model = spacy.load("es_dep_news_trf") if model is None else model
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for request in requests:
        if request["eligibility"] == "ready":
            grouped[request["context"]["text"]].append(request)
    result: dict[str, str | None] = {}
    print(f"Tagging {len(grouped)} unique lyric lines for occurrence POS...", flush=True)
    for document, text in zip(model.pipe(grouped, batch_size=32), grouped):
        for request in grouped[text]:
            start, end = request["context"]["target_span"]
            tokens = [token for token in document if token.idx < end and token.idx + len(token.text) > start]
            result[request["request_id"]] = tokens[0].pos_ if tokens else None
    return result


def _token_vectors(
    requests: list[dict[str, Any]], *, tokenizer: Any | None = None,
    model: Any | None = None, device: str | None = None,
):
    import numpy as np
    import torch
    from transformers import AutoModel, AutoTokenizer
    ready = [request for request in requests if request["eligibility"] == "ready"]
    tokenizer = tokenizer or AutoTokenizer.from_pretrained(BETO_MODEL, revision=BETO_REVISION)
    model = model or AutoModel.from_pretrained(BETO_MODEL, revision=BETO_REVISION, output_hidden_states=True)
    device = device or ("mps" if torch.backends.mps.is_available() else "cpu")
    model.eval().to(device)
    output = {}
    print(f"Encoding {len(ready)} exact lyric occurrences with BETO on {device}...", flush=True)
    with torch.no_grad():
        for offset in range(0, len(ready), 64):
            batch = ready[offset:offset + 64]
            texts = [request["context"]["text"] for request in batch]
            encoded = tokenizer(texts, return_tensors="pt", padding=True, truncation=True, max_length=96, return_offsets_mapping=True)
            offsets = encoded.pop("offset_mapping")
            hidden = model(**{key: value.to(device) for key, value in encoded.items()}).hidden_states
            representations = torch.stack(hidden[-4:]).mean(0).cpu().numpy()
            for index, request in enumerate(batch):
                start, end = request["context"]["target_span"]
                mapping = offsets[index].numpy()
                selected = [position for position, (left, right) in enumerate(mapping) if right > left and left < end and right > start]
                if selected:
                    vector = representations[index][selected].mean(0)
                    norm = float(np.linalg.norm(vector))
                    if norm:
                        output[request["request_id"]] = (vector / norm).astype(np.float32)
            print(f"  encoded {min(offset + len(batch), len(ready))}/{len(ready)}", flush=True)
    return output


def spanish_v5_required_texts(workspace: Workspace, *, run_id: str) -> list[str]:
    """Return exact Gemini texts needed by one prepared song without running models."""

    run = workspace.root / "runs/es/lyrics" / run_id
    requests = _records(run / "stages/04_wsd_prepare/output/requests.jsonl")
    candidates = {
        item["lexical_candidate_id"]: item
        for item in _records(run / "stages/03_lexical_menu/output/lexical-candidates.jsonl")
    }
    analyses_by_card = index_menu_analyses(json.loads(
        (run / "stages/03_lexical_menu/output/sense-menu.json").read_text(encoding="utf-8")
    ))
    texts: list[str] = []
    for request in requests:
        if request["eligibility"] != "ready":
            continue
        candidate = candidates[request["lexical_candidate_id"]]
        analyses = resolve_candidate_analyses(candidate, analyses_by_card)
        texts.append(request["context"]["text"])
        texts.extend(
            _gloss(candidate["lookup_form"], analysis, sense)
            for analysis in analyses for sense in analysis["senses"]
        )
    return texts


def build_spanish_v5_runtime(
    workspace: Workspace, *, required_texts: list[str], delta: Path,
    api_key: str | None = None, env_file: Path | None = None,
) -> SpanishV5Runtime:
    """Load expensive models once for one resumable execution branch."""

    import joblib
    import numpy as np
    import spacy
    import torch
    from transformers import AutoModel, AutoTokenizer

    base_embeddings = workspace.root / "raw/embeddings/google-gemini/gemini-embedding-001/recovered-2026-08-20-v1"
    prototypes = workspace.root / "raw/wsd/assets/es/beto/prototypes-sd-beto-cal-v5-v1"
    calibrator_root = workspace.root / "raw/wsd/assets/es/calibration/sd-beto-cal-v5-legacy-v1"
    for path in (base_embeddings / "vec.npy", prototypes / "proto.npy", calibrator_root / "calibrator.joblib"):
        if not path.is_file():
            raise LyricsWSDExecutionError(f"required pinned WSD asset is missing: {path}")
    resolved_api_key = api_key or os.environ.get("GEMINI_API_KEY")
    if resolved_api_key is None and env_file is not None:
        resolved_api_key = dotenv_value(env_file, "GEMINI_API_KEY")
    vector = _load_vectors(base_embeddings, delta, required_texts, resolved_api_key)
    print("Loading Spanish POS and BETO models once for this execution branch...", flush=True)
    spacy_model = spacy.load("es_dep_news_trf")
    tokenizer = AutoTokenizer.from_pretrained(BETO_MODEL, revision=BETO_REVISION)
    token_model = AutoModel.from_pretrained(
        BETO_MODEL, revision=BETO_REVISION, output_hidden_states=True
    )
    token_device = "mps" if torch.backends.mps.is_available() else "cpu"
    token_model.eval().to(token_device)
    calibrator = joblib.load(calibrator_root / "calibrator.joblib")
    calibrator_manifest = json.loads((calibrator_root / "manifest.json").read_text(encoding="utf-8"))
    cuts = calibrator_manifest.get("band_cuts") or {"high": 0.8776, "medium": 0.5528}
    return SpanishV5Runtime(
        vector=vector, spacy_model=spacy_model, tokenizer=tokenizer,
        token_model=token_model, token_device=token_device,
        prototype_matrix=np.load(prototypes / "proto.npy", mmap_mode="r"),
        prototype_index=json.loads((prototypes / "proto_index.json").read_text(encoding="utf-8")),
        calibrator=calibrator, high_cut=float(cuts.get("high", 0.8776)),
        medium_cut=float(cuts.get("medium", 0.5528)), base_embeddings=base_embeddings,
        prototypes=prototypes, calibrator_root=calibrator_root, delta=delta,
    )


def execute_spanish_v5_lyrics(
    repository_root: Path, workspace: Workspace, *, run_id: str,
    api_key: str | None = None, env_file: Path | None = None,
    runtime: SpanishV5Runtime | None = None, output_path: Path | None = None,
) -> Path:
    import numpy as np
    run = workspace.root / "runs/es/lyrics" / run_id
    request_path = run / "stages/04_wsd_prepare/output/requests.jsonl"
    candidate_path = run / "stages/03_lexical_menu/output/lexical-candidates.jsonl"
    menu_path = run / "stages/03_lexical_menu/output/sense-menu.json"
    requests = _records(request_path)
    candidates = {item["lexical_candidate_id"]: item for item in _records(candidate_path)}
    menu = json.loads(menu_path.read_text(encoding="utf-8"))
    analyses_by_card = index_menu_analyses(menu)
    candidate_analyses = {
        candidate_id: resolve_candidate_analyses(candidate, analyses_by_card)
        for candidate_id, candidate in candidates.items()
    }
    texts = []
    for request in requests:
        if request["eligibility"] != "ready":
            continue
        candidate = candidates[request["lexical_candidate_id"]]
        analyses = candidate_analyses[request["lexical_candidate_id"]]
        texts.append(request["context"]["text"])
        texts.extend(
            _gloss(candidate["lookup_form"], analysis, sense)
            for analysis in analyses for sense in analysis["senses"]
        )
    if runtime is None:
        runtime = build_spanish_v5_runtime(
            workspace, required_texts=texts,
            delta=workspace.root / "cache/derived/wsd/es" / run_id / "gemini-delta",
            api_key=api_key, env_file=env_file,
        )
    vector = runtime.vector
    observed_pos = _pos_tags(requests, runtime.spacy_model)
    token_vectors = _token_vectors(
        requests, tokenizer=runtime.tokenizer, model=runtime.token_model,
        device=runtime.token_device,
    )
    prototype_matrix = runtime.prototype_matrix
    prototype_index = runtime.prototype_index
    calibrator = runtime.calibrator
    high_cut = runtime.high_cut
    medium_cut = runtime.medium_cut
    results = []
    for request in requests:
        candidate = candidates[request["lexical_candidate_id"]]
        analyses = candidate_analyses[request["lexical_candidate_id"]]
        common = {
            "result_version": RESULT_VERSION, "request_id": request["request_id"],
            "run_id": run_id, "language": "es", "mode": "lyrics", "target": request["target"],
            "occurrence_id": request["occurrence_id"], "surface_card_id": request["surface_card_id"],
            "surface_form": request["surface_form"],
        }
        if request["eligibility"] != "ready":
            body = {**common, "status": request["eligibility"], "menu_content_id": None,
                    "menu_analysis_id": None, "selected_sense_id": None, "selected_tuple": None,
                    "decision_path": [], "evidence": {"reason_codes": [f"wsd_eligibility_{request['eligibility']}"]},
                    "confidence": None, "input_artifact_ids": request["input_artifact_ids"]}
            body["result_id"] = "wsd_result_" + canonical_content_id(body).removeprefix("sha256:")[:32]
            results.append(body); continue
        sentence = request["context"]["text"]
        query = vector(sentence)
        leaf_rows = []
        for analysis in analyses:
            for sense in analysis["senses"]:
                raw = float(query @ vector(_gloss(candidate["lookup_form"], analysis, sense)))
                leaf_rows.append({"analysis": analysis, "sense": sense, "raw": raw})
        # Prior is global provider order; candidate gates restrict the gloss argmax only.
        for rank, row in enumerate(leaf_rows):
            row["adjusted"] = row["raw"] + 0.02 * (0.5 ** rank)
        pos = observed_pos.get(request["request_id"])
        allowed_analyses = analyses
        # Reuse the clean policy's measured filtering via lightweight menu records is unnecessary here:
        # its public bridge and se gate are applied by analysis identity below.
        from fluency.wsd.languages.spanish import sense_compatible_bridged, se_reflexive_evidence
        compatible = [a for a in allowed_analyses if not pos or sense_compatible_bridged(a["part_of_speech"], pos)]
        if compatible:
            allowed_analyses = compatible
        se_evidence = se_reflexive_evidence(request["surface_form"], sentence)
        headwords = {a["headword"].lower() for a in analyses}
        ambiguous = any(not word.endswith("se") and word + "se" in headwords for word in headwords)
        if ambiguous and se_evidence is not None:
            compatible = [a for a in allowed_analyses if a["headword"].lower().endswith("se") is se_evidence]
            if compatible:
                allowed_analyses = compatible
        allowed_ids = {a["menu_analysis_id"] for a in allowed_analyses}
        selected = max((row for row in leaf_rows if row["analysis"]["menu_analysis_id"] in allowed_ids), key=lambda row: row["adjusted"])
        decision_path = ["candidate_preparation", "provider_prior", "gloss"]
        tuples = list(dict.fromkeys((row["analysis"]["headword"].strip().lower(), row["analysis"]["part_of_speech"].strip()) for row in leaf_rows))
        proto_keys = [f"{candidate['lookup_form']}\t{headword}\t{pos_value}" for headword, pos_value in tuples]
        token = token_vectors.get(request["request_id"])
        token_gap = token_agrees = 0.0
        token_available = 0.0
        token_evidence = {"status": "unavailable_incomplete_prototype_menu"}
        if token is not None and len(tuples) > 1 and all(key in prototype_index for key in proto_keys):
            proto = np.stack([prototype_matrix[prototype_index[key]] for key in proto_keys])
            similarities = proto @ token
            order = np.argsort(-similarities)
            token_gap = float(similarities[order[0]] - similarities[order[1]])
            token_available = 1.0
            winning_tuple = tuples[int(order[0])]
            if token_gap >= 0.02:
                selected = max((row for row in leaf_rows if (row["analysis"]["headword"].strip().lower(), row["analysis"]["part_of_speech"].strip()) == winning_tuple), key=lambda row: row["adjusted"])
                decision_path.append("token_tuple_vote")
            token_agrees = float(winning_tuple == (selected["analysis"]["headword"].strip().lower(), selected["analysis"]["part_of_speech"].strip()))
            token_evidence = {"status": "available", "winning_tuple": list(winning_tuple), "gap": token_gap, "minimum_gap": 0.02}
        tuple_ids = [(row["analysis"]["headword"].strip().lower(), row["analysis"]["part_of_speech"].strip()) for row in leaf_rows]
        class_ids = [(row["analysis"]["part_of_speech"], _normalize_translation(row["sense"].get("translation", ""))) for row in leaf_rows]
        chosen_index = leaf_rows.index(selected)
        chosen_tuple = tuple_ids[chosen_index]
        chosen_class = class_ids[chosen_index]
        tuple_best = {key: max(row["raw"] for row, item in zip(leaf_rows, tuple_ids) if item == key) for key in set(tuple_ids)}
        class_best = {key: max(row["raw"] for row, item in zip(leaf_rows, class_ids) if item == key) for key in set(class_ids)}
        tuple_gap = 1.0 if len(tuple_best) == 1 else tuple_best[chosen_tuple] - max(value for key, value in tuple_best.items() if key != chosen_tuple)
        class_gap = 1.0 if len(class_best) == 1 else class_best[chosen_class] - max(value for key, value in class_best.items() if key != chosen_class)
        enriched_senses = []
        for row in leaf_rows:
            enriched_senses.append({**row["sense"], "_headword": row["analysis"]["headword"].strip().lower(), "_pos": row["analysis"]["part_of_speech"].strip()})
        selected_enriched = enriched_senses[chosen_index]
        features = build_features(
            tuple_gap=tuple_gap, class_gap=class_gap, tuple_count=len(set(tuple_ids)), leaf_count=len(leaf_rows),
            sentence_length=len(sentence.split()), predicted_tuple=chosen_tuple,
            empty_translation=not bool((selected["sense"].get("translation") or "").strip()),
            token_available=token_available, token_gap=token_gap, token_agrees=token_agrees,
            companion=companion_features(candidate["lookup_form"], sentence, enriched_senses, selected_enriched),
            structural=structural_features(candidate["lookup_form"], sentence, enriched_senses, selected_enriched),
        )
        confidence = float(calibrator.predict_proba(np.asarray([features]))[0, 1])
        decision_path.append("calibration")
        # Exact v5 leaf repair: only inside the already-winning tuple.
        from fluency.wsd.languages.spanish import companion_satisfied, leaf_renderable
        sense_obj_by_id = {}
        from fluency.wsd.menus import SenseLeaf
        for row in leaf_rows:
            sense = row["sense"]
            sense_obj_by_id[(row["analysis"]["menu_analysis_id"], sense["sense_id"])] = SenseLeaf(
                sense["sense_id"], sense.get("translation") or "", sense.get("definition") or "",
                sense.get("source_reference") or f"spanishdict:{sense['sense_id']}", sense.get("provider_metadata") or {},
            )
        selected_obj = sense_obj_by_id[(selected["analysis"]["menu_analysis_id"], selected["sense"]["sense_id"])]
        if not (leaf_renderable(selected_obj) and companion_satisfied(selected_obj, sentence)):
            eligible = [row for row in leaf_rows if tuple_ids[leaf_rows.index(row)] == chosen_tuple and leaf_renderable(sense_obj_by_id[(row["analysis"]["menu_analysis_id"], row["sense"]["sense_id"])]) and companion_satisfied(sense_obj_by_id[(row["analysis"]["menu_analysis_id"], row["sense"]["sense_id"])], sentence)]
            if eligible:
                repaired = max(eligible, key=lambda row: row["adjusted"])
                if repaired is not selected:
                    selected = repaired; decision_path.insert(-1, "leaf_repair")
        band = "high" if confidence >= high_cut else "medium" if confidence >= medium_cut else "low"
        body = {**common, "status": "assigned", "menu_content_id": file_content_id(menu_path),
                "menu_analysis_id": selected["analysis"]["menu_analysis_id"], "selected_sense_id": selected["sense"]["sense_id"],
                "selected_tuple": {"headword": selected["analysis"]["headword"], "part_of_speech": selected["analysis"]["part_of_speech"]},
                "decision_path": decision_path,
                "evidence": {"reason_codes": [], "observed_pos": pos, "se_reflexive_evidence": se_evidence,
                             "gloss_top": [{"analysis_id": row["analysis"]["menu_analysis_id"], "sense_id": row["sense"]["sense_id"], "raw": row["raw"], "adjusted": row["adjusted"]} for row in sorted(leaf_rows, key=lambda row: -row["adjusted"])[:5]],
                             "token_tuple_vote": token_evidence, "calibration": {"raw_score": confidence, "legacy_band": band, "validation_scope": "dictionary_examples_only", "release_role": "evidence_only"}},
                "confidence": confidence, "input_artifact_ids": request["input_artifact_ids"]}
        body["result_id"] = "wsd_result_" + canonical_content_id(body).removeprefix("sha256:")[:32]
        results.append(body)
    def asset_ref(path: Path) -> dict[str, str]:
        return {"path": path.relative_to(workspace.root).as_posix(), "content_id": file_content_id(path)}
    asset_refs = {
        "gemini_vectors": asset_ref(runtime.base_embeddings / "vec.npy"),
        "gemini_index": asset_ref(runtime.base_embeddings / "vec_index.json"),
        "beto_prototypes": asset_ref(runtime.prototypes / "proto.npy"),
        "beto_prototype_index": asset_ref(runtime.prototypes / "proto_index.json"),
        "calibrator": asset_ref(runtime.calibrator_root / "calibrator.joblib"),
    }
    if (runtime.delta / "vec.npy").is_file():
        asset_refs["gemini_delta_vectors"] = asset_ref(runtime.delta / "vec.npy")
        asset_refs["gemini_delta_index"] = asset_ref(runtime.delta / "index.json")
    method = {
        "profile_id": METHOD_PROFILE, "source_method_id": SOURCE_METHOD,
        "source_repository_commit": SOURCE_COMMIT, "implementation_version": "spanish-v5-lyrics-executor/v1",
        "implementation_content_id": canonical_content_id({
            "executor": file_content_id(Path(__file__)),
            "features": file_content_id(repository_root / "src/fluency/wsd/spanish_v5_features.py"),
            "policy": file_content_id(repository_root / "src/fluency/wsd/languages/spanish.py"),
        }),
        "model_revisions": {"gloss": "gemini-embedding-001", "token": f"{BETO_MODEL}@{BETO_REVISION}", "occurrence_pos": SPACY_POS_MODEL, "calibrator_features": "5"},
        "asset_refs": asset_refs,
        "parameters": {"menu_prior": 0.02, "menu_prior_decay": 0.5, "pos_filter": "bridged-occurrence-pos/v1", "clitic_gate": "se-only", "tuple_vote_minimum_gap": 0.02, "calibrator_release_role": "evidence_only"},
        "optional_methods": {"alignment": "disabled", "generative_escalation": "disabled"},
        "random_seed": 0,
    }
    bundle = {
        "bundle_version": BUNDLE_VERSION, "run_id": run_id, "language": "es", "mode": "lyrics",
        "coverage": "complete_request_pool", "request_file_content_id": file_content_id(request_path),
        "sense_menu_content_id": file_content_id(menu_path), "method": method, "results": results,
    }
    target = (
        workspace.root / "raw/wsd/results/es/lyrics" / f"{run_id}-{METHOD_PROFILE}.json"
        if output_path is None else output_path.expanduser().resolve()
    )
    try:
        target.relative_to((workspace.root / "raw/wsd").resolve())
    except ValueError as error:
        raise LyricsWSDExecutionError("WSD result bundle must be written inside workspace/raw/wsd") from error
    if target.exists():
        raise LyricsWSDExecutionError(f"WSD result bundle already exists: {target}")
    atomic_write(target, bundle, workspace.root / ".fluency/temporary")
    return target
