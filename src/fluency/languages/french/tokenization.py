"""Deterministic French tokenization with traceable routing decisions."""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
import json
from pathlib import Path
import re
import unicodedata
from typing import Collection, Mapping

from fluency.core.text_units import TokenUnit, TokenizationResult
from fluency.languages.french.surfaces import (
    canonicalize_typography,
    normalize_surface,
)


CONFIG_SCHEMA_VERSION = "fr-tokenization/v1"
_URL_PATTERN = re.compile(r"https?://[^\s]+", re.IGNORECASE)
_EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", re.UNICODE)


@dataclass(frozen=True, slots=True)
class FrenchTokenizationConfig:
    elision_expansions: Mapping[str, tuple[str, ...]]
    contractions: Mapping[str, Mapping[str, tuple[str, ...]]]
    hyphen_clitics: frozenset[str]
    inversion_pronouns: frozenset[str]
    inversion_marker: str
    quarantined_fragments: frozenset[str]


def _default_config_path() -> Path:
    return (
        Path(__file__).resolve().parents[4]
        / "config"
        / "languages"
        / "fr"
        / "tokenization.json"
    )


@lru_cache(maxsize=1)
def load_tokenization_config() -> FrenchTokenizationConfig:
    path = _default_config_path()
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("schema_version") != CONFIG_SCHEMA_VERSION:
        raise ValueError(f"unsupported French tokenization configuration: {path}")

    elisions = {
        normalize_surface(prefix): tuple(normalize_surface(form) for form in forms)
        for prefix, forms in record["elision_expansions"].items()
    }
    contractions = {
        normalize_surface(surface): {
            "components": tuple(
                normalize_surface(value) for value in specification["components"]
            ),
            "grammatical_roles": tuple(specification["grammatical_roles"]),
        }
        for surface, specification in record["contractions"].items()
    }
    return FrenchTokenizationConfig(
        elision_expansions=elisions,
        contractions=contractions,
        hyphen_clitics=frozenset(
            normalize_surface(value) for value in record["hyphen_clitics"]
        ),
        inversion_pronouns=frozenset(
            normalize_surface(value) for value in record["inversion_pronouns"]
        ),
        inversion_marker=normalize_surface(record["inversion_marker"]),
        quarantined_fragments=frozenset(
            normalize_surface(value) for value in record["quarantined_fragments"]
        ),
    )


def _surface_pattern(surfaces: Collection[str]) -> re.Pattern[str] | None:
    if not surfaces:
        return None
    alternatives: list[str] = []
    for surface in sorted(surfaces, key=lambda value: (-len(value), value)):
        words = surface.split(" ")
        alternatives.append(r"\s+".join(re.escape(word) for word in words))
    return re.compile(
        r"(?<![\w’'-])(?:" + "|".join(alternatives) + r")(?![\w’'-])",
        re.IGNORECASE | re.UNICODE,
    )


def _is_candidate_character(character: str) -> bool:
    return (
        character.isalpha()
        or character.isdigit()
        or unicodedata.category(character).startswith("M")
        or character in {"’", "-"}
    )


def _eligible_unit(
    observed_text: str,
    start: int,
    *,
    token_class: str,
    decision: str,
    parent_text: str | None = None,
) -> TokenUnit:
    return TokenUnit(
        observed_text=observed_text,
        surface_key=normalize_surface(observed_text),
        start=start,
        end=start + len(observed_text),
        token_class=token_class,
        decision=decision,
        eligible=True,
        parent_text=parent_text,
    )


def _rejected_unit(
    observed_text: str,
    start: int,
    *,
    token_class: str,
    decision: str,
    rejection_reason: str,
    parent_text: str | None = None,
) -> TokenUnit:
    return TokenUnit(
        observed_text=observed_text,
        surface_key=None,
        start=start,
        end=start + len(observed_text),
        token_class=token_class,
        decision=decision,
        eligible=False,
        parent_text=parent_text,
        rejection_reason=rejection_reason,
    )


def _split_hyphenated(
    observed_text: str,
    start: int,
    config: FrenchTokenizationConfig,
) -> tuple[TokenUnit, ...]:
    parts = observed_text.split("-")
    normalized_parts = [normalize_surface(part) for part in parts]
    grammatical = False
    has_inversion_marker = False

    if (
        len(parts) == 3
        and normalized_parts[1] == config.inversion_marker
        and normalized_parts[2] in config.inversion_pronouns
    ):
        grammatical = True
        has_inversion_marker = True
    elif len(parts) >= 2 and all(
        part in config.hyphen_clitics for part in normalized_parts[1:]
    ):
        grammatical = True

    if not grammatical:
        return (
            _rejected_unit(
                observed_text,
                start,
                token_class="unresolved_hyphenated",
                decision="unresolved_hyphenation",
                rejection_reason="unknown_hyphenated_form",
            ),
        )

    units: list[TokenUnit] = []
    local_cursor = 0
    for index, part in enumerate(parts):
        local_start = observed_text.find(part, local_cursor)
        absolute_start = start + local_start
        local_cursor = local_start + len(part)
        if has_inversion_marker and index == 1:
            units.append(
                _rejected_unit(
                    part,
                    absolute_start,
                    token_class="inversion_marker",
                    decision="french_hyphen_split",
                    rejection_reason="euphonic_inversion_marker",
                    parent_text=observed_text,
                )
            )
        else:
            units.append(
                _eligible_unit(
                    part,
                    absolute_start,
                    token_class="word",
                    decision="french_hyphen_split",
                    parent_text=observed_text,
                )
            )
    return tuple(units)


def _classify_candidate(
    observed_text: str,
    start: int,
    *,
    known_surfaces: frozenset[str],
    config: FrenchTokenizationConfig,
    parent_text: str | None = None,
) -> tuple[TokenUnit, ...]:
    surface_key = normalize_surface(observed_text)

    if surface_key in config.quarantined_fragments:
        return (
            _rejected_unit(
                observed_text,
                start,
                token_class="source_fragment",
                decision="quarantined_source_fragment",
                rejection_reason="incomplete_elision_fragment",
                parent_text=parent_text,
            ),
        )
    if surface_key in known_surfaces:
        return (
            _eligible_unit(
                observed_text,
                start,
                token_class="known_surface",
                decision="approved_surface_longest_match",
                parent_text=parent_text,
            ),
        )
    if observed_text.isdigit():
        return (
            _rejected_unit(
                observed_text,
                start,
                token_class="number",
                decision="retained_nonlexical",
                rejection_reason="numeric_token",
                parent_text=parent_text,
            ),
        )
    if any(character.isdigit() for character in observed_text):
        return (
            _rejected_unit(
                observed_text,
                start,
                token_class="mixed",
                decision="retained_nonlexical",
                rejection_reason="mixed_alphanumeric_token",
                parent_text=parent_text,
            ),
        )

    if "’" in observed_text:
        apostrophe_index = observed_text.find("’")
        prefix_text = observed_text[: apostrophe_index + 1]
        prefix_key = normalize_surface(prefix_text)
        suffix_text = observed_text[apostrophe_index + 1 :]
        if prefix_key in config.elision_expansions:
            prefix = _eligible_unit(
                prefix_text,
                start,
                token_class="elided_clitic",
                decision="french_elision_split",
                parent_text=observed_text if suffix_text else parent_text,
            )
            if not suffix_text:
                return (prefix,)
            suffix_units = _classify_candidate(
                suffix_text,
                start + apostrophe_index + 1,
                known_surfaces=known_surfaces,
                config=config,
                parent_text=observed_text,
            )
            routed_suffixes = tuple(
                replace(unit, decision="french_elision_split", parent_text=observed_text)
                if unit.eligible
                else unit
                for unit in suffix_units
            )
            return (prefix, *routed_suffixes)

    if "-" in observed_text:
        return _split_hyphenated(observed_text, start, config)

    return (
        _eligible_unit(
            observed_text,
            start,
            token_class="word",
            decision="ordinary_token",
            parent_text=parent_text,
        ),
    )


def tokenize_french(
    text: str,
    *,
    known_surfaces: Collection[str] = (),
) -> TokenizationResult:
    """Tokenize canonical French text using an approved surface vocabulary."""

    canonical_text = canonicalize_typography(text)
    config = load_tokenization_config()
    normalized_known = frozenset(normalize_surface(value) for value in known_surfaces)
    approved_known = normalized_known - config.quarantined_fragments
    known_pattern = _surface_pattern(approved_known)
    quarantine_pattern = _surface_pattern(config.quarantined_fragments)

    units: list[TokenUnit] = []
    cursor = 0
    while cursor < len(canonical_text):
        quarantine_match = (
            None if quarantine_pattern is None else quarantine_pattern.match(canonical_text, cursor)
        )
        if quarantine_match is not None:
            observed = quarantine_match.group(0)
            units.append(
                _rejected_unit(
                    observed,
                    cursor,
                    token_class="source_fragment",
                    decision="quarantined_source_fragment",
                    rejection_reason="incomplete_elision_fragment",
                )
            )
            cursor = quarantine_match.end()
            continue

        known_match = None if known_pattern is None else known_pattern.match(canonical_text, cursor)
        if known_match is not None:
            observed = known_match.group(0)
            units.append(
                _eligible_unit(
                    observed,
                    cursor,
                    token_class="known_surface",
                    decision="approved_surface_longest_match",
                )
            )
            cursor = known_match.end()
            continue

        url_match = _URL_PATTERN.match(canonical_text, cursor)
        email_match = _EMAIL_PATTERN.match(canonical_text, cursor)
        nonlexical_match = url_match or email_match
        if nonlexical_match is not None:
            observed = nonlexical_match.group(0)
            units.append(
                _rejected_unit(
                    observed,
                    cursor,
                    token_class="mixed",
                    decision="retained_nonlexical",
                    rejection_reason="url_or_email",
                )
            )
            cursor = nonlexical_match.end()
            continue

        if not _is_candidate_character(canonical_text[cursor]):
            cursor += 1
            continue

        end = cursor + 1
        while end < len(canonical_text) and _is_candidate_character(canonical_text[end]):
            end += 1
        observed = canonical_text[cursor:end]
        units.extend(
            _classify_candidate(
                observed,
                cursor,
                known_surfaces=approved_known,
                config=config,
            )
        )
        cursor = end

    return TokenizationResult(canonical_text=canonical_text, units=tuple(units))

