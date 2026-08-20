"""Language-neutral records emitted by deterministic tokenizers."""

from __future__ import annotations

from dataclasses import dataclass


TOKEN_UNIT_VERSION = "token-unit/v1"
TOKEN_CLASSES = frozenset(
    {
        "word",
        "known_surface",
        "elided_clitic",
        "number",
        "mixed",
        "inversion_marker",
        "unresolved_hyphenated",
        "source_fragment",
    }
)
TOKEN_DECISIONS = frozenset(
    {
        "ordinary_token",
        "approved_surface_longest_match",
        "french_elision_split",
        "french_hyphen_split",
        "retained_nonlexical",
        "quarantined_source_fragment",
        "unresolved_hyphenation",
    }
)


@dataclass(frozen=True, slots=True)
class TokenUnit:
    observed_text: str
    surface_key: str | None
    start: int
    end: int
    token_class: str
    decision: str
    eligible: bool
    parent_text: str | None = None
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if not self.observed_text:
            raise ValueError("observed_text must not be empty")
        if self.start < 0 or self.end <= self.start:
            raise ValueError("token offsets must describe a non-empty span")
        if self.end - self.start != len(self.observed_text):
            raise ValueError("token offsets must match observed_text length")
        if self.token_class not in TOKEN_CLASSES:
            raise ValueError(f"unsupported token_class: {self.token_class}")
        if self.decision not in TOKEN_DECISIONS:
            raise ValueError(f"unsupported token decision: {self.decision}")
        if self.eligible:
            if not self.surface_key:
                raise ValueError("eligible tokens require a surface_key")
            if self.rejection_reason is not None:
                raise ValueError("eligible tokens cannot have a rejection_reason")
        else:
            if self.surface_key is not None:
                raise ValueError("ineligible tokens cannot have a surface_key")
            if not self.rejection_reason:
                raise ValueError("ineligible tokens require a rejection_reason")

    def to_dict(self) -> dict[str, object]:
        record: dict[str, object] = {
            "record_version": TOKEN_UNIT_VERSION,
            "observed_text": self.observed_text,
            "surface_key": self.surface_key,
            "start": self.start,
            "end": self.end,
            "token_class": self.token_class,
            "decision": self.decision,
            "eligible": self.eligible,
        }
        if self.parent_text is not None:
            record["parent_text"] = self.parent_text
        if self.rejection_reason is not None:
            record["rejection_reason"] = self.rejection_reason
        return record


@dataclass(frozen=True, slots=True)
class TokenizationResult:
    canonical_text: str
    units: tuple[TokenUnit, ...]

