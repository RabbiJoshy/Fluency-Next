"""Pure v7 projection helpers; changing a view never reruns WSD."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


SELECTION_PROJECTIONS = frozenset({"provider_only", "mwe_augmented"})
PUBLICATION_PROJECTIONS = frozenset({"forced_leaf", "supported_specificity"})


def materialize_selection(
    assignment: dict[str, Any], selection_projection: str
) -> dict[str, Any]:
    """Return one immutable Stage-04 row viewed through a candidate universe."""

    if selection_projection not in SELECTION_PROJECTIONS:
        raise ValueError("unsupported WSD selection projection")
    row = deepcopy(assignment)
    if row.get("status") != "assigned":
        return row
    projections = row.get("selection_projections")
    if not isinstance(projections, dict):
        if selection_projection != "provider_only":
            raise ValueError(
                "mwe_augmented projection requires a v7 assignment; WSD must not be guessed"
            )
        return row
    projection = projections.get(selection_projection)
    if not isinstance(projection, dict):
        # No expression was present, so both candidate universes are identical.
        if selection_projection == "mwe_augmented":
            projection = projections.get("provider_only")
            if isinstance(projection, dict):
                projections = deepcopy(projections)
                projections["mwe_augmented"] = deepcopy(projection)
                row["selection_projections"] = projections
        if not isinstance(projection, dict):
            raise ValueError("requested WSD selection projection is unavailable")
    row["menu_analysis_id"] = projection["menu_analysis_id"]
    row["selected_sense_id"] = projection["selected_sense_id"]
    row["selected_tuple"] = deepcopy(projection["selected_tuple"])
    row["emitted_level"] = projection["emitted_level"]
    evidence = deepcopy(row.get("evidence") or {})
    expression = None
    if projection.get("source_kind") == "multiword":
        expression = next(
            (
                item.get("expression")
                for item in evidence.get("multiword_candidates", [])
                if isinstance(item, dict)
                and item.get("menu_analysis_id") == projection["menu_analysis_id"]
                and item.get("expression_id") == projection["selected_sense_id"]
            ),
            None,
        )
        if not expression:
            raise ValueError("materialized multiword projection lacks candidate evidence")
    evidence["selected_multiword"] = expression
    evidence["release_selection_projection"] = selection_projection
    row["evidence"] = evidence
    row["active_selection_projection"] = selection_projection
    return row


def publishes_exact_leaf(assignment: dict[str, Any], publication_projection: str) -> bool:
    if publication_projection not in PUBLICATION_PROJECTIONS:
        raise ValueError("unsupported WSD publication projection")
    if assignment.get("status") != "assigned":
        return False
    return (
        publication_projection == "forced_leaf"
        or assignment.get("emitted_level") == "leaf"
    )
