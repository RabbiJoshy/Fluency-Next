"""Backwards-compatible re-export of the projection vocabulary.

Moved to :mod:`fluency.projections` so the release stage no longer depends on
the WSD package. Existing imports keep working; new code should import from
``fluency.projections``.
"""

from fluency.projections import (  # noqa: F401
    PUBLICATION_PROJECTIONS,
    SELECTION_PROJECTIONS,
    materialize_selection,
    publishes_exact_leaf,
)

__all__ = [
    "PUBLICATION_PROJECTIONS",
    "SELECTION_PROJECTIONS",
    "materialize_selection",
    "publishes_exact_leaf",
]
