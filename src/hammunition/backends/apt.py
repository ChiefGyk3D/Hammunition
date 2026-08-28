# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The apt backend.  DESIGN.md §6.

``apt`` via subprocess rather than ``python3-apt``: simpler, identical across
every Debian-family target, and its output can be shown to the operator
verbatim instead of paraphrased.

The half of this module that matters is not installation — that is one
``apt-get`` line — it is **resolution**. D-016 requires that a dry run be able
to tell you a package is unobtainable, which means asking apt before touching
anything, gathering every answer, and reporting them together. AHRL's failure
mode was the opposite: no ``set -e``, no exit-status checks, and a script that
greps the install transcript for error strings afterwards.

Two apt behaviours this module exists to handle correctly, because both look
like "the package does not exist" and neither is:

* ``apt-cache policy nosuchpkg`` **exits 0** and prints nothing to stdout. So a
  package's absence is detected by its stanza being missing, never by an exit
  status.
* A machine whose package lists have never been fetched reports *every* package
  as unknown. Answering "none of these 20 packages exist" there would be a
  confident lie, so :meth:`AptBackend.lists_populated` is checked first and the
  operator is told to refresh instead.

Recommends are deliberately **not** suppressed. ``--no-install-recommends``
would deviate from what every target distribution does by default, and several
ham applications get their runtime data and codecs that way. D-019 is about not
treating Debian Blend *task metapackages* — which are almost entirely
Recommends — as an install default; that is a catalog membership question and
is settled in the catalog, not by a global apt flag applied to everything.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from .base import BackendError, Command, CommandRunner

__all__ = ["APT_LISTS", "AptBackend", "AptPackageState", "parse_policy"]

APT_LISTS = Path("/var/lib/apt/lists")

# apt-get must never open a dialogue: an installer that blocks forever on a
# debconf prompt nobody can see is indistinguishable from a hang.
NONINTERACTIVE = {"DEBIAN_FRONTEND": "noninteractive"}


@dataclass(frozen=True)
class AptPackageState:
    """What apt knows about one package, right now."""

    name: str
    installed: str | None
    """Installed version, or None. apt prints ``(none)``; we do not carry that
    string around because ``"(none)"`` is truthy and has bitten people."""

    candidate: str | None
    """Installable version, or None when apt has no candidate at all."""

    @property
    def known(self) -> bool:
        """Whether apt can install this at all on this machine, as configured."""
        return self.candidate is not None

    @property
    def is_installed(self) -> bool:
        return self.installed is not None


def _version_or_none(value: str) -> str | None:
    value = value.strip()
    return None if value in {"", "(none)"} else value


def parse_policy(stdout: str) -> dict[str, AptPackageState]:
    """Parse ``apt-cache policy`` output into per-package state.

    Stanza format::

        rtl-sdr:
          Installed: (none)
          Candidate: 2.0.1-1
          Version table:

    A package apt does not know produces no stanza, so it is simply absent from
    the result — which is what makes the caller's "asked for, not returned"
    comparison the authoritative test rather than a heuristic on the text.
    """
    states: dict[str, AptPackageState] = {}
    name: str | None = None
    installed: str | None = None
    candidate: str | None = None

    def flush() -> None:
        if name is not None:
            states[name] = AptPackageState(name=name, installed=installed, candidate=candidate)

    for line in stdout.splitlines():
        if not line.strip():
            continue
        if not line[0].isspace() and line.rstrip().endswith(":"):
            flush()
            name = line.rstrip().removesuffix(":")
            installed = candidate = None
            continue
        stripped = line.strip()
        if stripped.startswith("Installed:"):
            installed = _version_or_none(stripped.removeprefix("Installed:"))
        elif stripped.startswith("Candidate:"):
            candidate = _version_or_none(stripped.removeprefix("Candidate:"))
    flush()
    return states


class AptBackend:
    """Resolution and installation through ``apt-get`` / ``apt-cache``."""

    method = "apt"

    def __init__(self, runner: CommandRunner, *, lists_dir: Path = APT_LISTS) -> None:
        self.runner = runner
        self.lists_dir = lists_dir

    # -- resolution (read-only, no privilege) -------------------------------

    def lists_populated(self) -> bool:
        """Whether apt has any package lists fetched.

        A fresh container image has none, and there every package resolves as
        unknown. Distinguishing "you have not run apt-get update" from "this
        software does not exist" is the difference between an actionable error
        and a wrong one.
        """
        if not self.lists_dir.is_dir():
            return False
        # apt names these `<host>_<path>_dists_<suite>_<component>_binary-<arch>_Packages`,
        # optionally with a compression suffix. Matching the `_Packages` infix rather
        # than a full pattern keeps this true across apt versions and acquire methods.
        return any("_Packages" in entry.name for entry in self.lists_dir.iterdir())

    def probe(self, packages: Sequence[str]) -> dict[str, AptPackageState]:
        """Ask apt about every package in one call.

        One call rather than one per package: it is faster, and it means a
        broken apt configuration fails once with one message instead of N
        times with N.
        """
        if not packages:
            return {}
        command = Command(
            # `--` is belt and braces: DEB_PACKAGE already refuses anything that
            # is not a package name, and this makes the argv wrong-by-construction
            # for an option even if that check is ever relaxed.
            argv=("apt-cache", "policy", "--", *packages),
            description=f"Ask apt what it knows about {len(packages)} package(s)",
            requires_root=False,
        )
        result = self.runner.run(command)
        if not result.ok:
            raise BackendError(
                f"apt-cache policy failed (exit {result.returncode}). Resolution "
                f"cannot proceed on a machine whose apt configuration is broken.\n"
                f"{result.stderr.strip()}"
            )
        return parse_policy(result.stdout)

    def unobtainable(self, packages: Sequence[str]) -> list[str]:
        """Packages apt has no candidate for. Sorted, for a stable report."""
        states = self.probe(packages)
        return sorted(p for p in packages if p not in states or not states[p].known)

    # -- execution ----------------------------------------------------------

    def refresh_command(self) -> Command:
        return Command(
            argv=("apt-get", "update"),
            description="Refresh apt package lists",
            requires_root=True,
            env=dict(NONINTERACTIVE),
        )

    def install_commands(self, packages: Iterable[str]) -> list[Command]:
        """One apt-get invocation for the whole set.

        Installing as one transaction rather than one package at a time is what
        lets apt resolve the dependency set once, and it means a conflict is
        reported before anything is unpacked instead of halfway through.
        """
        ordered = sorted(set(packages))
        if not ordered:
            return []
        return [
            Command(
                argv=("apt-get", "install", "--yes", "--", *ordered),
                description=f"Install {len(ordered)} package(s) with apt",
                requires_root=True,
                env=dict(NONINTERACTIVE),
            )
        ]
