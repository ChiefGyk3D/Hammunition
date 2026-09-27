# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``hammunition-devctl`` — the one thing here that runs as root.  D-056.

Three verbs, ``park NAME``, ``wake NAME`` and ``state``, reached through one
polkit action. Every caller -- the CLI, a menu entry, the Plasma applet in
``hammunition-tray`` -- runs *this*, so there is one privileged path to review
rather than three.

**It takes a name and derives everything else itself.** It re-reads the USB
bus and the catalog in this process and computes the paths it writes; an argv
that carried a path would be a way to write anywhere on the system as root,
and an argv that carried a *plan* would be the same thing spelled longer. The
name is the only thing an unprivileged caller supplies, and a name that is not
a parkable attached device is refused before anything happens.

It never reads the operator's station config. Parking a GPS has nothing to do
with a callsign and this process has no business holding one.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from hammunition.hardware.polkit import (
    WritabilityFinding,
    WritabilityRisk,
    describe_refusal,
    writable_including_symlink_target,
)
from hammunition.hardware.power import (
    Parkable,
    PowerError,
    execute,
    parkable,
    plan_park,
    plan_wake,
)

__all__ = ["main", "resolve"]

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_UNPLANNABLE = 2


def _survey() -> tuple[list[Parkable], list[tuple[str, str]]]:
    """What is parkable on this machine right now, read fresh from the bus.

    Fresh on every invocation, never cached and never taken from the caller:
    between an applet's poll and the switch being flipped a device can be
    unplugged, and a USB address can be reused by something else entirely.
    """
    from hammunition.cli.main import find_catalog
    from hammunition.hardware.detect import match_catalog, read_usb_bus
    from hammunition.manifest.hardware import DeviceClass, DeviceManifest
    from hammunition.manifest.load import load_hardware

    classes, devices = load_hardware(find_catalog(None) / "hardware")
    entries: dict[str, DeviceClass | DeviceManifest] = {**classes, **devices}
    matches, _ = match_catalog(read_usb_bus(), entries)
    return parkable(matches, entries)


def resolve(name: str, found: list[Parkable]) -> Parkable:
    """The one parkable device ``name`` refers to, or a refusal that says why.

    ``NAME`` or ``NAME@ADDRESS``. Two receivers of the same class are two
    parkable devices with one catalog name between them, and picking one
    silently would park whichever the bus happened to list first -- so an
    ambiguous name is refused with both addresses, and the operator says which.
    """
    wanted, _, address = name.partition("@")
    candidates = [p for p in found if p.name == wanted]
    if address:
        candidates = [p for p in candidates if p.address == address]
        if not candidates:
            raise PowerError(
                f"no parkable device {wanted!r} at address {address!r} is attached. "
                f"Attached: {_listing(found)}"
            )
    if not candidates:
        raise PowerError(
            f"{name!r} is not a parkable attached device. Parkable now: {_listing(found)}"
        )
    if len(candidates) > 1:
        addresses = ", ".join(f"{p.name}@{p.address}" for p in candidates)
        raise PowerError(
            f"{wanted!r} names {len(candidates)} attached devices and would be a "
            f"guess: {addresses}. Name one of those instead."
        )
    return candidates[0]


def _listing(found: list[Parkable]) -> str:
    if not found:
        return "nothing (no catalogued parkable device is attached)"
    return ", ".join(f"{p.name}@{p.address}" for p in sorted(found, key=lambda p: p.address))


def _do(verb: str, name: str) -> int:
    found, skipped = _survey()
    for unit, why in skipped:
        print(f"note: {unit} is not parkable right now: {why}", file=sys.stderr)
    try:
        target = resolve(name, found)
        plan = plan_park(target) if verb == "park" else plan_wake(target)
    except PowerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_UNPLANNABLE
    problems = execute(plan)
    for problem in problems:
        print(f"unverified: {problem}", file=sys.stderr)
    return EXIT_FAILED if problems else EXIT_OK


def _state() -> int:
    found, skipped = _survey()
    for unit, why in skipped:
        print(f"note: {unit} is not parkable right now: {why}", file=sys.stderr)
    # Always a JSON array, including when it is empty: the applet parses this
    # every five seconds and a human sentence here is a parse error every five
    # seconds.
    print(
        json.dumps(
            [
                {
                    "name": p.name,
                    "summary": p.summary,
                    "address": p.address,
                    "identifier": p.identifier,
                    "method": p.method,
                    "parked": p.parked,
                }
                for p in sorted(found, key=lambda p: (p.name, p.address))
            ]
        )
    )
    return EXIT_OK


def _runtime_writability_findings() -> tuple[WritabilityFinding | None, WritabilityFinding | None]:
    """The same D-056 check ``hardware apply`` runs before install, run again
    here, at the moment this process is actually about to act as root.

    Gated on really being root by the caller: an unprivileged invocation
    (every test in this repository, and a developer running this module
    directly to see what it prints) reading its own writable checkout is not
    the privilege escalation the check exists to catch -- only pkexec's
    elevated process is. A tree that was safe at apply time can still have
    become writable since (a package reinstalled somewhere looser, a
    permission loosened by hand), so this is not redundant with the
    apply-time gate; it is the defence for the gap between "we checked" and
    "we are now running".

    Both paths passed unresolved, deliberately: :func:`writable_including_symlink_target`
    checks the given path *and* its resolved real path, and resolving here
    first would throw away exactly the symlink-holding directory that exists
    to catch (fix round 3).
    """
    interpreter = writable_including_symlink_target(sys.executable)
    package = writable_including_symlink_target(str(Path(os.path.abspath(__file__)).parent.parent))
    return interpreter, package


def _refuse_or_warn_if_unsafe() -> int | None:
    """Returns an exit code this process should return immediately, or
    ``None`` to continue. Only called once the caller has confirmed this
    process is really running as root.

    Fix round 2: round 1 refused outright on *either* fact, which broke the
    project's own documented install -- a venv under `$HOME` is always
    owned by one specific non-root account, never by root, so the check
    fired on every single privileged invocation in the worktree the review
    measured. Only a component writable by *any* local account (not just its
    owner) is the real escalation and gets refused; a component merely owned
    by one non-root account is disclosed with a warning and the process
    proceeds, the same distinction `hardware apply` makes at install time.
    """
    interpreter, package = _runtime_writability_findings()
    refusing = [
        f
        for f in (interpreter, package)
        if f is not None and f.risk is WritabilityRisk.GROUP_OR_OTHER_WRITABLE
    ]
    if refusing:
        print(
            f"error: refusing to run: {describe_refusal(refusing)}, and this process "
            f"is running as root through it. Fix it, then re-run "
            f"`hammunition hardware apply`.",
            file=sys.stderr,
        )
        return EXIT_UNPLANNABLE

    warnings = [
        f
        for f in (interpreter, package)
        if f is not None and f.risk is WritabilityRisk.OWNED_BY_NON_ROOT
    ]
    for finding in warnings:
        print(
            f"warning: {finding.path} is owned by a non-root account, and this "
            f"process is running as root through it. This is the documented "
            f"install (a venv under $HOME); if that account should not be trusted "
            f"with root, fix its ownership.",
            file=sys.stderr,
        )
    return None


def main(argv: list[str] | None = None) -> int:
    if os.geteuid() == 0:
        exit_code = _refuse_or_warn_if_unsafe()
        if exit_code is not None:
            return exit_code

    parser = argparse.ArgumentParser(
        prog="hammunition-devctl",
        description=(
            "Park and wake catalogued devices. Runs as root through polkit; "
            "called by `hammunition hardware`, by the generated menu entries, "
            "and by the Plasma applet in hammunition-tray."
        ),
    )
    sub = parser.add_subparsers(dest="verb", required=True)
    for verb_name, help_text in (
        ("park", "detach a device and let its port suspend"),
        ("wake", "bring a parked device back"),
    ):
        p = sub.add_parser(verb_name, help=help_text)
        p.add_argument(
            "name",
            metavar="NAME",
            help="catalog name, or NAME@ADDRESS when two of a kind are attached",
        )
    sub.add_parser("state", help="JSON: every parkable attached device and whether it is parked")

    args = parser.parse_args(argv)
    if args.verb == "state":
        return _state()
    verb: str = args.verb
    return _do(verb, args.name)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
