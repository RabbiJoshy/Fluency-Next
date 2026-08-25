"""The ``fluency lyrics`` command group."""

from __future__ import annotations

from fluency.cli.shared import *  # noqa: F401,F403
from fluency.cli.shared import (  # noqa: F401
    Path, argparse, json, os, re,
    _workspace_path,  # private names are not re-exported by the star import
)

NAME = "lyrics"


def register(subparsers) -> None:
    lyrics = subparsers.add_parser(
        "lyrics", help="ingest and process auditable, language-agnostic Lyrics runs"
    )
    lyrics_actions = lyrics.add_subparsers(dest="lyrics_command", required=True)
    lyrics_plan_corpus = lyrics_actions.add_parser(
        "plan-corpus",
        help="pin and inventory an explicit multi-artist source corpus without executing it",
    )
    lyrics_plan_corpus.add_argument("--workspace", default=os.environ.get("FLUENCY_WORKSPACE"))
    lyrics_plan_corpus.add_argument("--config", type=Path, required=True)
    lyrics_plan_corpus.add_argument("--source-repository", type=Path, required=True)
    lyrics_plan_corpus.add_argument("--plan-id", required=True)
    lyrics_ingest_corpus = lyrics_actions.add_parser(
        "ingest-corpus",
        help="materialize every pinned song as an immutable source-ingest run with safe resume",
    )
    lyrics_ingest_corpus.add_argument("--workspace", default=os.environ.get("FLUENCY_WORKSPACE"))
    lyrics_ingest_corpus.add_argument("--plan", type=Path, required=True)
    lyrics_process_corpus = lyrics_actions.add_parser(
        "process-corpus",
        help="process every pinned song with one exact language profile and safe resume",
    )
    lyrics_process_corpus.add_argument("--workspace", default=os.environ.get("FLUENCY_WORKSPACE"))
    lyrics_process_corpus.add_argument("--plan", type=Path, required=True)
    lyrics_process_corpus.add_argument("--profile", type=Path, required=True)
    lyrics_menu_corpus = lyrics_actions.add_parser(
        "menu-corpus",
        help="build one provider union and exact resumable lexical menus for every processed song",
    )
    lyrics_menu_corpus.add_argument("--workspace", default=os.environ.get("FLUENCY_WORKSPACE"))
    lyrics_menu_corpus.add_argument("--plan", type=Path, required=True)
    lyrics_menu_corpus.add_argument("--dictionary-snapshot", type=Path, required=True)
    lyrics_menu_corpus.add_argument("--snapshot-id", required=True)
    lyrics_menu_corpus.add_argument("--language-policy", required=True)
    lyrics_menu_corpus.add_argument("--menu-id", required=True)
    lyrics_wsd_prepare_corpus = lyrics_actions.add_parser(
        "wsd-prepare-corpus",
        help="prepare exact WSD request pools for every menu-complete song without executing a model",
    )
    lyrics_wsd_prepare_corpus.add_argument("--workspace", default=os.environ.get("FLUENCY_WORKSPACE"))
    lyrics_wsd_prepare_corpus.add_argument("--plan", type=Path, required=True)
    lyrics_wsd_prepare_corpus.add_argument("--lexical-report", type=Path, required=True)
    lyrics_wsd_execute_corpus = lyrics_actions.add_parser(
        "wsd-execute-corpus",
        help="run the pinned best-so-far Spanish v5 method with one shared resumable model runtime",
    )
    lyrics_wsd_execute_corpus.add_argument("--workspace", default=os.environ.get("FLUENCY_WORKSPACE"))
    lyrics_wsd_execute_corpus.add_argument("--plan", type=Path, required=True)
    lyrics_wsd_execute_corpus.add_argument("--preparation-report", type=Path, required=True)
    lyrics_wsd_execute_corpus.add_argument(
        "--env-file", type=Path,
        help="optional dotenv file parsed as data for GEMINI_API_KEY; it is never executed",
    )
    lyrics_wsd_import_corpus = lyrics_actions.add_parser(
        "wsd-import-corpus",
        help="import an exact complete catalog of per-song WSD bundles from any compliant method",
    )
    lyrics_wsd_import_corpus.add_argument("--workspace", default=os.environ.get("FLUENCY_WORKSPACE"))
    lyrics_wsd_import_corpus.add_argument("--plan", type=Path, required=True)
    lyrics_wsd_import_corpus.add_argument("--preparation-report", type=Path, required=True)
    lyrics_wsd_import_corpus.add_argument("--catalog", type=Path, required=True)
    lyrics_consolidate_corpus = lyrics_actions.add_parser(
        "consolidate-corpus",
        help="consolidate every song after one complete exact corpus WSD import",
    )
    lyrics_consolidate_corpus.add_argument("--workspace", default=os.environ.get("FLUENCY_WORKSPACE"))
    lyrics_consolidate_corpus.add_argument("--plan", type=Path, required=True)
    lyrics_consolidate_corpus.add_argument("--wsd-import-report", type=Path, required=True)
    lyrics_consolidate_corpus.add_argument("--example-cap-per-sense", type=int, default=12)
    lyrics_consolidate_corpus.add_argument("--translation-language", default="en")
    lyrics_assemble_corpus = lyrics_actions.add_parser(
        "assemble-corpus",
        help="merge one exact WSD-method branch into clean multi-artist app data",
    )
    lyrics_assemble_corpus.add_argument("--workspace", default=os.environ.get("FLUENCY_WORKSPACE"))
    lyrics_assemble_corpus.add_argument("--plan", type=Path, required=True)
    lyrics_assemble_corpus.add_argument("--consolidation-report", type=Path, required=True)
    lyrics_release_corpus = lyrics_actions.add_parser(
        "build-corpus-release",
        help="compose clean corpus assignments with retained optional media as an inactive release",
    )
    lyrics_release_corpus.add_argument("--workspace", default=os.environ.get("FLUENCY_WORKSPACE"))
    lyrics_release_corpus.add_argument("--assembly", type=Path, required=True)
    lyrics_release_corpus.add_argument("--parity-release", type=Path, required=True)
    lyrics_release_corpus.add_argument("--release-id", required=True)
    lyrics_plan_processing = lyrics_actions.add_parser(
        "plan-processing-profile",
        help="pin shared and artist-specific inputs for one exact corpus processing run",
    )
    lyrics_plan_processing.add_argument("--workspace", default=os.environ.get("FLUENCY_WORKSPACE"))
    lyrics_plan_processing.add_argument("--plan", type=Path, required=True)
    lyrics_plan_processing.add_argument("--config", type=Path, required=True)
    lyrics_plan_processing.add_argument("--source-repository", type=Path, required=True)
    lyrics_plan_processing.add_argument("--profile-id", required=True)
    lyrics_ingest = lyrics_actions.add_parser(
        "ingest-legacy-genius",
        help="pin and normalize one song from a legacy Genius batch",
    )
    lyrics_ingest.add_argument(
        "--workspace", default=os.environ.get("FLUENCY_WORKSPACE")
    )
    lyrics_ingest.add_argument("--source-batch", type=Path, required=True)
    lyrics_ingest.add_argument("--translations", type=Path)
    lyrics_ingest.add_argument("--source-record-id", required=True)
    lyrics_ingest.add_argument("--snapshot-id", required=True)
    lyrics_ingest.add_argument("--run-id", required=True)
    lyrics_ingest.add_argument("--language", required=True)
    lyrics_ingest.add_argument("--artist-id", required=True)
    lyrics_ingest.add_argument("--artist-name", required=True)
    lyrics_ingest.add_argument("--translation-language", default="en")
    lyrics_process = lyrics_actions.add_parser(
        "process",
        help="tokenize, normalize, restore elisions, and route one source run",
    )
    lyrics_process.add_argument(
        "--workspace", default=os.environ.get("FLUENCY_WORKSPACE")
    )
    lyrics_process.add_argument("--run-id", required=True)
    lyrics_process.add_argument("--language", required=True)
    lyrics_process.add_argument("--elision-mapping", type=Path, required=True)
    lyrics_process.add_argument("--multi-word-elisions", type=Path, required=True)
    lyrics_process.add_argument("--known-forms", type=Path, required=True)
    lyrics_process.add_argument("--frequency-snapshot", type=Path, required=True)
    lyrics_process.add_argument("--lexeme-register", type=Path, required=True)
    lyrics_process.add_argument("--routing-snapshot", type=Path, required=True)
    lyrics_process.add_argument("--routing-mode", choices=("snapshot", "live"), default="snapshot")
    lyrics_process.add_argument("--english-frequency", type=Path)
    lyrics_process.add_argument("--english-loanwords", type=Path)
    lyrics_process.add_argument("--conjugation-reverse", type=Path)
    lyrics_process.add_argument("--caps-stats", type=Path)
    lyrics_process.add_argument(
        "--routing-overrides",
        type=Path,
        help="optional typed registry; omitted means no human routing overrides",
    )
    lyrics_menu = lyrics_actions.add_parser(
        "menu",
        help="build provider-neutral lexical candidates without running WSD",
    )
    lyrics_menu.add_argument("--workspace", default=os.environ.get("FLUENCY_WORKSPACE"))
    lyrics_menu.add_argument("--run-id", required=True)
    lyrics_menu.add_argument("--language", required=True)
    lyrics_menu.add_argument("--dictionary-snapshot", type=Path, required=True)
    lyrics_menu.add_argument("--snapshot-id", required=True)
    lyrics_menu.add_argument("--language-policy", required=True)
    lyrics_wsd_prepare = lyrics_actions.add_parser(
        "wsd-prepare",
        help="materialize exact WSD contexts and eligibility without executing a model",
    )
    lyrics_wsd_prepare.add_argument("--workspace", default=os.environ.get("FLUENCY_WORKSPACE"))
    lyrics_wsd_prepare.add_argument("--run-id", required=True)
    lyrics_wsd_prepare.add_argument("--language", required=True)
    lyrics_wsd_import = lyrics_actions.add_parser(
        "wsd-import", help="validate and publish one complete occurrence-level WSD result bundle",
    )
    lyrics_wsd_import.add_argument("--workspace", default=os.environ.get("FLUENCY_WORKSPACE"))
    lyrics_wsd_import.add_argument("--run-id", required=True)
    lyrics_wsd_import.add_argument("--language", required=True)
    lyrics_wsd_import.add_argument("--bundle", type=Path, required=True)
    lyrics_wsd_execute = lyrics_actions.add_parser(
        "wsd-execute", help="run one explicitly pinned WSD method into a raw complete-result bundle",
    )
    lyrics_wsd_execute.add_argument("--workspace", default=os.environ.get("FLUENCY_WORKSPACE"))
    lyrics_wsd_execute.add_argument("--run-id", required=True)
    lyrics_wsd_execute.add_argument("--language", required=True, choices=("es",))
    lyrics_wsd_execute.add_argument(
        "--method", required=True, choices=("es-sd-beto-cal-v5-migration-v1",),
    )
    lyrics_wsd_execute.add_argument(
        "--env-file", type=Path,
        help="optional dotenv file read as data for GEMINI_API_KEY; it is never executed",
    )
    lyrics_consolidate = lyrics_actions.add_parser(
        "consolidate",
        help="group exact WSD results into auditable surface cards, examples, and dispositions",
    )
    lyrics_consolidate.add_argument("--workspace", default=os.environ.get("FLUENCY_WORKSPACE"))
    lyrics_consolidate.add_argument("--run-id", required=True)
    lyrics_consolidate.add_argument("--language", required=True)
    lyrics_consolidate.add_argument("--example-cap-per-sense", type=int, default=12)
    lyrics_consolidate.add_argument("--translation-language", default="en")
    lyrics_assemble = lyrics_actions.add_parser(
        "assemble-app",
        help="render an inactive clean consolidation into the existing split Artist app contract",
    )
    lyrics_assemble.add_argument("--workspace", default=os.environ.get("FLUENCY_WORKSPACE"))
    lyrics_assemble.add_argument("--run-id", required=True)
    lyrics_assemble.add_argument("--language", required=True)
    lyrics_assemble.add_argument("--artist-slug", required=True)
    lyrics_assemble.add_argument("--comparison-release", type=Path)
    lyrics_preview = lyrics_actions.add_parser(
        "build-preview-release",
        help="package one clean app assembly as a validated inactive Lyrics release",
    )
    lyrics_preview.add_argument("--workspace", default=os.environ.get("FLUENCY_WORKSPACE"))
    lyrics_preview.add_argument("--run-id", required=True)
    lyrics_preview.add_argument("--language", required=True)
    lyrics_preview.add_argument("--artist-slug", required=True)
    lyrics_preview.add_argument("--release-id", required=True)
    lyrics_preview.add_argument("--parity-release", type=Path, required=True)
    lyrics_preview.add_argument("--song-source-id", required=True)


def handle_lyrics(args: argparse.Namespace) -> int:
    workspace = Workspace.load(_workspace_path(args.workspace))
    if args.lyrics_command == "plan-corpus":
        output = build_lyrics_corpus_plan(
            workspace, config_path=args.config,
            source_repository=args.source_repository, plan_id=args.plan_id,
        )
        manifest = json.loads(output.read_text(encoding="utf-8"))
        totals = manifest["totals"]
        print(f"Pinned immutable Lyrics corpus plan: {output}")
        print(
            f"Selected {totals['songs']} songs from {totals['included_artist_sources']} "
            f"artist sources across {totals['source_files']} exact files."
        )
        print(
            f"Recorded {len(manifest['excluded_sources'])} explicit exclusions and "
            f"{totals['cross_source_collisions']} artist-scoped source collisions."
        )
        print("No song run, routing, WSD, deck, release, or activation was executed.")
        return 0
    if args.lyrics_command == "ingest-corpus":
        def show_progress(event: dict) -> None:
            if event["completed"] == 1 or event["completed"] % 25 == 0 or event["completed"] == event["planned"]:
                print(
                    f"Source ingest {event['completed']}/{event['planned']}: "
                    f"{event['artist_slug']} song {event['source_record_id']} ({event['action']})",
                    flush=True,
                )

        result = ingest_lyrics_corpus_plan(workspace, plan_path=args.plan, progress=show_progress)
        print(f"Completed exact Lyrics corpus source ingest: {result['report_path']}")
        print(
            f"Verified {result['song_run_count']} immutable song runs: "
            f"created {result['created_this_invocation']}, "
            f"resumed/skipped {result['skipped_this_invocation']}."
        )
        print("No token routing, WSD, deck assembly, release build, or activation was run.")
        return 0
    if args.lyrics_command == "process-corpus":
        def show_processing_progress(event: dict) -> None:
            if event["completed"] == 1 or event["completed"] % 25 == 0 or event["completed"] == event["planned"]:
                print(
                    f"Lyrics processing {event['completed']}/{event['planned']}: "
                    f"{event['artist_slug']} song {event['source_record_id']} ({event['action']})",
                    flush=True,
                )

        result = process_lyrics_corpus_plan(
            workspace,
            plan_path=args.plan,
            profile_path=args.profile,
            progress=show_processing_progress,
        )
        print(f"Completed exact Lyrics corpus processing: {result['report_path']}")
        print(
            f"Verified {result['song_run_count']} immutable processing stages: "
            f"created {result['created_this_invocation']}, "
            f"resumed/skipped {result['skipped_this_invocation']}."
        )
        print("No lexical menu, WSD, deck assembly, release build, or activation was run.")
        return 0
    if args.lyrics_command == "menu-corpus":
        def show_menu_progress(event: dict) -> None:
            if event["completed"] == 1 or event["completed"] % 25 == 0 or event["completed"] == event["planned"]:
                print(
                    f"Lyrics menu {event['completed']}/{event['planned']}: "
                    f"{event['artist_slug']} song {event['source_record_id']} ({event['action']})",
                    flush=True,
                )

        result = build_lyrics_corpus_lexical_menus(
            project_root(),
            workspace,
            plan_path=args.plan,
            dictionary_snapshot=args.dictionary_snapshot,
            snapshot_id=args.snapshot_id,
            language_policy_id=args.language_policy,
            menu_id=args.menu_id,
            progress=show_menu_progress,
        )
        print(f"Completed exact Lyrics corpus lexical menus: {result['report_path']}")
        print(
            f"Verified {result['song_run_count']} immutable song menus over "
            f"{result['lookup_form_count']} shared lookup forms: "
            f"created {result['created_this_invocation']}, "
            f"resumed/skipped {result['skipped_this_invocation']}."
        )
        print("No sense was assigned; no deck, release, or activation was created.")
        return 0
    if args.lyrics_command == "wsd-prepare-corpus":
        def show_wsd_prepare_progress(event: dict) -> None:
            if event["completed"] == 1 or event["completed"] % 25 == 0 or event["completed"] == event["planned"]:
                print(
                    f"Lyrics WSD preparation {event['completed']}/{event['planned']}: "
                    f"{event['artist_slug']} song {event['source_record_id']} ({event['action']})",
                    flush=True,
                )

        result = prepare_lyrics_corpus_wsd(
            project_root(), workspace,
            plan_path=args.plan,
            lexical_report_path=args.lexical_report,
            progress=show_wsd_prepare_progress,
        )
        print(f"Completed exact corpus WSD preparation: {result['report_path']}")
        print(
            f"Verified {result['request_count']} requests across {result['song_run_count']} songs; "
            f"{result['executable_request_count']} are executable. "
            f"Created {result['created_this_invocation']}, "
            f"resumed/skipped {result['skipped_this_invocation']}."
        )
        print("No WSD method ran; no assignment, deck, release, or activation was created.")
        return 0
    if args.lyrics_command == "wsd-execute-corpus":
        def show_wsd_execution_progress(event: dict) -> None:
            if event["completed"] == 1 or event["completed"] % 25 == 0 or event["completed"] == event["planned"]:
                print(
                    f"Lyrics placeholder WSD {event['completed']}/{event['planned']}: "
                    f"{event['artist_slug']} song {event['source_record_id']} ({event['action']})",
                    flush=True,
                )

        result = execute_spanish_v5_corpus(
            project_root(), workspace, plan_path=args.plan,
            preparation_report_path=args.preparation_report,
            env_file=args.env_file, progress=show_wsd_execution_progress,
        )
        print(f"Completed best-so-far WSD bundle catalog: {result['catalog_path']}")
        print(
            f"Verified {result['song_run_count']} complete song bundles: "
            f"created {result['created_this_invocation']}, "
            f"resumed/skipped {result['skipped_this_invocation']}."
        )
        print("Results remain raw and inactive; no import, deck, release, or activation occurred.")
        return 0
    if args.lyrics_command == "wsd-import-corpus":
        def show_wsd_import_progress(event: dict) -> None:
            if event["completed"] == 1 or event["completed"] % 25 == 0 or event["completed"] == event["planned"]:
                print(
                    f"Lyrics WSD import {event['completed']}/{event['planned']}: "
                    f"{event['artist_slug']} song {event['source_record_id']} ({event['action']})",
                    flush=True,
                )

        result = import_lyrics_corpus_results(
            project_root(), workspace,
            plan_path=args.plan,
            preparation_report_path=args.preparation_report,
            catalog_path=args.catalog,
            progress=show_wsd_import_progress,
        )
        print(f"Completed exact corpus WSD result import: {result['report_path']}")
        print(
            f"Verified {result['result_count']} results across {result['song_run_count']} songs "
            f"from method {result['method_profile_id']}: "
            f"created {result['created_this_invocation']}, "
            f"resumed/skipped {result['skipped_this_invocation']}."
        )
        print("No consolidation, app assembly, release, or activation was created.")
        return 0
    if args.lyrics_command == "consolidate-corpus":
        def show_consolidation_progress(event: dict) -> None:
            if event["completed"] == 1 or event["completed"] % 25 == 0 or event["completed"] == event["planned"]:
                print(
                    f"Lyrics consolidation {event['completed']}/{event['planned']}: "
                    f"{event['artist_slug']} song {event['source_record_id']} ({event['action']})",
                    flush=True,
                )

        result = consolidate_lyrics_corpus(
            project_root(), workspace,
            plan_path=args.plan,
            wsd_import_report_path=args.wsd_import_report,
            example_cap_per_sense=args.example_cap_per_sense,
            translation_language=args.translation_language,
            progress=show_consolidation_progress,
        )
        print(f"Completed exact corpus consolidation: {result['report_path']}")
        print(
            f"Verified {result['song_run_count']} song consolidations with "
            f"{result['assigned_example_count']} assigned occurrence examples and "
            f"{result['selected_example_count']} selected examples: "
            f"created {result['created_this_invocation']}, "
            f"resumed/skipped {result['skipped_this_invocation']}."
        )
        print("No app assembly, release, deployment, or activation was created.")
        return 0
    if args.lyrics_command == "assemble-corpus":
        def show_assembly_progress(event: dict) -> None:
            if event["completed"] == 1 or event["completed"] % 25 == 0 or event["completed"] == event["planned"]:
                print(
                    f"Lyrics app assembly {event['completed']}/{event['planned']}: "
                    f"{event['artist_slug']} song {event['source_record_id']} ({event['action']})",
                    flush=True,
                )

        result = assemble_lyrics_corpus(
            project_root(), workspace, plan_path=args.plan,
            consolidation_report_path=args.consolidation_report,
            progress=show_assembly_progress,
        )
        print(f"Completed clean multi-artist app assembly: {result['assembly_path']}")
        print(
            f"Built {result['artist_count']} artists, {result['language_card_count']} shared "
            f"surface cards and {result['selected_example_count']} selected examples: "
            f"created {result['created_this_invocation']}, "
            f"resumed/skipped {result['skipped_this_invocation']} song assemblies."
        )
        print("No release, deployment, or activation was created.")
        return 0
    if args.lyrics_command == "build-corpus-release":
        output = build_clean_lyrics_corpus_release(
            workspace, assembly_path=args.assembly,
            parity_release=args.parity_release, release_id=args.release_id,
        )
        manifest, _composition = validate_lyrics_release(output)
        comparison = json.loads((output / "comparison.json").read_text(encoding="utf-8"))
        print(f"Built validated inactive clean Lyrics release: {output}")
        print(
            f"Packaged {manifest['artist_count']} artists and {manifest['card_count']} artist-card rows; "
            f"comparison found {comparison['totals']['cards_added']} added and "
            f"{comparison['totals']['cards_removed']} removed cards."
        )
        print("The active Lyrics release was not changed.")
        return 0
    if args.lyrics_command == "plan-processing-profile":
        output = build_lyrics_corpus_processing_profile(
            workspace,
            plan_path=args.plan,
            config_path=args.config,
            source_repository=args.source_repository,
            profile_id=args.profile_id,
        )
        profile = json.loads(output.read_text(encoding="utf-8"))
        print(f"Pinned immutable Lyrics processing profile: {output}")
        print(
            f"Selected {len(profile['shared_inputs'])} shared inputs and "
            f"{sum(len(value) for value in profile['artist_inputs'].values())} "
            f"artist-specific inputs across {len(profile['artist_inputs'])} sources."
        )
        print("No song processing, lexical menu, WSD, deck, release, or activation was run.")
        return 0
    if args.lyrics_command == "ingest-legacy-genius":
        output = ingest_legacy_genius_song(
            workspace,
            source_batch=args.source_batch,
            translations_path=args.translations,
            source_record_id=args.source_record_id,
            snapshot_id=args.snapshot_id,
            run_id=args.run_id,
            language=args.language,
            artist_id=args.artist_id,
            artist_name=args.artist_name,
            translation_language=args.translation_language,
        )
        report = json.loads((output / "report.json").read_text(encoding="utf-8"))
        print(f"Completed immutable Lyrics source ingest: {output}")
        print(
            f"Pinned {report['line_count']} source lines, "
            f"{report['alignment_count']} optional translations, and "
            f"{report['lineage_event_count']} lineage events."
        )
        if report["unaligned_line_count"]:
            print(
                f"Graceful degradation: {report['unaligned_line_count']} lines have no "
                "translation and remain valid source lines."
            )
        print("No token routing, WSD, deck assembly, release build, or activation was run.")
        return 0
    if args.lyrics_command == "process":
        output = process_lyrics_run(
            workspace,
            run_id=args.run_id,
            language=args.language,
            elision_mapping=args.elision_mapping,
            multi_word_elisions=args.multi_word_elisions,
            known_forms=args.known_forms,
            frequency_snapshot=args.frequency_snapshot,
            lexeme_register=args.lexeme_register,
            routing_snapshot=args.routing_snapshot,
            routing_mode=args.routing_mode,
            english_frequency=args.english_frequency,
            english_loanwords=args.english_loanwords,
            conjugation_reverse=args.conjugation_reverse,
            caps_stats=args.caps_stats,
            routing_overrides=args.routing_overrides,
        )
        report = json.loads((output / "report.json").read_text(encoding="utf-8"))
        print(f"Completed immutable Lyrics processing layer: {output}")
        print(
            f"Tokenized {report['occurrence_count']} occurrences into "
            f"{report['analysis_unit_count']} analysis units; emitted "
            f"{report['lineage_event_count']} lineage events."
        )
        if report["routing_provenance"] == "direct":
            print(
                "Normalization, elision restoration, and routing were recomputed directly; "
                "the pinned migration snapshot was used only for comparison."
            )
            print("Route comparison: " + json.dumps(report["route_comparison"], sort_keys=True))
        else:
            print(
                "Normalization and elision restoration were recomputed directly; "
                "routing is explicitly sourced from the pinned migration snapshot."
            )
        print("No WSD, deck assembly, release build, or activation was run.")
        return 0
    if args.lyrics_command == "menu":
        output = build_lyrics_lexical_menu_stage(
            project_root(),
            workspace,
            run_id=args.run_id,
            language=args.language,
            dictionary_snapshot=args.dictionary_snapshot,
            snapshot_id=args.snapshot_id,
            language_policy_id=args.language_policy,
        )
        report = json.loads((output / "report.json").read_text(encoding="utf-8"))
        print(f"Completed immutable Lyrics lexical-menu layer: {output}")
        print(
            f"Emitted {report['candidate_count']} occurrence-bound candidates: "
            + ", ".join(
                f"{status}={count}"
                for status, count in report["status_counts"].items()
            )
            + "."
        )
        print(
            f"Provider menu contains {report['ready_analysis_count']} analyses and "
            f"{report['ready_sense_count']} sense leaves."
        )
        print("No sense was assigned; no deck, release, or activation was created.")
        return 0
    if args.lyrics_command == "wsd-prepare":
        output = prepare_lyrics_wsd_stage(
            project_root(),
            workspace,
            run_id=args.run_id,
            language=args.language,
        )
        report = json.loads((output / "report.json").read_text(encoding="utf-8"))
        print(f"Completed immutable Lyrics WSD preparation: {output}")
        print(
            f"Prepared {report['request_count']} complete target records; "
            f"{report['executable_request_count']} are executable and "
            f"{report['translation_available_count']} have optional aligned translations."
        )
        print("No WSD model ran; no assignment, deck, release, or activation was created.")
        return 0
    if args.lyrics_command == "wsd-import":
        output = import_lyrics_wsd_results(
            project_root(), workspace, run_id=args.run_id,
            language=args.language, bundle_path=args.bundle,
        )
        report = json.loads((output / "report.json").read_text(encoding="utf-8"))
        counts = report["result_counts"]
        print(f"Published complete immutable Lyrics WSD results: {output}")
        print(", ".join(f"{status}={count}" for status, count in counts.items()))
        print("No deck, release, or activation was created.")
        return 0
    if args.lyrics_command == "wsd-execute":
        output = execute_spanish_v5_lyrics(
            project_root(), workspace, run_id=args.run_id, env_file=args.env_file,
        )
        print(f"Created complete raw Lyrics WSD result bundle: {output}")
        print("The result is inactive; run lyrics wsd-import only after validation.")
        return 0
    if args.lyrics_command == "consolidate":
        output = consolidate_lyrics_run(
            project_root(), workspace, run_id=args.run_id, language=args.language,
            example_cap_per_sense=args.example_cap_per_sense,
            translation_language=args.translation_language,
        )
        report = json.loads((output / "report.json").read_text(encoding="utf-8"))
        print(f"Completed immutable Lyrics occurrence consolidation: {output}")
        print(
            f"Built {report['study_card_count']} surface cards from "
            f"{report['assigned_example_count']} assigned occurrences; "
            f"selected {report['selected_example_count']} examples under the explicit cap policy."
        )
        print(
            f"Retained {report['non_study_disposition_count']} non-study outcomes as auditable dispositions."
        )
        print("No app assets, release, or activation were created.")
        return 0
    if args.lyrics_command == "assemble-app":
        output = assemble_lyrics_app_stage(
            project_root(), workspace, run_id=args.run_id, language=args.language,
            artist_slug=args.artist_slug, comparison_release=args.comparison_release,
        )
        report = json.loads((output / "report.json").read_text(encoding="utf-8"))
        print(f"Completed inactive Lyrics app assembly: {output}")
        print(
            f"Rendered {report['card_count']} cards and {report['example_count']} selected examples "
            f"into the exact split index/examples/master contract."
        )
        if report["comparison"]["status"] == "compared":
            print(
                f"Parity comparison: {report['comparison']['surface_words_already_in_parity']} clean surfaces already exist; "
                f"selected-example delta {report['comparison']['selected_example_delta']:+d}."
            )
        print("No release was composed or activated.")
        return 0
    if args.lyrics_command == "build-preview-release":
        output = build_clean_lyrics_preview_release(
            workspace, run_id=args.run_id, language=args.language,
            artist_slug=args.artist_slug, release_id=args.release_id,
            parity_release=args.parity_release, song_source_id=args.song_source_id,
        )
        manifest, _composition = validate_lyrics_release(output)
        comparison = json.loads((output / "comparison.json").read_text(encoding="utf-8"))
        print(f"Built validated inactive Lyrics preview release: {output}")
        print(
            f"Packaged {manifest['card_count']} cards across {len(manifest['files'])} exact app files "
            f"({comparison['payload_bytes']} bytes)."
        )
        print("The active Lyrics release was not changed.")
        return 0
    raise AssertionError(f"Unhandled lyrics command: {args.lyrics_command}")


def handle(args) -> int:
    return handle_lyrics(args)
