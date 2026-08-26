"""Provider-neutral sense features exposed to optional WSD specialists."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping


# `companion` is a word the sense requires nearby -- SpanishDict writes it as
# prose ("used with \"de\""), Wiktionary as a structured +obj template. Unlike the
# other families it is checkable rather than comparable: a gate can ask whether
# the word is present, instead of scoring a similarity.
FEATURE_FAMILIES = frozenset({"domain", "register", "construction", "companion"})
FeatureFamily = Literal["domain", "register", "construction", "companion"]


@dataclass(frozen=True, slots=True)
class SpecialistFeature:
    family: FeatureFamily
    kind: str
    value: str
    embedding_text: str

    def __post_init__(self) -> None:
        if self.family not in FEATURE_FAMILIES:
            raise ValueError("unsupported specialist feature family")
        for name, value in (
            ("kind", self.kind),
            ("value", self.value),
            ("embedding_text", self.embedding_text),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"specialist feature {name} must not be empty")

    def to_dict(self) -> dict[str, str]:
        return {
            "family": self.family,
            "kind": self.kind,
            "value": self.value,
            "embedding_text": self.embedding_text,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SpecialistFeature":
        if not isinstance(value, Mapping) or set(value) != {
            "family", "kind", "value", "embedding_text"
        }:
            raise ValueError("specialist feature fields do not match the contract")
        return cls(
            family=value["family"],
            kind=value["kind"],
            value=value["value"],
            embedding_text=value["embedding_text"],
        )


# Companion notes sometimes name a grammatical FORM rather than a word to look
# for in the line -- "used with an infinitive", "[with gerund]". Those constrain
# construction; only a real word can be a companion, because only a real word can
# be searched for.
GRAMMATICAL_FORMS = frozenset(
    {"a", "an", "the", "infinitive", "gerund", "participle", "subjunctive",
     "adjective", "adverb", "noun", "pronoun", "clause",
     # "[with direct object]", "[with indirect object]"
     "direct", "indirect", "object", "reflexive"}
)
