"""The ``fluency enrichment`` command group."""

from __future__ import annotations

from fluency.cli.shared import *  # noqa: F401,F403
from fluency.cli.shared import (  # noqa: F401
    Path, argparse, json, os, re,
    _workspace_path,  # private names are not re-exported by the star import
)

NAME = "enrichment"


def register(subparsers) -> None:
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


def handle(args) -> int:
    return handle_enrichment(args)
