"""Portuguese WSD surface location.

Follows the Spanish adapter rather than the French one: locating a surface is a
scan for word characters plus the shared normalizer, and needs no tokenizer
module. French requires one because of elision (``l'eau``), which Portuguese
does not have.

Hyphenated clitics (``da-me``, ``ve-lo``) and mesoclisis (``far-me-ia``) are
deliberately NOT joined into one token here. The inventory is built from a
frequency list whose tokenizer split on hyphens, so no hyphenated card exists to
locate; scanning for the parts is what matches the cards that do exist. This
mirrors how the harvester already matches them -- hyphen is a word boundary for
`SurfaceMatcher`, so ``Da-me o livro`` yields the `da`, `me` and `livro` cards.
"""

from __future__ import annotations

import re

from fluency.languages.portuguese.surfaces import normalize_surface
from fluency.wsd.languages.base import TargetOccurrence


class PortugueseWSDAdapter:
    language = "pt"

    # Portuguese uses acute, circumflex, grave, tilde and cedilla. Accents are
    # contrastive at the surface, so they are matched, never folded away.
    _WORD = re.compile(r"[0-9A-Za-zÁÂÃÀÉÊÍÓÔÕÚÜÇáâãàéêíóôõúüç]+")

    def locate(self, sentence: str, surface_form: str) -> tuple[TargetOccurrence, ...]:
        surface_key = normalize_surface(surface_form)
        found: list[TargetOccurrence] = []
        for match in self._WORD.finditer(sentence or ""):
            observed = match.group(0)
            if normalize_surface(observed) != surface_key:
                continue
            found.append(
                TargetOccurrence(
                    observed_text=observed,
                    surface_key=surface_key,
                    start=match.start(),
                    end=match.end(),
                )
            )
        return tuple(found)
