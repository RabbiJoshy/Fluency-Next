"""Flat, evidence-backed aliases for historical progress identifiers."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Mapping

from fluency.core.hashing import validate_content_id
from fluency.core.identity import IDENTITY_VERSION, build_card_id


ALIAS_REGISTRY_VERSION = "progress-alias-registry/v1"
ALIAS_RECORD_VERSION = "progress-alias/v1"
ALIAS_NAMESPACE = "fluency-progress-legacy/v1"
ALIAS_STATUSES = frozenset({"resolved", "ambiguous", "retired", "unresolved"})
PROVENANCE_STATUSES = frozenset({"observed", "reconstructed", "unknown"})
EVIDENCE_KINDS = frozenset({"deck_row", "nested_alias", "migration_component"})

_LANGUAGE_PATTERN = re.compile(r"^[a-z]{2,3}$")
_SLUG_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*$")
def _require_nonempty_text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{name} must be a non-empty trimmed string")


@dataclass(frozen=True, slots=True)
class AliasSource:
    """One content-hashed source shared by many alias observations."""

    source_id: str
    source_path: str
    source_content_id: str

    def __post_init__(self) -> None:
        _require_nonempty_text(self.source_id, "source_id")
        if _SLUG_PATTERN.fullmatch(self.source_id) is None:
            raise ValueError("invalid alias source_id")
        _require_nonempty_text(self.source_path, "source_path")
        validate_content_id(self.source_content_id)

    def to_dict(self) -> dict[str, str]:
        return {
            "source_path": self.source_path,
            "source_content_id": self.source_content_id,
        }


@dataclass(frozen=True, slots=True)
class AliasEvidence:
    """One immutable observation supporting a legacy alias claim."""

    source_id: str
    observation_kind: str
    observed_surface_key: str | None = None

    def __post_init__(self) -> None:
        _require_nonempty_text(self.source_id, "source_id")
        if _SLUG_PATTERN.fullmatch(self.source_id) is None:
            raise ValueError("invalid alias evidence source_id")
        if self.observation_kind not in EVIDENCE_KINDS:
            raise ValueError("invalid alias evidence observation_kind")
        if self.observed_surface_key is not None:
            _require_nonempty_text(
                self.observed_surface_key, "observed_surface_key"
            )

    def to_dict(self) -> dict[str, str]:
        record = {
            "source_id": self.source_id,
            "observation_kind": self.observation_kind,
        }
        if self.observed_surface_key is not None:
            record["observed_surface_key"] = self.observed_surface_key
        return record


@dataclass(frozen=True, slots=True)
class ProgressAlias:
    """A non-recursive historical progress key resolution."""

    alias_key: str
    language: str
    mode: str
    status: str
    provenance_status: str
    evidence: tuple[AliasEvidence, ...]
    canonical_card_id: str | None = None
    surface_key: str | None = None
    candidate_card_ids: tuple[str, ...] = ()
    candidate_surface_keys: tuple[str, ...] = ()
    alias_namespace: str = ALIAS_NAMESPACE

    def __post_init__(self) -> None:
        _require_nonempty_text(self.alias_key, "alias_key")
        if _LANGUAGE_PATTERN.fullmatch(self.language) is None:
            raise ValueError("invalid alias language")
        if _SLUG_PATTERN.fullmatch(self.mode) is None:
            raise ValueError("invalid alias mode")
        if self.status not in ALIAS_STATUSES:
            raise ValueError("invalid alias status")
        if self.provenance_status not in PROVENANCE_STATUSES:
            raise ValueError("invalid alias provenance_status")
        if self.alias_namespace != ALIAS_NAMESPACE:
            raise ValueError("unsupported alias namespace")
        if not self.evidence:
            raise ValueError("an alias requires at least one evidence record")

        if self.status in {"resolved", "retired"}:
            if self.canonical_card_id is None or self.surface_key is None:
                raise ValueError("resolved and retired aliases require one card")
            expected = build_card_id(self.language, self.surface_key)
            if self.canonical_card_id != expected:
                raise ValueError("alias card ID does not match its surface identity")
            if self.candidate_card_ids or self.candidate_surface_keys:
                raise ValueError("resolved aliases cannot contain candidates")
        elif self.status == "ambiguous":
            if self.canonical_card_id is not None or self.surface_key is not None:
                raise ValueError("ambiguous aliases cannot select one card")
            if len(self.candidate_surface_keys) < 2:
                raise ValueError("ambiguous aliases require at least two candidates")
            if len(self.candidate_card_ids) != len(self.candidate_surface_keys):
                raise ValueError("ambiguous alias candidate fields must align")
            expected = tuple(
                build_card_id(self.language, surface)
                for surface in self.candidate_surface_keys
            )
            if self.candidate_card_ids != expected:
                raise ValueError("ambiguous alias candidate IDs do not match surfaces")
        else:
            if any(
                (
                    self.canonical_card_id is not None,
                    self.surface_key is not None,
                    bool(self.candidate_card_ids),
                    bool(self.candidate_surface_keys),
                )
            ):
                raise ValueError("unresolved aliases cannot claim an identity")

    def to_dict(self) -> dict[str, object]:
        record: dict[str, object] = {
            "alias_version": ALIAS_RECORD_VERSION,
            "alias_namespace": self.alias_namespace,
            "alias_key": self.alias_key,
            "language": self.language,
            "mode": self.mode,
            "status": self.status,
            "provenance_status": self.provenance_status,
            "evidence": [item.to_dict() for item in self.evidence],
        }
        if self.canonical_card_id is not None:
            record["canonical_card_id"] = self.canonical_card_id
        if self.surface_key is not None:
            record["surface_key"] = self.surface_key
        if self.candidate_card_ids:
            record["candidate_card_ids"] = list(self.candidate_card_ids)
            record["candidate_surface_keys"] = list(self.candidate_surface_keys)
        return record


@dataclass(frozen=True, slots=True)
class ProgressAliasRegistry:
    """A complete flat alias registry for one language and activity mode."""

    language: str
    mode: str
    aliases: tuple[ProgressAlias, ...]
    sources: Mapping[str, AliasSource]

    def __post_init__(self) -> None:
        if _LANGUAGE_PATTERN.fullmatch(self.language) is None:
            raise ValueError("invalid registry language")
        if _SLUG_PATTERN.fullmatch(self.mode) is None:
            raise ValueError("invalid registry mode")
        keys: set[str] = set()
        for alias in self.aliases:
            if alias.language != self.language or alias.mode != self.mode:
                raise ValueError("alias scope does not match its registry")
            if alias.alias_key in keys:
                raise ValueError(f"duplicate alias key: {alias.alias_key}")
            keys.add(alias.alias_key)
        for source_id, source in self.sources.items():
            if not isinstance(source, AliasSource):
                raise ValueError("registry sources must be AliasSource records")
            if source_id != source.source_id:
                raise ValueError("alias source key does not match source_id")
        for alias in self.aliases:
            for item in alias.evidence:
                if item.source_id not in self.sources:
                    raise ValueError(
                        f"alias evidence references unknown source: {item.source_id}"
                    )

    def to_dict(self) -> dict[str, object]:
        return {
            "registry_version": ALIAS_REGISTRY_VERSION,
            "identity_version": IDENTITY_VERSION,
            "alias_namespace": ALIAS_NAMESPACE,
            "language": self.language,
            "mode": self.mode,
            "sources": {
                source_id: source.to_dict()
                for source_id, source in sorted(self.sources.items())
            },
            "aliases": [alias.to_dict() for alias in self.aliases],
        }

    def by_key(self) -> dict[str, ProgressAlias]:
        return {alias.alias_key: alias for alias in self.aliases}


def sorted_unique_evidence(
    evidence: Iterable[AliasEvidence],
) -> tuple[AliasEvidence, ...]:
    """Deduplicate evidence without relying on source traversal order."""

    return tuple(
        sorted(
            set(evidence),
            key=lambda item: (
                item.source_id,
                item.observation_kind,
                item.observed_surface_key or "",
            ),
        )
    )
