# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Removal of what Hammunition itself installed.

D-004 and DESIGN.md §7 fix the promise: no rollback, a transaction log, and an
``uninstall`` that removes what Hammunition added and reports honestly on what
it cannot safely reverse. This module is that promise's apt half.

## What "Hammunition installed it" means

Attribution replays the transaction log's ``command_end`` events in order: an
``apt-get install`` that exited 0 attributes the packages after its ``--``; an
``apt-get remove`` that exited 0 un-attributes them. The apt command's own
recorded outcome is the source of truth, not the surrounding transaction —
a run that died on command 3 of 5 still installed whatever command 2
installed, and reading only completed transactions would deny that.

## What is refused, by name

- A unit whose install on this target is not apt (source, git, binary): the
  engine does not yet know how to reverse a ``make install``, and pretending
  with a file sweep would be the shim CLAUDE.md forbids. The refusal names
  the backend.
- A package that is installed but was not installed by Hammunition: it was
  there before us (or arrived by another road), and removing it would exceed
  the promise. It is reported and left in place.

Shared dependencies that apt pulled in are left for ``apt autoremove``, and
the plan says so: removing them by name risks removing what another unit —
or the user's own work — still needs. Group memberships and written config
files are not yet reversed; the log records them, and the plan says that too.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from hammunition.manifest.schema import AptInstall, PackageManifest, ProfileManifest

if TYPE_CHECKING:
    from hammunition.backends.apt import AptPackageState
    from hammunition.distro import Target
    from hammunition.state.log import TransactionLog

__all__ = ["RemovalError", "RemovalPlan", "installed_by_hammunition", "plan_removal"]


class RemovalError(Exception):
    """The removal could not be planned. The message carries every blocker."""


def installed_by_hammunition(log: TransactionLog) -> frozenset[str]:
    """Every apt package the log shows this engine installed and not removed.

    Replayed chronologically from ``command_end`` events with returncode 0.
    Unknown events are ignored, per the log's own reader contract.
    """
    attributed: set[str] = set()
    for entry in log.read():
        if entry.get("event") != "command_end" or entry.get("returncode") != 0:
            continue
        packages = _packages_after_dashes(entry.get("argv"))
        if packages is None:
            continue
        verb = entry["argv"][1]
        if verb == "install":
            attributed.update(packages)
        elif verb == "remove":
            attributed.difference_update(packages)
    return frozenset(attributed)


def _packages_after_dashes(argv: Any) -> list[str] | None:
    """The package arguments of an ``apt-get install``/``remove`` argv, else None."""
    if not isinstance(argv, list) or len(argv) < 2 or argv[0] != "apt-get":
        return None
    if argv[1] not in ("install", "remove"):
        return None
    if "--" not in argv:
        return None
    return [str(p) for p in argv[argv.index("--") + 1 :]]


@dataclass(frozen=True)
class RemovalPlan:
    """What an uninstall will do, and everything it deliberately will not."""

    to_remove: dict[str, list[str]]
    """Unit name -> the apt packages that will be removed for it."""

    left_foreign: dict[str, list[str]]
    """Unit name -> installed packages left in place: not installed by us."""

    already_absent: dict[str, list[str]]
    """Unit name -> attributed packages that are already not installed."""

    apt_packages: tuple[str, ...] = field(init=False)
    """The flat, sorted set the single ``apt-get remove`` will name."""

    def __post_init__(self) -> None:
        flat = sorted({p for packages in self.to_remove.values() for p in packages})
        object.__setattr__(self, "apt_packages", tuple(flat))


def plan_removal(
    names: list[str],
    *,
    catalog: dict[str, PackageManifest],
    profiles: dict[str, ProfileManifest],
    target: Target,
    attributed: frozenset[str],
    states: dict[str, AptPackageState],
) -> RemovalPlan:
    """Resolve names to a removal plan, or raise with every blocker at once.

    ``states`` is the current apt view of every package the plan touches
    (from ``AptBackend.probe``) — what is installed *now*, not what the log
    said at install time.
    """
    blockers: list[str] = []
    units: list[str] = []
    for name in names:
        if name in profiles:
            units.extend(profiles[name].packages)
        elif name in catalog:
            units.append(name)
        else:
            blockers.append(f"{name}: not a package or profile in this catalog")

    to_remove: dict[str, list[str]] = {}
    left_foreign: dict[str, list[str]] = {}
    already_absent: dict[str, list[str]] = {}
    for unit in dict.fromkeys(units):  # preserve order, drop duplicates
        manifest = catalog[unit]
        block = manifest.resolve(target.distro, target.version, target.arch)
        if block is None:
            # Nothing installable here means nothing to remove here; if the
            # log attributed packages under another distro, that machine's
            # log is not this machine's.
            already_absent[unit] = []
            continue
        if not isinstance(block.install, AptInstall):
            blockers.append(
                f"{unit}: installed via the {block.install.method} backend, and "
                f"uninstall for {block.install.method} is not implemented — what "
                f"it wrote is in the transaction log"
            )
            continue
        for package in block.install.packages:
            state = states.get(package)
            currently = state is not None and state.is_installed
            if package in attributed and currently:
                to_remove.setdefault(unit, []).append(package)
            elif currently:
                left_foreign.setdefault(unit, []).append(package)
            else:
                already_absent.setdefault(unit, []).append(package)

    if blockers:
        raise RemovalError(
            "this removal cannot be planned:\n  " + "\n  ".join(sorted(blockers))
        )
    return RemovalPlan(
        to_remove=to_remove, left_foreign=left_foreign, already_absent=already_absent
    )
