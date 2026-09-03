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

And a third that looks like "the packages exist, so they install": a set of
packages that each has a candidate can still be unresolvable **together**.
Parrot's baseline installs 197 packages from its backports release, and a
``-dev`` package from the main release depends on its runtime at an exact
version the machine no longer has. ``apt-cache policy`` cannot see that;
:meth:`AptBackend.simulate` asks ``apt-get install --simulate`` for the whole
transaction, and when the refusal is a downgrade of a package installed from
one other release the plan retries from that release with
``--target-release`` and says so (D-038).

Recommends are deliberately **not** suppressed. ``--no-install-recommends``
would deviate from what every target distribution does by default, and several
ham applications get their runtime data and codecs that way. D-019 is about not
treating Debian Blend *task metapackages* — which are almost entirely
Recommends — as an install default; that is a catalog membership question and
is settled in the catalog, not by a global apt flag applied to everything.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from .base import BackendError, Command, CommandRunner

__all__ = [
    "APT_LISTS",
    "AptBackend",
    "AptPackageState",
    "AptSimulation",
    "downgrades_refused",
    "parse_policy",
    "parse_simulation",
]

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


_INST_LINE = re.compile(
    r"^Inst (?P<name>[^\s:]+)(?::\S+)? \((?P<version>\S+) (?P<origins>.*?) \[[^\]]*\]\)"
)


def parse_simulation(stdout: str) -> dict[str, frozenset[str]]:
    """``package -> archives it would come from``, from the ``Inst`` lines of
    ``apt-get --simulate``.

    Line format, one per package apt would unpack::

        Inst wsjtx-data (2.7.0+repack-1 Debian:13.1/stable [all])
        Inst cmake (3.31.6-2~bpo13+1 Parrot 7 Echo Parakeet:parrot-backports [amd64])
        Inst libkrb5-dev (1.21.3-5+deb13u1 Parrot 7 Echo Parakeet:parrot, Parrot 7 Echo Parakeet:parrot-security [amd64])
        Inst jtdx:i386 (...)

    ``Conf`` lines repeat the same names and ``Remv`` lines are removals, so
    only ``Inst`` counts. The architecture qualifier is dropped: a manifest
    declares a conflict by package name, and ``wsjtx-data:all`` is the same
    files as ``wsjtx-data``. Each origin is ``Label:[Version/]Archive``, and
    a version offered by several archives lists them all, comma-separated;
    the archive names are what let the plan say *which* packages a
    ``--target-release`` transaction takes from that release, measured
    rather than guessed.
    """
    installs: dict[str, frozenset[str]] = {}
    for line in stdout.splitlines():
        if not line.startswith("Inst "):
            continue
        match = _INST_LINE.match(line)
        if match is None:
            # An `Inst` line in a shape this parser has not met still names a
            # package that will be unpacked; the archive is simply unknown.
            installs[line.split()[1].partition(":")[0]] = frozenset()
            continue
        archives = frozenset(
            origin.rpartition(":")[2].rpartition("/")[2] for origin in match["origins"].split(", ")
        )
        installs[match["name"]] = archives
    return installs


_DOWNGRADE_LINE = re.compile(
    r"^\s*(?:\d+\.\s*)?(?P<name>[^\s:=]+)(?::\S+)?=\S+ is selected as a downgrade"
)


def downgrades_refused(error: str) -> list[str]:
    """Installed packages that apt's solver would have to downgrade to satisfy
    the request, from a failed ``apt-get install`` transcript.

    apt 3's solver explains a refusal like this (a clean Parrot 7.3,
    2026-09-02, asking for ``libcurl4-openssl-dev``)::

        E: Unable to correct problems, you have held broken packages.
        E: The following information from --solver 3.0 may provide additional context:
           Unable to satisfy dependencies. Reached two conflicting decisions:
           1. libcurl4t64:amd64=8.14.1-2+deb13u5 is not selected for install
           2. libcurl4t64:amd64=8.14.1-2+deb13u5 is selected as a downgrade because:
              1. libcurl4-openssl-dev:amd64=8.14.1-2+deb13u5 is selected for install
              2. libcurl4-openssl-dev:amd64=8.14.1-2+deb13u5 Depends libcurl4t64 (= 8.14.1-2+deb13u5)

    ``libcurl4t64`` is installed from ``parrot-backports`` at 8.21, the
    archive's default release offers the ``-dev`` at 8.14 with an exact-
    version dependency, and apt (rightly) will not downgrade a library to
    build against it. The name of the package it refuses to downgrade is the
    one clue to the release the transaction has to be resolved from.
    A transcript from another solver, or another kind of failure, yields an
    empty list: nothing is guessed from prose this parser has not measured.
    """
    names: list[str] = []
    for line in error.splitlines():
        match = _DOWNGRADE_LINE.match(line)
        if match is not None and match["name"] not in names:
            names.append(match["name"])
    return names


@dataclass(frozen=True)
class AptSimulation:
    """What ``apt-get install --simulate`` said about one transaction."""

    ok: bool
    installs: dict[str, frozenset[str]] = field(default_factory=dict)
    """``package -> archives`` for every package apt would unpack."""

    error: str = ""
    """apt's own account when ``ok`` is false, verbatim."""

    release: str | None = None
    """The ``--target-release`` the simulation was run with, if any."""

    def from_archive(self, archive: str) -> tuple[str, ...]:
        """Packages this transaction takes from *archive* -- and from nowhere
        else, so a version that the default release offers as well is not
        counted against the target release."""
        return tuple(
            sorted(name for name, archives in self.installs.items() if archives == {archive})
        )


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

    def simulate(self, packages: Sequence[str], *, release: str | None = None) -> AptSimulation:
        """Run apt's resolver over the whole transaction without touching
        anything.

        ``apt-get install --simulate`` runs the real resolver without root and
        without the lock, and prints one ``Inst <name> ...`` line per package
        it would unpack. `apt-cache policy` cannot answer this: it knows that
        `jtdx` has a candidate, not that installing it brings `wsjtx-data`,
        which is the file-level collision the plan needs to see coming -- nor
        that a `-dev` package's exact-version dependency cannot be met without
        a downgrade, which is what a clean Parrot said to six of fifteen
        profiles on 2026-09-02, at the apt step, after the plan had passed.

        A failed simulation is a result, not an exception: the plan reads
        apt's account and decides what it means.
        """
        ordered = sorted(set(packages))
        if not ordered:
            return AptSimulation(ok=True, release=release)
        target = ("--target-release", release) if release is not None else ()
        command = Command(
            argv=("apt-get", "install", "--simulate", "--yes", *target, "--", *ordered),
            description=f"Ask apt how it would install {len(ordered)} package(s)",
            requires_root=False,
            env=dict(NONINTERACTIVE),
        )
        result = self.runner.run(command)
        if not result.ok:
            # apt puts the E: lines and the solver's explanation on stderr;
            # stdout is "Reading package lists..." and worth nothing to a
            # reader of the failure unless stderr is empty.
            error = result.stderr.strip() or result.stdout.strip()
            return AptSimulation(ok=False, error=error, release=release)
        return AptSimulation(ok=True, installs=parse_simulation(result.stdout), release=release)

    def would_install(self, packages: Sequence[str]) -> set[str]:
        """Every package apt would unpack to install *packages* -- the named
        ones and everything they pull in. Raises when apt cannot resolve
        the set; :meth:`simulate` is the form that reports instead."""
        simulation = self.simulate(packages)
        if not simulation.ok:
            raise BackendError(
                "apt-get install --simulate failed. apt cannot resolve this "
                f"transaction, so nothing will be started.\n{simulation.error}"
            )
        return set(simulation.installs)

    def archives(self) -> dict[str, str]:
        """``origin line -> archive name`` for every package file apt reads.

        ``apt-cache policy`` with no arguments lists them::

             599 https://deb.parrot.sh/parrot echo-backports/main amd64 Packages
                 release o=Parrot,a=parrot-backports,n=echo-backports,l=Parrot 7 Echo Parakeet,c=main,b=amd64
                 origin deb.parrot.sh

        The first line is exactly what the per-package ``policy`` prints under
        an installed version, so it is the key that joins the two; ``a=`` is
        the name ``--target-release`` accepts and the one ``Inst`` lines carry.
        """
        result = self.runner.run(
            Command(
                argv=("apt-cache", "policy"),
                description="Ask apt which archives it reads",
                requires_root=False,
            )
        )
        if not result.ok:
            return {}
        archives: dict[str, str] = {}
        origin: str | None = None
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if stripped.startswith("release ") and origin is not None:
                fields = dict(
                    part.split("=", 1)
                    for part in stripped.removeprefix("release ").split(",")
                    if "=" in part
                )
                if "a" in fields:
                    archives[origin] = fields["a"]
                origin = None
            elif stripped and stripped[0].isdigit() and " " in stripped:
                origin = stripped.split(" ", 1)[1]
        return archives

    def installed_archive(self, package: str) -> str | None:
        """The archive the installed version of *package* came from, or None.

        From the version table of ``apt-cache policy <package>``: the ``***``
        row is the installed version and the origin rows beneath it say where
        that version is on offer. ``/var/lib/dpkg/status`` is where every
        installed package is "on offer" and says nothing, so it is skipped;
        a version no configured archive carries any more resolves to None.
        """
        result = self.runner.run(
            Command(
                argv=("apt-cache", "policy", "--", package),
                description=f"Ask apt where the installed {package} came from",
                requires_root=False,
            )
        )
        if not result.ok:
            return None
        archives = self.archives()
        under_installed = False
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if stripped.startswith("***"):
                under_installed = True
                continue
            if not under_installed:
                continue
            # A version row is `<version> <priority>`; an origin row is
            # `<priority> <uri> <suite>/<component> <arch> Packages`. The
            # priority is the integer, and only an origin row has one first.
            head, _, rest = stripped.partition(" ")
            if not (head.isdigit() and rest and not rest.isdigit()):
                break  # the next version row, or the end of the table
            if rest.startswith("/"):
                continue  # /var/lib/dpkg/status: installed, origin unknown
            if rest in archives:
                return archives[rest]
        return None

    # -- execution ----------------------------------------------------------

    def refresh_command(self) -> Command:
        return Command(
            argv=("apt-get", "update"),
            description="Refresh apt package lists",
            requires_root=True,
            env=dict(NONINTERACTIVE),
        )

    def install_commands(
        self, packages: Iterable[str], *, release: str | None = None
    ) -> list[Command]:
        """One apt-get invocation for the whole set.

        Installing as one transaction rather than one package at a time is what
        lets apt resolve the dependency set once, and it means a conflict is
        reported before anything is unpacked instead of halfway through.

        *release* is apt's own ``--target-release``: the plan passes it only
        when it has measured that the transaction resolves from that release
        and from nowhere else (D-038), and it appears in the printed command
        so the operator sees it before it runs.
        """
        ordered = sorted(set(packages))
        if not ordered:
            return []
        target = ("--target-release", release) if release is not None else ()
        where = f" from {release}" if release is not None else ""
        return [
            Command(
                argv=("apt-get", "install", "--yes", *target, "--", *ordered),
                description=f"Install {len(ordered)} package(s) with apt{where}",
                requires_root=True,
                env=dict(NONINTERACTIVE),
            )
        ]

    def remove_commands(self, packages: Iterable[str]) -> list[Command]:
        """One ``apt-get remove`` for the whole set.

        ``remove``, not ``purge``: configuration a user may have edited stays
        on disk, which is the conservative half of D-004's honesty. Dependencies
        apt pulled in are deliberately not named — ``apt autoremove`` exists,
        the uninstall plan points at it, and removing shared dependencies by
        name is how an uninstall breaks a package it never touched.
        """
        ordered = sorted(set(packages))
        if not ordered:
            return []
        return [
            Command(
                argv=("apt-get", "remove", "--yes", "--", *ordered),
                description=f"Remove {len(ordered)} package(s) with apt",
                requires_root=True,
                env=dict(NONINTERACTIVE),
            )
        ]
