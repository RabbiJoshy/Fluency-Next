"""French dictionary lookup candidates that never alter card identity."""

from __future__ import annotations

from dataclasses import dataclass

from fluency.core.identity import CardRecord
from fluency.languages.french.tokenization import load_tokenization_config


LOOKUP_CANDIDATE_VERSION = "lookup-candidate/v1"


@dataclass(frozen=True, slots=True)
class LookupCandidate:
    card_id: str
    surface_key: str
    lookup_form: str
    relation: str
    priority: int
    reason: str

    def __post_init__(self) -> None:
        if self.priority < 0:
            raise ValueError("lookup priority must not be negative")
        if self.relation not in {"exact", "elision_expansion"}:
            raise ValueError(f"unsupported lookup relation: {self.relation}")
        if not self.lookup_form or not self.reason:
            raise ValueError("lookup form and reason must not be empty")

    def to_dict(self) -> dict[str, object]:
        return {
            "record_version": LOOKUP_CANDIDATE_VERSION,
            "card_id": self.card_id,
            "surface_key": self.surface_key,
            "lookup_form": self.lookup_form,
            "relation": self.relation,
            "priority": self.priority,
            "reason": self.reason,
        }


def build_lookup_candidates(card: CardRecord) -> tuple[LookupCandidate, ...]:
    if card.language != "fr":
        raise ValueError("French lookup candidates require a French card")

    candidates = [
        LookupCandidate(
            card_id=card.card_id,
            surface_key=card.surface_key,
            lookup_form=card.surface_key,
            relation="exact",
            priority=0,
            reason="Exact surface lookup",
        )
    ]
    expansions = load_tokenization_config().elision_expansions.get(card.surface_key, ())
    for lookup_form in expansions:
        candidates.append(
            LookupCandidate(
                card_id=card.card_id,
                surface_key=card.surface_key,
                lookup_form=lookup_form,
                relation="elision_expansion",
                priority=1,
                reason=f"French {card.surface_key} may represent {lookup_form}",
            )
        )
    return tuple(candidates)

