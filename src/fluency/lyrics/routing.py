"""Explicit routing-snapshot adapter for migration-stage Lyrics runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class RoutingSnapshot:
    method_id = "legacy-word-routing-snapshot/v1"

    def __init__(self, path: Path) -> None:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or value.get("schema_version") != 2:
            raise ValueError("word routing snapshot must use schema_version 2")
        self.value = value
        self.exclude = {
            str(word).casefold(): label
            for label, words in value.get("exclude", {}).items()
            for word in words
        }
        self.classifier = {
            str(word).casefold(): label
            for label, words in value.get("classifier", {}).items()
            for word in (words if isinstance(words, list) else words.keys())
        }
        self.derivations = {str(word).casefold(): target for word, target in value.get("derivation_map", {}).items()}
        self.discovery = {str(word).casefold() for word in value.get("sense_discovery", [])}
        self.clitics = {str(word).casefold(): target for word, target in value.get("clitic_merge", {}).items()}

    def route(self, form: str) -> dict[str, Any]:
        key = form.casefold()
        if key in self.exclude:
            return {"status": "excluded", "bucket": f"exclude.{self.exclude[key]}", "target": None}
        if key in self.classifier:
            return {"status": "classified", "bucket": f"classifier.{self.classifier[key]}", "target": None}
        if key in self.derivations:
            return {"status": "derived", "bucket": "derivation_map", "target": self.derivations[key]}
        if key in self.clitics:
            return {"status": "classified", "bucket": "clitic_merge", "target": self.clitics[key]}
        if key in self.discovery:
            return {"status": "review", "bucket": "sense_discovery", "target": None}
        return {"status": "unresolved", "bucket": "unresolved", "target": None}

