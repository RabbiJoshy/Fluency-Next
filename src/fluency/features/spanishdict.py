"""Extract provider-neutral features from SpanishDict senses.

The companion note is the reason this exists. SpanishDict records it as prose
inside ``context`` -- ``to remove; used with "de"`` -- while Wiktionary records
the same fact as a structured ``+obj`` template. Same concept, two encodings, so
it belongs behind an adapter rather than being read as a feature of either
provider.

Measured: 587 SpanishDict senses carry one (de 149, con 132, a 127, en 72,
por 40), against 632 in Portuguese Wiktionary (de 126, em 119, com 91, a 87).
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from fluency.features.contract import GRAMMATICAL_FORMS, SpecialistFeature


# `used with "de"`, `used with de`, `used with an infinitive`
COMPANION = re.compile(r'used with\s+["“]?(?P<companion>[\wÀ-ɏ]+)', re.IGNORECASE)



def extract(sense: Mapping[str, Any]) -> tuple[SpecialistFeature, ...]:
    """Return typed features for one SpanishDict sense."""

    features: list[SpecialistFeature] = []
    context = sense.get("context")
    if isinstance(context, str) and context.strip():
        match = COMPANION.search(context)
        if match:
            companion = match.group("companion").lower()
            if companion in GRAMMATICAL_FORMS:
                features.append(
                    SpecialistFeature("construction", "companion_form", context.strip(), context.strip())
                )
            else:
                features.append(
                    SpecialistFeature("companion", "required_word", companion, companion)
                )
        else:
            features.append(
                SpecialistFeature("domain", "context", context.strip(), context.strip())
            )

    for region in sense.get("regions", []) or []:
        if isinstance(region, str) and region.strip():
            features.append(
                SpecialistFeature("register", "region", region.strip(), region.strip())
            )
    return tuple(features)
