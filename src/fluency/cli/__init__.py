"""Fluency command-line interface.

Formerly one 1,706-line module holding 57 subcommands, which made it the file
every concurrent session had to edit and therefore the repository's main source
of merge conflicts. Each command group now owns a module under
``fluency.cli.commands`` exposing ``NAME``, ``register`` and ``handle``; this
root only builds the parser and dispatches.

Adding a command touches one new file and one line of ``COMMAND_MODULES``.
"""

from __future__ import annotations

import argparse
from typing import Sequence

from fluency.cli.registry import load_commands
# Re-exported so that `from fluency.cli import ...` keeps working for callers
# written against the single-module layout.
from fluency.cli.shared import (  # noqa: F401
    APP_DATA_ROUTES,
    DEFAULT_HOST,
    DEFAULT_PORT,
    project_root,
    resolve_active_app_asset,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fluency")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for module in load_commands():
        module.register(subparsers)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    for module in load_commands():
        if module.NAME == args.command:
            return module.handle(args)
    raise AssertionError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
