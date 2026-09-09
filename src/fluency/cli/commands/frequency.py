"""The ``fluency frequency`` command group."""

from __future__ import annotations

from fluency.cli.shared import *  # noqa: F401,F403
from fluency.cli.shared import (  # noqa: F401
    Path, argparse, json, os, re,
    _workspace_path,  # private names are not re-exported by the star import
)

NAME = "frequency"


def register(subparsers) -> None:
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
    coverage = frequency_actions.add_parser(
        "build-coverage",
        help="what share of a corpus each deck surface accounts for",
    )
    coverage.add_argument("--workspace", default=os.environ.get("FLUENCY_WORKSPACE"))
    coverage.add_argument("--language", required=True)
    coverage.add_argument("--release-index", type=Path, required=True)
    coverage.add_argument("--release-id", required=True)
    coverage.add_argument(
        "--frequency-source",
        type=Path,
        required=True,
        help="a 'surface count' list, e.g. an OpenSubtitles frequency file",
    )
    coverage.add_argument("--provider", default="opensubtitles-2018")
    coverage.add_argument(
        "--out",
        type=Path,
        help="default: <workspace>/coverage/<language>/coverage.json",
    )


def handle_frequency(args: argparse.Namespace) -> int:
    workspace = Workspace.load(_workspace_path(args.workspace))
    if args.frequency_command == "build-coverage":
        layer = build_coverage_layer(
            language=args.language,
            release_index=args.release_index,
            frequency_source=args.frequency_source,
            provider=args.provider,
            release_id=args.release_id,
        )
        out = args.out or workspace.root / "coverage" / args.language / "coverage.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(json_bytes(layer))
        print(
            f"{args.language}: {layer['covered_surfaces']} of {layer['deck_surfaces']} "
            f"deck surfaces found in {layer['corpus']['distinct_surfaces']} corpus surfaces"
        )
        print(f"Wrote {out}")
        return 0
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


def handle(args) -> int:
    return handle_frequency(args)
