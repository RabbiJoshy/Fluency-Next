"""The ``fluency workspace`` command group."""

from __future__ import annotations

from fluency.cli.shared import *  # noqa: F401,F403
from fluency.cli.shared import (  # noqa: F401
    Path, argparse, json, os, re,
    _workspace_path,  # private names are not re-exported by the star import
)

NAME = "workspace"


def register(subparsers) -> None:
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


def handle(args) -> int:
    return handle_workspace(args.workspace_command, args.path)
