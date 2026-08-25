"""The ``fluency pilot`` command group."""

from __future__ import annotations

from fluency.cli.shared import *  # noqa: F401,F403
from fluency.cli.shared import (  # noqa: F401
    Path, argparse, json, os, re,
    _workspace_path,  # private names are not re-exported by the star import
)

NAME = "pilot"


def register(subparsers) -> None:
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


def handle_pilot(command: str, raw_workspace: str | None) -> int:
    workspace = Workspace.load(_workspace_path(raw_workspace))
    if command == "build":
        release_directory = build_pilot_release(workspace)
        print(f"Published French Speech pilot: {release_directory}")
        print("Cards: 25")
        print("WSD: disabled (curated fixture)")
        return 0
    raise AssertionError(f"Unhandled pilot command: {command}")


def handle(args) -> int:
    return handle_pilot(args.pilot_command, args.workspace)
