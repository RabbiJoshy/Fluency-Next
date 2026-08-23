"""Shared Lyrics routing contract and legacy-snapshot comparator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol


class LyricsRouter(Protocol):
    method_id: str
    evidence_kind: str

    def route(self, form: str) -> dict[str, Any]: ...


class RoutingSnapshot:
    method_id = "legacy-word-routing-snapshot/v1"
    evidence_kind = "materialized_snapshot"

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
            return self._decision("excluded", f"exclude.{self.exclude[key]}")
        if key in self.classifier:
            return self._decision("classified", f"classifier.{self.classifier[key]}")
        if key in self.derivations:
            return self._decision("derived", "derivation_map", self.derivations[key])
        if key in self.clitics:
            return self._decision("classified", "clitic_merge", self.clitics[key])
        if key in self.discovery:
            return self._decision("review", "sense_discovery")
        return self._decision("unresolved", "unresolved")

    @staticmethod
    def _decision(status: str, bucket: str, target: str | None = None) -> dict[str, Any]:
        return {
            "status": status,
            "bucket": bucket,
            "target": target,
            "reason_codes": ["snapshot_bucket_lookup"],
            "consulted_inputs": ["routing_snapshot"],
            "details": {},
            "policy_trace": [
                {
                    "policy_id": "legacy.snapshot_bucket_lookup/v1",
                    "outcome": "match",
                    "inputs": ["routing_snapshot"],
                    "evidence": {"bucket": bucket},
                }
            ],
            "evidence_kind": "materialized_snapshot",
        }
