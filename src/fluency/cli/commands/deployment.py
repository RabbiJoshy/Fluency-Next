"""The ``fluency deployment`` command group."""

from __future__ import annotations

from fluency.cli.shared import *  # noqa: F401,F403
from fluency.cli.shared import (  # noqa: F401
    Path, argparse, json, os, re,
    _workspace_path,  # private names are not re-exported by the star import
)

NAME = "deployment"


def register(subparsers) -> None:
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


def handle(args) -> int:
    return handle_deployment(args)
