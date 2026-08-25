"""Loading a POS model at a pinned revision, and tagging a target span with it.

Both modes already declared the same pin -- ``es_dep_news_trf@3.8.0`` -- but only
speech enforced it. Lyrics used its constant solely to write ``occurrence_pos``
into the run manifest, while calling ``spacy.load("es_dep_news_trf")`` with no
version check, so the artifact asserted a revision it never verified. A
provenance field that can be wrong is worse than an absent one, because nothing
downstream has reason to doubt it.
"""

from __future__ import annotations

from typing import Any


class PinnedModelError(RuntimeError):
    """Raised when the installed model is not the revision a run claims."""


def parse_pin(pin: str) -> tuple[str, str]:
    """Split ``name@version`` into its parts."""

    name, separator, version = pin.partition("@")
    if not separator or not name.strip() or not version.strip():
        raise PinnedModelError(f"model pin must be 'name@version', got {pin!r}")
    return name.strip(), version.strip()


def load_pinned(pin: str, *, model: Any | None = None) -> Any:
    """Return the spaCy model for ``pin``, refusing a different revision.

    Failing loudly is the point. The alternative is a run that silently produces
    different tags from the same inputs, which the immutable-artifact contract
    everywhere else in this pipeline is specifically designed to prevent.

    Only a model this function loads is verified. An explicitly injected one is
    the caller's responsibility -- it is how tests supply a double, and how a
    caller that has already loaded and checked a model avoids doing it twice.
    """

    name, version = parse_pin(pin)
    if model is not None:
        return model

    import spacy

    model = spacy.load(name)
    actual = str((getattr(model, "meta", None) or {}).get("version") or "")
    if actual != version:
        raise PinnedModelError(
            f"installed {name} is version {actual or 'unknown'}, but this run "
            f"claims {pin}. Install the pinned revision, or change the pin "
            f"deliberately -- do not record a version that was not used."
        )
    return model


def canonicalize_target(
    text: str,
    span: tuple[int, int] | None,
    *,
    display_form: str,
    observed_form: str | None = None,
) -> tuple[str, tuple[int, int] | None, bool]:
    """Rewrite the target to its canonical form before tagging.

    A sentence-initial capital or a mid-sentence uppercase makes the tagger read
    the token as a proper noun. Substituting the card's display form keeps the
    surrounding context intact while removing that artefact. Returns the text to
    tag, the adjusted span, and whether a substitution happened.
    """

    if span is None:
        return text, None, False
    start, end = span
    if not (0 <= start < end <= len(text)):
        raise ValueError("target span falls outside the POS context")
    observed = text[start:end]
    expected = observed_form or display_form
    if observed != expected:
        raise ValueError("target span does not reproduce the persisted observed form")
    if observed.casefold() == display_form.casefold() and observed != display_form:
        return (
            text[:start] + display_form + text[end:],
            (start, start + len(display_form)),
            True,
        )
    return text, (start, end), False


def tag_of_span(document: Any, start: int, end: int) -> str | None:
    """Return the POS of the first token overlapping ``[start, end)``."""

    for token in document:
        if token.idx < end and token.idx + len(token.text) > start:
            return token.pos_
    return None
