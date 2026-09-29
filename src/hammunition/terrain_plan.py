# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Which terrain tiles the station's regions need, resolved before the plan
prints.  D-061.

For each region, in order:

1. its record, ``<data>/dem-copernicus/<slug>.tiles``, written the last time
   its tiles were installed -- no network; or
2. its Geofabrik outline, ``<region>.poly``, asked through the same
   :class:`~hammunition.geofabrik.Probe` that resolves the regions, turned
   into the squares it touches and filtered by the carried tile list (a
   square not in it is sea).

Then every tile not already installed is resolved to a verifiable download:
from its pin, asking nothing, or from the bucket's ``HEAD`` for its size and
ETag MD5. A pinned tile about to be fetched is ``HEAD``-checked too, as a
pinned region is (piece 1, fix round 1, I3), so an offline plan refuses
before anything runs rather than after apt has.

Offline, the rule is piece 1's: what is installed stays installed and needs
no network; a region with no record and a tile not installed cannot be
resolved, and every such one is named together in one
:class:`~hammunition.copernicus.CopernicusError`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from .backends.dem import TIF, TILES, DemResolution, RegionTiles, read_record
from .copernicus import (
    CopernicusError,
    TileFile,
    TilePin,
    TileProbe,
    parse_poly,
    resolve_tile,
    select,
    squares_touching,
)
from .geofabrik import BASE, GeofabrikError, Probe


def poly_url(region: str) -> str:
    return f"{BASE}/{region}.poly"


def region_tiles(
    region: str, slug: str, *, installed: Path, tile_list: frozenset[str], probe: Probe
) -> RegionTiles:
    """*region*'s tiles: its record when there is one, else its outline."""
    recorded = read_record(installed / f"{slug}{TILES}", region, slug)
    if recorded is not None:
        return recorded
    outer, holes = parse_poly(probe.text(poly_url(region)))
    tiles, sea = select(squares_touching(outer, holes), tile_list)
    return RegionTiles(region, slug, tiles, sea)


def resolve_terrain(
    regions: Sequence[tuple[str, str]],
    *,
    installed: Path,
    tile_list: frozenset[str],
    pins: Mapping[str, TilePin],
    region_probe: Probe,
    tile_probe: TileProbe,
) -> DemResolution:
    """*regions* as ``(region, slug)`` pairs -- this run's and the kept ones --
    resolved to the tiles they need and how each is fetched. A pair named
    twice is resolved once, so its outline is never asked for twice."""
    refused: list[str] = []
    entries: list[RegionTiles] = []
    seen: set[tuple[str, str]] = set()
    for region, slug in regions:
        if (region, slug) in seen:
            continue
        seen.add((region, slug))
        try:
            entries.append(
                region_tiles(
                    region, slug, installed=installed, tile_list=tile_list, probe=region_probe
                )
            )
        except (GeofabrikError, CopernicusError, OSError) as exc:
            refused.append(f"  {region}: its outline could not be read: {exc}")
    wanted = sorted({name for entry in entries for name in entry.tiles})
    fetch: list[TileFile] = []
    current: list[str] = []
    for name in wanted:
        if (installed / f"{name}{TIF}").is_file():
            current.append(name)
            continue
        try:
            tile = resolve_tile(name, pins=pins, probe=tile_probe)
            if tile.sha256 is not None:
                status, _, _ = tile_probe.head(tile.url)
                if status != 200:
                    raise CopernicusError(f"{tile.url} answered HTTP {status}, not 200")
        except (CopernicusError, OSError) as exc:
            refused.append(f"  {name}: {exc}")
            continue
        fetch.append(tile)
    if refused:
        raise CopernicusError(
            f"{len(refused)} terrain item(s) could not be resolved and are not installed "
            f"already:\n" + "\n".join(refused)
        )
    return DemResolution(regions=tuple(entries), fetch=tuple(fetch), current=tuple(current))
