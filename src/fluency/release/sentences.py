"""How many sentences a corpus line contains.

This is a selection concern, not a harvesting one: the harvest keeps every row
it matches, and choosing which of them to *show* is where a multi-sentence row
matters. Keeping it out of fluency.harvest.matching also keeps the harvest's
implementation hash stable, so adding a display rule does not invalidate
finished harvests and force a rescan of millions of subtitle lines.
"""

from __future__ import annotations

import re

_WORDS = re.compile(r"[^\W\d_]+", re.UNICODE)

_SENTENCE_BOUNDARY = re.compile(
    # A terminator, then whitespace, then something that starts a new sentence:
    # an opening quote or bracket, an inverted Spanish mark, or a capital in any
    # of the scripts the decks use. "..." is not a boundary -- it is one speaker
    # trailing off inside a single line.
    # A dash after the terminator is the commonest second-speaker marker in
    # subtitles -- "disso. - Nao, nao." -- and leaving it out let two-speaker
    # exchanges through the single-sentence rule after it had already shipped.
    r"(?<=[.!?])\s+(?=[-\u2013\u2014]?\s*[\"'\u00ab\u00bf\u00a1(\[]?[^\W\d_a-z\u00df-\u00ff])",
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




def near_duplicate(a: str, b: str, *, threshold: float = 0.8) -> bool:
    """Whether two sentences are the same example with a word swapped.

    Exact identity catches punctuation variants and nothing else. Tatoeba's
    contributors deliberately write agreement families -- "Vous etes plus
    grand/grande/grands que moi", "Ele/Ela nao esta com o bilhete" -- so a card
    asking for three examples receives one sentence three times. Measured on
    100-card audits: 43 of 100 French cards and 22 of 100 Portuguese.

    Similarity is over the token SET, so word order does not rescue a pair that
    shares its whole vocabulary, and length is respected: a short sentence
    contained in a longer one is not the same example.
    """

    at = {w for w in _WORDS.findall(a.casefold())}
    bt = {w for w in _WORDS.findall(b.casefold())}
    if not at or not bt:
        return False
    overlap = len(at & bt)
    return overlap / max(len(at), len(bt)) >= threshold


_PLACEHOLDER_NAMES = re.compile(
    r"\b(?:Tom|Mary|Mária|Marie|Maria|John|Ken|Bob|Alice|Jim)\b", re.UNICODE
)


def has_placeholder_name(text: str) -> bool:
    """Whether a sentence uses Tatoeba's stock cast.

    Tatoeba's contributors use Tom and Mary the way a maths textbook uses x and
    y, and they are 7-17% of every language's corpus -- 17.4% of Czech. They
    then arrive over-represented on cards, because a Tom sentence is short and
    built from common words, which is exactly what the easiness score rewards:
    a quarter of the Czech examples read carried one.

    A learner meeting Tom in every fourth sentence is learning a corpus habit,
    not a language, so these are preferred against. They are not rejected: for
    a rare card a Tom sentence is better than nothing.
    """

    return bool(_PLACEHOLDER_NAMES.search(text))
