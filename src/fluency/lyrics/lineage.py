"""Construction and validation of append-only lyrics lineage events."""

from __future__ import annotations

from typing import Any

from fluency.core.hashing import canonical_content_id


EVENT_VERSION = "lyrics-lineage-event/v1"
PHASES = frozenset(
    {"acquire", "extract", "align", "normalize", "tag", "route", "menu", "assign", "consolidate", "assemble", "review"}
)
OPERATIONS = frozenset(
    {"preserve", "normalize", "split", "merge", "align", "tag", "route", "abstain", "assign", "exclude", "materialize", "override"}
)
EVIDENCE_KINDS = frozenset({"direct", "reconstructed", "materialized_snapshot", "human_review"})


def build_lineage_event(
    *,
    subject: dict[str, str],
    phase: str,
    operation: str,
    run_id: str,
    method_id: str,
    input_refs: list[dict[str, Any]],
    output_refs: list[dict[str, Any]],
    evidence_kind: str,
    decision: dict[str, Any] | None = None,
    reason_codes: list[str] | None = None,
    language_adapter: str | None = None,
) -> dict[str, Any]:
    body = {
        "record_version": EVENT_VERSION,
        "subject": subject,
        "phase": phase,
        "operation": operation,
        "run": {"run_id": run_id, "profile_id": None, "config_hash": None},
        "method": {
            "method_id": method_id,
            "version": None,
            "language_adapter": language_adapter,
        },
        "input_refs": input_refs,
        "output_refs": output_refs,
        "decision": decision,
        "reason_codes": reason_codes or [],
        "confidence": None,
        "evidence_kind": evidence_kind,
    }
    event_id = "event_" + canonical_content_id(body).removeprefix("sha256:")[:32]
    event = {"event_id": event_id, **body}
    validate_lineage_event(event)
    return event


def validate_lineage_event(event: dict[str, Any]) -> None:
    if event.get("record_version") != EVENT_VERSION:
        raise ValueError("unsupported lyrics lineage event")
    if not isinstance(event.get("event_id"), str) or not event["event_id"].startswith("event_"):
        raise ValueError("lineage event identity is invalid")
    if event.get("phase") not in PHASES or event.get("operation") not in OPERATIONS:
        raise ValueError("lineage event phase or operation is invalid")
    if event.get("evidence_kind") not in EVIDENCE_KINDS:
        raise ValueError("lineage evidence kind is invalid")
    subject = event.get("subject")
    if not isinstance(subject, dict) or not isinstance(subject.get("id"), str):
        raise ValueError("lineage event subject is missing")
    for field in ("input_refs", "output_refs"):
        refs = event.get(field)
        if not isinstance(refs, list) or any(
            not isinstance(ref, dict)
            or not isinstance(ref.get("kind"), str)
            or not isinstance(ref.get("id"), str)
            for ref in refs
        ):
            raise ValueError(f"lineage event {field} are invalid")

