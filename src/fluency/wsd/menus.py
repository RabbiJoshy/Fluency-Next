"""Provider-neutral closed sense menus with strict analysis identity."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from fluency.core.hashing import canonical_content_id


SENSE_MENU_VERSION = "sense-menu/v1"


@dataclass(frozen=True, slots=True)
class SenseLeaf:
    sense_id: str
    translation: str
    definition: str
    source_reference: str
    provider_metadata: Mapping[str, Any]

    def __post_init__(self) -> None:
        for name, value in (
            ("sense_id", self.sense_id),
            ("source_reference", self.source_reference),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must not be empty")
        if not isinstance(self.translation, str):
            raise ValueError("translation must be a string")

    @property
    def gloss_text(self) -> str:
        return " — ".join(value for value in (self.translation, self.definition) if value)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sense_id": self.sense_id,
            "translation": self.translation,
            "definition": self.definition,
            "source_reference": self.source_reference,
            "provider_metadata": dict(self.provider_metadata),
        }


def build_analysis_id(
    *,
    card_id: str,
    source_adapter: str,
    source_analysis_key: str,
) -> str:
    if not source_adapter or not source_analysis_key:
        raise ValueError("analysis identity requires source adapter and source key")
    digest = canonical_content_id(
        [SENSE_MENU_VERSION, card_id, source_adapter, source_analysis_key]
    ).removeprefix("sha256:")
    return f"analysis_{digest[:32]}"


@dataclass(frozen=True, slots=True)
class MenuAnalysis:
    menu_analysis_id: str
    card_id: str
    surface_form: str
    headword: str
    part_of_speech: str
    source_adapter: str
    source_analysis_key: str
    senses: tuple[SenseLeaf, ...]
    provider_metadata: Mapping[str, Any]

    def __post_init__(self) -> None:
        expected = build_analysis_id(
            card_id=self.card_id,
            source_adapter=self.source_adapter,
            source_analysis_key=self.source_analysis_key,
        )
        if self.menu_analysis_id != expected:
            raise ValueError("menu_analysis_id does not match its source identity")
        for name, value in (
            ("surface_form", self.surface_form),
            ("headword", self.headword),
            ("part_of_speech", self.part_of_speech),
        ):
            if not value.strip():
                raise ValueError(f"{name} must not be empty")
        if not self.senses:
            raise ValueError("a menu analysis must contain at least one sense")
        ids = [sense.sense_id for sense in self.senses]
        if len(ids) != len(set(ids)):
            raise ValueError("sense IDs must be unique inside an analysis")

    def sense(self, sense_id: str) -> SenseLeaf:
        for leaf in self.senses:
            if leaf.sense_id == sense_id:
                return leaf
        raise KeyError(f"sense is not in analysis {self.menu_analysis_id}: {sense_id}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "menu_analysis_id": self.menu_analysis_id,
            "headword": self.headword,
            "part_of_speech": self.part_of_speech,
            "source_analysis_key": self.source_analysis_key,
            "senses": [sense.to_dict() for sense in self.senses],
            "provider_metadata": dict(self.provider_metadata),
        }


def require_analysis(
    analyses: Iterable[MenuAnalysis],
    menu_analysis_id: str,
) -> MenuAnalysis:
    """Resolve only an exact analysis ID; never use ordering or headword similarity."""

    matches = [item for item in analyses if item.menu_analysis_id == menu_analysis_id]
    if len(matches) != 1:
        raise KeyError(f"exact menu analysis is unavailable: {menu_analysis_id}")
    return matches[0]
