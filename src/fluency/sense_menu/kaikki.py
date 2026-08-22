"""Stream English-Wiktionary Kaikki JSONL into a French closed sense menu."""

from __future__ import annotations

from collections import defaultdict
import gzip
import json
from pathlib import Path
from typing import Any, Iterable, Iterator

from fluency.core.hashing import canonical_content_id, file_content_id
from fluency.languages.french.surfaces import normalize_surface
from fluency.wsd.menus import MenuAnalysis, SenseLeaf, build_analysis_id


ADAPTER_ID = "wiktionary-sense-menu/v1"
MENU_VERSION = "sense-menu/v1"
REPORT_VERSION = "sense-menu-report/v1"
FORM_TAGS = frozenset({"form-of", "alt-of"})


class KaikkiMenuError(ValueError):
    """Raised when a Kaikki snapshot cannot produce an exact menu."""


def _safe_surface(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return normalize_surface(value)
    except (TypeError, ValueError):
        return None


def _json_values(value: object) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _sense_tags(sense: dict[str, Any]) -> set[str]:
    raw = sense.get("tags")
    return {tag for tag in raw if isinstance(tag, str)} if isinstance(raw, list) else set()


def _glosses(sense: dict[str, Any], field: str = "glosses") -> list[str]:
    raw = sense.get(field)
    return [value.strip() for value in raw if isinstance(value, str) and value.strip()] if isinstance(raw, list) else []


def _redirect_targets(row: dict[str, Any]) -> set[str]:
    targets: set[str] = set()
    for sense in _json_values(row.get("senses")):
        if not (_sense_tags(sense) & FORM_TAGS):
            continue
        for field in ("form_of", "alt_of"):
            for target in _json_values(sense.get(field)):
                normalized = _safe_surface(target.get("word"))
                if normalized is not None:
                    targets.add(normalized)
    return targets


def _semantic_senses(row: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        sense
        for sense in _json_values(row.get("senses"))
        if not (_sense_tags(sense) & FORM_TAGS) and _glosses(sense)
    ]


def _open_jsonl(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8")
    return path.open("r", encoding="utf-8")


def _iter_rows(path: Path, *, language_code: str) -> Iterator[dict[str, Any]]:
    with _open_jsonl(path) as stream:
        for line_number, line in enumerate(stream, start=1):
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise KaikkiMenuError(
                    f"Kaikki snapshot contains invalid JSON on line {line_number}"
                ) from error
            if not isinstance(row, dict):
                raise KaikkiMenuError(
                    f"Kaikki snapshot line {line_number} is not an object"
                )
            if row.get("lang_code") == language_code:
                yield row


def _sense_id(
    sense: dict[str, Any],
    *,
    headword: str,
    part_of_speech: str,
    ordinal: int,
) -> tuple[str, str]:
    provider_id = sense.get("id")
    if isinstance(provider_id, str) and provider_id.strip():
        return provider_id, f"kaikki:{provider_id}"
    identity = canonical_content_id(
        {
            "adapter": ADAPTER_ID,
            "headword": headword,
            "part_of_speech": part_of_speech,
            "ordinal": ordinal,
            "glosses": _glosses(sense),
            "raw_glosses": _glosses(sense, "raw_glosses"),
            "tags": sorted(_sense_tags(sense)),
        }
    ).removeprefix("sha256:")
    fallback = f"sense_{identity[:32]}"
    return fallback, f"kaikki-content:{fallback}"


def _metadata(row: dict[str, Any], sense: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "tags": sorted(_sense_tags(sense)),
        "topics": [value for value in sense.get("topics", []) if isinstance(value, str)],
        "raw_glosses": _glosses(sense, "raw_glosses"),
    }
    for field in ("qualifier", "sense_index"):
        value = sense.get(field)
        if isinstance(value, (str, int)) and value != "":
            metadata[field] = value
    examples = sense.get("examples")
    if isinstance(examples, list):
        metadata["examples"] = [item for item in examples if isinstance(item, dict)]
    for field in ("etymology_number", "etymology_text"):
        value = row.get(field)
        if isinstance(value, (str, int)) and value != "":
            metadata[field] = value
    return metadata


class KaikkiSenseMenuAdapter:
    """Resolve direct and structured form-of entries without lemma-keyed cards."""

    def __init__(
        self,
        path: Path,
        *,
        language_code: str = "fr",
        gloss_language: str = "en",
        source_edition: str = "enwiktionary",
        max_redirect_hops: int = 5,
    ) -> None:
        self.path = path.resolve()
        if not self.path.is_file():
            raise KaikkiMenuError(f"Kaikki snapshot does not exist: {self.path}")
        if max_redirect_hops < 1:
            raise ValueError("max_redirect_hops must be positive")
        self.language_code = language_code
        self.gloss_language = gloss_language
        if source_edition != "enwiktionary" or gloss_language != "en":
            raise KaikkiMenuError(
                "the current French WSD profile requires English glosses from enwiktionary"
            )
        self.source_edition = source_edition
        self.max_redirect_hops = max_redirect_hops
        self.snapshot_content_id = file_content_id(self.path)

    def _collect(
        self,
        surfaces: set[str],
    ) -> tuple[
        dict[str, list[dict[str, Any]]],
        dict[str, dict[str, tuple[str, ...]]],
        dict[str, int],
    ]:
        rows_by_word: dict[str, list[dict[str, Any]]] = defaultdict(list)
        paths: dict[str, dict[str, tuple[str, ...]]] = {
            surface: {surface: (surface,)} for surface in surfaces
        }
        scanned: set[str] = set()
        rows_read = 0
        passes = 0

        for _ in range(self.max_redirect_hops + 1):
            wanted = {
                headword
                for by_headword in paths.values()
                for headword in by_headword
                if headword not in scanned
            }
            if not wanted:
                break
            passes += 1
            found: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for row in _iter_rows(self.path, language_code=self.language_code):
                rows_read += 1
                word = _safe_surface(row.get("word"))
                if word in wanted:
                    found[word].append(row)
            for word in sorted(wanted):
                rows_by_word[word].extend(found.get(word, []))
            scanned.update(wanted)

            for surface, by_headword in paths.items():
                additions: dict[str, tuple[str, ...]] = {}
                for headword, path in tuple(by_headword.items()):
                    if len(path) > self.max_redirect_hops:
                        continue
                    for row in found.get(headword, []):
                        for target in sorted(_redirect_targets(row)):
                            if target in path:
                                continue
                            candidate = (*path, target)
                            previous = by_headword.get(target) or additions.get(target)
                            if previous is None or candidate < previous:
                                additions[target] = candidate
                by_headword.update(additions)

        return dict(rows_by_word), paths, {"passes": passes, "rows_read": rows_read}

    def build(
        self,
        cards: Iterable[dict[str, Any]],
        *,
        snapshot_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        card_list = list(cards)
        by_surface: dict[str, dict[str, Any]] = {}
        for card in card_list:
            surface = _safe_surface(card.get("surface_key"))
            if surface is None or surface != card.get("surface_key"):
                raise KaikkiMenuError("inventory surface is not canonically normalized")
            if surface in by_surface:
                raise KaikkiMenuError(f"duplicate inventory surface: {surface}")
            by_surface[surface] = card

        rows_by_word, paths, scan = self._collect(set(by_surface))
        menu_cards: list[dict[str, Any]] = []
        per_surface: list[dict[str, Any]] = []
        total_analyses = 0
        total_senses = 0

        for surface, card in by_surface.items():
            grouped: dict[tuple[str, str], list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
            entry_counts: dict[tuple[str, str], int] = defaultdict(int)
            for headword in sorted(paths[surface]):
                for row in rows_by_word.get(headword, []):
                    part_of_speech = row.get("pos")
                    if not isinstance(part_of_speech, str) or not part_of_speech:
                        continue
                    semantic = _semantic_senses(row)
                    if not semantic:
                        continue
                    key = (headword, part_of_speech)
                    entry_counts[key] += 1
                    grouped[key].extend((row, sense) for sense in semantic)

            analyses: list[MenuAnalysis] = []
            for (headword, part_of_speech), row_senses in sorted(grouped.items()):
                source_key = f"{self.language_code}:{headword}:{part_of_speech}"
                leaves: dict[str, SenseLeaf] = {}
                for ordinal, (row, sense) in enumerate(row_senses):
                    glosses = _glosses(sense)
                    sense_id, source_reference = _sense_id(
                        sense,
                        headword=headword,
                        part_of_speech=part_of_speech,
                        ordinal=ordinal,
                    )
                    leaf = SenseLeaf(
                        sense_id=sense_id,
                        translation=glosses[0],
                        definition=" | ".join(glosses[1:]),
                        source_reference=source_reference,
                        provider_metadata=_metadata(row, sense),
                    )
                    previous = leaves.get(sense_id)
                    if previous is not None and previous != leaf:
                        raise KaikkiMenuError(
                            f"provider sense ID is not unique: {sense_id}"
                        )
                    leaves[sense_id] = leaf
                analysis = MenuAnalysis(
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
                    senses=tuple(leaves[key] for key in sorted(leaves)),
                    provider_metadata={
                        "resolution_path": list(paths[surface][headword]),
                        "resolution": "direct" if headword == surface else "structured_form_of",
                        "source_entry_count": entry_counts[(headword, part_of_speech)],
                    },
                )
                analyses.append(analysis)

            total_analyses += len(analyses)
            sense_count = sum(len(analysis.senses) for analysis in analyses)
            total_senses += sense_count
            menu_cards.append(
                {
                    "card_id": card["card_id"],
                    "surface_form": surface,
                    "analyses": [analysis.to_dict() for analysis in analyses],
                }
            )
            per_surface.append(
                {
                    "card_id": card["card_id"],
                    "surface_form": surface,
                    "analysis_count": len(analyses),
                    "sense_count": sense_count,
                    "status": "ready" if analyses else "no_menu",
                }
            )

        payload = {
            "menu_version": MENU_VERSION,
            "language": self.language_code,
            "gloss_language": self.gloss_language,
            "source_edition": self.source_edition,
            "source_adapter": ADAPTER_ID,
            "snapshot_id": snapshot_id,
            "snapshot_content_id": self.snapshot_content_id,
            "cards": menu_cards,
        }
        report = {
            "report_version": REPORT_VERSION,
            "language": self.language_code,
            "source_adapter": ADAPTER_ID,
            "source_edition": self.source_edition,
            "snapshot_id": snapshot_id,
            "snapshot_content_id": self.snapshot_content_id,
            "inventory_cards": len(card_list),
            "cards_ready": sum(item["status"] == "ready" for item in per_surface),
            "cards_without_menu": sum(item["status"] == "no_menu" for item in per_surface),
            "analysis_count": total_analyses,
            "sense_count": total_senses,
            "scan_passes": scan["passes"],
            "rows_read_across_passes": scan["rows_read"],
            "fallbacks": [],
            "per_surface": per_surface,
        }
        return payload, report
