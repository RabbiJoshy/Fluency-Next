"""Backwards-compatible re-export of the provider-neutral feature contract.

The contract moved to :mod:`fluency.features` so that dictionary adapters stop
depending on the WSD package. Existing imports keep working; new code should
import from ``fluency.features`` directly.
"""

from fluency.features.contract import (
    FEATURE_FAMILIES,
    FeatureFamily,
    SpecialistFeature,
)

__all__ = ["FEATURE_FAMILIES", "FeatureFamily", "SpecialistFeature"]
