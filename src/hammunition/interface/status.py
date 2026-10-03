# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``status`` as data: the machine, the catalog, and what the log records.  D-059."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

from hammunition.distro import Target
from hammunition.interface.envelope import Strict, TargetView, described, target_view
from hammunition.manifest.schema import PackageManifest, ProfileManifest
from hammunition.plan import PlannedPackage
from hammunition.update import pin_of

__all__ = ["StatusDocument", "build_status", "render_status"]


@dataclass(frozen=True)
class CatalogSummary(Strict):
    """The catalog this run read."""

    path: str = described("the catalog directory")
    packages: int = described("manifests loaded")
    resolvable: int = described("of those, the ones with an install block for this target")
    profiles: int = described("profiles loaded")


@dataclass(frozen=True)
class CheckLine(Strict):
    """An effect the transaction could not confirm afterwards (D-031)."""

    subject: str = described("what was checked")
    detail: str = described("what was found instead")


@dataclass(frozen=True)
class LoggedDeferral(Strict):
    """Something that transaction deferred by design (D-035, D-039)."""

    kind: str = described("`config` or `package`")
    subject: str = described("what was deferred")
    what: str = described("what did not happen")
    why: str = described("what was missing")


@dataclass(frozen=True)
class LatestTransaction(Strict):
    """The most recent `transaction_begin` in the log, and how it ended."""

    when: str | None = described("its timestamp, ISO 8601, when recorded")
    outcome: str = described(
        "`completed`, `failed`, or `interrupted` (no ending recorded: killed, or still running)"
    )
    completed_commands: int | None = described("commands that ran; null when interrupted")
    intended: tuple[str, ...] = described("the apt packages it set out to install")
    verified: bool | None = described(
        "the D-031 effect check's verdict; null when the log predates it or the run did not end"
    )
    checks: int = described("effect checks recorded")
    unconfirmed: tuple[CheckLine, ...] = described("the checks that failed")
    deferred: tuple[LoggedDeferral, ...] = described("what it deferred")


@dataclass(frozen=True)
class RecordedUnit(Strict):
    """A unit some install or uninstall here named, and how the latest one ended.

    Not a claim that the unit is installed now: `update --json` compares the
    machine. A unit the catalog no longer carries has null method and pin."""

    name: str = described("the catalog unit")
    last_named: str | None = described("when the latest install or uninstall naming it began")
    last_outcome: str = described(
        "an install's `completed`, `failed` or `interrupted`; an uninstall's "
        "`removed`, `removal failed` or `removal interrupted`"
    )
    catalog_version: str | None = described("the manifest's version today")
    method: str | None = described("the install method that resolves on this target")
    pin: str | None = described("the catalog's pin for a built unit; null for apt")


@dataclass(frozen=True)
class StatusDocument(Strict):
    """What this machine is, what the catalog holds, and what has been done here."""

    KIND: ClassVar[str] = "status"

    target: TargetView = described("the system")
    catalog: CatalogSummary = described("the catalog read")
    log_path: str = described("the transaction log file")
    log_entries: int = described("events in the log")
    latest: LatestTransaction | None = described(
        "the most recent transaction; null when the log records none"
    )
    recorded_units: tuple[RecordedUnit, ...] = described(
        "every unit an install or uninstall here named, first-seen order"
    )


def _latest(entries: Sequence[Mapping[str, Any]]) -> LatestTransaction | None:
    begin_index = max(
        (i for i, e in enumerate(entries) if e.get("event") == "transaction_begin"),
        default=None,
    )
    if begin_index is None:
        return None
    begin = entries[begin_index]
    tail = entries[begin_index + 1 :]
    ended = next((e for e in tail if e.get("event") == "transaction_end"), None)
    failed = next((e for e in tail if e.get("event") == "transaction_failed"), None)
    verified: bool | None = None
    checks: list[Mapping[str, Any]] = []
    if failed is not None:
        outcome, completed = "failed", int(failed.get("completed", 0))
    elif ended is not None:
        outcome, completed = "completed", int(ended.get("completed", 0))
        # transaction_end version 2 carries the D-031 effect check; a version 1
        # entry has no `verified` key, and nothing is inferred from its absence.
        if "verified" in ended:
            verified = bool(ended.get("verified"))
            checks = list(ended.get("checks", []))
    else:
        outcome, completed = "interrupted", None
    return LatestTransaction(
        when=begin.get("timestamp"),
        outcome=outcome,
        completed_commands=completed,
        intended=tuple(str(p) for p in begin.get("apt_packages", [])),
        verified=verified,
        checks=len(checks),
        unconfirmed=tuple(
            CheckLine(subject=str(c.get("subject", "?")), detail=str(c.get("detail", "")))
            for c in checks
            if not c.get("confirmed", False)
        ),
        deferred=tuple(
            LoggedDeferral(
                kind=str(d.get("kind", "config")),
                subject=str(d.get("subject", "?")),
                what=str(d.get("what", "")),
                why=str(d.get("why", "")),
            )
            for d in begin.get("deferred", [])
        ),
    )


#: For each opening event, the outcome its ending gives the units it names;
#: the key "" is the outcome when no ending was recorded.
_OUTCOMES: Mapping[str, Mapping[str, str]] = {
    "transaction_begin": {
        "transaction_end": "completed",
        "transaction_failed": "failed",
        "": "interrupted",
    },
    "uninstall_begin": {
        "uninstall_end": "removed",
        "uninstall_failed": "removal failed",
        "": "removal interrupted",
    },
}


def _last_outcomes(entries: Sequence[Mapping[str, Any]]) -> dict[str, tuple[str | None, str]]:
    """Each unit the log names, with when it was last named and how that ended."""
    last: dict[str, tuple[str | None, str]] = {}
    # The open transaction: its start, the units it names, and the outcome
    # each ending gives them. An uninstall is the latest word on a unit until
    # a later install names it again (final review I1).
    current: tuple[str | None, list[str], Mapping[str, str]] | None = None

    def close(event: str) -> None:
        if current is not None:
            for name in current[1]:
                last[name] = (current[0], current[2][event])

    for entry in entries:
        event = entry.get("event")
        if event in _OUTCOMES:
            close("")
            current = (
                entry.get("timestamp"),
                [str(p) for p in entry.get("packages", [])],
                _OUTCOMES[str(event)],
            )
            for name in current[1]:
                last[name] = (current[0], current[2][""])
        elif current is not None and event in current[2]:
            close(str(event))
            current = None
    close("")
    return last


def installed_units(entries: Sequence[Mapping[str, Any]]) -> frozenset[str]:
    """The units whose latest word in the log is a completed install.

    The same reading `status` reports as ``last_outcome == "completed"``; an
    absent log (no entries) is the empty set, never an error.
    """
    return frozenset(
        name for name, (_when, outcome) in _last_outcomes(entries).items() if outcome == "completed"
    )


def _recorded(
    entries: Sequence[Mapping[str, Any]], packages: Mapping[str, PackageManifest], target: Target
) -> tuple[RecordedUnit, ...]:
    units: list[RecordedUnit] = []
    for name, (when, outcome) in _last_outcomes(entries).items():
        manifest = packages.get(name)
        block = manifest.resolve(target.distro, target.version, target.arch) if manifest else None
        pin = (
            pin_of(PlannedPackage(manifest=manifest, block=block, apt_packages=()))
            if manifest is not None and block is not None
            else None
        )
        units.append(
            RecordedUnit(
                name=name,
                last_named=when,
                last_outcome=outcome,
                catalog_version=manifest.version if manifest else None,
                method=block.install.method if block else None,
                pin=pin,
            )
        )
    return tuple(units)


def build_status(
    *,
    target: Target,
    catalog_root: Path,
    packages: Mapping[str, PackageManifest],
    profiles: Mapping[str, ProfileManifest],
    log_path: Path,
    entries: Sequence[Mapping[str, Any]],
) -> StatusDocument:
    resolvable = sum(
        1 for m in packages.values() if m.resolve(target.distro, target.version, target.arch)
    )
    return StatusDocument(
        target=target_view(target),
        catalog=CatalogSummary(
            path=str(catalog_root),
            packages=len(packages),
            resolvable=resolvable,
            profiles=len(profiles),
        ),
        log_path=str(log_path),
        log_entries=len(entries),
        latest=_latest(entries),
        recorded_units=_recorded(entries, packages, target),
    )


def render_status(doc: StatusDocument) -> list[str]:
    """``status`` as the terminal shows it."""
    lines = [
        f"Target: {doc.target.description}",
        "Debian family: "
        + ("yes" if doc.target.debian_family else "no — installation is refused here"),
        f"Catalog: {doc.catalog.path}",
        f"  {doc.catalog.packages} packages, {doc.catalog.resolvable} of which resolve on this target",
        f"  {doc.catalog.profiles} profiles",
        f"Transaction log: {doc.log_path}",
    ]
    if not doc.log_entries:
        return [*lines, "  no transactions recorded"]
    lines.append(f"  {doc.log_entries} entries")
    latest = doc.latest
    if latest is None:
        return [*lines, "  no transaction start recorded (log holds only other events)"]
    intended = len(latest.intended)
    if latest.outcome == "failed":
        lines.append(
            f"  most recent transaction FAILED after {latest.completed_commands} command(s); "
            f"{intended} package(s) were intended, not necessarily installed"
        )
    elif latest.outcome == "completed":
        lines.append(
            f"  most recent transaction completed {latest.completed_commands} "
            f"command(s); {intended} package(s) intended"
        )
        if latest.verified is True:
            lines.append(f"  effects confirmed afterwards: {latest.checks} check(s) passed (D-031)")
        elif latest.verified is False:
            lines.append(
                f"  UNVERIFIED: {len(latest.unconfirmed)} effect(s) could not be confirmed:"
            )
            lines += [f"    {c.subject}: {c.detail}" for c in latest.unconfirmed]
    else:
        lines.append(
            f"  most recent transaction did not record an ending (interrupted or "
            f"still running); {intended} package(s) were intended"
        )
    lines += [f"    {name}" for name in latest.intended]
    if latest.deferred:
        lines.append(f"  deferred in that transaction, by design ({len(latest.deferred)}):")
        lines += [f"    {d.subject}: {d.what} -- {d.why}" for d in latest.deferred]
    return lines
