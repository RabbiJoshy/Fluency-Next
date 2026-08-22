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
from fluency.enrichments.conjugations import build_conjugation_layer, pin_jehle_snapshot
from fluency.harvest.runner import harvest_run_stage
from fluency.inventory.corpus_frequency import compile_corpus_frequency_snapshot
from fluency.inventory.runner import build_inventory_stage
from fluency.lyrics.ingest import ingest_legacy_genius_song
from fluency.migration.legacy_identity import write_legacy_crosswalk
from fluency.migration.spanish_assets import migrate_spanish_retained_assets
from fluency.migration.spanish_dictionary import migrate_spanish_dictionary_snapshot
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
