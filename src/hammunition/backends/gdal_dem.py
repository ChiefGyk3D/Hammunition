# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The ``gdal-dem`` converter: QMapShack's elevation and contour overlay,
from the installed tiles.  D-061.

Two outputs under ``<data>/<unit>/``:

* ``dem/dem.vrt`` -- a GDAL virtual raster over every installed tile, by
  absolute path. QMapShack's DEM: it draws hillshade and slope from it and
  reads elevation for track profiles. It does not draw contour lines.
* ``contours/contours.vrt`` over ``contours/tiles/<tile>.tif`` -- plain
  unlabelled 20 m contour lines rasterised per tile, a raster map QMapShack
  lists beside the Garmin maps. Legible, not pretty.

Per tile, as the operator in the build's one working directory
``<staging>/dem.work/`` (:meth:`Staging.workdir`): ``gdal_contour -i 20``
into a GeoPackage (4 s on one mountain tile, 97.8 MB), then
``gdal_rasterize`` into a DEFLATE Byte GeoTIFF on the tile's own one degree
square at 7200 x 7200 (1.5 s, 5.4 MB); the raster is published as
``contours/tiles/<tile>.tif`` with a ``.source`` sidecar naming the tile and
:data:`CONVERTER`, and the working directory -- GeoPackage and all -- is
emptied. ``gdal_contour`` exits 0 onto an existing GeoPackage and appends to
it (measured), so the working directory is emptied before each tile too.

The two virtual rasters are rebuilt whenever the set of tiles or the
converter changes, from the installed files by absolute path (measured:
gdalbuildvrt writes ``relativeToVRT="0"`` for a file outside the VRT's own
directory), so each VRT is correct wherever it is copied -- and names the
installed tiles, which must therefore be installed first. Their inputs are
the tiles this run resolves that are on disk as ``.tif`` files, never a
record of what should be: a VRT naming a missing file is a broken map.
Every argv here was run on 2026-09-28 with Debian's gdal-bin 3.10.3.

``<data>/<unit>/tiles.source`` records the tiles both VRTs were built over
and, on its last line, :data:`CONVERTER`. It is written only when every
resolved tile made it into both, so a missing one is built next run.

One lock for the whole build, ``<staging>/dem.work.lock``: every run and
every clear holds it (``lock=`` passed explicitly), so no other conversion
clears this build's scratch while a phase is using it. Scratch is only ever
cleared by :meth:`Staging.clear`; a refused one (125) deletes nothing and
fails that part by name, and a clear that fails is reported, never a silent
"cleared".
"""

from __future__ import annotations

import shlex
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path

from ..manifest.schema import DerivedDataInstall, PackageManifest
from ..usgs3dep import PIXELS as THREEDEP_PIXELS
from ..usgs3dep import TILE as THREEDEP_TILE
from ..usgs3dep import dem_square
from .base import Action, BackendError, Command, CommandRunner
from .data import human_size
from .dem import TIF, DemResolution
from .regions import SOURCE, data_root, installed_converter, prefix_writer, removal_steps
from .staging import REFUSED, Staging
from .terrain import (
    MEASURED,
    TerrainLedger,
    contour_bytes,
    contour_scratch,
    tile_key,
)
from .verified import PrefixWriter

INTERVAL = 20
PIXELS = 7200
RECORD = "tiles.source"
#: What the contours and rasters were built by: the last line of
#: :data:`RECORD` and of each contour tile's sidecar. Bumped whenever an argv
#: changes the output, so everything an older one drew is drawn again.
CONVERTER = "gdal-dem 1"
#: The build's one working directory under the staging directory, and its lock.
WORKDIR = "dem"
#: The ledger key of the virtual rasters; a tile's is ``gdal-dem:<tile>``.
KEY = "gdal-dem"


def contour_argv(tile: Path, gpkg: Path) -> list[str]:
    return ["gdal_contour", "-q", "-i", str(INTERVAL), "-a", "elev", str(tile), str(gpkg)]


def pixels_for(name: str) -> int:
    """The contour raster's width and height for tile *name*: 7,200 for a
    Copernicus tile, 10,812 for a USGS 3DEP 1/3" one, whose detail 7,200
    would throw a third of away (the spike, 2026-09-29)."""
    return THREEDEP_PIXELS if THREEDEP_TILE.fullmatch(name) else PIXELS


def rasterize_argv(gpkg: Path, out: Path, name: str) -> list[str]:
    lat, lon = dem_square(name)
    pixels = pixels_for(name)
    return [
        "gdal_rasterize",
        "-q",
        "-l",
        "contour",
        "-burn",
        "1",
        "-init",
        "0",
        "-a_nodata",
        "0",
        "-ot",
        "Byte",
        "-te",
        str(lon),
        str(lat),
        str(lon + 1),
        str(lat + 1),
        "-ts",
        str(pixels),
        str(pixels),
        "-co",
        "COMPRESS=DEFLATE",
        "-of",
        "GTiff",
        str(gpkg),
        str(out),
    ]


def buildvrt_argv(vrt: Path, inputs: Sequence[Path]) -> list[str]:
    return ["gdalbuildvrt", "-q", str(vrt), *map(str, inputs)]


def render_record(tiles: Sequence[str], provider: str = "copernicus-glo30") -> str:
    """The tiles both rasters were built over and the converter. A 3DEP build
    also names its provider (D-068, amended 2026-10-01), so a change of
    ``dem_source`` never reads as current; a Copernicus record is byte for
    byte what it was, so no existing install is rebuilt for it."""
    elevation = "" if provider == "copernicus-glo30" else f"elevation: {provider}\n"
    return "".join(f"{t}\n" for t in tiles) + elevation + f"converter: {CONVERTER}\n"


def _tail(text: str) -> str:
    return text.strip()[-300:]


def _refused(program: str, result: subprocess.CompletedProcess[str]) -> str:
    """A run :meth:`Staging.run` refused (125): *program* never started."""
    return f"{program} was not started: {_tail(result.stderr) or 'refused'}"


def _with(text: str, who: str) -> str:
    return f"{text} {who}" if who else text


@dataclass(frozen=True)
class GdalDemConverter:
    """Turns a ``derived`` block with ``converter: gdal-dem`` into steps."""

    prefix: Path
    resolution: DemResolution
    staging: Staging
    ledger: TerrainLedger = field(default_factory=TerrainLedger)
    runner: CommandRunner | None = None
    euid: int | None = None
    privileged: bool | None = None
    source_unit: str | None = None
    """The ``dem-tiles`` unit the tiles are read from instead of the block's
    ``source``: its ``alternative`` when the station chose that provider
    (D-068, amended 2026-10-01)."""
    provider: str = "copernicus-glo30"
    """The provider :attr:`resolution` is for; it picks the estimates and
    the record's ``elevation:`` line."""

    @property
    def writer(self) -> PrefixWriter:
        return prefix_writer(self.prefix, self.privileged, self.runner, self.euid)

    @property
    def work(self) -> Path:
        """The one working directory every phase of the build shares."""
        return self.staging.workdir(WORKDIR)

    @property
    def lock(self) -> Path:
        """The build's one lock, held by every run and every clear."""
        return self.staging.lockfile(self.work)

    def data_dir(self, manifest: PackageManifest) -> Path:
        return data_root(self.prefix) / manifest.name

    def pending(self, manifest: PackageManifest) -> list[str]:
        """Tiles whose contours are drawn this run: no contour raster, or one
        whose sidecar records another converter (or none)."""
        tiles = self.data_dir(manifest) / "contours" / "tiles"
        return [
            t
            for t in self.resolution.tiles
            if not (
                (tiles / f"{t}{TIF}").is_file()
                and installed_converter(tiles / f"{t}{TIF}") == CONVERTER
            )
        ]

    def current(self, manifest: PackageManifest) -> bool:
        """Whether both rasters exist and were built over exactly this run's tiles."""
        out = self.data_dir(manifest)
        try:
            recorded = (out / RECORD).read_text()
        except OSError:
            return False
        return (
            recorded == render_record(self.resolution.tiles, self.provider)
            and (out / "dem" / "dem.vrt").is_file()
            and (out / "contours" / "contours.vrt").is_file()
        )

    def steps(self, manifest: PackageManifest, block: DerivedDataInstall) -> list[Action | Command]:
        out = self.data_dir(manifest)
        source = data_root(self.prefix) / (self.source_unit or block.source)
        writer = self.writer
        contours = out / "contours"
        work = self.work
        steps: list[Action | Command] = []
        pending = self.pending(manifest)
        removals = removal_steps(contours / "tiles", TIF, set(self.resolution.tiles), writer)
        if not pending and not removals and self.current(manifest):
            return []
        for name in pending:
            tile = source / f"{name}{TIF}"
            gpkg = work / f"{name}.gpkg"
            staged = work / f"{name}{TIF}"
            drawn: dict[str, str] = {}
            steps.append(
                Action(
                    kind="convert",
                    description=(
                        f"Draw {INTERVAL} m contours for terrain tile {name}, as the operator, "
                        f"in {work}: {shlex.join(contour_argv(tile, gpkg))}, "
                        f"then {shlex.join(rasterize_argv(gpkg, staged, name))}; output about "
                        f"{human_size(contour_bytes(self.provider))} and up to "
                        f"{human_size(contour_scratch(self.provider))} of scratch ({MEASURED})"
                    ),
                    detail=str(staged),
                    perform=partial(self._draw, name, tile, gpkg, staged, drawn),
                )
            )
            dest = contours / "tiles" / f"{name}{TIF}"
            steps.append(
                Action(
                    kind="install-data",
                    description=(
                        f"Install the contours of terrain tile {name}, then clear its "
                        f"scratch {work} (the {gpkg.name} GeoPackage with it)"
                    ),
                    # The destination, verbatim, for uninstall's attribution replay.
                    detail=str(dest),
                    perform=partial(self._install, name, staged, dest, drawn, writer),
                    requires_root=writer.privileged,
                )
            )
        steps.extend(removals)
        steps.append(
            Action(
                kind="install-data",
                description=(
                    f"Build QMapShack's elevation ({out / 'dem' / 'dem.vrt'}, for hillshade "
                    f"and slope) and contour map ({contours / 'contours.vrt'}) over every "
                    f"installed tile, as the operator, in {work}, with gdalbuildvrt -q; "
                    f"then install both and clear {work}"
                ),
                detail=str(out / RECORD),
                perform=partial(self._rasters, source, out, writer),
                requires_root=writer.privileged,
            )
        )
        return steps

    def _clear(self, lead: str) -> str:
        """Clear the working directory under the build's lock: "" when it
        cleared, else *lead* and why not (never a silent "cleared")."""
        cleared = self.staging.clear(self.work, lock=self.lock)
        if cleared.returncode == 0:
            return ""
        return (
            f"{lead}its scratch {self.work} was not cleared: "
            f"{_tail(cleared.stderr) or 'no reason given'}"
        )

    def _begin(self) -> str | None:
        """Create and empty the working directory; why not, or None. A refused
        clear (125) deleted nothing: the directory is another run's."""
        refusal = self.staging.prepare(self.work)
        if refusal is not None:
            return refusal
        cleared = self.staging.clear(self.work, lock=self.lock)
        if cleared.returncode == REFUSED:
            return _refused("the build", cleared)
        if cleared.returncode != 0:
            return f"could not clear {self.work}: {_tail(cleared.stderr) or 'no reason given'}"
        return None

    def _draw(self, name: str, tile: Path, gpkg: Path, staged: Path, drawn: dict[str, str]) -> str:
        key = f"{KEY}:{name}"
        if tile_key(name) in self.ledger.failed:
            return f"skipped: terrain tile {name} did not install"
        if not tile.is_file():
            return self.ledger.fail(key, f"{name}: {tile} is not installed")
        # gdal_contour exits 0 onto an existing GeoPackage and appends
        # (measured): the directory is emptied first, under the lock.
        refusal = self._begin()
        if refusal is not None:
            return self.ledger.fail(key, f"{name}: {refusal}")
        work = self.work
        lines = self.staging.run(contour_argv(tile, gpkg), cwd=work, lock=self.lock)
        if lines.returncode == REFUSED:
            return self.ledger.fail(key, f"{name}: {_refused('gdal_contour', lines)}")
        if lines.returncode != 0 or self.staging.digest(gpkg) is None:
            return self.ledger.fail(
                key,
                f"{name}: gdal_contour drew no contours (exit {lines.returncode}): "
                f"{_tail(lines.stderr or lines.stdout)}{self._clear('; ')}",
            )
        raster = self.staging.run(rasterize_argv(gpkg, staged, name), cwd=work, lock=self.lock)
        if raster.returncode == REFUSED:
            return self.ledger.fail(key, f"{name}: {_refused('gdal_rasterize', raster)}")
        digest = self.staging.digest(staged)
        if raster.returncode != 0 or digest is None:
            return self.ledger.fail(
                key,
                f"{name}: gdal_rasterize wrote no contour raster (exit {raster.returncode}): "
                f"{_tail(raster.stderr or raster.stdout)}{self._clear('; ')}",
            )
        drawn["sha256"] = digest
        return f"{_with(f'drew the contours of {name}', self.staging.who())} (staged, {staged})"

    def _install(
        self, name: str, staged: Path, dest: Path, drawn: dict[str, str], writer: PrefixWriter
    ) -> str:
        if "sha256" not in drawn:
            return f"skipped: the contours of {name} were not drawn"
        key = f"{KEY}:{name}"
        failure = None
        try:
            self.staging.publish(staged, dest, digest=drawn["sha256"], writer=writer)
            writer.write_text(
                dest.with_name(dest.name + SOURCE), f"{name}\nconverter: {CONVERTER}\n"
            )
        except (BackendError, OSError) as exc:
            failure = str(exc)
        scratch = self._clear("")
        if failure is not None:
            return self.ledger.fail(key, f"{name}: {failure}{'; ' + scratch if scratch else ''}")
        if scratch:
            return self.ledger.fail(key, f"{name}: installed {dest}, but {scratch}")
        return f"installed {dest}; cleared {self.work}"

    def _rasters(self, source: Path, out: Path, writer: PrefixWriter) -> str:
        wanted = self.resolution.tiles
        tiles = [t for t in wanted if (source / f"{t}{TIF}").is_file()]
        drawn = [
            out / "contours" / "tiles" / f"{t}{TIF}"
            for t in tiles
            if (out / "contours" / "tiles" / f"{t}{TIF}").is_file()
        ]
        if not tiles:
            return "no terrain tile is installed; QMapShack gets no elevation this run"
        refusal = self._begin()
        if refusal is not None:
            return self.ledger.fail(KEY, f"QMapShack's elevation not built: {refusal}")
        work = self.work
        built: list[str] = []
        for staged, inputs, dest in (
            (work / "dem.vrt", [source / f"{t}{TIF}" for t in tiles], out / "dem" / "dem.vrt"),
            (work / "contours.vrt", drawn, out / "contours" / "contours.vrt"),
        ):
            if not inputs:
                continue
            result = self.staging.run(buildvrt_argv(staged, inputs), cwd=work, lock=self.lock)
            if result.returncode == REFUSED:
                return self.ledger.fail(
                    KEY, f"{dest.name} not built: {_refused('gdalbuildvrt', result)}"
                )
            digest = self.staging.digest(staged)
            if result.returncode != 0 or digest is None:
                return self.ledger.fail(
                    KEY,
                    f"gdalbuildvrt did not build {dest.name} (exit {result.returncode}): "
                    f"{_tail(result.stderr or result.stdout)}{self._clear('; ')}",
                )
            try:
                self.staging.publish(staged, dest, digest=digest, writer=writer)
            except (BackendError, OSError) as exc:
                return self.ledger.fail(KEY, f"{dest}: {exc}{self._clear('; ')}")
            built.append(f"{dest} ({len(inputs)} tile(s))")
        scratch = self._clear("")
        # Recorded only when every tile made it into both: a missing one is
        # built next run.
        if len(tiles) == len(wanted) == len(drawn):
            writer.write_text(out / RECORD, render_record(wanted, self.provider))
        done = _with("built " + " and ".join(built), self.staging.who())
        if scratch:
            return self.ledger.fail(KEY, f"{done}, but {scratch}")
        return f"{done}; cleared {work}"
