"""The ``fluency enrichment`` command group."""

from __future__ import annotations

from fluency.cli.shared import *  # noqa: F401,F403
from fluency.cli.shared import (  # noqa: F401
    Path, argparse, json, json_bytes, os, re,
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
    cognates = enrichment_actions.add_parser(
        "build-cognates",
        help="score how transparent a deck's surfaces are to languages the learner reads",
    )
    cognates.add_argument("--workspace", default=os.environ.get("FLUENCY_WORKSPACE"))
    cognates.add_argument("--language", required=True)
    cognates.add_argument("--release-index", type=Path, required=True)
    cognates.add_argument(
        "--release-id",
        required=True,
        help="recorded as provenance; the mapping is keyed by language, not by release",
    )
    cognates.add_argument("--config-root", type=Path, default=Path("config"))
    cognates.add_argument(
        "--out",
        type=Path,
        help="app-facing cognates.json (default: <workspace>/cognates/<language>/cognates.json)",
    )
    cognates.add_argument("--layer-out", type=Path, help="full layer, with match provenance")
    # One flag per known language: "en" needs no extract because the deck's
    # glosses are already English; any other language takes its dictionary.
    cognates.add_argument(
        "--known",
        action="append",
        required=True,
        metavar="CODE[=EXTRACT]",
        help="known language, e.g. --known en --known pl=/path/kaikki-Polish.jsonl",
    )


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
    if args.enrichment_command == "build-cognates":
        known: dict[str, Path | None] = {}
        for item in args.known:
            code, _, extract = str(item).partition("=")
            known[code.strip()] = Path(extract) if extract else None
        workspace_root = Workspace.load(_workspace_path(args.workspace)).root
        out = args.out or workspace_root / "cognates" / args.language / "cognates.json"
        layer = build_cognate_layer(
            language=args.language,
            release_index=args.release_index,
            known_extracts=known,
            config_root=args.config_root,
            release_id=args.release_id,
        )
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(json_bytes(build_app_cognates(layer)))
        if args.layer_out:
            args.layer_out.parent.mkdir(parents=True, exist_ok=True)
            args.layer_out.write_bytes(json_bytes(layer))
        for code in layer["known_languages"]:
            report = layer["coverage"][code]
            print(
                f"{args.language}->{code}: scored {report['scored_surfaces']} of "
                f"{report['deck_surfaces']} deck surfaces "
                f"against {report['known_entries']} {code} entries"
            )
        print(f"Wrote {out}")
        print("No release was composed or activated.")
        return 0
    raise AssertionError(f"Unhandled enrichment command: {args.enrichment_command}")


def handle(args) -> int:
    return handle_enrichment(args)
