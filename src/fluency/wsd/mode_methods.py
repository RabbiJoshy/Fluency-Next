"""Which WSD method each mode runs, declared rather than implied.

A mode's method used to be visible only as an import: speech reaching for the
v6/v7 runner, lyrics for ``spanish_v5_features``. So when speech advanced from
v6 to v7, nothing recorded that lyrics had not followed, and nothing forced the
question of whether it should.

Divergence between modes is legitimate -- song lines are not subtitle lines --
but it should be a decision someone made, not a thing that quietly happened.
Declaring it does not prevent drift; it makes drift impossible to miss.
"""

from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
from typing import Any


CONFIG_VERSION = "wsd-mode-methods/v1"
_CONFIG = Path(__file__).resolve().parents[3] / "config" / "wsd" / "modes.json"


class ModeMethodError(ValueError):
    """Raised when a mode's WSD method is undeclared or malformed."""


@lru_cache(maxsize=None)
def mode_methods() -> dict[str, dict[str, Any]]:
    try:
        document = json.loads(_CONFIG.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ModeMethodError(f"mode method declaration is missing: {_CONFIG}") from error
    except json.JSONDecodeError as error:
        raise ModeMethodError("mode method declaration is not valid JSON") from error
    if document.get("config_version") != CONFIG_VERSION:
        raise ModeMethodError("unsupported mode method declaration")
    modes = document.get("modes")
    if not isinstance(modes, dict) or not modes:
        raise ModeMethodError("at least one mode must be declared")
    return modes


def method_for_mode(mode: str) -> str:
    """Return the declared method version for a mode."""

    declared = mode_methods().get(mode)
    if not isinstance(declared, dict) or not declared.get("method"):
        raise ModeMethodError(
            f"mode {mode!r} declares no WSD method; add it to {_CONFIG.name}"
        )
    return str(declared["method"])


def diverging_modes() -> dict[str, str]:
    """Return {mode: method} whenever modes do not all run the same method.

    Empty when they agree. Intended for reports and reviews, so that a split is
    stated in the output rather than discovered later.
    """

    methods = {mode: str(spec.get("method", "")) for mode, spec in mode_methods().items()}
    return {} if len(set(methods.values())) <= 1 else methods
