"""French WSD surface location, with no morphology or clitic sense gate yet."""

from __future__ import annotations

from fluency.languages.french.surfaces import normalize_surface
from fluency.languages.french.tokenization import tokenize_french
from fluency.wsd.languages.base import TargetOccurrence


class FrenchWSDAdapter:
    language = "fr"

    def locate(
        self,
        sentence: str,
        surface_form: str,
    ) -> tuple[TargetOccurrence, ...]:
        surface_key = normalize_surface(surface_form)
        result = tokenize_french(sentence, known_surfaces={surface_key})
        return tuple(
            TargetOccurrence(
                observed_text=unit.observed_text,
                surface_key=surface_key,
                start=unit.start,
                end=unit.end,
            )
            for unit in result.units
            if unit.eligible and unit.surface_key == surface_key
        )
