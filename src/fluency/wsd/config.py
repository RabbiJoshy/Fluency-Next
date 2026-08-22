"""Load the exact shared, language, and model profiles selected by a run."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from fluency.core.hashing import canonical_content_id, validate_content_id


_PROFILE_ID = re.compile(r"^[a-z0-9-]+$")
_VERSIONS = {
    "shared": "wsd-shared-profile/v1",
    "languages": "wsd-language-profile/v1",
    "models": "wsd-model-profile/v1",
}


class WSDProfileError(ValueError):
    """Raised when selected WSD profiles are missing, inconsistent, or unready."""


def _load(root: Path, family: str, profile_id: str) -> dict[str, Any]:
    if _PROFILE_ID.fullmatch(profile_id) is None:
        raise WSDProfileError(f"invalid WSD {family} profile ID: {profile_id!r}")
    path = root / "config" / "wsd" / family / f"{profile_id}.json"
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise WSDProfileError(f"WSD profile does not exist: {path}") from error
    except json.JSONDecodeError as error:
        raise WSDProfileError(f"WSD profile is not valid JSON: {path}") from error
    if not isinstance(record, dict):
        raise WSDProfileError(f"WSD profile must contain an object: {path}")
    if record.get("config_version") != _VERSIONS[family]:
        raise WSDProfileError(f"unsupported WSD profile version: {path}")
    if record.get("profile_id") != profile_id:
        raise WSDProfileError(f"WSD profile ID does not match its filename: {path}")
    return record


def model_revisions(model: dict[str, Any]) -> dict[str, str]:
    revisions: dict[str, str] = {}
    component_fields = {
        "gloss": ("model_revision",),
        "token_tuple_vote": ("model_revision", "prototype_content_id"),
        "calibration": ("model_revision", "feature_version"),
        "alignment": ("model_revision",),
    }
    for component, fields in component_fields.items():
        selection = model.get(component)
        if not isinstance(selection, dict):
            raise WSDProfileError(f"model profile is missing {component}")
        if selection.get("enabled") is not True:
            continue
        for field in fields:
            value = selection.get(field)
            if not isinstance(value, str) or not value:
                raise WSDProfileError(f"enabled {component} requires {field}")
            if field == "prototype_content_id":
                validate_content_id(value)
            revisions[f"{component}.{field}"] = value
    return revisions


def load_wsd_profiles(
    repository_root: Path,
    pipeline_profile: dict[str, Any],
    *,
    require_ready: bool = False,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], str]:
    selection = pipeline_profile["wsd"]
    shared = _load(repository_root, "shared", selection["shared_profile"])
    language = _load(repository_root, "languages", selection["language_profile"])
    model = _load(repository_root, "models", selection["model_profile"])
    if language.get("language") != pipeline_profile.get("language"):
        raise WSDProfileError("WSD language profile does not match the run")
    if model.get("language") != pipeline_profile.get("language"):
        raise WSDProfileError("WSD model profile does not match the run")
    status = model.get("execution_status")
    if status != selection.get("execution_status"):
        raise WSDProfileError("pipeline and WSD model execution statuses disagree")
    if shared.get("fallback_policy") != "none":
        raise WSDProfileError("WSD fallback policy must remain disabled")
    if shared.get("generative_escalation") is not False:
        raise WSDProfileError("shared WSD profile unexpectedly enables escalation")
    if model.get("generative_escalation") is not False:
        raise WSDProfileError("model WSD profile unexpectedly enables escalation")
    if require_ready and status != "ready":
        raise WSDProfileError(f"WSD execution is blocked: {status}")
    if status == "ready":
        revisions = model_revisions(model)
        if revisions != selection.get("model_revisions"):
            raise WSDProfileError("pipeline model pins do not match the selected model profile")
    combined = {"selection": selection, "shared": shared, "language": language, "model": model}
    return shared, language, model, canonical_content_id(combined)
