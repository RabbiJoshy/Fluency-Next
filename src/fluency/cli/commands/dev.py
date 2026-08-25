"""The ``fluency dev`` command group."""

from __future__ import annotations

from fluency.cli.shared import *  # noqa: F401,F403
from fluency.cli.shared import (  # noqa: F401
    Path, argparse, json, os, re,
    _workspace_path,  # private names are not re-exported by the star import
)

NAME = "dev"


def register(subparsers) -> None:
    dev = subparsers.add_parser("dev", help="serve the local app directory")
    dev.add_argument(
        "--host",
        default=os.environ.get("FLUENCY_HOST", DEFAULT_HOST),
        help="address to bind (default: %(default)s)",
    )
    dev.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("FLUENCY_PORT", DEFAULT_PORT)),
        help="port to bind (default: %(default)s)",
    )
    dev.add_argument(
        "--workspace",
        default=os.environ.get("FLUENCY_WORKSPACE"),
        help="workspace whose releases are mounted at /releases/",
    )


def serve_app(host: str, port: int, raw_workspace: str | None) -> None:
    app_directory = project_root() / "app"
    if not app_directory.is_dir():
        raise SystemExit(f"App directory does not exist: {app_directory}")
    workspace = Workspace.load(_workspace_path(raw_workspace))
    releases_directory = workspace.root / "releases"
    audit_resolver = LyricsAuditResolver(
        project_root=project_root(), workspace_root=workspace.root,
    )

    handler = partial(
        FluencyRequestHandler,
        directory=str(app_directory),
        releases_directory=releases_directory,
        audit_resolver=audit_resolver,
    )
    server = ThreadingHTTPServer((host, port), handler)
    print(f"Serving Fluency Next from {app_directory}")
    print(f"Mounting releases read-only from {releases_directory}")
    print(f"Open http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping local server")
    finally:
        server.server_close()


def handle(args) -> int:
    serve_app(args.host, args.port, args.workspace)
    return 0
