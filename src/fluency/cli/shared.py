"""Imports, constants and helpers shared by the command modules.

Split out of the former single ``cli.py`` (1,706 lines, 57 subcommands) so that
adding a command means creating a module rather than editing one file that every
other command also edits. That file was the repository's main collision point
between concurrent sessions.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from typing import Sequence
from urllib.parse import unquote, urlsplit

from fluency.artist.release import (
    activate_lyrics_release,
    build_lyrics_catalog_release,
    resolve_active_lyrics_asset,
    validate_lyrics_release,
)
from fluency.core.languages import app_data_routes
from fluency.core.workspace import Workspace
from fluency.deployment.static import build_static_deployment
from fluency.enrichments.conjugations import build_conjugation_layer, pin_jehle_snapshot
from fluency.harvest.runner import harvest_run_stage
from fluency.inventory.corpus_frequency import compile_corpus_frequency_snapshot
from fluency.inventory.runner import build_inventory_stage
from fluency.lyrics.ingest import ingest_legacy_genius_song
from fluency.lyrics.corpus import build_lyrics_corpus_plan, ingest_lyrics_corpus_plan
from fluency.lyrics.corpus_process import (
    build_lyrics_corpus_processing_profile,
    process_lyrics_corpus_plan,
)
from fluency.lyrics.corpus_lexical import build_lyrics_corpus_lexical_menus
from fluency.lyrics.corpus_wsd import prepare_lyrics_corpus_wsd
from fluency.lyrics.audit_server import LyricsAuditResolver, LyricsAuditServerError
from fluency.lyrics.corpus_results import import_lyrics_corpus_results
from fluency.lyrics.corpus_consolidate import consolidate_lyrics_corpus
from fluency.lyrics.corpus_assemble import assemble_lyrics_corpus
from fluency.lyrics.corpus_release import build_clean_lyrics_corpus_release
from fluency.lyrics.corpus_execute import execute_spanish_v5_corpus
from fluency.lyrics.consolidate import consolidate_lyrics_run
from fluency.lyrics.assemble import assemble_lyrics_app_stage
from fluency.lyrics.preview import build_clean_lyrics_preview_release
from fluency.lyrics.lexical import build_lyrics_lexical_menu_stage
from fluency.lyrics.process import process_lyrics_run
from fluency.lyrics.wsd import prepare_lyrics_wsd_stage
from fluency.lyrics.wsd_results import import_lyrics_wsd_results
from fluency.lyrics.wsd_execute import execute_spanish_v5_lyrics
from fluency.migration.legacy_identity import write_legacy_crosswalk
from fluency.migration.spanish_assets import migrate_spanish_retained_assets
from fluency.migration.spanish_dictionary import migrate_spanish_dictionary_snapshot
from fluency.migration.spanish_wsd_assets import migrate_spanish_wsd_assets
from fluency.harvest.pools import (
    read_pool,
    rebuild_catalog,
    register_pool_from_run,
)
from fluency.pipeline.budget import (
    check_wsd_budget,
    display_examples_per_card,
    wsd_budget_per_card,
)
from fluency.pipeline.planning import create_pipeline_plan, load_pipeline_profile
from fluency.release.activation import activate_release
from fluency.release.catalog import build_catalog, write_catalog
from fluency.release.composition import compose_release, load_json_object
from fluency.release.pilot import build_pilot_release
from fluency.release.run_candidate import build_inactive_run_candidate
from fluency.release.validation import validate_release_bundle
from fluency.sense_menu.runner import build_sense_menu_stage
from fluency.wsd.importer import import_wsd_assignments


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 4173
APP_DATA_ROUTES = app_data_routes()
SAFE_ACTIVE_RELEASE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def project_root() -> Path:
    """Return the repository root for a source checkout.

    Depth counted from ``src/fluency/cli/shared.py``: cli -> fluency -> src ->
    root. This moved one level deeper when the single ``cli.py`` was split, and
    it resolves every config lookup, so it is asserted in tests/test_bootstrap.
    """

    return Path(__file__).resolve().parents[3]

def _workspace_path(raw_path: str | None) -> Path:
    if not raw_path:
        raise SystemExit(
            "Workspace path is required: pass --path or set FLUENCY_WORKSPACE"
        )
    return Path(raw_path)


def resolve_active_app_asset(releases_directory: Path, request_path: str) -> Path | None:
    route = APP_DATA_ROUTES.get(request_path)
    if route is None:
        return None
    language, asset_field = route
    release_root = releases_directory / language / "speech"
    try:
        active = json.loads((release_root / "active.json").read_text(encoding="utf-8"))
        release_id = active["release_id"]
    except (FileNotFoundError, KeyError, TypeError, json.JSONDecodeError):
        return release_root / ".missing-active-app-asset"
    if not isinstance(release_id, str) or SAFE_ACTIVE_RELEASE_ID.fullmatch(release_id) is None:
        return release_root / ".invalid-active-app-asset"
    release_directory = (release_root / release_id).resolve()
    try:
        release_directory.relative_to(release_root.resolve())
    except ValueError:
        return release_root / ".invalid-active-app-asset"
    if asset_field == "__manifest__":
        return release_directory / "manifest.json"
    if asset_field == "__composition__":
        return release_directory / "composition.json"
    try:
        manifest = json.loads(
            (release_directory / "manifest.json").read_text(encoding="utf-8")
        )
        relative_path = manifest["app_contract"][asset_field]
    except (FileNotFoundError, KeyError, TypeError, json.JSONDecodeError):
        return release_root / ".missing-active-app-asset"
    if not isinstance(relative_path, str):
        return release_root / ".invalid-active-app-asset"
    candidate = (release_directory / relative_path).resolve()
    try:
        candidate.relative_to(release_directory)
    except ValueError:
        return release_root / ".invalid-active-app-asset"
    return candidate


