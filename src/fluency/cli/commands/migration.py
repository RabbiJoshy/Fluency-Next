"""The ``fluency migration`` command group."""

from __future__ import annotations

from fluency.cli.shared import *  # noqa: F401,F403
from fluency.cli.shared import (  # noqa: F401
    Path, argparse, json, os, re,
    _workspace_path,  # private names are not re-exported by the star import
)

NAME = "migration"


def register(subparsers) -> None:
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
        print(f"Pinned complete offline SpanishDict menu snapshot: {target}")
        print("No WSD assignment, example selection, deck, or release was migrated.")
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


def handle(args) -> int:
    return handle_migration(args)
