"""The ``fluency pools`` command group."""

from __future__ import annotations

from fluency.cli.shared import *  # noqa: F401,F403
from fluency.cli.shared import (  # noqa: F401
    Path, argparse, json, os, re,
    _workspace_path,  # private names are not re-exported by the star import
)

NAME = "pools"


def register(subparsers) -> None:
    pools = subparsers.add_parser(
        "pools", help="name, describe, and list reusable harvested sentence pools"
    )
    pool_actions = pools.add_subparsers(dest="pools_command", required=True)
    pool_register = pool_actions.add_parser(
        "register", help="promote a finished harvest into a named, described pool"
    )
    pool_register.add_argument("--workspace", type=Path, required=True)
    pool_register.add_argument("--run-id", required=True)
    pool_register.add_argument("--language", default="fr")
    pool_register.add_argument("--mode", default="speech")
    pool_register.add_argument("--pool-id", required=True)
    pool_register.add_argument(
        "--description", required=True,
        help="free text: what this pool is for, in your own words",
    )
    pool_register.add_argument("--intent", default=None)
    pool_register.add_argument(
        "--variety", default=None, help="advisory tag such as european or brazilian"
    )
    pool_list = pool_actions.add_parser("list", help="show the pools available to pick from")
    pool_list.add_argument("--workspace", type=Path, required=True)
    pool_list.add_argument("--language", default="fr")


def handle_pools(args) -> int:
    workspace = Workspace.initialize(args.workspace)
    if args.pools_command == "register":
        run_directory = (
            workspace.root / "runs" / args.language / args.mode / args.run_id
        )
        directory = register_pool_from_run(
            workspace.root,
            run_directory,
            pool_id=args.pool_id,
            description=args.description,
            intent=args.intent,
            variety=args.variety,
        )
        descriptor = read_pool(workspace.root, args.language, args.pool_id)
        coverage = descriptor["coverage"]
        print(f"Registered pool: {directory}")
        print(f"  {descriptor['description']}")
        print(f"  {coverage['sentences']:,} sentences")
        years = coverage.get("years") or {}
        if years:
            recent = sum(v for y, v in years.items() if int(y) >= 2010)
            total = sum(years.values())
            print(
                f"  years {min(years)}-{max(years)}; "
                f"{recent / total:.1%} from 2010 or later"
            )
        return 0
    if args.pools_command == "list":
        catalog = rebuild_catalog(workspace.root, args.language)
        if not catalog["pools"]:
            print(f"No pools registered for {args.language}.")
            return 0
        print(f"Pools available for {args.language}:")
        for pool_id, entry in catalog["pools"].items():
            variety = f" [{entry['variety']}]" if entry.get("variety") else ""
            print(f"  {pool_id}{variety}  {entry['sentences']:,} sentences")
            print(f"      {entry['description']}")
        return 0
    return 1


def handle(args) -> int:
    return handle_pools(args)
