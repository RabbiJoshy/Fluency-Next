"""Conservative Spanish surface normalization for Lyrics occurrences."""

from __future__ import annotations

import json
from pathlib import Path
import re
import unicodedata

from fluency.lyrics.languages.base import NormalizedUnit


LEADING_ELISIONS = {
    "tamos": "estamos", "tamo": "estamos", "taba": "estaba", "tabas": "estabas",
    "toy": "estoy", "tá": "está", "tás": "estás", "tan": "están", "tán": "están",
    "onde": "donde", "el": "del", "e": "de",
}
AMBIGUOUS = {
    "ve'": {"default": "ves", "override": "vez", "preceding": {"una", "otra", "cada", "tal", "última", "primera", "esta", "esa", "la", "qué", "alguna", "cualquier"}},
    "vo'": {"default": "vos", "override": "voy", "following": {"a"}},
}
TRAILING_CONSONANTS = "sdzrln"
INTERNAL_CONSONANTS = "bcdfghjklmnñpqrstvwxyz"

D_ELISION_RULES = (
    (re.compile(r"^(.+)a['’]o$"), "ado"),
    (re.compile(r"^(.+)a['’]a$"), "ada"),
    (re.compile(r"^(.+)a['’]os$"), "ados"),
    (re.compile(r"^(.+)a['’]as$"), "adas"),
    (re.compile(r"^(.+)[íi]['’]o$"), "ido"),
    (re.compile(r"^(.+)[íi]['’]a$"), "ida"),
    (re.compile(r"^(.+)[íi]['’]os$"), "idos"),
    (re.compile(r"^(.+)[íi]['’]as$"), "idas"),
)
BARE_D_RULES = (
    (re.compile(r"^(.+)ao$"), "ado"),
    (re.compile(r"^(.+)aos$"), "ados"),
    (re.compile(r"^(.+)ío$"), "ido"),
    (re.compile(r"^(.+)íos$"), "idos"),
)


def _read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


class SpanishLyricsAdapter:
    language = "es"
    method_id = "spanish-lyrics-normalizer/v2"

    def __init__(
        self,
        *,
        elision_mapping: Path,
        multi_word_elisions: Path,
        known_forms: Path,
        frequency_snapshot: Path,
        lexeme_register: Path,
    ) -> None:
        mapping = _read_json(elision_mapping)
        if not isinstance(mapping, list):
            raise ValueError("Spanish elision mapping must contain a list")
        self.explicit = {
            str(item["elided_word"]).casefold().replace("’", "'"): str(item["target_word"]).casefold()
            for item in mapping
            if isinstance(item, dict)
            and item.get("action") == "merge"
            and item.get("merge_type") in {"elision_pair", "elided_only"}
            and item.get("elided_word")
            and item.get("target_word")
        }
        multi = _read_json(multi_word_elisions)
        if not isinstance(multi, dict):
            raise ValueError("Spanish multi-word elisions must contain an object")
        entries = multi.get("entries", {})
        self.multi = {}
        for surface, expansion in entries.items() if isinstance(entries, dict) else ():
            values = expansion.split() if isinstance(expansion, str) else expansion
            if isinstance(values, list) and values:
                self.multi[str(surface).casefold().replace("’", "'")] = tuple(str(value).casefold() for value in values)
        forms = _read_json(known_forms)
        if isinstance(forms, dict):
            self.known_forms = frozenset(str(value).casefold() for value in forms)
        elif isinstance(forms, list):
            self.known_forms = frozenset(str(value).casefold() for value in forms)
        else:
            raise ValueError("Spanish known forms must contain an object or list")
        self.frequencies = {}
        for line in frequency_snapshot.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) >= 2:
                try:
                    self.frequencies[parts[0].casefold()] = int(parts[1])
                except ValueError:
                    continue
        register = _read_json(lexeme_register)
        if not isinstance(register, dict):
            raise ValueError("Spanish lexeme register must contain an object")
        self.protected_lexemes = frozenset(
            str(value).casefold()
            for card in register.values()
            if isinstance(card, dict)
            for value in (card.get("word"), card.get("lemma"))
            if isinstance(value, str) and value
        )

    def _known_unique(self, values: list[str]) -> str | None:
        hits = sorted({value for value in values if value in self.known_forms})
        return hits[0] if len(hits) == 1 else None

    def _restore_internal(self, form: str) -> str | None:
        if form.count("'") != 1 or form.endswith("'") or form.startswith("'"):
            return None
        left, right = form.split("'", 1)
        candidates = [left + consonant + right for consonant in INTERNAL_CONSONANTS]
        candidates += [left.replace("k", "c") + consonant + right for consonant in INTERNAL_CONSONANTS]
        return self._known_unique(candidates)

    def _restore_trailing(self, form: str, *, allow_protected_stem: bool = False) -> str | None:
        if not form.endswith("'") or len(form) < 3:
            return None
        stem = form[:-1]
        if stem in self.protected_lexemes and not allow_protected_stem:
            return None
        hits = sorted({stem + consonant for consonant in TRAILING_CONSONANTS if stem + consonant in self.known_forms})
        protected_hits = [hit for hit in hits if hit in self.protected_lexemes]
        if len(protected_hits) == 1:
            return protected_hits[0]
        if len(hits) == 1:
            return hits[0] if self.frequencies.get(hits[0], 0) > 0 else None
        ranked = sorted(((self.frequencies.get(hit, 0), hit) for hit in hits), reverse=True)
        if len(ranked) > 1:
            best_frequency, best = ranked[0]
            runner_up = ranked[1][0]
            if best_frequency >= 20 and best_frequency >= 4 * runner_up:
                return best
        return None

    def _restore_d(self, form: str) -> str | None:
        for pattern, suffix in D_ELISION_RULES:
            match = pattern.fullmatch(form)
            if match:
                return match.group(1) + suffix
        if form not in self.known_forms:
            for pattern, suffix in BARE_D_RULES:
                match = pattern.fullmatch(form)
                if match and match.group(1) + suffix in self.known_forms:
                    return match.group(1) + suffix
        return None

    def normalize(self, surface: str, *, previous: str | None, following: str | None) -> tuple[NormalizedUnit, ...]:
        form = unicodedata.normalize("NFC", surface).casefold().replace("’", "'")
        if form.startswith("'"):
            lookup = form[1:].rstrip("'")
            if lookup in LEADING_ELISIONS:
                return (NormalizedUnit(LEADING_ELISIONS[lookup], "normalize", "spanish_leading_aphesis"),)
        if form in self.multi:
            return tuple(NormalizedUnit(value, "split", "spanish_multi_word_elision") for value in self.multi[form])
        ambiguous = AMBIGUOUS.get(form)
        if ambiguous:
            if previous and previous.casefold() in ambiguous.get("preceding", set()):
                target = ambiguous["override"]
            elif following and following.casefold() in ambiguous.get("following", set()):
                target = ambiguous["override"]
            else:
                target = ambiguous["default"]
            return (NormalizedUnit(target, "normalize", "spanish_contextual_elision"),)
        if form in self.explicit:
            target = self.explicit[form]
            chained = self._restore_d(target)
            return (NormalizedUnit(chained or target, "normalize", "spanish_curated_elision"),)
        restored = self._restore_d(form)
        if restored:
            return (NormalizedUnit(restored, "normalize", "spanish_d_elision"),)
        internal = self._restore_internal(form)
        if internal:
            return (NormalizedUnit(internal, "normalize", "spanish_internal_elision"),)
        # A capitalized mid-line surface can be a clipped proper-name form even
        # when its lower-case stem is independently valid (for example Dio').
        # Restoration still requires dictionary and strong frequency evidence;
        # lower-case colloquial forms such as mai' remain protected.
        trailing = self._restore_trailing(
            form,
            allow_protected_stem=surface[:1].isupper(),
        )
        if trailing:
            return (NormalizedUnit(trailing, "normalize", "spanish_trailing_elision"),)
        return (NormalizedUnit(form, "preserve", "surface_preserved"),)
