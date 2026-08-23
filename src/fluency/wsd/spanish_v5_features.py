"""Frozen feature contract for the retained Spanish v5 calibrator."""

from __future__ import annotations

import re


FEATURE_VERSION = 5
TOKEN = re.compile(r"[a-záéíóúüñ0-9']+")
COMPANION = re.compile(r'used with\s+"([^"]+)"|used with\s+([a-záéíóúüñ]+)', re.I)
STRUCTURES = (
    ("gerund", re.compile(r"\bgerund\b|\bprogressive construction", re.I)),
    ("participle", re.compile(r"\bparticiple\b|\bpassive voice\b", re.I)),
    ("infinitive", re.compile(r"\binfinitive\b", re.I)),
)
GERUND = re.compile(r"\w+(?:ando|iendo|yendo)$", re.I)
INFINITIVE = re.compile(r"\w{3,}(?:ar|er|ir)$", re.I)
PARTICIPLE = re.compile(r"\w+(?:ado|ada|ados|adas|ido|ida|idos|idas)$", re.I)
IRREGULAR_PARTICIPLES = frozenset({
    "hecho", "dicho", "visto", "puesto", "escrito", "roto", "vuelto",
    "muerto", "abierto", "cubierto", "resuelto", "impreso", "frito",
})


def _context(sense: dict) -> str:
    metadata = sense.get("provider_metadata") or {}
    value = metadata.get("context")
    return value if isinstance(value, str) else str(sense.get("definition") or "")


def _companion(sense: dict) -> str | None:
    match = COMPANION.search(_context(sense))
    if match is None:
        return None
    value = (match.group(1) or match.group(2) or "").strip().lower()
    return value or None


def _structure(sense: dict) -> str | None:
    context = _context(sense)
    for name, pattern in STRUCTURES:
        if pattern.search(context):
            return name
    return None


def _structure_satisfied(kind: str | None, word: str, sentence: str) -> bool:
    if not kind:
        return True
    tokens = TOKEN.findall(sentence.lower())
    try:
        index = tokens.index(word.lower())
        window = tokens[index + 1:index + 4]
    except ValueError:
        window = tokens
    if kind == "gerund":
        return any(GERUND.match(token) for token in window)
    if kind == "participle":
        return any(PARTICIPLE.match(token) or token in IRREGULAR_PARTICIPLES for token in window)
    if kind == "infinitive":
        return any(INFINITIVE.match(token) for token in window)
    return True


def companion_features(word: str, sentence: str, senses: list[dict], predicted: dict) -> list[float]:
    companions = {sense["sense_id"]: _companion(sense) for sense in senses}
    companions = {key: value for key, value in companions.items() if value}
    if not companions:
        return [0.0] * 5
    tokens = TOKEN.findall(sentence.lower())
    token_set = set(tokens)
    predicted_companion = companions.get(predicted["sense_id"])
    tuples_with = {
        (sense["_headword"], sense["_pos"])
        for sense in senses if sense["sense_id"] in companions
    }
    all_tuples = {(sense["_headword"], sense["_pos"]) for sense in senses}
    present = adjacent = 0.0
    if predicted_companion:
        parts = predicted_companion.split()
        present = float(all(part in token_set for part in parts))
        if present and word.lower() in tokens:
            word_index = tokens.index(word.lower())
            adjacent = float(any(abs(index - word_index) <= 2 for index, token in enumerate(tokens) if token == parts[0]))
    return [
        1.0, float(predicted_companion is not None), present, adjacent,
        float(bool(tuples_with) and tuples_with != all_tuples),
    ]


def structural_features(word: str, sentence: str, senses: list[dict], predicted: dict) -> list[float]:
    kinds = {sense["sense_id"]: _structure(sense) for sense in senses}
    if not any(kinds.values()):
        return [0.0] * 5
    predicted_kind = kinds.get(predicted["sense_id"])
    tuples_with = {
        (sense["_headword"], sense["_pos"])
        for sense in senses if kinds[sense["sense_id"]]
    }
    all_tuples = {(sense["_headword"], sense["_pos"]) for sense in senses}
    satisfied = float(bool(predicted_kind) and _structure_satisfied(predicted_kind, word, sentence))
    alternate = 0.0
    predicted_tuple = (predicted["_headword"], predicted["_pos"])
    for sense in senses:
        kind = kinds[sense["sense_id"]]
        if (
            sense["sense_id"] != predicted["sense_id"] and kind
            and (sense["_headword"], sense["_pos"]) == predicted_tuple
            and _structure_satisfied(kind, word, sentence) and not satisfied
        ):
            alternate = 1.0
            break
    return [
        1.0, float(predicted_kind is not None), satisfied,
        float(bool(tuples_with) and tuples_with != all_tuples), alternate,
    ]


def build_features(
    *, tuple_gap: float, class_gap: float, tuple_count: int, leaf_count: int,
    sentence_length: int, predicted_tuple: tuple[str, str], empty_translation: bool,
    token_available: float, token_gap: float, token_agrees: float,
    companion: list[float], structural: list[float],
) -> list[float]:
    headword, pos = predicted_tuple
    return [
        float(tuple_gap), float(class_gap), float(class_gap >= 0.999),
        float(tuple_count), float(leaf_count), leaf_count / max(tuple_count, 1),
        float(sentence_length), float(headword.endswith("se")), float(pos == "VERB"),
        float(pos in ("NOUN", "ADJ")), float(empty_translation),
        float(token_available), float(token_gap), float(token_agrees),
        *companion, *structural,
    ]
