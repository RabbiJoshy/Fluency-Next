"""Cognate transparency between a deck language and a language the learner
already reads.

The question this answers is not "are these two words historically related" but
"will a speaker of the known language recognise this deck word for free". Those
differ: ``čerstvý``/``czerstwy`` share an ancestor and mean opposite things, and
``central``/``central`` are transparent on the page while being pronounced quite
differently. So a pair is scored on two axes and combined into one number the
learner sets a cutoff on.

    form     how alike the two written forms are
    meaning  how much of their live meaning they share

Both are computed from English glosses, which every Wiktionary extract carries
for every language. That is what keeps this provider-agnostic: the deck language
and the known language never need a bilingual dictionary between them, only a
shared pivot they both already point at.

Two design notes worth keeping.

*The meaning axis is not a tie-breaker, it is the safety property.* Form
similarity alone hides false friends. Requiring shared meaning is what keeps
``sklep`` (cellar / shop) out, because sharing no gloss is precisely what makes
a false friend false. It is imperfect — see ``DEAD_SENSE_TAGS`` — but it is the
mechanism, not a filter bolted on afterwards.

*Dead senses must be excluded before the meaning axis is computed.* Polish
``chyba`` is a particle meaning "probably"; its noun sense "error, mistake" is
tagged obsolete. Pooling that with the live senses matches Czech ``chyba``
(mistake) at full confidence and hides a word the learner will meet constantly
and misread. Wiktionary already tags these, so honouring the tags removes the
need for a curated false-friend list per pair.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


COGNATE_SCORE_SCHEMA = "cognate-score/v1"

# Senses Wiktionary marks as no longer current. A learner will not meet these,
# so letting them satisfy the meaning axis manufactures agreement that does not
# exist in the language as spoken.
DEAD_SENSE_TAGS = frozenset(
    {
        "obsolete",
        "archaic",
        "dated",
        "historical",
        "rare",
        "poetic",
        "dialectal",
        "Middle",
        "Old",
        "proscribed",
        "nonstandard",
        "form-of",
    }
)

# Parts of speech that cannot be transparent vocabulary: names carry no meaning
# to share, and affixes are not words a learner studies.
EXCLUDED_PARTS_OF_SPEECH = frozenset(
    {"name", "prefix", "suffix", "infix", "affix", "character", "punct", "phrase", "prov"}
)

# Gloss words too common to identify a sense. A shared "person" means nothing;
# a shared "hedgehog" means a great deal.
GLOSS_STOP_WORDS = frozenset(
    {
        "a", "an", "the", "of", "to", "in", "on", "for", "with", "by", "or", "and",
        "that", "this", "one", "who", "which", "something", "someone", "being",
        "be", "is", "as", "at", "from", "used", "especially", "also", "form",
        "sense", "synonym", "obsolete", "archaic", "see", "not", "it", "its",
        "his", "her", "their", "any", "some", "other", "such", "more", "most",
    }
)

_PARENTHETICAL = re.compile(r"\([^)]*\)")
_NON_GLOSS = re.compile(r"[^a-z' ]+")


class CognatePolicyError(ValueError):
    """A pair policy is absent or does not describe the pair it was asked for."""


@dataclass(frozen=True, slots=True)
class CognatePolicy:
    """Everything pair-specific, so the engine itself stays pair-agnostic.

    ``target_skeleton`` and ``known_skeleton`` are ordered rewrite rules that
    map both languages onto a shared alphabet before the forms are compared.
    They exist because orthography hides regular correspondences: Czech ``h``
    answers Polish ``g``, Czech ``ě`` answers Polish ``ie``. Without them
    ``hlavní``/``główny`` scores 0.17 and with them 0.83. Order matters —
    digraphs must rewrite before their component letters.
    """

    target_language: str
    known_language: str
    target_skeleton: tuple[tuple[str, str], ...] = ()
    known_skeleton: tuple[tuple[str, str], ...] = ()
    minimum_length: int = 4
    length_guard: float = 0.70
    gloss_maximum_words: int = 6
    # How far past the most informative gloss word the candidate search may
    # widen. The rarest token is always spent in full; this bounds what the
    # remaining tokens may add, so cost is capped without deciding in advance
    # that a common word carries no signal.
    candidate_budget: int = 400
    meaning_floor: float = 0.75
    meaning_weight: float = 0.25
    # The "auto" cutoff for this pair: at or above it, a learner who reads the
    # known language already has the word and it moves to Extras. One number
    # per pair rather than one shared slider, because each known language
    # decides alone — these scores are never compared with one another.
    default_threshold: float = 0.70
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.target_language or not self.known_language:
            raise CognatePolicyError("a cognate policy names both languages")
        if self.target_language == self.known_language:
            raise CognatePolicyError("a cognate policy needs two different languages")
        if not 0.0 <= self.default_threshold <= 1.0:
            raise CognatePolicyError("default_threshold is a score between 0 and 1")
        if not 0.0 <= self.length_guard <= 1.0:
            raise CognatePolicyError("length_guard is a ratio between 0 and 1")
        if abs(self.meaning_floor + self.meaning_weight - 1.0) > 1e-9:
            raise CognatePolicyError(
                "meaning_floor + meaning_weight must be 1.0 so a perfect pair scores 1.0"
            )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CognatePolicy":
        def rules(key: str) -> tuple[tuple[str, str], ...]:
            raw = value.get(key) or []
            if not isinstance(raw, list):
                raise CognatePolicyError(f"{key} must be an ordered list of pairs")
            out: list[tuple[str, str]] = []
            for rule in raw:
                if not isinstance(rule, (list, tuple)) or len(rule) != 2:
                    raise CognatePolicyError(f"{key} entries are [from, to] pairs")
                out.append((str(rule[0]), str(rule[1])))
            return tuple(out)

        known = dict(value)
        return cls(
            target_language=str(known.get("target_language", "")),
            known_language=str(known.get("known_language", "")),
            target_skeleton=rules("target_skeleton"),
            known_skeleton=rules("known_skeleton"),
            minimum_length=int(known.get("minimum_length", 4)),
            length_guard=float(known.get("length_guard", 0.70)),
            gloss_maximum_words=int(known.get("gloss_maximum_words", 6)),
            candidate_budget=int(known.get("candidate_budget", 400)),
            meaning_floor=float(known.get("meaning_floor", 0.75)),
            meaning_weight=float(known.get("meaning_weight", 0.25)),
            default_threshold=float(known.get("default_threshold", 0.70)),
            notes=str(known.get("notes", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_language": self.target_language,
            "known_language": self.known_language,
            "target_skeleton": [list(rule) for rule in self.target_skeleton],
            "known_skeleton": [list(rule) for rule in self.known_skeleton],
            "minimum_length": self.minimum_length,
            "length_guard": self.length_guard,
            "gloss_maximum_words": self.gloss_maximum_words,
            "candidate_budget": self.candidate_budget,
            "meaning_floor": self.meaning_floor,
            "meaning_weight": self.meaning_weight,
            "default_threshold": self.default_threshold,
            "notes": self.notes,
        }


def policy_path(config_root: Path, target_language: str, known_language: str) -> Path:
    return Path(config_root) / "cognates" / f"{target_language}-{known_language}.json"


def load_policy(config_root: Path, target_language: str, known_language: str) -> CognatePolicy:
    """Load one pair's policy. A missing file is a refusal, not a default.

    Invariant 2: absence is declared, never inferred. Scoring a pair with no
    policy would silently apply Czech-Polish orthography to, say, Greek.
    """

    path = policy_path(config_root, target_language, known_language)
    if not path.is_file():
        raise CognatePolicyError(
            f"no cognate policy for {target_language}->{known_language}: expected {path}"
        )
    policy = CognatePolicy.from_dict(json.loads(path.read_text(encoding="utf-8")))
    if policy.target_language != target_language or policy.known_language != known_language:
        raise CognatePolicyError(f"{path} declares a different language pair")
    return policy


def available_known_languages(config_root: Path, target_language: str) -> tuple[str, ...]:
    """Which known languages this deck language has a policy for.

    Discovered by listing files, so a pair is added by creating one.
    """

    directory = Path(config_root) / "cognates"
    if not directory.is_dir():
        return ()
    found = []
    for path in sorted(directory.glob(f"{target_language}-*.json")):
        known = path.stem.split("-", 1)[1]
        if known:
            found.append(known)
    return tuple(found)


# ---------------------------------------------------------------- normalising


def strip_accents(word: str) -> str:
    decomposed = unicodedata.normalize("NFD", (word or "").lower())
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def skeleton(word: str, rules: Sequence[tuple[str, str]]) -> str:
    """Rewrite a word onto the pair's shared alphabet, then strip accents."""

    out = (word or "").lower()
    for source, target in rules:
        out = out.replace(source, target)
    return strip_accents(out)


def normalise_gloss(gloss: str) -> str:
    text = _NON_GLOSS.sub(" ", _PARENTHETICAL.sub(" ", (gloss or "").lower()))
    text = " ".join(text.split())
    for prefix in ("to ", "the ", "a ", "an "):
        if text.startswith(prefix):
            return text[len(prefix):]
    return text


def gloss_tokens(glosses: Iterable[str]) -> frozenset[str]:
    tokens: set[str] = set()
    for gloss in glosses:
        for token in gloss.split():
            if token not in GLOSS_STOP_WORDS and len(token) > 2:
                tokens.add(token)
    return frozenset(tokens)


def live_glosses(entry: Mapping[str, Any], maximum_words: int) -> frozenset[str]:
    """Short English glosses from senses that are still current.

    A gloss longer than ``maximum_words`` is a definition rather than a
    translation, and matching on definitions produces agreement between any two
    words that happen to be explained with the same words.
    """

    out: set[str] = set()
    for sense in entry.get("senses") or []:
        if not isinstance(sense, Mapping):
            continue
        if DEAD_SENSE_TAGS & {str(tag) for tag in (sense.get("tags") or [])}:
            continue
        for gloss in sense.get("glosses") or []:
            text = normalise_gloss(str(gloss))
            if text and len(text.split()) <= maximum_words:
                out.add(text)
    return frozenset(out)


# -------------------------------------------------------------------- scoring


def edit_distance(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left or not right:
        return max(len(left), len(right))
    previous = list(range(len(right) + 1))
    for i, a in enumerate(left, 1):
        current = [i]
        for j, b in enumerate(right, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (a != b)))
        previous = current
    return previous[-1]


def similarity(left: str, right: str) -> float:
    """Normalised Levenshtein.

    Normalising by the longer string is what makes a short word matching a long
    one score badly, which plain ratio metrics do not: ``stan`` against
    ``státní`` looks like agreement to a subsequence matcher and does not to
    this.
    """

    if not left or not right:
        return 0.0
    return 1.0 - edit_distance(left, right) / max(len(left), len(right))


def form_score(target_word: str, known_word: str, policy: CognatePolicy) -> float:
    """Best of raw spelling and the pair's shared skeleton."""

    raw = similarity(strip_accents(target_word), strip_accents(known_word))
    mapped = similarity(
        skeleton(target_word, policy.target_skeleton),
        skeleton(known_word, policy.known_skeleton),
    )
    return max(raw, mapped)


def meaning_score(target_tokens: frozenset[str], known_tokens: frozenset[str]) -> float:
    """Overlap of the two words' live meaning, against the smaller sense set.

    The ``+ 0.5`` damping keeps a single shared token from reading as total
    agreement when one side has one gloss and the other has twenty.
    """

    if not target_tokens or not known_tokens:
        return 0.0
    shared = len(target_tokens & known_tokens)
    if shared == 0:
        return 0.0
    return shared / (min(len(target_tokens), len(known_tokens)) + 0.5)


def passes_length_guard(target_word: str, known_word: str, policy: CognatePolicy) -> bool:
    left, right = strip_accents(target_word), strip_accents(known_word)
    if not left or not right:
        return False
    return min(len(left), len(right)) / max(len(left), len(right)) >= policy.length_guard


@dataclass(frozen=True, slots=True)
class CognateMatch:
    known_word: str
    form: float
    meaning: float
    score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "known_word": self.known_word,
            "form": round(self.form, 3),
            "meaning": round(self.meaning, 3),
            "score": round(self.score, 3),
        }


def combine(form: float, meaning: float, policy: CognatePolicy) -> float:
    """One number, form-led.

    Form drives it because transparency is a property of what the learner sees;
    meaning discounts it rather than gating it, so a look-alike with no shared
    sense sinks in the ranking instead of being silently kept or silently
    dropped.
    """

    return form * (policy.meaning_floor + policy.meaning_weight * meaning)


@dataclass
class KnownLanguageIndex:
    """Known-language words reachable by the English glosses they share."""

    policy: CognatePolicy
    words: dict[str, frozenset[str]] = field(default_factory=dict)
    by_token: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))

    def candidates(self, target_glosses: frozenset[str]) -> set[str]:
        """Known words sharing a gloss word with the target, rarest word first.

        Matching whole glosses only is too strict — one dictionary writes "to
        write", the other "write in ink". Matching on every token is too loose,
        and scanning the bucket for a word like "way" costs more than it says.

        Discarding common tokens outright was the first attempt and it silently
        lost real cognates: Czech ``způsob`` and Polish ``sposób`` share only
        "way", so capping by document frequency made the pair unreachable at
        any threshold. Instead the tokens are spent rarest-first and stop at a
        budget, so a discriminating word is always preferred but a common one
        is still used when it is all the pair has.
        """

        ranked = sorted(
            gloss_tokens(target_glosses),
            key=lambda token: len(self.by_token.get(token, ())),
        )
        found: set[str] = set()
        for position, token in enumerate(ranked):
            bucket = self.by_token.get(token)
            if not bucket:
                continue
            # The rarest token is the best evidence the pair has, so it is
            # always spent in full even when its bucket is large — that is the
            # case a frequency cap used to lose. Every later token is optional
            # and only widens the search while the budget allows.
            if position > 0 and len(found) + len(bucket) > self.policy.candidate_budget:
                break
            found.update(bucket)
        return found


def build_known_index(
    entries: Iterable[Mapping[str, Any]], policy: CognatePolicy
) -> KnownLanguageIndex:
    index = KnownLanguageIndex(policy=policy)
    for entry in entries:
        if str(entry.get("pos") or "") in EXCLUDED_PARTS_OF_SPEECH:
            continue
        word = str(entry.get("word") or "").lower()
        if not word or "-" in word or " " in word:
            continue
        glosses = live_glosses(entry, policy.gloss_maximum_words)
        if not glosses:
            continue
        index.words[word] = index.words.get(word, frozenset()) | glosses
    for word, glosses in index.words.items():
        for token in gloss_tokens(glosses):
            index.by_token[token].append(word)
    return index


def best_match(
    target_word: str,
    target_glosses: frozenset[str],
    index: KnownLanguageIndex,
) -> CognateMatch | None:
    """The known-language word that makes this deck word most recognisable."""

    policy = index.policy
    if len(strip_accents(target_word)) < policy.minimum_length:
        return None
    target_tokens = gloss_tokens(target_glosses)
    if not target_tokens:
        return None
    best: CognateMatch | None = None
    for known_word in index.candidates(target_glosses):
        if not passes_length_guard(target_word, known_word, policy):
            continue
        form = form_score(target_word, known_word, policy)
        meaning = meaning_score(target_tokens, gloss_tokens(index.words[known_word]))
        if meaning <= 0.0:
            continue
        score = combine(form, meaning, policy)
        if score <= 0.0:
            continue
        if best is None or score > best.score:
            best = CognateMatch(known_word=known_word, form=form, meaning=meaning, score=score)
    return best


def score_deck(
    deck_entries: Mapping[str, frozenset[str]],
    index: KnownLanguageIndex,
) -> dict[str, CognateMatch]:
    """Score every deck word that finds a counterpart. Words that find none are
    simply absent from the result — never present with a zero, which would be a
    claim that they were checked and found unrelated when they were not
    reachable at all.
    """

    scored: dict[str, CognateMatch] = {}
    for word, glosses in deck_entries.items():
        match = best_match(word, glosses, index)
        if match is not None:
            scored[word] = match
    return scored
