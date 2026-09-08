"""How many sentences a corpus line contains.

This is a selection concern, not a harvesting one: the harvest keeps every row
it matches, and choosing which of them to *show* is where a multi-sentence row
matters. Keeping it out of fluency.harvest.matching also keeps the harvest's
implementation hash stable, so adding a display rule does not invalidate
finished harvests and force a rescan of millions of subtitle lines.
"""

from __future__ import annotations

import re

_SENTENCE_BOUNDARY = re.compile(
    # A terminator, then whitespace, then something that starts a new sentence:
    # an opening quote or bracket, an inverted Spanish mark, or a capital in any
    # of the scripts the decks use. "..." is not a boundary -- it is one speaker
    # trailing off inside a single line.
    r"(?<=[.!?])\s+(?=[\"'\u00ab\u00bf\u00a1(\[]?[^\W\d_a-z\u00df-\u00ff])",
    re.UNICODE,
)


# A terminator that belongs to an abbreviation ends no sentence. Titles are what
# actually occur in subtitles ("A Sra. Silva chegou." is one sentence), along
# with initials, where the token before the stop is a single capital.
_ABBREVIATION = re.compile(
    r"(?:^|\s)(?:[Ss]r|[Ss]ra|[Ss]rta|[Dd]r|[Dd]ra|[Pp]rof|[Ee]ng|[Ss]t|[Vv]s|[Ee]tc"
    r"|[Pp]|[Pp]í|[Ii]ng|[Mm]gr|[Jj]UDr|[Cc]Sc|[Aa]td|[Nn]apr|[Tt]j|[Ss]tr"
    r"|\w)$",
    re.UNICODE,
)


def sentence_count(text: str) -> int:
    """How many sentences a corpus line actually contains.

    A subtitle row is a unit of display, not a unit of language: it often holds
    a whole exchange. "- O que esta a fazer? Nao." is two speakers, and for the
    `que` card the second half is noise the learner must read past to find the
    word being taught.
    """

    stripped = text.strip()
    if not stripped:
        return 0
    count = 1
    for match in _SENTENCE_BOUNDARY.finditer(stripped):
        before = stripped[: match.start()].rstrip(".!?")
        if _ABBREVIATION.search(before):
            continue
        count += 1
    return count


