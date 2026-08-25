"""Named, described pools of harvested sentences, and the catalog over them.

A pool is a flat set of sentences. Deliberately no cards: a card-indexed pool
would be welded to the inventory it was built against, so changing the word list
would invalidate it. Keeping cards out is what lets one European pool serve a
200-card audit and a 5,000-card deck alike.

Everything below a pool only narrows within it -- the per-card WSD budget, WSD
abstaining, the display limit -- so "every example on this card came from one
pool" is true by construction rather than by bookkeeping.

Pools may overlap. A sentence can sit in both an ``european`` and an
``easy-short`` pool without conflict, because which pool a card drew from is a
property of the run's choice, not of the sentence.

Nothing here is required. A run that names no pool harvests inline exactly as
before, which is what every existing run does: one implicit, unnamed pool.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
import shutil
from typing import Any

from fluency.core.hashing import canonical_content_id
from fluency.core.io import atomic_write


POOL_VERSION = "harvest-pool/v1"
CATALOG_VERSION = "harvest-pool-catalog/v1"
POOL_FILE = "pool.json"
CATALOG_FILE = "catalog.json"
_POOL_ID = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class PoolError(ValueError):
    """Raised when a pool is unnamed, undescribed, or would be overwritten."""


def pools_root(workspace_root: Path, language: str) -> Path:
    return workspace_root / "pools" / language


def _validate_id(pool_id: str) -> str:
    if not isinstance(pool_id, str) or _POOL_ID.fullmatch(pool_id) is None:
        raise PoolError(f"invalid pool ID: {pool_id!r}")
    return pool_id


def build_pool_descriptor(
    *,
    pool_id: str,
    language: str,
    description: str,
    sources: list[dict[str, Any]],
    config: dict[str, Any],
    coverage: dict[str, Any],
    intent: str | None = None,
    variety: str | None = None,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    """Return a pool descriptor.

    ``description`` is required and must be non-empty. A pool whose purpose is
    not written down in words is exactly the pool that becomes unusable three
    months later, which is the problem this file exists to solve.
    """

    _validate_id(pool_id)
    if not isinstance(description, str) or not description.strip():
        raise PoolError("a pool requires a non-empty free-text description")
    if not sources:
        raise PoolError("a pool must record at least one source snapshot")

    descriptor: dict[str, Any] = {
        "pool_version": POOL_VERSION,
        "pool_id": pool_id,
        "language": language,
        "description": description.strip(),
        "created_at": (created_at or datetime.now(UTC))
        .astimezone(UTC)
        .isoformat()
        .replace("+00:00", "Z"),
        "sources": sources,
        "config": config,
        "coverage": coverage,
    }
    if intent and intent.strip():
        descriptor["intent"] = intent.strip()
    if variety and variety.strip():
        descriptor["variety"] = variety.strip()
    descriptor["content_id"] = canonical_content_id(
        {k: v for k, v in descriptor.items() if k != "created_at"}
    )
    return descriptor


def year_histogram(records: Any) -> dict[str, int]:
    """Return a release-year histogram from sentence records that carry one.

    Recency is otherwise invisible without a separate IMDb lookup, which is how
    a corpus whose newest film was 2011 went unnoticed.
    """

    years: Counter[str] = Counter()
    for record in records:
        year = ((record.get("source") or {}).get("document") or {}).get("year")
        if isinstance(year, str) and year.isdigit():
            years[year] += 1
    return dict(sorted(years.items()))


def write_pool(workspace_root: Path, descriptor: dict[str, Any]) -> Path:
    """Write one immutable pool descriptor and return its directory."""

    pool_id = _validate_id(descriptor.get("pool_id", ""))
    directory = pools_root(workspace_root, descriptor["language"]) / pool_id
    target = directory / POOL_FILE
    if target.exists():
        raise PoolError(
            f"pool already exists; choose a new pool ID rather than overwriting: {target}"
        )
    directory.mkdir(parents=True, exist_ok=True)
    atomic_write(target, descriptor, workspace_root / ".fluency" / "temporary")
    return directory


def read_pool(workspace_root: Path, language: str, pool_id: str) -> dict[str, Any]:
    path = pools_root(workspace_root, language) / _validate_id(pool_id) / POOL_FILE
    try:
        descriptor = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise PoolError(f"pool does not exist: {path}") from error
    except json.JSONDecodeError as error:
        raise PoolError(f"pool descriptor is not valid JSON: {path}") from error
    if descriptor.get("pool_version") != POOL_VERSION:
        raise PoolError(f"unsupported pool descriptor: {path}")
    return descriptor


def rebuild_catalog(workspace_root: Path, language: str) -> dict[str, Any]:
    """Rewrite the catalog from whatever pools exist on disk.

    Derived, never authoritative: a pool is real because its directory exists,
    not because the catalog mentions it.
    """

    root = pools_root(workspace_root, language)
    pools: dict[str, Any] = {}
    if root.is_dir():
        for directory in sorted(p for p in root.iterdir() if p.is_dir()):
            path = directory / POOL_FILE
            if not path.is_file():
                continue
            descriptor = json.loads(path.read_text(encoding="utf-8"))
            entry = {
                "path": f"pools/{language}/{directory.name}",
                "description": descriptor.get("description", ""),
                "sentences": (descriptor.get("coverage") or {}).get("sentences", 0),
                "content_id": descriptor.get("content_id", ""),
            }
            for optional in ("intent", "variety"):
                if descriptor.get(optional):
                    entry[optional] = descriptor[optional]
            pools[descriptor.get("pool_id", directory.name)] = entry

    catalog = {
        "catalog_version": CATALOG_VERSION,
        "language": language,
        "updated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "pools": pools,
    }
    root.mkdir(parents=True, exist_ok=True)
    atomic_write(root / CATALOG_FILE, catalog, workspace_root / ".fluency" / "temporary")
    return catalog


def register_pool_from_run(
    workspace_root: Path,
    run_directory: Path,
    *,
    pool_id: str,
    description: str,
    intent: str | None = None,
    variety: str | None = None,
) -> Path:
    """Promote a finished harvest into a named, reusable pool.

    The harvest a run already produced *is* a pool -- an unnamed one, with one
    source and no description. Registering it only writes down what it is and
    lifts it out of the run, so a later run can pick it deliberately instead of
    re-scanning the corpus.

    The sentence bank is hard-linked to the run's copy where the filesystem
    allows it, falling back to a real copy across devices. Both files are
    immutable by contract, so sharing the inode costs nothing and a pool no
    longer doubles the bytes of the run it came from. This is a stopgap for the
    shared content-addressed store, which additionally deduplicates ACROSS runs
    (measured at 59% duplication over three Spanish runs); correctness does not
    depend on either, so neither is a prerequisite for naming pools.
    """

    stage = run_directory / "stages" / "03_sentence_harvest" / "output"
    bank = stage / "sentence-bank.jsonl"
    report_path = stage / "report.json"
    if not bank.is_file() or not report_path.is_file():
        raise PoolError(f"run has no completed sentence harvest: {stage}")

    report = json.loads(report_path.read_text(encoding="utf-8"))
    profile = json.loads((run_directory / "profile.json").read_text(encoding="utf-8"))

    records = [json.loads(line) for line in bank.read_text(encoding="utf-8").splitlines() if line.strip()]
    sources = [
        {
            "name": source.get("source", ""),
            "adapter": source.get("adapter", ""),
            "snapshot_id": source.get("snapshot_id", ""),
            "snapshot_content_id": source.get("snapshot_content_id", ""),
        }
        for source in report.get("sources", [])
    ]

    descriptor = build_pool_descriptor(
        pool_id=pool_id,
        language=report["language"],
        description=description,
        intent=intent,
        variety=variety,
        sources=sources,
        config={
            "shared_policy": profile["harvest"]["shared_policy"],
            "language_policy": profile["harvest"]["language_policy"],
        },
        coverage={
            "sentences": len(records),
            "records_scanned": report.get("records_scanned", 0),
            "years": year_histogram(records),
        },
    )

    directory = write_pool(workspace_root, descriptor)
    target = directory / "sentence-bank.jsonl"
    try:
        os.link(bank, target)
    except OSError:
        # Different device, or a filesystem without hard links.
        shutil.copyfile(bank, target)
    rebuild_catalog(workspace_root, descriptor["language"])
    return directory
