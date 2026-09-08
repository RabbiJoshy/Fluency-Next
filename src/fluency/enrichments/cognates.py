"""Build a cognate layer: for one deck language, how transparent each surface
is to a speaker of each language the learner already reads.

The layer sits beside a release rather than inside it, and that placement is
deliberate. Cognate transparency is a property of ``(surface, language pair)``,
not of a particular deck — the same Czech word is equally recognisable to a
Polish reader whichever release it ships in. Keeping it out of the immutable
release also means adding a known language never re-cuts a deck.

The mapping is keyed by surface and by language, not by release. A score does
not expire when the deck changes: whether ``každý`` is free to a Polish reader
has nothing to do with which deck it ships in. A surface the mapping has not
seen is simply not excluded, and scores for surfaces the deck no longer carries
go unused — both cost at most one easy card. The release it was built from is
recorded as provenance, so you can tell what it was computed against, but it is
information rather than a gate.

The known side needs an English-glossed dictionary for the language the learner
reads. English itself needs none — the deck's glosses are already English, so
each gloss word stands as its own entry, and the same engine runs unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from fluency.core.hashing import file_content_id
from fluency.features.cognates import (
    COGNATE_SCORE_SCHEMA,
    CognatePolicy,
    build_known_index,
    live_glosses,
    load_policy,
    normalise_gloss,
    score_deck,
)


LAYER_VERSION = "cognate-layer/v1"


class CognateLayerError(ValueError):
    """The inputs cannot produce a layer that could be trusted."""


def _target_glosses(index_rows: Iterable[Mapping[str, Any]], policy: CognatePolicy):
    """Surface -> the English senses the deck actually teaches for it.

    The release index is preferred over the raw dictionary here: it holds the
    senses that survived selection, which is what the learner will meet. A
    dictionary sense the deck never shows should not make a word count as
    already-known.
    """

    surfaces: dict[str, set[str]] = {}
    for row in index_rows:
        word = str(row.get("word") or "").strip().lower()
        if not word:
            continue
        glosses = surfaces.setdefault(word, set())
        for meaning in row.get("meanings") or []:
            if not isinstance(meaning, Mapping):
                continue
            for part in str(meaning.get("translation") or "").split(","):
                text = normalise_gloss(part)
                if text and len(text.split()) <= policy.gloss_maximum_words:
                    glosses.add(text)
    return {word: frozenset(glosses) for word, glosses in surfaces.items() if glosses}


def _english_index_entries(target: Mapping[str, frozenset[str]]):
    """Treat every English gloss word as its own dictionary entry.

    English is the pivot the deck already carries, so a Czech word is compared
    against the English words that translate it. Synthesising entries keeps one
    scoring engine rather than a second code path for the free case.
    """

    seen: set[str] = set()
    for glosses in target.values():
        for gloss in glosses:
            for token in gloss.split():
                if token in seen:
                    continue
                seen.add(token)
                yield {"word": token, "pos": "noun", "senses": [{"glosses": [token]}]}


def _extract_entries(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as error:
                raise CognateLayerError(f"{path} is not a JSONL dictionary extract") from error


def build_cognate_layer(
    *,
    language: str,
    release_index: Path,
    known_extracts: Mapping[str, Path | None],
    config_root: Path,
    release_id: str,
) -> dict[str, Any]:
    """Score one deck's surfaces against every known language given.

    ``known_extracts`` maps a language code to its English-glossed dictionary
    extract, or to ``None`` for English, which needs none.
    """

    if not known_extracts:
        raise CognateLayerError("a cognate layer needs at least one known language")
    rows = json.loads(release_index.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise CognateLayerError("release index must be a list of deck rows")

    scores: dict[str, dict[str, Any]] = {}
    coverage: dict[str, Any] = {}
    policies: dict[str, Any] = {}
    for known_language in sorted(known_extracts):
        policy = load_policy(config_root, language, known_language)
        target = _target_glosses(rows, policy)
        extract = known_extracts[known_language]
        if known_language == "en" and extract is None:
            entries = _english_index_entries(target)
            source = {"kind": "deck_glosses", "content_id": None}
        else:
            if extract is None:
                raise CognateLayerError(
                    f"{known_language} needs a dictionary extract; only en may omit one"
                )
            entries = _extract_entries(Path(extract))
            source = {"kind": "wiktionary_extract", "content_id": file_content_id(Path(extract))}
        index = build_known_index(entries, policy)
        matched = score_deck(target, index)
        for surface, match in matched.items():
            scores.setdefault(surface, {})[known_language] = match.to_dict()
        coverage[known_language] = {
            "deck_surfaces": len(target),
            "scored_surfaces": len(matched),
            "known_entries": len(index.words),
            "source": source,
        }
        policies[known_language] = policy.to_dict()

    return {
        "layer_version": LAYER_VERSION,
        "score_schema": COGNATE_SCORE_SCHEMA,
        "language": language,
        "layer_kind": "cognates",
        # Card identity is the observed surface form, so that is the join key.
        # Nothing here is keyed by lemma or sense.
        "join_key": "surface",
        # Provenance, not a key: this says what the mapping was computed from,
        # and nothing looks the file up by it.
        "built_from": {
            "release_id": release_id,
            "release_index_content_id": file_content_id(release_index),
        },
        "known_languages": sorted(known_extracts),
        "policies": policies,
        "coverage": coverage,
        "scores": scores,
    }


def build_app_cognates(layer: Mapping[str, Any]) -> dict[str, Any]:
    """The app-facing view: surface -> {known language: score}.

    The app only needs the number it thresholds. Which known word produced it,
    and how form and meaning contributed, stay in the layer for auditing — the
    same split the release makes everywhere else between what ships and what is
    kept to explain it.
    """

    scores = {
        surface: {
            known: round(float(match["score"]), 3)
            for known, match in sorted(per_language.items())
        }
        for surface, per_language in sorted(layer.get("scores", {}).items())
    }
    # Each known language carries its own cutoff. The app never compares one
    # language's score with another's — it asks each in turn whether this word
    # is already free — so the numbers do not need a common scale.
    thresholds = {
        known: policy["default_threshold"]
        for known, policy in sorted(layer.get("policies", {}).items())
    }
    return {
        "schema": COGNATE_SCORE_SCHEMA,
        "language": layer["language"],
        "known_languages": list(layer["known_languages"]),
        "built_from_release_id": layer.get("built_from", {}).get("release_id"),
        "thresholds": thresholds,
        "scores": scores,
    }
