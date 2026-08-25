"""Locate language-specific surface helpers by discovery, not registration.

Each language package under ``fluency.languages`` declares its own
``LANGUAGE_CODE``; this module finds the one that matches. Nothing here changes
when a language is added, which is the point: the previous if-chains were a
shared file every new language had to edit, and therefore a guaranteed conflict
between concurrent sessions working on different languages.

A language that does not supply an optional helper simply does not define it,
and the caller gets a clear error naming what is missing rather than a silent
fallback to another language's rules.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache
from importlib import import_module
import pkgutil
from types import ModuleType


class LanguageSupportError(ValueError):
    """Raised when a language, or one of its helpers, is not available."""


@lru_cache(maxsize=None)
def _packages_by_code() -> dict[str, str]:
    """Map declared language code to package name, by scanning the namespace."""

    import fluency.languages as root

    found: dict[str, str] = {}
    for info in pkgutil.iter_modules(root.__path__):
        if not info.ispkg:
            continue
        module = import_module(f"fluency.languages.{info.name}")
        code = getattr(module, "LANGUAGE_CODE", None)
        if not isinstance(code, str) or not code:
            continue
        if code in found:
            raise LanguageSupportError(
                f"two language packages declare {code!r}: "
                f"{found[code]} and {info.name}"
            )
        found[code] = info.name
    return found


def registered_languages() -> tuple[str, ...]:
    """Return every declared language code, sorted."""

    return tuple(sorted(_packages_by_code()))


def _surfaces_module(language: str) -> ModuleType:
    packages = _packages_by_code()
    package = packages.get(language)
    if package is None:
        raise LanguageSupportError(
            f"no language package declares {language!r}; "
            f"available: {', '.join(sorted(packages)) or 'none'}"
        )
    return import_module(f"fluency.languages.{package}.surfaces")


def _helper(language: str, name: str) -> Callable[[str], str]:
    module = _surfaces_module(language)
    helper = getattr(module, name, None)
    if helper is None:
        raise LanguageSupportError(
            f"{language!r} provides no {name}; add it to {module.__name__}"
        )
    return helper


def normalizer_for_language(language: str) -> Callable[[str], str]:
    """Return the language's surface normalizer, used for card identity."""

    return _helper(language, "normalize_surface")


def typography_canonicalizer_for_language(language: str) -> Callable[[str], str]:
    """Return the language's case-preserving typography canonicalizer.

    Used where a raw dictionary headword must be compared against an observed
    surface without casefolding it first.
    """

    return _helper(language, "canonicalize_typography")
