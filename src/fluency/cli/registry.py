"""Command registry.

Each command module exposes ``NAME``, ``register(subparsers)`` and
``handle(args)``. The root parser walks this list, so neither adding nor removing
a command requires editing a shared parser block or dispatch chain.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any, Protocol


COMMAND_MODULES = (
    "dev", "workspace", "pilot", "frequency", "migration", "enrichment",
    "deployment", "artist", "lyrics", "release", "pools", "pipeline", "identity",
)


class Command(Protocol):
    NAME: str

    def register(self, subparsers: Any) -> None: ...

    def handle(self, args: Any) -> int: ...


def load_commands() -> list[Any]:
    """Import every registered command module, in declared order."""

    return [import_module(f"fluency.cli.commands.{name}") for name in COMMAND_MODULES]
