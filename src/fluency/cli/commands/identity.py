"""The ``fluency identity`` command group."""

from __future__ import annotations

from fluency.cli.shared import *  # noqa: F401,F403
from fluency.cli.shared import (  # noqa: F401
    Path, argparse, json, os, re,
    _workspace_path,  # private names are not re-exported by the star import
)

NAME = "identity"


def register(subparsers) -> None:
    identity = subparsers.add_parser(
        "identity", help="audit and build explicit card/progress identity mappings"
    )
    identity_actions = identity.add_subparsers(
        dest="identity_command", required=True
    )
    crosswalk = identity_actions.add_parser(
        "crosswalk", help="build an immutable flat legacy progress-alias report"
    )
    crosswalk.add_argument(
        "--workspace", default=os.environ.get("FLUENCY_WORKSPACE")
    )
    crosswalk.add_argument("--migration-id", required=True)
    crosswalk.add_argument("--language", required=True)
    crosswalk.add_argument("--mode", default="speech")
    crosswalk.add_argument("--inventory", type=Path, required=True)
    crosswalk.add_argument(
        "--legacy-index", type=Path, action="append", required=True
    )
    crosswalk.add_argument("--legacy-migration", type=Path, required=True)


def handle_identity(args: argparse.Namespace) -> int:
    workspace = Workspace.load(_workspace_path(args.workspace))
    if args.identity_command == "crosswalk":
        output = write_legacy_crosswalk(
            workspace,
            migration_id=args.migration_id,
            language=args.language,
            mode=args.mode,
            inventory_path=args.inventory,
            legacy_index_paths=args.legacy_index,
            legacy_migration_path=args.legacy_migration,
        )
        report = json.loads((output / "report.json").read_text(encoding="utf-8"))
        counts = report["alias_counts"]
        print(f"Completed immutable progress identity crosswalk: {output}")
        print(
            f"Canonical cards: {report['active_cards']}; resolved aliases: "
            f"{counts.get('resolved', 0)}; ambiguous: {counts.get('ambiguous', 0)}; "
            f"unresolved: {counts.get('unresolved', 0)}."
        )
        print("No source file, Google Sheet row, or active release was modified.")
        return 0
    raise AssertionError(f"Unhandled identity command: {args.identity_command}")


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


def handle(args) -> int:
    return handle_identity(args)
