"""Canonical accounting envelope for dictionary sense metadata.

The feature taxonomy is intentionally allowed to grow.  This envelope is the
stable part: every adapter says what it inspected, retains its provider data,
and accounts for material that is not yet represented by a typed feature.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

from fluency.features.contract import SpecialistFeature


METADATA_CONTRACT_VERSION = "sense-metadata/v1"
CoverageState = Literal["parsed", "preserved", "unavailable", "not_applicable"]
COVERAGE_STATES = frozenset({"parsed", "preserved", "unavailable", "not_applicable"})


def _accounting_items(
    name: str, items: tuple[Mapping[str, Any], ...]
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, Mapping):
            raise ValueError(f"{name} metadata entries must be mappings")
        source_field = item.get("source_field")
        reason = item.get("reason")
        if not isinstance(source_field, str) or not source_field.strip():
            raise ValueError(f"{name} metadata requires source_field")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError(f"{name} metadata requires reason")
        records.append(dict(item))
    return records


@dataclass(frozen=True, slots=True)
class MetadataAccounting:
    """What an adapter knew how to do with the metadata it encountered."""

    coverage: Mapping[str, CoverageState] = field(default_factory=dict)
    unclassified: tuple[Mapping[str, Any], ...] = ()
    ignored: tuple[Mapping[str, Any], ...] = ()

    def __post_init__(self) -> None:
        for source_field, state in self.coverage.items():
            if not isinstance(source_field, str) or not source_field.strip():
                raise ValueError("metadata coverage field names must not be empty")
            if state not in COVERAGE_STATES:
                raise ValueError(f"unsupported metadata coverage state: {state}")
        _accounting_items("unclassified", self.unclassified)
        _accounting_items("ignored", self.ignored)

    def envelope(
        self,
        *,
        source_metadata: Mapping[str, Any],
        features: tuple[SpecialistFeature, ...],
    ) -> dict[str, Any]:
        return {
            "contract_version": METADATA_CONTRACT_VERSION,
            "features": [feature.to_dict() for feature in features],
            "source_metadata": dict(source_metadata),
            "coverage": dict(sorted(self.coverage.items())),
            "unclassified": _accounting_items("unclassified", self.unclassified),
            "ignored": _accounting_items("ignored", self.ignored),
        }

    @classmethod
    def from_envelope(cls, value: Mapping[str, Any] | None) -> "MetadataAccounting":
        """Rebuild accounting while accepting menus made before the envelope."""

        if not value:
            return cls()
        if value.get("contract_version") != METADATA_CONTRACT_VERSION:
            raise ValueError("unsupported sense metadata contract")
        coverage = value.get("coverage", {})
        unclassified = value.get("unclassified", [])
        ignored = value.get("ignored", [])
        if not isinstance(coverage, Mapping):
            raise ValueError("metadata coverage must be a mapping")
        if not isinstance(unclassified, list) or not isinstance(ignored, list):
            raise ValueError("metadata accounting collections must be lists")
        return cls(
            coverage=dict(coverage),
            unclassified=tuple(unclassified),
            ignored=tuple(ignored),
        )
