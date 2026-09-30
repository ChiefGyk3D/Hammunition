# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The ``brouter-mapcreator`` converter: BRouter's routing files from every
region, with Copernicus elevation folded in.  D-063.

BRouter routes over ``.rd5`` files, one per 5-degree square, named by the
square's south-west corner (``W80_N35.rd5``). brouter.de publishes a set
rebuilt weekly with no checksum of any kind, which is why D-061 left BRouter
out; they are never downloaded here. The files are built on the machine
from the regions Hammunition already fetched and verified (``osm-regions``,
D-057) and the elevation tiles it already fetched and verified
(``dem-copernicus``, D-061), with the map creator in BRouter's own pinned
jar, following upstream's ``misc/scripts/mapcreation/process_pbf_planet.sh``
less its database pseudo-tags.

One build over every region, never one per region: two regions in one
square would each write that square's file, and one routing file per square
must hold every region in it. The Routino converter's shape (D-061), in one
working directory under the staging directory, ``brouter.work``, held under
one lock, ``brouter.work.lock``, by every phase and every clear:

1. ``osmium merge`` the regions into one input when there are two or more;
   ``OsmFastCutter`` reads one file.
2. Per 5-degree square that holds an installed tile, when the block names an
   ``elevation`` unit: ``gdalbuildvrt`` over the installed tiles in the
   square and the one-degree ring around it, ``gdalwarp`` of each of the
   square's tiles out of that mosaic into a one-arc-second SRTM ``.hgt``
   (sampling a mosaic, not a lone tile, gives each ``.hgt`` its edge rows
   from the neighbour), then ``ElevationRasterTileConverter`` into the
   square's ``.bef``; the ``.hgt`` files are removed before the next square.
3. ``OsmFastCutter``, with ``-DavoidMapPolling=true``: without it the parser
   sleeps 10 s at a time waiting for its input to grow, 120 s in all for a
   file under 100 MB (upstream runs ``osmupdate`` beside it; measured
   2026-09-29 on a synthetic region, 120.1 s without and 0.1 s with).
4. ``PosUnifier`` over the ``.bef`` directory, which is empty when there is
   no elevation, and the routes are then flat.
5. ``WayLinker`` into ``segments/*.rd5``.
6. Every ``.rd5`` published under a temporary name, then all renamed into
   ``<data>/<unit>/``, files no longer built removed, and the record written;
   all or none, as the Routino database is.

Every argv was run on 2026-09-29 against the pinned jar on two synthetic
regions and a synthetic tile, and BRouter routed across both with the
tile's elevation. Outputs are checked, not exit statuses (D-031).

``<data>/<unit>/segments.source`` records the regions and snapshots, each
tile folded in, the jar, each routing file installed and, last,
:data:`CONVERTER`. The build is current when that record, less its
``segment`` lines, is what this run would write and every segment named in
it exists. The tiles recorded are the ones on disk when the build ran, so a
tile that failed to download is built in by the next run.
"""

from __future__ import annotations

import shlex
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path

from ..copernicus import square_of
from ..geofabrik import RegionFile
from ..manifest.schema import DerivedDataInstall, PackageManifest
from .base import Action, BackendError, Command, CommandRunner
from .data import human_size
from .dem import TIF, DemResolution
from .regions import PBF, MapLedger, data_root, installed_snapshot, prefix_writer
from .routino import _rename
from .source import tree_destination
from .staging import REFUSED, Staging
from .terrain import (
    BROUTER_FACTOR,
    BROUTER_SCRATCH_FACTOR,
    ELEVATION_SCRATCH_BYTES,
    MEASURED,
    TerrainLedger,
)
from .verified import PrefixWriter

#: What the routing files were built by: the record's last line. Bumped
#: whenever an argv changes the output, so every file an older one built is
#: built again.
CONVERTER = "brouter-mapcreator 1"
RECORD = "segments.source"
RD5 = ".rd5"
#: The suffix a routing file is published under before the set is renamed in.
NEW = ".new"
WORKDIR = "brouter"
#: BRouter's jar, as its release zip names it: the router and the map creator.
JAR_GLOB = "brouter-*-all.jar"
#: One heap for every Java phase. Measured on Delaware: the elevation
#: converter peaked at 1.33 GB, the cutter at 593 MB; larger regions are not
#: measured, and the JVM takes only what it uses.
HEAP = "-Xmx4000m"
MERGED = "merged.osm.pbf"
#: The map creator's filters from the ``profiles`` unit, and what it reads
#: from BRouter's own ``profiles2``.
ALL_BRF, SOFTACCESS_BRF = "all.brf", "softaccess.brf"
LOOKUPS, TREKKING_BRF = "lookups.dat", "trekking.brf"
#: One arc second, and half of one: the ``.hgt`` grid's pixel centres sit on
#: whole arc seconds, so its edges are half a second outside the degree.
ARCSEC = 1 / 3600
#: What each map-creator phase must leave behind: (directory under the
#: working directory, pattern).
EFFECT = {
    "OsmFastCutter": ("nodes55", "*.n5d"),
    "PosUnifier": ("unodes55", "*.u5d*"),
    "WayLinker": ("segments", f"*{RD5}"),
}
#: How the operator's ``find`` marks each file it lists.
_FOUND = "found:"
SRTM1 = 3601


def square_of_tile(name: str) -> tuple[int, int]:
    """(latitude, longitude) of the south-west corner of the 5-degree square
    holding the Copernicus tile *name*."""
    lat, lon = square_of(name)
    return (lat // 5 * 5, lon // 5 * 5)


def srtm_name(lat0: int, lon0: int) -> str:
    """The map creator's name for the square at (*lat0*, *lon0*):
    ``PosUnifier.genFilenameXY``, whose last two characters of ``"0" + index``
    give ``-1`` north of 65°, which ``ElevationRasterTileConverter`` parses
    back to the same square."""
    lon_index = (lon0 + 180) // 5 + 1
    lat_index = (60 - lat0) // 5
    return f"srtm_{f'0{lon_index}'[-2:]}_{f'0{lat_index}'[-2:]}"


def hgt_name(tile: str) -> str:
    """The SRTM file name the converter looks for, for one tile's square."""
    lat, lon = square_of(tile)
    ns, ew = ("N" if lat >= 0 else "S"), ("E" if lon >= 0 else "W")
    return f"{ns}{abs(lat):02d}{ew}{abs(lon):03d}.hgt"


def window_tiles(square: tuple[int, int], tiles: Sequence[str]) -> tuple[str, ...]:
    """The tiles in *square* and the one-degree ring around it."""
    lat0, lon0 = square
    return tuple(
        t
        for t in sorted(tiles)
        if lat0 - 1 <= square_of(t)[0] <= lat0 + 5 and lon0 - 1 <= square_of(t)[1] <= lon0 + 5
    )


def in_square(square: tuple[int, int], tiles: Sequence[str]) -> tuple[str, ...]:
    return tuple(t for t in sorted(tiles) if square_of_tile(t) == square)


def _deg(value: float) -> str:
    return f"{value:.9f}"


def warp_argv(vrt: Path, hgt: Path, tile: str) -> list[str]:
    """One tile's degree out of the window's mosaic, as a one-arc-second
    ``.hgt``: 3601 x 3601 pixels centred on whole arc seconds."""
    lat, lon = square_of(tile)
    half = ARCSEC / 2
    return [
        "gdalwarp",
        "-q",
        "--config",
        "GDAL_PAM_ENABLED",
        "NO",
        "-te",
        _deg(lon - half),
        _deg(lat - half),
        _deg(lon + 1 + half),
        _deg(lat + 1 + half),
        "-ts",
        str(SRTM1),
        str(SRTM1),
        "-ot",
        "Int16",
        "-of",
        "SRTMHGT",
        str(vrt),
        str(hgt),
    ]


def _java(jar: Path, cls: str, *args: object, props: Sequence[str] = ()) -> list[str]:
    return ["java", HEAP, *props, "-cp", str(jar), f"btools.mapcreator.{cls}", *map(str, args)]


def find_jar(tree: Path) -> Path | None:
    """The one ``brouter-*-all.jar`` in BRouter's tree, or None (none, or several)."""
    found = sorted(tree.glob(JAR_GLOB))
    return found[0] if len(found) == 1 else None


def render_record(
    regions: Sequence[str], tiles: Sequence[str], jar: str | None, segments: Sequence[str]
) -> str:
    """The record: region lines, each tile folded in, the jar, each segment
    installed, then :data:`CONVERTER`."""
    lines = [
        *regions,
        *(f"elevation {t}" for t in tiles),
        f"program {jar or '-'}",
        *(f"segment {s}" for s in sorted(segments)),
        f"converter: {CONVERTER}",
    ]
    return "".join(f"{line}\n" for line in lines)


def _without_segments(record: str) -> str:
    return "".join(
        line for line in record.splitlines(keepends=True) if not line.startswith("segment ")
    )


def _segments_of(record: str) -> list[str]:
    return [line.split(" ", 1)[1] for line in record.splitlines() if line.startswith("segment ")]


def _tail(text: str) -> str:
    return text.strip()[-300:]


@dataclass(frozen=True)
class Source:
    """One region the routing files are built from."""

    region: str
    slug: str
    snapshot: str | None
    pbf: Path
    size: int

    @property
    def line(self) -> str:
        return f"{self.slug} {self.snapshot or '-'}"


@dataclass(frozen=True)
class BRouterConverter:
    """Turns a ``derived`` block with ``converter: brouter-mapcreator`` into steps."""

    prefix: Path
    files: Sequence[RegionFile]
    resolution: DemResolution
    staging: Staging
    keep: frozenset[str] = frozenset()
    """Slugs kept as installed because a newer map could not be checked for."""
    regions: MapLedger = field(default_factory=MapLedger)
    ledger: TerrainLedger = field(default_factory=TerrainLedger)
    runner: CommandRunner | None = None
    euid: int | None = None
    privileged: bool | None = None

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

    def sources(self, block: DerivedDataInstall) -> list[Source]:
        """Every region the routing files cover: this run's, then the kept ones."""
        source_dir = data_root(self.prefix) / block.source
        out = [
            Source(f.region, f.slug, f.snapshot, source_dir / f"{f.slug}{PBF}", f.size)
            for f in self.files
        ]
        for slug in sorted(self.keep - {f.slug for f in self.files}):
            pbf = source_dir / f"{slug}{PBF}"
            size = pbf.stat().st_size if pbf.is_file() else 0
            out.append(Source(slug, slug, installed_snapshot(pbf), pbf, size))
        return out

    def wanted_tiles(self, block: DerivedDataInstall) -> tuple[str, ...]:
        """Every tile the regions need, when the block folds in elevation."""
        return self.resolution.tiles if block.elevation is not None else ()

    def squares(self, block: DerivedDataInstall) -> list[tuple[int, int]]:
        return sorted({square_of_tile(t) for t in self.wanted_tiles(block)})

    def _tree(self, block: DerivedDataInstall) -> Path:
        assert block.program is not None  # the schema requires it
        return tree_destination(self.prefix, block.program)

    def pending(self, manifest: PackageManifest, block: DerivedDataInstall) -> list[Source]:
        """The regions the routing files are rebuilt over this run, or none
        when they are current."""
        sources = self.sources(block)
        out = self.data_dir(manifest)
        try:
            recorded = (out / RECORD).read_text()
        except OSError:
            recorded = None
        jar = find_jar(self._tree(block))
        if sources and recorded is not None and jar is not None:
            expected = render_record(
                sorted(s.line for s in sources), self.wanted_tiles(block), jar.name, ()
            )
            segments = _segments_of(recorded)
            if (
                _without_segments(recorded) == expected
                and segments
                and all((out / name).is_file() for name in segments)
            ):
                return []
        return sources

    # -- steps -------------------------------------------------------------

    def steps(self, manifest: PackageManifest, block: DerivedDataInstall) -> list[Action | Command]:
        sources = self.pending(manifest, block)
        if not sources:
            return []
        out = self.data_dir(manifest)
        work = self.work
        key = manifest.name
        writer = self.writer
        total = sum(s.size for s in sources)
        state: dict[str, str] = {}
        tree = self._tree(block)
        profiles = data_root(self.prefix) / (block.profiles or "")
        steps: list[Action | Command] = [
            Action(
                kind="convert",
                description=(
                    f"Prepare BRouter's routing build over {len(sources)} region(s), as the "
                    f"operator, in {work}: check its jar ({tree / JAR_GLOB}) and the map "
                    f"creator's filters ({profiles / ALL_BRF}, {profiles / SOFTACCESS_BRF}), "
                    f"then empty the working directory. The routing files are built here "
                    f"from your own regions and never downloaded from brouter.de, which "
                    f"publishes no checksum"
                ),
                detail=str(work),
                perform=partial(self._begin, sources, block, key, state),
            )
        ]
        if len(sources) > 1:
            argv = self._merge_argv(sources)
            steps.append(
                Action(
                    kind="convert",
                    description=(
                        f"Merge the {len(sources)} regions into one input for BRouter's map "
                        f"creator, as the operator, in {work}: {shlex.join(argv)}"
                    ),
                    detail=str(work / MERGED),
                    perform=partial(self._merge, argv, key, state),
                )
            )
        if block.elevation is not None:
            tiles_dir = data_root(self.prefix) / block.elevation
            for square in self.squares(block):
                name = srtm_name(*square)
                own = in_square(square, self.wanted_tiles(block))
                steps.append(
                    Action(
                        kind="convert",
                        description=(
                            f"Build BRouter's elevation for square {name} from {len(own)} "
                            f"terrain tile(s), as the operator, in {work}: gdalbuildvrt over "
                            f"the installed tiles in the square and the degree around it, "
                            f"gdalwarp of each into a one-arc-second .hgt, then "
                            f"ElevationRasterTileConverter {name}; up to "
                            f"{human_size(ELEVATION_SCRATCH_BYTES)} of scratch while it runs"
                        ),
                        detail=str(work / "bef" / f"{name}.bef"),
                        perform=partial(self._elevation, square, tiles_dir, block, key, state),
                    )
                )
        for phase, text in (
            ("OsmFastCutter", "cut the ways and nodes into tiles"),
            ("PosUnifier", "place every node and fold in its elevation"),
            ("WayLinker", "link the ways into the routing files"),
        ):
            steps.append(
                Action(
                    kind="convert",
                    description=(
                        f"BRouter's map creator, {phase}: {text}, as the operator, in {work}"
                        + (
                            f"; the routing files about {human_size(round(total * BROUTER_FACTOR))} "
                            f"({BROUTER_FACTOR}x the downloads together, {MEASURED}), with up "
                            f"to {human_size(BROUTER_SCRATCH_FACTOR * total)} of scratch "
                            f"(not measured, an allowance)"
                            if phase == "WayLinker"
                            else ""
                        )
                    ),
                    detail=str(work),
                    perform=partial(self._phase, phase, sources, block, key, state),
                )
            )
        steps.append(
            Action(
                kind="install-data",
                description=(
                    f"Install BRouter's routing files (*.rd5) and their record under {out}, "
                    f"remove any no longer built, then clear the scratch {work}"
                ),
                detail=str(out / RECORD),
                perform=partial(self._install, sources, out, key, state, writer),
                requires_root=writer.privileged,
            )
        )
        return steps

    # -- the phases ----------------------------------------------------------

    def _fail(self, key: str, state: dict[str, str], why: str) -> str:
        state["failed"] = why
        scratch = self._scratch("; ")
        return self.ledger.fail(key, f"BRouter routing files not built: {why}{scratch}")

    def _scratch(self, lead: str) -> str:
        """Clear the working directory under the build's lock: "" when it
        cleared, else *lead* and why not (never a silent "cleared")."""
        cleared = self.staging.clear(self.work, lock=self.lock)
        if cleared.returncode == 0:
            return ""
        return (
            f"{lead}its scratch {self.work} was not cleared: "
            f"{_tail(cleared.stderr) or 'no reason given'}"
        )

    def _run(self, argv: Sequence[str]) -> subprocess.CompletedProcess[str]:
        return self.staging.run(argv, cwd=self.work, lock=self.lock)

    def _listing(self, directory: Path, pattern: str) -> list[str] | None:
        """Non-empty regular files in *directory* matching *pattern*, listed by
        the operator's own ``find``; None when the listing itself failed."""
        found = self._run(
            [
                "find",
                str(directory),
                "-maxdepth",
                "1",
                "-type",
                "f",
                "-name",
                pattern,
                "-size",
                "+0",
                "-printf",
                f"{_FOUND}%f\\n",
            ]
        )
        if found.returncode != 0:
            return None
        # flock --verbose shares stdout; only find's own marked lines count.
        return sorted(
            line[len(_FOUND) :]
            for line in found.stdout.splitlines()
            if line.startswith(_FOUND) and len(line) > len(_FOUND)
        )

    def _jar(self, block: DerivedDataInstall) -> Path | None:
        return find_jar(self._tree(block))

    def _begin(
        self, sources: Sequence[Source], block: DerivedDataInstall, key: str, state: dict[str, str]
    ) -> str:
        for source in sources:
            if source.slug in self.regions.failed:
                # The regions ledger reports the region; nothing here ran.
                state["failed"] = (
                    f"{source.region} did not install, and the routing files are built "
                    f"over every region or none; the installed ones are left as they were"
                )
                return f"skipped: {state['failed']}"
        missing: list[str] = []
        tree = self._tree(block)
        jar = self._jar(block)
        if jar is None:
            missing.append(f"exactly one {JAR_GLOB} in {tree}")
        for path in (tree / "profiles2" / LOOKUPS, tree / "profiles2" / TREKKING_BRF):
            if not path.is_file():
                missing.append(str(path))
        profiles = data_root(self.prefix) / (block.profiles or "")
        for name in (ALL_BRF, SOFTACCESS_BRF):
            if not (profiles / name).is_file():
                missing.append(str(profiles / name))
        missing.extend(f"{s.region}: {s.pbf}" for s in sources if not s.pbf.is_file())
        if missing:
            state["failed"] = "not installed: " + "; ".join(missing)
            return self.ledger.fail(key, f"BRouter routing files not built: {state['failed']}")
        work = self.work
        refusal = self.staging.prepare(work)
        if refusal is not None:
            state["failed"] = refusal
            return self.ledger.fail(key, f"BRouter routing files not built: {refusal}")
        cleared = self.staging.clear(work, lock=self.lock)
        if cleared.returncode != 0:
            # 125: another conversion holds the directory; nothing in it is deleted.
            state["failed"] = (
                f"the build was not started: {_tail(cleared.stderr) or 'refused'}"
                if cleared.returncode == REFUSED
                else f"could not clear {work}: {_tail(cleared.stderr) or 'no reason given'}"
            )
            return self.ledger.fail(key, f"BRouter routing files not built: {state['failed']}")
        subdirectories = [
            work / name
            for name in (
                "nodetiles",
                "waytiles",
                "nodes55",
                "waytiles55",
                "unodes55",
                "segments",
                "hgt",
                "bef",
            )
        ]
        refusal = self.staging.prepare(work, *subdirectories)
        if refusal is not None:
            return self._fail(key, state, refusal)
        assert jar is not None
        state["jar"] = str(jar)
        state["input"] = str(sources[0].pbf)
        return f"prepared {work} for BRouter's build{_who(self.staging.who())}"

    def _merge_argv(self, sources: Sequence[Source]) -> list[str]:
        return [
            "osmium",
            "merge",
            *(str(s.pbf) for s in sources),
            "-o",
            str(self.work / MERGED),
            "--overwrite",
        ]

    def _merge(self, argv: list[str], key: str, state: dict[str, str]) -> str:
        if "failed" in state:
            return f"skipped: {state['failed']}"
        result = self._run(argv)
        if result.returncode != 0 or self.staging.digest(self.work / MERGED) is None:
            return self._fail(
                key,
                state,
                f"osmium could not merge the regions (exit {result.returncode}): "
                f"{_tail(result.stderr or result.stdout)}",
            )
        state["input"] = str(self.work / MERGED)
        return f"merged the regions into {self.work / MERGED}{_who(self.staging.who())}"

    def _elevation(
        self,
        square: tuple[int, int],
        tiles_dir: Path,
        block: DerivedDataInstall,
        key: str,
        state: dict[str, str],
    ) -> str:
        if "failed" in state:
            return f"skipped: {state['failed']}"
        name = srtm_name(*square)
        on_disk = [t for t in self.wanted_tiles(block) if (tiles_dir / f"{t}{TIF}").is_file()]
        own = in_square(square, on_disk)
        if not own:
            return f"no terrain tile is installed in square {name}; it is built flat"
        work = self.work
        hgt, bef = work / "hgt", work / "bef"
        vrt = work / "window.vrt"
        window = window_tiles(square, on_disk)
        mosaic = self._run(
            ["gdalbuildvrt", "-q", str(vrt), *(str(tiles_dir / f"{t}{TIF}") for t in window)]
        )
        if mosaic.returncode != 0 or self.staging.digest(vrt) is None:
            return self._fail(
                key,
                state,
                f"elevation for {name}: gdalbuildvrt failed (exit {mosaic.returncode}): "
                f"{_tail(mosaic.stderr or mosaic.stdout)}",
            )
        for tile in own:
            out = hgt / hgt_name(tile)
            warped = self._run(warp_argv(vrt, out, tile))
            if warped.returncode != 0 or self.staging.digest(out) is None:
                return self._fail(
                    key,
                    state,
                    f"elevation for {name}: gdalwarp did not write {out.name} "
                    f"(exit {warped.returncode}): {_tail(warped.stderr or warped.stdout)}",
                )
        converted = self._run(
            _java(Path(state["jar"]), "ElevationRasterTileConverter", name, hgt, bef, 1)
        )
        if converted.returncode != 0 or self.staging.digest(bef / f"{name}.bef") is None:
            return self._fail(
                key,
                state,
                f"elevation for {name}: ElevationRasterTileConverter wrote no {name}.bef "
                f"(exit {converted.returncode}): {_tail(converted.stderr or converted.stdout)}",
            )
        state["tiles"] = " ".join(sorted({*state.get("tiles", "").split(), *own}))
        emptied = self.staging.clear(hgt, lock=self.lock)
        if emptied.returncode != 0:
            return self._fail(
                key,
                state,
                f"elevation for {name}: its .hgt files were not removed: "
                f"{_tail(emptied.stderr) or 'no reason given'}",
            )
        return f"built the elevation of {name} from {len(own)} tile(s){_who(self.staging.who())}"

    def _phase_argv(
        self, phase: str, block: DerivedDataInstall, state: dict[str, str]
    ) -> list[str]:
        work = self.work
        jar = Path(state["jar"])
        p2 = self._tree(block) / "profiles2"
        brf = data_root(self.prefix) / (block.profiles or "")
        if phase == "OsmFastCutter":
            return _java(
                jar,
                phase,
                p2 / LOOKUPS,
                work / "nodetiles",
                work / "waytiles",
                work / "nodes55",
                work / "waytiles55",
                work / "bordernids.dat",
                work / "relations.dat",
                work / "restrictions.dat",
                brf / ALL_BRF,
                p2 / TREKKING_BRF,
                brf / SOFTACCESS_BRF,
                state["input"],
                props=("-DavoidMapPolling=true", "-DuseDenseMaps=true", "-Ddeletetmpfiles=true"),
            )
        if phase == "PosUnifier":
            return _java(
                jar,
                phase,
                work / "nodes55",
                work / "unodes55",
                work / "bordernids.dat",
                work / "bordernodes.dat",
                work / "bef",
                props=("-DuseDenseMaps=true", "-Ddeletetmpfiles=true"),
            )
        return _java(
            jar,
            phase,
            work / "unodes55",
            work / "waytiles55",
            work / "bordernodes.dat",
            work / "restrictions.dat",
            p2 / LOOKUPS,
            brf / ALL_BRF,
            work / "segments",
            "rd5",
            props=("-DuseDenseMaps=true", "-DskipEncodingCheck=true"),
        )

    def _phase(
        self,
        phase: str,
        sources: Sequence[Source],
        block: DerivedDataInstall,
        key: str,
        state: dict[str, str],
    ) -> str:
        if "failed" in state:
            return f"skipped: {state['failed']}"
        result = self._run(self._phase_argv(phase, block, state))
        if result.returncode == REFUSED:
            return self._fail(key, state, f"{phase} was not started: {_tail(result.stderr)}")
        directory, pattern = EFFECT[phase]
        written = self._listing(self.work / directory, pattern)
        if result.returncode != 0 or not written:
            what = "no routing file" if phase == "WayLinker" else f"no {pattern} in {directory}"
            return self._fail(
                key,
                state,
                f"{phase} wrote {what} (exit {result.returncode}): "
                f"{_tail(result.stderr or result.stdout)}",
            )
        if phase != "WayLinker":
            return f"{phase}: {len(written)} file(s) in {directory}{_who(self.staging.who())}"
        for name in written:
            digest = self.staging.digest(self.work / "segments" / name)
            if digest is None:
                return self._fail(key, state, f"WayLinker's {name} could not be read back")
            state[f"rd5:{name}"] = digest
        return (
            f"built {len(written)} routing file(s) over {len(sources)} region(s), staged"
            f"{_who(self.staging.who())}"
        )

    def _install(
        self,
        sources: Sequence[Source],
        out: Path,
        key: str,
        state: dict[str, str],
        writer: PrefixWriter,
    ) -> str:
        built = {k.split(":", 1)[1]: v for k, v in state.items() if k.startswith("rd5:")}
        if "failed" in state or not built:
            return "skipped: BRouter's routing files were not built"
        record = render_record(
            sorted(s.line for s in sources),
            state.get("tiles", "").split(),
            Path(state["jar"]).name,
            sorted(built),
        )
        failure = self._publish(built, out, record, writer)
        scratch = self._scratch("")
        if failure is not None:
            return self.ledger.fail(key, f"{failure}{'; ' + scratch if scratch else ''}")
        if scratch:
            return self.ledger.fail(
                key, f"installed BRouter's routing files under {out}, but {scratch}"
            )
        return f"installed {len(built)} BRouter routing file(s) under {out}; cleared {self.work}"

    def _publish(
        self, built: dict[str, str], out: Path, record: str, writer: PrefixWriter
    ) -> str | None:
        """Install every routing file and the record, all or none; why not, or None."""
        names = sorted(built)
        temporaries = [out / f"{name}{NEW}" for name in names]
        try:
            stale = sorted(p for p in out.glob(f"*{RD5}") if p.name not in built)
        except OSError:
            stale = []
        try:
            try:
                for name, temporary in zip(names, temporaries, strict=True):
                    self.staging.publish(
                        self.work / "segments" / name, temporary, digest=built[name], writer=writer
                    )
            except (BackendError, OSError) as exc:
                writer.remove(temporaries)
                return (
                    f"BRouter's routing files not installed, the previous ones left as they "
                    f"were: {exc}"
                )
            try:
                writer.remove([out / RECORD])
                for name, temporary in zip(names, temporaries, strict=True):
                    _rename(writer, temporary, out / name)
                writer.remove(stale)
                writer.write_text(out / RECORD, record)
            except (BackendError, OSError) as exc:
                writer.remove([*temporaries, *(out / name for name in names), *stale, out / RECORD])
                return (
                    f"BRouter's routing files not installed, and removed rather than left "
                    f"mixed; the next run rebuilds them: {exc}"
                )
        except (BackendError, OSError) as exc:
            return f"BRouter's routing files not installed: {exc}"
        return None


def _who(who: str) -> str:
    return f", {who}" if who else ""


__all__ = [
    "CONVERTER",
    "RECORD",
    "BRouterConverter",
    "find_jar",
    "hgt_name",
    "render_record",
    "square_of_tile",
    "srtm_name",
    "warp_argv",
    "window_tiles",
]
