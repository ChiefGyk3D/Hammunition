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

from .backends.regions import MapResolution, data_root
from .backends.topo import QUADS, TIF, RegionQuads, TopoResolution, read_record
from .copernicus import CopernicusError, TileProbe, parse_poly
from .geofabrik import BASE, GeofabrikError, Probe
from .manifest.schema import TopoQuadsInstall
from .plan import InstallPlan
from .ustopo import QuadIndex, UstopoError, check_quad, load_index

INDEX = Path("data") / "ustopo-quads.txt"


def poly_url(region: str) -> str:
    return f"{BASE}/{region}.poly"


@dataclass
class MemoProbe:
    """A :class:`~hammunition.geofabrik.Probe` that asks each URL's text once.

    The terrain and the US Topo sheets both follow a region's outline; one
    plan asks Geofabrik for it once, not once per unit. Failures are not
    remembered, so each caller sees the error for itself."""

    probe: Probe
    texts: dict[str, str] = field(default_factory=dict)

    def head(self, url: str) -> tuple[int, int, str | None]:
        return self.probe.head(url)

    def text(self, url: str) -> str:
        if url not in self.texts:
            self.texts[url] = self.probe.text(url)
        return self.texts[url]


def region_quads(
    region: str, slug: str, *, installed: Path, index: QuadIndex, probe: Probe, notes: list[str]
) -> RegionQuads:
    """*region*'s sheets: its record when it is current, else its outline."""
    recorded = read_record(installed / f"{slug}{QUADS}", region, slug)
    listed = index.by_path()
    if recorded is not None and all(q.path in listed for q in recorded.quads):
        return recorded
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
) -> tuple[TopoResolution, tuple[str, ...]]:
    """*regions* as ``(region, slug)`` pairs resolved to the sheets they
    need and how each is fetched, and any notes for the plan."""
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
        except (GeofabrikError, CopernicusError, OSError) as exc:
            refused.append(f"  {region}: its outline could not be read: {exc}")
    wanted = {q.path: q for entry in entries for q in entry.quads}
    fetch = []
    current = []
    for path in sorted(wanted):
        quad = wanted[path]
        if (installed / f"{quad.name}{TIF}").is_file():
            current.append(quad)
            continue
        try:
            check_quad(quad, quad_probe)
        except (UstopoError, CopernicusError, OSError) as exc:
            refused.append(f"  {quad.name}: {exc}")
            continue
        fetch.append(quad)
    if refused:
        raise UstopoError(
            f"{len(refused)} US Topo item(s) could not be resolved and are not installed "
            f"already:\n" + "\n".join(refused)
        )
    resolution = TopoResolution(regions=tuple(entries), fetch=tuple(fetch), current=tuple(current))
    return resolution, tuple(notes)


def resolve_station_topo(
    plan: InstallPlan,
    maps: MapResolution,
    catalog_root: Path,
    *,
    prefix: Path,
    region_probe: Probe,
    quad_probe: TileProbe,
) -> tuple[TopoResolution, tuple[str, ...]]:
    """The plan's US Topo sheets, or an empty resolution when it holds no
    ``topo-quads`` unit. A missing or empty index is refused by name."""
    unit = next((p for p in plan.packages if isinstance(p.block.install, TopoQuadsInstall)), None)
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
    )
