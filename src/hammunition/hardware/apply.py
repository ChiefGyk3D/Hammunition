# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Planning the hardware role: udev rules and group membership. D-029, M4.

The detection and rule-generation engines already exist (:mod:`.detect`,
:mod:`.udev`); this is the piece that turns them into *what an apply will do to
this machine* — the same disclose-everything-first shape ``install`` has. It
computes a plan and changes nothing; the CLI renders it, and only then runs it.

Two system changes, both idempotent and both disclosed:

- **The rules file.** The whole catalog's rules go to
  ``/etc/udev/rules.d/65-hammunition.rules`` — declarative and harmless for a
  device that is not attached, so writing all of them means a supported device
  works the moment it is plugged in, not only if it happened to be present at
  apply time. If the file on disk already matches, that half is a no-op.
- **Group membership.** The union of the access groups the catalog's devices
  need (``plugdev``, ``dialout``) — added only where the operator is not
  already a member.

Detection is reported alongside but drives nothing (D-020): an apply writes the
same rules whether or not the operator's HackRF is plugged in right now.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from hammunition.hardware.detect import AttachedDevice, Match, match_catalog, read_usb_bus
from hammunition.hardware.udev import RULES_PATH, Omission, rules_file
from hammunition.manifest.hardware import DeviceClass, DeviceManifest

__all__ = ["HardwarePlan", "plan_hardware"]


@dataclass(frozen=True)
class HardwarePlan:
    """What ``hammunition hardware apply`` will do, and what it deliberately won't."""

    user: str
    rules_path: Path
    rules_content: str
    """The complete 65-hammunition.rules the apply will write."""

    rules_already_current: bool
    """True when the file on disk already matches — the write is a no-op."""

    groups_to_add: list[str]
    """Access groups the operator is not yet in; each becomes a gpasswd add."""

    groups_present: list[str]
    """Access groups the operator already has — reported, not touched."""

    omissions: list[Omission]
    """Catalog rules deliberately not emitted, each with why (from udev.py)."""

    detected: list[Match]
    """Recognised devices currently attached. Informational; drives nothing."""

    unrecognised: list[AttachedDevice]
    """Attached devices the catalog does not know — a contributing prompt."""

    @property
    def is_noop(self) -> bool:
        return self.rules_already_current and not self.groups_to_add


def _device_groups(
    classes: dict[str, DeviceClass], devices: dict[str, DeviceManifest]
) -> list[str]:
    """The union of access groups every catalog hardware entry declares.

    A device inherits its class's groups, so both are read. Sorted for a stable
    plan and a stable test.
    """
    groups: set[str] = set()
    for entry in (*classes.values(), *devices.values()):
        groups.update(entry.groups)
    for device in devices.values():
        if device.device_class and device.device_class in classes:
            groups.update(classes[device.device_class].groups)
    return sorted(groups)


def plan_hardware(
    classes: dict[str, DeviceClass],
    devices: dict[str, DeviceManifest],
    *,
    user: str,
    user_groups_now: frozenset[str],
    attached: list[AttachedDevice] | None = None,
    rules_path: str = RULES_PATH,
    sysfs_root: Path | None = None,
) -> HardwarePlan:
    """Resolve a hardware plan. Reads sysfs and the current rules file; writes nothing.

    ``attached`` overrides bus detection (for tests and for a caller that has
    already read it); otherwise sysfs is read here. ``user_groups_now`` is the
    operator's current membership, so the plan adds only what is missing.
    """
    all_entries: list[DeviceClass | DeviceManifest] = [*classes.values(), *devices.values()]
    content, omissions = rules_file(all_entries)

    path = Path(rules_path)
    try:
        current = path.read_text()
    except (OSError, UnicodeDecodeError):
        current = None

    every: dict[str, DeviceClass | DeviceManifest] = {**classes, **devices}
    bus = attached if attached is not None else read_usb_bus(sysfs_root)
    matches, unrecognised = match_catalog(bus, every)

    wanted = _device_groups(classes, devices)
    to_add = [g for g in wanted if g not in user_groups_now]
    present = [g for g in wanted if g in user_groups_now]

    return HardwarePlan(
        user=user,
        rules_path=path,
        rules_content=content,
        rules_already_current=current == content,
        groups_to_add=to_add,
        groups_present=present,
        omissions=omissions,
        detected=matches,
        unrecognised=unrecognised,
    )
