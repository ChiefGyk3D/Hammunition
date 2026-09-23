# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Parking and waking a catalogued device.  D-056.

Turning a ``power_control`` block into the exact sysfs writes it means, and
performing them with the effect verified afterwards rather than the exit
status trusted (D-031).

**Nothing here is persisted.** A reboot resets sysfs, every device wakes, and
:func:`parkable` reads the truth back from the bus. There is no state file to
go stale and nothing to reconcile at boot, which is the whole reason this is
three small functions rather than a daemon.

**Nothing here knows about polkit, argparse or the tray.** It is given matched
devices and returns writes. The privileged boundary is
:mod:`hammunition.cli.devctl`; the surfaces are the CLI, the menu and an applet
in another repository. All three go through the same planner so all three
disclose the same thing.
"""

from __future__ import annotations

import os
import pwd
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from hammunition.manifest.hardware import PowerMethod, QuietVerb

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Mapping

    from hammunition.hardware.detect import Match
    from hammunition.manifest.hardware import DeviceClass, DeviceManifest

__all__ = [
    "ALLOWED_ROOTS",
    "Parkable",
    "PowerError",
    "PowerPlan",
    "Write",
    "execute",
    "guard",
    "parkable",
    "plan_park",
    "plan_wake",
]

ALLOWED_ROOTS = ("/sys/bus/usb/devices", "/sys/bus/pci/devices")
"""The only directories a device node may sit directly beneath.

Two, not one, because ``pci_runtime`` is schema-valid now and its helper
support lands with the card that proves it. A root added here without a
method that uses it widens the guard for nothing.
"""


class PowerError(Exception):
    """A park or wake could not be planned or performed."""


@dataclass(frozen=True)
class Write:
    """One sysfs file and the value to put in it."""

    path: str
    value: str


@dataclass(frozen=True)
class PowerPlan:
    """The ordered writes a park or wake means, and the consumers to hush."""

    writes: tuple[Write, ...]
    quiet: tuple[QuietVerb, ...]
    restore: bool
    """False on a park (hush the consumer), True on a wake (restore it)."""


@dataclass(frozen=True)
class Parkable:
    """A catalogued device, attached now, that can be parked."""

    name: str
    summary: str
    method: PowerMethod
    quiet: tuple[QuietVerb, ...]
    sysfs_path: str
    identifier: str
    """``vendor:product`` as the bus reported it, so a caller can confirm the
    node still holds the same device before writing to it."""

    parked: bool

    @property
    def address(self) -> str:
        """The bus address alone (``1-4``), which is what distinguishes two
        devices of the same class and so what the operator types."""
        return Path(self.sysfs_path).name


def guard(path: str) -> str:
    """Refuse any path that is not a file inside a device node under an allowed root.

    **The trap this exists for is that a real device node is itself a
    symlink.** ``/sys/bus/usb/devices/1-4`` points into
    ``/sys/devices/pci0000:00/…``, so the obvious containment check --
    ``Path(p).resolve().is_relative_to(root)`` -- refuses every device on the
    machine. Written the other obvious way, without resolving, it accepts
    ``…/devices/../../../etc/shadow``.

    So neither: the *lexical* path is normalised without touching the
    filesystem (``os.path.normpath`` collapses ``..`` textually), and the
    result must sit strictly below one of the roots. What the node is a
    symlink to is then irrelevant, because we never followed it.
    """
    normalised = os.path.normpath(path)
    for root in ALLOWED_ROOTS:
        prefix = root.rstrip("/") + "/"
        if normalised.startswith(prefix) and len(normalised) > len(prefix):
            return normalised
    raise PowerError(
        f"{path!r} is outside the device roots this may write to "
        f"({', '.join(ALLOWED_ROOTS)}). A power-control write goes to a device "
        f"node and nowhere else; refusing before any write, not after."
    )


def _read(path: Path) -> str | None:
    try:
        return path.read_text().strip()
    except (OSError, UnicodeDecodeError):
        return None


def parkable(
    matches: list[Match],
    entries: Mapping[str, DeviceClass | DeviceManifest],
) -> tuple[list[Parkable], list[tuple[str, str]]]:
    """Which matched, attached devices can be parked — and which cannot, with why.

    An **ambiguous** match (D-028) is parkable. D-028 governs giving a device a
    persistent name, where being wrong is silent and permanent; parking is a
    reversible unplug of a device the operator has named, and being wrong is
    immediately visible and undone by ``wake``.

    A device the catalog does not mark parkable is not skipped-with-a-reason;
    it simply is not one, and returning it as a refusal would fill the report
    with every device on the bus.
    """
    found: list[Parkable] = []
    skipped: list[tuple[str, str]] = []
    for match in matches:
        entry = entries.get(match.name)
        if entry is None or entry.power_control is None:
            continue
        if not match.attached.sysfs_path:
            skipped.append(
                (match.name, "no sysfs node recorded for it, so there is nothing to write to")
            )
            continue
        node = Path(match.attached.sysfs_path)
        state = _read(node / "authorized")
        if state is None:
            skipped.append(
                (
                    match.name,
                    f"{node / 'authorized'} could not be read, so whether it is parked "
                    f"is unknown; not every bus exposes it and the device may have "
                    f"been unplugged",
                )
            )
            continue
        found.append(
            Parkable(
                name=match.name,
                summary=entry.summary,
                method=entry.power_control.method,
                quiet=tuple(entry.power_control.quiet),
                sysfs_path=str(node),
                identifier=match.attached.identifier,
                parked=state == "0",
            )
        )
    return found, skipped


def _usb_writes(p: Parkable, *, park: bool) -> tuple[Write, ...]:
    node = Path(p.sysfs_path)
    if park:
        return (
            Write(path=guard(str(node / "authorized")), value="0"),
            Write(path=guard(str(node / "power" / "control")), value="auto"),
        )
    # Waking writes `authorized` alone. Restoring power/control to "on" would
    # undo a runtime-PM setting the operator or a udev rule may own -- the
    # DW5930e on the field laptop has exactly such a rule -- and an authorized
    # device is not suspended in any case.
    return (Write(path=guard(str(node / "authorized")), value="1"),)


def _plan(p: Parkable, *, park: bool) -> PowerPlan:
    if p.method == "pci_runtime":
        raise PowerError(
            f"{p.name!r} declares method 'pci_runtime', which is not implemented. "
            f"It is schema-valid so a wwan-modem class can carry it, and it ships "
            f"refused until a card has proved it here: nothing is shipped that has "
            f"not been run."
        )
    return PowerPlan(writes=_usb_writes(p, park=park), quiet=p.quiet, restore=not park)


def plan_park(p: Parkable) -> PowerPlan:
    """The writes that detach ``p`` and let its port suspend."""
    return _plan(p, park=True)


def plan_wake(p: Parkable) -> PowerPlan:
    """The writes that bring ``p`` back."""
    return _plan(p, park=False)


def _invoking_uid() -> int | None:
    """The user behind ``pkexec``, or None when there is no such user.

    ``PKEXEC_UID`` is set by pkexec and by nothing else, so under ``sudo`` or a
    direct root invocation it is simply absent. That is a normal way to run the
    helper, not an error, and it must never raise: by the time the quiet verbs
    run the hardware write has already happened, which is the worst moment in
    the whole operation to take an exception.
    """
    raw = os.environ.get("PKEXEC_UID")
    if not raw:
        return None
    try:
        uid = int(raw)
    except ValueError:
        return None
    try:
        pwd.getpwuid(uid)
    except KeyError:
        return None
    return uid


def _nm_autoconnect(*, restore: bool, uid: int | None) -> str:
    """Set ``connection.autoconnect`` on the profiles NetworkManager would
    bring up, so a parked device is not woken by an autoconnect a second later.

    Runs as the invoking user where there is one: NetworkManager profiles are
    per-user for a user-owned connection, and doing this as root would edit the
    system's rather than the operator's.
    """
    value = "yes" if restore else "no"
    argv = ["nmcli", "--terse", "--fields", "NAME", "connection", "show"]
    prefix: list[str] = []
    if uid is not None:
        prefix = ["setpriv", "--reuid", str(uid), "--regid", str(uid), "--clear-groups", "--"]
    try:
        listed = subprocess.run([*prefix, *argv], capture_output=True, text=True, check=False)
    except (FileNotFoundError, PermissionError) as exc:
        return f"networkmanager_autoconnect: could not run nmcli ({exc}); nothing hushed"
    if listed.returncode != 0:
        return (
            f"networkmanager_autoconnect: nmcli exited {listed.returncode}; no profile was changed"
        )
    names = [n for n in listed.stdout.splitlines() if n.strip()]
    for name in names:
        subprocess.run(
            [*prefix, "nmcli", "connection", "modify", name, "connection.autoconnect", value],
            capture_output=True,
            text=True,
            check=False,
        )
    return f"networkmanager_autoconnect: set autoconnect {value} on {len(names)} profile(s)"


def execute(plan: PowerPlan, *, uid: int | None = None) -> list[str]:
    """Perform the plan. Returns the problems; an empty list is success.

    **The hardware writes come first and the quiet verbs after** (or, on a
    wake, the verbs after too). A verb is a courtesy to a consumer, not a
    precondition of the hardware step, so a machine with no NetworkManager
    still parks its GPS.

    Every write is read back and compared. D-031: ``write_text`` returning a
    byte count is not evidence that a byte reached the device.

    **Every path is re-checked by** :func:`guard` **here, at the write, not
    only at whoever assembled the plan.** This is the function that runs as
    root behind a polkit action, so it is the last place containment can be
    enforced before a byte reaches a device node -- a plan built safely today
    is not a guarantee about how a plan is built tomorrow, and a check that
    fires only where the plan happened to be assembled is a check with an
    escape hatch built in.
    """
    problems: list[str] = []
    for write in plan.writes:
        target = Path(guard(write.path))
        try:
            target.write_text(write.value)
        except OSError as exc:
            problems.append(f"{write.path}: could not write {write.value!r} ({exc})")
            continue
        seen = _read(target)
        if seen != write.value:
            problems.append(
                f"{write.path}: wrote {write.value!r} and read back {seen!r} — "
                f"the write reported success and did not take"
            )
    resolved = _invoking_uid() if uid is None else uid
    for verb in plan.quiet:
        if verb == "networkmanager_autoconnect":
            outcome = _nm_autoconnect(restore=plan.restore, uid=resolved)
            if "could not" in outcome or "exited" in outcome:
                problems.append(outcome)
    return problems
