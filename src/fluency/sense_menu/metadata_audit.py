"""Cross-language inventory for sense metadata policy work."""

from __future__ import annotations

from collections import Counter
import gzip
import json
from pathlib import Path
from typing import Any, Iterator

from fluency.features.wiktionary import extract, metadata_accounting
from fluency.sense_menu.config import (
    load_sense_menu_language_policy,
    load_sense_menu_registry,
)


WIKTIONARY_LANGUAGE_NAMES = {
    "cs": "Czech",
    "fr": "French",
    "it": "Italian",
    "nl": "Dutch",
    "pl": "Polish",
    "pt": "Portuguese",
    "ru": "Russian",
    "sv": "Swedish",
}


def _open_jsonl(path: Path):
    return gzip.open(path, "rt", encoding="utf-8") if path.suffix == ".gz" else path.open(encoding="utf-8")


def _senses(path: Path, language: str) -> Iterator[dict[str, Any]]:
    with _open_jsonl(path) as stream:
        for line_number, line in enumerate(stream, 1):
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid Wiktionary JSON on line {line_number}") from error
            if not isinstance(row, dict) or row.get("lang_code") != language:
                continue
            for sense in row.get("senses", []) or []:
                if isinstance(sense, dict):
                    yield sense


def audit_wiktionary_snapshot(
    repository_root: Path,
    *,
    language: str,
    policy_id: str,
    snapshot: Path,
) -> dict[str, Any]:
    """Summarize what is typed and what remains in the classification queue."""

    policy = load_sense_menu_language_policy(
        repository_root, policy_id=policy_id, language=language
    )
    if policy["provider"] != "wiktionary":
        raise ValueError("Wiktionary audit requires a Wiktionary language policy")
    feature_families: Counter[str] = Counter()
    unclassified: Counter[tuple[str, str, str]] = Counter()
    ignored: Counter[tuple[str, str, str]] = Counter()
    observed_tags: Counter[str] = Counter()
    observed_templates: Counter[str] = Counter()
    sense_count = 0
    for sense in _senses(snapshot, language):
        sense_count += 1
        tags = sorted({tag for tag in sense.get("tags", []) or [] if isinstance(tag, str)})
        observed_tags.update(tags)
        for template in sense.get("info_templates", []) or []:
            if isinstance(template, dict):
                observed_templates[str(template.get("name") or "<unnamed>")] += 1
            else:
                observed_templates["<invalid>"] += 1
        feature_families.update(
            feature.family for feature in extract(sense, tags=tags, policy=policy)
        )
        accounting = metadata_accounting(sense, tags=tags, policy=policy)
        for item in accounting.unclassified:
            value = item.get("value")
            rendered = json.dumps(value, ensure_ascii=False, sort_keys=True)
            unclassified[(item["source_field"], rendered, item["reason"])] += 1
        for item in accounting.ignored:
            value = item.get("value")
            rendered = json.dumps(value, ensure_ascii=False, sort_keys=True)
            ignored[(item["source_field"], rendered, item["reason"])] += 1
    return {
        "report_version": "sense-metadata-audit/v1",
        "metadata_contract": "sense-metadata/v1",
        "language": language,
        "policy_id": policy_id,
        "policy_audit_status": policy["audit_status"],
        "snapshot": str(snapshot),
        "sense_count": sense_count,
        "feature_families": dict(sorted(feature_families.items())),
        "observed_tags": dict(sorted(observed_tags.items())),
        "observed_templates": dict(sorted(observed_templates.items())),
        "unclassified": [
            {
                "source_field": source_field,
                "value": json.loads(value),
                "reason": reason,
                "count": count,
            }
            for (source_field, value, reason), count in sorted(
                unclassified.items(), key=lambda item: (-item[1], item[0])
            )
        ],
        "ignored": [
            {
                "source_field": source_field,
                "value": json.loads(value),
                "reason": reason,
                "count": count,
            }
            for (source_field, value, reason), count in sorted(
                ignored.items(), key=lambda item: (-item[1], item[0])
            )
        ],
    }


def _release_status(app_root: Path | None, entry: dict[str, Any]) -> dict[str, Any]:
    if app_root is None:
        return {"release_status": "not_checked", "release_metadata_contract": None}
    config_path = app_root / "config" / "config.json"
    if not config_path.is_file():
        return {"release_status": "missing", "release_metadata_contract": None}
    config = json.loads(config_path.read_text(encoding="utf-8"))
    language = (config.get("languages") or {}).get(entry["app_key"])
    if not isinstance(language, dict):
        return {"release_status": "missing", "release_metadata_contract": None}
    if language.get("hasData") is False:
        return {"release_status": "inactive", "release_metadata_contract": None}
    manifest_path = language.get("releaseManifestPath")
    if not isinstance(manifest_path, str) or not (app_root / manifest_path).is_file():
        return {"release_status": "missing", "release_metadata_contract": None}
    manifest = json.loads((app_root / manifest_path).read_text(encoding="utf-8"))
    contract = manifest.get("metadata_contract")
    return {
        "release_status": "current" if contract == "sense-metadata/v1" else "legacy",
        "release_metadata_contract": contract,
    }


def metadata_status(
    repository_root: Path,
    workspace_root: Path | None = None,
    app_root: Path | None = None,
) -> dict[str, Any]:
    """Build the policy/snapshot matrix from files rather than a hand-kept table."""

    registry = load_sense_menu_registry(repository_root)
    rows = []
    for language, entry in sorted(registry["languages"].items()):
        snapshots: list[Path] = []
        if workspace_root is not None:
            if entry["provider"] == "wiktionary":
                name = WIKTIONARY_LANGUAGE_NAMES[language]
                snapshots = sorted(
                    (workspace_root / "raw" / "wiktionary").glob(
                        f"*/kaikki.org-dictionary-{name}.jsonl*"
                    )
                )
            elif entry["provider"] == "spanishdict":
                snapshots = sorted(
                    path.parent
                    for path in (workspace_root / "raw" / "spanishdict").glob(
                        "*/artifact.json"
                    )
                )
        rows.append({
            "language": language,
            "provider": entry["provider"],
            "policy_id": entry["policy_id"],
            "audit_status": entry["audit_status"],
            "snapshot": str(snapshots[-1]) if snapshots else None,
            **_release_status(app_root, entry),
        })
    return {
        "report_version": "sense-metadata-status/v1",
        "metadata_contract": registry["metadata_contract"],
        "languages": rows,
    }
