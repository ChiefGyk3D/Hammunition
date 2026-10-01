# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""What piece 2's maps, routing and terrain cost, and how their failures are
reported.  D-061.

The factors were measured on 2026-09-28 on one US-state-sized region on the
development host (docs/superpowers/specs/2026-09-28-hiking-maps-design.md);
every place the plan prints one says "measured on one region".

A failure here -- a tile that did not verify, a Garmin map mkgmap did not
build, a Routino database planetsplitter did not finish -- is recorded in the
:class:`TerrainLedger`, the rest of the transaction continues, and the
ledger's own step, last, fails the transaction naming every one. It is a
ledger of its own and not piece 1's :class:`~hammunition.backends.regions.MapLedger`:
a region that installed and whose Garmin map did not build is still a region
Navit converts, so a converter's failure must never read as the region's.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from .base import Action, BackendError
from .data import human_size
from .mapsforge import PHONE_NOTE
from .pmtiles import TILES_NOTE
from .regions import device_at, disk_shortfall, free_bytes_at

MEASURED = "measured on one region"

#: ``gmapsupp.img`` against its ``.osm.pbf``: 0.85.
GARMIN_FACTOR = 0.85
#: mkgmap's staging while it runs, against the ``.osm.pbf``: the splitter's
#: tiles (1.13) and mkgmap's tile images with ``gmapsupp.img`` (1.70), 2.83,
#: rounded up. Removed once the map is installed, before the next region.
GARMIN_SCRATCH_FACTOR = 3
#: The Routino database against the sum of its ``.osm.pbf`` files: 0.67.
ROUTINO_FACTOR = 0.67
#: planetsplitter's staging directory at its peak, output included, against
#: the same sum: 5.02 sampled once a second over ``--parse-only`` (22 s) then
#: ``--process-only`` (83 s) on one region, rounded up to 6 because a
#: once-a-second sample can miss the top. Its intermediate files are gone
#: when ``--process-only`` finishes.
ROUTINO_SCRATCH_FACTOR = 6
#: One tile's rasterised contours, a DEFLATE Byte GeoTIFF: 5,439,059 bytes
#: measured on one mountain tile at a 20 m interval.
CONTOUR_BYTES = 5_500_000
#: A US Topo sheet warped with its overviews against its download, and the
#: warp's scratch: 8.9 MB from 9.2 MB on one Delaware sheet, both rounded up
#: to 1.0 (D-068). Here, not in ``topo_mosaic``, so the disk check needs no
#: converter to count.
WARP_FACTOR = 1.0
WARP_SCRATCH_FACTOR = 1.0
#: One tile's contour GeoPackage, removed once rasterised: 97,812,480 bytes
#: on that tile, the largest a tile is expected to need.
CONTOUR_SCRATCH_BYTES = 98_000_000
#: The same two for a USGS 3DEP 1/3" tile (D-068, amended 2026-10-01): the
#: spike's n39w079 traced to a 212 MB GeoPackage at a 20 m interval, and its
#: raster at 10,812 pixels is the 5.0 MB measured at 7,200 scaled by the
#: pixel count, until Task 10's live tile measures it.
CONTOUR_BYTES_3DEP = 11_300_000
CONTOUR_SCRATCH_BYTES_3DEP = 212_000_000


def contour_bytes(provider: str) -> int:
    """One tile's rasterised contours, by elevation provider."""
    return CONTOUR_BYTES_3DEP if provider == "usgs-3dep" else CONTOUR_BYTES


def contour_scratch(provider: str) -> int:
    """One tile's contour GeoPackage scratch, by elevation provider."""
    return CONTOUR_SCRATCH_BYTES_3DEP if provider == "usgs-3dep" else CONTOUR_SCRATCH_BYTES


#: BRouter's routing files against the sum of the ``.osm.pbf`` files they are
#: built from: Delaware's 3.3 MB of ``.rd5`` (with elevation) against its
#: 22.1 MB download, 0.15, rounded up (D-063, the routing spike, 2026-09-29).
BROUTER_FACTOR = 0.2
#: The map creator's working files against the same sum. **Not measured**:
#: an allowance, stated as one wherever it is printed.
BROUTER_SCRATCH_FACTOR = 3
#: One one-arc-second ``.hgt`` as gdalwarp writes it: 3601 x 3601 Int16,
#: 25,934,402 bytes, measured.
HGT_BYTES = 25_934_402
#: A square's elevation scratch: its own 25 tiles as ``.hgt`` files at most,
#: removed before the next square.
ELEVATION_SCRATCH_BYTES = 25 * HGT_BYTES
#: One square's ``.bef``, kept until the build ends: 7,987,865 bytes for
#: Delaware's square, measured; rounded up.
BEF_BYTES = 8_000_000

TERRAIN_NOTE = (
    f"QMapShack's maps at {GARMIN_FACTOR}x each download with "
    f"{GARMIN_SCRATCH_FACTOR}x of scratch, the Routino database at {ROUTINO_FACTOR}x "
    f"of every download together with up to {ROUTINO_SCRATCH_FACTOR}x of scratch, and "
    f"contours at about {human_size(CONTOUR_BYTES)} a tile with up to "
    f"{human_size(CONTOUR_SCRATCH_BYTES)} of scratch, {MEASURED}; BRouter's routing "
    f"files at {BROUTER_FACTOR}x of every download together ({MEASURED}), with "
    f"{BROUTER_SCRATCH_FACTOR}x of scratch allowed, not measured; and US Topo quads "
    f"warped at {WARP_FACTOR}x each download with as much again of scratch, measured "
    f"on one quad"
)


def garmin_estimate(size: int) -> int:
    return round(size * GARMIN_FACTOR)


def routino_estimate(total: int) -> int:
    return round(total * ROUTINO_FACTOR)


def brouter_estimate(total: int) -> int:
    return round(total * BROUTER_FACTOR)


def tile_key(name: str) -> str:
    """The ledger key of a terrain tile: its name, which no slug can be."""
    return f"tile {name}"


@dataclass
class TerrainLedger:
    """Which of piece 2's steps failed this run, keyed by what failed."""

    failed: dict[str, str] = field(default_factory=dict)

    def fail(self, key: str, message: str) -> str:
        self.failed.setdefault(key, message)
        return f"FAILED, the rest continues: {message}"

    def check(self) -> str:
        if not self.failed:
            return "every QMapShack map, routing database and terrain tile installed"
        lines = "\n".join(f"  {message}" for message in self.failed.values())
        raise BackendError(
            f"{len(self.failed)} part(s) of QMapShack's maps, routing or terrain did not "
            f"install; everything else did:\n{lines}"
        )

    def step(self) -> Action:
        return Action(
            kind="check-terrain",
            description=(
                "Fail the transaction by name if any QMapShack map, routing database "
                "or terrain tile did not install"
            ),
            detail="terrain",
            perform=self.check,
        )


@dataclass(frozen=True)
class TerrainWork:
    """Bytes piece 2 moves this run, for the disk check."""

    tiles: int = 0
    """Bytes of tiles downloaded."""
    garmin: tuple[int, ...] = ()
    """The ``.osm.pbf`` size of each region mkgmap builds a map from."""
    routino: int = 0
    """The sum of every ``.osm.pbf`` when the database is rebuilt, else 0."""
    contour_tiles: int = 0
    """How many tiles have contours drawn."""
    brouter: int = 0
    """The sum of every ``.osm.pbf`` when BRouter's routing files are rebuilt, else 0."""
    brouter_regions: int = 0
    """How many regions they are rebuilt over: two or more are merged first."""
    brouter_squares: int = 0
    """How many 5 degree squares get elevation built."""
    quads: int = 0
    """Bytes of US Topo sheets downloaded (D-068)."""
    warp: tuple[int, ...] = ()
    """The download size of each sheet ``ustopo-mosaic`` warps."""

    def any(self) -> bool:
        return bool(
            self.tiles
            or self.garmin
            or self.routino
            or self.contour_tiles
            or self.brouter
            or self.quads
            or self.warp
        )


def terrain_needs(
    work: TerrainWork,
    *,
    cache: Path,
    garmin_staging: Path,
    routino_staging: Path,
    contour_staging: Path,
    prefix: Path,
    brouter_staging: Path | None = None,
    mosaic_staging: Path | None = None,
) -> dict[Path, int]:
    """Bytes each location needs: each tile and sheet in the fetch cache and
    under the prefix; the largest Garmin build's scratch (they run one at a
    time and each is removed before the next); the Routino build's scratch
    and output; one tile's contour scratch plus every rasterised tile; the
    largest sheet's warp scratch (one at a time, D-068); and every output
    again under the prefix. BRouter's build (D-063): its allowance of scratch,
    the merged input when there are two regions or more, one square's
    ``.hgt`` files and every square's ``.bef`` in its staging directory, and
    its routing files under the prefix."""
    garmin_out = sum(garmin_estimate(size) for size in work.garmin)
    routino_out = routino_estimate(work.routino)
    brouter_out = brouter_estimate(work.brouter)
    contours = work.contour_tiles * CONTOUR_BYTES
    warped = round(sum(work.warp) * WARP_FACTOR)
    brouter_scratch = (
        BROUTER_SCRATCH_FACTOR * work.brouter
        + (work.brouter if work.brouter_regions > 1 else 0)
        + (
            ELEVATION_SCRATCH_BYTES + BEF_BYTES * work.brouter_squares
            if work.brouter_squares
            else 0
        )
        + brouter_out
        if work.brouter
        else 0
    )
    needs: dict[Path, int] = {}
    for where, amount in (
        (cache, work.tiles + work.quads),
        (garmin_staging, GARMIN_SCRATCH_FACTOR * max(work.garmin, default=0)),
        (routino_staging, ROUTINO_SCRATCH_FACTOR * work.routino),
        (contour_staging, (CONTOUR_SCRATCH_BYTES if work.contour_tiles else 0) + contours),
        (brouter_staging or routino_staging, brouter_scratch),
        (mosaic_staging or contour_staging, WARP_SCRATCH_FACTOR * max(work.warp, default=0)),
        (
            prefix,
            work.tiles + garmin_out + routino_out + contours + brouter_out + work.quads + warped,
        ),
    ):
        needs[where] = needs.get(where, 0) + round(amount)
    return needs


def combined_shortfall(
    map_needs: Mapping[Path, int],
    terrain: Mapping[Path, int],
    *,
    phone: Mapping[Path, int] | None = None,
    tiles: Mapping[Path, int] | None = None,
    free_at: Callable[[Path], int] = free_bytes_at,
    device_of: Callable[[Path], int] = device_at,
) -> str | None:
    """Piece 1's disk refusal over piece 1's, piece 2's, the phone
    converters' (D-067) and the vector-tile converter's (D-071) needs
    together, saying what each added part was estimated from when it counted."""
    phone = phone or {}
    tiles = tiles or {}
    merged = dict(map_needs)
    for extra in (terrain, phone, tiles):
        for path, amount in extra.items():
            merged[path] = merged.get(path, 0) + amount
    short = disk_shortfall(merged, free_at=free_at, device_of=device_of)
    if short is None:
        return short
    notes = [
        note
        for note, part in ((TERRAIN_NOTE, terrain), (PHONE_NOTE, phone), (TILES_NOTE, tiles))
        if any(part.values())
    ]
    if not notes:
        return short
    return f"{short}\n  The estimate includes {'; and '.join(notes)}."
