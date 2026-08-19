"""Command-line entry point for local Fluency development."""

from __future__ import annotations

import argparse
import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Sequence


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 4173


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
    return parser


def serve_app(host: str, port: int) -> None:
    app_directory = project_root() / "app"
    if not app_directory.is_dir():
        raise SystemExit(f"App directory does not exist: {app_directory}")

    handler = partial(SimpleHTTPRequestHandler, directory=str(app_directory))
    server = ThreadingHTTPServer((host, port), handler)
    print(f"Serving Fluency Next from {app_directory}")
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
        serve_app(args.host, args.port)
        return 0
    raise AssertionError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())

