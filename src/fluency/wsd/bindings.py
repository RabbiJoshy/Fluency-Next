"""What a language brings to a WSD run: an adapter, a POS model, a POS gate.

The speech executor previously named Spanish in ten places -- the surface
adapter, the pinned tagger, the candidate policy's POS filter, and the language
written into the bundle. Running any other language meant editing all of them
together and getting every one right.

The POS gate is deliberately keyed on the DICTIONARY rather than the language.
SpanishDict and Wiktionary disagree about categories in ways that silently
delete correct senses, and French reads Wiktionary too, so the fix belongs with
the provider that needs it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True, slots=True)
class LanguageBinding:
    language: str
    adapter_factory: Callable[[], Any]
    # None means this language HAS no POS model, stated rather than approximated.
    # spaCy publishes no Czech pipeline, and a POS gate is only ever subtractive:
    # it removes senses the observed tag rules out, while the embedding does the
    # choosing. An uncalibrated gate is therefore not neutral but destructive --
    # unbridged filtering deleted every sense on 34% of real Portuguese
    # occurrences. Declaring the absence runs Czech with no gate at all, which
    # can only widen the candidate set, never silently empty it.
    pos_model_role: str | None
    menu_provider: str


_BINDINGS: dict[str, LanguageBinding] = {}


class LanguageBindingError(ValueError):
    """Raised when a language has no WSD binding."""


def _spanish() -> Any:
    from fluency.wsd.languages.spanish import SpanishWSDAdapter

    return SpanishWSDAdapter()


def _portuguese() -> Any:
    from fluency.wsd.languages.portuguese import PortugueseWSDAdapter

    return PortugueseWSDAdapter()


def _czech() -> Any:
    from fluency.wsd.languages.czech import CzechWSDAdapter

    return CzechWSDAdapter()


def _french() -> Any:
    from fluency.wsd.languages.french import FrenchWSDAdapter

    return FrenchWSDAdapter()


_BINDINGS["es"] = LanguageBinding("es", _spanish, "occurrence-pos", "spanishdict")
_BINDINGS["pt"] = LanguageBinding("pt", _portuguese, "occurrence-pos-pt", "wiktionary")
_BINDINGS["fr"] = LanguageBinding("fr", _french, "occurrence-pos-fr", "wiktionary")
_BINDINGS["cs"] = LanguageBinding("cs", _czech, None, "wiktionary")


def binding_for(language: str) -> LanguageBinding:
    found = _BINDINGS.get(language)
    if found is None:
        raise LanguageBindingError(
            f"no WSD binding for {language!r}; available: {', '.join(sorted(_BINDINGS))}"
        )
    return found


def pos_gate_for(language: str) -> tuple[Callable[[str, str], bool], Callable[[str], bool]]:
    """Return (sense_compatible, is_orthogonal) for a language's menu provider.

    SpanishDict keeps its own gate unchanged; every Wiktionary-backed language
    gets the bridge that absorbs `contraction` and the absent `aux`.
    """

    binding = binding_for(language)
    if binding.pos_model_role is None:
        # No tagger, so nothing is observed to filter on. Admit every sense and
        # let the embedding decide; measured on Czech, 78% of the cards needing
        # disambiguation carry senses of a single part of speech, where a gate
        # could not have discriminated anyway.
        return (lambda sense_pos, observed_pos: True, lambda sense_pos: False)

    provider = binding.menu_provider
    if provider == "spanishdict":
        from fluency.wsd.languages.spanish import ORTHOGONAL_POS, sense_compatible_bridged

        return (
            sense_compatible_bridged,
            lambda value: str(value or "").upper() in ORTHOGONAL_POS,
        )

    from fluency.wsd.pos_bridge import compatible, is_orthogonal

    return (
        lambda sense_pos, observed_pos: compatible(provider, observed_pos, sense_pos),
        lambda sense_pos: is_orthogonal(provider, sense_pos),
    )
