# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The ``splat-sdf`` converter: SPLAT's terrain from the installed elevation
tiles, for SPLAT! and Signal-Server.  D-061, amended 2026-10-02.

SPLAT reads SPLAT Data Files, one per one-degree square: 1200 samples a side
for ``splat`` (``<lat>:<lat+1>:<west>:<west+1>.sdf``) and 3600 for
``splat-hd`` (``...-hd.sdf``), longitudes counted west and positive, plain or
bzip2-compressed. Signal-Server reads the same files under its own names
(``<lat>_<lat+1>_<west>_<west+1>``). Every name and the format were measured
on 2026-10-01 from Debian's ``srtm2sdf``/``srtm2sdf-hd`` (splat 1.4.2-3) and
Signal-Server's ``LoadSDF`` (W3AXL, 7f6242a).

Per tile, as the operator, in the build's one working directory
``<staging>/splat.work/`` under one lock (the ``gdal-dem`` shape):

1. ``gdalbuildvrt -resolution highest`` over the tile and the installed tiles
   of the one-degree ring around it: a Copernicus tile's south row and east
   column belong to its neighbours.
2. ``gdalwarp -r average -dstnodata -32768`` of the tile's degree into a
   one-arc-second SRTM ``.hgt``, 3601 x 3601 samples centred on whole arc
   seconds; a sample no installed tile covers is -32768, a void.
3. ``srtm2sdf-hd -d /dev/null -n -32767``, then ``bzip2 -9``. By default the
   tool replaces every elevation below zero with its neighbours' average
   (measured: a -50 m block came out at 104 m), and ``-d /dev/null`` is its
   manual's "prevents data replacement" -- it would otherwise read the
   operator's ``~/.splat_path``, which names this converter's own output.
   With ``-n -32767`` only the void value is averaged.
4. The same at three arc seconds, 1201 x 1201, with ``srtm2sdf``.
5. Both ``.sdf.bz2`` files published under ``<data>/<unit>/``, each with a
   ``.source`` sidecar naming the tile, the ring it was built with and
   :data:`CONVERTER`, and a symbolic link beside each under Signal-Server's
   name.

Outputs are checked, never exit statuses (D-031). A file is current when its
sidecar is what this run would write: a change of elevation source names
another tile for the same square, and a neighbour gained or lost changes the
ring, so either rebuilds it. A square no region needs any more loses its
files, sidecars and links.
"""

from __future__ import annotations

import shlex
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path

from ..manifest.schema import DerivedDataInstall, PackageManifest
from ..usgs3dep import dem_square
from .base import Action, BackendError, Command, CommandRunner
from .data import human_size
from .dem import TIF, DemResolution
from .regions import SOURCE, data_root, prefix_writer
from .staging import REFUSED, Staging
from .terrain import SDF_BYTES, SDF_MEASURED, SDF_SCRATCH_BYTES, TerrainLedger, tile_key
from .verified import PrefixWriter

#: What the files were made by: the last line of each sidecar. Bumped whenever
#: an argv changes the output, so every file an older one made is made again.
CONVERTER = "splat-sdf 1"
#: The build's one working directory under the staging directory, and its lock.
WORKDIR = "splat"
#: The ledger key of a tile's conversion is ``splat-sdf:<tile>``.
KEY = "splat-sdf"
#: Samples a side of the ``.hgt`` each tool reads: one and three arc seconds.
HD_SAMPLES = 3601
SD_SAMPLES = 1201
SDF = ".sdf"
BZ2 = ".bz2"
#: The void value: what gdalwarp writes where no tile covers a sample, and the
#: only value ``srtm2sdf -n -32767`` replaces.
VOID = -32768


def _west(lon: int) -> tuple[int, int]:
    """SPLAT's west-positive bounds of the square whose west edge is *lon*
    (east-positive): (``min_west``, ``max_west``), as ``srtm2sdf`` writes them
    -- ``max_west`` wraps to 0 for the square east of Greenwich (measured)."""
    return (-(lon + 1)) % 360, (-lon) % 360


def sdf_name(tile: str, *, hd: bool) -> str:
    """The compressed file SPLAT reads for *tile*'s square, as ``srtm2sdf``
    and ``srtm2sdf-hd`` name it (measured on nine squares in four
    hemispheres, 2026-10-01): ``36:37:116:117-hd.sdf.bz2`` for N36W117."""
    lat, lon = dem_square(tile)
    low, high = _west(lon)
    return f"{lat}:{lat + 1}:{low}:{high}{'-hd' if hd else ''}{SDF}{BZ2}"


def signal_server_name(tile: str, *, hd: bool) -> str:
    """The same square as Signal-Server's ``LoadTopoData`` asks for it:
    underscores, and the upper west bound ``min_west + 1`` with no wrap, so
    the square east of Greenwich is ``0_1_359_360`` where SPLAT's is
    ``0:1:359:0``. Read from its source; not run on that square."""
    lat, lon = dem_square(tile)
    low, _ = _west(lon)
    return f"{lat}_{lat + 1}_{low}_{low + 1}{'-hd' if hd else ''}{SDF}{BZ2}"


def hgt_name(tile: str) -> str:
    """The SRTM name the tools insist on (``N36W117.hgt``): they name their
    output from it."""
    lat, lon = dem_square(tile)
    ns, ew = ("N" if lat >= 0 else "S"), ("E" if lon >= 0 else "W")
    return f"{ns}{abs(lat):02d}{ew}{abs(lon):03d}.hgt"


def ring(tile: str, tiles: Sequence[str]) -> tuple[str, ...]:
    """The tiles of *tiles* in the eight squares around *tile*'s, sorted."""
    lat, lon = dem_square(tile)
    return tuple(
        sorted(
            t
            for t in tiles
            if t != tile and abs(dem_square(t)[0] - lat) <= 1 and abs(dem_square(t)[1] - lon) <= 1
        )
    )


def _deg(value: float) -> str:
    return f"{value:.9f}"


def window_argv(vrt: Path, inputs: Sequence[Path]) -> list[str]:
    return ["gdalbuildvrt", "-q", "-resolution", "highest", str(vrt), *map(str, inputs)]


def warp_argv(vrt: Path, hgt: Path, tile: str, samples: int) -> list[str]:
    """*tile*'s degree out of the window, as an SRTM ``.hgt`` of *samples* a
    side centred on whole multiples of its spacing: half a sample beyond each
    edge."""
    lat, lon = dem_square(tile)
    half = 1 / (2 * (samples - 1))
    return [
        "gdalwarp",
        "-q",
        "--config",
        "GDAL_PAM_ENABLED",
        "NO",
        "-r",
        "average",
        "-dstnodata",
        str(VOID),
        "-te",
        _deg(lon - half),
        _deg(lat - half),
        _deg(lon + 1 + half),
        _deg(lat + 1 + half),
        "-ts",
        str(samples),
        str(samples),
        "-ot",
        "Int16",
        "-of",
        "SRTMHGT",
        str(vrt),
        str(hgt),
    ]


def convert_argv(hgt: str, *, hd: bool) -> list[str]:
    """SPLAT's own converter over *hgt*, a bare name in the working directory,
    with nothing replaced but voids."""
    return ["srtm2sdf-hd" if hd else "srtm2sdf", "-d", "/dev/null", "-n", str(VOID + 1), hgt]


def compress_argv(sdf: str) -> list[str]:
    return ["bzip2", "-9", "--", sdf]


def render_sidecar(tile: str, neighbours: Sequence[str]) -> str:
    return f"{tile}\nwindow: {' '.join(neighbours)}\nconverter: {CONVERTER}\n"


def _tail(text: str) -> str:
    return text.strip()[-300:]


def _refused(program: str, result: subprocess.CompletedProcess[str]) -> str:
    """A run :meth:`Staging.run` refused (125): *program* never started."""
    return f"{program} was not started: {_tail(result.stderr) or 'refused'}"


def _with(text: str, who: str) -> str:
    return f"{text} {who}" if who else text


@dataclass(frozen=True)
class SplatSdfConverter:
    """Turns a ``derived`` block with ``converter: splat-sdf`` into steps."""

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
    (D-068, amended 2026-10-01), exactly as ``gdal-dem`` reads it."""

    @property
    def writer(self) -> PrefixWriter:
        return prefix_writer(self.prefix, self.privileged, self.runner, self.euid)

    @property
    def work(self) -> Path:
        return self.staging.workdir(WORKDIR)

    @property
    def lock(self) -> Path:
        return self.staging.lockfile(self.work)

    def data_dir(self, manifest: PackageManifest) -> Path:
        return data_root(self.prefix) / manifest.name

    def _expected(self, tile: str) -> str:
        return render_sidecar(tile, ring(tile, self.resolution.tiles))

    def pending(self, manifest: PackageManifest) -> list[str]:
        """Tiles whose files are made this run: either file missing, or a
        sidecar naming another tile, ring or converter."""
        out = self.data_dir(manifest)
        todo: list[str] = []
        for tile in self.resolution.tiles:
            expected = self._expected(tile)
            for hd in (True, False):
                path = out / sdf_name(tile, hd=hd)
                try:
                    recorded = path.with_name(path.name + SOURCE).read_text()
                except OSError:
                    recorded = ""
                if not path.is_file() or path.is_symlink() or recorded != expected:
                    todo.append(tile)
                    break
        return todo

    def _wanted_names(self) -> set[str]:
        return {
            name(tile, hd=hd)
            for tile in self.resolution.tiles
            for hd in (True, False)
            for name in (sdf_name, signal_server_name)
        }

    def stale(self, manifest: PackageManifest) -> list[Path]:
        """Files and links for squares no region needs any more."""
        out = self.data_dir(manifest)
        if not out.is_dir():
            return []
        wanted = self._wanted_names()
        return sorted(
            path
            for path in out.glob(f"*{SDF}{BZ2}")
            if path.name not in wanted and (path.is_file() or path.is_symlink())
        )

    def current(self, manifest: PackageManifest) -> bool:
        return not self.pending(manifest) and not self.stale(manifest)

    def steps(self, manifest: PackageManifest, block: DerivedDataInstall) -> list[Action | Command]:
        out = self.data_dir(manifest)
        source = data_root(self.prefix) / (self.source_unit or block.source)
        writer = self.writer
        steps: list[Action | Command] = []
        for tile in self.pending(manifest):
            staged: dict[str, str] = {}
            work = self.work
            hgt = hgt_name(tile)
            steps.append(
                Action(
                    kind="convert",
                    description=(
                        f"Make SPLAT's terrain for tile {tile}, as the operator, in {work}: "
                        f"{shlex.join(window_argv(work / 'window.vrt', [source / f'{tile}{TIF}']))}"
                        f" (with the installed tiles around it), "
                        f"{shlex.join(warp_argv(work / 'window.vrt', work / hgt, tile, HD_SAMPLES))}, "
                        f"{shlex.join(convert_argv(hgt, hd=True))} and bzip2 -9, then the same at "
                        f"{SD_SAMPLES} samples with srtm2sdf; output about "
                        f"{human_size(SDF_BYTES)} and up to {human_size(SDF_SCRATCH_BYTES)} "
                        f"of scratch ({SDF_MEASURED})"
                    ),
                    detail=str(work / sdf_name(tile, hd=True)),
                    perform=partial(self._convert, tile, source, staged),
                )
            )
            for hd in (True, False):
                dest = out / sdf_name(tile, hd=hd)
                steps.append(
                    Action(
                        kind="install-data",
                        description=(
                            f"Install {dest.name} for SPLAT{'-HD' if hd else ''}, with a link "
                            f"{signal_server_name(tile, hd=hd)} for Signal-Server"
                            + (f", then clear {work}" if not hd else "")
                        ),
                        # The destination, verbatim, for uninstall's attribution replay.
                        detail=str(dest),
                        perform=partial(self._install, tile, hd, dest, staged, writer),
                        requires_root=writer.privileged,
                    )
                )
        for path in self.stale(manifest):
            steps.append(
                Action(
                    kind="remove-data",
                    description=f"Remove {path.name}: no longer in your map regions",
                    detail=str(path),
                    perform=partial(self._remove, path, writer),
                    requires_root=writer.privileged,
                )
            )
        return steps

    # -- running ------------------------------------------------------------

    def _clear(self, lead: str) -> str:
        cleared = self.staging.clear(self.work, lock=self.lock)
        if cleared.returncode == 0:
            return ""
        return (
            f"{lead}its scratch {self.work} was not cleared: "
            f"{_tail(cleared.stderr) or 'no reason given'}"
        )

    def _begin(self) -> str | None:
        refusal = self.staging.prepare(self.work)
        if refusal is not None:
            return refusal
        cleared = self.staging.clear(self.work, lock=self.lock)
        if cleared.returncode == REFUSED:
            return _refused("the build", cleared)
        if cleared.returncode != 0:
            return f"could not clear {self.work}: {_tail(cleared.stderr) or 'no reason given'}"
        return None

    def _step(self, argv: list[str], program: str, output: Path, tile: str) -> str | None:
        """Run *argv*; why it did not leave *output*, or None (D-031)."""
        result = self.staging.run(argv, cwd=self.work, lock=self.lock)
        if result.returncode == REFUSED:
            return f"{tile}: {_refused(program, result)}"
        if result.returncode != 0 or self.staging.digest(output) is None:
            return (
                f"{tile}: {program} did not write {output.name} (exit {result.returncode}): "
                f"{_tail(result.stderr or result.stdout)}"
            )
        return None

    def _discard(self, name: str, tile: str) -> str | None:
        """Remove the ``.hgt`` once converted: the next resolution's warp
        writes the same name, and gdalwarp refuses an existing output
        (measured), as it should."""
        result = self.staging.run(["rm", "-f", "--", name], cwd=self.work, lock=self.lock)
        # Checked as the operator, like every other look into staging.
        if result.returncode != 0 or self.staging.digest(self.work / name) is not None:
            return f"{tile}: {name} could not be removed: {_tail(result.stderr) or 'still there'}"
        return None

    def _convert(self, tile: str, source: Path, staged: dict[str, str]) -> str:
        key = f"{KEY}:{tile}"
        if tile_key(tile) in self.ledger.failed:
            return f"skipped: terrain tile {tile} did not install"
        own = source / f"{tile}{TIF}"
        if not own.is_file():
            return self.ledger.fail(key, f"{tile}: {own} is not installed")
        refusal = self._begin()
        if refusal is not None:
            return self.ledger.fail(key, f"{tile}: {refusal}")
        work = self.work
        neighbours = [
            t for t in ring(tile, self.resolution.tiles) if (source / f"{t}{TIF}").is_file()
        ]
        vrt = work / "window.vrt"
        hgt = hgt_name(tile)
        why = self._step(
            window_argv(vrt, [own, *(source / f"{t}{TIF}" for t in neighbours)]),
            "gdalbuildvrt",
            vrt,
            tile,
        )
        for hd, samples in ((True, HD_SAMPLES), (False, SD_SAMPLES)):
            if why is not None:
                break
            text = sdf_name(tile, hd=hd).removesuffix(BZ2)
            why = (
                self._step(warp_argv(vrt, work / hgt, tile, samples), "gdalwarp", work / hgt, tile)
                or self._step(
                    convert_argv(hgt, hd=hd),
                    "srtm2sdf-hd" if hd else "srtm2sdf",
                    work / text,
                    tile,
                )
                or self._step(compress_argv(text), "bzip2", work / f"{text}{BZ2}", tile)
                or self._discard(hgt, tile)
            )
            if why is None:
                digest = self.staging.digest(work / f"{text}{BZ2}")
                if digest is None:  # pragma: no cover - _step checked it
                    why = f"{tile}: {text}{BZ2} vanished"
                else:
                    staged["hd" if hd else "sd"] = digest
        if why is not None:
            staged.clear()
            return self.ledger.fail(key, f"{why}{self._clear('; ')}")
        staged["sidecar"] = render_sidecar(tile, neighbours)
        return f"{_with(f'made the SPLAT terrain of {tile}', self.staging.who())} (staged, {work})"

    def _install(
        self, tile: str, hd: bool, dest: Path, staged: dict[str, str], writer: PrefixWriter
    ) -> str:
        part = "hd" if hd else "sd"
        if part not in staged:
            return f"skipped: the SPLAT terrain of {tile} was not made"
        key = f"{KEY}:{tile}"
        link = dest.with_name(signal_server_name(tile, hd=hd))
        failure = None
        try:
            self.staging.publish(self.work / dest.name, dest, digest=staged[part], writer=writer)
            writer.write_text(dest.with_name(dest.name + SOURCE), staged["sidecar"])
            if link != dest:
                writer.link(link, dest.name)
        except (BackendError, OSError) as exc:
            failure = str(exc)
        # The scratch goes once both files are in (the standard one is last).
        scratch = "" if hd else self._clear("")
        if failure is not None:
            return self.ledger.fail(key, f"{tile}: {failure}{'; ' + scratch if scratch else ''}")
        if scratch:
            return self.ledger.fail(key, f"{tile}: installed {dest}, but {scratch}")
        cleared = "" if hd else f"; cleared {self.work}"
        return f"installed {dest} and {link.name}{cleared}"

    @staticmethod
    def _remove(path: Path, writer: PrefixWriter) -> str:
        writer.remove([path, path.with_name(path.name + SOURCE)])
        return f"removed {path}"
