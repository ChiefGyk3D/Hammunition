# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""Installed versus the catalog: the `update` report.  D-053.

Every manifest has carried an ``update`` block since D-010 -- a probe and a
strategy -- and until this module nothing read it. AHRL's failure mode was
"install once, rot forever", and a catalog that can describe how to learn a
version but never does is one step from the same place.

The report is exactly that: a report. It runs no command that changes the
machine and asks nothing over the network. Two comparisons, each against a
fact the engine already has:

* **apt units** against the archive as the local lists describe it. The
  same ``apt-cache policy`` call resolution makes, read for versions this
  time: the installed one and apt's candidate. When they differ, apt would
  change the package on its next upgrade, and the report says so with both
  versions and the exact ``--only-upgrade`` command, which never removes and
  never downgrades. Whether the lists are current is disclosed, not assumed.
* **built units** against the catalog's pin, through the D-051 attribution:
  the effect on disk and a verified transaction that built exactly this pin.
  A build the log attributes at this pin is up to date by the only measure
  the engine has; a build present but not attributed is behind the pin or
  was never verified here, and ``install`` rebuilds it either way.

What it does not do is compare the catalog's pin to upstream. The GitHub,
PyPI and label-file probes describe how a maintainer would learn that; it
is a network question about the catalog rather than this machine, and it
is the second half of D-053, not this one.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from hammunition.backends.apt import AptPackageState
from hammunition.manifest.schema import (
    AptInstall,
    BinaryInstall,
    GitInstall,
    NodeInstall,
    PackageManifest,
    SourceInstall,
    VenvInstall,
)
from hammunition.plan import InstallPlan, PlannedPackage

UP_TO_DATE = "up to date"
CANDIDATE_DIFFERS = "candidate differs"
BEHIND_PIN = "behind the pin"
NOT_INSTALLED = "not installed"
UNKNOWN = "unknown"
ON_INSTALL = "re-checked on install"
MANUAL = "manual"

UPSTREAM_PROBES = frozenset(
    {"github_release", "github_tags", "pypi", "label_file", "binary_version"}
)


@dataclass(frozen=True)
class UpdateRow:
    unit: str
    state: str
    detail: str
    strategy: str
    upgradable: tuple[str, ...] = ()
    """apt packages whose candidate differs from the installed version."""


@dataclass(frozen=True)
class UpdateReport:
    rows: tuple[UpdateRow, ...]
    upstream_declared: tuple[str, ...]
    """Units whose probe would ask upstream; not consulted here."""

    @property
    def upgradable(self) -> tuple[str, ...]:
        seen: dict[str, None] = {}
        for row in self.rows:
            for package in row.upgradable:
                seen.setdefault(package, None)
        return tuple(seen)

    @property
    def behind(self) -> tuple[str, ...]:
        return tuple(row.unit for row in self.rows if row.state == BEHIND_PIN)

    def count(self, state: str) -> int:
        return sum(1 for row in self.rows if row.state == state)


def pin_of(planned: PlannedPackage) -> str | None:
    """The catalog's pin for a built unit, as a short human token."""
    method = planned.block.install
    if isinstance(method, SourceInstall):
        return f"sha256 {method.source.sha256[:12]}…"
    if isinstance(method, GitInstall):
        return f"ref {method.ref}"
    if isinstance(method, BinaryInstall):
        return f"sha256 {method.artifact.sha256[:12]}…"
    return None


def _apt_row(
    planned: PlannedPackage, method: AptInstall, states: Mapping[str, AptPackageState]
) -> UpdateRow:
    strategy = planned.manifest.update.strategy
    missing = [p for p in method.packages if p not in states or not states[p].is_installed]
    if missing:
        return UpdateRow(planned.name, NOT_INSTALLED, ", ".join(missing), strategy)
    differing: list[str] = []
    lines: list[str] = []
    no_candidate: list[str] = []
    for package in method.packages:
        state = states[package]
        if state.candidate is None:
            no_candidate.append(package)
        elif state.candidate != state.installed:
            differing.append(package)
            lines.append(f"{package} {state.installed} -> {state.candidate}")
        else:
            lines.append(f"{package} {state.installed}")
    if differing:
        detail = "; ".join(lines)
        if no_candidate:
            detail += f"; no candidate in the archive as configured: {', '.join(no_candidate)}"
        return UpdateRow(planned.name, CANDIDATE_DIFFERS, detail, strategy, tuple(differing))
    detail = "; ".join(lines)
    if no_candidate:
        detail = (
            f"{detail}; " if detail else ""
        ) + f"installed, no candidate in the archive as configured: {', '.join(no_candidate)}"
    return UpdateRow(planned.name, UP_TO_DATE, detail, strategy)


def _built_row(
    planned: PlannedPackage,
    *,
    present: bool | None,
    attributed: bool,
) -> UpdateRow:
    strategy = planned.manifest.update.strategy
    pin = pin_of(planned) or "the catalog's pin"
    if present is None:
        return UpdateRow(
            planned.name,
            UNKNOWN,
            "declares no binaries and no tree marker, so nothing on disk can be checked",
            strategy,
        )
    if not present:
        return UpdateRow(
            planned.name, NOT_INSTALLED, f"nothing declared is on disk; pin {pin}", strategy
        )
    if attributed:
        return UpdateRow(
            planned.name, UP_TO_DATE, f"built here at {pin} and verified (D-051)", strategy
        )
    return UpdateRow(
        planned.name,
        BEHIND_PIN,
        f"on disk, but not attributed at {pin}: built at an earlier pin, or never "
        f"verified here; `install {planned.name}` rebuilds",
        strategy,
    )


def _first_sentence(manifest: PackageManifest) -> str:
    """A manual unit's cadence hint, cut to its first sentence for the table;
    the manifest carries the rest, and the row says where to look."""
    hint = (manifest.update.cadence_hint or "").strip()
    if not hint:
        return "re-pinned by hand; see the manifest's update block"
    first, sep, _rest = hint.partition(". ")
    return f"{first}. (more in the manifest)" if sep else hint


def report(
    plan: InstallPlan,
    *,
    apt_states: Mapping[str, AptPackageState],
    present: Mapping[str, bool | None],
    built: Iterable[str],
) -> UpdateReport:
    """One row per planned unit. Pure: every fact arrives as an argument.

    ``apt_states`` is the policy probe for every apt package the plan names;
    ``present`` is :func:`hammunition.execute.build_effects_present` per built
    unit; ``built`` is :func:`hammunition.execute.already_built` for the plan.
    """
    attributed = frozenset(built)
    rows: list[UpdateRow] = []
    upstream: list[str] = []
    for planned in plan.packages:
        manifest = planned.manifest
        method = planned.block.install
        strategy = manifest.update.strategy
        if manifest.update.probe.method in UPSTREAM_PROBES:
            upstream.append(planned.name)
        if strategy == "manual":
            rows.append(UpdateRow(planned.name, MANUAL, _first_sentence(manifest), strategy))
            continue
        if isinstance(method, AptInstall):
            rows.append(_apt_row(planned, method, apt_states))
        elif isinstance(method, BinaryInstall) and method.format == "deb":
            if planned.deb_installed:
                rows.append(
                    UpdateRow(
                        planned.name,
                        UP_TO_DATE,
                        f"vendor .deb installed by this engine at {pin_of(planned)} (#67)",
                        strategy,
                    )
                )
            else:
                rows.append(
                    UpdateRow(
                        planned.name,
                        BEHIND_PIN,
                        f"dpkg does not hold the catalog's .deb ({pin_of(planned)}) as this "
                        f"engine's; `install {planned.name}` fetches it",
                        strategy,
                    )
                )
        elif isinstance(method, SourceInstall | GitInstall | BinaryInstall):
            rows.append(
                _built_row(
                    planned,
                    present=present.get(planned.name),
                    attributed=planned.name in attributed,
                )
            )
        elif isinstance(method, VenvInstall):
            rows.append(
                UpdateRow(
                    planned.name,
                    ON_INSTALL,
                    "pip resolves the venv on every install; nothing to compare offline",
                    strategy,
                )
            )
        elif isinstance(method, NodeInstall):
            rows.append(
                UpdateRow(
                    planned.name,
                    ON_INSTALL,
                    "npm resolves the tree on every install; nothing to compare offline",
                    strategy,
                )
            )
        else:
            rows.append(UpdateRow(planned.name, UNKNOWN, "no comparison for this method", strategy))
    return UpdateReport(rows=tuple(rows), upstream_declared=tuple(upstream))


def requested_units(entries: Iterable[Mapping[str, Any]]) -> tuple[str, ...]:
    """Every unit a ``transaction_begin`` here has ever named, in first-seen order.

    Deliberately wider than D-051's attribution: a transaction that failed
    after its apt step (the field laptop's first full install, 2026-09-12)
    still installed a thousand packages, and a default that read only clean
    endings hid ninety units the machine has. The report resolves each unit
    and looks at apt and the disk, so a unit that never landed reads *not
    installed* rather than being guessed either way.
    """
    seen: dict[str, None] = {}
    for entry in entries:
        if entry.get("event") == "transaction_begin":
            for name in entry.get("packages", ()):
                seen.setdefault(str(name), None)
    return tuple(seen)


def render(report: UpdateReport, *, lists_note: str) -> str:
    """The report as the terminal shows it."""
    width = max((len(row.unit) for row in report.rows), default=8)
    out: list[str] = [f"Units ({len(report.rows)}):"]
    for row in report.rows:
        out.append(f"  {row.unit:<{width}}  {row.state:<22} {row.detail}")
    out.append("")
    out.append(
        f"{report.count(UP_TO_DATE)} up to date, {report.count(CANDIDATE_DIFFERS)} with a "
        f"different apt candidate, {report.count(BEHIND_PIN)} behind the catalog's pin, "
        f"{report.count(NOT_INSTALLED)} not installed, {report.count(UNKNOWN)} unknown, "
        f"{report.count(ON_INSTALL)} re-checked on install, {report.count(MANUAL)} manual."
    )
    out.append(f"apt lists: {lists_note}")
    if report.upgradable:
        out.append("")
        out.append(
            "To take apt's candidates (upgrade only, never a removal; apt decides the rest):"
        )
        out.append(
            "  $ sudo env DEBIAN_FRONTEND=noninteractive apt-get install --yes --only-upgrade "
            f"--no-remove -- {' '.join(report.upgradable)}"
        )
    if report.behind:
        out.append("")
        out.append("To rebuild at the catalog's pin:")
        out.append(f"  $ hammunition install {' '.join(report.behind)}")
    if report.upstream_declared:
        out.append("")
        out.append(
            f"Upstream was not consulted: {len(report.upstream_declared)} unit(s) declare a "
            f"probe that would ask GitHub, PyPI or a version file. Whether the catalog's pin "
            f"is behind upstream is a question about the catalog, answered over the network, "
            f"and not part of this report (D-053)."
        )
    out.append("")
    out.append("Nothing above was executed.")
    return "\n".join(out)


def sequence(names: Sequence[str]) -> tuple[str, ...]:
    """Requested names, deduplicated in order."""
    return tuple(dict.fromkeys(names))
