# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Parking and waking a catalogued device.  D-056.

Turning a ``power_control`` block into the exact sysfs writes it means, and
performing them with the effect verified afterwards rather than the exit
status trusted (D-031).

**What persists is intent, not state.** A parked device stays parked through
one udev rule per device in `KEPT_RULES`, applied by udev as the device
appears. Whether a device *is* parked is still read from sysfs by
:func:`parkable`; the file only says what the operator asked for, and `state`
reports both.

**Nothing here knows about polkit, argparse or the tray.** It is given matched
devices and returns writes. The privileged boundary is
:mod:`hammunition.cli.devctl`; the surfaces are the CLI, the menu and an applet
in another repository. All three go through the same planner so all three
disclose the same thing.
"""

from __future__ import annotations

import contextlib
import fcntl
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from hammunition.manifest.hardware import PowerMethod, QuietVerb

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Iterable, Iterator, Mapping

    from hammunition.hardware.detect import Match
    from hammunition.manifest.hardware import DeviceClass, DeviceManifest

__all__ = [
    "ALLOWED_ROOTS",
    "KEPT_RULES",
    "KeptEntry",
    "Parkable",
    "PowerError",
    "PowerPlan",
    "Write",
    "execute",
    "guard",
    "kept_entry",
    "parkable",
    "parse_kept",
    "plan_forget",
    "plan_park",
    "plan_wake",
    "read_kept",
    "render_kept",
]

ALLOWED_ROOTS: tuple[str, ...] = ("/sys/bus/usb/devices", "/sys/bus/pci/devices")
"""The only directories a device node may sit directly beneath.

Two, not one, because ``pci_runtime`` is schema-valid now and its helper
support lands with the card that proves it. A root added here without a
method that uses it widens the guard for nothing.

Annotated as ``tuple[str, ...]`` rather than left to inference: a
``tuple[str, str]`` would make ``monkeypatch.setattr(power, "ALLOWED_ROOTS",
(*power.ALLOWED_ROOTS, str(tmp_path)))`` in the test fixture a type error the
moment anyone runs mypy over the tests, for a widening this module's own
tests need to do honestly.
"""

WRITABLE_LEAVES = ("authorized", "power/control")
"""The only files this module ever writes under a device node.

guard() pins the leaf as well as the root because a node's own contents are
not safe by virtue of being under it: every USB node carries kernel-made
symlinks -- driver/unbind, subsystem/drivers_probe, driver/module/parameters
-- that are root-writable and would otherwise pass a root-only check. Two
filenames is the whole legitimate surface, so naming them closes the class.
"""


KEPT_RULES = "/etc/udev/rules.d/66-hammunition-kept.rules"
"""The one file outside sysfs this module writes: devices kept parked across
reboots. udev applies it as a device appears, so nothing runs at boot. Named
66 to run after Hammunition's own 65-hammunition.rules."""

KEPT_HEADER = (
    "# Written by hammunition-devctl (D-056): devices kept parked across reboots.\n"
    "# Change it with `hammunition hardware park` and `wake`, not by hand.\n"
)

_ADDRESS = re.compile(r"\d+-\d+(\.\d+)*")
_HEX4 = re.compile(r"[0-9a-f]{4}")
_NAME = re.compile(r"[a-z0-9][a-z0-9-]*")
_RULE = re.compile(
    r'ACTION=="add", SUBSYSTEM=="usb", ENV\{DEVTYPE\}=="usb_device", '
    r'KERNEL=="(?P<address>[^"]*)", ATTR\{idVendor\}=="(?P<vendor>[^"]*)", '
    r'ATTR\{idProduct\}=="(?P<product>[^"]*)", ATTR\{authorized\}="0"'
)
_NAME_LINE = "# kept: "


@dataclass(frozen=True)
class KeptEntry:
    """One device kept parked: the port it sits in and what it is."""

    name: str
    address: str
    vendor: str
    product: str

    def rule(self) -> str:
        return (
            f'ACTION=="add", SUBSYSTEM=="usb", ENV{{DEVTYPE}}=="usb_device", '
            f'KERNEL=="{self.address}", ATTR{{idVendor}}=="{self.vendor}", '
            f'ATTR{{idProduct}}=="{self.product}", ATTR{{authorized}}="0"'
        )

    def same_device(self, other: KeptEntry) -> bool:
        """Port and model together. The name is a label, not identity."""
        return (self.address, self.vendor, self.product) == (
            other.address,
            other.vendor,
            other.product,
        )


def _validated(entry: KeptEntry) -> KeptEntry:
    for field, value, pattern in (
        ("name", entry.name, _NAME),
        ("address", entry.address, _ADDRESS),
        ("vendor", entry.vendor, _HEX4),
        ("product", entry.product, _HEX4),
    ):
        if not pattern.fullmatch(value):
            raise PowerError(
                f"refusing to keep {entry.name!r} parked: its {field} {value!r} is not "
                f"the shape a USB {field} has, and nothing else may reach a udev rule "
                f"that root applies"
            )
    return entry


def kept_entry(p: Parkable) -> KeptEntry:
    """The entry that keeps ``p`` parked, from values read off the device."""
    vendor, _, product = p.identifier.lower().partition(":")
    return _validated(KeptEntry(p.name, p.address, vendor, product))


def render_kept(entries: Iterable[KeptEntry]) -> str:
    body = "".join(
        f"{_NAME_LINE}{e.name}\n{e.rule()}\n"
        for e in sorted(set(entries), key=lambda e: (e.address, e.vendor, e.product, e.name))
    )
    return KEPT_HEADER + body


def parse_kept(text: str) -> list[KeptEntry]:
    """Read the file back. A line this module did not write is a refusal, never
    skipped: rewriting a file that holds somebody else's rule would delete it."""
    header = set(KEPT_HEADER.splitlines())
    entries: list[KeptEntry] = []
    pending: str | None = None
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip() or line in header:
            continue
        if line.startswith(_NAME_LINE) and pending is None:
            pending = line[len(_NAME_LINE) :]
            continue
        match = _RULE.fullmatch(line)
        if pending is None or match is None:
            raise PowerError(
                f"{KEPT_RULES} line {number} was not written by Hammunition: {line!r}. "
                f"Refusing to rewrite a file holding a rule it does not own; move that "
                f"line to a file of its own and try again."
            )
        entries.append(
            _validated(KeptEntry(pending, match["address"], match["vendor"], match["product"]))
        )
        pending = None
    if pending is not None:
        raise PowerError(f"{KEPT_RULES} ends with '# kept: {pending}' and no rule after it")
    return entries


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
    keep: KeptEntry | None = None
    """On a park: the entry to add so the device stays parked. None with --until-reboot."""
    forget: KeptEntry | None = None
    """On a wake, a forget or a park --until-reboot: the entry to remove, if it is there."""


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
    """Refuse any path that is not one of ``WRITABLE_LEAVES`` inside a device
    node under an allowed root.

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

    **Sitting under a root is not enough on its own.** Every USB node carries
    kernel-made symlinks -- ``driver``, ``subsystem``, ``remove`` -- and
    writing to what is reachable through them (``driver/unbind``,
    ``subsystem/drivers_probe``) is root-writable and has nothing to do with
    parking a device. A *suffix* test on ``WRITABLE_LEAVES`` is not enough
    either: ``driver`` and ``subsystem`` are themselves symlinks, so
    ``<address>/driver/authorized`` ends in a permitted leaf while pointing
    clean out of the node it claims to be inside. The check below is
    structural instead -- the path under the root must be *exactly* one
    address component followed by one of ``WRITABLE_LEAVES``, nothing more
    and nothing fewer, so no intermediate segment gets to ride a permitted
    leaf name out of the node.
    """
    normalised = os.path.normpath(path)
    for root in ALLOWED_ROOTS:
        prefix = root.rstrip("/") + "/"
        if not normalised.startswith(prefix):
            continue
        rest = normalised[len(prefix) :].split("/")
        # `rest` must be the node's address (one non-empty component -- a PCI
        # address like `0000:00:14.0` is one component too, `:` and `.` are
        # not separators) followed by exactly one of the two writable
        # leaves. Anything shorter, longer, or with an empty component from
        # a stray slash is not a shape this module ever writes to.
        if len(rest) >= 2 and rest[0] and "" not in rest:
            leaf = "/".join(rest[1:])
            if leaf in WRITABLE_LEAVES:
                return normalised
        raise PowerError(
            f"{path!r} is not one of the files this module writes "
            f"({', '.join(WRITABLE_LEAVES)}). A device node carries kernel-made "
            f"symlinks -- driver/unbind, subsystem/drivers_probe -- that sit "
            f"under the same root and are not ours to write to."
        )
    raise PowerError(
        f"{path!r} is outside the device roots this may write to "
        f"({', '.join(ALLOWED_ROOTS)}). A power-control write goes to a device "
        f"node and nowhere else; refusing before any write, not after."
    )


def _guard_kept(path: str) -> str:
    """The rules file and nothing else: an exact match against `KEPT_RULES`.

    Deliberately not a branch of :func:`guard`. guard() is also the check
    :func:`execute` runs on every sysfs write, so admitting the rules file
    there would let a plan carrying ``Write(KEPT_RULES, 'RUN+=...')`` put a
    rule of its choosing where root's udev applies it. This check is called by
    :func:`_write_kept` alone, whose content is only ever :func:`render_kept`.
    """
    if path != KEPT_RULES:
        raise PowerError(
            f"{path!r} is not {KEPT_RULES}, the one file outside sysfs this module writes"
        )
    return path


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
    if p.quiet:
        raise PowerError(
            f"{p.name!r} declares quiet verbs {list(p.quiet)}, which are not "
            f"implemented. The verb vocabulary is schema-valid so a manifest can "
            f"carry it, and it ships refused for the same reason 'pci_runtime' "
            f"does: the only device that needs hushing a consumer is a WWAN "
            f"modem, whose method is itself refused until a card proves it here. "
            f"Nothing is shipped that has not been run."
        )
    return PowerPlan(writes=_usb_writes(p, park=park), quiet=p.quiet, restore=not park)


def plan_park(p: Parkable, *, keep: bool = True) -> PowerPlan:
    """The writes that detach ``p`` and let its port suspend, and, unless
    ``keep`` is false, the entry that keeps it parked across reboots.

    With ``keep`` false (``--until-reboot``) any entry already kept for ``p``
    is removed: the promise is that a reboot wakes it, and an entry left from
    an earlier keeping park would re-park it at boot instead."""
    base = _plan(p, park=True)
    entry = kept_entry(p)
    if keep:
        return PowerPlan(base.writes, base.quiet, base.restore, keep=entry)
    return PowerPlan(base.writes, base.quiet, base.restore, forget=entry)


def plan_wake(p: Parkable) -> PowerPlan:
    """The writes that bring ``p`` back, and removal of its kept entry."""
    base = _plan(p, park=False)
    return PowerPlan(base.writes, base.quiet, base.restore, forget=kept_entry(p))


def plan_forget(entry: KeptEntry) -> PowerPlan:
    """Remove a kept entry for a device that is not attached. No sysfs writes:
    there is no node to write to, and the entry is all that is left of it."""
    return PowerPlan(writes=(), quiet=(), restore=True, forget=entry)


def read_kept() -> list[KeptEntry]:
    path = Path(KEPT_RULES)
    if not path.exists():
        return []
    return parse_kept(path.read_text())


def _reload_udev() -> str | None:
    if shutil.which("udevadm") is None:
        return "udevadm is not on PATH"
    result = subprocess.run(
        ["udevadm", "control", "--reload"], capture_output=True, text=True, check=False
    )
    return (
        None if result.returncode == 0 else (result.stderr.strip() or f"exit {result.returncode}")
    )


def _write_kept(entries: list[KeptEntry]) -> None:
    path = Path(_guard_kept(KEPT_RULES))
    if not entries:
        path.unlink(missing_ok=True)
        return
    # A unique temp name in the same directory, never a fixed one: two helper
    # runs sharing `<name>.tmp` can interleave into one spliced file that
    # parse_kept then refuses forever. Hidden and not `*.rules`, so udev never
    # reads it; unlinked on any failure so nothing is left behind.
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.stem}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(render_kept(entries))
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


@contextlib.contextmanager
def _kept_lock() -> Iterator[None]:
    """Hold an exclusive flock on the rules directory for one read-modify-write,
    so a second helper run reads the first run's result instead of losing it.
    The directory itself is locked, so no lock file is left in rules.d."""
    fd = os.open(Path(_guard_kept(KEPT_RULES)).parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def _apply_kept(plan: PowerPlan) -> list[str]:
    who = plan.keep or plan.forget
    assert who is not None
    try:
        with _kept_lock():
            current = read_kept()
            wanted = [e for e in current if not (plan.forget and e.same_device(plan.forget))]
            if plan.keep and not any(e.same_device(plan.keep) for e in wanted):
                wanted.append(plan.keep)
            if wanted == current:
                return []
            _write_kept(wanted)
            after = read_kept()
    except (OSError, PowerError) as exc:
        if plan.keep:
            return [f"{who.name} is parked now but will not stay parked: {exc}"]
        return [f"{who.name}'s kept entry could not be removed: {exc}"]
    if plan.keep and not any(e.same_device(plan.keep) for e in after):
        return [f"{who.name} is parked now but will not stay parked: the entry did not read back"]
    if plan.forget and any(e.same_device(plan.forget) for e in after):
        return [f"{who.name}'s kept entry is still in {KEPT_RULES} after removing it"]
    reason = _reload_udev()
    if reason is not None:
        if plan.keep:
            return [
                f"udev did not reload its rules ({reason}); the entry applies from the next boot"
            ]
        return [
            f"udev did not reload its rules ({reason}); the removed entry still applies "
            f"to a replug until udev reloads or the machine reboots"
        ]
    return []


def execute(plan: PowerPlan) -> list[str]:
    """Perform the plan's hardware writes. Returns the problems; an empty list is success.

    **This covers the hardware writes only.** There is no quiet-verb step:
    ``PowerPlan.quiet`` is refused non-empty at plan time (see :func:`_plan`),
    so by the time a plan reaches here it is always empty, and what this
    function returns means one thing -- whether the sysfs writes took, not
    also whether some other command's human-readable stdout happened to
    contain a recognised word.

    Every write is read back and compared. D-031: ``write_text`` returning a
    byte count is not evidence that a byte reached the device.

    **Every path is re-checked by** :func:`guard` **here, at the write, not
    only at whoever assembled the plan.** This is the function that runs as
    root behind a polkit action, so it is the last place containment can be
    enforced before a byte reaches a device node -- a plan built safely today
    is not a guarantee about how a plan is built tomorrow, and a check that
    fires only where the plan happened to be assembled is a check with an
    escape hatch built in.

    **A failed write stops the plan; it does not move on to the next one.**
    ``plan_park`` orders its writes ``authorized`` then ``power/control``,
    and ``_usb_writes`` deliberately never restores ``power/control`` on
    wake -- doing so would clobber a runtime-PM setting the operator or a
    udev rule may already own. If the ``authorized`` write raised or did not
    read back and the loop carried on to write ``power/control`` anyway, the
    device would be left with runtime PM enabled while still authorized and
    live -- a side effect no shipped verb undoes, since `wake` only ever
    writes ``authorized``. Stopping at the first problem leaves every write
    after it untouched instead.
    """
    problems: list[str] = []
    for write in plan.writes:
        target = Path(guard(write.path))
        try:
            target.write_text(write.value)
        except OSError as exc:
            problems.append(f"{write.path}: could not write {write.value!r} ({exc})")
            break
        seen = _read(target)
        if seen != write.value:
            problems.append(
                f"{write.path}: wrote {write.value!r} and read back {seen!r} — "
                f"the write reported success and did not take"
            )
            break
    if problems or (plan.keep is None and plan.forget is None):
        return problems
    return _apply_kept(plan)
