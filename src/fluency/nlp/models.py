"""The models this pipeline calls, declared once rather than per module.

``gemini-embedding-001``, ``SEMANTIC_SIMILARITY`` and ``es_dep_news_trf@3.8.0``
were each written into several modules independently. Changing a provider meant
finding every copy, and a run manifest recorded whichever copy its code path
happened to read -- so two modes could disagree about what they had just used.

Model identity is configuration, like a language policy or a corpus snapshot.
"""

from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
from typing import Any


CONFIG_VERSION = "nlp-model-registry/v1"
_CONFIG = Path(__file__).resolve().parents[3] / "config" / "nlp" / "models.json"


class ModelRegistryError(ValueError):
    """Raised when a model is undeclared or its declaration is malformed."""


@lru_cache(maxsize=None)
def _registry() -> dict[str, dict[str, Any]]:
    try:
        document = json.loads(_CONFIG.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ModelRegistryError(f"model registry is missing: {_CONFIG}") from error
    except json.JSONDecodeError as error:
        raise ModelRegistryError("model registry is not valid JSON") from error
    if document.get("config_version") != CONFIG_VERSION:
        raise ModelRegistryError("unsupported model registry version")
    models = document.get("models")
    if not isinstance(models, dict) or not models:
        raise ModelRegistryError("the registry declares no models")
    return models


def model(role: str) -> dict[str, Any]:
    """Return the declaration for a role such as ``exact-text-embedding``."""

    declared = _registry().get(role)
    if not isinstance(declared, dict):
        raise ModelRegistryError(
            f"no model is declared for {role!r}; available: "
            f"{', '.join(sorted(_registry()))}"
        )
    return declared


def pin(role: str) -> str:
    """Return ``name@revision`` for a role that declares a revision."""

    declared = model(role)
    name, revision = declared.get("name"), declared.get("revision")
    if not name or not revision:
        raise ModelRegistryError(f"{role!r} declares no pinned revision")
    return f"{name}@{revision}"


def setting(role: str, key: str, default: Any = None) -> Any:
    """Return one declared parameter, falling back when it is not stated."""

    return model(role).get(key, default)
