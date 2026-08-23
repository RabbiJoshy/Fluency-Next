"""Typed, scoped, and attributable human overrides for Lyrics routing."""

from __future__ import annotations

import json
from pathlib import Path
import unicodedata
from typing import Any


REGISTRY_VERSION = "lyrics-routing-overrides/v1"


class RoutingOverrideError(ValueError):
    """Raised when an override registry is ambiguous or structurally invalid."""


class RoutingOverrideRegistry:
    """Resolve at most one explicit human decision for a routed surface.

    Empty scope lists mean "all". Multiple matching active entries are rejected so
    there is never an undocumented precedence rule between human decisions.
    """

    def __init__(
        self,
        path: Path,
        *,
        language: str,
        mode: str,
        artist_id: str | None,
        song_id: str | None,
    ) -> None:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or value.get("schema_version") != REGISTRY_VERSION:
            raise RoutingOverrideError(f"override registry must use {REGISTRY_VERSION}")
        entries = value.get("entries")
        if not isinstance(entries, list):
            raise RoutingOverrideError("override registry entries must be an array")
        identifiers: set[str] = set()
        self.entries: list[dict[str, Any]] = []
        for entry in entries:
            if not isinstance(entry, dict):
                raise RoutingOverrideError("every override entry must be an object")
            identifier = entry.get("override_id")
            if not isinstance(identifier, str) or not identifier:
                raise RoutingOverrideError("every override requires an override_id")
            if identifier in identifiers:
                raise RoutingOverrideError(f"duplicate override_id: {identifier}")
            identifiers.add(identifier)
            if entry.get("status") not in {"active", "revoked"}:
                raise RoutingOverrideError(f"override {identifier} has an invalid status")
            decision = entry.get("decision")
            if not isinstance(decision, dict) or not decision.get("status") or not decision.get("bucket"):
                raise RoutingOverrideError(f"override {identifier} requires a complete decision")
            if not all(entry.get(field) for field in ("language", "normalized_form", "reason", "author", "created_at")):
                raise RoutingOverrideError(f"override {identifier} is missing attribution")
            scope = entry.get("scope", {})
            if not isinstance(scope, dict):
                raise RoutingOverrideError(f"override {identifier} scope must be an object")
            for field in ("modes", "artist_ids", "song_ids"):
                if not isinstance(scope.get(field, []), list):
                    raise RoutingOverrideError(f"override {identifier} scope.{field} must be an array")
            self.entries.append(entry)
        self.language = language
        self.mode = mode
        self.artist_id = artist_id
        self.song_id = song_id

    @staticmethod
    def _form(value: str) -> str:
        return unicodedata.normalize("NFC", value).casefold()

    @staticmethod
    def _allows(values: list[str], current: str | None) -> bool:
        return not values or (current is not None and current in values)

    def match(self, form: str) -> dict[str, Any] | None:
        key = self._form(form)
        matches: list[dict[str, Any]] = []
        for entry in self.entries:
            scope = entry.get("scope", {})
            if (
                entry["status"] == "active"
                and entry["language"] == self.language
                and self._form(entry["normalized_form"]) == key
                and self._allows(scope.get("modes", []), self.mode)
                and self._allows(scope.get("artist_ids", []), self.artist_id)
                and self._allows(scope.get("song_ids", []), self.song_id)
            ):
                matches.append(entry)
        if len(matches) > 1:
            identifiers = ", ".join(sorted(entry["override_id"] for entry in matches))
            raise RoutingOverrideError(f"conflicting active overrides for {form!r}: {identifiers}")
        return matches[0] if matches else None
