# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""The `hammunition console` subcommand's body (the CLI delegates here).

The refusals come first and need no urwid: not a terminal, TERM=dumb, root. urwid
is imported only when the screen is about to be drawn, so `hammunition` itself never
needs it, and its absence is one line on stderr and exit 2.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TextIO

from hammunition.console.context import EngineLike
from hammunition.console.helptext import full_help


def engine_version() -> str:
    """The engine's version: the console has none of its own (one release, one version)."""
    from hammunition.interface import envelope

    return envelope.engine_version()


def _debian_family(os_release: Path = Path("/etc/os-release")) -> bool:
    try:
        text = os_release.read_text()
    except OSError:
        return False
    ids: set[str] = set()
    for line in text.splitlines():
        key, _, value = line.partition("=")
        if key in ("ID", "ID_LIKE"):
            ids.update(value.strip().strip("\"'").split())
    return bool(ids & {"debian", "ubuntu"})


def missing_urwid_line(*, in_venv: bool | None = None, debian: bool | None = None) -> str:
    """The one line printed when urwid cannot be imported.

    A virtualenv does not see the archive's python3-urwid, so inside one the answer is pip
    (bootstrap.sh installs the extra for you); outside one on the Debian family it is apt.
    """
    venv = (sys.prefix != sys.base_prefix) if in_venv is None else in_venv
    deb = _debian_family() if debian is None else debian
    if deb and not venv:
        return "hammunition console needs urwid: run `sudo apt install python3-urwid`."
    return "hammunition console needs urwid: run `pip install 'hammunition[console]'`."


def main(
    argv: Sequence[str] | None = None,
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    environ: Mapping[str, str] | None = None,
    euid: int | None = None,
    engine: EngineLike | None = None,
) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout
    env = os.environ if environ is None else environ
    uid = os.geteuid() if euid is None else euid
    if args in (["--help"], ["-h"]):
        print(full_help(), file=stdout)
        return 0
    if args == ["--version"]:
        print(f"hammunition {engine_version()}", file=stdout)
        return 0
    if args:
        print(f"hammunition console: unknown argument {args[0]!r} (see --help)", file=sys.stderr)
        return 2
    if uid == 0:
        print(
            "hammunition console: do not run this as root. It runs as you and asks for sudo "
            "itself, inside a terminal pane, only for the commands that need it.",
            file=sys.stderr,
        )
        return 2
    if not (stdin.isatty() and stdout.isatty()):
        print(
            "hammunition console needs a terminal (stdin and stdout must both be one).",
            file=sys.stderr,
        )
        return 2
    if env.get("TERM", "dumb") == "dumb":
        print(
            "hammunition console: TERM is 'dumb' or unset; it cannot draw a screen.",
            file=sys.stderr,
        )
        return 2
    try:
        import urwid  # noqa: F401
    except ImportError:
        print(missing_urwid_line(), file=sys.stderr)
        return 2
    from hammunition.console.app import run  # imported late: the refusals above need no urwid

    return run(env, engine)
