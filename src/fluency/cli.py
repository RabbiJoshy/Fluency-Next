"""Command-line entry point for local Fluency development."""

from __future__ import annotations

import argparse
import json
import os
import re
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from typing import Sequence
from urllib.parse import unquote, urlsplit

from fluency.core.workspace import Workspace
from fluency.pipeline.planning import create_pipeline_plan, load_pipeline_profile
from fluency.release.activation import activate_release
from fluency.release.catalog import build_catalog, write_catalog
from fluency.release.composition import compose_release, load_json_object
from fluency.release.pilot import build_pilot_release
from fluency.release.validation import validate_release_bundle


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 4173
APP_DATA_ROUTES = {
    "/Data/French/vocabulary.index.json": ("fr", "index_path"),
    "/Data/French/vocabulary.examples.json": ("fr", "examples_path"),
    "/Data/Spanish/vocabulary.index.json": ("es", "index_path"),
    "/Data/Spanish/vocabulary.examples.json": ("es", "examples_path"),
    "/Data/Dutch/vocabulary.index.json": ("nl", "index_path"),
    "/Data/Dutch/vocabulary.examples.json": ("nl", "examples_path"),
    "/Data/Portuguese/vocabulary.index.json": ("pt", "index_path"),
    "/Data/Portuguese/vocabulary.examples.json": ("pt", "examples_path"),
}
SAFE_ACTIVE_RELEASE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def project_root() -> Path:
    """Return the repository root for a source checkout."""

    return Path(__file__).resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fluency")
    subparsers = parser.add_subparsers(dest="command", required=True)

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

    workspace = subparsers.add_parser(
        "workspace", help="initialize and inspect the external data workspace"
    )
    workspace_actions = workspace.add_subparsers(
        dest="workspace_command", required=True
    )
    for action, help_text in (
        ("init", "initialize an empty workspace"),
        ("show", "show workspace identity and location"),
        ("doctor", "diagnose workspace safety and layout"),
    ):
        action_parser = workspace_actions.add_parser(action, help=help_text)
        action_parser.add_argument(
            "--path",
            default=os.environ.get("FLUENCY_WORKSPACE"),
            help="workspace root (or set FLUENCY_WORKSPACE)",
        )

    pilot = subparsers.add_parser(
        "pilot", help="build the hand-curated French Speech pilot"
    )
    pilot_actions = pilot.add_subparsers(dest="pilot_command", required=True)
    pilot_build = pilot_actions.add_parser(
        "build", help="publish the deterministic pilot release"
    )
    pilot_build.add_argument(
        "--workspace",
        default=os.environ.get("FLUENCY_WORKSPACE"),
        help="workspace root (or set FLUENCY_WORKSPACE)",
    )

    release = subparsers.add_parser("release", help="compose, inspect, validate, and activate exact releases")
    release_actions = release.add_subparsers(dest="release_command", required=True)
    for action in ("list", "catalog"):
        action_parser = release_actions.add_parser(action)
        action_parser.add_argument("--workspace", default=os.environ.get("FLUENCY_WORKSPACE"))
        action_parser.add_argument("--language", default="fr")
        action_parser.add_argument("--mode", default="speech")
    validate = release_actions.add_parser("validate")
    validate.add_argument("release_id")
    validate.add_argument("--workspace", default=os.environ.get("FLUENCY_WORKSPACE"))
    validate.add_argument("--language", default="fr")
    validate.add_argument("--mode", default="speech")
    activate = release_actions.add_parser("activate")
    activate.add_argument("release_id")
    activate.add_argument("--workspace", default=os.environ.get("FLUENCY_WORKSPACE"))
    activate.add_argument("--language", default="fr")
    activate.add_argument("--mode", default="speech")
    compose = release_actions.add_parser("compose")
    compose.add_argument("--workspace", default=os.environ.get("FLUENCY_WORKSPACE"))
    compose.add_argument("--composition", type=Path, required=True, help="exact release-composition JSON")
    compose.add_argument("--deck", type=Path, required=True, help="already assembled compact deck JSON")

    pipeline = subparsers.add_parser("pipeline", help="plan clean, auditable data runs")
    pipeline_actions = pipeline.add_subparsers(dest="pipeline_command", required=True)
    pipeline_plan = pipeline_actions.add_parser(
        "plan", help="create a non-executing run skeleton from an exact profile"
    )
    pipeline_plan.add_argument(
        "--workspace", default=os.environ.get("FLUENCY_WORKSPACE")
    )
    pipeline_plan.add_argument("--profile", type=Path, required=True)
    return parser


def _workspace_path(raw_path: str | None) -> Path:
    if not raw_path:
        raise SystemExit(
            "Workspace path is required: pass --path or set FLUENCY_WORKSPACE"
        )
    return Path(raw_path)


def resolve_active_app_asset(releases_directory: Path, request_path: str) -> Path | None:
    route = APP_DATA_ROUTES.get(request_path)
    if route is None:
        return None
    language, asset_field = route
    release_root = releases_directory / language / "speech"
    try:
        active = json.loads((release_root / "active.json").read_text(encoding="utf-8"))
        release_id = active["release_id"]
    except (FileNotFoundError, KeyError, TypeError, json.JSONDecodeError):
        return release_root / ".missing-active-app-asset"
    if not isinstance(release_id, str) or SAFE_ACTIVE_RELEASE_ID.fullmatch(release_id) is None:
        return release_root / ".invalid-active-app-asset"
    release_directory = (release_root / release_id).resolve()
    try:
        release_directory.relative_to(release_root.resolve())
    except ValueError:
        return release_root / ".invalid-active-app-asset"
    try:
        manifest = json.loads(
            (release_directory / "manifest.json").read_text(encoding="utf-8")
        )
        relative_path = manifest["app_contract"][asset_field]
    except (FileNotFoundError, KeyError, TypeError, json.JSONDecodeError):
        return release_root / ".missing-active-app-asset"
    if not isinstance(relative_path, str):
        return release_root / ".invalid-active-app-asset"
    candidate = (release_directory / relative_path).resolve()
    try:
        candidate.relative_to(release_directory)
    except ValueError:
        return release_root / ".invalid-active-app-asset"
    return candidate


def handle_workspace(command: str, raw_path: str | None) -> int:
    path = _workspace_path(raw_path)
    if command == "init":
        workspace = Workspace.initialize(path)
        print(f"Initialized Fluency workspace: {workspace.root}")
        print(f"Workspace ID: {workspace.workspace_id}")
        return 0

    workspace = Workspace.load(path)
    if command == "show":
        record = {"path": str(workspace.root), **workspace.to_dict()}
        print(json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if command == "doctor":
        diagnostics = workspace.doctor(code_root=project_root())
        for diagnostic in diagnostics:
            marker = "OK" if diagnostic.ok else "FAIL"
            print(f"[{marker}] {diagnostic.name}: {diagnostic.detail}")
        return 0 if all(item.ok for item in diagnostics) else 1
    raise AssertionError(f"Unhandled workspace command: {command}")


def handle_pilot(command: str, raw_workspace: str | None) -> int:
    workspace = Workspace.load(_workspace_path(raw_workspace))
    if command == "build":
        release_directory = build_pilot_release(workspace)
        print(f"Published French Speech pilot: {release_directory}")
        print("Cards: 25")
        print("WSD: disabled (curated fixture)")
        return 0
    raise AssertionError(f"Unhandled pilot command: {command}")


def handle_release(args: argparse.Namespace) -> int:
    workspace = Workspace.load(_workspace_path(args.workspace))
    if args.release_command == "compose":
        directory = compose_release(workspace, load_json_object(args.composition), load_json_object(args.deck))
        print(f"Composed immutable candidate: {directory}")
        print("Activation unchanged. Validate, then run `fluency release activate ...`.")
        return 0
    if args.release_command == "validate":
        directory = workspace.root / "releases" / args.language / args.mode / args.release_id
        manifest, _, composition = validate_release_bundle(directory)
        print(f"Valid release: {manifest['release_id']}")
        print(f"Layers: {', '.join(sorted(composition['layers']))}")
        return 0
    if args.release_command == "activate":
        path = activate_release(workspace, args.language, args.mode, args.release_id)
        print(f"Activated release: {args.release_id}")
        print(f"Pointer: {path}")
        return 0
    if args.release_command == "catalog":
        path = write_catalog(workspace, args.language, args.mode)
        print(f"Wrote release catalog: {path}")
        return 0
    if args.release_command == "list":
        catalog = build_catalog(workspace, args.language, args.mode)
        for candidate in catalog["candidates"]:
            marker = "*" if candidate["active"] else " "
            print(f"{marker} {candidate['release_id']}  {candidate['card_count']} cards  WSD={candidate['wsd_status']}  fallbacks={candidate['fallback_layers']}")
        return 0
    raise AssertionError(f"Unhandled release command: {args.release_command}")


def handle_pipeline(args: argparse.Namespace) -> int:
    workspace = Workspace.load(_workspace_path(args.workspace))
    if args.pipeline_command == "plan":
        profile = load_pipeline_profile(args.profile)
        run_directory = create_pipeline_plan(workspace, profile)
        target = (
            profile["scope"]["surface_limit"]
            * profile["scope"]["examples_per_surface"]
        )
        print(f"Created fresh pipeline skeleton: {run_directory}")
        print(
            f"Audit target: {profile['scope']['surface_limit']} surface cards, "
            f"{profile['scope']['examples_per_surface']} examples each ({target} total)"
        )
        print("No data stages were executed and no release was activated.")
        return 0
    raise AssertionError(f"Unhandled pipeline command: {args.pipeline_command}")


class FluencyRequestHandler(SimpleHTTPRequestHandler):
    """Serve app code plus a read-only release mount from the workspace."""

    def __init__(
        self,
        *args: object,
        directory: str,
        releases_directory: Path,
        **kwargs: object,
    ) -> None:
        self.releases_directory = releases_directory.resolve()
        super().__init__(*args, directory=directory, **kwargs)

    def translate_path(self, path: str) -> str:
        request_path = unquote(urlsplit(path).path)
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


def serve_app(host: str, port: int, raw_workspace: str | None) -> None:
    app_directory = project_root() / "app"
    if not app_directory.is_dir():
        raise SystemExit(f"App directory does not exist: {app_directory}")
    workspace = Workspace.load(_workspace_path(raw_workspace))
    releases_directory = workspace.root / "releases"

    handler = partial(
        FluencyRequestHandler,
        directory=str(app_directory),
        releases_directory=releases_directory,
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


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "dev":
        serve_app(args.host, args.port, args.workspace)
        return 0
    if args.command == "workspace":
        return handle_workspace(args.workspace_command, args.path)
    if args.command == "pilot":
        return handle_pilot(args.pilot_command, args.workspace)
    if args.command == "release":
        return handle_release(args)
    if args.command == "pipeline":
        return handle_pipeline(args)
    raise AssertionError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
