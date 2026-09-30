# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The ``tilemaker-pmtiles`` converter: one PMTiles file of vector tiles per region.  D-071.

The archive's ``tilemaker`` (3.0.0 on Debian 13 and Parrot 7) turns a region's
``.osm.pbf`` into vector tiles in the OpenMapTiles schema, which the OSM Bright
style draws in the browser page ``hammunition reference serve`` serves. The
package ships no profile, so tilemaker's own ``config-openmaptiles.json`` and
``process-openmaptiles.lua`` at v3.0.0 come from the ``vector-map-kit`` data
unit (members of Debian's copy of that tag's tarball), with the four Natural
Earth layers the config names: the ocean, urban areas, glaciers and Antarctic
ice shelves.

**The ocean is Natural Earth's**, not osmdata.openstreetmap.de's water
polygons: both of those sets, full and simplified, are rebuilt daily with no
checksum (the simplified one changed size overnight, measured 2026-09-29/30),
so neither can be pinned. ``ne_10m_ocean`` is one world-sized polygon, so it is
clipped to each region's box first with ``ogr2ogr -clipsrc`` (0.1 s on
Delaware's box, measured); the box is read from the region's ``.osm.pbf``
header by :func:`hammunition.osm_pbf.header_bbox`, the capped reader Navit's
centre uses. A header with no box, or one crossing the antimeridian, gets the
whole polygon, which is correct and slower, and the outcome says so.

Each region takes two steps, as :mod:`hammunition.backends.mapsforge`'s do.
**convert**, as the operator in ``<staging>/<slug>.work/`` under its lock:
clear it; make ``coastline/``, ``landcover/<layer>/`` and ``store/``; clip or
link the ocean as ``coastline/water_polygons``, link the land-cover layers
where the config looks for them; run tilemaker with ``--store store`` (0.49 GB
of memory on Delaware against 2.8 GB without, measured by the spike); check the
output starts with ``PMTiles``. **install**: publish into
``<data>/osm-pmtiles/<slug>.pmtiles`` re-verified, with a ``.source`` sidecar
(the snapshot and :data:`CONVERTER`), and clear the working directory.

A failure is recorded in the :class:`TilesLedger`, the other regions
continue, and the ledger's step, last in the transaction, fails it by name.
"""

from __future__ import annotations

import shlex
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path

from .. import osm_pbf
from ..geofabrik import RegionFile
from ..manifest.schema import DerivedDataInstall, PackageManifest
from .base import Action, BackendError, Command, CommandRunner
from .data import human_size
from .regions import (
    PBF,
    SOURCE,
    MapLedger,
    data_root,
    installed_converter,
    installed_snapshot,
    prefix_writer,
    removal_steps,
)
from .staging import REFUSED, Staging
from .verified import PrefixWriter

#: tilemaker's profile inside the kit's data directory (members of the
#: v3.0.0 tarball, extracted into ``tilemaker/``).
CONFIG = Path("tilemaker/resources/config-openmaptiles.json")
PROCESS = Path("tilemaker/resources/process-openmaptiles.lua")
#: The Natural Earth layers the pinned config names, as the kit installs them.
OCEAN = "ne_10m_ocean"
LANDCOVER: tuple[str, ...] = (
    "ne_10m_urban_areas",
    "ne_10m_glaciated_areas",
    "ne_10m_antarctic_ice_shelves_polys",
)
SHAPE_PARTS: tuple[str, ...] = ("shp", "shx", "dbf", "prj")
#: Where the config looks for the ocean, relative to tilemaker's directory.
WATER = Path("coastline/water_polygons")
#: Degrees added round the header box before the ocean is clipped to it.
PAD = 0.1
#: PMTiles v3 starts with these seven bytes, then its version.
MAGIC = "PMTiles"
#: The first tilemaker that writes PMTiles (its 3.0 changelog); Ubuntu 24.04
#: carries 2.4.0. Checked at plan time against the archive (D-071).
TILEMAKER_FLOOR = (3, 0)

MEASURED = "measured on one region"
#: ``.pmtiles`` against its ``.osm.pbf``: 20.1 MB / 22.14 MB on Delaware (the
#: spike, with osmdata's simplified water polygons), 0.908, rounded up.
FACTOR = 0.91
#: Not measured: the spike did not size ``--store``. An allowance, and the
#: plan says so.
SCRATCH_FACTOR = 3
#: Recorded in each output's ``.source`` sidecar; bumped when the argv or the
#: kit's profile changes the output.
CONVERTER = "tilemaker-pmtiles 1"

TILES_NOTE = (
    f"the vector-tile maps at {FACTOR}x each download ({MEASURED}) with about "
    f"{SCRATCH_FACTOR}x of scratch allowed, not measured"
)


def estimate(size: int) -> int:
    return round(size * FACTOR)


def tilemaker_argv(pbf: Path, out: Path, kit: Path, work: Path) -> list[str]:
    """The fixed argv of one run. Nothing in it comes from a manifest."""
    return [
        "tilemaker",
        "--input",
        str(pbf),
        "--output",
        str(out),
        "--config",
        str(kit / CONFIG),
        "--process",
        str(kit / PROCESS),
        "--store",
        str(work / "store"),
    ]


def clip_box(bbox: osm_pbf.BBox) -> tuple[float, float, float, float] | None:
    """(west, south, east, north) for ``ogr2ogr -clipsrc``: the header's
    (left, right, top, bottom) with :data:`PAD` round it, kept on the globe;
    None for a box that crosses the antimeridian, which ``-clipsrc`` cannot
    take as one rectangle."""
    left, right, top, bottom = bbox
    if right < left:
        return None
    return (
        max(-180.0, left - PAD),
        max(-90.0, bottom - PAD),
        min(180.0, right + PAD),
        min(90.0, top + PAD),
    )


def ogr2ogr_argv(box: tuple[float, float, float, float], ocean: Path) -> list[str]:
    """The ocean clipped to *box*, written where the config looks for it."""
    return [
        "ogr2ogr",
        "-f",
        "ESRI Shapefile",
        "-clipsrc",
        *(f"{value:.6f}" for value in box),
        "-nln",
        WATER.name,
        f"{WATER}.shp",
        str(ocean),
    ]


def kit_files(kit: Path) -> list[Path]:
    """Every file of the kit the converter reads."""
    shapes = [kit / f"{layer}.{part}" for layer in (OCEAN, *LANDCOVER) for part in SHAPE_PARTS]
    return [kit / CONFIG, kit / PROCESS, *shapes]


def _tail(text: str) -> str:
    return text.strip()[-300:]


@dataclass
class TilesLedger:
    """Which vector-tile map failed this run, keyed by unit and region."""

    failed: dict[str, str] = field(default_factory=dict)

    def fail(self, key: str, message: str) -> str:
        self.failed.setdefault(key, message)
        return f"FAILED, the rest continues: {message}"

    def check(self) -> str:
        if not self.failed:
            return "every vector-tile map installed"
        lines = "\n".join(f"  {message}" for message in self.failed.values())
        raise BackendError(
            f"{len(self.failed)} vector-tile map(s) did not install; everything else did:\n{lines}"
        )

    def step(self) -> Action:
        return Action(
            kind="check-vector-tiles",
            description="Fail the transaction by name if any vector-tile map did not install",
            detail="vector-tile maps",
            perform=self.check,
        )


@dataclass(frozen=True)
class TilesConverter:
    """Turns a ``derived`` block with ``converter: tilemaker-pmtiles`` into steps."""

    prefix: Path
    files: Sequence[RegionFile]
    staging: Staging
    keep: frozenset[str] = frozenset()
    regions: MapLedger = field(default_factory=MapLedger)
    """Piece 1's ledger, read only: a region that did not install is not built."""
    ledger: TilesLedger = field(default_factory=TilesLedger)
    runner: CommandRunner | None = None
    euid: int | None = None
    privileged: bool | None = None
    suffix = ".pmtiles"

    @property
    def writer(self) -> PrefixWriter:
        return prefix_writer(self.prefix, self.privileged, self.runner, self.euid)

    def data_dir(self, manifest: PackageManifest) -> Path:
        return data_root(self.prefix) / manifest.name

    def _current(self, dest: Path, region: RegionFile) -> bool:
        return (
            dest.is_file()
            and installed_snapshot(dest) == region.snapshot
            and installed_converter(dest) == CONVERTER
        )

    def pending(self, manifest: PackageManifest, block: DerivedDataInstall) -> list[RegionFile]:
        """Regions this run builds: no file, or one from another snapshot or converter."""
        out = self.data_dir(manifest)
        return [f for f in self.files if not self._current(out / f"{f.slug}{self.suffix}", f)]

    def steps(self, manifest: PackageManifest, block: DerivedDataInstall) -> list[Action | Command]:
        if block.kit is None:  # pragma: no cover - the schema requires it
            raise BackendError(f"{manifest.name}: a tilemaker-pmtiles block names no kit")
        out = self.data_dir(manifest)
        source_dir = data_root(self.prefix) / block.source
        kit = data_root(self.prefix) / block.kit
        writer = self.writer
        steps: list[Action | Command] = []
        for region in self.files:
            dest = out / f"{region.slug}{self.suffix}"
            if self._current(dest, region):
                continue
            pbf = source_dir / f"{region.slug}{PBF}"
            work = self.staging.workdir(region.slug)
            staged = work / f"{region.slug}{self.suffix}"
            key = f"{manifest.name}:{region.slug}"
            built: dict[str, str] = {}
            shown = shlex.join(tilemaker_argv(pbf, staged, kit, work))
            steps.append(
                Action(
                    kind="convert",
                    description=(
                        f"Build the vector-tile map of {region.region} ({region.snapshot}), "
                        f"as the operator, in {work}: clip Natural Earth's ocean "
                        f"({kit / OCEAN}.shp) to the region's box with ogr2ogr, link the "
                        f"three land-cover layers, then {shown}; output about "
                        f"{human_size(estimate(region.size))} ({FACTOR}x the download, "
                        f"{MEASURED}) and about {human_size(SCRATCH_FACTOR * region.size)} "
                        f"of scratch allowed (not measured)"
                    ),
                    detail=str(work),
                    perform=partial(self._convert, region, key, pbf, kit, work, staged, built),
                )
            )
            steps.append(
                Action(
                    kind="install-data",
                    description=(
                        f"Install the vector-tile map of {region.region} ({region.snapshot}), "
                        f"then clear its scratch {work}"
                    ),
                    # The destination, verbatim, for uninstall's attribution replay.
                    detail=str(dest),
                    perform=partial(self._install, region, key, work, staged, dest, built, writer),
                    requires_root=writer.privileged,
                )
            )
        keep = {f.slug for f in self.files} | set(self.keep)
        steps.extend(removal_steps(out, self.suffix, keep, writer))
        return steps

    def _ocean(self, region: RegionFile, pbf: Path, kit: Path, work: Path) -> tuple[bool, str]:
        """Clip the ocean to the region's box, or link the whole of it.
        (done, what was done or why not)."""
        try:
            bbox = osm_pbf.header_bbox(pbf)
            why = "its header carries no bounding box"
        except (OSError, osm_pbf.OsmPbfError) as exc:
            bbox, why = None, f"its header could not be read ({exc})"
        box = clip_box(bbox) if bbox is not None else None
        if bbox is not None and box is None:
            why = "its box crosses the antimeridian"
        if box is not None:
            made = self.staging.run(ogr2ogr_argv(box, kit / f"{OCEAN}.shp"), cwd=work)
            if made.returncode != 0 or self.staging.digest(work / f"{WATER}.shp") is None:
                return False, (
                    f"ogr2ogr did not clip the ocean (exit {made.returncode}): "
                    f"{_tail(made.stderr or made.stdout)}"
                )
            return True, "the ocean clipped to the region's box"
        linked = self._link(
            [kit / f"{OCEAN}.{part}" for part in SHAPE_PARTS],
            [work / f"{WATER}.{part}" for part in SHAPE_PARTS],
            work,
        )
        if linked is not None:
            return False, linked
        return True, f"the whole world's ocean polygon used, because {why}: slower, not wrong"

    def _link(self, sources: Sequence[Path], targets: Sequence[Path], work: Path) -> str | None:
        """Symbolic links, made by the operator; why not, or None."""
        for source, target in zip(sources, targets, strict=True):
            made = self.staging.run(["ln", "-s", "--", str(source), str(target)], cwd=work)
            if made.returncode != 0:
                return f"could not link {target}: {_tail(made.stderr) or 'refused'}"
        return None

    def _convert(
        self,
        region: RegionFile,
        key: str,
        pbf: Path,
        kit: Path,
        work: Path,
        staged: Path,
        built: dict[str, str],
    ) -> str:
        if region.slug in self.regions.failed:
            return f"skipped: {region.region} did not install"
        if not pbf.is_file():
            return self.ledger.fail(key, f"{region.region}: {pbf} is not installed")
        missing = [str(p) for p in kit_files(kit) if not p.is_file()]
        if missing:
            return self.ledger.fail(
                key,
                f"{region.region}: tilemaker was not started, because the kit is missing "
                f"{', '.join(missing)} (`hammunition install vector-map-kit`)",
            )
        refusal = self.staging.prepare(work)
        if refusal is not None:
            return self.ledger.fail(key, f"{region.region}: {refusal}")
        cleared = self.staging.clear(work)  # a failed run's leftovers, under the lock
        if cleared.returncode != 0:
            why = "refused" if cleared.returncode == REFUSED else "failed"
            return self.ledger.fail(
                key, f"{region.region}: clearing {work} {why}: {_tail(cleared.stderr)}"
            )
        layers = [work / "landcover" / layer for layer in LANDCOVER]
        refusal = self.staging.prepare(work / WATER.parent, *layers, work / "store")
        if refusal is not None:
            return self.ledger.fail(key, f"{region.region}: {refusal}{self._scratch(work, '; ')}")
        done, ocean = self._ocean(region, pbf, kit, work)
        if not done:
            return self.ledger.fail(key, f"{region.region}: {ocean}{self._scratch(work, '; ')}")
        linked = self._link(
            [kit / f"{layer}.{part}" for layer in LANDCOVER for part in SHAPE_PARTS],
            [
                work / "landcover" / layer / f"{layer}.{part}"
                for layer in LANDCOVER
                for part in SHAPE_PARTS
            ],
            work,
        )
        if linked is not None:
            return self.ledger.fail(key, f"{region.region}: {linked}{self._scratch(work, '; ')}")
        made = self.staging.run(tilemaker_argv(pbf, staged, kit, work), cwd=work)
        if made.returncode == REFUSED:
            return self.ledger.fail(
                key,
                f"{region.region}: tilemaker was not started: {_tail(made.stderr) or 'refused'}",
            )
        digest = self.staging.digest(staged)
        if made.returncode != 0 or digest is None:
            return self.ledger.fail(
                key,
                f"{region.region}: tilemaker wrote no PMTiles file from {pbf.name} "
                f"(exit {made.returncode}): {_tail(made.stderr or made.stdout)}"
                f"{self._scratch(work, '; ')}",
            )
        if not self._starts_with(staged, work):
            return self.ledger.fail(
                key,
                f"{region.region}: {staged.name} is not a PMTiles file (it does not start "
                f"with {MAGIC!r}), though tilemaker exited {made.returncode}"
                f"{self._scratch(work, '; ')}",
            )
        built["sha256"] = digest
        who = self.staging.who()
        return (
            f"built the vector-tile map of {region.region}{' ' + who if who else ''}, "
            f"{ocean} (staged, {staged})"
        )

    def _starts_with(self, path: Path, work: Path) -> bool:
        """Whether *path* starts with :data:`MAGIC`, read by the operator's own
        ``head`` and compared as hex in the same shell, so only the exit status
        is read (the mapsforge converter's check, D-067)."""
        check = self.staging.run(
            [
                "sh",
                "-c",
                'test "$(head -c "$1" -- "$2" | od -An -v -tx1 | tr -d " \\n")" = "$3"',
                "sh",
                str(len(MAGIC)),
                str(path),
                MAGIC.encode("ascii").hex(),
            ],
            cwd=work,
        )
        return check.returncode == 0

    def _install(
        self,
        region: RegionFile,
        key: str,
        work: Path,
        staged: Path,
        dest: Path,
        built: dict[str, str],
        writer: PrefixWriter,
    ) -> str:
        if "sha256" not in built:
            return f"skipped: the vector-tile map of {region.region} was not built"
        failure = None
        try:
            self.staging.publish(staged, dest, digest=built["sha256"], writer=writer)
            writer.write_text(
                dest.with_name(dest.name + SOURCE), f"{region.snapshot}\nconverter: {CONVERTER}\n"
            )
        except (BackendError, OSError) as exc:
            failure = str(exc)
        scratch = self._scratch(work, "")
        if failure is not None:
            return self.ledger.fail(
                key, f"{region.region}: {failure}{'; ' + scratch if scratch else ''}"
            )
        if scratch:
            return self.ledger.fail(key, f"{region.region}: installed {dest}, but {scratch}")
        return f"installed {dest}; cleared {work}"

    def _scratch(self, work: Path, lead: str) -> str:
        """Clear *work* under its lock: "" when it cleared, else *lead* and why not."""
        cleared: subprocess.CompletedProcess[str] = self.staging.clear(work)
        if cleared.returncode == 0:
            return ""
        return f"{lead}its scratch {work} was not cleared: {_tail(cleared.stderr) or 'no reason given'}"
