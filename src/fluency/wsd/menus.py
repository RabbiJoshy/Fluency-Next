"""Backwards-compatible re-export of the sense-menu contract.

The contract moved to :mod:`fluency.menus` so that the sense-menu stage no
longer depends on the WSD package. Existing imports keep working; new code
should import from ``fluency.menus`` directly.
"""

from fluency.menus import (  # noqa: F401
    SENSE_MENU_VERSION,
    MenuAnalysis,
    SenseLeaf,
    build_analysis_id,
    require_analysis,
)

__all__ = [
    "SENSE_MENU_VERSION",
    "MenuAnalysis",
    "SenseLeaf",
    "build_analysis_id",
    "require_analysis",
]
