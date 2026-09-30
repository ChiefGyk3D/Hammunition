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
from pathlib import Path
from typing import Any

from hammunition.backends.apt import AptPackageState
from hammunition.comaps import MapFile
from hammunition.kiwix import BookFile
from hammunition.manifest.schema import (
    AptInstall,
    BinaryInstall,
    DemTilesInstall,
    GitInstall,
    KiwixBooksInstall,
    MwmRegionsInstall,
    NodeInstall,
    PackageManifest,
    RegionalDataInstall,
    SourceInstall,
    TopoQuadsInstall,
    VenvInstall,
)
from hammunition.plan import NO_REFERENCE_BOOKS, InstallPlan, PlannedPackage

UP_TO_DATE = "up to date"
CANDIDATE_DIFFERS = "candidate differs"
BEHIND_PIN = "behind the pin"
NOT_INSTALLED = "not installed"
UNKNOWN = "unknown"
ON_INSTALL = "re-checked on install"
MANUAL = "manual"

UPSTREAM_PROBES = frozenset(
    {
        "github_release",
        "github_tags",
        "pypi",
        "label_file",
        "binary_version",
        "kiwix",
        "comaps_maps",
    }
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


@dataclass(frozen=True)
class RegionSnapshot:
    """One installed map region against the newest snapshot the pin list
    carries for it.  D-057."""

    slug: str
    installed: str
    newer_pinned: str | None
    """A pinned snapshot newer than *installed*, or None when there is none
    (the pin list has no row for this slug, or its newest is not newer)."""


def region_snapshots(
    installed: Mapping[str, str], newest_pinned: Mapping[str, str]
) -> tuple[RegionSnapshot, ...]:
    """Pure: compares what is on disk against the pin list, both keyed by slug.

    *installed* is slug -> the snapshot recorded in its ``.source`` sidecar
    (:func:`hammunition.backends.regions.installed_slugs`); *newest_pinned*
    is slug -> the pinned snapshot the station's freshness mode would
    resolve to today, restricted to pins that exist
    (:func:`hammunition.geofabrik.current_pinned_snapshots`, fix round 1
    I1 -- comparing against the newest pin of *any* snapshot reported a
    yearly install behind a monthly-shaped pin it would never chase). A
    slug the pin list does not carry compares against nothing and is never
    reported behind -- it is verified by Geofabrik's MD5 only, and the pin
    list has no opinion on it.
    """
    out: list[RegionSnapshot] = []
    for slug in sorted(installed):
        snapshot = installed[slug]
        newer = newest_pinned.get(slug)
        behind = newer if newer is not None and newer > snapshot else None
        out.append(RegionSnapshot(slug, snapshot, behind))
    return tuple(out)


def _regions_row(planned: PlannedPackage, snapshots: Sequence[RegionSnapshot]) -> UpdateRow:
    """A count, never a region's slug or path (fix round 1, I2; controller
    ruling): D-057 argues a region list says where somebody lives or
    travels, the same class of fact as a grid square, and keeps it out of
    pasteable output everywhere but the install plan. The install plan's own
    Map regions section (`render_plan_view`) is the one place a region's
    name or path is shown; this never does.
    """
    strategy = planned.manifest.update.strategy
    if not snapshots:
        return UpdateRow(planned.name, NOT_INSTALLED, "no map regions installed", strategy)
    count = len(snapshots)
    noun = "region" if count == 1 else "regions"
    behind = [s for s in snapshots if s.newer_pinned is not None]
    if not behind:
        return UpdateRow(planned.name, UP_TO_DATE, f"{count} {noun} installed", strategy)
    newer = sorted({s.newer_pinned for s in behind if s.newer_pinned is not None})
    detail = (
        f"{count} {noun} installed; {len(behind)} behind the pin "
        f"(newer map data pinned: {', '.join(newer)})"
    )
    return UpdateRow(planned.name, BEHIND_PIN, detail, strategy)


def _tiles_row(planned: PlannedPackage, count: int, no_terrain: int = 0) -> UpdateRow:
    """Counts only (D-061): a tile's name is a latitude and longitude, as
    telling as a region's. *no_terrain* is how many regions Copernicus
    publishes no tile for at all (final review, I1), never called sea."""
    strategy = planned.manifest.update.strategy
    withheld = (
        f"; {no_terrain} region(s) with no published tile at Copernicus GLO-30 "
        f"(sea, or land it does not release)"
        if no_terrain
        else ""
    )
    if not count:
        return UpdateRow(
            planned.name, NOT_INSTALLED, f"no terrain tiles installed{withheld}", strategy
        )
    return UpdateRow(
        planned.name,
        UP_TO_DATE,
        f"{count} terrain tile(s) installed; a tile changes only when the publisher's "
        f"tile list does{withheld}",
        strategy,
    )


def _quads_row(planned: PlannedPackage, count: int, stale: int) -> UpdateRow:
    """Counts only (D-068): a sheet's name is a place, as telling as a region's."""
    strategy = planned.manifest.update.strategy
    if not count:
        return UpdateRow(planned.name, NOT_INSTALLED, "no US Topo quads installed", strategy)
    if stale:
        return UpdateRow(
            planned.name,
            BEHIND_PIN,
            f"{count} US Topo quad(s) installed; {stale} of them have a newer edition in "
            f"the carried index",
            strategy,
        )
    return UpdateRow(
        planned.name,
        UP_TO_DATE,
        f"{count} US Topo quad(s) installed, each at the edition the carried index lists",
        strategy,
    )


def books_state(chosen: Sequence[BookFile], installed: Path) -> tuple[str, str]:
    """``(state, detail)`` for the Kiwix books unit, offline (D-066).

    Each chosen book against its pin: the pinned file on disk at its exact
    size is current; another date of the same book is behind the pin; no
    file of it is not installed. Book ids are not location data, but the
    row counts them anyway, as every data unit's row does.
    """
    if not chosen:
        return NOT_INSTALLED, f"{NO_REFERENCE_BOOKS}; `hammunition reference books` lists them"
    current = behind = 0
    for book in chosen:
        pinned = installed / book.pin.file
        if pinned.is_file() and pinned.stat().st_size == book.pin.size:
            current += 1
        elif any(installed.glob(f"{book.book.id}_????-??.zim")):
            behind += 1
    count = len(chosen)
    if behind:
        return (
            BEHIND_PIN,
            f"{behind} of {count} book(s) installed at another date than the pin; "
            f"`install kiwix-library` fetches the pinned file",
        )
    if current == count:
        return UP_TO_DATE, f"{count} book(s) installed at their pins"
    return NOT_INSTALLED, f"{count - current} of {count} book(s) not installed"


def mwm_state(files: Sequence[MapFile], installed: Path, *, unmapped: int) -> tuple[str, str]:
    """``(state, detail)`` for CoMaps' maps, offline (D-069).

    Each map the station's regions need against its pin: the file at the
    pinned version and size is current; the same map under another version
    directory is behind the pin; neither is not installed. Counts only: which
    maps are installed says which regions, the same class of fact as a grid
    square.
    """
    if not files:
        return (
            NOT_INSTALLED,
            f"none of the station's {unmapped} map region(s) has a CoMaps map"
            if unmapped
            else "no map regions set",
        )
    current = behind = 0
    for f in files:
        pinned = installed / str(f.version) / f.file
        if pinned.is_file() and not pinned.is_symlink() and pinned.stat().st_size == f.pin.size:
            current += 1
        elif any(p for p in installed.glob(f"*/{f.file}") if p.parent.name != str(f.version)):
            behind += 1
    count = len(files)
    extra = f"; {unmapped} region(s) have no CoMaps map" if unmapped else ""
    if behind:
        return (
            BEHIND_PIN,
            f"{behind} of {count} map(s) installed at another version than the pin; "
            f"`install comaps-maps` fetches the pinned one{extra}",
        )
    if count and current == count:
        return UP_TO_DATE, f"{count} map(s) installed at their pinned version{extra}"
    return NOT_INSTALLED, f"{count - current} of {count} map(s) not installed{extra}"


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
    regions: Mapping[str, Sequence[RegionSnapshot]] | None = None,
    tiles: Mapping[str, int] | None = None,
    no_terrain: Mapping[str, int] | None = None,
    quads: Mapping[str, tuple[int, int]] | None = None,
    books: Mapping[str, tuple[str, str]] | None = None,
    mwm: Mapping[str, tuple[str, str]] | None = None,
) -> UpdateReport:
    """One row per planned unit. Pure: every fact arrives as an argument.

    ``apt_states`` is the policy probe for every apt package the plan names;
    ``present`` is :func:`hammunition.execute.build_effects_present` per built
    unit; ``built`` is :func:`hammunition.execute.already_built` for the plan;
    ``regions`` is an ``osm-regions`` unit's name to its installed regions
    against the pin list (:func:`region_snapshots`), offline (D-053).

    ``tiles`` is a ``dem-tiles`` unit's name to how many tiles it has
    installed (D-061), a count and nothing else; ``no_terrain`` is how many
    of its regions Copernicus publishes no tile for, a count likewise.

    ``quads`` is a ``topo-quads`` unit's name to (sheets installed, of those
    the ones the carried index has since replaced with a newer edition),
    counts only (D-068).
    """
    attributed = frozenset(built)
    region_report = regions or {}
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
        elif isinstance(method, RegionalDataInstall):
            rows.append(_regions_row(planned, region_report.get(planned.name, ())))
        elif isinstance(method, DemTilesInstall):
            rows.append(
                _tiles_row(
                    planned,
                    (tiles or {}).get(planned.name, 0),
                    (no_terrain or {}).get(planned.name, 0),
                )
            )
        elif isinstance(method, TopoQuadsInstall):
            rows.append(_quads_row(planned, *(quads or {}).get(planned.name, (0, 0))))
        elif isinstance(method, KiwixBooksInstall):
            state, detail = (books or {}).get(
                planned.name, (UNKNOWN, "the chosen books were not resolved")
            )
            rows.append(UpdateRow(planned.name, state, detail, strategy))
        elif isinstance(method, MwmRegionsInstall):
            state, detail = (mwm or {}).get(
                planned.name, (UNKNOWN, "the station's CoMaps maps were not resolved")
            )
            rows.append(UpdateRow(planned.name, state, detail, strategy))
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


def upgrade_command(report: UpdateReport) -> str | None:
    """The command that takes apt's differing candidates, or None when none differ."""
    if not report.upgradable:
        return None
    return (
        "sudo env DEBIAN_FRONTEND=noninteractive apt-get install --yes --only-upgrade "
        f"--no-remove -- {' '.join(report.upgradable)}"
    )


def rebuild_command(report: UpdateReport) -> str | None:
    """The command that rebuilds every unit behind the pin, or None.

    `install osm-regions` alone never reconverts the derived maps, since
    osm-navit's dependency on it is one-directional (fix round 1, M2), so
    `osm-navit` is named alongside it here too when it is not already in the
    list.
    """
    if not report.behind:
        return None
    names = list(report.behind)
    if "osm-regions" in names and "osm-navit" not in names:
        names.append("osm-navit")
    # D-061: QMapShack's maps and routing are derived from the same regions;
    # D-063: so are BRouter's routing files; D-067: so are the phone files.
    reported = {row.unit for row in report.rows}
    if "osm-regions" in names:
        derived = (
            "osm-garmin",
            "osm-routino",
            "brouter-segments",
            "mapsforge-map",
            "mapsforge-poi",
        )
        names.extend(u for u in derived if u in reported and u not in names)
    # D-063: a new BRouter or new map-creator filters rebuild the routing files.
    if (
        {"brouter", "brouter-mapcreator-profiles"} & set(names)
        and "brouter-segments" in reported
        and "brouter-segments" not in names
    ):
        names.append("brouter-segments")
    # D-068: the US Topo mosaic is warped from the sheets.
    if (
        "usgs-ustopo" in names
        and "ustopo-qmapshack" in reported
        and "ustopo-qmapshack" not in names
    ):
        names.append("ustopo-qmapshack")
    return f"hammunition install {' '.join(names)}"


def render(report: UpdateReport, *, lists_note: str, upstream_asked: bool = False) -> str:
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
    upgrade = upgrade_command(report)
    if upgrade is not None:
        out.append("")
        out.append(
            "To take apt's candidates (upgrade only, never a removal; apt decides the rest):"
        )
        out.append(f"  $ {upgrade}")
    rebuild = rebuild_command(report)
    if rebuild is not None:
        out.append("")
        out.append("To rebuild at the catalog's pin:")
        out.append(f"  $ {rebuild}")
    if report.upstream_declared and not upstream_asked:
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
