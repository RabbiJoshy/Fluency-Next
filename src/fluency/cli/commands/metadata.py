"""Inspect the cross-language sense-metadata architecture."""

from __future__ import annotations

import json
from pathlib import Path

from fluency.cli.shared import project_root
from fluency.sense_menu.metadata_audit import audit_wiktionary_snapshot, metadata_status
from fluency.core.workspace import Workspace
from fluency.release.metadata_upgrade import upgrade_release_metadata


NAME = "metadata"


def register(subparsers) -> None:
    parser = subparsers.add_parser("metadata", help="audit dictionary metadata across languages")
    actions = parser.add_subparsers(dest="metadata_command", required=True)
    status = actions.add_parser("status", help="show policy and source-snapshot readiness")
    status.add_argument("--workspace", type=Path)
    status.add_argument("--app-root", type=Path, help="inspect the releases configured by this app tree")
    audit = actions.add_parser("audit-wiktionary", help="inventory typed and unclassified metadata")
    audit.add_argument("--language", required=True)
    audit.add_argument("--policy", required=True)
    audit.add_argument("--snapshot", type=Path, required=True)
    audit.add_argument("--output", type=Path)
    upgrade = actions.add_parser(
        "upgrade-release", help="publish an immutable canonical-metadata successor"
    )
    upgrade.add_argument("--workspace", type=Path, required=True)
    upgrade.add_argument("--language", required=True)
    upgrade.add_argument("--mode", default="speech")
    upgrade.add_argument("--source-release", required=True)
    upgrade.add_argument("--target-release", required=True)


def handle(args) -> int:
    if args.metadata_command == "status":
        report = metadata_status(project_root(), args.workspace, args.app_root)
    elif args.metadata_command == "audit-wiktionary":
        report = audit_wiktionary_snapshot(
            project_root(),
            language=args.language,
            policy_id=args.policy,
            snapshot=args.snapshot,
        )
    elif args.metadata_command == "upgrade-release":
        output = upgrade_release_metadata(
            project_root(),
            Workspace.load(args.workspace),
            language=args.language,
            mode=args.mode,
            source_release_id=args.source_release,
            target_release_id=args.target_release,
        )
        print(f"Built inactive canonical-metadata release: {output}")
        return 0
    else:
        raise AssertionError(f"Unhandled metadata command: {args.metadata_command}")
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if getattr(args, "output", None):
        args.output.write_text(rendered, encoding="utf-8")
        print(f"Wrote metadata audit: {args.output}")
    else:
        print(rendered, end="")
    return 0
