# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Which US Topo sheets the station's regions need, resolved before the plan
prints.  D-068.

For each region, in order:

1. its record, ``<data>/usgs-ustopo/<slug>.quads``, written the last time its
   sheets were installed -- whole index rows, so no network is needed; or
2. its Geofabrik outline, ``<region>.poly``, asked through the same probe
   that resolves the regions and the terrain (one fetch serves both,
   :class:`MemoProbe`), turned into the 1/8-degree cells it touches and
   matched against the carried index.

A record naming a sheet the carried index no longer lists (a newer edition
was indexed since) is re-selected from the outline, so the newer edition is
fetched and the older removed. Offline, that re-selection cannot happen, and
the record is kept as it is, with a note: what is installed stays installed.

Then every sheet not already installed is checked against the bucket with a
``HEAD`` (:func:`hammunition.ustopo.check_quad`): the same size and ETag the
index carries, or the plan refuses naming it. Offline, a region with no
record and a sheet not installed cannot be resolved, and every such one is
named together in one :class:`~hammunition.ustopo.UstopoError`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from .backends.fstopo import FsTopoResolution, RegionSheets
from .backends.fstopo import read_record as read_sheets
from .backends.regions import MapResolution, data_root
from .backends.topo import QUADS, TIF, RegionQuads, TopoResolution, read_record
from .copernicus import CopernicusError, TileProbe, parse_poly
from .fstopo import FsIndex, FsPin, FsQuad, FsQuadFile, FstopoError, GatewayProbe
from .fstopo import load_index as load_fstopo_index
from .fstopo import load_pins as load_fstopo_pins
from .geofabrik import BASE, GeofabrikError, Probe
from .manifest.schema import DerivedDataInstall, TopoQuadsInstall
from .plan import InstallPlan, PlannedPackage
from .progress import run_checks
from .retry import OnOutage, Outages, PublisherUnavailable, hint_for, reporter_for
from .ustopo import Quad, QuadIndex, UstopoError, check_quad, load_index

INDEX = Path("data") / "ustopo-quads.txt"
FSTOPO_INDEX = Path("data") / "fstopo-quads.txt"
FSTOPO_PINS = Path("data") / "fstopo-pins.yaml"


def poly_url(region: str) -> str:
    return f"{BASE}/{region}.poly"


@dataclass
class MemoProbe:
    """A :class:`~hammunition.geofabrik.Probe` that asks each URL's text once.

    The terrain and the US Topo sheets both follow a region's outline; one
    plan asks Geofabrik for it once, not once per unit. A publisher that did
    not answer *after the retries* (:class:`~hammunition.retry.PublisherUnavailable`)
    is remembered for the rest of the run, so each unit that needs the outline
    is told at once and the same dead request is not retried per unit (#200);
    any other failure is not remembered, so each caller sees the error for
    itself."""

    probe: Probe
    texts: dict[str, str] = field(default_factory=dict)
    outages: dict[str, PublisherUnavailable] = field(default_factory=dict)

    def head(self, url: str) -> tuple[int, int, str | None]:
        return self.probe.head(url)

    def text(self, url: str) -> str:
        if url in self.outages:
            raise self.outages[url]
        if url not in self.texts:
            try:
                self.texts[url] = self.probe.text(url)
            except PublisherUnavailable as exc:
                self.outages[url] = exc
                raise
        return self.texts[url]


def region_quads(
    region: str, slug: str, *, installed: Path, index: QuadIndex, probe: Probe, notes: list[str]
) -> RegionQuads:
    """*region*'s sheets: its record when it is current, else its outline."""
    recorded = read_record(installed / f"{slug}{QUADS}", region, slug)
    listed = index.by_path()
    if recorded is not None and all(q.path in listed for q in recorded.quads):
        # The index's rows, not the record's (review M1): a regenerated index
        # carries a re-uploaded object's new size and ETag under the same name.
        return RegionQuads(region, slug, tuple(listed[q.path] for q in recorded.quads))
    try:
        outer, holes = parse_poly(probe.text(poly_url(region)))
    except (GeofabrikError, CopernicusError, OSError):
        if recorded is None:
            raise
        notes.append(
            f"{region}: a newer US Topo edition is indexed for some of its quads, and its "
            f"outline could not be fetched to choose them; the installed quads are kept"
        )
        return recorded
    return RegionQuads(region, slug, index.select(outer, holes))


def resolve_topo(
    regions: Sequence[tuple[str, str]],
    *,
    installed: Path,
    index: QuadIndex,
    region_probe: Probe,
    quad_probe: TileProbe,
    on_outage: OnOutage | None = None,
) -> tuple[TopoResolution, tuple[str, ...]]:
    """*regions* as ``(region, slug)`` pairs resolved to the sheets they
    need and how each is fetched, and any notes for the plan.

    A publisher that did not answer after the retries (#200) is passed to
    *on_outage* with the item it concerned -- a region whose outline is not
    available, or one sheet -- and that item is left out; with no *on_outage*
    (a unit the operator typed by name) it is refused like any other."""
    refused: list[str] = []
    notes: list[str] = []
    entries: list[RegionQuads] = []
    seen: set[tuple[str, str]] = set()
    for region, slug in regions:
        if (region, slug) in seen:
            continue
        seen.add((region, slug))
        try:
            entries.append(
                region_quads(
                    region, slug, installed=installed, index=index, probe=region_probe, notes=notes
                )
            )
        except PublisherUnavailable as exc:
            if on_outage is None:
                refused.append(f"  {region}: its outline could not be read: {exc}")
            else:
                on_outage(f"{region} (its outline)", exc)
        except (GeofabrikError, CopernicusError, OSError) as exc:
            refused.append(f"  {region}: its outline could not be read: {exc}")
    wanted = {q.path: q for entry in entries for q in entry.quads}
    fetch = []
    current = []
    deferred: list[Quad] = []
    todo = []
    for path in sorted(wanted):
        quad = wanted[path]
        if (installed / f"{quad.name}{TIF}").is_file():
            current.append(quad)
        else:
            todo.append(quad)
    outcomes = run_checks(
        todo,
        lambda quad: check_quad(quad, quad_probe),
        label="US Topo sheets against the USGS bucket",
    )
    for quad, outcome in zip(todo, outcomes, strict=True):
        try:
            outcome.get()
        except PublisherUnavailable as exc:
            if on_outage is None:
                refused.append(f"  {quad.name}: {exc}")
            else:
                on_outage(quad.name, exc)
                deferred.append(quad)
            continue
        except (UstopoError, CopernicusError, OSError) as exc:
            refused.append(f"  {quad.name}: {exc}")
            continue
        fetch.append(quad)
    if refused:
        raise UstopoError(
            f"{len(refused)} US Topo item(s) could not be resolved and are not installed "
            f"already:\n" + "\n".join(refused) + hint_for(refused)
        )
    resolution = TopoResolution(
        regions=tuple(entries),
        fetch=tuple(fetch),
        current=tuple(current),
        deferred=tuple(deferred),
    )
    return resolution, tuple(notes)


def resolve_station_topo(
    plan: InstallPlan,
    maps: MapResolution,
    catalog_root: Path,
    *,
    prefix: Path,
    region_probe: Probe,
    quad_probe: TileProbe,
    outages: Outages | None = None,
) -> tuple[TopoResolution, tuple[str, ...]]:
    """The plan's US Topo sheets, or an empty resolution when it holds no
    ``topo-quads`` unit. A missing or empty index is refused by name. With
    *outages*, a publisher that is not answering defers what it concerned
    unless the operator typed the unit (#200)."""
    unit = _planned_topo(plan, "usgs-ustopo")
    if unit is None:
        return TopoResolution(), ()
    index = load_index(catalog_root / INDEX)
    regions = [(f.region, f.slug) for f in maps.files]
    ours = {slug for _, slug in regions}
    regions += [(k.region, k.slug) for k in maps.kept if k.slug not in ours]
    return resolve_topo(
        regions,
        installed=data_root(prefix) / unit.name,
        index=index,
        region_probe=region_probe,
        quad_probe=quad_probe,
        on_outage=reporter_for(outages, unit),
    )


def _planned_topo(plan: InstallPlan, provider: str) -> PlannedPackage | None:
    for planned in plan.packages:
        block = planned.block.install
        if isinstance(block, TopoQuadsInstall) and block.provider == provider:
            return planned
    return None


# ---------------------------------------------------------------------------
# FSTopo (D-068, amended 2026-10-01): the same selection over the GTAC index,
# each sheet located through the raster gateway's one redirect.
# ---------------------------------------------------------------------------


def region_sheets(
    region: str, slug: str, *, installed: Path, index: FsIndex, probe: Probe, notes: list[str]
) -> RegionSheets:
    """*region*'s FSTopo sheets: its record when every sheet in it is still
    indexed (taken at the index's vintage), else its outline."""
    recorded = read_sheets(installed / f"{slug}{QUADS}", region, slug)
    listed = index.by_secoord()
    if recorded is not None and all(q.secoord in listed for q in recorded.quads):
        return RegionSheets(region, slug, tuple(listed[q.secoord] for q in recorded.quads))
    try:
        outer, holes = parse_poly(probe.text(poly_url(region)))
    except (GeofabrikError, CopernicusError, OSError):
        if recorded is None:
            raise
        notes.append(
            f"{region}: the FSTopo index no longer carries some of its quads, and its "
            f"outline could not be fetched to choose again; the installed quads are kept"
        )
        return recorded
    return RegionSheets(region, slug, index.select(outer, holes))


def resolve_fstopo(
    regions: Sequence[tuple[str, str]],
    *,
    installed: Path,
    index: FsIndex,
    pins: dict[int, FsPin],
    region_probe: Probe,
    gateway: GatewayProbe,
    on_outage: OnOutage | None = None,
) -> tuple[FsTopoResolution, tuple[str, ...]]:
    """*regions* resolved to the FSTopo sheets they need; every sheet not
    installed is located through the gateway and sized, and checked against
    its pin's size where it has one. Every refusal is named together. A
    publisher that did not answer after the retries goes to *on_outage* and
    that item is left out (#200); without it, it is refused."""
    refused: list[str] = []
    notes: list[str] = []
    entries: list[RegionSheets] = []
    seen: set[tuple[str, str]] = set()
    for region, slug in regions:
        if (region, slug) in seen:
            continue
        seen.add((region, slug))
        try:
            entries.append(
                region_sheets(
                    region, slug, installed=installed, index=index, probe=region_probe, notes=notes
                )
            )
        except PublisherUnavailable as exc:
            if on_outage is None:
                refused.append(f"  {region}: its outline could not be read: {exc}")
            else:
                on_outage(f"{region} (its outline)", exc)
        except (GeofabrikError, CopernicusError, OSError) as exc:
            refused.append(f"  {region}: its outline could not be read: {exc}")
    wanted = {q.secoord: q for entry in entries for q in entry.quads}
    fetch: list[FsQuadFile] = []
    deferred: list[FsQuad] = []
    current = []
    todo: list[tuple[int, FsQuad]] = []
    for secoord in sorted(wanted):
        quad = wanted[secoord]
        if (installed / f"{quad.name}{TIF}").is_file():
            current.append(quad)
        else:
            todo.append((secoord, quad))
    # Each sheet is two requests (the gateway's redirect, then the file's size).
    outcomes = run_checks(
        todo,
        lambda item: gateway.locate(item[0]),
        label="FSTopo sheets against the Forest Service gateway",
    )
    for (secoord, quad), outcome in zip(todo, outcomes, strict=True):
        try:
            url, size = outcome.get()
        except PublisherUnavailable as exc:
            if on_outage is None:
                refused.append(f"  {quad.name}: {exc}")
            else:
                on_outage(quad.name, exc)
                deferred.append(quad)
            continue
        except (FstopoError, OSError) as exc:
            refused.append(f"  {quad.name}: {exc}")
            continue
        pin = pins.get(secoord)
        if pin is not None and pin.size != size:
            refused.append(
                f"  {quad.name}: the gateway now announces {size} bytes where the pin has "
                f"{pin.size}; the Forest Service re-issued it, so it is not fetched against "
                f"the old pin. scripts/gen_fstopo_index.py --pin {secoord} measures it again"
            )
            continue
        fetch.append(FsQuadFile(quad, url, size, pin.sha256 if pin else None))
    if refused:
        raise FstopoError(
            f"{len(refused)} FSTopo item(s) could not be resolved and are not installed "
            f"already:\n" + "\n".join(refused) + hint_for(refused)
        )
    pinned = frozenset(s for s in wanted if s in pins)
    return (
        FsTopoResolution(tuple(entries), tuple(fetch), tuple(current), pinned, tuple(deferred)),
        tuple(notes),
    )


def installed_sheets(directory: Path) -> FsTopoResolution:
    """The FSTopo sheets on disk, from their regions' records, offline: what
    the mosaic reads when the unit is not in the plan (it is installed by
    name only, D-068 amended 2026-10-01). Nothing is fetched or removed."""
    found: dict[int, FsQuad] = {}
    for record in sorted(directory.glob(f"*{QUADS}")):
        entry = read_sheets(record, record.stem, record.stem)
        for quad in entry.quads if entry is not None else ():
            if (directory / f"{quad.name}{TIF}").is_file():
                found[quad.secoord] = quad
    return FsTopoResolution(current=tuple(found[s] for s in sorted(found)))


def resolve_station_fstopo(
    plan: InstallPlan,
    maps: MapResolution,
    catalog_root: Path,
    *,
    prefix: Path,
    region_probe: Probe,
    gateway: GatewayProbe,
    outages: Outages | None = None,
) -> tuple[FsTopoResolution, tuple[str, ...]]:
    """The plan's FSTopo sheets, or nothing when it holds no ``usfs-fstopo``
    unit. A missing index or a malformed pins file is refused by name."""
    unit = _planned_topo(plan, "usfs-fstopo")
    if unit is None:
        # Not planned: the mosaic still draws the sheets installed by name.
        mosaic = next(
            (
                p.block.install
                for p in plan.packages
                if isinstance(p.block.install, DerivedDataInstall)
                and p.block.install.converter == "ustopo-mosaic"
                and p.block.install.fstopo
            ),
            None,
        )
        if mosaic is None or mosaic.fstopo is None:
            return FsTopoResolution(), ()
        return installed_sheets(data_root(prefix) / mosaic.fstopo), ()
    index = load_fstopo_index(catalog_root / FSTOPO_INDEX)
    pins = load_fstopo_pins(catalog_root / FSTOPO_PINS)
    regions = [(f.region, f.slug) for f in maps.files]
    ours = {slug for _, slug in regions}
    regions += [(k.region, k.slug) for k in maps.kept if k.slug not in ours]
    return resolve_fstopo(
        regions,
        installed=data_root(prefix) / unit.name,
        index=index,
        pins=pins,
        region_probe=region_probe,
        gateway=gateway,
        on_outage=reporter_for(outages, unit),
    )
