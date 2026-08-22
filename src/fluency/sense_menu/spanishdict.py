"""Offline SpanishDict cache adapter with explicit surface-card binding."""

from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
import unicodedata
from typing import Any, Iterable

from fluency.core.hashing import canonical_content_id, file_content_id
from fluency.wsd.menus import MenuAnalysis, SenseLeaf, build_analysis_id


ADAPTER_ID = "spanishdict-sense-menu/v1"
MENU_VERSION = "sense-menu/v1"
REPORT_VERSION = "sense-menu-report/v1"
SNAPSHOT_VERSION = "spanishdict-snapshot/v1"
REQUIRED_FILES = (
    "surface_cache.json",
    "headword_cache.json",
    "spanish_forms.json",
    "conjugation_reverse.json",
)
CLITIC_SUFFIXES = (
    "selos", "selas", "melos", "melas", "noslo", "nosla", "telos", "telas",
    "selo", "sela", "melo", "mela", "telo", "tela", "nos", "los", "las",
    "les", "me", "te", "se", "lo", "la", "le", "os",
)


class SpanishDictMenuError(ValueError):
    """Raised when a SpanishDict snapshot or menu result is ambiguous."""


def _load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise SpanishDictMenuError(f"SpanishDict snapshot file is missing: {path}") from error
    except json.JSONDecodeError as error:
        raise SpanishDictMenuError(f"SpanishDict snapshot file is invalid JSON: {path}") from error
    if not isinstance(value, dict):
        raise SpanishDictMenuError(f"SpanishDict snapshot file must be an object: {path}")
    return value


def _deaccent(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(
        character
        for character in decomposed
        if unicodedata.category(character) != "Mn" and character not in "'’"
    )


def _normalize_analyses(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    analyses: list[dict[str, Any]] = []
    for raw in value:
        if not isinstance(raw, dict):
            continue
        senses = raw.get("senses") or []
        if isinstance(senses, dict):
            senses = list(senses.values())
        analyses.append(
            {
                "headword": raw.get("headword"),
                "senses": [deepcopy(item) for item in senses if isinstance(item, dict)],
            }
        )
    return analyses


def _analysis_signature(analysis: dict[str, Any]) -> tuple[object, tuple[tuple[str, str, str], ...]]:
    values = sorted(
        (
            str(sense.get("pos", "")),
            str(sense.get("translation", "")),
            str(sense.get("context", "")),
        )
        for sense in analysis.get("senses", [])
        if isinstance(sense, dict)
    )
    return analysis.get("headword"), tuple(values)


def _abbreviation_mismatch(surface: str, headword: object) -> bool:
    return isinstance(headword, str) and "." in headword and "." not in surface


def _phrase_only(analysis: dict[str, Any]) -> bool:
    senses = [item for item in analysis.get("senses", []) if isinstance(item, dict)]
    return bool(senses) and all(str(item.get("pos", "")).upper() == "PHRASE" for item in senses)


def _noun_stem(value: str) -> str:
    if value.endswith("es") and len(value) > 3:
        value = value[:-2]
    elif value.endswith("s") and len(value) > 2:
        value = value[:-1]
    if len(value) > 2 and value[-1] in "ao":
        value = value[:-1]
    return value


def _regular_noun_variant(surface: str, headword: str) -> bool:
    if headword.endswith("z") and surface == headword[:-1] + "ces":
        return True
    if surface.endswith("z") and headword == surface[:-1] + "ces":
        return True
    if surface in {headword + "s", headword + "es"} or headword in {
        surface + "s", surface + "es"
    }:
        return True
    surface_stem, headword_stem = _noun_stem(surface), _noun_stem(headword)
    return len(surface_stem) >= 3 and surface_stem == headword_stem and surface != headword


def _conjugation_variants(form: str) -> set[str]:
    clean = form.replace("'", "").replace("’", "")
    variants = {clean, clean + "s"}
    for suffix in CLITIC_SUFFIXES:
        if clean.endswith(suffix) and len(clean) > len(suffix) + 1:
            variants.update({clean[: -len(suffix)], clean[: -len(suffix)] + "s"})
    for value in list(variants):
        if value.endswith(("as", "os")):
            variants.add(value[:-2] + "o")
        elif value.endswith("a"):
            variants.add(value[:-1] + "o")
        if value.endswith("s"):
            variants.add(value[:-1])
    return variants


def _legacy_sense_ids(
    headword: str,
    senses: list[dict[str, Any]],
    used_ids: set[str],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for sense in senses:
        digest = hashlib.md5(
            f"{headword}|{sense.get('pos', '')}|{sense.get('translation', '')}".encode("utf-8"),
            usedforsecurity=False,
        ).hexdigest()
        sense_id = digest
        for length in range(3, len(digest) + 1):
            candidate = digest[:length]
            if candidate not in result and candidate not in used_ids:
                sense_id = candidate
                break
        result[sense_id] = deepcopy(sense)
        used_ids.add(sense_id)
    return result


@dataclass(slots=True)
class SpanishDictSenseMenuAdapter:
    """Rebuild closed menus from verified caches without network access."""

    path: Path
    language_code: str = "es"
    gloss_language: str = "en"
    source_edition: str = "spanishdict-pinned-snapshot"
    language_policy: dict[str, Any] | None = None
    snapshot_content_id: str = field(init=False)
    snapshot_id: str = field(init=False)
    surface_cache: dict[str, Any] = field(init=False)
    headword_cache: dict[str, Any] = field(init=False)
    spanish_forms: set[str] = field(init=False)
    conjugation_deaccented: dict[str, set[str]] = field(init=False)
    conjugation_original: dict[str, set[str]] = field(init=False)

    def __post_init__(self) -> None:
        self.path = self.path.expanduser().resolve()
        if self.language_code != "es" or self.gloss_language != "en":
            raise SpanishDictMenuError("SpanishDict adapter requires Spanish cards and English glosses")
        if not isinstance(self.language_policy, dict) or self.language_policy.get("provider") != "spanishdict":
            raise SpanishDictMenuError("explicit SpanishDict language policy is required")
        manifest = _load_object(self.path / "artifact.json")
        if (
            manifest.get("schema_version") != SNAPSHOT_VERSION
            or manifest.get("artifact_kind") != "dictionary_menu_source"
            or manifest.get("language") != "es"
            or manifest.get("provider") != "spanishdict"
        ):
            raise SpanishDictMenuError("unsupported SpanishDict snapshot manifest")
        records = {
            item.get("path"): item
            for item in manifest.get("content_files", [])
            if isinstance(item, dict) and isinstance(item.get("path"), str)
        }
        content_ids: dict[str, str] = {}
        for filename in REQUIRED_FILES:
            record = records.get(filename)
            if not isinstance(record, dict):
                raise SpanishDictMenuError(f"SpanishDict snapshot omits {filename}")
            content_id = file_content_id(self.path / filename)
            if content_id != f"sha256:{record.get('sha256')}":
                raise SpanishDictMenuError(f"SpanishDict snapshot hash changed: {filename}")
            content_ids[filename] = content_id
        self.snapshot_id = str(manifest.get("snapshot_id", ""))
        if not self.snapshot_id:
            raise SpanishDictMenuError("SpanishDict snapshot ID is missing")
        self.snapshot_content_id = canonical_content_id(
            {"manifest": file_content_id(self.path / "artifact.json"), "files": content_ids}
        )
        self.surface_cache = _load_object(self.path / "surface_cache.json")
        self.headword_cache = _load_object(self.path / "headword_cache.json")
        forms = _load_object(self.path / "spanish_forms.json")
        reverse = _load_object(self.path / "conjugation_reverse.json")
        self.spanish_forms = {_deaccent(str(value)) for value in forms}
        self.conjugation_deaccented = defaultdict(set)
        self.conjugation_original = defaultdict(set)
        for form, entries in reverse.items():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                lemma = entry.get("lemma") if isinstance(entry, dict) else None
                if isinstance(lemma, str) and lemma.strip():
                    self.conjugation_deaccented[_deaccent(form)].add(_deaccent(lemma))
                    self.conjugation_original[form.strip().lower()].add(lemma.strip().lower())

    def _reverse_conjugation(self, surface: str, headword: str) -> bool:
        base = headword[:-2] if headword.endswith("se") else headword
        for variant in _conjugation_variants(surface):
            lemmas = self.conjugation_deaccented.get(variant, set())
            if headword in lemmas or base in lemmas:
                return True
        return False

    def _clitic_equals_headword(self, surface: str, headword: str) -> bool:
        base = headword[:-2] if headword.endswith("se") else headword
        if not (
            headword in self.conjugation_deaccented
            or base in self.conjugation_deaccented
            or headword.endswith(("ar", "er", "ir"))
            or base.endswith(("ar", "er", "ir"))
        ):
            return False
        return any(
            surface.endswith(suffix)
            and len(surface) > len(suffix) + 1
            and surface[: -len(suffix)] in {headword, base}
            for suffix in CLITIC_SUFFIXES
        )

    def _plausible(
        self,
        surface: str,
        headword: object,
        relation: object,
        conjugation_lemmas: set[str],
    ) -> bool:
        if not isinstance(headword, str) or not headword.strip():
            return True
        source, target = _deaccent(surface), _deaccent(headword)
        if source == target:
            return True
        if str(relation).lower() in {"conjugation", "inflection"}:
            return True
        if any(target == lemma or target.startswith(lemma) or lemma.startswith(target) for lemma in conjugation_lemmas):
            return True
        if self._reverse_conjugation(source, target):
            return True
        if self._clitic_equals_headword(source, target):
            return True
        return target in self.spanish_forms and _regular_noun_variant(source, target)

    def _reverse_direction_conjugation(
        self, surface: str, analyses: list[dict[str, Any]]
    ) -> bool:
        surface_lower = surface.strip().lower()
        lemmas = self.conjugation_original.get(surface_lower, set())
        if not lemmas or surface_lower in lemmas:
            return False
        headwords = {
            str(item.get("headword", "")).strip().lower()
            for item in analyses
            if str(item.get("headword", "")).strip()
        }
        if headwords != {surface_lower} or headwords & lemmas:
            return False
        total = spanish_like = 0
        excluded = {_deaccent(surface_lower), *(_deaccent(value) for value in headwords)}
        for analysis in analyses:
            for sense in analysis.get("senses", []):
                translation = str(sense.get("translation", "")).strip()
                if not translation:
                    continue
                total += 1
                tokens = re.findall(r"[^\W\d_]+", translation.lower(), flags=re.UNICODE)
                minimum = 3 if len(tokens) == 1 else 4
                if any(
                    len(_deaccent(token)) >= minimum
                    and _deaccent(token) not in excluded
                    and _deaccent(token) in self.spanish_forms
                    for token in tokens
                ):
                    spanish_like += 1
        return total > 0 and spanish_like * 2 > total

    def _analyses(self, surface: str, quarantine: list[dict[str, str]]) -> list[dict[str, Any]]:
        surface_entry = self.surface_cache.get(surface)
        if not isinstance(surface_entry, dict):
            return []
        entry_language = str(surface_entry.get("entry_lang", "")).strip()
        if entry_language and entry_language != "es":
            quarantine.append({"surface": surface, "headword": "", "reason": "provider_wrong_language"})
            return []
        analyses = [
            item
            for item in _normalize_analyses(surface_entry.get("dictionary_analyses"))
            if not _abbreviation_mismatch(surface, item.get("headword"))
        ]
        seen_headwords = {item.get("headword") for item in analyses if item.get("headword")}
        signatures = {_analysis_signature(item) for item in analyses}
        possible_results = [
            item for item in surface_entry.get("possible_results", []) if isinstance(item, dict)
        ]
        for result in possible_results:
            headword = str(result.get("headword", "")).strip()
            if not headword or headword in seen_headwords or _abbreviation_mismatch(surface, headword):
                continue
            entry = self.headword_cache.get(headword)
            if not isinstance(entry, dict):
                continue
            for analysis in _normalize_analyses(entry.get("dictionary_analyses")):
                analysis["headword"] = analysis.get("headword") or headword
                analysis["surface_relation"] = result.get("heuristic", "")
                analysis["surface_from"] = surface
                signature = _analysis_signature(analysis)
                if signature not in signatures:
                    analyses.append(analysis)
                    signatures.add(signature)
                    seen_headwords.add(analysis.get("headword"))

        surface_normalized = _deaccent(surface)
        has_self = any(
            _deaccent(str(item.get("headword", "")).strip()) == surface_normalized
            and not item.get("surface_from")
            for item in analyses
        )
        if has_self:
            plural_spellings = {surface_normalized + "s", surface_normalized + "es"}
            kept = []
            for analysis in analyses:
                collision = (
                    _deaccent(str(analysis.get("headword", "")).strip()) in plural_spellings
                    and str(analysis.get("surface_relation", "")).lower() in {"", "inflection"}
                )
                if collision:
                    quarantine.append(
                        {
                            "surface": surface,
                            "headword": str(analysis.get("headword", "")),
                            "reason": "plural_analysis_conflicts_with_exact_surface",
                        }
                    )
                else:
                    kept.append(analysis)
            analyses = kept

        if not entry_language and self._reverse_direction_conjugation(surface, analyses):
            replacements: list[dict[str, Any]] = []
            for lemma in sorted(self.conjugation_original.get(surface.lower(), set())):
                entry = self.headword_cache.get(lemma)
                if not isinstance(entry, dict):
                    continue
                for analysis in _normalize_analyses(entry.get("dictionary_analyses")):
                    analysis["headword"] = analysis.get("headword") or lemma
                    analysis["surface_relation"] = "conjugation"
                    analysis["surface_from"] = surface
                    replacements.append(analysis)
            if replacements:
                quarantine.extend(
                    {
                        "surface": surface,
                        "headword": str(item.get("headword", "")),
                        "reason": "reverse_direction_conjugation",
                    }
                    for item in analyses
                )
                analyses = replacements

        if any(
            item.get("surface_relation") == "conjugation"
            and str(item.get("headword", "")).lower() != surface.lower()
            for item in analyses
        ):
            analyses = [
                item
                for item in analyses
                if not (
                    str(item.get("headword", "")).lower() == surface.lower()
                    and _phrase_only(item)
                )
            ]

        conjugation_lemmas = {
            _deaccent(str(item.get("headword", "")))
            for item in possible_results
            if str(item.get("heuristic", "")).lower() in {"conjugation", "inflection"}
            and str(item.get("headword", "")).strip()
        }
        kept = []
        for analysis in analyses:
            if self._plausible(
                surface,
                analysis.get("headword"),
                analysis.get("surface_relation", ""),
                conjugation_lemmas,
            ):
                kept.append(analysis)
            else:
                quarantine.append(
                    {
                        "surface": surface,
                        "headword": str(analysis.get("headword", "")),
                        "reason": "implausible_fuzzy_headword",
                    }
                )
        return kept

    def build(
        self,
        cards: Iterable[dict[str, Any]],
        *,
        snapshot_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if snapshot_id != self.snapshot_id:
            raise SpanishDictMenuError("requested SpanishDict snapshot ID does not match its manifest")
        card_list = list(cards)
        menu_cards: list[dict[str, Any]] = []
        per_surface: list[dict[str, Any]] = []
        quarantine: list[dict[str, str]] = []
        total_analyses = total_senses = 0

        for card in card_list:
            surface = card.get("surface_key")
            if not isinstance(surface, str) or not surface:
                raise SpanishDictMenuError("inventory card has no canonical surface")
            raw_analyses = self._analyses(surface, quarantine)
            normalized: list[MenuAnalysis] = []
            used_sense_ids: set[str] = set()
            for raw_index, raw in enumerate(raw_analyses):
                headword = str(raw.get("headword") or surface).strip()
                legacy = _legacy_sense_ids(
                    headword,
                    raw.get("senses", []),
                    used_sense_ids,
                )
                grouped: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
                for sense_id, sense in legacy.items():
                    part_of_speech = str(sense.get("pos", "X")).strip() or "X"
                    translation = str(sense.get("translation", "")).strip()
                    grouped[part_of_speech].append((sense_id, sense))
                for part_of_speech, senses in grouped.items():
                    source_key = f"es:{headword}:{part_of_speech}:{raw_index}"
                    leaves = tuple(
                        SenseLeaf(
                            sense_id=sense_id,
                            translation=str(sense["translation"]).strip(),
                            definition=str(sense.get("context", "")).strip(),
                            source_reference=f"spanishdict-menu:{headword}:{sense_id}",
                            provider_metadata={
                                "spanishdict": {
                                    key: deepcopy(value)
                                    for key, value in sense.items()
                                    if key not in {"translation", "context", "pos", "headword", "source"}
                                },
                                "legacy_menu_sense_id": sense_id,
                                "context": str(sense.get("context", "")),
                                "translation_status": (
                                    "present"
                                    if str(sense.get("translation", "")).strip()
                                    else "explicit_missing"
                                ),
                            },
                        )
                        for sense_id, sense in senses
                    )
                    normalized.append(
                        MenuAnalysis(
                            menu_analysis_id=build_analysis_id(
                                card_id=card["card_id"],
                                source_adapter=ADAPTER_ID,
                                source_analysis_key=source_key,
                            ),
                            card_id=card["card_id"],
                            surface_form=surface,
                            headword=headword,
                            part_of_speech=part_of_speech,
                            source_adapter=ADAPTER_ID,
                            source_analysis_key=source_key,
                            senses=leaves,
                            provider_metadata={
                                "spanishdict": {
                                    "query": surface,
                                    "response_headword": headword,
                                    "entry_language": (self.surface_cache.get(surface) or {}).get("entry_lang"),
                                    "resolution": "direct" if not raw.get("surface_from") else raw.get("surface_relation", "redirect"),
                                },
                                "menu_order_prior": len(normalized),
                            },
                        )
                    )
            sense_count = sum(len(item.senses) for item in normalized)
            total_analyses += len(normalized)
            total_senses += sense_count
            menu_cards.append(
                {
                    "card_id": card["card_id"],
                    "surface_form": surface,
                    "analyses": [item.to_dict() for item in normalized],
                }
            )
            per_surface.append(
                {
                    "card_id": card["card_id"],
                    "surface_form": surface,
                    "analysis_count": len(normalized),
                    "sense_count": sense_count,
                    "status": "ready" if normalized else "no_menu",
                }
            )

        payload = {
            "menu_version": MENU_VERSION,
            "language": "es",
            "gloss_language": "en",
            "source_edition": self.source_edition,
            "source_adapter": ADAPTER_ID,
            "snapshot_id": snapshot_id,
            "snapshot_content_id": self.snapshot_content_id,
            "cards": menu_cards,
        }
        reasons = Counter(item["reason"] for item in quarantine)
        report = {
            "report_version": REPORT_VERSION,
            "language": "es",
            "source_adapter": ADAPTER_ID,
            "source_edition": self.source_edition,
            "snapshot_id": snapshot_id,
            "snapshot_content_id": self.snapshot_content_id,
            "inventory_cards": len(card_list),
            "cards_ready": sum(item["status"] == "ready" for item in per_surface),
            "cards_without_menu": sum(item["status"] == "no_menu" for item in per_surface),
            "analysis_count": total_analyses,
            "sense_count": total_senses,
            "quarantine_count": len(quarantine),
            "quarantine_reasons": dict(sorted(reasons.items())),
            "quarantine": quarantine,
            "fallbacks": [],
            "per_surface": per_surface,
        }
        return payload, report
