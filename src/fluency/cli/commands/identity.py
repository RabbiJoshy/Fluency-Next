"""The ``fluency identity`` command group."""

from __future__ import annotations

from fluency.cli.shared import *  # noqa: F401,F403
from fluency.cli.shared import (  # noqa: F401
    Path, argparse, json, os, re,
    _workspace_path,  # private names are not re-exported by the star import
)

NAME = "identity"


def register(subparsers) -> None:
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


def handle(args) -> int:
    return handle_identity(args)
