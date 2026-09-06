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
- **exited-clean** — exit 0 before the timeout with nothing on stderr that
  names a fault. Some GUIs background themselves and this is fine; some
  print ``--help`` and quit, which is not. The report lists them for a
  human eye rather than guessing.
- **suspect** — exit 0 before the timeout *with* a fault line on stderr: a
  traceback, a Java ``Caused by:``, the dynamic loader, Qt's platform
  plugin, a segfault, no display. yaac on a headless JRE did exactly this
  (issue #31): HeadlessException at the splash screen, then exit 0. By
  exit status alone that was `exited-clean`; the verdict reads stderr too,
  and the tail leads with the fault line rather than the last four frames.
  Counts as red, like `failed`.
- **failed** — non-zero exit, with the stderr tail that says why. This is
  the category the lane exists for: the missing shared library, the
  instant segfault, the Qt platform plugin that is not there.

A `failed` row is a *finding*, not automatically a bug in the catalog — a
sound-card app may legitimately refuse a machine with no audio device. The
report exists so a human reads the tail and decides; nothing here fakes a
verdict (D-031: the effect is what was observed, and what was observed is
what is reported).

**Run it in the foreground, not detached.** Under ``nohup`` on a box that
already has a display server running (a logged-in Wayland/X session),
``xvfb-run`` can block on a display lock and the whole sweep wedges with no
output — Python block-buffers stdout when it is not a tty, so you see
nothing. Run it attached (progress prints per entry), or on a genuinely
headless VM with no competing session. This lane wants eyes on it anyway:
"it launched" is a weaker claim than "it came up correctly", and the second
is a human's call.

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
    result = subprocess.run(["dpkg", "-L", *packages], capture_output=True, text=True)
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
                if subprocess.run(["dpkg-query", "-W", p], capture_output=True).returncode == 0
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


# Lines that name a launch fault. Anchored to how the faults actually print,
# not to the word "error": a Python traceback header, the JVM's `Exception in
# thread "..."` line, a Java `Caused by:` or a bare `pkg.SomeException:` line,
# the dynamic loader, Qt's platform plugin, a segfault, and the two ways X
# reports no display. `ErrorDialog.class` and "INFO no errors" must not match
# -- a lane that cries wolf gets ignored.
FAULT = re.compile(
    r"^(?:Traceback \(most recent call last\)"
    r"|Exception in thread \""
    r"|Caused by: "
    r"|(?:[A-Za-z_][\w$]*\.)+[A-Z]\w*(?:Exception|Error)\b"
    r"|[A-Z]\w*(?:Exception|Error): "
    r"|.*error while loading shared libraries: "
    r"|qt\.qpa\.plugin: "
    r"|Segmentation fault"
    r"|.*\bcannot open display\b"
    r"|.*\bcould not connect to display\b"
    r")"
)


def classify(rc: int, stderr: str) -> tuple[str, str]:
    """('alive'|'exited-clean'|'suspect'|'failed', the tail worth reading).

    The verdict reads the exit status *and* stderr. yaac on a headless JRE
    raised java.awt.HeadlessException at the splash screen and exited 0
    (issue #31): by exit status alone that is `exited-clean`, the same
    bucket as a program that printed --help and left. With a fault line on
    stderr it is `suspect`, and the tail leads with that line rather than
    with whichever four stack frames happened to come last.
    """
    lines = stderr.strip().splitlines()
    faults = [i for i, line in enumerate(lines) if FAULT.match(line)]
    # A Java trace names the wrapper first and the real fault in its last
    # `Caused by:` -- InvocationTargetException says nothing; the
    # HeadlessException under it says everything. Lead with the innermost.
    causes = [i for i in faults if lines[i].startswith("Caused by: ")]
    first_fault = causes[-1] if causes else faults[0] if faults else None
    if first_fault is None:
        tail = "\n".join(lines[-4:])
    else:
        tail = "\n".join(lines[first_fault : first_fault + 4])
    if rc == 124:
        return "alive", tail
    if rc == 0:
        return ("suspect" if first_fault is not None else "exited-clean"), tail
    return "failed", tail


def smoke(cmd: str, timeout: int) -> tuple[str, int, str]:
    """('alive'|'exited-clean'|'suspect'|'failed', rc, stderr tail)."""
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
    verdict, tail = classify(result.returncode, result.stderr)
    return verdict, result.returncode, tail


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=int, default=8)
    parser.add_argument("--only", nargs="*", default=[])
    args = parser.parse_args()

    todo = collect(args.only)
    total = sum(len(v) for v in todo.values())
    print(f"# GUI smoke — {total} desktop entr(ies) across {len(todo)} unit(s)\n")

    counts = {"alive": 0, "exited-clean": 0, "suspect": 0, "failed": 0}
    failures: list[str] = []
    suspects: list[str] = []
    early: list[str] = []
    for unit, entries in todo.items():
        for entry, cmd in entries:
            verdict, rc, tail = smoke(cmd, args.timeout)
            counts[verdict] += 1
            mark = {"alive": "✓", "exited-clean": "○", "suspect": "?", "failed": "✗"}[verdict]
            # flush each line so a foreground run shows live progress rather
            # than one silent block at the end (the nohup wedge lesson).
            print(f"[{mark}] {unit}: {entry} — {verdict} (rc={rc})", flush=True)
            if verdict == "failed":
                failures.append(f"### {unit} — {entry}\nrc={rc}\n```\n{tail}\n```")
            elif verdict == "suspect":
                suspects.append(f"### {unit} — {entry}\nrc=0\n```\n{tail}\n```")
            elif verdict == "exited-clean" and tail:
                early.append(f"- {unit} / {entry}: {tail.splitlines()[-1][:120]}")

    print(
        f"\n**{counts['alive']} alive, {counts['exited-clean']} exited clean, "
        f"{counts['suspect']} suspect, {counts['failed']} failed** of {total}."
    )
    if failures:
        print("\n## Failures — read the tail, then decide\n")
        print("\n\n".join(failures))
    if suspects:
        print("\n## Exited 0 with a fault on stderr — read the tail, then decide\n")
        print("\n\n".join(suspects))
    if early:
        print("\n## Exited clean before the timeout — worth a human eye\n")
        print("\n".join(early))
    return 1 if counts["failed"] or counts["suspect"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
