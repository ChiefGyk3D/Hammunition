#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Smoke-launch every desktop entry the catalog put on this machine.

The install campaigns prove software *installs*; this proves the menu
entries the operator actually sees *launch*. Runs on a VM, headless, under
``xvfb-run`` — every ``.desktop`` file owned by a catalog unit's apt
packages, plus every ``hammunition-*.desktop`` our launcher layer generated,
gets its ``Exec`` line started and eight seconds to live.

Classification is by observed behaviour, not hope:

- **alive** — still running when the timeout landed. A GUI came up (or is
  sitting in a first-run dialog, which counts: it launched).
- **exited-clean** — exit 0 before the timeout. Some GUIs background
  themselves and this is fine; some print ``--help`` and quit, which is
  not. The report lists them for a human eye rather than guessing.
- **failed** — non-zero exit, with the stderr tail that says why. This is
  the category the lane exists for: the missing shared library, the
  instant segfault, the Qt platform plugin that is not there.

A `failed` row is a *finding*, not automatically a bug in the catalog — a
sound-card app may legitimately refuse a machine with no audio device. The
report exists so a human reads the tail and decides; nothing here fakes a
verdict (D-031: the effect is what was observed, and what was observed is
what is reported).

Usage, on the VM, from the repo checkout:
    sudo apt-get install -y xvfb dbus-x11
    .venv/bin/python scripts/vm_gui_smoke.py [--timeout 8] [--only unit ...]
"""

from __future__ import annotations

import argparse
import re
import shlex
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from hammunition.distro import Target  # noqa: E402
from hammunition.manifest.load import load_catalog  # noqa: E402
from hammunition.manifest.schema import AptInstall  # noqa: E402

FIELD_CODES = re.compile(r"%[fFuUdDnNickvm]")


def desktop_exec(path: Path) -> str | None:
    """The Exec line of a .desktop file, field codes stripped."""
    in_entry = False
    try:
        for line in path.read_text(errors="replace").splitlines():
            if line.strip() == "[Desktop Entry]":
                in_entry = True
            elif line.startswith("[") and in_entry:
                break
            elif in_entry and line.startswith("Exec="):
                return FIELD_CODES.sub("", line[len("Exec=") :]).strip()
    except OSError:
        return None
    return None


def dpkg_desktop_files(packages: list[str]) -> list[Path]:
    """Every /usr/share/applications entry the given packages own."""
    result = subprocess.run(
        ["dpkg", "-L", *packages], capture_output=True, text=True
    )
    if result.returncode != 0:
        return []
    return [
        Path(line)
        for line in result.stdout.splitlines()
        if line.startswith("/usr/share/applications/") and line.endswith(".desktop")
    ]


def collect(only: list[str]) -> dict[str, list[tuple[str, str]]]:
    """unit -> [(entry name, exec line)] for everything present on this box."""
    target = Target.detect()
    catalog = load_catalog(REPO_ROOT / "catalog" / "packages")
    todo: dict[str, list[tuple[str, str]]] = {}
    for name, manifest in sorted(catalog.items()):
        if only and name not in only:
            continue
        block = manifest.resolve(target.distro, target.version, target.arch)
        if block is None:
            continue
        entries: list[tuple[str, str]] = []
        if isinstance(block.install, AptInstall):
            installed = [
                p
                for p in block.install.packages
                if subprocess.run(
                    ["dpkg-query", "-W", p], capture_output=True
                ).returncode
                == 0
            ]
            for desktop in dpkg_desktop_files(installed):
                cmd = desktop_exec(desktop)
                if cmd:
                    entries.append((desktop.name, cmd))
        for launcher in manifest.launchers:
            generated = (
                Path.home()
                / ".local"
                / "share"
                / "applications"
                / f"hammunition-{launcher.name}.desktop"
            )
            if generated.exists():
                cmd = desktop_exec(generated)
                if cmd:
                    entries.append((generated.name, cmd))
        if entries:
            todo[name] = entries
    return todo


def smoke(cmd: str, timeout: int) -> tuple[str, int, str]:
    """('alive'|'exited-clean'|'failed', rc, stderr tail)."""
    argv = [
        "timeout",
        "--signal=TERM",
        str(timeout),
        "xvfb-run",
        "-a",
        "-s",
        "-screen 0 1280x800x24",
        "dbus-run-session",
        "--",
        *shlex.split(cmd),
    ]
    result = subprocess.run(argv, capture_output=True, text=True)
    tail = "\n".join(result.stderr.strip().splitlines()[-4:])
    if result.returncode == 124:
        return "alive", 124, tail
    if result.returncode == 0:
        return "exited-clean", 0, tail
    return "failed", result.returncode, tail


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=int, default=8)
    parser.add_argument("--only", nargs="*", default=[])
    args = parser.parse_args()

    todo = collect(args.only)
    total = sum(len(v) for v in todo.values())
    print(f"# GUI smoke — {total} desktop entr(ies) across {len(todo)} unit(s)\n")

    counts = {"alive": 0, "exited-clean": 0, "failed": 0}
    failures: list[str] = []
    early: list[str] = []
    for unit, entries in todo.items():
        for entry, cmd in entries:
            verdict, rc, tail = smoke(cmd, args.timeout)
            counts[verdict] += 1
            mark = {"alive": "✓", "exited-clean": "○", "failed": "✗"}[verdict]
            print(f"[{mark}] {unit}: {entry} — {verdict} (rc={rc})")
            if verdict == "failed":
                failures.append(f"### {unit} — {entry}\nrc={rc}\n```\n{tail}\n```")
            elif verdict == "exited-clean" and tail:
                early.append(f"- {unit} / {entry}: {tail.splitlines()[-1][:120]}")

    print(
        f"\n**{counts['alive']} alive, {counts['exited-clean']} exited clean, "
        f"{counts['failed']} failed** of {total}."
    )
    if failures:
        print("\n## Failures — read the tail, then decide\n")
        print("\n\n".join(failures))
    if early:
        print("\n## Exited clean before the timeout — worth a human eye\n")
        print("\n".join(early))
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
