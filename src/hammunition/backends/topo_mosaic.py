# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The ``ustopo-mosaic`` converter: the installed US Topo sheets as one map
QMapShack can open.  D-068.

A US Topo GeoTIFF is the whole printed page, collar included, each sheet in
its own Transverse Mercator (central meridian at the sheet's centre, NAD83).
``gdalbuildvrt`` cannot mosaic sheets in different coordinate systems, and
stacked uncropped each collar hides its neighbour. So, per sheet, as the
operator in the build's one working directory ``<staging>/ustopo.work/``
(:meth:`Staging.workdir`), under one lock:

* ``gdalwarp`` to EPSG:3857 with ``-te`` the sheet's own box in EPSG:4269
  (NAD83, the sheet's datum), which crops the collar away, JPEG in YCbCr,
  tiled; then
* ``gdaladdo`` 2 4 8 16, internal overviews, so the zoomed-out mosaic reads
  a few kilobytes a sheet rather than whole pages.

Measured on 2026-09-29 on one Delaware sheet with Debian's gdal-bin 3.10.3
(a 9.2 MB download): 2.5 s to warp to 6.0 MB, 0.9 s to add overviews, 8.9 MB
in all, collar gone and the corners exactly the sheet's box
(:data:`WARP_FACTOR`, "measured on one quad" wherever it is printed).

Each warped sheet is published as ``quads/<stem>_<date>.tif`` with a
``.source`` sidecar naming the sheet and :data:`CONVERTER`, and the working
directory is emptied. Then ``gdalbuildvrt`` over every warped sheet on disk,
by absolute path, published as ``ustopo.vrt`` -- the one file QMapShack
lists, since it looks for ``*.vrt`` in the map directory and not below it.
``quads.source`` records the sheets the VRT was built over and, last,
:data:`CONVERTER`; it is written only when every resolved sheet made it in,
so a missing one is built next run.

Effects are checked, not exit statuses (D-031): each output must exist, be
non-empty and hash to what is published. Failures go into D-061's
:class:`~hammunition.backends.terrain.TerrainLedger`; one sheet failing
does not stop the others.
"""

from __future__ import annotations

import shlex
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path

from ..fstopo import FsQuad
from ..manifest.schema import DerivedDataInstall, PackageManifest
from ..ustopo import Quad
from .base import Action, BackendError, Command, CommandRunner
from .data import human_size
from .fstopo import FsTopoResolution
from .regions import SOURCE, data_root, installed_converter, prefix_writer, removal_steps
from .staging import REFUSED, Staging
from .terrain import FSTOPO_FACTOR, FSTOPO_MEASURED, WARP_FACTOR, TerrainLedger
from .topo import TIF, TopoResolution, quad_key, replaced_steps, stem_of
from .verified import PrefixWriter

#: What a warped sheet and the VRT were built by: the last line of
#: :data:`RECORD` and of each sheet's sidecar. Bumped whenever an argv
#: changes the output, so everything an older one warped is warped again.
CONVERTER = "ustopo-mosaic 1"
RECORD = "quads.source"
VRT = "ustopo.vrt"
QUADS_DIR = "quads"
WORKDIR = "ustopo"
#: The ledger key of the VRT; a sheet's is ``ustopo-mosaic:<name>``.
KEY = "ustopo-mosaic"
MEASURED = "measured on one quad"
#: The FSTopo half (D-068, amended 2026-10-01): each sheet expanded from its
#: palette to RGB in tiled JPEG with overviews, and one ``FSTopo.vrt``, the
#: second map QMapShack lists in the same directory.
FSTOPO_CONVERTER = "ustopo-mosaic fstopo 1"
FSTOPO_RECORD = "fstopo.source"
FSTOPO_VRT = "FSTopo.vrt"
FSTOPO_DIR = "fstopo"
FSTOPO_WORKDIR = "fstopo"
FSTOPO_KEY = "ustopo-mosaic:fstopo"


def translate_argv(source: Path, out: Path) -> list[str]:
    """An FSTopo sheet as RGB, tiled JPEG: its palette expanded, because
    ``gdalbuildvrt`` keeps the first sheet's palette for every sheet
    (measured 2026-10-01), and tiled, because the sheet is stored in strips."""
    return [
        "gdal_translate",
        "-q",
        "-expand",
        "rgb",
        "-co",
        "TILED=YES",
        "-co",
        "COMPRESS=JPEG",
        "-co",
        "PHOTOMETRIC=YCBCR",
        str(source),
        str(out),
    ]


def warp_argv(quad: Quad, source: Path, out: Path) -> list[str]:
    """Reproject to Web Mercator and crop to the sheet's own box, collar gone."""
    return [
        "gdalwarp",
        "-q",
        "-overwrite",
        "-t_srs",
        "EPSG:3857",
        "-te_srs",
        "EPSG:4269",
        "-te",
        _deg(quad.west),
        _deg(quad.south),
        _deg(quad.east),
        _deg(quad.north),
        "-r",
        "bilinear",
        "-co",
        "COMPRESS=JPEG",
        "-co",
        "PHOTOMETRIC=YCBCR",
        "-co",
        "TILED=YES",
        str(source),
        str(out),
    ]


def overviews_argv(out: Path) -> list[str]:
    return [
        "gdaladdo",
        "-q",
        "-r",
        "average",
        "--config",
        "COMPRESS_OVERVIEW",
        "JPEG",
        "--config",
        "PHOTOMETRIC_OVERVIEW",
        "YCBCR",
        str(out),
        "2",
        "4",
        "8",
        "16",
    ]


def buildvrt_argv(vrt: Path, inputs: Sequence[Path]) -> list[str]:
    return ["gdalbuildvrt", "-q", str(vrt), *map(str, inputs)]


def render_record(names: Sequence[str], converter: str = CONVERTER) -> str:
    return "".join(f"{n}\n" for n in names) + f"converter: {converter}\n"


def warp_estimate(size: int) -> int:
    return round(size * WARP_FACTOR)


def fstopo_estimate(size: int) -> int:
    return round(size * FSTOPO_FACTOR)


def _deg(value: float) -> str:
    text = f"{value:.7f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def _tail(text: str) -> str:
    return text.strip()[-300:]


def _refused(program: str, result: subprocess.CompletedProcess[str]) -> str:
    return f"{program} was not started: {_tail(result.stderr) or 'refused'}"


def _with(text: str, who: str) -> str:
    return f"{text} {who}" if who else text


@dataclass(frozen=True)
class UstopoMosaicConverter:
    """Turns a ``derived`` block with ``converter: ustopo-mosaic`` into steps."""

    prefix: Path
    resolution: TopoResolution
    staging: Staging
    ledger: TerrainLedger = field(default_factory=TerrainLedger)
    runner: CommandRunner | None = None
    euid: int | None = None
    privileged: bool | None = None
    fstopo: FsTopoResolution | None = None
    """The Forest Service's sheets, when the block names an ``fstopo`` unit."""

    @property
    def writer(self) -> PrefixWriter:
        return prefix_writer(self.prefix, self.privileged, self.runner, self.euid)

    @property
    def work(self) -> Path:
        return self.staging.workdir(WORKDIR)

    @property
    def fstopo_work(self) -> Path:
        return self.staging.workdir(FSTOPO_WORKDIR)

    @property
    def lock(self) -> Path:
        return self.staging.lockfile(self.work)

    def data_dir(self, manifest: PackageManifest) -> Path:
        return data_root(self.prefix) / manifest.name

    def pending(self, manifest: PackageManifest) -> list[Quad]:
        """Sheets warped this run: none warped yet, or by another converter."""
        quads = self.data_dir(manifest) / QUADS_DIR
        return [
            q
            for q in self.resolution.quads
            if not (
                (quads / f"{q.name}{TIF}").is_file()
                and installed_converter(quads / f"{q.name}{TIF}") == CONVERTER
            )
        ]

    def current(self, manifest: PackageManifest) -> bool:
        """Whether the VRT exists and was built over exactly this run's sheets."""
        out = self.data_dir(manifest)
        try:
            recorded = (out / RECORD).read_text()
        except OSError:
            return False
        names = [q.name for q in self.resolution.quads]
        return recorded == render_record(names) and (out / VRT).is_file()

    def steps(self, manifest: PackageManifest, block: DerivedDataInstall) -> list[Action | Command]:
        """US Topo's steps, then FSTopo's when the block names its sheets."""
        return [*self._ustopo_steps(manifest, block), *self._fstopo_steps(manifest, block)]

    def _ustopo_steps(
        self, manifest: PackageManifest, block: DerivedDataInstall
    ) -> list[Action | Command]:
        out = self.data_dir(manifest)
        source = data_root(self.prefix) / block.source
        writer = self.writer
        work = self.work
        steps: list[Action | Command] = []
        pending = self.pending(manifest)
        keep = {q.name for q in self.resolution.quads}
        old, replacing = replaced_steps(out / QUADS_DIR, sorted(keep), writer, "warped quad")
        removals = [*removal_steps(out / QUADS_DIR, TIF, keep | old, writer), *replacing]
        if not keep:
            # No region needs a sheet (every region outside the US, say): a
            # VRT left from before would name files just removed, a broken
            # map, so it goes with them.
            if (out / VRT).is_file() or (out / RECORD).is_file():
                removals.append(
                    Action(
                        kind="remove-data",
                        description=(
                            f"Remove {out / VRT}: none of your map regions needs a US Topo quad"
                        ),
                        detail=str(out / VRT),
                        perform=partial(self._remove_vrt, out, writer),
                        requires_root=writer.privileged,
                    )
                )
            return removals
        if not pending and not removals and self.current(manifest):
            return []
        for quad in pending:
            sheet = source / f"{quad.name}{TIF}"
            staged = work / f"{quad.name}{TIF}"
            warped: dict[str, str] = {}
            steps.append(
                Action(
                    kind="convert",
                    description=(
                        f"Warp US Topo quad {quad.name} to Web Mercator with its collar "
                        f"cropped, as the operator, in {work}: "
                        f"{shlex.join(warp_argv(quad, sheet, staged))}, then "
                        f"{shlex.join(overviews_argv(staged))}; output about "
                        f"{human_size(warp_estimate(quad.size))} ({MEASURED})"
                    ),
                    detail=str(staged),
                    perform=partial(self._warp, quad, sheet, staged, warped),
                )
            )
            dest = out / QUADS_DIR / f"{quad.name}{TIF}"
            steps.append(
                Action(
                    kind="install-data",
                    description=f"Install the warped quad {quad.name}, then clear {work}",
                    # The destination, verbatim, for uninstall's attribution replay.
                    detail=str(dest),
                    perform=partial(self._install, quad, staged, dest, warped, writer),
                    requires_root=writer.privileged,
                )
            )
        steps.extend(removals)
        steps.append(
            Action(
                kind="install-data",
                description=(
                    f"Build QMapShack's US Topo map {out / VRT} over every warped quad, as "
                    f"the operator, in {work}, with gdalbuildvrt -q; then install it and "
                    f"clear {work}"
                ),
                detail=str(out / RECORD),
                perform=partial(self._vrt, out, writer),
                requires_root=writer.privileged,
            )
        )
        return steps

    @staticmethod
    def _remove_vrt(out: Path, writer: PrefixWriter) -> str:
        writer.remove([out / VRT, out / RECORD])
        return f"removed {out / VRT}"

    def _clear(self, lead: str, work: Path | None = None) -> str:
        work = work or self.work
        cleared = self.staging.clear(work, lock=self.staging.lockfile(work))
        if cleared.returncode == 0:
            return ""
        return (
            f"{lead}its scratch {work} was not cleared: "
            f"{_tail(cleared.stderr) or 'no reason given'}"
        )

    def _begin(self, work: Path | None = None) -> str | None:
        work = work or self.work
        refusal = self.staging.prepare(work)
        if refusal is not None:
            return refusal
        cleared = self.staging.clear(work, lock=self.staging.lockfile(work))
        if cleared.returncode == REFUSED:
            return _refused("the build", cleared)
        if cleared.returncode != 0:
            return f"could not clear {work}: {_tail(cleared.stderr) or 'no reason given'}"
        return None

    def _warp(self, quad: Quad, sheet: Path, staged: Path, warped: dict[str, str]) -> str:
        key = f"{KEY}:{quad.name}"
        if quad_key(quad.name) in self.ledger.failed:
            return f"skipped: US Topo quad {quad.name} did not install"
        if not sheet.is_file():
            return self.ledger.fail(key, f"{quad.name}: {sheet} is not installed")
        # gdalwarp -overwrite replaces a leftover, and gdaladdo would add
        # overviews to one: the directory is emptied first, under the lock.
        refusal = self._begin()
        if refusal is not None:
            return self.ledger.fail(key, f"{quad.name}: {refusal}")
        result = self.staging.run(warp_argv(quad, sheet, staged), cwd=self.work, lock=self.lock)
        if result.returncode == REFUSED:
            return self.ledger.fail(key, f"{quad.name}: {_refused('gdalwarp', result)}")
        if result.returncode != 0 or self.staging.digest(staged) is None:
            return self.ledger.fail(
                key,
                f"{quad.name}: gdalwarp wrote no warped quad (exit {result.returncode}): "
                f"{_tail(result.stderr or result.stdout)}{self._clear('; ')}",
            )
        result = self.staging.run(overviews_argv(staged), cwd=self.work, lock=self.lock)
        if result.returncode == REFUSED:
            return self.ledger.fail(key, f"{quad.name}: {_refused('gdaladdo', result)}")
        digest = self.staging.digest(staged)
        if result.returncode != 0 or digest is None:
            return self.ledger.fail(
                key,
                f"{quad.name}: gdaladdo did not add overviews (exit {result.returncode}): "
                f"{_tail(result.stderr or result.stdout)}{self._clear('; ')}",
            )
        warped["sha256"] = digest
        return f"{_with(f'warped {quad.name}', self.staging.who())} (staged, {staged})"

    def _install(
        self, quad: Quad, staged: Path, dest: Path, warped: dict[str, str], writer: PrefixWriter
    ) -> str:
        if "sha256" not in warped:
            return f"skipped: {quad.name} was not warped"
        key = f"{KEY}:{quad.name}"
        failure = None
        try:
            self.staging.publish(staged, dest, digest=warped["sha256"], writer=writer)
            writer.write_text(
                dest.with_name(dest.name + SOURCE), f"{quad.name}\nconverter: {CONVERTER}\n"
            )
        except (BackendError, OSError) as exc:
            failure = str(exc)
        scratch = self._clear("")
        if failure is not None:
            return self.ledger.fail(
                key, f"{quad.name}: {failure}{'; ' + scratch if scratch else ''}"
            )
        if scratch:
            return self.ledger.fail(key, f"{quad.name}: installed {dest}, but {scratch}")
        return f"installed {dest}; cleared {self.work}"

    def _vrt(self, out: Path, writer: PrefixWriter) -> str:
        wanted = [q.name for q in self.resolution.quads]
        quads = out / QUADS_DIR
        warped: list[Path] = []
        exact = 0
        for name in wanted:
            if (quads / f"{name}{TIF}").is_file():
                warped.append(quads / f"{name}{TIF}")
                exact += 1
                continue
            # An older edition kept because this one did not arrive (review
            # I1): the map keeps it rather than a hole.
            older = sorted(
                p for p in quads.glob(f"*{TIF}") if stem_of(p.name[: -len(TIF)]) == stem_of(name)
            )
            if older:
                warped.append(older[-1])
        if not warped:
            # Review M3: every warped sheet it named is gone; a VRT left
            # behind would be a broken map.
            if (out / VRT).is_file() or (out / RECORD).is_file():
                self._remove_vrt(out, writer)
                return f"no US Topo quad is warped; removed {out / VRT}"
            return "no US Topo quad is warped; QMapShack gets no US Topo map this run"
        refusal = self._begin()
        if refusal is not None:
            return self.ledger.fail(KEY, f"{VRT} not built: {refusal}")
        staged = self.work / VRT
        result = self.staging.run(buildvrt_argv(staged, warped), cwd=self.work, lock=self.lock)
        if result.returncode == REFUSED:
            return self.ledger.fail(KEY, f"{VRT} not built: {_refused('gdalbuildvrt', result)}")
        digest = self.staging.digest(staged)
        if result.returncode != 0 or digest is None:
            return self.ledger.fail(
                KEY,
                f"gdalbuildvrt did not build {VRT} (exit {result.returncode}): "
                f"{_tail(result.stderr or result.stdout)}{self._clear('; ')}",
            )
        try:
            self.staging.publish(staged, out / VRT, digest=digest, writer=writer)
        except (BackendError, OSError) as exc:
            return self.ledger.fail(KEY, f"{out / VRT}: {exc}{self._clear('; ')}")
        scratch = self._clear("")
        # Recorded only when every sheet made it in at its own edition: a
        # missing one is built next run.
        if exact == len(wanted):
            writer.write_text(out / RECORD, render_record(wanted))
        done = _with(f"built {out / VRT} ({len(warped)} quad(s))", self.staging.who())
        if scratch:
            return self.ledger.fail(KEY, f"{done}, but {scratch}")
        return f"{done}; cleared {self.work}"

    # -----------------------------------------------------------------------
    # FSTopo (D-068, amended 2026-10-01): no warp -- the sheet is already
    # EPSG:4269 and collarless -- but a palette expansion and tiles, then one
    # FSTopo.vrt beside ustopo.vrt, in the directory QMapShack already lists.
    # -----------------------------------------------------------------------

    def fstopo_pending(self, manifest: PackageManifest) -> list[FsQuad]:
        """FSTopo sheets converted this run: none converted yet, or by another converter."""
        if self.fstopo is None:
            return []
        done = self.data_dir(manifest) / FSTOPO_DIR
        return [
            q
            for q in self.fstopo.quads
            if not (
                (done / f"{q.name}{TIF}").is_file()
                and installed_converter(done / f"{q.name}{TIF}") == FSTOPO_CONVERTER
            )
        ]

    def fstopo_sizes(self, manifest: PackageManifest, block: DerivedDataInstall) -> list[int]:
        """The sheet size of each pending FSTopo sheet: the download's when it
        is fetched this run, else the installed file's."""
        if self.fstopo is None:
            return []
        fetched = {f.quad.secoord: f.size for f in self.fstopo.fetch}
        source = data_root(self.prefix) / (block.fstopo or "")
        sizes = []
        for quad in self.fstopo_pending(manifest):
            size = fetched.get(quad.secoord)
            if size is None:
                try:
                    size = (source / f"{quad.name}{TIF}").stat().st_size
                except OSError:
                    size = 0
            sizes.append(size)
        return sizes

    def _fstopo_current(self, out: Path, names: Sequence[str]) -> bool:
        try:
            recorded = (out / FSTOPO_RECORD).read_text()
        except OSError:
            return False
        return recorded == render_record(names, FSTOPO_CONVERTER) and (out / FSTOPO_VRT).is_file()

    def _fstopo_steps(
        self, manifest: PackageManifest, block: DerivedDataInstall
    ) -> list[Action | Command]:
        if block.fstopo is None or self.fstopo is None:
            return []
        out = self.data_dir(manifest)
        source = data_root(self.prefix) / block.fstopo
        writer = self.writer
        work = self.fstopo_work
        keep = {q.name for q in self.fstopo.quads}
        old, replacing = replaced_steps(
            out / FSTOPO_DIR, sorted(keep), writer, "converted FSTopo quad"
        )
        removals = [*removal_steps(out / FSTOPO_DIR, TIF, keep | old, writer), *replacing]
        if not keep:
            if (out / FSTOPO_VRT).is_file() or (out / FSTOPO_RECORD).is_file():
                removals.append(
                    Action(
                        kind="remove-data",
                        description=(
                            f"Remove {out / FSTOPO_VRT}: none of your map regions needs an "
                            f"FSTopo quad"
                        ),
                        detail=str(out / FSTOPO_VRT),
                        perform=partial(self._remove_fstopo_vrt, out, writer),
                        requires_root=writer.privileged,
                    )
                )
            return removals
        pending = self.fstopo_pending(manifest)
        names = [q.name for q in self.fstopo.quads]
        if not pending and not removals and self._fstopo_current(out, names):
            return []
        steps: list[Action | Command] = []
        for quad, size in zip(pending, self.fstopo_sizes(manifest, block), strict=True):
            sheet = source / f"{quad.name}{TIF}"
            staged = work / f"{quad.name}{TIF}"
            made: dict[str, str] = {}
            steps.append(
                Action(
                    kind="convert",
                    description=(
                        f"Convert FSTopo quad {quad.name} to tiled RGB, as the operator, in "
                        f"{work}: {shlex.join(translate_argv(sheet, staged))}, then "
                        f"{shlex.join(overviews_argv(staged))}; output about "
                        f"{human_size(fstopo_estimate(size))} ({FSTOPO_MEASURED})"
                    ),
                    detail=str(staged),
                    perform=partial(self._translate, quad, sheet, staged, made),
                )
            )
            dest = out / FSTOPO_DIR / f"{quad.name}{TIF}"
            steps.append(
                Action(
                    kind="install-data",
                    description=f"Install the converted FSTopo quad {quad.name}, then clear {work}",
                    detail=str(dest),
                    perform=partial(self._install_fstopo, quad, staged, dest, made, writer),
                    requires_root=writer.privileged,
                )
            )
        steps.extend(removals)
        steps.append(
            Action(
                kind="install-data",
                description=(
                    f"Build QMapShack's FSTopo map {out / FSTOPO_VRT} over every converted "
                    f"quad, as the operator, in {work}, with gdalbuildvrt -q; then install it "
                    f"and clear {work}"
                ),
                detail=str(out / FSTOPO_RECORD),
                perform=partial(self._fstopo_vrt, out, writer),
                requires_root=writer.privileged,
            )
        )
        return steps

    @staticmethod
    def _remove_fstopo_vrt(out: Path, writer: PrefixWriter) -> str:
        writer.remove([out / FSTOPO_VRT, out / FSTOPO_RECORD])
        return f"removed {out / FSTOPO_VRT}"

    def _translate(self, quad: FsQuad, sheet: Path, staged: Path, made: dict[str, str]) -> str:
        key = f"{FSTOPO_KEY}:{quad.name}"
        work = self.fstopo_work
        lock = self.staging.lockfile(work)
        if quad_key(quad.name) in self.ledger.failed:
            return f"skipped: FSTopo quad {quad.name} did not install"
        if not sheet.is_file():
            return self.ledger.fail(key, f"{quad.name}: {sheet} is not installed")
        refusal = self._begin(work)
        if refusal is not None:
            return self.ledger.fail(key, f"{quad.name}: {refusal}")
        result = self.staging.run(translate_argv(sheet, staged), cwd=work, lock=lock)
        if result.returncode == REFUSED:
            return self.ledger.fail(key, f"{quad.name}: {_refused('gdal_translate', result)}")
        if result.returncode != 0 or self.staging.digest(staged) is None:
            return self.ledger.fail(
                key,
                f"{quad.name}: gdal_translate wrote no converted quad (exit "
                f"{result.returncode}): {_tail(result.stderr or result.stdout)}"
                f"{self._clear('; ', work)}",
            )
        result = self.staging.run(overviews_argv(staged), cwd=work, lock=lock)
        if result.returncode == REFUSED:
            return self.ledger.fail(key, f"{quad.name}: {_refused('gdaladdo', result)}")
        digest = self.staging.digest(staged)
        if result.returncode != 0 or digest is None:
            return self.ledger.fail(
                key,
                f"{quad.name}: gdaladdo did not add overviews (exit {result.returncode}): "
                f"{_tail(result.stderr or result.stdout)}{self._clear('; ', work)}",
            )
        made["sha256"] = digest
        return f"{_with(f'converted {quad.name}', self.staging.who())} (staged, {staged})"

    def _install_fstopo(
        self, quad: FsQuad, staged: Path, dest: Path, made: dict[str, str], writer: PrefixWriter
    ) -> str:
        if "sha256" not in made:
            return f"skipped: {quad.name} was not converted"
        key = f"{FSTOPO_KEY}:{quad.name}"
        work = self.fstopo_work
        failure = None
        try:
            self.staging.publish(staged, dest, digest=made["sha256"], writer=writer)
            writer.write_text(
                dest.with_name(dest.name + SOURCE), f"{quad.name}\nconverter: {FSTOPO_CONVERTER}\n"
            )
        except (BackendError, OSError) as exc:
            failure = str(exc)
        scratch = self._clear("", work)
        if failure is not None:
            return self.ledger.fail(
                key, f"{quad.name}: {failure}{'; ' + scratch if scratch else ''}"
            )
        if scratch:
            return self.ledger.fail(key, f"{quad.name}: installed {dest}, but {scratch}")
        return f"installed {dest}; cleared {work}"

    def _fstopo_vrt(self, out: Path, writer: PrefixWriter) -> str:
        assert self.fstopo is not None
        wanted = [q.name for q in self.fstopo.quads]
        done = out / FSTOPO_DIR
        work = self.fstopo_work
        inputs: list[Path] = []
        exact = 0
        for name in wanted:
            if (done / f"{name}{TIF}").is_file():
                inputs.append(done / f"{name}{TIF}")
                exact += 1
                continue
            older = sorted(
                p for p in done.glob(f"*{TIF}") if stem_of(p.name[: -len(TIF)]) == stem_of(name)
            )
            if older:
                inputs.append(older[-1])
        if not inputs:
            if (out / FSTOPO_VRT).is_file() or (out / FSTOPO_RECORD).is_file():
                self._remove_fstopo_vrt(out, writer)
                return f"no FSTopo quad is converted; removed {out / FSTOPO_VRT}"
            return "no FSTopo quad is converted; QMapShack gets no FSTopo map this run"
        refusal = self._begin(work)
        if refusal is not None:
            return self.ledger.fail(FSTOPO_KEY, f"{FSTOPO_VRT} not built: {refusal}")
        staged = work / FSTOPO_VRT
        result = self.staging.run(
            buildvrt_argv(staged, inputs), cwd=work, lock=self.staging.lockfile(work)
        )
        if result.returncode == REFUSED:
            return self.ledger.fail(
                FSTOPO_KEY, f"{FSTOPO_VRT} not built: {_refused('gdalbuildvrt', result)}"
            )
        digest = self.staging.digest(staged)
        if result.returncode != 0 or digest is None:
            return self.ledger.fail(
                FSTOPO_KEY,
                f"gdalbuildvrt did not build {FSTOPO_VRT} (exit {result.returncode}): "
                f"{_tail(result.stderr or result.stdout)}{self._clear('; ', work)}",
            )
        try:
            self.staging.publish(staged, out / FSTOPO_VRT, digest=digest, writer=writer)
        except (BackendError, OSError) as exc:
            return self.ledger.fail(
                FSTOPO_KEY, f"{out / FSTOPO_VRT}: {exc}{self._clear('; ', work)}"
            )
        scratch = self._clear("", work)
        if exact == len(wanted):
            writer.write_text(out / FSTOPO_RECORD, render_record(wanted, FSTOPO_CONVERTER))
        built = _with(f"built {out / FSTOPO_VRT} ({len(inputs)} quad(s))", self.staging.who())
        if scratch:
            return self.ledger.fail(FSTOPO_KEY, f"{built}, but {scratch}")
        return f"{built}; cleared {work}"
