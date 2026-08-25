"""Stream English-Wiktionary Kaikki JSONL into a closed sense menu."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import gzip
import json
from pathlib import Path
import re
from typing import Any, Callable, Iterable, Iterator

from fluency.core.hashing import canonical_content_id, file_content_id
from fluency.languages.surfaces import (
    normalizer_for_language,
    typography_canonicalizer_for_language,
)
from fluency.wsd.features import SpecialistFeature
from fluency.wsd.menus import MenuAnalysis, SenseLeaf, build_analysis_id


ADAPTER_ID = "wiktionary-sense-menu/v1"
MENU_VERSION = "sense-menu/v1"
REPORT_VERSION = "sense-menu-report/v1"
FORM_TAGS = frozenset({"form-of", "alt-of"})
REGISTER_TAGS = frozenset(
    {"archaic", "colloquial", "dated", "formal", "informal", "offensive", "slang", "vulgar"}
)
CONSTRUCTION_TAGS = frozenset(
    {"ditransitive", "impersonal", "intransitive", "reflexive", "transitive"}
)


class KaikkiMenuError(ValueError):
    """Raised when a Kaikki snapshot cannot produce an exact menu."""


def _safe_surface(value: object, normalize: Callable[[str], str]) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return normalize(value)
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


@dataclass(frozen=True, slots=True)
class RedirectEdge:
    target: str
    target_parts_of_speech: frozenset[str]


def _redirect_edges(
    row: dict[str, Any],
    policy: dict[str, Any],
    *,
    source_surface: str,
    normalize: Callable[[str], str],
    canonicalize: Callable[[str], str],
) -> set[RedirectEdge]:
    redirects = policy["redirects"]
    raw_word = row.get("word")
    if redirects["require_source_case_match"] and (
        not isinstance(raw_word, str)
        or canonicalize(raw_word).strip() != source_surface
    ):
        return set()
    source_pos = row.get("pos")
    allowed = redirects["target_pos_by_source_pos"].get(source_pos)
    if not isinstance(allowed, list) or not allowed:
        return set()
    reject_tags = set(redirects["reject_tags"])
    allow_if_tags = set(redirects["allow_if_tags"])
    edges: set[RedirectEdge] = set()
    for sense in _json_values(row.get("senses")):
        tags = _sense_tags(sense)
        if not (tags & FORM_TAGS):
            continue
        if tags & reject_tags and not tags & allow_if_tags:
            continue
        for field in ("form_of", "alt_of"):
            for target in _json_values(sense.get(field)):
                normalized = _safe_surface(target.get("word"), normalize)
                if normalized is not None:
                    edges.add(RedirectEdge(normalized, frozenset(allowed)))
    return edges


def _surface_grammar(row: dict[str, Any], normalize: Callable[[str], str]) -> dict[str, list[str]]:
    """Return {target headword: grammatical tags} from a row's form-of senses.

    ``_semantic_senses`` discards form-of senses because they carry no meaning,
    and with them goes Wiktionary's own analysis of the surface: ``diz`` is the
    third-person singular present indicative of ``dizer``. That is a fact about
    the surface, not about any sense, so it is kept on the analysis rather than
    on a leaf.

    It is worth keeping because it is the dictionary's grammatical claim in the
    dictionary's own tagset -- the mismatch that made the POS menu filter delete
    correct senses on common words does not arise here.
    """

    grammar: dict[str, list[str]] = {}
    for sense in _json_values(row.get("senses")):
        if not (_sense_tags(sense) & FORM_TAGS):
            continue
        tags = sorted(tag for tag in _sense_tags(sense) if tag not in FORM_TAGS)
        if not tags:
            continue
        for field in ("form_of", "alt_of"):
            for target in _json_values(sense.get(field)):
                word = target.get("word")
                if not isinstance(word, str) or not word.strip():
                    continue
                try:
                    key = normalize(word)
                except (TypeError, ValueError):
                    continue
                merged = set(grammar.get(key, ())) | set(tags)
                grammar[key] = sorted(merged)
    return grammar


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


_PARENTHETICAL = re.compile(r"^\((?P<context>[^)]{2,60})\)\s*\S")


def _context(sense: dict[str, Any]) -> str:
    """Return a short disambiguating label, the equivalent of SpanishDict's context.

    SpanishDict publishes ``context`` on every sense; Wiktionary carries the same
    information but embedded in the prose. A nested sub-gloss is preferred when
    present, then the leading parenthetical of a raw gloss -- ``(interrogative)``,
    ``(relative)``, ``(only in subordinate clauses)`` -- then topic and qualifier
    labels. Deriving it lifts coverage from 16.5% to roughly 61% of senses, and
    the recovered labels are mostly grammatical rather than topical, which is the
    axis a bilingual dictionary's context field usually marks.
    """

    glosses = _glosses(sense)
    if len(glosses) > 1:
        return " | ".join(glosses[1:])
    for raw in _glosses(sense, "raw_glosses"):
        match = _PARENTHETICAL.match(raw)
        if match:
            return match.group("context").strip()
    topics = [value for value in sense.get("topics", []) if isinstance(value, str)]
    if topics:
        return ", ".join(topics)
    qualifier = sense.get("qualifier")
    if isinstance(qualifier, str) and qualifier.strip():
        return qualifier.strip()
    return ""


def _regions(sense: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    """Return regional usage labels, the equivalent of SpanishDict's regions.

    Which tags count as regional is language knowledge, not adapter knowledge, so
    the list comes from the sense-menu language policy. A language that declares
    none simply gets an empty list rather than a missing field.
    """

    known = policy.get("region_tags")
    if not isinstance(known, list) or not known:
        return []
    tags = _sense_tags(sense)
    return sorted(tag for tag in tags if tag in set(known))


def _sense_keys(sense: dict[str, Any]) -> tuple[str, ...]:
    """Return Wiktionary's own ``{{senseid}}`` values for one sense."""

    return tuple(
        value.strip()
        for value in sense.get("senseid", [])
        if isinstance(value, str) and value.strip()
    )


def _sense_id(
    sense: dict[str, Any],
    *,
    language_code: str,
    headword: str,
    part_of_speech: str,
    provider_id_collides: bool = False,
    sense_keys_collide: bool = False,
) -> tuple[str, str]:
    """Return one stable sense ID plus its provenance reference.

    Kaikki flattens a sense's ``senseid`` list to its FIRST entry and appends a
    counter when that collides, but it does not re-check the counter against IDs
    it has already emitted. Nested sub-senses therefore share one ``id``: all of
    ``não``'s sub-senses arrive as ``en-não-pt-adv-pt:not1``. This is observed in
    16 Portuguese and 20 French entries, on common words in both.

    Wiktionary's own identifiers are not ambiguous — the discarded tail of
    ``senseid`` separates them — so a collision falls back to the full list
    rather than to a hash. Content hashing remains the last resort for senses
    that carry no usable ``senseid``, and deliberately excludes the sense's
    ordinal so that reordering an entry cannot re-key a card.
    """

    provider_id = sense.get("id")
    has_provider_id = isinstance(provider_id, str) and bool(provider_id.strip())
    if has_provider_id and not provider_id_collides:
        return provider_id, f"kaikki:{provider_id}"

    keys = _sense_keys(sense)
    if provider_id_collides and keys and not sense_keys_collide:
        joined = "|".join(keys)
        derived = f"en-{headword}-{language_code}-{part_of_speech}-{joined}"
        return derived, f"kaikki-senseid:{derived}"

    identity = canonical_content_id(
        {
            "adapter": ADAPTER_ID,
            "headword": headword,
            "part_of_speech": part_of_speech,
            "sense_keys": list(keys),
            "glosses": _glosses(sense),
            "raw_glosses": _glosses(sense, "raw_glosses"),
            "tags": sorted(_sense_tags(sense)),
            "topics": sorted(
                value for value in sense.get("topics", []) if isinstance(value, str)
            ),
        }
    ).removeprefix("sha256:")
    fallback = f"sense_{identity[:32]}"
    return fallback, f"kaikki-content:{fallback}"


def _metadata(
    row: dict[str, Any],
    sense: dict[str, Any],
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "tags": sorted(_sense_tags(sense)),
        "topics": [value for value in sense.get("topics", []) if isinstance(value, str)],
        "raw_glosses": _glosses(sense, "raw_glosses"),
        # Declared for every language so the shape does not vary by provider.
        # Empty is a statement that this language has no regional marking, not
        # an absence of the concept.
        "context": _context(sense),
        "regions": _regions(sense, policy or {}),
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


def _specialist_features(sense: dict[str, Any]) -> tuple[SpecialistFeature, ...]:
    features = [
        SpecialistFeature("domain", "topic", topic.strip(), topic.strip())
        for topic in sense.get("topics", [])
        if isinstance(topic, str) and topic.strip()
    ]
    for tag in sorted(_sense_tags(sense)):
        if tag in REGISTER_TAGS:
            features.append(SpecialistFeature("register", "usage_tag", tag, tag))
        elif tag in CONSTRUCTION_TAGS:
            features.append(SpecialistFeature("construction", "grammar_tag", tag, tag))
    return tuple(features)


class KaikkiSenseMenuAdapter:
    """Resolve direct and structured form-of entries without lemma-keyed cards."""

    def __init__(
        self,
        path: Path,
        *,
        language_code: str = "fr",
        gloss_language: str = "en",
        source_edition: str = "enwiktionary",
        language_policy: dict[str, Any] | None = None,
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
        if not isinstance(language_policy, dict):
            raise KaikkiMenuError("an explicit sense-menu language policy is required")
        self.language_policy = language_policy
        self._normalize = normalizer_for_language(language_code)
        self._canonicalize = typography_canonicalizer_for_language(language_code)
        self.max_redirect_hops = max_redirect_hops
        self.snapshot_content_id = file_content_id(self.path)

    def _collect(
        self,
        surfaces: set[str],
    ) -> tuple[
        dict[str, list[dict[str, Any]]],
        dict[str, dict[str, tuple[str, ...]]],
        dict[str, dict[str, set[str] | None]],
        dict[str, int],
    ]:
        rows_by_word: dict[str, list[dict[str, Any]]] = defaultdict(list)
        surface_grammar: dict[str, dict[str, list[str]]] = defaultdict(dict)
        paths: dict[str, dict[str, tuple[str, ...]]] = {
            surface: {surface: (surface,)} for surface in surfaces
        }
        allowed_positions: dict[str, dict[str, set[str] | None]] = {
            surface: {surface: None} for surface in surfaces
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
                word = _safe_surface(row.get("word"), self._normalize)
                if word in wanted:
                    found[word].append(row)
            for word in sorted(wanted):
                rows_by_word[word].extend(found.get(word, []))
            scanned.update(wanted)

            for surface, by_headword in paths.items():
                additions: dict[str, tuple[str, ...]] = {}
                for row in found.get(surface, []):
                    for target, tags in _surface_grammar(row, self._normalize).items():
                        merged = set(surface_grammar[surface].get(target, ())) | set(tags)
                        surface_grammar[surface][target] = sorted(merged)
                addition_positions: dict[str, set[str]] = defaultdict(set)
                for headword, path in tuple(by_headword.items()):
                    if len(path) > self.max_redirect_hops:
                        continue
                    for row in found.get(headword, []):
                        source_pos = row.get("pos")
                        allowed_source = allowed_positions[surface][headword]
                        if allowed_source is not None and source_pos not in allowed_source:
                            continue
                        for edge in sorted(
                            _redirect_edges(
                                row,
                                self.language_policy,
                                source_surface=headword,
                                normalize=self._normalize,
                                canonicalize=self._canonicalize,
                            ),
                            key=lambda item: (item.target, sorted(item.target_parts_of_speech)),
                        ):
                            target = edge.target
                            if target in path:
                                continue
                            candidate = (*path, target)
                            previous = by_headword.get(target) or additions.get(target)
                            if previous is None or candidate < previous:
                                additions[target] = candidate
                            addition_positions[target].update(edge.target_parts_of_speech)
                by_headword.update(additions)
                for target, positions in addition_positions.items():
                    previous = allowed_positions[surface].get(target)
                    if previous is None and target in allowed_positions[surface]:
                        continue
                    if previous is None:
                        allowed_positions[surface][target] = set(positions)
                    else:
                        previous.update(positions)

        return (
            dict(rows_by_word),
            paths,
            allowed_positions,
            dict(surface_grammar),
            {"passes": passes, "rows_read": rows_read},
        )

    def build(
        self,
        cards: Iterable[dict[str, Any]],
        *,
        snapshot_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        card_list = list(cards)
        by_surface: dict[str, dict[str, Any]] = {}
        for card in card_list:
            surface = _safe_surface(card.get("surface_key"), self._normalize)
            if surface is None or surface != card.get("surface_key"):
                raise KaikkiMenuError("inventory surface is not canonically normalized")
            if surface in by_surface:
                raise KaikkiMenuError(f"duplicate inventory surface: {surface}")
            by_surface[surface] = card

        rows_by_word, paths, allowed_positions, surface_grammar, scan = self._collect(
            set(by_surface)
        )
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
                    allowed = allowed_positions[surface][headword]
                    if allowed is not None and part_of_speech not in allowed:
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
                provider_id_counts: Counter[str] = Counter(
                    sense["id"]
                    for _, sense in row_senses
                    if isinstance(sense.get("id"), str) and sense["id"].strip()
                )
                sense_key_counts: Counter[tuple[str, ...]] = Counter(
                    _sense_keys(sense) for _, sense in row_senses
                )
                leaves: dict[str, SenseLeaf] = {}
                for row, sense in row_senses:
                    glosses = _glosses(sense)
                    raw_provider_id = sense.get("id")
                    provider_id_collides = (
                        isinstance(raw_provider_id, str)
                        and provider_id_counts[raw_provider_id] > 1
                    )
                    sense_id, source_reference = _sense_id(
                        sense,
                        language_code=self.language_code,
                        headword=headword,
                        part_of_speech=part_of_speech,
                        provider_id_collides=provider_id_collides,
                        sense_keys_collide=sense_key_counts[_sense_keys(sense)] > 1,
                    )
                    leaf = SenseLeaf(
                        sense_id=sense_id,
                        translation=glosses[0],
                        definition=_context(sense),
                        source_reference=source_reference,
                        provider_metadata=_metadata(row, sense, self.language_policy),
                        specialist_features=_specialist_features(sense),
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
                        # Declared for every analysis; empty when the surface is
                        # the headword or the dictionary offers no analysis.
                        "surface_grammar": surface_grammar.get(surface, {}).get(headword, []),
                        "allowed_parts_of_speech": (
                            None
                            if allowed_positions[surface][headword] is None
                            else sorted(allowed_positions[surface][headword])
                        ),
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
