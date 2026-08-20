"""Stable, language-neutral card identity primitives."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Literal


IDENTITY_VERSION = "surface-card/v1"
SUPPORTED_UNIT_TYPES = frozenset({"surface"})
CARD_STATUSES = frozenset({"active", "retired", "merged"})

_LANGUAGE_PATTERN = re.compile(r"^[a-z]{2,3}$")
_CARD_ID_PATTERN = re.compile(r"^card_([a-z]{2,3})_([0-9a-f]{32})$")

CardStatus = Literal["active", "retired", "merged"]


def _validate_language(language: str) -> None:
    if not isinstance(language, str):
        raise TypeError("language must be a string")
    if not _LANGUAGE_PATTERN.fullmatch(language):
        raise ValueError(
            "language must be a lowercase ISO 639 language code such as 'fr'"
        )


def _validate_surface_key(surface_key: str) -> None:
    if not isinstance(surface_key, str):
        raise TypeError("surface_key must be a string")
    if not surface_key:
        raise ValueError("surface_key must not be empty")
    if surface_key != surface_key.strip():
        raise ValueError("surface_key must not contain surrounding whitespace")


def _validate_unit_type(unit_type: str) -> None:
    if unit_type not in SUPPORTED_UNIT_TYPES:
        supported = ", ".join(sorted(SUPPORTED_UNIT_TYPES))
        raise ValueError(f"unit_type must be one of: {supported}")


def build_card_id(
    language: str,
    surface_key: str,
    *,
    unit_type: str = "surface",
    identity_version: str = IDENTITY_VERSION,
) -> str:
    """Build a deterministic card ID from its complete identity tuple."""

    _validate_language(language)
    _validate_surface_key(surface_key)
    _validate_unit_type(unit_type)
    if identity_version != IDENTITY_VERSION:
        raise ValueError(f"unsupported identity version: {identity_version}")

    identity_tuple = [identity_version, language, unit_type, surface_key]
    payload = json.dumps(
        identity_tuple,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256(payload).digest()[:16].hex()
    return f"card_{language}_{digest}"


@dataclass(frozen=True, slots=True)
class CardRecord:
    card_id: str
    identity_version: str
    language: str
    unit_type: str
    surface_key: str
    display_form: str
    status: CardStatus = "active"
    redirect_card_id: str | None = None

    def __post_init__(self) -> None:
        expected_id = build_card_id(
            self.language,
            self.surface_key,
            unit_type=self.unit_type,
            identity_version=self.identity_version,
        )
        if self.card_id != expected_id:
            raise ValueError("card_id does not match the card identity fields")
        if not isinstance(self.display_form, str) or not self.display_form.strip():
            raise ValueError("display_form must be a non-empty string")
        if self.status not in CARD_STATUSES:
            allowed = ", ".join(sorted(CARD_STATUSES))
            raise ValueError(f"status must be one of: {allowed}")

        if self.status == "merged":
            if self.redirect_card_id is None:
                raise ValueError("a merged card must specify redirect_card_id")
            match = _CARD_ID_PATTERN.fullmatch(self.redirect_card_id)
            if match is None:
                raise ValueError("redirect_card_id is not a valid card ID")
            if match.group(1) != self.language:
                raise ValueError("a merged card cannot redirect across languages")
            if self.redirect_card_id == self.card_id:
                raise ValueError("a merged card cannot redirect to itself")
        elif self.redirect_card_id is not None:
            raise ValueError("only a merged card may specify redirect_card_id")

    def to_dict(self) -> dict[str, str]:
        record = {
            "card_id": self.card_id,
            "identity_version": self.identity_version,
            "language": self.language,
            "unit_type": self.unit_type,
            "surface_key": self.surface_key,
            "display_form": self.display_form,
            "status": self.status,
        }
        if self.redirect_card_id is not None:
            record["redirect_card_id"] = self.redirect_card_id
        return record


def create_card_record(
    language: str,
    surface_key: str,
    *,
    display_form: str | None = None,
    unit_type: str = "surface",
    status: CardStatus = "active",
    redirect_card_id: str | None = None,
) -> CardRecord:
    """Create and validate a card registry record."""

    return CardRecord(
        card_id=build_card_id(language, surface_key, unit_type=unit_type),
        identity_version=IDENTITY_VERSION,
        language=language,
        unit_type=unit_type,
        surface_key=surface_key,
        display_form=surface_key if display_form is None else display_form,
        status=status,
        redirect_card_id=redirect_card_id,
    )

