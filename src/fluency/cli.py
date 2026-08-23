"""Command-line entry point for local Fluency development."""

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
from fluency.lyrics.corpus_results import import_lyrics_corpus_results
from fluency.lyrics.corpus_consolidate import consolidate_lyrics_corpus
from fluency.lyrics.corpus_assemble import assemble_lyrics_corpus
from fluency.lyrics.corpus_release import build_clean_lyrics_corpus_release
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
APP_DATA_ROUTES = {
    "/Data/French/vocabulary.index.json": ("fr", "index_path"),
    "/Data/French/vocabulary.examples.json": ("fr", "examples_path"),
    "/Data/French/study-structure.json": ("fr", "study_structure_path"),
    "/Data/French/release-manifest.json": ("fr", "__manifest__"),
    "/Data/French/release-composition.json": ("fr", "__composition__"),
    "/Data/French/conjugations.json": ("fr", "conjugations_path"),
    "/Data/Spanish/vocabulary.index.json": ("es", "index_path"),
    "/Data/Spanish/vocabulary.examples.json": ("es", "examples_path"),
    "/Data/Spanish/study-structure.json": ("es", "study_structure_path"),
    "/Data/Spanish/release-manifest.json": ("es", "__manifest__"),
    "/Data/Spanish/release-composition.json": ("es", "__composition__"),
    "/Data/Spanish/conjugations.json": ("es", "conjugations_path"),
    "/Data/Dutch/vocabulary.index.json": ("nl", "index_path"),
    "/Data/Dutch/vocabulary.examples.json": ("nl", "examples_path"),
    "/Data/Dutch/study-structure.json": ("nl", "study_structure_path"),
    "/Data/Dutch/release-manifest.json": ("nl", "__manifest__"),
    "/Data/Dutch/release-composition.json": ("nl", "__composition__"),
    "/Data/Dutch/conjugations.json": ("nl", "conjugations_path"),
    "/Data/Portuguese/vocabulary.index.json": ("pt", "index_path"),
    "/Data/Portuguese/vocabulary.examples.json": ("pt", "examples_path"),
    "/Data/Portuguese/study-structure.json": ("pt", "study_structure_path"),
    "/Data/Portuguese/release-manifest.json": ("pt", "__manifest__"),
    "/Data/Portuguese/release-composition.json": ("pt", "__composition__"),
    "/Data/Portuguese/conjugations.json": ("pt", "conjugations_path"),
}
SAFE_ACTIVE_RELEASE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def project_root() -> Path:
    """Return the repository root for a source checkout."""

    return Path(__file__).resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fluency")
    subparsers = parser.add_subparsers(dest="command", required=True)

    dev = subparsers.add_parser("dev", help="serve the local app directory")
    dev.add_argument(
        "--host",
        default=os.environ.get("FLUENCY_HOST", DEFAULT_HOST),
        help="address to bind (default: %(default)s)",
    )
    dev.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("FLUENCY_PORT", DEFAULT_PORT)),
        help="port to bind (default: %(default)s)",
    )
    dev.add_argument(
        "--workspace",
        default=os.environ.get("FLUENCY_WORKSPACE"),
        help="workspace whose releases are mounted at /releases/",
    )

    workspace = subparsers.add_parser(
        "workspace", help="initialize and inspect the external data workspace"
    )
    workspace_actions = workspace.add_subparsers(
        dest="workspace_command", required=True
    )
    for action, help_text in (
        ("init", "initialize an empty workspace"),
        ("show", "show workspace identity and location"),
        ("doctor", "diagnose workspace safety and layout"),
    ):
        action_parser = workspace_actions.add_parser(action, help=help_text)
        action_parser.add_argument(
            "--path",
            default=os.environ.get("FLUENCY_WORKSPACE"),
            help="workspace root (or set FLUENCY_WORKSPACE)",
        )

    pilot = subparsers.add_parser(
        "pilot", help="build the hand-curated French Speech pilot"
    )
    pilot_actions = pilot.add_subparsers(dest="pilot_command", required=True)
    pilot_build = pilot_actions.add_parser(
        "build", help="publish the deterministic pilot release"
    )
    pilot_build.add_argument(
        "--workspace",
        default=os.environ.get("FLUENCY_WORKSPACE"),
        help="workspace root (or set FLUENCY_WORKSPACE)",
    )

    frequency = subparsers.add_parser(
        "frequency", help="compile reusable, immutable surface-frequency snapshots"
    )
    frequency_actions = frequency.add_subparsers(
        dest="frequency_command", required=True
    )
    compile_corpus = frequency_actions.add_parser(
        "compile-corpus", help="stream one pinned text corpus into ranked surfaces"
    )
    compile_corpus.add_argument(
        "--workspace", default=os.environ.get("FLUENCY_WORKSPACE")
    )
    compile_corpus.add_argument("--language", required=True)
    compile_corpus.add_argument("--corpus", type=Path, required=True)
    compile_corpus.add_argument("--snapshot-id", required=True)
    compile_corpus.add_argument("--provider", required=True)

    migration = subparsers.add_parser(
        "migration", help="pin explicitly approved retained sources into the workspace"
    )
    migration_actions = migration.add_subparsers(
        dest="migration_command", required=True
    )
    spanish_assets = migration_actions.add_parser(
        "spanish-retained-assets",
        help="migrate the audited inventory, sentence bank, and Gemini cache only",
    )
    spanish_assets.add_argument(
        "--workspace", default=os.environ.get("FLUENCY_WORKSPACE")
    )
    spanish_assets.add_argument("--source-repository", type=Path, required=True)
    spanish_dictionary = migration_actions.add_parser(
        "spanish-dictionary-snapshot",
        help="pin the audited offline SpanishDict and morphology inputs",
    )
    spanish_dictionary.add_argument(
        "--workspace", default=os.environ.get("FLUENCY_WORKSPACE")
    )
    spanish_dictionary.add_argument("--source-repository", type=Path, required=True)
    spanish_wsd = migration_actions.add_parser(
        "spanish-wsd-assets",
        help="pin exact BETO prototypes and legacy calibrator without assignments",
    )
    spanish_wsd.add_argument("--workspace", default=os.environ.get("FLUENCY_WORKSPACE"))
    spanish_wsd.add_argument("--source-repository", type=Path, required=True)
    spanish_jehle = migration_actions.add_parser(
        "spanish-jehle-snapshot",
        help="pin one recovered Jehle conjugation CSV as immutable source evidence",
    )
    spanish_jehle.add_argument(
        "--workspace", default=os.environ.get("FLUENCY_WORKSPACE")
    )
    spanish_jehle.add_argument("--source", type=Path, required=True)
    spanish_jehle.add_argument("--snapshot-id", required=True)

    enrichment = subparsers.add_parser(
        "enrichment", help="build independently selectable optional product layers"
    )
    enrichment_actions = enrichment.add_subparsers(
        dest="enrichment_command", required=True
    )
    conjugations = enrichment_actions.add_parser(
        "build-conjugations",
        help="build a bounded conjugation layer for one exact sense menu",
    )
    conjugations.add_argument(
        "--workspace", default=os.environ.get("FLUENCY_WORKSPACE")
    )
    conjugations.add_argument("--sense-menu", type=Path, required=True)
    conjugations.add_argument("--source-snapshot", type=Path, required=True)
    conjugations.add_argument("--locale", default="es-ES")

    deployment = subparsers.add_parser(
        "deployment", help="compose an inactive self-contained static app candidate"
    )
    deployment_actions = deployment.add_subparsers(dest="deployment_command", required=True)
    deployment_build = deployment_actions.add_parser(
        "build-static", help="copy exact Speech and Lyrics releases into a deployable static site"
    )
    deployment_build.add_argument("--workspace", default=os.environ.get("FLUENCY_WORKSPACE"))
    deployment_build.add_argument("--deployment-id", required=True)
    deployment_build.add_argument(
        "--speech", action="append", required=True, metavar="LANGUAGE=RELEASE_ID"
    )
    deployment_build.add_argument("--lyrics-release", required=True)

    artist = subparsers.add_parser(
        "artist", help="build, validate, and activate immutable Lyrics catalogs"
    )
    artist_actions = artist.add_subparsers(dest="artist_command", required=True)
    artist_build = artist_actions.add_parser(
        "build-catalog-release",
        help="freeze the configured legacy Artist app assets into one exact release",
    )
    artist_build.add_argument(
        "--workspace", default=os.environ.get("FLUENCY_WORKSPACE")
    )
    artist_build.add_argument("--source-repository", type=Path, required=True)
    artist_build.add_argument("--release-id", required=True)
    for action in ("validate", "activate"):
        action_parser = artist_actions.add_parser(action)
        action_parser.add_argument(
            "--workspace", default=os.environ.get("FLUENCY_WORKSPACE")
        )
        action_parser.add_argument("release_id")

    lyrics = subparsers.add_parser(
        "lyrics", help="ingest and process auditable, language-agnostic Lyrics runs"
    )
    lyrics_actions = lyrics.add_subparsers(dest="lyrics_command", required=True)
    lyrics_plan_corpus = lyrics_actions.add_parser(
        "plan-corpus",
        help="pin and inventory an explicit multi-artist source corpus without executing it",
    )
    lyrics_plan_corpus.add_argument("--workspace", default=os.environ.get("FLUENCY_WORKSPACE"))
    lyrics_plan_corpus.add_argument("--config", type=Path, required=True)
    lyrics_plan_corpus.add_argument("--source-repository", type=Path, required=True)
    lyrics_plan_corpus.add_argument("--plan-id", required=True)
    lyrics_ingest_corpus = lyrics_actions.add_parser(
        "ingest-corpus",
        help="materialize every pinned song as an immutable source-ingest run with safe resume",
    )
    lyrics_ingest_corpus.add_argument("--workspace", default=os.environ.get("FLUENCY_WORKSPACE"))
    lyrics_ingest_corpus.add_argument("--plan", type=Path, required=True)
    lyrics_process_corpus = lyrics_actions.add_parser(
        "process-corpus",
        help="process every pinned song with one exact language profile and safe resume",
    )
    lyrics_process_corpus.add_argument("--workspace", default=os.environ.get("FLUENCY_WORKSPACE"))
    lyrics_process_corpus.add_argument("--plan", type=Path, required=True)
    lyrics_process_corpus.add_argument("--profile", type=Path, required=True)
    lyrics_menu_corpus = lyrics_actions.add_parser(
        "menu-corpus",
        help="build one provider union and exact resumable lexical menus for every processed song",
    )
    lyrics_menu_corpus.add_argument("--workspace", default=os.environ.get("FLUENCY_WORKSPACE"))
    lyrics_menu_corpus.add_argument("--plan", type=Path, required=True)
    lyrics_menu_corpus.add_argument("--dictionary-snapshot", type=Path, required=True)
    lyrics_menu_corpus.add_argument("--snapshot-id", required=True)
    lyrics_menu_corpus.add_argument("--language-policy", required=True)
    lyrics_menu_corpus.add_argument("--menu-id", required=True)
    lyrics_wsd_prepare_corpus = lyrics_actions.add_parser(
        "wsd-prepare-corpus",
        help="prepare exact WSD request pools for every menu-complete song without executing a model",
    )
    lyrics_wsd_prepare_corpus.add_argument("--workspace", default=os.environ.get("FLUENCY_WORKSPACE"))
    lyrics_wsd_prepare_corpus.add_argument("--plan", type=Path, required=True)
    lyrics_wsd_prepare_corpus.add_argument("--lexical-report", type=Path, required=True)
    lyrics_wsd_import_corpus = lyrics_actions.add_parser(
        "wsd-import-corpus",
        help="import an exact complete catalog of per-song WSD bundles from any compliant method",
    )
    lyrics_wsd_import_corpus.add_argument("--workspace", default=os.environ.get("FLUENCY_WORKSPACE"))
    lyrics_wsd_import_corpus.add_argument("--plan", type=Path, required=True)
    lyrics_wsd_import_corpus.add_argument("--preparation-report", type=Path, required=True)
    lyrics_wsd_import_corpus.add_argument("--catalog", type=Path, required=True)
    lyrics_consolidate_corpus = lyrics_actions.add_parser(
        "consolidate-corpus",
        help="consolidate every song after one complete exact corpus WSD import",
    )
    lyrics_consolidate_corpus.add_argument("--workspace", default=os.environ.get("FLUENCY_WORKSPACE"))
    lyrics_consolidate_corpus.add_argument("--plan", type=Path, required=True)
    lyrics_consolidate_corpus.add_argument("--wsd-import-report", type=Path, required=True)
    lyrics_consolidate_corpus.add_argument("--example-cap-per-sense", type=int, default=12)
    lyrics_consolidate_corpus.add_argument("--translation-language", default="en")
    lyrics_assemble_corpus = lyrics_actions.add_parser(
        "assemble-corpus",
        help="merge one exact WSD-method branch into clean multi-artist app data",
    )
    lyrics_assemble_corpus.add_argument("--workspace", default=os.environ.get("FLUENCY_WORKSPACE"))
    lyrics_assemble_corpus.add_argument("--plan", type=Path, required=True)
    lyrics_assemble_corpus.add_argument("--consolidation-report", type=Path, required=True)
    lyrics_release_corpus = lyrics_actions.add_parser(
        "build-corpus-release",
        help="compose clean corpus assignments with retained optional media as an inactive release",
    )
    lyrics_release_corpus.add_argument("--workspace", default=os.environ.get("FLUENCY_WORKSPACE"))
    lyrics_release_corpus.add_argument("--assembly", type=Path, required=True)
    lyrics_release_corpus.add_argument("--parity-release", type=Path, required=True)
    lyrics_release_corpus.add_argument("--release-id", required=True)
    lyrics_plan_processing = lyrics_actions.add_parser(
        "plan-processing-profile",
        help="pin shared and artist-specific inputs for one exact corpus processing run",
    )
    lyrics_plan_processing.add_argument("--workspace", default=os.environ.get("FLUENCY_WORKSPACE"))
    lyrics_plan_processing.add_argument("--plan", type=Path, required=True)
    lyrics_plan_processing.add_argument("--config", type=Path, required=True)
    lyrics_plan_processing.add_argument("--source-repository", type=Path, required=True)
    lyrics_plan_processing.add_argument("--profile-id", required=True)
    lyrics_ingest = lyrics_actions.add_parser(
        "ingest-legacy-genius",
        help="pin and normalize one song from a legacy Genius batch",
    )
    lyrics_ingest.add_argument(
        "--workspace", default=os.environ.get("FLUENCY_WORKSPACE")
    )
    lyrics_ingest.add_argument("--source-batch", type=Path, required=True)
    lyrics_ingest.add_argument("--translations", type=Path)
    lyrics_ingest.add_argument("--source-record-id", required=True)
    lyrics_ingest.add_argument("--snapshot-id", required=True)
    lyrics_ingest.add_argument("--run-id", required=True)
    lyrics_ingest.add_argument("--language", required=True)
    lyrics_ingest.add_argument("--artist-id", required=True)
    lyrics_ingest.add_argument("--artist-name", required=True)
    lyrics_ingest.add_argument("--translation-language", default="en")
    lyrics_process = lyrics_actions.add_parser(
        "process",
        help="tokenize, normalize, restore elisions, and route one source run",
    )
    lyrics_process.add_argument(
        "--workspace", default=os.environ.get("FLUENCY_WORKSPACE")
    )
    lyrics_process.add_argument("--run-id", required=True)
    lyrics_process.add_argument("--language", required=True)
    lyrics_process.add_argument("--elision-mapping", type=Path, required=True)
    lyrics_process.add_argument("--multi-word-elisions", type=Path, required=True)
    lyrics_process.add_argument("--known-forms", type=Path, required=True)
    lyrics_process.add_argument("--frequency-snapshot", type=Path, required=True)
    lyrics_process.add_argument("--lexeme-register", type=Path, required=True)
    lyrics_process.add_argument("--routing-snapshot", type=Path, required=True)
    lyrics_process.add_argument("--routing-mode", choices=("snapshot", "live"), default="snapshot")
    lyrics_process.add_argument("--english-frequency", type=Path)
    lyrics_process.add_argument("--english-loanwords", type=Path)
    lyrics_process.add_argument("--conjugation-reverse", type=Path)
    lyrics_process.add_argument("--caps-stats", type=Path)
    lyrics_process.add_argument(
        "--routing-overrides",
        type=Path,
        help="optional typed registry; omitted means no human routing overrides",
    )
    lyrics_menu = lyrics_actions.add_parser(
        "menu",
        help="build provider-neutral lexical candidates without running WSD",
    )
    lyrics_menu.add_argument("--workspace", default=os.environ.get("FLUENCY_WORKSPACE"))
    lyrics_menu.add_argument("--run-id", required=True)
    lyrics_menu.add_argument("--language", required=True)
    lyrics_menu.add_argument("--dictionary-snapshot", type=Path, required=True)
    lyrics_menu.add_argument("--snapshot-id", required=True)
    lyrics_menu.add_argument("--language-policy", required=True)
    lyrics_wsd_prepare = lyrics_actions.add_parser(
        "wsd-prepare",
        help="materialize exact WSD contexts and eligibility without executing a model",
    )
    lyrics_wsd_prepare.add_argument("--workspace", default=os.environ.get("FLUENCY_WORKSPACE"))
    lyrics_wsd_prepare.add_argument("--run-id", required=True)
    lyrics_wsd_prepare.add_argument("--language", required=True)
    lyrics_wsd_import = lyrics_actions.add_parser(
        "wsd-import", help="validate and publish one complete occurrence-level WSD result bundle",
    )
    lyrics_wsd_import.add_argument("--workspace", default=os.environ.get("FLUENCY_WORKSPACE"))
    lyrics_wsd_import.add_argument("--run-id", required=True)
    lyrics_wsd_import.add_argument("--language", required=True)
    lyrics_wsd_import.add_argument("--bundle", type=Path, required=True)
    lyrics_wsd_execute = lyrics_actions.add_parser(
        "wsd-execute", help="run one explicitly pinned WSD method into a raw complete-result bundle",
    )
    lyrics_wsd_execute.add_argument("--workspace", default=os.environ.get("FLUENCY_WORKSPACE"))
    lyrics_wsd_execute.add_argument("--run-id", required=True)
    lyrics_wsd_execute.add_argument("--language", required=True, choices=("es",))
    lyrics_wsd_execute.add_argument(
        "--method", required=True, choices=("es-sd-beto-cal-v5-migration-v1",),
    )
    lyrics_wsd_execute.add_argument(
        "--env-file", type=Path,
        help="optional dotenv file read as data for GEMINI_API_KEY; it is never executed",
    )
    lyrics_consolidate = lyrics_actions.add_parser(
        "consolidate",
        help="group exact WSD results into auditable surface cards, examples, and dispositions",
    )
    lyrics_consolidate.add_argument("--workspace", default=os.environ.get("FLUENCY_WORKSPACE"))
    lyrics_consolidate.add_argument("--run-id", required=True)
    lyrics_consolidate.add_argument("--language", required=True)
    lyrics_consolidate.add_argument("--example-cap-per-sense", type=int, default=12)
    lyrics_consolidate.add_argument("--translation-language", default="en")
    lyrics_assemble = lyrics_actions.add_parser(
        "assemble-app",
        help="render an inactive clean consolidation into the existing split Artist app contract",
    )
    lyrics_assemble.add_argument("--workspace", default=os.environ.get("FLUENCY_WORKSPACE"))
    lyrics_assemble.add_argument("--run-id", required=True)
    lyrics_assemble.add_argument("--language", required=True)
    lyrics_assemble.add_argument("--artist-slug", required=True)
    lyrics_assemble.add_argument("--comparison-release", type=Path)
    lyrics_preview = lyrics_actions.add_parser(
        "build-preview-release",
        help="package one clean app assembly as a validated inactive Lyrics release",
    )
    lyrics_preview.add_argument("--workspace", default=os.environ.get("FLUENCY_WORKSPACE"))
    lyrics_preview.add_argument("--run-id", required=True)
    lyrics_preview.add_argument("--language", required=True)
    lyrics_preview.add_argument("--artist-slug", required=True)
    lyrics_preview.add_argument("--release-id", required=True)
    lyrics_preview.add_argument("--parity-release", type=Path, required=True)
    lyrics_preview.add_argument("--song-source-id", required=True)

    release = subparsers.add_parser("release", help="compose, inspect, validate, and activate exact releases")
    release_actions = release.add_subparsers(dest="release_command", required=True)
    for action in ("list", "catalog"):
        action_parser = release_actions.add_parser(action)
        action_parser.add_argument("--workspace", default=os.environ.get("FLUENCY_WORKSPACE"))
        action_parser.add_argument("--language", default="fr")
        action_parser.add_argument("--mode", default="speech")
    validate = release_actions.add_parser("validate")
    validate.add_argument("release_id")
    validate.add_argument("--workspace", default=os.environ.get("FLUENCY_WORKSPACE"))
    validate.add_argument("--language", default="fr")
    validate.add_argument("--mode", default="speech")
    activate = release_actions.add_parser("activate")
    activate.add_argument("release_id")
    activate.add_argument("--workspace", default=os.environ.get("FLUENCY_WORKSPACE"))
    activate.add_argument("--language", default="fr")
    activate.add_argument("--mode", default="speech")
    compose = release_actions.add_parser("compose")
    compose.add_argument("--workspace", default=os.environ.get("FLUENCY_WORKSPACE"))
    compose.add_argument("--composition", type=Path, required=True, help="exact release-composition JSON")
    compose.add_argument("--deck", type=Path, required=True, help="already assembled compact deck JSON")

    pipeline = subparsers.add_parser("pipeline", help="plan clean, auditable data runs")
    pipeline_actions = pipeline.add_subparsers(dest="pipeline_command", required=True)
    pipeline_plan = pipeline_actions.add_parser(
        "plan", help="create a non-executing run skeleton from an exact profile"
    )
    pipeline_plan.add_argument(
        "--workspace", default=os.environ.get("FLUENCY_WORKSPACE")
    )
    pipeline_plan.add_argument("--profile", type=Path, required=True)
    pipeline_harvest = pipeline_actions.add_parser(
        "harvest", help="harvest explicit corpus snapshots into one planned run"
    )
    pipeline_harvest.add_argument(
        "--workspace", default=os.environ.get("FLUENCY_WORKSPACE")
    )
    pipeline_harvest.add_argument("--run-id", required=True)
    pipeline_harvest.add_argument("--language", default="fr")
    pipeline_harvest.add_argument("--mode", default="speech")
    pipeline_harvest.add_argument(
        "--source",
        action="append",
        required=True,
        metavar="NAME=PATH",
        help="explicit source snapshot inside workspace/raw; repeat for an explicit union",
    )
    pipeline_inventory = pipeline_actions.add_parser(
        "inventory", help="build a surface-only inventory from one explicit ranked snapshot"
    )
    pipeline_inventory.add_argument(
        "--workspace", default=os.environ.get("FLUENCY_WORKSPACE")
    )
    pipeline_inventory.add_argument("--run-id", required=True)
    pipeline_inventory.add_argument("--language", default="fr")
    pipeline_inventory.add_argument("--mode", default="speech")
    pipeline_inventory.add_argument(
        "--snapshot", type=Path, required=True,
        help="ranked file or compiled snapshot directory inside workspace/raw",
    )
    pipeline_inventory.add_argument(
        "--snapshot-id", required=True,
        help="explicit upstream snapshot label, such as lexique-4.00-2026-02-10",
    )
    pipeline_sense_menu = pipeline_actions.add_parser(
        "sense-menu", help="normalize one explicit dictionary snapshot into a planned run"
    )
    pipeline_sense_menu.add_argument(
        "--workspace", default=os.environ.get("FLUENCY_WORKSPACE")
    )
    pipeline_sense_menu.add_argument("--run-id", required=True)
    pipeline_sense_menu.add_argument("--language", default="fr")
    pipeline_sense_menu.add_argument("--mode", default="speech")
    pipeline_sense_menu.add_argument(
        "--snapshot", type=Path, required=True,
        help="provider snapshot file or directory inside workspace/raw",
    )
    pipeline_sense_menu.add_argument(
        "--snapshot-id", required=True,
        help="explicit snapshot label, such as enwiktionary-2026-08-05",
    )
    pipeline_wsd_import = pipeline_actions.add_parser(
        "wsd-import",
        help="validate and publish one complete external WSD assignment bundle",
    )
    pipeline_wsd_import.add_argument(
        "--workspace", default=os.environ.get("FLUENCY_WORKSPACE")
    )
    pipeline_wsd_import.add_argument("--run-id", required=True)
    pipeline_wsd_import.add_argument("--language", default="fr")
    pipeline_wsd_import.add_argument("--mode", default="speech")
    pipeline_wsd_import.add_argument(
        "--bundle",
        type=Path,
        required=True,
        help="complete assignment bundle under workspace/raw/wsd",
    )
    pipeline_run_release = pipeline_actions.add_parser(
        "build-run-release",
        help="build an inactive real-data release with explicit unassigned examples",
    )
    pipeline_run_release.add_argument(
        "--workspace", default=os.environ.get("FLUENCY_WORKSPACE")
    )
    pipeline_run_release.add_argument("--run-id", required=True)
    pipeline_run_release.add_argument("--release-id", required=True)
    pipeline_run_release.add_argument("--language", default="fr")
    pipeline_run_release.add_argument("--mode", default="speech")
    pipeline_run_release.add_argument(
        "--conjugations-artifact",
        help="exact optional conjugation-layer/v1 artifact ID",
    )

    identity = subparsers.add_parser(
        "identity", help="audit and build explicit card/progress identity mappings"
    )
    identity_actions = identity.add_subparsers(
        dest="identity_command", required=True
    )
    crosswalk = identity_actions.add_parser(
        "crosswalk", help="build an immutable flat legacy progress-alias report"
    )
    crosswalk.add_argument(
        "--workspace", default=os.environ.get("FLUENCY_WORKSPACE")
    )
    crosswalk.add_argument("--migration-id", required=True)
    crosswalk.add_argument("--language", required=True)
    crosswalk.add_argument("--mode", default="speech")
    crosswalk.add_argument("--inventory", type=Path, required=True)
    crosswalk.add_argument(
        "--legacy-index", type=Path, action="append", required=True
    )
    crosswalk.add_argument("--legacy-migration", type=Path, required=True)
    return parser


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


def handle_workspace(command: str, raw_path: str | None) -> int:
    path = _workspace_path(raw_path)
    if command == "init":
        workspace = Workspace.initialize(path)
        print(f"Initialized Fluency workspace: {workspace.root}")
        print(f"Workspace ID: {workspace.workspace_id}")
        return 0

    workspace = Workspace.load(path)
    if command == "show":
        record = {"path": str(workspace.root), **workspace.to_dict()}
        print(json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if command == "doctor":
        diagnostics = workspace.doctor(code_root=project_root())
        for diagnostic in diagnostics:
            marker = "OK" if diagnostic.ok else "FAIL"
            print(f"[{marker}] {diagnostic.name}: {diagnostic.detail}")
        return 0 if all(item.ok for item in diagnostics) else 1
    raise AssertionError(f"Unhandled workspace command: {command}")


def handle_pilot(command: str, raw_workspace: str | None) -> int:
    workspace = Workspace.load(_workspace_path(raw_workspace))
    if command == "build":
        release_directory = build_pilot_release(workspace)
        print(f"Published French Speech pilot: {release_directory}")
        print("Cards: 25")
        print("WSD: disabled (curated fixture)")
        return 0
    raise AssertionError(f"Unhandled pilot command: {command}")


def handle_release(args: argparse.Namespace) -> int:
    workspace = Workspace.load(_workspace_path(args.workspace))
    if args.release_command == "compose":
        directory = compose_release(workspace, load_json_object(args.composition), load_json_object(args.deck))
        print(f"Composed immutable candidate: {directory}")
        print("Activation unchanged. Validate, then run `fluency release activate ...`.")
        return 0
    if args.release_command == "validate":
        directory = workspace.root / "releases" / args.language / args.mode / args.release_id
        manifest, _, composition = validate_release_bundle(directory)
        print(f"Valid release: {manifest['release_id']}")
        print(f"Layers: {', '.join(sorted(composition['layers']))}")
        return 0
    if args.release_command == "activate":
        path = activate_release(workspace, args.language, args.mode, args.release_id)
        print(f"Activated release: {args.release_id}")
        print(f"Pointer: {path}")
        return 0
    if args.release_command == "catalog":
        path = write_catalog(workspace, args.language, args.mode)
        print(f"Wrote release catalog: {path}")
        return 0
    if args.release_command == "list":
        catalog = build_catalog(workspace, args.language, args.mode)
        for candidate in catalog["candidates"]:
            marker = "*" if candidate["active"] else " "
            print(f"{marker} {candidate['release_id']}  {candidate['card_count']} cards  WSD={candidate['wsd_status']}  fallbacks={candidate['fallback_layers']}")
        return 0
    raise AssertionError(f"Unhandled release command: {args.release_command}")


def handle_frequency(args: argparse.Namespace) -> int:
    workspace = Workspace.load(_workspace_path(args.workspace))
    if args.frequency_command == "compile-corpus":
        def progress(state: dict[str, int]) -> None:
            gib = state["source_bytes"] / (1024 ** 3)
            print(
                f"Scanned {state['source_lines']:,} lines / {gib:.2f} GiB; "
                f"{state['total_tokens']:,} tokens; "
                f"{state['unique_surfaces']:,} surfaces",
                flush=True,
            )

        output = compile_corpus_frequency_snapshot(
            project_root(),
            workspace,
            language=args.language,
            corpus_path=args.corpus,
            snapshot_id=args.snapshot_id,
            provider=args.provider,
            progress_callback=progress,
        )
        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        print(f"Compiled immutable corpus-frequency snapshot: {output}")
        print(
            f"Counted {manifest['total_tokens']:,} tokens across "
            f"{manifest['source_lines']:,} lines and "
            f"{manifest['unique_surfaces']:,} surfaces."
        )
        print("No pipeline run, WSD, release build, or activation was performed.")
        return 0
    raise AssertionError(f"Unhandled frequency command: {args.frequency_command}")


def handle_migration(args: argparse.Namespace) -> int:
    workspace = Workspace.load(_workspace_path(args.workspace))
    if args.migration_command == "spanish-retained-assets":
        targets = migrate_spanish_retained_assets(
            workspace,
            source_repository=args.source_repository,
        )
        print("Pinned approved Spanish retained assets:")
        for family, path in targets.items():
            print(f"  {family}: {path}")
        print("No WSD assignments, example selections, deck output, or release was migrated.")
        return 0
    if args.migration_command == "spanish-dictionary-snapshot":
        target = migrate_spanish_dictionary_snapshot(
            workspace,
            source_repository=args.source_repository,
        )
        print(f"Pinned offline SpanishDict snapshot: {target}")
        print("No built menu, WSD assignment, example selection, deck, or release was migrated.")
        return 0
    if args.migration_command == "spanish-wsd-assets":
        targets = migrate_spanish_wsd_assets(
            workspace, source_repository=args.source_repository,
        )
        print("Pinned exact Spanish WSD reproduction assets:")
        for family, path in targets.items():
            print(f"  {family}: {path}")
        print("No token vectors, assignments, deck, release, or activation was migrated.")
        return 0
    if args.migration_command == "spanish-jehle-snapshot":
        target = pin_jehle_snapshot(
            workspace,
            source=args.source,
            snapshot_id=args.snapshot_id,
        )
        print(f"Pinned recovered Jehle conjugation source: {target}")
        print("No old conjugation table, WSD assignment, deck, or release was migrated.")
        return 0
    raise AssertionError(f"Unhandled migration command: {args.migration_command}")


def handle_enrichment(args: argparse.Namespace) -> int:
    workspace = Workspace.load(_workspace_path(args.workspace))
    if args.enrichment_command == "build-conjugations":
        metadata, coverage = build_conjugation_layer(
            workspace,
            sense_menu=args.sense_menu,
            source_snapshot=args.source_snapshot,
            locale=args.locale,
        )
        print(f"Built immutable conjugation layer: {metadata.artifact_id}")
        print(
            f"Covered {coverage['covered_headwords']} of "
            f"{coverage['requested_headwords']} requested verb headwords."
        )
        if coverage["missing_headwords"]:
            print("Missing headwords: " + ", ".join(coverage["missing_headwords"]))
        print("No release was composed or activated.")
        return 0
    raise AssertionError(f"Unhandled enrichment command: {args.enrichment_command}")


def handle_deployment(args: argparse.Namespace) -> int:
    workspace = Workspace.load(_workspace_path(args.workspace))
    if args.deployment_command == "build-static":
        speech: dict[str, str] = {}
        for value in args.speech:
            language, separator, release_id = value.partition("=")
            if not separator or not language or not release_id or language in speech:
                raise SystemExit("Each --speech must be one unique LANGUAGE=RELEASE_ID selection")
            speech[language] = release_id
        output = build_static_deployment(
            project_root(), workspace,
            deployment_id=args.deployment_id,
            speech_releases=speech,
            lyrics_release_id=args.lyrics_release,
        )
        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        print(f"Built inactive static deployment candidate: {output}")
        print(
            f"Packaged {manifest['file_count']} hashed files "
            f"({manifest['total_bytes']} bytes) from exact Speech and Lyrics releases."
        )
        print("Backend secrets, development docs and the lineage explorer were excluded.")
        print("Nothing was deployed and no active release changed.")
        return 0
    raise AssertionError(f"Unhandled deployment command: {args.deployment_command}")


def handle_artist(args: argparse.Namespace) -> int:
    workspace = Workspace.load(_workspace_path(args.workspace))
    if args.artist_command == "build-catalog-release":
        output = build_lyrics_catalog_release(
            workspace,
            source_repository=args.source_repository,
            release_id=args.release_id,
        )
        manifest, _ = validate_lyrics_release(output)
        print(f"Built immutable Lyrics catalog release: {output}")
        print(
            f"Frozen {manifest['artist_count']} artist sources across "
            f"{', '.join(manifest['languages'])}; {manifest['card_count']} source-card rows."
        )
        print("Historical materialized assignments were retained explicitly for product parity.")
        print("No Artist pipeline, model, Google Sheet, or release activation was run.")
        return 0
    release_directory = workspace.root / "releases/lyrics" / args.release_id
    if args.artist_command == "validate":
        manifest, _ = validate_lyrics_release(release_directory)
        print(
            f"Valid Lyrics release {manifest['release_id']}: "
            f"{manifest['artist_count']} artists, {manifest['card_count']} source-card rows."
        )
        return 0
    if args.artist_command == "activate":
        active = activate_lyrics_release(workspace, args.release_id)
        print(f"Activated local Lyrics catalog: {active}")
        return 0
    raise AssertionError(f"Unhandled artist command: {args.artist_command}")


def handle_lyrics(args: argparse.Namespace) -> int:
    workspace = Workspace.load(_workspace_path(args.workspace))
    if args.lyrics_command == "plan-corpus":
        output = build_lyrics_corpus_plan(
            workspace, config_path=args.config,
            source_repository=args.source_repository, plan_id=args.plan_id,
        )
        manifest = json.loads(output.read_text(encoding="utf-8"))
        totals = manifest["totals"]
        print(f"Pinned immutable Lyrics corpus plan: {output}")
        print(
            f"Selected {totals['songs']} songs from {totals['included_artist_sources']} "
            f"artist sources across {totals['source_files']} exact files."
        )
        print(
            f"Recorded {len(manifest['excluded_sources'])} explicit exclusions and "
            f"{totals['cross_source_collisions']} artist-scoped source collisions."
        )
        print("No song run, routing, WSD, deck, release, or activation was executed.")
        return 0
    if args.lyrics_command == "ingest-corpus":
        def show_progress(event: dict) -> None:
            if event["completed"] == 1 or event["completed"] % 25 == 0 or event["completed"] == event["planned"]:
                print(
                    f"Source ingest {event['completed']}/{event['planned']}: "
                    f"{event['artist_slug']} song {event['source_record_id']} ({event['action']})",
                    flush=True,
                )

        result = ingest_lyrics_corpus_plan(workspace, plan_path=args.plan, progress=show_progress)
        print(f"Completed exact Lyrics corpus source ingest: {result['report_path']}")
        print(
            f"Verified {result['song_run_count']} immutable song runs: "
            f"created {result['created_this_invocation']}, "
            f"resumed/skipped {result['skipped_this_invocation']}."
        )
        print("No token routing, WSD, deck assembly, release build, or activation was run.")
        return 0
    if args.lyrics_command == "process-corpus":
        def show_processing_progress(event: dict) -> None:
            if event["completed"] == 1 or event["completed"] % 25 == 0 or event["completed"] == event["planned"]:
                print(
                    f"Lyrics processing {event['completed']}/{event['planned']}: "
                    f"{event['artist_slug']} song {event['source_record_id']} ({event['action']})",
                    flush=True,
                )

        result = process_lyrics_corpus_plan(
            workspace,
            plan_path=args.plan,
            profile_path=args.profile,
            progress=show_processing_progress,
        )
        print(f"Completed exact Lyrics corpus processing: {result['report_path']}")
        print(
            f"Verified {result['song_run_count']} immutable processing stages: "
            f"created {result['created_this_invocation']}, "
            f"resumed/skipped {result['skipped_this_invocation']}."
        )
        print("No lexical menu, WSD, deck assembly, release build, or activation was run.")
        return 0
    if args.lyrics_command == "menu-corpus":
        def show_menu_progress(event: dict) -> None:
            if event["completed"] == 1 or event["completed"] % 25 == 0 or event["completed"] == event["planned"]:
                print(
                    f"Lyrics menu {event['completed']}/{event['planned']}: "
                    f"{event['artist_slug']} song {event['source_record_id']} ({event['action']})",
                    flush=True,
                )

        result = build_lyrics_corpus_lexical_menus(
            project_root(),
            workspace,
            plan_path=args.plan,
            dictionary_snapshot=args.dictionary_snapshot,
            snapshot_id=args.snapshot_id,
            language_policy_id=args.language_policy,
            menu_id=args.menu_id,
            progress=show_menu_progress,
        )
        print(f"Completed exact Lyrics corpus lexical menus: {result['report_path']}")
        print(
            f"Verified {result['song_run_count']} immutable song menus over "
            f"{result['lookup_form_count']} shared lookup forms: "
            f"created {result['created_this_invocation']}, "
            f"resumed/skipped {result['skipped_this_invocation']}."
        )
        print("No sense was assigned; no deck, release, or activation was created.")
        return 0
    if args.lyrics_command == "wsd-prepare-corpus":
        def show_wsd_prepare_progress(event: dict) -> None:
            if event["completed"] == 1 or event["completed"] % 25 == 0 or event["completed"] == event["planned"]:
                print(
                    f"Lyrics WSD preparation {event['completed']}/{event['planned']}: "
                    f"{event['artist_slug']} song {event['source_record_id']} ({event['action']})",
                    flush=True,
                )

        result = prepare_lyrics_corpus_wsd(
            project_root(), workspace,
            plan_path=args.plan,
            lexical_report_path=args.lexical_report,
            progress=show_wsd_prepare_progress,
        )
        print(f"Completed exact corpus WSD preparation: {result['report_path']}")
        print(
            f"Verified {result['request_count']} requests across {result['song_run_count']} songs; "
            f"{result['executable_request_count']} are executable. "
            f"Created {result['created_this_invocation']}, "
            f"resumed/skipped {result['skipped_this_invocation']}."
        )
        print("No WSD method ran; no assignment, deck, release, or activation was created.")
        return 0
    if args.lyrics_command == "wsd-import-corpus":
        def show_wsd_import_progress(event: dict) -> None:
            if event["completed"] == 1 or event["completed"] % 25 == 0 or event["completed"] == event["planned"]:
                print(
                    f"Lyrics WSD import {event['completed']}/{event['planned']}: "
                    f"{event['artist_slug']} song {event['source_record_id']} ({event['action']})",
                    flush=True,
                )

        result = import_lyrics_corpus_results(
            project_root(), workspace,
            plan_path=args.plan,
            preparation_report_path=args.preparation_report,
            catalog_path=args.catalog,
            progress=show_wsd_import_progress,
        )
        print(f"Completed exact corpus WSD result import: {result['report_path']}")
        print(
            f"Verified {result['result_count']} results across {result['song_run_count']} songs "
            f"from method {result['method_profile_id']}: "
            f"created {result['created_this_invocation']}, "
            f"resumed/skipped {result['skipped_this_invocation']}."
        )
        print("No consolidation, app assembly, release, or activation was created.")
        return 0
    if args.lyrics_command == "consolidate-corpus":
        def show_consolidation_progress(event: dict) -> None:
            if event["completed"] == 1 or event["completed"] % 25 == 0 or event["completed"] == event["planned"]:
                print(
                    f"Lyrics consolidation {event['completed']}/{event['planned']}: "
                    f"{event['artist_slug']} song {event['source_record_id']} ({event['action']})",
                    flush=True,
                )

        result = consolidate_lyrics_corpus(
            project_root(), workspace,
            plan_path=args.plan,
            wsd_import_report_path=args.wsd_import_report,
            example_cap_per_sense=args.example_cap_per_sense,
            translation_language=args.translation_language,
            progress=show_consolidation_progress,
        )
        print(f"Completed exact corpus consolidation: {result['report_path']}")
        print(
            f"Verified {result['song_run_count']} song consolidations with "
            f"{result['assigned_example_count']} assigned occurrence examples and "
            f"{result['selected_example_count']} selected examples: "
            f"created {result['created_this_invocation']}, "
            f"resumed/skipped {result['skipped_this_invocation']}."
        )
        print("No app assembly, release, deployment, or activation was created.")
        return 0
    if args.lyrics_command == "assemble-corpus":
        def show_assembly_progress(event: dict) -> None:
            if event["completed"] == 1 or event["completed"] % 25 == 0 or event["completed"] == event["planned"]:
                print(
                    f"Lyrics app assembly {event['completed']}/{event['planned']}: "
                    f"{event['artist_slug']} song {event['source_record_id']} ({event['action']})",
                    flush=True,
                )

        result = assemble_lyrics_corpus(
            project_root(), workspace, plan_path=args.plan,
            consolidation_report_path=args.consolidation_report,
            progress=show_assembly_progress,
        )
        print(f"Completed clean multi-artist app assembly: {result['assembly_path']}")
        print(
            f"Built {result['artist_count']} artists, {result['language_card_count']} shared "
            f"surface cards and {result['selected_example_count']} selected examples: "
            f"created {result['created_this_invocation']}, "
            f"resumed/skipped {result['skipped_this_invocation']} song assemblies."
        )
        print("No release, deployment, or activation was created.")
        return 0
    if args.lyrics_command == "build-corpus-release":
        output = build_clean_lyrics_corpus_release(
            workspace, assembly_path=args.assembly,
            parity_release=args.parity_release, release_id=args.release_id,
        )
        manifest, _composition = validate_lyrics_release(output)
        comparison = json.loads((output / "comparison.json").read_text(encoding="utf-8"))
        print(f"Built validated inactive clean Lyrics release: {output}")
        print(
            f"Packaged {manifest['artist_count']} artists and {manifest['card_count']} artist-card rows; "
            f"comparison found {comparison['totals']['cards_added']} added and "
            f"{comparison['totals']['cards_removed']} removed cards."
        )
        print("The active Lyrics release was not changed.")
        return 0
    if args.lyrics_command == "plan-processing-profile":
        output = build_lyrics_corpus_processing_profile(
            workspace,
            plan_path=args.plan,
            config_path=args.config,
            source_repository=args.source_repository,
            profile_id=args.profile_id,
        )
        profile = json.loads(output.read_text(encoding="utf-8"))
        print(f"Pinned immutable Lyrics processing profile: {output}")
        print(
            f"Selected {len(profile['shared_inputs'])} shared inputs and "
            f"{sum(len(value) for value in profile['artist_inputs'].values())} "
            f"artist-specific inputs across {len(profile['artist_inputs'])} sources."
        )
        print("No song processing, lexical menu, WSD, deck, release, or activation was run.")
        return 0
    if args.lyrics_command == "ingest-legacy-genius":
        output = ingest_legacy_genius_song(
            workspace,
            source_batch=args.source_batch,
            translations_path=args.translations,
            source_record_id=args.source_record_id,
            snapshot_id=args.snapshot_id,
            run_id=args.run_id,
            language=args.language,
            artist_id=args.artist_id,
            artist_name=args.artist_name,
            translation_language=args.translation_language,
        )
        report = json.loads((output / "report.json").read_text(encoding="utf-8"))
        print(f"Completed immutable Lyrics source ingest: {output}")
        print(
            f"Pinned {report['line_count']} source lines, "
            f"{report['alignment_count']} optional translations, and "
            f"{report['lineage_event_count']} lineage events."
        )
        if report["unaligned_line_count"]:
            print(
                f"Graceful degradation: {report['unaligned_line_count']} lines have no "
                "translation and remain valid source lines."
            )
        print("No token routing, WSD, deck assembly, release build, or activation was run.")
        return 0
    if args.lyrics_command == "process":
        output = process_lyrics_run(
            workspace,
            run_id=args.run_id,
            language=args.language,
            elision_mapping=args.elision_mapping,
            multi_word_elisions=args.multi_word_elisions,
            known_forms=args.known_forms,
            frequency_snapshot=args.frequency_snapshot,
            lexeme_register=args.lexeme_register,
            routing_snapshot=args.routing_snapshot,
            routing_mode=args.routing_mode,
            english_frequency=args.english_frequency,
            english_loanwords=args.english_loanwords,
            conjugation_reverse=args.conjugation_reverse,
            caps_stats=args.caps_stats,
            routing_overrides=args.routing_overrides,
        )
        report = json.loads((output / "report.json").read_text(encoding="utf-8"))
        print(f"Completed immutable Lyrics processing layer: {output}")
        print(
            f"Tokenized {report['occurrence_count']} occurrences into "
            f"{report['analysis_unit_count']} analysis units; emitted "
            f"{report['lineage_event_count']} lineage events."
        )
        if report["routing_provenance"] == "direct":
            print(
                "Normalization, elision restoration, and routing were recomputed directly; "
                "the pinned migration snapshot was used only for comparison."
            )
            print("Route comparison: " + json.dumps(report["route_comparison"], sort_keys=True))
        else:
            print(
                "Normalization and elision restoration were recomputed directly; "
                "routing is explicitly sourced from the pinned migration snapshot."
            )
        print("No WSD, deck assembly, release build, or activation was run.")
        return 0
    if args.lyrics_command == "menu":
        output = build_lyrics_lexical_menu_stage(
            project_root(),
            workspace,
            run_id=args.run_id,
            language=args.language,
            dictionary_snapshot=args.dictionary_snapshot,
            snapshot_id=args.snapshot_id,
            language_policy_id=args.language_policy,
        )
        report = json.loads((output / "report.json").read_text(encoding="utf-8"))
        print(f"Completed immutable Lyrics lexical-menu layer: {output}")
        print(
            f"Emitted {report['candidate_count']} occurrence-bound candidates: "
            + ", ".join(
                f"{status}={count}"
                for status, count in report["status_counts"].items()
            )
            + "."
        )
        print(
            f"Provider menu contains {report['ready_analysis_count']} analyses and "
            f"{report['ready_sense_count']} sense leaves."
        )
        print("No sense was assigned; no deck, release, or activation was created.")
        return 0
    if args.lyrics_command == "wsd-prepare":
        output = prepare_lyrics_wsd_stage(
            project_root(),
            workspace,
            run_id=args.run_id,
            language=args.language,
        )
        report = json.loads((output / "report.json").read_text(encoding="utf-8"))
        print(f"Completed immutable Lyrics WSD preparation: {output}")
        print(
            f"Prepared {report['request_count']} complete target records; "
            f"{report['executable_request_count']} are executable and "
            f"{report['translation_available_count']} have optional aligned translations."
        )
        print("No WSD model ran; no assignment, deck, release, or activation was created.")
        return 0
    if args.lyrics_command == "wsd-import":
        output = import_lyrics_wsd_results(
            project_root(), workspace, run_id=args.run_id,
            language=args.language, bundle_path=args.bundle,
        )
        report = json.loads((output / "report.json").read_text(encoding="utf-8"))
        counts = report["result_counts"]
        print(f"Published complete immutable Lyrics WSD results: {output}")
        print(", ".join(f"{status}={count}" for status, count in counts.items()))
        print("No deck, release, or activation was created.")
        return 0
    if args.lyrics_command == "wsd-execute":
        output = execute_spanish_v5_lyrics(
            project_root(), workspace, run_id=args.run_id, env_file=args.env_file,
        )
        print(f"Created complete raw Lyrics WSD result bundle: {output}")
        print("The result is inactive; run lyrics wsd-import only after validation.")
        return 0
    if args.lyrics_command == "consolidate":
        output = consolidate_lyrics_run(
            project_root(), workspace, run_id=args.run_id, language=args.language,
            example_cap_per_sense=args.example_cap_per_sense,
            translation_language=args.translation_language,
        )
        report = json.loads((output / "report.json").read_text(encoding="utf-8"))
        print(f"Completed immutable Lyrics occurrence consolidation: {output}")
        print(
            f"Built {report['study_card_count']} surface cards from "
            f"{report['assigned_example_count']} assigned occurrences; "
            f"selected {report['selected_example_count']} examples under the explicit cap policy."
        )
        print(
            f"Retained {report['non_study_disposition_count']} non-study outcomes as auditable dispositions."
        )
        print("No app assets, release, or activation were created.")
        return 0
    if args.lyrics_command == "assemble-app":
        output = assemble_lyrics_app_stage(
            project_root(), workspace, run_id=args.run_id, language=args.language,
            artist_slug=args.artist_slug, comparison_release=args.comparison_release,
        )
        report = json.loads((output / "report.json").read_text(encoding="utf-8"))
        print(f"Completed inactive Lyrics app assembly: {output}")
        print(
            f"Rendered {report['card_count']} cards and {report['example_count']} selected examples "
            f"into the exact split index/examples/master contract."
        )
        if report["comparison"]["status"] == "compared":
            print(
                f"Parity comparison: {report['comparison']['surface_words_already_in_parity']} clean surfaces already exist; "
                f"selected-example delta {report['comparison']['selected_example_delta']:+d}."
            )
        print("No release was composed or activated.")
        return 0
    if args.lyrics_command == "build-preview-release":
        output = build_clean_lyrics_preview_release(
            workspace, run_id=args.run_id, language=args.language,
            artist_slug=args.artist_slug, release_id=args.release_id,
            parity_release=args.parity_release, song_source_id=args.song_source_id,
        )
        manifest, _composition = validate_lyrics_release(output)
        comparison = json.loads((output / "comparison.json").read_text(encoding="utf-8"))
        print(f"Built validated inactive Lyrics preview release: {output}")
        print(
            f"Packaged {manifest['card_count']} cards across {len(manifest['files'])} exact app files "
            f"({comparison['payload_bytes']} bytes)."
        )
        print("The active Lyrics release was not changed.")
        return 0
    raise AssertionError(f"Unhandled lyrics command: {args.lyrics_command}")


def handle_pipeline(args: argparse.Namespace) -> int:
    workspace = Workspace.load(_workspace_path(args.workspace))
    if args.pipeline_command == "plan":
        profile = load_pipeline_profile(args.profile)
        run_directory = create_pipeline_plan(workspace, profile)
        target = (
            profile["scope"]["surface_limit"]
            * profile["scope"]["examples_per_surface"]
        )
        print(f"Created fresh pipeline skeleton: {run_directory}")
        print(
            f"Audit target: {profile['scope']['surface_limit']} surface cards, "
            f"{profile['scope']['examples_per_surface']} examples each ({target} total)"
        )
        print("No data stages were executed and no release was activated.")
        return 0
    if args.pipeline_command == "inventory":
        output = build_inventory_stage(
            project_root(),
            workspace,
            run_id=args.run_id,
            language=args.language,
            mode=args.mode,
            frequency_snapshot=args.snapshot,
            snapshot_id=args.snapshot_id,
        )
        report = json.loads((output / "report.json").read_text(encoding="utf-8"))
        print(f"Completed immutable surface inventory: {output}")
        print(
            f"Selected {report['inventory_surfaces']} cards from "
            f"{report['accepted_unique_surfaces']} ranked surfaces "
            f"({report['source_adapter']})."
        )
        print("No lemma data, sentence harvesting, WSD, release build, or activation was run.")
        return 0
    if args.pipeline_command == "harvest":
        snapshots: dict[str, Path] = {}
        for raw_source in args.source:
            name, separator, raw_path = raw_source.partition("=")
            if not separator or not name or not raw_path:
                raise SystemExit("Each --source must have the form NAME=PATH")
            if name in snapshots:
                raise SystemExit(f"Duplicate --source name: {name}")
            snapshots[name] = Path(raw_path)
        output = harvest_run_stage(
            project_root(),
            workspace,
            run_id=args.run_id,
            language=args.language,
            mode=args.mode,
            source_snapshots=snapshots,
        )
        report = json.loads((output / "report.json").read_text(encoding="utf-8"))
        print(f"Completed immutable sentence harvest: {output}")
        print(
            f"Retained {report['retained_candidate_matches']} candidate assignments "
            f"across {len(report['per_surface'])} surfaces."
        )
        if report["release_blocked_by_shortfall"]:
            print(
                f"Release remains blocked: {report['surfaces_with_shortfall']} surfaces "
                "have fewer than three candidates."
            )
        print("No WSD, final example selection, release build, or activation was run.")
        return 0
    if args.pipeline_command == "sense-menu":
        output = build_sense_menu_stage(
            project_root(),
            workspace,
            run_id=args.run_id,
            language=args.language,
            mode=args.mode,
            dictionary_snapshot=args.snapshot,
            snapshot_id=args.snapshot_id,
        )
        report = json.loads((output / "report.json").read_text(encoding="utf-8"))
        print(f"Completed immutable sense-menu build: {output}")
        print(
            f"Built {report['analysis_count']} headword/POS analyses and "
            f"{report['sense_count']} leaves for {report['cards_ready']} cards."
        )
        if report["cards_without_menu"]:
            print(
                f"Review required: {report['cards_without_menu']} cards have no menu; "
                "they remain explicit no_menu cases."
            )
        print("No WSD, example selection, release build, or activation was run.")
        return 0
    if args.pipeline_command == "wsd-import":
        output = import_wsd_assignments(
            workspace,
            run_id=args.run_id,
            language=args.language,
            mode=args.mode,
            bundle_path=args.bundle,
        )
        report = json.loads((output / "report.json").read_text(encoding="utf-8"))
        counts = report["assignment_counts"]
        print(f"Published immutable external WSD assignments: {output}")
        print(
            f"Assigned {counts['assigned']}; rejected {counts['rejected']}; "
            f"abstained {counts['abstained']}; no-menu {counts['no_menu']}."
        )
        print("No example selection, release build, or activation was run.")
        return 0
    if args.pipeline_command == "build-run-release":
        output = build_inactive_run_candidate(
            workspace,
            run_id=args.run_id,
            release_id=args.release_id,
            language=args.language,
            mode=args.mode,
            conjugations_artifact_id=args.conjugations_artifact,
        )
        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        print(f"Built inactive real-data release: {output}")
        print(
            f"Published {manifest['card_count']} cards with explicit unassigned examples."
        )
        if args.conjugations_artifact:
            print(f"Conjugations: {args.conjugations_artifact}")
        print("No WSD was run and the release was not activated.")
        return 0
    raise AssertionError(f"Unhandled pipeline command: {args.pipeline_command}")


def handle_identity(args: argparse.Namespace) -> int:
    workspace = Workspace.load(_workspace_path(args.workspace))
    if args.identity_command == "crosswalk":
        output = write_legacy_crosswalk(
            workspace,
            migration_id=args.migration_id,
            language=args.language,
            mode=args.mode,
            inventory_path=args.inventory,
            legacy_index_paths=args.legacy_index,
            legacy_migration_path=args.legacy_migration,
        )
        report = json.loads((output / "report.json").read_text(encoding="utf-8"))
        counts = report["alias_counts"]
        print(f"Completed immutable progress identity crosswalk: {output}")
        print(
            f"Canonical cards: {report['active_cards']}; resolved aliases: "
            f"{counts.get('resolved', 0)}; ambiguous: {counts.get('ambiguous', 0)}; "
            f"unresolved: {counts.get('unresolved', 0)}."
        )
        print("No source file, Google Sheet row, or active release was modified.")
        return 0
    raise AssertionError(f"Unhandled identity command: {args.identity_command}")


class FluencyRequestHandler(SimpleHTTPRequestHandler):
    """Serve app code plus a read-only release mount from the workspace."""

    def __init__(
        self,
        *args: object,
        directory: str,
        releases_directory: Path,
        **kwargs: object,
    ) -> None:
        self.releases_directory = releases_directory.resolve()
        super().__init__(*args, directory=directory, **kwargs)

    def translate_path(self, path: str) -> str:
        request_path = unquote(urlsplit(path).path)
        active_lyrics_asset = resolve_active_lyrics_asset(
            self.releases_directory, request_path
        )
        if active_lyrics_asset is not None:
            return str(active_lyrics_asset)
        active_app_asset = resolve_active_app_asset(
            self.releases_directory, request_path
        )
        if active_app_asset is not None:
            return str(active_app_asset)
        if not request_path.startswith("/releases/"):
            return super().translate_path(path)

        relative = PurePosixPath(request_path.removeprefix("/releases/"))
        if any(part in {"", ".", ".."} for part in relative.parts):
            return str(self.releases_directory / ".invalid-release-path")
        candidate = self.releases_directory.joinpath(*relative.parts).resolve()
        try:
            candidate.relative_to(self.releases_directory)
        except ValueError:
            return str(self.releases_directory / ".invalid-release-path")
        return str(candidate)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def serve_app(host: str, port: int, raw_workspace: str | None) -> None:
    app_directory = project_root() / "app"
    if not app_directory.is_dir():
        raise SystemExit(f"App directory does not exist: {app_directory}")
    workspace = Workspace.load(_workspace_path(raw_workspace))
    releases_directory = workspace.root / "releases"

    handler = partial(
        FluencyRequestHandler,
        directory=str(app_directory),
        releases_directory=releases_directory,
    )
    server = ThreadingHTTPServer((host, port), handler)
    print(f"Serving Fluency Next from {app_directory}")
    print(f"Mounting releases read-only from {releases_directory}")
    print(f"Open http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping local server")
    finally:
        server.server_close()


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "dev":
        serve_app(args.host, args.port, args.workspace)
        return 0
    if args.command == "workspace":
        return handle_workspace(args.workspace_command, args.path)
    if args.command == "pilot":
        return handle_pilot(args.pilot_command, args.workspace)
    if args.command == "frequency":
        return handle_frequency(args)
    if args.command == "migration":
        return handle_migration(args)
    if args.command == "enrichment":
        return handle_enrichment(args)
    if args.command == "deployment":
        return handle_deployment(args)
    if args.command == "artist":
        return handle_artist(args)
    if args.command == "lyrics":
        return handle_lyrics(args)
    if args.command == "release":
        return handle_release(args)
    if args.command == "pipeline":
        return handle_pipeline(args)
    if args.command == "identity":
        return handle_identity(args)
    raise AssertionError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
