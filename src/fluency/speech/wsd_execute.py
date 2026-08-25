"""Execute v7 closed-menu WSD over one planned speech run and emit a bundle.

Mirrors the lyrics executor: the pipeline imports a complete, externally produced
bundle rather than calling models inside a stage, so a stage never depends on a
network or a GPU and a run can be re-imported byte-identically.

The bundle covers the COMPLETE candidate pool by contract. Every harvested
candidate gets a typed outcome — assigned, abstained, rejected or no_menu —
because an occurrence that quietly disappears is indistinguishable from one that
was never considered.

Embeddings are joined by EXACT TEXT, never by row position. A cache miss is
embedded into a run-scoped delta and reported; it is never silently skipped and
never filled from a neighbouring row.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
import os
import time
from pathlib import Path
from typing import Any, Iterable, Sequence

from fluency.nlp.models import pin, setting
from fluency.nlp.embeddings import ensure_embeddings, load_cache
from fluency.nlp.pos import load_pinned
from fluency.core.hashing import canonical_content_id, file_content_id
from fluency.wsd.commit import CommitPolicy
from fluency.wsd.contracts import SelectedTuple, SelectionProjection, WSDAssignment
from fluency.wsd.features import SpecialistFeature
from fluency.wsd.disposition import DispositionPolicy
from fluency.wsd.gloss_scoring import LeafScore
from fluency.wsd.languages.spanish import SpanishV5CandidatePolicy, SpanishWSDAdapter
from fluency.wsd.menus import MenuAnalysis, SenseLeaf
from fluency.wsd.multiword import index_multiword_senses, multiword_analyses
from fluency.wsd.sampling import (
    DEFAULT_EXECUTION_CAP,
    OccurrenceSamplingPolicy,
    sampling_report,
    select_occurrences,
    sole_leaf,
)
from fluency.wsd.runner import (
    ClosedMenuWSDRunner,
    WSDComponents,
    WSDExecutionProfile,
    WSDRequest,
)

BUNDLE_VERSION = "wsd-assignment-bundle/v1"
EMBED_MODEL = setting("exact-text-embedding", "name")
TASK_TYPE = setting("exact-text-embedding", "task_type")
SPACY_POS_MODEL = pin("occurrence-pos")
SPACY_POS_MODEL_NAME, SPACY_POS_MODEL_VERSION = SPACY_POS_MODEL.split("@", 1)
SUPPORTED_PROFILE_CONSTRAINT_MODES = {
    "es-v6-1": "filter",
    "es-v7-1": "filter",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def build_analyses(
    card: dict[str, Any], *, menu_source_adapter: str
) -> tuple[MenuAnalysis, ...]:
    """Rebuild exact MenuAnalysis records from the immutable menu stage."""

    built: list[MenuAnalysis] = []
    for analysis in card["analyses"]:
        senses = tuple(
            SenseLeaf(
                sense_id=leaf["sense_id"],
                translation=leaf.get("translation") or "",
                definition=leaf.get("definition") or "",
                source_reference=leaf.get("source_reference") or "spanishdict",
                provider_metadata=leaf.get("provider_metadata") or {},
                specialist_features=tuple(
                    SpecialistFeature.from_dict(item)
                    for item in leaf.get("specialist_features", [])
                ),
            )
            for leaf in analysis["senses"]
        )
        built.append(
            MenuAnalysis(
                menu_analysis_id=analysis["menu_analysis_id"],
                card_id=card["card_id"],
                surface_form=card["surface_form"],
                headword=analysis["headword"],
                part_of_speech=analysis["part_of_speech"],
                source_adapter=analysis.get("source_adapter") or menu_source_adapter,
                source_analysis_key=analysis["source_analysis_key"],
                senses=senses,
                provider_metadata=analysis.get("provider_metadata") or {},
            )
        )
    return tuple(built)


def occurrence_pos_tags(
    work: Sequence[tuple[dict[str, Any], dict[str, Any], str, str, str]],
    *,
    model_name: str = SPACY_POS_MODEL_NAME,
    model: Any | None = None,
) -> tuple[
    dict[tuple[str, str], str | None],
    dict[tuple[str, str], dict[str, Any]],
]:
    """Tag each exact speech occurrence, refusing ambiguous repeated uses.

    The sentence bank has no POS field.  v6 accepted ``observed_pos`` in the
    runner but never populated it, so its AUX bridge could not affect a deck.
    Repeated surface occurrences are used only when every occurrence has the
    same observed POS; disagreement is explicit and passes ``None``.
    """

    if model_name != SPACY_POS_MODEL_NAME:
        raise RuntimeError(
            f"occurrence POS model does not match the pinned revision {SPACY_POS_MODEL}"
        )
    model = load_pinned(SPACY_POS_MODEL, model=model)
    grouped: dict[
        str,
        list[
            tuple[
                tuple[str, str], str, tuple[int, int] | None, str | None, bool
            ]
        ],
    ] = defaultdict(list)
    for card, _menu_card, sentence_id, text, _translation in work:
        target_span = card.get("target_span")
        model_text = text
        model_span = None if target_span is None else tuple(target_span)
        model_observed = card.get("target_observed_form")
        normalized_for_model = False
        if model_span is not None:
            start, end = model_span
            observed_text = text[start:end]
            expected_observed = model_observed or card["display_form"]
            if observed_text != expected_observed:
                raise ValueError(
                    "target span does not reproduce the persisted observed form"
                )
            canonical = card["display_form"]
            if observed_text.casefold() != canonical.casefold():
                model_text = text[:start] + canonical + text[end:]
                model_span = (start, start + len(canonical))
                model_observed = canonical
                normalized_for_model = True
        grouped[model_text].append((
            (card["card_id"], sentence_id),
            card["display_form"],
            model_span,
            model_observed,
            normalized_for_model,
        ))
    adapter = SpanishWSDAdapter()
    observed: dict[tuple[str, str], str | None] = {}
    diagnostics: dict[tuple[str, str], dict[str, Any]] = {}
    for document, text in zip(model.pipe(grouped, batch_size=1), grouped):
        for (
            key,
            surface,
            target_span,
            target_observed_form,
            normalized_for_model,
        ) in grouped[text]:
            if target_span is None:
                occurrences = adapter.locate(text, surface)
            else:
                start, end = target_span
                if not (0 <= start < end <= len(text)):
                    raise ValueError("target span falls outside the POS context")
                observed_text = text[start:end]
                expected_observed = target_observed_form or surface
                if observed_text != expected_observed:
                    raise ValueError(
                        "target span does not reproduce the persisted observed form"
                    )
                from fluency.wsd.languages.base import TargetOccurrence
                occurrences = (
                    TargetOccurrence(observed_text, surface.casefold(), start, end),
                )
            tags: list[str] = []
            for occurrence in occurrences:
                overlapping = [
                    token
                    for token in document
                    if token.idx < occurrence.end
                    and token.idx + len(token.text) > occurrence.start
                ]
                if overlapping:
                    tags.append(overlapping[0].pos_)
            unique = sorted(set(tags))
            value = unique[0] if len(unique) == 1 else None
            status = (
                "observed"
                if len(unique) == 1
                else "ambiguous_repeated_occurrence"
                if len(unique) > 1
                else "unavailable"
            )
            observed[key] = value
            diagnostics[key] = {
                "status": status,
                "observed_pos": value,
                "occurrence_tags": tags,
                "canonicalized_target_for_model": normalized_for_model,
                "model_revision": SPACY_POS_MODEL,
            }
    return observed, diagnostics


class ExactTextGlossScorer:
    """Cosine between the sentence vector and each leaf's gloss vector.

    Both sides are looked up by exact text. A multiword candidate renders in the
    same shape as a menu leaf, so the competition measures meaning rather than
    formatting.
    """

    model_revision = EMBED_MODEL

    def __init__(self, vectors: dict[str, Any]) -> None:
        self.vectors = vectors

    def score(self, sentence: str, analyses: tuple[MenuAnalysis, ...]) -> Sequence[LeafScore]:
        import numpy as np

        query = self.vectors.get(sentence)
        scores: list[LeafScore] = []
        for analysis in analyses:
            for leaf in analysis.senses:
                gloss = leaf.gloss_text
                if query is None:
                    raise KeyError(f"missing exact-text embedding for sentence: {sentence!r}")
                if not gloss.strip():
                    # An empty-gloss leaf cannot be rendered on a card, so it
                    # loses by construction rather than being silently dropped
                    # from the candidate pool.
                    value = -1.0
                else:
                    vector = self.vectors.get(gloss)
                    if vector is None:
                        raise KeyError(f"missing exact-text embedding for gloss: {gloss!r}")
                    value = float(np.dot(query, vector))
                scores.append(
                    LeafScore(
                        menu_analysis_id=analysis.menu_analysis_id,
                        sense_id=leaf.sense_id,
                        score=value,
                    )
                )
        return scores


def embed_texts(texts: Sequence[str], *, api_key: str) -> dict[str, Any]:
    import numpy as np
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    out: dict[str, Any] = {}
    started = time.time()
    done = 0
    for index in range(0, len(texts), 50):
        batch = list(texts[index : index + 50])
        # Pace under the provider's per-minute cap rather than discovering it.
        while done + len(batch) > 2200 / 60 * (time.time() - started) + 50:
            time.sleep(0.5)
        for attempt in range(6):
            try:
                response = client.models.embed_content(
                    model=EMBED_MODEL,
                    contents=batch,
                    config=types.EmbedContentConfig(task_type=TASK_TYPE),
                )
                break
            except Exception:
                if attempt == 5:
                    raise
                time.sleep(8 * (attempt + 1))
        for text, item in zip(batch, response.embeddings):
            vector = np.asarray(item.values, dtype=np.float32)
            out[text] = vector / np.linalg.norm(vector)
        done += len(batch)
        if done % 2000 < 50:
            print(f"    embedded {done:,}/{len(texts):,}", flush=True)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--multiword-inventory", type=Path)
    parser.add_argument(
        "--profile-id",
        choices=tuple(SUPPORTED_PROFILE_CONSTRAINT_MODES),
        default="es-v7-1",
    )
    parser.add_argument(
        "--spacy-model",
        choices=(SPACY_POS_MODEL_NAME,),
        default=SPACY_POS_MODEL_NAME,
        help=f"pinned spaCy model used for exact occurrence POS tagging ({SPACY_POS_MODEL})",
    )
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument(
        "--embedding-cache", type=Path,
        help="shared exact-text vector cache. Defaults to a per-LANGUAGE cache "
             "in the workspace, not a per-run one: gloss vectors are a property "
             "of the dictionary and sentence vectors of the corpus, so both "
             "outlive any single run. A per-run cache silently re-embeds "
             "everything each time and destroys the amortisation.",
    )
    parser.add_argument(
        "--execution-cap", type=int, default=DEFAULT_EXECUTION_CAP,
        help="max occurrences per surface card that reach WSD (default: the "
             "mature historical 10). Separate from the study-example cap.",
    )
    args = parser.parse_args()

    stages = args.run_dir / "stages"
    inventory_path = stages / "01_inventory/output/inventory.json"
    menu_path = stages / "02_sense_menu/output/sense-menu.json"
    candidates_path = stages / "03_sentence_harvest/output/candidates.json"
    bank_path = stages / "03_sentence_harvest/output/sentence-bank.jsonl"

    menu = load_json(menu_path)
    menu_source_adapter = str(menu.get("source_adapter") or "")
    if not menu_source_adapter:
        raise SystemExit("sense menu does not declare its source adapter")
    menu_stage_content_id = file_content_id(menu_path)
    candidates = load_json(candidates_path)
    run_id = candidates["run_id"]
    menu_by_card = {card["card_id"]: card for card in menu["cards"]}
    sentences = {
        row["sentence_id"]: row
        for row in (json.loads(line) for line in bank_path.read_text(encoding="utf-8").splitlines() if line.strip())
    }

    multiword_index = None
    multiword_content_id = None
    if args.multiword_inventory:
        multiword_index = index_multiword_senses(load_json(args.multiword_inventory))
        multiword_content_id = file_content_id(args.multiword_inventory)
        print(f"multiword inventory: {len(multiword_index):,} attach words")

    profile = WSDExecutionProfile(
        token_tuple_vote=False,
        tuple_vote_minimum_margin=0.0,
        calibration=False,
        alignment=False,
        generative_escalation=False,
        disposition=DispositionPolicy(minimum_confidence=None, weak="retain"),
        candidate_preparation=True,
        multiword_candidates=multiword_index is not None,
        commit=CommitPolicy(),
    )

    # --- gather every exact text the run needs, then embed the misses ---
    policy = OccurrenceSamplingPolicy(cap_per_surface=args.execution_cap)
    needed: set[str] = set()
    work: list[tuple[dict[str, Any], dict[str, Any], str, str, str]] = []
    capped: list[tuple[dict[str, Any], dict[str, Any], str]] = []
    deterministic: list[tuple[dict[str, Any], dict[str, Any], str]] = []
    selections = []
    for card in candidates["cards"]:
        card_id = card["card_id"]
        menu_card = menu_by_card.get(card_id)
        selection = select_occurrences(card["candidates"], policy, card_id=card_id)
        selections.append(selection)
        for sentence_id in selection.overflow:
            capped.append((card, menu_card, sentence_id))
        analyses = (
            build_analyses(menu_card, menu_source_adapter=menu_source_adapter)
            if menu_card and menu_card["analyses"]
            else ()
        )
        only = sole_leaf(analyses) if analyses else None
        for sentence_id in selection.selected:
            row = sentences.get(sentence_id)
            if row is None:
                continue
            text = row["target"]["text"]
            has_multiword_alternative = bool(
                multiword_index is not None
                and next(
                    iter(
                        multiword_analyses(
                            card_id=card_id,
                            surface_form=card["display_form"],
                            sentence=text,
                            index=multiword_index,
                        )
                    ),
                    None,
                )
                is not None
            )
            if only is not None and not has_multiword_alternative:
                # A one-sense menu is not disambiguation. Assign it without any
                # contextual model and mark it as a default, so the auditor can
                # tell it apart from a genuine multi-option decision.
                deterministic.append((card, menu_card, sentence_id))
                continue
            translation = (row.get("translation") or {}).get("text") or ""
            work.append((card, menu_card, sentence_id, text, translation))
            needed.add(text)
    report = sampling_report(selections, policy)
    print(
        f"sampling: cap {policy.cap_per_surface}/surface -> "
        f"{report['occurrences_selected']:,} selected, "
        f"{report['occurrences_not_evaluated']:,} not evaluated, "
        f"{report['surface_cards_reaching_cap']:,} cards reached the cap"
    )
    print(f"  deterministic single-option (no model): {len(deterministic):,}")
    print(f"  model-scored provider/MWE assignments:  {len(work):,}")
    print(f"Tagging occurrence POS with {args.spacy_model} (batch size 1)...", flush=True)
    observed_pos, observed_pos_evidence = occurrence_pos_tags(
        work, model_name=args.spacy_model
    )
    if multiword_index is not None:
        for card, menu_card, _sentence_id, text, _translation in work:
            for analysis, _entry, _span in multiword_analyses(
                card_id=card["card_id"], surface_form=card["display_form"],
                sentence=text, index=multiword_index,
            ):
                needed.add(analysis.senses[0].gloss_text)
    scored_cards = {card["card_id"] for card, _menu, _sid, _t, _tr in work}
    for card in menu["cards"]:
        if card["card_id"] not in scored_cards:
            continue
        for analysis in card["analyses"]:
            for leaf in analysis["senses"]:
                translation = leaf.get("translation") or ""
                definition = leaf.get("definition") or ""
                needed.add(" — ".join(value for value in (translation, definition) if value))

    # SpanishDict publishes leaves with no translation, so gloss_text can be the
    # empty string. Embedding "" fails and retries forever; an empty gloss is a
    # candidate that cannot be scored, not a transport error.
    empty = sum(1 for text in needed if not text.strip())
    needed = {text for text in needed if text.strip()}
    print(f"candidate assignments: {len(work):,}   exact texts to embed: {len(needed):,}"
          f"   (skipped {empty} empty gloss texts)")
    # run_dir is <workspace>/runs/<language>/<mode>/<run-id>, so the workspace
    # root is four levels up. Getting this wrong is silent: the cache is simply
    # written somewhere nothing will look for it and every run re-embeds.
    workspace_root = args.run_dir.resolve().parents[3]
    cache_path = args.embedding_cache or (
        # Named for the model that produced it: vectors from different models
        # must never share a store.
        workspace_root / "embeddings" / "es" / f"exact-text-{EMBED_MODEL}.npz"
    )
    api_key = ""
    if args.env_file.is_file():
        for line in args.env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("GEMINI_API_KEY"):
                api_key = line.split("=", 1)[1].strip().strip('"').strip("'")

    cached_before = len(load_cache(cache_path))
    # Shared store, resumable writer: an interrupted embed keeps every vector
    # already paid for instead of starting the run again from nothing.
    vectors = ensure_embeddings(cache_path, needed, api_key=api_key or None)
    missing = [text for text in needed if text not in vectors]
    if missing:
        raise SystemExit(f"{len(missing):,} exact-text embeddings could not be created")
    newly_embedded = max(0, len(vectors) - cached_before)
    print(f"exact-text cache: {len(vectors):,} vectors at {cache_path}")
    print(f"reused {len(needed) - newly_embedded:,}, newly embedded {newly_embedded:,}")

    components = WSDComponents(
        language=SpanishWSDAdapter(),
        gloss=ExactTextGlossScorer(vectors),
        candidate_policy=SpanishV5CandidatePolicy(
            constraint_mode=SUPPORTED_PROFILE_CONSTRAINT_MODES[args.profile_id]
        ),
        multiword_index=multiword_index,
        multiword_inventory_content_id=multiword_content_id,
        context_model_revisions={"occurrence_pos": SPACY_POS_MODEL},
    )
    runner = ClosedMenuWSDRunner(profile, components)

    assignments: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for card, menu_card, sentence_id, text, translation in work:
        analyses = (
            build_analyses(menu_card, menu_source_adapter=menu_source_adapter)
            if menu_card
            else ()
        )
        request_key = (card["card_id"], sentence_id)
        request = WSDRequest(
            card_id=card["card_id"],
            surface_form=card["display_form"],
            sentence_id=sentence_id,
            sentence=text,
            translation=translation,
            sense_menu_content_id=menu_stage_content_id if analyses else None,
            analyses=analyses,
            observed_pos=observed_pos.get(request_key),
            observed_pos_evidence=observed_pos_evidence.get(request_key),
        )
        assignment = runner.assign(request)
        counts[assignment.status] = counts.get(assignment.status, 0) + 1
        assignments.append(assignment.to_dict())

    # Occurrences above the cap: no model looked at them. They are reported,
    # never dropped, and never described as sense-assigned.
    for card, menu_card, sentence_id in capped:
        has_menu = bool(menu_card and menu_card["analyses"])
        assignments.append(
            WSDAssignment(
                card_id=card["card_id"],
                surface_form=card["display_form"],
                sentence_id=sentence_id,
                status="not_evaluated_example_cap" if has_menu else "no_menu",
                sense_menu_content_id=menu_stage_content_id if has_menu else None,
                menu_analysis_id=None,
                selected_sense_id=None,
                selected_tuple=None,
                decision_path=(),
                evidence={"reason": "per_surface_wsd_execution_cap",
                          "cap_per_surface": policy.cap_per_surface} if has_menu
                         else {"reason": "no_candidate_analysis"},
                confidence=None,
                model_revisions={
                    "gloss": EMBED_MODEL,
                    "occurrence_pos": SPACY_POS_MODEL,
                } if has_menu else {},
            ).to_dict()
        )
        counts["not_evaluated_example_cap" if has_menu else "no_menu"] = counts.get(
            "not_evaluated_example_cap" if has_menu else "no_menu", 0) + 1

    # One-sense menus: assigned without any contextual model, and marked so.
    for card, menu_card, sentence_id in deterministic:
        analyses = build_analyses(
            menu_card, menu_source_adapter=menu_source_adapter
        )
        analysis, leaf = sole_leaf(analyses)
        assignments.append(
            WSDAssignment(
                card_id=card["card_id"],
                surface_form=card["display_form"],
                sentence_id=sentence_id,
                status="assigned",
                sense_menu_content_id=menu_stage_content_id,
                menu_analysis_id=analysis.menu_analysis_id,
                selected_sense_id=leaf.sense_id,
                selected_tuple=SelectedTuple(
                    headword=analysis.headword, part_of_speech=analysis.part_of_speech
                ),
                decision_path=("constrain",),
                evidence={
                    "reason": "sole_menu_sense",
                    "candidate_leaf_count": 1,
                    "commit": {
                        "selected_ref": {
                            "menu_analysis_id": analysis.menu_analysis_id,
                            "sense_id": leaf.sense_id,
                        },
                        "emitted_level": "leaf",
                        "raw_axis_margins": {"leaf": 1.0, "glosskey": 1.0, "tuple": 1.0},
                        "axis_confidences": {"leaf": None, "glosskey": None, "tuple": None},
                        "calibration": {"status": "deterministic", "artifact_content_id": None},
                    },
                },
                confidence=None,
                model_revisions={
                    "gloss": EMBED_MODEL,
                    "occurrence_pos": SPACY_POS_MODEL,
                },
                emitted_level="leaf",
                decision_kind="deterministic_default",
                selection_projections={
                    "provider_only": SelectionProjection(
                        menu_analysis_id=analysis.menu_analysis_id,
                        selected_sense_id=leaf.sense_id,
                        selected_tuple=SelectedTuple(
                            headword=analysis.headword,
                            part_of_speech=analysis.part_of_speech,
                        ),
                        source_kind="provider",
                        selected_score=1.0,
                        runner_up_score=None,
                        raw_margin=None,
                        rank=1,
                        emitted_level="leaf",
                        raw_axis_margins={
                            "leaf": 1.0,
                            "glosskey": 1.0,
                            "tuple": 1.0,
                        },
                    )
                },
                active_selection_projection="provider_only",
            ).to_dict()
        )
        counts["assigned"] = counts.get("assigned", 0) + 1

    bundle = {
        "bundle_version": BUNDLE_VERSION,
        "sampling": report,
        "run_id": run_id,
        "language": "es",
        "mode": "speech",
        "coverage": "complete_candidate_pool",
        "method": {
            "profile_id": args.profile_id,
            "implementation_version": "fluency.speech.wsd_execute/v7",
            "implementation_content_id": file_content_id(Path(__file__)),
            "model_revisions": {
                "gloss": EMBED_MODEL,
                "occurrence_pos": SPACY_POS_MODEL,
            },
            "constraint_mode": SUPPORTED_PROFILE_CONSTRAINT_MODES[args.profile_id],
            "random_seed": 0,
        },
        "inputs": {
            "inventory": file_content_id(inventory_path),
            "sense_menu": file_content_id(menu_path),
            "candidates": file_content_id(candidates_path),
            "sentence_bank": file_content_id(bank_path),
            **(
                {"multiword_inventory": multiword_content_id}
                if multiword_content_id
                else {}
            ),
        },
        "assignments": assignments,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(bundle, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"\nwrote {args.out}")
    for status, count in sorted(counts.items()):
        print(f"   {status:<12}{count:>7,}")


if __name__ == "__main__":
    main()
