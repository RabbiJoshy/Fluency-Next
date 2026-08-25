"""The ``fluency pipeline`` command group."""

from __future__ import annotations

from fluency.cli.shared import *  # noqa: F401,F403
from fluency.cli.shared import (  # noqa: F401
    Path, argparse, json, os, re,
    _workspace_path,  # private names are not re-exported by the star import
)

NAME = "pipeline"


def register(subparsers) -> None:
    pipeline = subparsers.add_parser("pipeline", help="plan clean, auditable data runs")
    pipeline_actions = pipeline.add_subparsers(dest="pipeline_command", required=True)
    pipeline_plan = pipeline_actions.add_parser(
        "plan", help="create a non-executing run skeleton from an exact profile"
    )
    pipeline_plan.add_argument(
        "--workspace", default=os.environ.get("FLUENCY_WORKSPACE")
    )
    pipeline_plan.add_argument("--profile", type=Path, required=True)
    pipeline_harvest = pipeline_actions.add_parser(
        "harvest", help="harvest explicit corpus snapshots into one planned run"
    )
    pipeline_harvest.add_argument(
        "--workspace", default=os.environ.get("FLUENCY_WORKSPACE")
    )
    pipeline_harvest.add_argument("--run-id", required=True)
    pipeline_harvest.add_argument("--language", default="fr")
    pipeline_harvest.add_argument("--mode", default="speech")
    pipeline_harvest.add_argument(
        "--source",
        action="append",
        required=True,
        metavar="NAME=PATH",
        help="explicit source snapshot inside workspace/raw; repeat for an explicit union",
    )
    pipeline_inventory = pipeline_actions.add_parser(
        "inventory", help="build a surface-only inventory from one explicit ranked snapshot"
    )
    pipeline_inventory.add_argument(
        "--workspace", default=os.environ.get("FLUENCY_WORKSPACE")
    )
    pipeline_inventory.add_argument("--run-id", required=True)
    pipeline_inventory.add_argument("--language", default="fr")
    pipeline_inventory.add_argument("--mode", default="speech")
    pipeline_inventory.add_argument(
        "--snapshot", type=Path, required=True,
        help="ranked file or compiled snapshot directory inside workspace/raw",
    )
    pipeline_inventory.add_argument(
        "--snapshot-id", required=True,
        help="explicit upstream snapshot label, such as lexique-4.00-2026-02-10",
    )
    pipeline_sense_menu = pipeline_actions.add_parser(
        "sense-menu", help="normalize one explicit dictionary snapshot into a planned run"
    )
    pipeline_sense_menu.add_argument(
        "--workspace", default=os.environ.get("FLUENCY_WORKSPACE")
    )
    pipeline_sense_menu.add_argument("--run-id", required=True)
    pipeline_sense_menu.add_argument("--language", default="fr")
    pipeline_sense_menu.add_argument("--mode", default="speech")
    pipeline_sense_menu.add_argument(
        "--snapshot", type=Path, required=True,
        help="provider snapshot file or directory inside workspace/raw",
    )
    pipeline_sense_menu.add_argument(
        "--snapshot-id", required=True,
        help="explicit snapshot label, such as enwiktionary-2026-08-05",
    )
    pipeline_wsd_import = pipeline_actions.add_parser(
        "wsd-import",
        help="validate and publish one complete external WSD assignment bundle",
    )
    pipeline_wsd_import.add_argument(
        "--workspace", default=os.environ.get("FLUENCY_WORKSPACE")
    )
    pipeline_wsd_import.add_argument("--run-id", required=True)
    pipeline_wsd_import.add_argument("--language", default="fr")
    pipeline_wsd_import.add_argument("--mode", default="speech")
    pipeline_wsd_import.add_argument(
        "--bundle",
        type=Path,
        required=True,
        help="complete assignment bundle under workspace/raw/wsd",
    )
    pipeline_run_release = pipeline_actions.add_parser(
        "build-run-release",
        help="build an inactive real-data release, attaching WSD assignments when stage 04 exists",
    )
    pipeline_run_release.add_argument(
        "--workspace", default=os.environ.get("FLUENCY_WORKSPACE")
    )
    pipeline_run_release.add_argument("--run-id", required=True)
    pipeline_run_release.add_argument("--release-id", required=True)
    pipeline_run_release.add_argument("--language", default="fr")
    pipeline_run_release.add_argument("--mode", default="speech")
    pipeline_run_release.add_argument(
        "--conjugations-artifact",
        help="exact optional conjugation-layer/v1 artifact ID",
    )
    pipeline_run_release.add_argument(
        "--source-titles",
        type=Path,
        help="optional pinned source-title JSON snapshot inside workspace/raw",
    )
    pipeline_run_release.add_argument(
        "--wsd-selection-projection",
        choices=("provider_only", "mwe_augmented"),
        default="provider_only",
        help="candidate universe to materialize from the immutable v7 assignment",
    )
    pipeline_run_release.add_argument(
        "--wsd-publication-projection",
        choices=("forced_leaf", "supported_specificity"),
        default="forced_leaf",
        help="publish every forced leaf or only leaf-level supported claims",
    )


def handle_pipeline(args: argparse.Namespace) -> int:
    workspace = Workspace.load(_workspace_path(args.workspace))
    if args.pipeline_command == "plan":
        profile = load_pipeline_profile(args.profile)
        run_directory = create_pipeline_plan(workspace, profile)
        target = (
            profile["scope"]["surface_limit"]
            * display_examples_per_card(profile["scope"])
        )
        print(f"Created fresh pipeline skeleton: {run_directory}")
        print(
            f"Audit target: {profile['scope']['surface_limit']} surface cards, "
            f"{display_examples_per_card(profile['scope'])} examples each ({target} total)"
        )
        budget = check_wsd_budget(profile)
        print(
            f"WSD spend: {profile['scope']['surface_limit']} cards x "
            f"{wsd_budget_per_card(profile['harvest'])} sentences = "
            f"{budget['projected_wsd_units']:,} units "
            f"(ceiling {budget['max_wsd_units_per_run']:,})"
        )
        print("No data stages were executed and no release was activated.")
        return 0
    if args.pipeline_command == "inventory":
        output = build_inventory_stage(
            project_root(),
            workspace,
            run_id=args.run_id,
            language=args.language,
            mode=args.mode,
            frequency_snapshot=args.snapshot,
            snapshot_id=args.snapshot_id,
        )
        report = json.loads((output / "report.json").read_text(encoding="utf-8"))
        print(f"Completed immutable surface inventory: {output}")
        print(
            f"Selected {report['inventory_surfaces']} cards from "
            f"{report['accepted_unique_surfaces']} ranked surfaces "
            f"({report['source_adapter']})."
        )
        print("No lemma data, sentence harvesting, WSD, release build, or activation was run.")
        return 0
    if args.pipeline_command == "harvest":
        snapshots: dict[str, Path] = {}
        for raw_source in args.source:
            name, separator, raw_path = raw_source.partition("=")
            if not separator or not name or not raw_path:
                raise SystemExit("Each --source must have the form NAME=PATH")
            if name in snapshots:
                raise SystemExit(f"Duplicate --source name: {name}")
            snapshots[name] = Path(raw_path)
        output = harvest_run_stage(
            project_root(),
            workspace,
            run_id=args.run_id,
            language=args.language,
            mode=args.mode,
            source_snapshots=snapshots,
        )
        report = json.loads((output / "report.json").read_text(encoding="utf-8"))
        print(f"Completed immutable sentence harvest: {output}")
        print(
            f"Retained {report['retained_candidate_matches']} candidate assignments "
            f"across {len(report['per_surface'])} surfaces."
        )
        if report["release_blocked_by_shortfall"]:
            print(
                f"Release remains blocked: {report['surfaces_with_shortfall']} surfaces "
                "have fewer than three candidates."
            )
        print("No WSD, final example selection, release build, or activation was run.")
        return 0
    if args.pipeline_command == "sense-menu":
        output = build_sense_menu_stage(
            project_root(),
            workspace,
            run_id=args.run_id,
            language=args.language,
            mode=args.mode,
            dictionary_snapshot=args.snapshot,
            snapshot_id=args.snapshot_id,
        )
        report = json.loads((output / "report.json").read_text(encoding="utf-8"))
        print(f"Completed immutable sense-menu build: {output}")
        print(
            f"Built {report['analysis_count']} headword/POS analyses and "
            f"{report['sense_count']} leaves for {report['cards_ready']} cards."
        )
        if report["cards_without_menu"]:
            print(
                f"Review required: {report['cards_without_menu']} cards have no menu; "
                "they remain explicit no_menu cases."
            )
        print("No WSD, example selection, release build, or activation was run.")
        return 0
    if args.pipeline_command == "wsd-import":
        output = import_wsd_assignments(
            workspace,
            run_id=args.run_id,
            language=args.language,
            mode=args.mode,
            bundle_path=args.bundle,
        )
        report = json.loads((output / "report.json").read_text(encoding="utf-8"))
        counts = report["assignment_counts"]
        print(f"Published immutable external WSD assignments: {output}")
        print(
            f"Assigned {counts['assigned']}; rejected {counts['rejected']}; "
            f"abstained {counts['abstained']}; no-menu {counts['no_menu']}."
        )
        print("No example selection, release build, or activation was run.")
        return 0
    if args.pipeline_command == "build-run-release":
        output = build_inactive_run_candidate(
            workspace,
            run_id=args.run_id,
            release_id=args.release_id,
            language=args.language,
            mode=args.mode,
            conjugations_artifact_id=args.conjugations_artifact,
            source_titles_path=args.source_titles,
            wsd_selection_projection=args.wsd_selection_projection,
            wsd_publication_projection=args.wsd_publication_projection,
        )
        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        deck = json.loads((output / "deck.json").read_text(encoding="utf-8"))
        examples = [item for card in deck["cards"] for item in card["examples"]]
        assigned = sum(1 for item in examples if item["assignment_status"] == "assigned")
        print(f"Built inactive real-data release: {output}")
        print(f"Published {manifest['card_count']} cards.")
        # Reporting "no WSD was run" regardless of whether it ran made a real
        # deck indistinguishable from an empty one at the console.
        if assigned:
            print(
                f"Examples: {assigned} assigned, {len(examples) - assigned} unassigned "
                f"(WSD assignments attached from stage 04)."
            )
        else:
            print(
                f"Examples: all {len(examples)} explicitly unassigned; no WSD stage was present."
            )
        if args.conjugations_artifact:
            print(f"Conjugations: {args.conjugations_artifact}")
        if args.source_titles:
            print(f"Source titles: {args.source_titles}")
        print("The release was not activated.")
        return 0
    raise AssertionError(f"Unhandled pipeline command: {args.pipeline_command}")


def handle(args) -> int:
    return handle_pipeline(args)
