"""Preserve flattened Artist assignments in the dual-view WSD contract."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import Any, Iterable

from fluency.core.hashing import canonical_content_id


ARTIST_WSD_EVIDENCE_VERSION = "artist-wsd-evidence/v1"
WSD_DISTRIBUTION_VERSION = "wsd-distribution/v1"
SUPPORT_LEVELS = ("leaf", "glosskey", "tuple", "unresolved")


class ArtistWSDBridgeError(ValueError):
    """Raised when flattened Artist assets cannot be bridged without guessing."""


def _decision_id(card_id: str, bucket_index: int, example_index: int, record: dict[str, Any]) -> str:
    identity = {
        "card_id": card_id,
        "bucket_index": bucket_index,
        "example_index": example_index,
        "song": record.get("song"),
        "target": record.get("spanish", record.get("target")),
        "timestamp_ms": record.get("timestamp_ms"),
    }
    return "materialized_decision_" + canonical_content_id(identity).removeprefix("sha256:")[:32]


def bridge_materialized_assignments(
    index: list[dict[str, Any]],
    examples: dict[str, dict[str, Any]],
    master: dict[str, dict[str, Any]],
    *,
    artist_slug: str,
    allow_migration: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Add the forced-leaf view while declaring absent support evidence honestly.

    Legacy Artist assets retain final sense buckets but not the independent v7
    supported-specificity decision.  The bridge preserves every flattened
    assignment as a forced decision and leaves ``supported_selection`` absent;
    it never promotes a missing confidence judgment into a supported leaf.

    This is a **migration** path. It gives historical decisions the current
    contract's shape; it does not recompute them. Passing
    ``allow_migration=False`` refuses that, which is what a run wanting genuine
    v7 decisions should do -- otherwise older choices are frozen behind a v7
    label and every later measurement silently describes the wrong classifier.
    """

    if not allow_migration:
        raise ArtistWSDBridgeError(
            "migration is disabled for this run: flattened assignments would be "
            "given the v7 contract without being recomputed by v7. Run WSD "
            "natively, or set allow_migration=True to ship retained decisions."
        )

    bridged_index = deepcopy(index)
    evidence_cards: dict[str, Any] = {}
    seen_decision_ids: set[str] = set()
    total_decisions = 0

    for card in bridged_index:
        if not isinstance(card, dict):
            raise ArtistWSDBridgeError("Artist index contains a non-object card")
        card_id = card.get("id")
        if not isinstance(card_id, str) or not card_id:
            raise ArtistWSDBridgeError("Artist index card is missing its ID")
        master_card = master.get(card_id)
        split = examples.get(card_id)
        if not isinstance(master_card, dict) or not isinstance(split, dict):
            raise ArtistWSDBridgeError(f"Artist WSD bridge cannot resolve card {card_id}")
        senses = master_card.get("senses") or []
        buckets = split.get("m") or []
        if not isinstance(senses, list) or not isinstance(buckets, list) or len(senses) != len(buckets):
            raise ArtistWSDBridgeError(
                f"Artist WSD bridge sense/example buckets disagree for {card_id}"
            )

        forced_counts: Counter[str] = Counter()
        decisions: list[dict[str, Any]] = []
        for bucket_index, (sense, bucket) in enumerate(zip(senses, buckets, strict=True)):
            if not isinstance(sense, dict) or not isinstance(bucket, list):
                raise ArtistWSDBridgeError(f"Artist WSD bridge bucket is invalid for {card_id}")
            sense_id = sense.get("sense_id")
            if not isinstance(sense_id, str) or not sense_id:
                if bucket:
                    raise ArtistWSDBridgeError(
                        f"Materialized assignments lack a sense ID for {card_id}"
                    )
                continue
            for example_index, record in enumerate(bucket):
                if not isinstance(record, dict):
                    raise ArtistWSDBridgeError(
                        f"Materialized assignment is invalid for {card_id}"
                    )
                decision_id = _decision_id(card_id, bucket_index, example_index, record)
                if decision_id in seen_decision_ids:
                    raise ArtistWSDBridgeError("Materialized WSD decision identity collided")
                seen_decision_ids.add(decision_id)
                forced_counts[sense_id] += 1
                decisions.append({
                    "decision_id": decision_id,
                    "subject": {
                        "kind": "materialized_example",
                        "bucket_index": bucket_index,
                        "example_index": example_index,
                    },
                    "forced_selection": {
                        "sense_id": sense_id,
                        "selected_tuple": {
                            "headword": sense.get("headword") or master_card.get("lemma") or master_card.get("word"),
                            "part_of_speech": sense.get("pos"),
                        },
                    },
                    "supported_selection": None,
                    "supported_status": "not_recorded",
                    "provenance": {
                        "assignment_method": record.get("assignment_method"),
                        "prompt_id": record.get("prompt_id"),
                        "run_ts": record.get("run_ts"),
                    },
                })

        if not decisions:
            continue
        denominator = len(decisions)
        distribution = {
            "distribution_version": WSD_DISTRIBUTION_VERSION,
            "selection_projection": "provider_only",
            "publication_projection": "forced_leaf",
            "denominator": denominator,
            "forced_leaf_counts": dict(forced_counts),
            "supported_leaf_counts": {},
            "published_leaf_counts": dict(forced_counts),
            "supported_level_counts": {level: 0 for level in SUPPORT_LEVELS},
            "status_counts": {"assigned": denominator},
            "known_leaf_mass": denominator,
            "unresolved_mass": 0,
            "supported_unavailable_mass": denominator,
        }
        card["wsd_distribution"] = distribution
        evidence_cards[card_id] = {
            "surface_form": master_card.get("word"),
            "lemma": master_card.get("lemma"),
            "distribution": distribution,
            "decisions": decisions,
        }
        total_decisions += denominator

    if not evidence_cards:
        return bridged_index, None
    evidence = {
        "evidence_version": ARTIST_WSD_EVIDENCE_VERSION,
        "artist_slug": artist_slug,
        "selection_projection": "provider_only",
        "publication_views": {
            "forced_leaf": {"status": "available"},
            "supported_specificity": {"status": "not_recorded"},
        },
        "source_kind": "retained_materialized_assignments",
        "card_count": len(evidence_cards),
        "decision_count": total_decisions,
        "cards": evidence_cards,
    }
    validate_artist_wsd_evidence(evidence)
    return bridged_index, evidence


def overlay_native_assignments(
    index: list[dict[str, Any]], evidence: dict[str, Any] | None,
    master: dict[str, dict[str, Any]], records: Iterable[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Overlay native v7 decisions without guessing across inventory drift."""
    result_index = deepcopy(index)
    index_by_id = {str(card["id"]): card for card in result_index}
    by_surface: dict[str, list[str]] = {}
    by_sense: dict[str, list[tuple[str, str]]] = {}
    for card_id, card in master.items():
        by_surface.setdefault(str(card.get("word") or "").casefold(), []).append(card_id)
        for sense in card.get("senses") or []:
            canonical = sense.get("sense_id")
            if not canonical:
                continue
            for sense_id in (canonical, *(sense.get("sense_id_aliases") or [])):
                by_sense.setdefault(str(sense_id), []).append((card_id, str(canonical)))

    native: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        assignment = record.get("assignment") or {}
        projection = (assignment.get("selection_projections") or {}).get("provider_only") or {}
        selected_id = projection.get("selected_sense_id")
        if not selected_id:
            raise ArtistWSDBridgeError("native v7 record lost its provider-only leaf")
        surface_ids = set(by_surface.get(str(record.get("surface") or "").casefold(), []))
        matches = by_sense.get(str(selected_id), [])
        matches = [match for match in matches if match[0] in surface_ids] or matches
        canonical = matches[0][1] if matches else None
        card_id = matches[0][0] if matches else (next(iter(surface_ids)) if len(surface_ids) == 1 else None)
        if card_id is None:
            continue
        level = str(projection.get("emitted_level") or assignment.get("emitted_level") or "unresolved")
        status = "assigned"
        if canonical is None:
            level, status = "unresolved", "inventory_mismatch"
        supported: dict[str, Any] = {"level": level}
        if level == "leaf":
            supported.update(sense_id=canonical, selected_tuple=projection.get("selected_tuple"))
        elif level in {"glosskey", "tuple"}:
            supported["selected_tuple"] = projection.get("selected_tuple")
        identity = {
            "card_id": card_id, "occurrence_id": record.get("occurrence_id"),
            "example_id": record.get("example_id"), "example_index": record.get("example_index"),
        }
        native.setdefault(card_id, []).append({
            "decision_id": "native_v7_" + canonical_content_id(identity).removeprefix("sha256:")[:32],
            "subject": {"kind": "persisted_occurrence", **{k: record.get(k) for k in ("occurrence_id", "example_id", "example_index")}},
            "forced_selection": {"sense_id": canonical or selected_id, "selected_tuple": projection.get("selected_tuple")},
            "supported_selection": supported,
            "supported_status": status,
            "provenance": {"assignment_method": "native-v7", "menu_analysis_id": projection.get("menu_analysis_id"), "raw_margin": projection.get("raw_margin")},
        })

    result = deepcopy(evidence or {
        "evidence_version": ARTIST_WSD_EVIDENCE_VERSION, "artist_slug": "unknown",
        "selection_projection": "provider_only", "cards": {},
    })
    cards = result.setdefault("cards", {})
    for card_id, decisions in native.items():
        forced = Counter(row["forced_selection"]["sense_id"] for row in decisions)
        supported = Counter(
            row["supported_selection"]["sense_id"] for row in decisions
            if row["supported_selection"]["level"] == "leaf"
        )
        levels = Counter(row["supported_selection"]["level"] for row in decisions)
        statuses = Counter(row["supported_status"] for row in decisions)
        distribution = {
            "distribution_version": WSD_DISTRIBUTION_VERSION,
            "selection_projection": "provider_only", "publication_projection": "forced_leaf",
            "denominator": len(decisions), "forced_leaf_counts": dict(forced),
            "supported_leaf_counts": dict(supported), "published_leaf_counts": dict(forced),
            "supported_level_counts": {level: levels[level] for level in SUPPORT_LEVELS},
            "status_counts": dict(statuses), "known_leaf_mass": sum(supported.values()),
            "unresolved_mass": levels["unresolved"], "supported_unavailable_mass": levels["unresolved"],
        }
        index_by_id[card_id]["wsd_distribution"] = distribution
        cards[card_id] = {"surface_form": master[card_id].get("word"), "lemma": master[card_id].get("lemma"), "distribution": distribution, "decisions": decisions}
    result["publication_views"] = {"forced_leaf": {"status": "available"}, "supported_specificity": {"status": "available"}}
    result["source_kind"] = "native_v7_with_materialized_fallback"
    result["card_count"] = len(cards)
    result["decision_count"] = sum(len(card["decisions"]) for card in cards.values())
    validate_artist_wsd_evidence(result)
    return result_index, result


def validate_artist_wsd_evidence(evidence: dict[str, Any]) -> None:
    """Validate the release-facing envelope shared by imported and native WSD."""

    if evidence.get("evidence_version") != ARTIST_WSD_EVIDENCE_VERSION:
        raise ArtistWSDBridgeError("unsupported Artist WSD evidence version")
    cards = evidence.get("cards")
    if not isinstance(cards, dict) or len(cards) != evidence.get("card_count"):
        raise ArtistWSDBridgeError("Artist WSD evidence card count disagrees")
    decisions = 0
    for card_id, card in cards.items():
        if not isinstance(card_id, str) or not isinstance(card, dict):
            raise ArtistWSDBridgeError("Artist WSD evidence contains an invalid card")
        distribution = card.get("distribution")
        rows = card.get("decisions")
        if not isinstance(distribution, dict) or not isinstance(rows, list):
            raise ArtistWSDBridgeError("Artist WSD evidence card is incomplete")
        if distribution.get("distribution_version") != WSD_DISTRIBUTION_VERSION:
            raise ArtistWSDBridgeError("Artist WSD distribution version is invalid")
        if distribution.get("denominator") != len(rows):
            raise ArtistWSDBridgeError("Artist WSD denominator disagrees")
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("forced_selection"), dict):
                raise ArtistWSDBridgeError("Artist WSD evidence lost a forced selection")
            supported = row.get("supported_selection")
            if supported is not None and (
                not isinstance(supported, dict) or supported.get("level") not in SUPPORT_LEVELS
            ):
                raise ArtistWSDBridgeError("Artist WSD supported selection is invalid")
        decisions += len(rows)
    if decisions != evidence.get("decision_count"):
        raise ArtistWSDBridgeError("Artist WSD evidence decision count disagrees")
