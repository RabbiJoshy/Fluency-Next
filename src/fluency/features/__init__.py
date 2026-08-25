"""Provider-neutral sense features.

This package is the contract between two sides that must not import each other:

    extractors (dictionary adapters)  ->  features  <-  specialists (WSD)

A dictionary adapter emits features from whatever its provider happens to carry.
A WSD specialist consumes whichever families are present and tolerates absence.
Neither knows the other exists, so a feature can be added without touching a
classifier, and a classifier can change without re-running extraction.

It previously lived under ``fluency.wsd``, which meant a sense menu could not be
built unless the WSD package imported cleanly -- even though WSD is optional
enrichment and the menu stage runs long before it.
"""

from fluency.features.contract import (
    FEATURE_FAMILIES,
    FeatureFamily,
    SpecialistFeature,
)

__all__ = ["FEATURE_FAMILIES", "FeatureFamily", "SpecialistFeature"]
