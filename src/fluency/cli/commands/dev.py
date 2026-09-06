"""The ``fluency dev`` command group."""

from __future__ import annotations

from fluency.cli.shared import *  # noqa: F401,F403
from fluency.cli.shared import (  # noqa: F401
    Path, argparse, json, os, re,
    _workspace_path,  # private names are not re-exported by the star import
)

NAME = "dev"


class FluencyRequestHandler(SimpleHTTPRequestHandler):
    """Serve app code plus a read-only release mount from the workspace."""

    def __init__(
        self,
        *args: object,
        directory: str,
        releases_directory: Path,
        audit_resolver: LyricsAuditResolver,
        **kwargs: object,
    ) -> None:
        self.releases_directory = releases_directory.resolve()
        self.audit_resolver = audit_resolver
        super().__init__(*args, directory=directory, **kwargs)

    def _send_json(self, payload: bytes, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        request_path = unquote(urlsplit(self.path).path)
        try:
            if request_path == "/lyrics-audit/data/catalog.json":
                self._send_json(self.audit_resolver.catalog_bytes())
                return
            if self.audit_resolver.matches_song_path(request_path):
                self._send_json(self.audit_resolver.song_bytes(request_path))
                return
        except (LyricsAuditServerError, OSError, ValueError, json.JSONDecodeError) as error:
            self._send_json(
                json.dumps({"error": str(error)}, separators=(",", ":")).encode(),
                status=404,
            )
            return
        super().do_GET()

    def translate_path(self, path: str) -> str:
        request_path = unquote(urlsplit(path).path)
        active_lyrics_asset = resolve_active_lyrics_asset(
            self.releases_directory, request_path
        )
        if active_lyrics_asset is not None:
            return str(active_lyrics_asset)
        active_app_asset = resolve_active_app_asset(
            self.releases_directory, request_path
        )
        if active_app_asset is not None:
            return str(active_app_asset)
        if not request_path.startswith("/releases/"):
            return super().translate_path(path)

        relative = PurePosixPath(request_path.removeprefix("/releases/"))
        if any(part in {"", ".", ".."} for part in relative.parts):
            return str(self.releases_directory / ".invalid-release-path")
        candidate = self.releases_directory.joinpath(*relative.parts).resolve()
        try:
            candidate.relative_to(self.releases_directory)
        except ValueError:
            return str(self.releases_directory / ".invalid-release-path")
        return str(candidate)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


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
