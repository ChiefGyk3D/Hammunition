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
   square not in it has no published tile: sea, or land Copernicus does
   not release).

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
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path

from .backends.base import CommandRunner
from .backends.brouter import JAR_GLOB, BRouterConverter, InputPins
from .backends.brouter import Source as BRouterSource
from .backends.dem import (
    TIF,
    TILES,
    DemResolution,
    DemTilesBackend,
    RegionTiles,
    TerrainDisclosure,
    read_record,
)
from .backends.derived import Converter
from .backends.garmin import MKGMAP_HEAP, SPLITTER_HEAP, GarminConverter
from .backends.gdal_dem import GdalDemConverter
from .backends.regions import MapLedger, MapResolution, data_root
from .backends.routino import RoutinoConverter, Source
from .backends.staging import Staging
from .backends.terrain import TerrainLedger, TerrainWork, terrain_needs
from .copernicus import (
    CopernicusError,
    TileFile,
    TilePin,
    TileProbe,
    load_pins,
    load_tile_list,
    parse_poly,
    resolve_tile,
    select,
    squares_touching,
)
from .fetch import Fetcher
from .geofabrik import BASE, GeofabrikError, Probe, RegionFile
from .manifest.schema import BinaryInstall, DemTilesInstall, DerivedDataInstall
from .plan import InstallPlan, PlannedPackage


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
    tiles, unpublished = select(squares_touching(outer, holes), tile_list)
    return RegionTiles(region, slug, tiles, unpublished)


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


# ---------------------------------------------------------------------------
# The whole of piece 2 for one install run: which units the plan holds, the
# backends that build them, what the plan discloses and what the disk needs.
# ---------------------------------------------------------------------------

TILE_LIST = Path("data") / "copernicus-glo30-tiles.txt"
PINS = Path("data") / "copernicus-glo30-pins.yaml"
#: The splitter's heap through ``JAVA_OPTS``, mkgmap's through
#: ``JAVA_TOOL_OPTIONS``: Debian's mkgmap wrapper ignores ``JAVA_OPTS``
#: (Task 6 review, I2), so one variable alone would leave mkgmap on the JVM's
#: default heap.
SPLITTER_ENV = {"JAVA_OPTS": SPLITTER_HEAP, "JAVA_TOOL_OPTIONS": MKGMAP_HEAP}


def _planned(
    plan: InstallPlan, method: type[object], converter: str | None = None
) -> PlannedPackage | None:
    for planned in plan.packages:
        block = planned.block.install
        if isinstance(block, method) and (
            converter is None or getattr(block, "converter", None) == converter
        ):
            return planned
    return None


def resolve_station_terrain(
    plan: InstallPlan,
    maps: MapResolution,
    catalog_root: Path,
    *,
    prefix: Path,
    region_probe: Probe,
    tile_probe: TileProbe,
) -> DemResolution:
    """The plan's terrain, or an empty resolution when it holds no dem-tiles unit.

    The regions are this run's resolved files and the ones kept offline.
    A missing tile list is refused by name: without it every square would
    look unpublished, and a region would silently get no terrain.

    A region's record is written only when its terrain is installed, so until
    then every plan -- a dry run included -- asks for its outline again; the
    plan says so (Task 10's note, ruled at Task 13: no plan-time cache, which
    under sudo would be a root-owned file in the operator's cache)."""
    unit = _planned(plan, DemTilesInstall)
    if unit is None:
        return DemResolution()
    listed = catalog_root / TILE_LIST
    try:
        tile_list = load_tile_list(listed)
    except OSError as exc:
        raise CopernicusError(
            f"the Copernicus tile list {listed} cannot be read ({exc.strerror or exc}); "
            f"it is carried in the catalog, and scripts/gen_copernicus_pins.py --refresh-list "
            f"writes it"
        ) from exc
    pins_path = catalog_root / PINS
    pins = load_pins(pins_path) if pins_path.is_file() else {}
    regions = [(f.region, f.slug) for f in maps.files]
    ours = {slug for _, slug in regions}
    regions += [(k.region, k.slug) for k in maps.kept if k.slug not in ours]
    return resolve_terrain(
        regions,
        installed=data_root(prefix) / unit.name,
        tile_list=tile_list,
        pins=pins,
        region_probe=region_probe,
        tile_probe=tile_probe,
    )


def brouter_pins(plan: InstallPlan) -> InputPins:
    """The jar and the filters' version the plan installs for the BRouter
    build (D-063), from the planned manifests: a BRouter bumped in this run
    is seen before its new tree is on disk."""
    build = _planned(plan, DerivedDataInstall, "brouter-mapcreator")
    if build is None or not isinstance(build.block.install, DerivedDataInstall):
        return InputPins()
    block = build.block.install
    planned = {p.name: p for p in plan.packages}
    jar = None
    program = planned.get(block.program or "")
    if program is not None and isinstance(program.block.install, BinaryInstall):
        marker = program.block.install.tree_marker
        if marker is not None and fnmatch(marker, JAR_GLOB):
            jar = marker
    profiles = planned.get(block.profiles or "")
    return InputPins(jar=jar, profiles=profiles.manifest.version if profiles else None)


@dataclass(frozen=True)
class TerrainRun:
    """Piece 2's backends for one run, sharing one :class:`TerrainLedger`."""

    ledger: TerrainLedger
    dem: DemTilesBackend
    garmin: GarminConverter
    routino: RoutinoConverter
    gdal: GdalDemConverter
    brouter: BRouterConverter

    @property
    def converters(self) -> dict[str, Converter]:
        return {
            "mkgmap": self.garmin,
            "routino-planetsplitter": self.routino,
            "gdal-dem": self.gdal,
            "brouter-mapcreator": self.brouter,
        }

    def disclosure(self, plan: InstallPlan) -> TerrainDisclosure | None:
        """What the plan says about piece 2; None when it holds none of its units."""
        dem = _planned(plan, DemTilesInstall)
        garmin = _planned(plan, DerivedDataInstall, "mkgmap")
        routino = _planned(plan, DerivedDataInstall, "routino-planetsplitter")
        gdal = _planned(plan, DerivedDataInstall, "gdal-dem")
        brouter = _planned(plan, DerivedDataInstall, "brouter-mapcreator")
        if not (dem or garmin or routino or gdal or brouter):
            return None
        sources = self._routino_sources(routino)
        rebuilt, tiles, squares = self._brouter_work(brouter)
        # Contours from the tiles still to draw; `drawing` from those and the
        # record check -- not from a count of steps, which would count a
        # removal as drawing (Task 12 review).
        contours = self.gdal.pending(gdal.manifest) if gdal is not None else []
        drawing = gdal is not None and (bool(contours) or not self.gdal.current(gdal.manifest))
        licence = dem.block.install if dem is not None else None
        return TerrainDisclosure(
            resolution=self.dem.resolution if dem is not None else DemResolution(),
            licence=licence.licence if isinstance(licence, DemTilesInstall) else "",
            licence_url=licence.licence_url if isinstance(licence, DemTilesInstall) else "",
            garmin=tuple(self.garmin.pending(garmin.manifest)) if garmin is not None else (),
            routino_regions=len(sources),
            routino_total=sum(s.size for s in sources),
            contours=len(contours),
            drawing=drawing,
            brouter_regions=len(rebuilt),
            brouter_total=sum(s.size for s in rebuilt),
            brouter_tiles=tiles,
            brouter_squares=squares,
        )

    def _brouter_work(self, brouter: PlannedPackage | None) -> tuple[list[BRouterSource], int, int]:
        """The regions BRouter's routing files are rebuilt over this run, and
        the tiles and squares folded in; nothing when they are current."""
        if brouter is None or not isinstance(brouter.block.install, DerivedDataInstall):
            return [], 0, 0
        block = brouter.block.install
        rebuilt = self.brouter.pending(brouter.manifest, block)
        if not rebuilt:
            return [], 0, 0
        return rebuilt, len(self.brouter.wanted_tiles(block)), len(self.brouter.squares(block))

    def _routino_sources(self, routino: PlannedPackage | None) -> list[Source]:
        if routino is None or not isinstance(routino.block.install, DerivedDataInstall):
            return []
        return self.routino.pending(routino.manifest, routino.block.install)

    def needs(self, plan: InstallPlan, *, cache: Path, prefix: Path) -> dict[Path, int]:
        """Bytes piece 2 needs per directory this run; empty when it has no units."""
        disclosed = self.disclosure(plan)
        if disclosed is None:
            return {}
        work = TerrainWork(
            tiles=sum(t.size for t in disclosed.resolution.fetch),
            garmin=tuple(f.size for f in disclosed.garmin),
            routino=disclosed.routino_total,
            contour_tiles=disclosed.contours,
            brouter=disclosed.brouter_total,
            brouter_regions=disclosed.brouter_regions,
            brouter_squares=disclosed.brouter_squares,
        )
        return terrain_needs(
            work,
            cache=cache,
            garmin_staging=self.garmin.staging.directory,
            routino_staging=self.routino.staging.directory,
            contour_staging=self.gdal.staging.directory,
            prefix=prefix,
            brouter_staging=self.brouter.staging.directory,
        )


def build_terrain_run(
    *,
    prefix: Path,
    builds: Path,
    owner: str | None,
    runner: CommandRunner | None,
    fetcher: Fetcher,
    files: Sequence[RegionFile],
    keep: frozenset[str],
    regions: MapLedger,
    resolution: DemResolution,
    pins: InputPins | None = None,
) -> TerrainRun:
    """Every piece-2 backend for one run. Each converter stages in its own
    directory under the operator's build tree and runs as the operator."""
    ledger = TerrainLedger()
    return TerrainRun(
        ledger=ledger,
        dem=DemTilesBackend(
            fetcher=fetcher,
            prefix=prefix,
            resolution=resolution,
            keep=keep,
            ledger=ledger,
            runner=runner,
        ),
        garmin=GarminConverter(
            prefix=prefix,
            files=files,
            staging=Staging(builds / "osm-garmin", owner=owner, environ=SPLITTER_ENV),
            keep=keep,
            regions=regions,
            ledger=ledger,
            runner=runner,
        ),
        routino=RoutinoConverter(
            prefix=prefix,
            files=files,
            staging=Staging(builds / "osm-routino", owner=owner),
            keep=keep,
            regions=regions,
            ledger=ledger,
            runner=runner,
        ),
        gdal=GdalDemConverter(
            prefix=prefix,
            resolution=resolution,
            staging=Staging(builds / "dem-qmapshack", owner=owner),
            ledger=ledger,
            runner=runner,
        ),
        brouter=BRouterConverter(
            prefix=prefix,
            files=files,
            resolution=resolution,
            staging=Staging(builds / "brouter-segments", owner=owner),
            keep=keep,
            regions=regions,
            ledger=ledger,
            runner=runner,
            pins=pins or InputPins(),
        ),
    )
