"""The ``fluency artist`` command group."""

from __future__ import annotations

from fluency.cli.shared import *  # noqa: F401,F403
from fluency.cli.shared import (  # noqa: F401
    Path, argparse, json, os, re,
    _workspace_path,  # private names are not re-exported by the star import
)

NAME = "artist"


def register(subparsers) -> None:
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
    artist_build.add_argument(
        "--artist",
        action="append",
        dest="artists",
        help="include only this artist slug; repeat for more than one source",
    )
    artist_build.add_argument(
        "--wsd-assignments", action="append", default=[], metavar="ARTIST=PATH",
        help="overlay native v7 JSONL assignments for an artist; repeat as needed",
    )
    for action in ("validate", "activate"):
        action_parser = artist_actions.add_parser(action)
        action_parser.add_argument(
            "--workspace", default=os.environ.get("FLUENCY_WORKSPACE")
        )
        action_parser.add_argument("release_id")


def handle_artist(args: argparse.Namespace) -> int:
    workspace = Workspace.load(_workspace_path(args.workspace))
    if args.artist_command == "build-catalog-release":
        wsd_assignments: dict[str, Path] = {}
        for value in args.wsd_assignments:
            artist, separator, path = value.partition("=")
            if not separator or not artist or not path or artist in wsd_assignments:
                raise SystemExit("Each --wsd-assignments must be one unique ARTIST=PATH mapping")
            wsd_assignments[artist] = Path(path).expanduser().resolve()
        output = build_lyrics_catalog_release(
            workspace,
            source_repository=args.source_repository,
            release_id=args.release_id,
            include_artists=set(args.artists) if args.artists else None,
            wsd_assignment_overrides=wsd_assignments,
        )
        manifest, _ = validate_lyrics_release(output)
        print(f"Built immutable Lyrics catalog release: {output}")
        print(
            f"Frozen {manifest['artist_count']} artist sources across "
            f"{', '.join(manifest['languages'])}; {manifest['card_count']} source-card rows."
        )
        if wsd_assignments:
            print("Native v7 evidence was overlaid for: " + ", ".join(sorted(wsd_assignments)))
            print("Both forced-leaf and supported-specificity publication views are available there.")
        else:
            print("Historical forced-leaf assignments were retained in the dual-view WSD contract.")
            print("Supported-specificity remains explicitly not recorded; no confidence was invented.")
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


def handle(args) -> int:
    return handle_artist(args)
