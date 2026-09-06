"""High-precision leaf correction from an already supplied English translation.

The corrector never translates. It asks a local word aligner which English word
corresponds to the marked source token, then accepts a menu leaf only when a
literal English cue belongs to that exact leaf and no sibling leaf.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
import re
from typing import Mapping, Protocol, Sequence

from fluency.nlp.models import model as declared_model
from fluency.wsd.menus import MenuAnalysis


TOKEN_RE = re.compile(r"[^\W_]+(?:'[^\W_]+)?", re.UNICODE)
PAREN_RE = re.compile(r"\([^)]*\)")
WEAK_SINGLE_TOKENS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "been", "but", "by",
    "can", "could", "did", "do", "does", "for", "from", "had", "has",
    "have", "he", "her", "him", "his", "i", "if", "in", "is", "it",
    "its", "may", "me", "might", "more", "my", "no", "not", "of", "on",
    "one", "or", "our", "out", "she", "should", "so", "some", "than",
    "that", "the", "their", "them", "there", "these", "they", "this",
    "those", "to", "up", "us", "very", "was", "we", "were", "what",
    "when", "where", "which", "who", "will", "with", "would", "you", "your",
})
LEADING_GLOSS_WORDS = frozenset(
    {"a", "an", "the", "to", "someone", "somebody", "something", "one"}
)
IRREGULAR_FORMS = {
    "be": ("am", "are", "is", "was", "were", "been", "being"),
    "begin": ("began", "begun", "beginning"),
    "break": ("broke", "broken", "breaking"),
    "bring": ("brought", "bringing"), "build": ("built", "building"),
    "buy": ("bought", "buying"), "catch": ("caught", "catching"),
    "choose": ("chose", "chosen", "choosing"), "come": ("came", "coming"),
    "do": ("did", "done", "doing", "does"), "draw": ("drew", "drawn", "drawing"),
    "drink": ("drank", "drunk", "drinking"), "drive": ("drove", "driven", "driving"),
    "eat": ("ate", "eaten", "eating"), "fall": ("fell", "fallen", "falling"),
    "feel": ("felt", "feeling"), "find": ("found", "finding"),
    "fly": ("flew", "flown", "flying"), "forget": ("forgot", "forgotten", "forgetting"),
    "get": ("got", "gotten", "getting", "gets"), "give": ("gave", "given", "giving"),
    "go": ("went", "gone", "going", "goes"), "grow": ("grew", "grown", "growing"),
    "have": ("had", "has", "having"), "hear": ("heard", "hearing"),
    "hold": ("held", "holding"), "keep": ("kept", "keeping"),
    "know": ("knew", "known", "knowing"), "lead": ("led", "leading"),
    "leave": ("left", "leaving"), "lose": ("lost", "losing"),
    "make": ("made", "making"), "mean": ("meant", "meaning"),
    "meet": ("met", "meeting"), "pay": ("paid", "paying"),
    "put": ("put", "putting"), "read": ("read", "reading"),
    "ride": ("rode", "ridden", "riding"), "run": ("ran", "running"),
    "say": ("said", "saying", "says"), "see": ("saw", "seen", "seeing"),
    "sell": ("sold", "selling"), "send": ("sent", "sending"),
    "show": ("showed", "shown", "showing"), "sit": ("sat", "sitting"),
    "speak": ("spoke", "spoken", "speaking"), "stand": ("stood", "standing"),
    "take": ("took", "taken", "taking"), "teach": ("taught", "teaching"),
    "tell": ("told", "telling"), "think": ("thought", "thinking"),
    "throw": ("threw", "thrown", "throwing"),
    "understand": ("understood", "understanding"),
    "wear": ("wore", "worn", "wearing"), "win": ("won", "winning"),
    "write": ("wrote", "written", "writing"),
}


@dataclass(frozen=True, slots=True)
class AlignmentCorrection:
    menu_analysis_id: str
    sense_id: str
    aligned_target: str
    aligned_translation: str
    cue: str | None = None
    method: str = "inter"
    alignment_pairs: tuple[tuple[int, int], ...] = ()


class AlignmentCorrector(Protocol):
    model_revision: str

    def correct(
        self,
        *,
        sentence: str,
        translation: str,
        surface_form: str,
        analyses: tuple[MenuAnalysis, ...],
        current_analysis_id: str,
        current_sense_id: str,
        target_span: tuple[int, int] | None = None,
    ) -> AlignmentCorrection | None: ...


class WordAligner(Protocol):
    model_revision: str

    def align(
        self, source_tokens: Sequence[str], translation_tokens: Sequence[str]
    ) -> Mapping[str, Sequence[tuple[int, int]]]: ...


def _tokens(text: str) -> tuple[str, ...]:
    return tuple(match.group(0).casefold() for match in TOKEN_RE.finditer(text or ""))


def _token_spans(text: str) -> tuple[tuple[str, int, int], ...]:
    return tuple(
        (match.group(0).casefold(), match.start(), match.end())
        for match in TOKEN_RE.finditer(text or "")
    )


def _starts(sequence: Sequence[str], phrase: Sequence[str]) -> list[int]:
    if not phrase:
        return []
    return [
        index for index in range(len(sequence) - len(phrase) + 1)
        if tuple(sequence[index:index + len(phrase)]) == tuple(phrase)
    ]


def _regular_variants(word: str) -> set[str]:
    variants = {word, *IRREGULAR_FORMS.get(word, ())}
    if len(word) < 3:
        return variants
    if word.endswith("y") and len(word) > 3 and word[-2] not in "aeiou":
        variants.update({word[:-1] + "ies", word[:-1] + "ied", word[:-1] + "ying"})
    elif word.endswith("e"):
        variants.update({word + "s", word + "d", word[:-1] + "ing"})
    else:
        variants.update({word + "s", word + "ed", word + "ing"})
        if word.endswith(("s", "sh", "ch", "x", "z", "o")):
            variants.add(word + "es")
    return variants


def literal_cues(gloss: str) -> set[tuple[str, ...]]:
    cues: set[tuple[str, ...]] = set()
    text = PAREN_RE.sub(" ", gloss or "")
    for part in re.split(r"\s*(?:;|/|,(?=\s))\s*", text):
        tokens = list(_tokens(part))
        while len(tokens) > 1 and tokens[0] in LEADING_GLOSS_WORDS:
            tokens.pop(0)
        if not tokens:
            continue
        if len(tokens) == 1:
            if tokens[0] in WEAK_SINGLE_TOKENS or len(tokens[0]) < 2:
                continue
            cues.update((variant,) for variant in _regular_variants(tokens[0]))
        else:
            cues.add(tuple(tokens))
    return cues


class LiteralGlossAlignmentCorrector:
    """Correct only when alignment and a unique literal leaf cue intersect."""

    method_id = "literal-gloss-alignment/v1"

    def __init__(self, word_aligner: WordAligner, *, method: str = "inter") -> None:
        self.word_aligner = word_aligner
        self.method = method
        self.model_revision = f"{self.method_id}+{word_aligner.model_revision}"

    def correct(
        self,
        *,
        sentence: str,
        translation: str,
        surface_form: str,
        analyses: tuple[MenuAnalysis, ...],
        current_analysis_id: str,
        current_sense_id: str,
        target_span: tuple[int, int] | None = None,
    ) -> AlignmentCorrection | None:
        del current_analysis_id, current_sense_id
        if not translation.strip():
            return None
        source_spans = _token_spans(sentence)
        source_tokens = tuple(item[0] for item in source_spans)
        translation_tokens = _tokens(translation)
        if not source_tokens or not translation_tokens:
            return None
        if target_span is not None:
            start, end = target_span
            target_indices = {
                index for index, (_token, left, right) in enumerate(source_spans)
                if left < end and right > start
            }
        else:
            surface_tokens = _tokens(surface_form)
            starts = _starts(source_tokens, surface_tokens)
            if len(starts) != 1:
                return None
            target_indices = set(range(starts[0], starts[0] + len(surface_tokens)))
        if not target_indices:
            return None

        owners: dict[tuple[str, ...], set[tuple[str, str]]] = defaultdict(set)
        for analysis in analyses:
            for leaf in analysis.senses:
                for cue in literal_cues(leaf.translation):
                    owners[cue].add((analysis.menu_analysis_id, leaf.sense_id))
        unique = {cue: next(iter(refs)) for cue, refs in owners.items() if len(refs) == 1}
        cue_hits: list[tuple[tuple[str, str], tuple[str, ...], set[int]]] = []
        for cue, ref in unique.items():
            for start in _starts(translation_tokens, cue):
                cue_hits.append((ref, cue, set(range(start, start + len(cue)))))
        if not cue_hits:
            return None

        methods = self.word_aligner.align(source_tokens, translation_tokens)
        pairs = tuple((int(left), int(right)) for left, right in methods.get(self.method, ()))
        linked = {right for left, right in pairs if left in target_indices}
        matched = [item for item in cue_hits if linked.intersection(item[2])]
        refs = {item[0] for item in matched}
        if len(refs) != 1:
            return None
        menu_analysis_id, sense_id = next(iter(refs))
        cues = sorted({" ".join(item[1]) for item in matched})
        aligned_translation = " ".join(
            translation_tokens[index] for index in sorted(linked) if index < len(translation_tokens)
        )
        return AlignmentCorrection(
            menu_analysis_id=menu_analysis_id,
            sense_id=sense_id,
            aligned_target=" ".join(source_tokens[index] for index in sorted(target_indices)),
            aligned_translation=aligned_translation,
            cue=cues[0] if cues else None,
            method=self.method,
            alignment_pairs=pairs,
        )


class SimAlignWordAligner:
    """Lazy, local-only SimAlign adapter pinned through the NLP registry."""

    def __init__(self, *, model_path: Path | None = None, device: str = "cpu") -> None:
        declaration = declared_model("word-alignment")
        self.name = str(declaration["name"])
        self.revision = str(declaration["revision"])
        self.model_path = model_path
        self.device = device
        self.model_revision = (
            f"simalign@{version('simalign')}|{self.name}@{self.revision}|"
            "bpe-layer8-inter"
        )
        self._aligner = None

    def _load(self):
        if self._aligner is None:
            from huggingface_hub import snapshot_download
            from simalign import SentenceAligner

            path = self.model_path or Path(snapshot_download(
                repo_id=self.name,
                revision=self.revision,
                local_files_only=True,
            ))
            self._aligner = SentenceAligner(
                model=str(path), token_type="bpe", matching_methods="a",
                device=self.device, layer=8,
            )
        return self._aligner

    def align(
        self, source_tokens: Sequence[str], translation_tokens: Sequence[str]
    ) -> Mapping[str, Sequence[tuple[int, int]]]:
        return self._load().get_word_aligns(list(source_tokens), list(translation_tokens))
