#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""A stand-in for `hammunition`, for tests only.

--json reads are answered from tests/fixtures (see respond()). A real `install`
or `hardware apply` behaves like the engine's consent gate: it reads an answer
with input() ONLY when stdin is a tty, prints a prompt, exits 0 on `yes` and 3
otherwise (the engine's "consent declined or not presented"). Nothing here ever
reads the environment for consent. Environment knobs: FAKE_HAMMUNITION_FIXTURES,
FAKE_HAMMUNITION_SUFFIX ("" or "-without": the engine with or without E1/E2),
FAKE_HAMMUNITION_STATION ("set" or "none"), FAKE_HAMMUNITION_LOG (a file that
gets one JSON line per invocation: argv, whether stdin is a tty, and the names
of any HAMMUNITION_ variables it saw).
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

FIXTURES = Path(os.environ.get("FAKE_HAMMUNITION_FIXTURES", Path(__file__).parent / "fixtures"))
VERSION = "0.20.0"


def _read(fixtures: Path, name: str) -> tuple[str, int] | None:
    path = fixtures / f"{name}.json"
    if not path.exists():
        return None
    exit_file = fixtures / f"{name}.exit"
    code = int(exit_file.read_text().strip()) if exit_file.exists() else 0
    return path.read_text(), code


def respond(
    argv: Sequence[str],
    fixtures: Path = FIXTURES,
    suffix: str = "",
    station: str = "set",
    secrets: str = "none",
) -> tuple[str, int] | None:
    """The stdout and exit code for a `--json` read, or None when nobody mapped it."""
    words = [w for w in argv[1:] if w != "--json"]
    manifest = json.loads((fixtures / "manifest.json").read_text())
    if words == ["status"]:
        return _read(fixtures, "status")
    if words == ["doctor"]:
        return _read(fixtures, "doctor")
    if words == ["logs"]:
        return _read(fixtures, "logs")
    if words[:1] == ["list"]:
        return _read(fixtures, f"list-all{suffix}")
    if words[:2] == ["secrets", "status"]:
        return _read(fixtures, f"secrets-{secrets}")
    if words[:2] == ["station", "show"]:
        return _read(fixtures, "station-set" if station == "set" else "station-none")
    if words[:1] == ["update"]:
        names = [w for w in words[1:] if not w.startswith("-")]
        return _read(fixtures, f"update-all{suffix}" if not names else "update-profile")
    if words[:2] == ["maps", "regions"]:
        return _read(fixtures, "regions")
    if words[:2] == ["reference", "books"]:
        return _read(fixtures, "books")
    if words[:1] == ["show"] and len(words) == 2:
        name = words[1]
        if name == manifest["gated"]:
            return _read(fixtures, "show-gated")
        return _read(fixtures, "show-station") if name == manifest["profile"] else None
    if words[:1] in (["install"], ["uninstall"]) and "--dry-run" in words:
        names = [w for w in words[1:] if not w.startswith("-")]
        if words[0] == "uninstall":
            return _read(fixtures, "plan-uninstall")
        if names and names[0] == manifest["refused"]:
            return _read(fixtures, "plan-refused")
        if names and names[0] == manifest["gated"]:
            return _read(fixtures, "plan-gated")
        return _read(fixtures, "plan-station")
    return None


def _ask(prompt: str) -> int:
    if not sys.stdin.isatty():
        print(
            "hammunition: no interactive terminal; a consent gate cannot be answered",
            file=sys.stderr,
        )
        return 3
    print(prompt, end="", flush=True)
    try:
        answer = input()
    except EOFError:
        return 3
    if answer.strip() == "yes":
        print("confirmed")
        return 0
    print("declined")
    return 3


def _record_keys(path: str) -> int:
    """A long-running install: write the hex of every byte read from the tty to `path`
    (and our pid to `path`.pid) until a capital X arrives. Test-only."""
    import termios
    import tty

    Path(path + ".pid").write_text(str(os.getpid()))
    saved = termios.tcgetattr(0)
    tty.setraw(0)
    try:
        print("recording", flush=True)
        while True:
            byte = os.read(0, 1)
            if not byte:
                return 3
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(byte.hex() + "\n")
            if byte == b"X":
                return 0
    finally:
        termios.tcsetattr(0, termios.TCSADRAIN, saved)


def main(argv: list[str]) -> int:
    log = os.environ.get("FAKE_HAMMUNITION_LOG")
    if log:
        entry = {
            "argv": argv,
            "tty": sys.stdin.isatty(),
            "env": sorted(
                k for k in os.environ if k.startswith("HAMMUNITION_") or k.endswith("_CONSENT")
            ),
            # only whether a registered secret's variable is present, never its value
            "secrets_present": [k for k in ("REPEATERBOOK",) if k in os.environ],
        }
        with open(log, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
    if argv == ["--version"]:
        print(f"hammunition {VERSION}")
        return 0
    suffix = os.environ.get("FAKE_HAMMUNITION_SUFFIX", "")
    station = os.environ.get("FAKE_HAMMUNITION_STATION", "set")
    if "--json" in argv:
        secrets = "environment" if os.environ.get("REPEATERBOOK") else "none"
        answered = respond(["hammunition", *argv], FIXTURES, suffix, station, secrets)
        if answered is None:
            print(f"FAKE: unmapped argv {argv!r}", file=sys.stderr)
            return 99
        sys.stdout.write(answered[0])
        return answered[1]
    keys_file = os.environ.get("FAKE_HAMMUNITION_KEYS")
    if keys_file and argv[:1] == ["install"] and "--dry-run" not in argv:
        return _record_keys(keys_file)
    if argv[:1] == ["install"] and "--dry-run" not in argv:
        print(f"Installing {' '.join(argv[1:])}")
        code = _ask("Type 'yes' to continue: ")
        if code == 0:
            print("installed")
        return code
    if argv[:2] == ["hardware", "apply"]:
        print("plan: write udev rules, add groups")
        return _ask("Type 'yes' to apply: ")
    if argv[:3] == ["maps", "repeaters", "fetch-repeaterbook"]:
        print("fetched")
        return 0
    if argv[:2] == ["station", "set"]:
        print("saved")
        return 0
    print(f"FAKE: unmapped argv {argv!r}", file=sys.stderr)
    return 99


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
