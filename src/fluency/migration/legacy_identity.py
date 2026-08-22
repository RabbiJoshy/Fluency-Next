"""Build a flat progress-alias registry from historical deck evidence."""

from __future__ import annotations

from collections import Counter, defaultdict
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Callable, Iterable

from fluency.core.aliases import (
    AliasEvidence,
    AliasSource,
    ProgressAlias,
    ProgressAliasRegistry,
    sorted_unique_evidence,
)
from fluency.core.canonical_json import canonical_json
from fluency.core.hashing import file_content_id
from fluency.core.identity import CardRecord, create_card_record
from fluency.core.workspace import Workspace
from fluency.languages.surfaces import normalizer_for_language


CROSSWALK_VERSION = "legacy-progress-crosswalk/v1"
LEGACY_MODE_BITS = {"speech": "0", "artist": "1"}
_MIGRATION_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def _load_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ValueError(f"identity evidence does not exist: {path}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"identity evidence is not valid JSON: {path}") from error


def _surface_from_row(row: dict[str, object]) -> str | None:
    surface = row.get("word") or row.get("surface")
    return surface if isinstance(surface, str) and surface.strip() else None


def _source_label(ordinal: int, kind: str) -> str:
    return f"{kind}_{ordinal:02d}"


def _connected_components(adjacency: dict[str, set[str]]) -> list[tuple[str, ...]]:
    seen: set[str] = set()
    components: list[tuple[str, ...]] = []
    for start in sorted(adjacency):
        if start in seen:
            continue
        stack = [start]
        seen.add(start)
        component: list[str] = []
        while stack:
            node = stack.pop()
            component.append(node)
            for neighbor in sorted(adjacency[node], reverse=True):
                if neighbor not in seen:
                    seen.add(neighbor)
                    stack.append(neighbor)
        components.append(tuple(sorted(component)))
    return components


def _directed_migration_counts(mapping: dict[str, str]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for start in mapping:
        current = start
        seen: set[str] = set()
        while current in mapping and current not in seen:
            seen.add(current)
            current = mapping[current]
        counts["cycle_keys" if current in seen else "terminal_keys"] += 1
    return dict(sorted(counts.items()))


def build_legacy_crosswalk(
    *,
    language: str,
    mode: str,
    inventory_path: Path,
    legacy_index_paths: Iterable[Path],
    legacy_migration_path: Path,
    normalize_surface: Callable[[str], str] | None = None,
) -> tuple[tuple[CardRecord, ...], ProgressAliasRegistry, dict[str, object]]:
    """Build an in-memory crosswalk without mutating any source or workspace."""

    if mode not in LEGACY_MODE_BITS:
        raise ValueError("legacy progress crosswalk supports speech or artist mode")
    normalize = (
        normalizer_for_language(language)
        if normalize_surface is None
        else normalize_surface
    )
    index_paths = tuple(Path(path) for path in legacy_index_paths)
    if not index_paths:
        raise ValueError("at least one legacy index is required")

    inventory_raw = _load_json(Path(inventory_path))
    if not isinstance(inventory_raw, list):
        raise ValueError("surface inventory must be a JSON array")

    cards_by_surface: dict[str, CardRecord] = {}
    for row in inventory_raw:
        if not isinstance(row, dict):
            raise ValueError("surface inventory rows must be objects")
        surface = _surface_from_row(row)
        if surface is None:
            raise ValueError("surface inventory row is missing word/surface")
        surface_key = normalize(surface)
        if surface_key in cards_by_surface:
            raise ValueError(f"duplicate normalized inventory surface: {surface_key}")
        cards_by_surface[surface_key] = create_card_record(
            language, surface_key, display_form=surface.strip()
        )

    inventory_source = AliasSource(
        source_id="inventory",
        source_path=str(Path(inventory_path).resolve()),
        source_content_id=file_content_id(Path(inventory_path)),
    )
    sources: dict[str, AliasSource] = {
        inventory_source.source_id: inventory_source
    }
    observations: dict[str, dict[str, list[AliasEvidence]]] = defaultdict(
        lambda: defaultdict(list)
    )
    index_rows = 0
    index_surfaces: Counter[str] = Counter()
    legacy_id_lengths: Counter[int] = Counter()
    per_index: list[dict[str, object]] = []

    for ordinal, path in enumerate(index_paths, start=1):
        raw = _load_json(path)
        if not isinstance(raw, list):
            raise ValueError(f"legacy index must be a JSON array: {path}")
        label = _source_label(ordinal, "legacy_index")
        content_id = file_content_id(path)
        sources[label] = AliasSource(
            source_id=label,
            source_path=str(path.resolve()),
            source_content_id=content_id,
        )
        file_rows = 0
        file_surfaces: Counter[str] = Counter()
        file_id_lengths: Counter[int] = Counter()
        for row in raw:
            if not isinstance(row, dict):
                raise ValueError(f"legacy index row must be an object: {path}")
            legacy_id = row.get("id")
            surface = _surface_from_row(row)
            if not isinstance(legacy_id, str) or surface is None:
                raise ValueError(f"legacy index row lacks id/surface: {path}")
            surface_key = normalize(surface)
            index_rows += 1
            index_surfaces[surface_key] += 1
            legacy_id_lengths[len(legacy_id)] += 1
            file_rows += 1
            file_surfaces[surface_key] += 1
            file_id_lengths[len(legacy_id)] += 1
            observations[legacy_id][surface_key].append(
                AliasEvidence(
                    source_id=label,
                    observation_kind="deck_row",
                    observed_surface_key=surface_key,
                )
            )
            aliases = row.get("alias_ids") or []
            if isinstance(aliases, dict):
                aliases = [aliases]
            if not isinstance(aliases, list):
                raise ValueError(f"legacy alias_ids must be an array: {path}")
            for alias in aliases:
                if not isinstance(alias, dict):
                    raise ValueError(f"legacy alias must be an object: {path}")
                alias_id = alias.get("id")
                alias_surface = alias.get("surface")
                if not isinstance(alias_id, str) or not isinstance(
                    alias_surface, str
                ):
                    raise ValueError(f"legacy alias lacks id/surface: {path}")
                alias_surface_key = normalize(alias_surface)
                observations[alias_id][alias_surface_key].append(
                    AliasEvidence(
                        source_id=label,
                        observation_kind="nested_alias",
                        observed_surface_key=alias_surface_key,
                    )
                )
        per_index.append(
            {
                "path": str(path.resolve()),
                "content_id": content_id,
                "rows": file_rows,
                "unique_surfaces": len(file_surfaces),
                "duplicate_surfaces": sum(
                    count > 1 for count in file_surfaces.values()
                ),
                "id_lengths": {
                    str(length): count
                    for length, count in sorted(file_id_lengths.items())
                },
            }
        )

    migration_raw = _load_json(Path(legacy_migration_path))
    if not isinstance(migration_raw, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in migration_raw.items()
    ):
        raise ValueError("legacy migration map must be a string-to-string object")
    migration = dict(migration_raw)
    migration_path = Path(legacy_migration_path)
    migration_content_id = file_content_id(migration_path)
    migration_label = "legacy_migration"
    sources[migration_label] = AliasSource(
        source_id=migration_label,
        source_path=str(migration_path.resolve()),
        source_content_id=migration_content_id,
    )

    adjacency: dict[str, set[str]] = defaultdict(set)
    for source, target in migration.items():
        adjacency[source].add(target)
        adjacency[target].add(source)
    for legacy_id in observations:
        adjacency.setdefault(legacy_id, set())

    components = _connected_components(adjacency)
    alias_records: list[ProgressAlias] = []
    component_kinds: Counter[str] = Counter()
    legacy_prefix = f"{language}{LEGACY_MODE_BITS[mode]}"

    for component in components:
        component_surfaces = sorted(
            {
                surface
                for legacy_id in component
                for surface in observations.get(legacy_id, {})
            }
        )
        component_kind = (
            "unresolved"
            if not component_surfaces
            else "resolved"
            if len(component_surfaces) == 1
            else "ambiguous"
        )
        component_kinds[component_kind] += 1

        for legacy_id in component:
            direct = observations.get(legacy_id, {})
            direct_surfaces = sorted(direct)
            evidence = [item for items in direct.values() for item in items]
            inferred = False
            if len(direct_surfaces) == 1:
                chosen_surfaces = direct_surfaces
            elif len(direct_surfaces) > 1:
                chosen_surfaces = direct_surfaces
            else:
                chosen_surfaces = component_surfaces
                inferred = True
                evidence.append(
                    AliasEvidence(
                        source_id=migration_label,
                        observation_kind="migration_component",
                    )
                )

            for surface_key in chosen_surfaces:
                if surface_key not in cards_by_surface:
                    cards_by_surface[surface_key] = create_card_record(
                        language,
                        surface_key,
                        status="retired",
                    )

            common = {
                "alias_key": legacy_prefix + legacy_id,
                "language": language,
                "mode": mode,
                "evidence": sorted_unique_evidence(evidence),
            }
            if len(chosen_surfaces) == 1:
                surface_key = chosen_surfaces[0]
                card = cards_by_surface[surface_key]
                alias_records.append(
                    ProgressAlias(
                        **common,
                        status=("retired" if card.status == "retired" else "resolved"),
                        provenance_status=("reconstructed" if inferred else "observed"),
                        canonical_card_id=card.card_id,
                        surface_key=surface_key,
                    )
                )
            elif len(chosen_surfaces) > 1:
                surfaces = tuple(chosen_surfaces)
                alias_records.append(
                    ProgressAlias(
                        **common,
                        status="ambiguous",
                        provenance_status=("reconstructed" if inferred else "observed"),
                        candidate_surface_keys=surfaces,
                        candidate_card_ids=tuple(
                            cards_by_surface[surface].card_id for surface in surfaces
                        ),
                    )
                )
            else:
                alias_records.append(
                    ProgressAlias(
                        **common,
                        status="unresolved",
                        provenance_status="unknown",
                    )
                )

    aliases = tuple(sorted(alias_records, key=lambda item: item.alias_key))
    registry = ProgressAliasRegistry(
        language=language,
        mode=mode,
        aliases=aliases,
        sources=sources,
    )
    cards = tuple(
        sorted(cards_by_surface.values(), key=lambda card: card.surface_key)
    )
    status_counts = Counter(alias.status for alias in aliases)
    report: dict[str, object] = {
        "crosswalk_version": CROSSWALK_VERSION,
        "language": language,
        "mode": mode,
        "inventory_rows": len(inventory_raw),
        "active_cards": sum(card.status == "active" for card in cards),
        "retired_cards": sum(card.status == "retired" for card in cards),
        "legacy_index_files": len(index_paths),
        "legacy_indexes": per_index,
        "primary_legacy_index": per_index[0],
        "legacy_index_rows": index_rows,
        "legacy_unique_surfaces": len(index_surfaces),
        "combined_legacy_surfaces_with_multiple_rows": sum(
            count > 1 for count in index_surfaces.values()
        ),
        "legacy_id_lengths": {
            str(length): count for length, count in sorted(legacy_id_lengths.items())
        },
        "legacy_migration_entries": len(migration),
        "migration_traversal": _directed_migration_counts(migration),
        "migration_components": dict(sorted(component_kinds.items())),
        "alias_counts": dict(sorted(status_counts.items())),
        "sources": {
            source_id: source.to_dict()
            for source_id, source in sorted(sources.items())
        },
        "sheet_rows_modified": 0,
    }
    return cards, registry, report


def write_legacy_crosswalk(
    workspace: Workspace,
    *,
    migration_id: str,
    language: str,
    mode: str,
    inventory_path: Path,
    legacy_index_paths: Iterable[Path],
    legacy_migration_path: Path,
) -> Path:
    """Write one immutable migration report without copying source data."""

    if _MIGRATION_ID_PATTERN.fullmatch(migration_id) is None:
        raise ValueError("invalid migration_id")
    output = workspace.root / "migrations" / language / mode / migration_id
    if output.exists():
        raise FileExistsError(f"migration output already exists: {output}")

    cards, registry, report = build_legacy_crosswalk(
        language=language,
        mode=mode,
        inventory_path=inventory_path,
        legacy_index_paths=legacy_index_paths,
        legacy_migration_path=legacy_migration_path,
    )
    payloads = {
        "cards.json": [card.to_dict() for card in cards],
        "aliases.json": registry.to_dict(),
        "exceptions.json": [
            alias.to_dict()
            for alias in registry.aliases
            if alias.status in {"ambiguous", "unresolved"}
        ],
        "report.json": report,
    }
    temporary_root = workspace.root / ".fluency" / "temporary"
    temporary = Path(tempfile.mkdtemp(prefix="identity-", dir=temporary_root))
    try:
        for filename, payload in payloads.items():
            (temporary / filename).write_text(
                canonical_json(payload) + "\n", encoding="utf-8"
            )

        manifest = {
            "crosswalk_version": CROSSWALK_VERSION,
            "migration_id": migration_id,
            "language": language,
            "mode": mode,
            "outputs": {
                filename: file_content_id(temporary / filename)
                for filename in sorted(payloads)
            },
            "sources": registry.to_dict()["sources"],
            "mutations": {
                "source_files": False,
                "google_sheets": False,
                "active_release": False,
            },
        }
        (temporary / "manifest.json").write_text(
            canonical_json(manifest) + "\n", encoding="utf-8"
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return output
