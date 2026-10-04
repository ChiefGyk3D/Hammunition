# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""Record the documents the console reads from a real engine, safely.

Never run this on a maintainer's machine against the real engine: on 2026-10-03 a
capture overwrote a real station file through a HOME override (console issue #5).
It refuses to run unless the HOME the engine would see is a temporary directory
this module created itself (`capture_home`), outside every real account's home,
and it drops the variables the engine reads to find an owner (USER, LOGNAME,
SUDO_USER) so root cannot reach a real home by another door. The station is set to
the placeholders N0TST / FN31pr, so nothing real is read. Output is scrubbed
(the throwaway home becomes /home/user, this host becomes `host`, this user
`user`) and scanned by fixture_scan.py; a finding aborts the write and names the
line, because a fixture must be reviewed by a person before commit.

Run it from a container or a throwaway VM, with the repository's tests directory on
PYTHONPATH:

  PYTHONPATH=tests python3 -m console.capture_fixtures --engine "hammunition" \\
      --docs docs/reference/json-interface.md

The engine's own `engine` field is not read by the console any more (one release,
one version), so a recording needs no version match.
"""

from __future__ import annotations

import argparse
import contextlib
import getpass
import json
import os
import pwd
import re
import shlex
import socket
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from .fixture_scan import findings, host_pattern, live_identity_findings

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SENTINEL = ".hammunition-capture-home"
# What the engine reads to decide whose home it is working in; none may reach it.
OWNER_VARIABLES = ("USER", "LOGNAME", "SUDO_USER", "XDG_RUNTIME_DIR")


class UnsafeHome(RuntimeError):
    """The engine was about to run where it could reach an operator's real files."""


def _real_homes() -> set[Path]:
    homes = {Path(pw.pw_dir).resolve() for pw in pwd.getpwall() if pw.pw_dir not in ("", "/")}
    homes.add(Path.home().resolve())
    return homes


def assert_safe_home(env: dict[str, str]) -> None:
    """Refuse unless env's HOME is a directory `capture_home` made, under the temp dir."""
    raw = env.get("HOME")
    if not raw:
        raise UnsafeHome("HOME is not set in the environment the engine would get")
    home = Path(raw).resolve()
    try:
        marked = (home / SENTINEL).is_file()
    except OSError:
        marked = False
    if not marked:
        raise UnsafeHome(
            f"{home} was not created by capture_home(); refusing to run the engine there"
        )
    tmp = Path(tempfile.gettempdir()).resolve()
    if tmp not in home.parents:
        raise UnsafeHome(f"{home} is not under the temporary directory {tmp}")
    for real in _real_homes():
        if home == real or real in home.parents or home in real.parents:
            raise UnsafeHome(f"{home} is, or contains, a real account's home")
    for key in OWNER_VARIABLES:
        if key in env:
            raise UnsafeHome(f"{key} is set; the engine would use it to find a real home")
    if os.geteuid() == 0:
        raise UnsafeHome("running as root: refusing; capture in a container as an ordinary user")


@contextlib.contextmanager
def capture_home() -> Iterator[str]:
    """A throwaway home this module owns, marked so assert_safe_home can tell."""
    with tempfile.TemporaryDirectory(prefix="hammunition-capture-") as tmp:
        (Path(tmp) / SENTINEL).write_text("created by capture_fixtures.capture_home\n")
        yield tmp


def capture_env(home: str) -> dict[str, str]:
    env = {
        **os.environ,
        "HOME": home,
        "XDG_CONFIG_HOME": f"{home}/.config",
        "XDG_STATE_HOME": f"{home}/.local/state",
        "XDG_CACHE_HOME": f"{home}/.cache",
        "XDG_DATA_HOME": f"{home}/.local/share",
    }
    for key in OWNER_VARIABLES:
        env.pop(key, None)
    for key in [k for k in env if k.startswith("HAMMUNITION_ACCEPT_")]:
        del env[key]
    return env


STATION = ["--callsign=N0TST", "--grid-square=FN31pr", "--node-alias=TEST"]
REFUSED = "no-such-unit-xyz"
KINDS = [
    "status",
    "doctor",
    "catalog",
    "profile",
    "station",
    "logs",
    "update",
    "plan",
    "error",
    "regions",
    "books",
]

# name -> (words, run before the station is set?)
READS: dict[str, tuple[list[str], bool]] = {
    "station-none": (["station", "show"], True),
    "status": (["status"], False),
    "doctor": (["doctor"], False),
    "list-all": (["list"], False),
    "logs-empty": (["logs"], False),
    "station-set": (["station", "show"], False),
    "show-station": (["show", "station"], False),
    "update-profile": (["update", "station"], False),
    "plan-station": (["install", "station", "--dry-run"], False),
    "plan-uninstall": (["uninstall", "station", "--dry-run"], False),
    "plan-refused": (["install", REFUSED, "--dry-run"], False),
    "books": (["reference", "books"], False),
}


def extract_schemas(markdown: str) -> dict[str, dict[str, Any]]:
    """kind -> the first JSON Schema block under `### <kind>` in json-interface.md."""
    out: dict[str, dict[str, Any]] = {}
    for m in re.finditer(r"^### ([a-z-]+)\n(.*?)(?=^### |\Z)", markdown, re.S | re.M):
        block = re.search(r"```json\n(.*?)\n```", m.group(2), re.S)
        if block:
            out[m.group(1)] = json.loads(block.group(1))
    return out


def scrub(text: str, home: str) -> str:
    text = text.replace(home, "/home/user")
    user = getpass.getuser()
    if len(user) >= 3:
        text = re.sub(re.escape(user), "user", text, flags=re.I)
    host = socket.gethostname().split(".")[0]
    if len(host) >= 3:
        text = host_pattern(host).sub("host", text)
    return text


def run(
    engine: list[str], words: list[str], env: dict[str, str], json_out: bool = True
) -> tuple[int, str]:
    assert_safe_home(env)
    proc = subprocess.run(
        [*engine, *words, *(["--json"] if json_out else [])],
        capture_output=True,
        text=True,
        env=env,
        timeout=900,
        stdin=subprocess.DEVNULL,
    )
    return proc.returncode, proc.stdout


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--engine", default="hammunition", help="the engine command (shell-quoted)")
    ap.add_argument("--out", default=str(FIXTURES))
    ap.add_argument(
        "--suffix", default="", help="appended to the list/update/schema names, e.g. -without"
    )
    ap.add_argument("--only", default="", help="comma-separated fixture names to record")
    ap.add_argument(
        "--docs", default="", help="the engine's docs/reference/json-interface.md, for the schemas"
    )
    args = ap.parse_args(argv)
    engine = shlex.split(args.engine)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    only = {n for n in args.only.split(",") if n}
    suffixed = {"list-all", "update-profile"}

    if args.docs:
        schemas = extract_schemas(Path(args.docs).read_text(encoding="utf-8"))
        (out / "schemas").mkdir(exist_ok=True)
        for kind in KINDS:
            (out / "schemas" / f"{kind}{args.suffix}.json").write_text(
                json.dumps(schemas[kind], indent=2) + "\n", encoding="utf-8"
            )
        print(f"schemas written for {', '.join(KINDS)}")

    with capture_home() as home:
        env = capture_env(home)
        try:
            assert_safe_home(env)
        except UnsafeHome as exc:
            print(f"refusing to capture: {exc}", file=sys.stderr)
            return 2
        problems: list[str] = []
        gated: str | None = None

        def record(name: str, words: list[str]) -> None:
            nonlocal gated
            code, stdout = run(engine, words, env)
            text = scrub(stdout, home)
            bad = [*findings(text), *live_identity_findings(text)]
            if bad:
                problems.append(f"{name}: {bad}")
                return
            suffix = args.suffix if name in suffixed else ""
            (out / f"{name}{suffix}.json").write_text(text, encoding="utf-8")
            exit_file = out / f"{name}{suffix}.exit"
            if code:
                exit_file.write_text(f"{code}\n", encoding="utf-8")
            elif exit_file.exists():
                exit_file.unlink()
            print(f"recorded {name}{suffix} (exit {code})")
            if name == "list-all" and not only:
                doc = json.loads(text)
                gated = next((p["name"] for p in doc["profiles"] if p.get("consent_gated")), None)

        for name, (words, before) in READS.items():
            if before and (not only or name in only):
                record(name, words)
        if not only or "station-set" in only or only - set(READS):
            code, _ = run(engine, ["station", "set", *STATION], env, json_out=False)
            if code:
                print(f"station set failed with exit {code}", file=sys.stderr)
                return 1
        for name, (words, before) in READS.items():
            if not before and (not only or name in only):
                record(name, words)
        if gated and not only:
            record("plan-gated", ["install", gated, "--dry-run"])
            record("show-gated", ["show", gated])
            (out / "manifest.json").write_text(
                json.dumps({"profile": "station", "gated": gated, "refused": REFUSED}, indent=2)
                + "\n",
                encoding="utf-8",
            )
        if problems:
            print("NOT WRITTEN (identifier-like content; review each by hand):", file=sys.stderr)
            for p in problems:
                print(f"  {p}", file=sys.stderr)
            return 1
    print(
        "Review every new file in tests/console/fixtures by eye before committing: the scan is a net, not a guarantee."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
