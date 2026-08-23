"""Deterministic Spanish routing policy over shared Lyrics analysis units."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import unicodedata
from typing import Any

from fluency.lyrics.overrides import RoutingOverrideRegistry


_REPEAT_RE = re.compile(r"(.)\1{2,}")
_CLITICS = ("nos", "les", "los", "las", "me", "te", "se", "lo", "la", "le")
_OBJECT_CLITICS = frozenset({"lo", "la", "le", "los", "las", "les"})
_REFLEXIVE_PERSON = {"me": "1s", "te": "2s", "nos": "1p", "os": "2p"}
_HOST_MOODS = frozenset({"imperativo", "infinitivo", "gerundio"})

_DERIVATION_RULES = (
    ("ísimos", 3, ("os", "o")), ("ísimas", 3, ("as", "a")),
    ("ísimo", 3, ("o", "")), ("ísima", 3, ("a", "")),
    ("ecito", 2, ("e", "", "o")), ("ecita", 2, ("a", "e", "")),
    ("citos", 3, ("es", "s", "", "o", "a", "e")),
    ("citas", 3, ("as", "s", "", "a", "o", "e")),
    ("cito", 3, ("", "e", "n")), ("cita", 3, ("a", "", "e")),
    ("ecitos", 2, ("es", "s", "", "o", "a", "e")),
    ("ecitas", 2, ("as", "es", "", "a", "o", "e")),
    ("itos", 3, ("os", "es", "s", "", "o", "a", "e")),
    ("itas", 3, ("as", "es", "s", "", "a", "o", "e")),
    ("ito", 3, ("o", "e", "")), ("ita", 3, ("a", "e", "")),
    ("illos", 3, ("os", "es")), ("illas", 3, ("as", "es")),
    ("illo", 3, ("o", "e", "")), ("illa", 3, ("a", "e", "")),
)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _wordlist(path: Path) -> frozenset[str]:
    return frozenset(
        parts[0].casefold()
        for line in path.read_text(encoding="utf-8").splitlines()
        if (parts := line.split())
    )


def _frequencies(path: Path) -> dict[str, int]:
    output: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) >= 2:
            try:
                output[parts[0].casefold()] = int(parts[1])
            except ValueError:
                continue
    return output


def _strip_acute(value: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFD", value)
        if character != "\u0301"
    )


def _decision(
    status: str,
    bucket: str,
    *,
    reason: str,
    consulted: tuple[str, ...],
    target: str | None = None,
    details: dict[str, Any] | None = None,
    policy_trace: list[dict[str, Any]] | None = None,
    evidence_kind: str = "direct",
) -> dict[str, Any]:
    return {
        "status": status,
        "bucket": bucket,
        "target": target,
        "reason_codes": [reason],
        "consulted_inputs": list(consulted),
        "details": details or {},
        "policy_trace": policy_trace or [],
        "evidence_kind": evidence_kind,
    }


@dataclass(frozen=True, slots=True)
class SpanishRoutingResources:
    """Parsed language resources shared safely across artist-scoped routers."""

    forms: dict[str, frozenset[str]]
    spanish_frequency: dict[str, int]
    english: frozenset[str]
    loanwords: frozenset[str]
    conjugations: dict[str, Any]
    caps: dict[str, Any]
    elision_skips: frozenset[str]

    @classmethod
    def load(
        cls,
        *,
        known_forms: Path,
        spanish_frequency: Path,
        english_frequency: Path,
        english_loanwords: Path,
        conjugation_reverse: Path,
        caps_stats: Path,
        elision_mapping: Path,
    ) -> "SpanishRoutingResources":
        raw_forms = _read_json(known_forms)
        if not isinstance(raw_forms, dict):
            raise ValueError("Spanish routing requires the POS-bearing spanish_forms object")
        loanword_value = _read_json(english_loanwords)
        conjugation_value = _read_json(conjugation_reverse)
        if not isinstance(conjugation_value, dict):
            raise ValueError("Spanish conjugation reverse index must contain an object")
        caps_value = _read_json(caps_stats)
        if not isinstance(caps_value, dict):
            raise ValueError("Spanish capitalization statistics must contain an object")
        elisions = _read_json(elision_mapping)
        return cls(
            forms={
                str(word).casefold(): frozenset(
                    part for part in str(pos).casefold().split(",") if part
                )
                for word, pos in raw_forms.items()
            },
            spanish_frequency=_frequencies(spanish_frequency),
            english=_wordlist(english_frequency),
            loanwords=frozenset(
                str(word).casefold()
                for word in (
                    loanword_value.keys()
                    if isinstance(loanword_value, dict)
                    else loanword_value
                )
            ),
            conjugations={
                str(word).casefold(): rows
                for word, rows in conjugation_value.items()
            },
            caps={str(word).casefold(): value for word, value in caps_value.items()},
            elision_skips=frozenset(
                str(item.get("word", "")).casefold()
                for item in elisions
                if isinstance(item, dict)
                and item.get("action") == "skip"
                and item.get("word")
            ),
        )


class SpanishLiveRouter:
    """Current Spanish Artist routing decisions without legacy output lookup."""

    method_id = "spanish-artist-router/v3"
    evidence_kind = "direct"

    def __init__(
        self,
        *,
        known_forms: Path | None = None,
        spanish_frequency: Path | None = None,
        english_frequency: Path | None = None,
        english_loanwords: Path | None = None,
        conjugation_reverse: Path | None = None,
        caps_stats: Path | None = None,
        elision_mapping: Path | None = None,
        routing_overrides: Path | None = None,
        artist_id: str | None = None,
        song_id: str | None = None,
        resources: SpanishRoutingResources | None = None,
    ) -> None:
        if resources is None:
            paths = {
                "known_forms": known_forms,
                "spanish_frequency": spanish_frequency,
                "english_frequency": english_frequency,
                "english_loanwords": english_loanwords,
                "conjugation_reverse": conjugation_reverse,
                "caps_stats": caps_stats,
                "elision_mapping": elision_mapping,
            }
            missing = sorted(name for name, path in paths.items() if path is None)
            if missing:
                raise ValueError("Spanish routing resources are missing: " + ", ".join(missing))
            resources = SpanishRoutingResources.load(**paths)  # type: ignore[arg-type]
        self.forms = resources.forms
        self.spanish_frequency = resources.spanish_frequency
        self.english = resources.english
        self.loanwords = resources.loanwords
        self.conjugations = resources.conjugations
        self.caps = resources.caps
        self.elision_skips = resources.elision_skips
        self.overrides = (
            RoutingOverrideRegistry(
                routing_overrides,
                language="es",
                mode="lyrics",
                artist_id=artist_id,
                song_id=song_id,
            )
            if routing_overrides is not None
            else None
        )

    def _clitic(self, form: str) -> tuple[str, str, list[dict[str, str]]] | None:
        surface_pos = self.forms.get(form, frozenset())
        if surface_pos and any(pos != "verb" for pos in surface_pos):
            return None
        for clitic in _CLITICS:
            if not form.endswith(clitic) or len(form) < len(clitic) + 2:
                continue
            host = _strip_acute(form[:-len(clitic)])
            rows = [
                row for row in self.conjugations.get(host, [])
                if isinstance(row, dict) and row.get("mood") in _HOST_MOODS and row.get("lemma")
            ]
            if not rows:
                continue
            lemmas = list(dict.fromkeys(str(row["lemma"]).casefold() for row in rows))
            parent = max(lemmas, key=lambda lemma: self.spanish_frequency.get(lemma, 0))
            reflexive = False
            if clitic == "se":
                reflexive = True
            elif clitic not in _OBJECT_CLITICS:
                imperatives = [row for row in rows if row.get("mood") == "imperativo"]
                wanted = _REFLEXIVE_PERSON.get(clitic)
                reflexive = bool(wanted and any(row.get("person") == wanted for row in imperatives))
            if reflexive and parent + "se" in self.forms:
                parent += "se"
            role = "reflexive" if reflexive else (
                "direct" if clitic in {"lo", "la", "los", "las"}
                else "indirect" if clitic in {"le", "les"}
                else "object"
            )
            return parent, clitic, [{"pronoun": clitic, "role": role}]
        return None

    def _derivation(self, form: str) -> str | None:
        known = self.forms.keys()
        for suffix, minimum, endings in _DERIVATION_RULES:
            if not form.endswith(suffix):
                continue
            stem = form[:-len(suffix)]
            if len(stem) < minimum:
                continue
            for ending in endings:
                candidates = {stem + ending, _strip_acute(stem) + ending}
                if stem.endswith("qu") and ending[:1] in "oa":
                    candidates.add(stem[:-2] + "c" + ending)
                if stem.endswith("gu") and ending[:1] in "oa":
                    candidates.add(stem[:-2] + "g" + ending)
                for candidate in sorted(candidates):
                    if candidate in known:
                        return candidate
        return None

    def route(self, form: str) -> dict[str, Any]:
        key = unicodedata.normalize("NFC", form).casefold()
        trace: list[dict[str, Any]] = []

        def evaluated(policy_id: str, matched: bool, inputs: tuple[str, ...], evidence: dict[str, Any]) -> bool:
            trace.append({"policy_id": policy_id, "outcome": "match" if matched else "pass", "inputs": list(inputs), "evidence": evidence})
            return matched

        def finish(status: str, bucket: str, reason: str, *, target: str | None = None, details: dict[str, Any] | None = None, evidence_kind: str = "direct") -> dict[str, Any]:
            consulted = tuple(dict.fromkeys(name for item in trace for name in item["inputs"]))
            return _decision(status, bucket, reason=reason, consulted=consulted, target=target, details=details, policy_trace=trace, evidence_kind=evidence_kind)

        override = self.overrides.match(key) if self.overrides is not None else None
        if evaluated(
            "human.typed_override/v1",
            override is not None,
            ("routing_overrides",) if self.overrides is not None else (),
            {
                "override_id": override.get("override_id") if override else None,
                "registry_configured": self.overrides is not None,
            },
        ):
            decision = override["decision"]
            return finish(
                decision["status"],
                decision["bucket"],
                "typed_human_override",
                target=decision.get("target"),
                details={
                    "override_id": override["override_id"],
                    "reason": override["reason"],
                    "author": override["author"],
                    "created_at": override["created_at"],
                    "scope": override["scope"],
                },
                evidence_kind="human_review",
            )

        repeated = bool(_REPEAT_RE.search(key))
        if evaluated("orthography.repeated_character_noise/v1", repeated, (), {"triple_repeat": repeated}):
            return finish("excluded", "exclude.noise", "repeated_character_noise")
        pos = self.forms.get(key)
        if evaluated("lexicon.wiktionary_name_only/v1", pos == {"name"}, ("known_forms",), {"parts_of_speech": sorted(pos or ())}):
            return finish("excluded", "exclude.proper_nouns", "wiktionary_name_only")
        # A lexical interjection is a distinct disposition only when the source
        # offers no ordinary reading. Polysemous forms such as ``arriba`` and
        # ``no`` must continue to the normal vocabulary/conjugation policies.
        interjection = pos == {"intj"}
        if evaluated(
            "lexicon.spoken_particle/v1",
            interjection,
            ("known_forms",),
            {"parts_of_speech": sorted(pos or ())},
        ):
            return finish(
                "classified",
                "classifier.spoken_particle",
                "lexical_interjection",
                details={"parts_of_speech": sorted(pos)},
            )
        cap = self.caps.get(key)
        mid_total = int(cap.get("total", 0)) - int(cap.get("firstcap", 0)) if isinstance(cap, dict) else 0
        caps_match = bool(
            isinstance(cap, dict)
            and float(cap.get("cap_rate", 0)) >= 0.65
            and mid_total >= 3
            and (not pos or "name" in pos)
        )
        cap_evidence = {
            "cap_rate": cap.get("cap_rate", 0) if isinstance(cap, dict) else None,
            "mid_sentence_count": mid_total,
            "parts_of_speech": sorted(pos or ()),
        }
        if evaluated(
            "corpus.mid_sentence_caps_candidate/v1",
            caps_match,
            ("caps_stats", "known_forms"),
            cap_evidence,
        ):
            return finish(
                "review",
                "review.proper_noun_candidate",
                "mid_sentence_caps_candidate",
                details=cap_evidence,
            )
        loanword = key in self.loanwords
        if evaluated("etymology.english_loanword/v1", loanword, ("english_loanwords",), {"english_loanword": loanword}):
            return finish("excluded", "exclude.english", "english_loanword")
        english_not_spanish = key in self.english and key not in self.spanish_frequency
        if evaluated("frequency.english_not_spanish/v1", english_not_spanish, ("english_frequency", "frequency_snapshot"), {"in_english_frequency": key in self.english, "in_spanish_frequency": key in self.spanish_frequency}):
            return finish("excluded", "exclude.english", "english_not_spanish_frequency")
        clitic = self._clitic(key)
        if evaluated("morphology.guarded_clitic/v1", clitic is not None, ("known_forms", "conjugation_reverse", "frequency_snapshot"), {"candidate": clitic[0] if clitic else None}):
            parent, pronoun, roles = clitic
            return finish("classified", "clitic_merge", "guarded_spanish_clitic", target=parent, details={"clitics": [pronoun], "roles": roles, "reflexive": parent.endswith("se")})
        derivation = self._derivation(key)
        unknown_derivation = derivation is not None and pos is None
        if evaluated("morphology.unknown_derivation/v1", unknown_derivation, ("known_forms",), {"candidate": derivation}):
            return finish("derived", "derivation_map", "productive_derivation", target=derivation)
        if derivation and pos is not None:
            shared = (pos & self.forms.get(derivation, frozenset())) - {"verb"}
            reclaim = not key.endswith(("illo", "illa", "illos", "illas")) and key not in self.spanish_frequency and key not in self.conjugations and bool(shared)
        else:
            reclaim = False
        if evaluated("morphology.known_derivation_reclaim/v1", reclaim, ("known_forms", "frequency_snapshot", "conjugation_reverse"), {"candidate": derivation}):
            return finish("derived", "derivation_map", "productive_derivation_reclaim", target=derivation)
        if evaluated("lexicon.known_spanish_form/v1", bool(pos), ("known_forms",), {"parts_of_speech": sorted(pos or ())}):
            bucket = "classifier.conjugation" if "verb" in pos else "classifier.normal_vocab"
            return finish("classified", bucket, "known_spanish_form", details={"parts_of_speech": sorted(pos)})
        elision_skip = key in self.elision_skips
        if evaluated("normalization.elision_skip/v1", elision_skip, ("elision_mapping",), {"listed": elision_skip}):
            return finish("classified", "classifier.elision", "curated_elision_skip")
        english_fallback = key in self.english
        if evaluated("frequency.english_fallback/v1", english_fallback, ("english_frequency", "known_forms"), {"in_english_frequency": english_fallback}):
            return finish("excluded", "exclude.english", "english_fallback")
        evaluated("fallback.sense_discovery/v1", True, ("known_forms", "english_frequency"), {"reason": "no_lexical_analysis"})
        return finish("review", "sense_discovery", "no_lexical_analysis")
