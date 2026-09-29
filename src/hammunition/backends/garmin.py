# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The ``mkgmap`` converter: a Garmin map per region, for QMapShack.  D-061.

Each region takes two steps. **convert**, as the operator in
the region's own working directory ``<staging>/<slug>.work/``
(:meth:`Staging.workdir`): ``mkgmap-splitter`` cuts the region's ``.osm.pbf`` into
tiles in ``split/`` (48 s on one US-state-sized region), then ``mkgmap`` with
its ``default`` style, which already draws and routes
``highway=path|footway|track|bridleway``, ``sac_scale`` and ``tracktype``,
builds ``img/gmapsupp.img`` from them (126 s). Its output is checked, not
its exit status (D-031): mkgmap exits 0 while logging SEVERE. **install**,
as root only where the prefix needs it: ``gmapsupp.img`` is published as
``<data>/<unit>/<slug>.img`` re-verified against the operator's digest, with
a ``.source`` sidecar holding the snapshot and :data:`CONVERTER`, and
``<staging>/<slug>.work/`` is emptied. A failed build empties it too: a
region's scratch is about three times its download. A map whose sidecar
records no converter, or another one, is built again even at the same
snapshot, as Navit's are since #133.

Scratch is only ever cleared by :meth:`Staging.clear`, which empties the
working directory as the operator under the lock :meth:`Staging.run` takes,
so a directory another conversion is using is left alone (125, nothing
deleted). Root never removes a working directory itself, and a refused run
(125) removes nothing: the refusal proves another conversion owns it.

Not passed: ``--index`` and ``--housenumbers``. They need mkgmap's upstream
bounds files, which have no published checksum, and QMapShack does not read
that index (spec section 7).

Heap. Debian's ``/usr/bin/mkgmap-splitter`` honours ``JAVA_OPTS`` (it adds
``-Xmx2000m`` only when ``JAVA_OPTS`` names no ``-Xmx``); the spike ran it with
4000 MB, :data:`SPLITTER_HEAP`. Debian's ``/usr/bin/mkgmap`` is
``java -jar mkgmap.jar "$@"`` and ignores ``JAVA_OPTS``, so without help it
runs on the JVM's default heap, a quarter of the machine's memory -- 4 GB on a
16 GB machine, where the spike needed about 6 GB. The JVM itself reads
``JAVA_TOOL_OPTIONS``, so mkgmap's heap, :data:`MKGMAP_HEAP`, arrives through
that; the splitter's command-line ``-Xmx`` from ``JAVA_OPTS`` overrides
``JAVA_TOOL_OPTIONS``, so one environment serves both. A dropped process gets
a minimal environment, so neither reaches it from root's own: Task 12 builds
``Staging(environ={"JAVA_OPTS": SPLITTER_HEAP, "JAVA_TOOL_OPTIONS":
MKGMAP_HEAP})``. The plan states the need (:data:`MKGMAP_NEED`). The JVM
prints ``Picked up JAVA_TOOL_OPTIONS`` on stderr, seen only in a failure tail.

Every run is refused before it starts -- return code 125 -- when another
conversion holds the region's working directory or root has nobody to run as;
that fails the region by name with the reason, and the rest continue.

mkgmap runs in ``split/``, as the spike measured it. That was believed
necessary because ``template.args`` names its tiles relatively
(``input-file: 63240001.osm.pbf``), but mkgmap's ``options.txt`` says a
relative ``input-file`` read through ``-c`` resolves against the args file's
own location. The build may then be able to run in ``<slug>.work`` under the
same lock as the split; that is unconfirmed on a real mkgmap, and Task 16
checks it before anything changes.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path

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
from .terrain import (
    GARMIN_FACTOR,
    GARMIN_SCRATCH_FACTOR,
    MEASURED,
    TerrainLedger,
    garmin_estimate,
)
from .verified import PrefixWriter

IMG = ".img"
#: The splitter's heap, through ``JAVA_OPTS`` (the spike's 4 GB).
SPLITTER_HEAP = "-Xmx4000m"
#: mkgmap's heap, through ``JAVA_TOOL_OPTIONS``: its wrapper ignores ``JAVA_OPTS``.
MKGMAP_HEAP = "-Xmx6000m"
#: What the plan says mkgmap needs, from :data:`MKGMAP_HEAP`.
MKGMAP_NEED = "needs about 6 GB free for mkgmap"
#: What an ``.img`` was built by, on the second line of its ``.source``
#: sidecar. Bumped whenever the argv or the style changes the output, so every
#: map built by an older one is built again though its snapshot has not moved.
CONVERTER = "mkgmap 1"


def splitter_argv(pbf: Path, split: Path) -> list[str]:
    """The fixed argv of the split. Nothing in it comes from a manifest."""
    return [
        "mkgmap-splitter",
        "--output=pbf",
        "--max-nodes=1600000",
        f"--output-dir={split}",
        str(pbf),
    ]


def mkgmap_argv(split: Path, img: Path, jobs: int) -> list[str]:
    """The fixed argv of the build, run in *split* as the spike measured it
    (the module docstring says why that may be unnecessary)."""
    return [
        "mkgmap",
        f"--output-dir={img}",
        "--style=default",
        "--route",
        "--add-pois-to-areas",
        "--unicode",
        "--gmapsupp",
        f"--max-jobs={jobs}",
        "-c",
        str(split / "template.args"),
    ]


def _tail(text: str) -> str:
    return text.strip()[-300:]


def _refused(program: str, result: subprocess.CompletedProcess[str]) -> str:
    """A run :meth:`Staging.run` refused (125): *program* never started."""
    return f"{program} was not started: {_tail(result.stderr) or 'refused'}"


@dataclass(frozen=True)
class GarminConverter:
    """Turns a ``derived`` block with ``converter: mkgmap`` into steps."""

    prefix: Path
    files: Sequence[RegionFile]
    staging: Staging
    keep: frozenset[str] = frozenset()
    regions: MapLedger = field(default_factory=MapLedger)
    """Piece 1's ledger, read only: a region that did not install is not built."""
    ledger: TerrainLedger = field(default_factory=TerrainLedger)
    runner: CommandRunner | None = None
    euid: int | None = None
    privileged: bool | None = None
    jobs: int = field(default_factory=lambda: os.cpu_count() or 1)

    @property
    def writer(self) -> PrefixWriter:
        return prefix_writer(self.prefix, self.privileged, self.runner, self.euid)

    def data_dir(self, manifest: PackageManifest) -> Path:
        return data_root(self.prefix) / manifest.name

    @staticmethod
    def _current(dest: Path, region: RegionFile) -> bool:
        return (
            dest.is_file()
            and installed_snapshot(dest) == region.snapshot
            and installed_converter(dest) == CONVERTER
        )

    def pending(self, manifest: PackageManifest) -> list[RegionFile]:
        """Regions this run builds: no ``.img``, or one from another snapshot
        or another converter (none recorded counts as another)."""
        out = self.data_dir(manifest)
        return [f for f in self.files if not self._current(out / f"{f.slug}{IMG}", f)]

    def steps(self, manifest: PackageManifest, block: DerivedDataInstall) -> list[Action | Command]:
        out = self.data_dir(manifest)
        source_dir = data_root(self.prefix) / block.source
        writer = self.writer
        steps: list[Action | Command] = []
        for region in self.files:
            dest = out / f"{region.slug}{IMG}"
            if self._current(dest, region):
                continue
            pbf = source_dir / f"{region.slug}{PBF}"
            work = self.staging.workdir(region.slug)
            split, img = work / "split", work / "img"
            key = f"{manifest.name}:{region.slug}"
            built: dict[str, str] = {}
            steps.append(
                Action(
                    kind="convert",
                    description=(
                        f"Build the Garmin map of {region.region} ({region.snapshot}) for "
                        f"QMapShack, as the operator, in {work}: "
                        f"{shlex.join(splitter_argv(pbf, split))}, then in {split}: "
                        f"{shlex.join(mkgmap_argv(split, img, self.jobs))}, which "
                        f"{MKGMAP_NEED}; output about "
                        f"{human_size(garmin_estimate(region.size))} ({GARMIN_FACTOR}x the "
                        f"download) and up to {human_size(GARMIN_SCRATCH_FACTOR * region.size)} "
                        f"of scratch while it runs ({MEASURED})"
                    ),
                    detail=str(work),
                    perform=partial(self._convert, region, key, pbf, work, built),
                )
            )
            steps.append(
                Action(
                    kind="install-data",
                    description=(
                        f"Install the Garmin map of {region.region} ({region.snapshot}), "
                        f"then clear its scratch {work}"
                    ),
                    # The destination, verbatim, for uninstall's attribution replay.
                    detail=str(dest),
                    perform=partial(self._install, region, key, work, dest, built, writer),
                    requires_root=writer.privileged,
                )
            )
        keep = {f.slug for f in self.files} | set(self.keep)
        steps.extend(removal_steps(out, IMG, keep, writer))
        return steps

    def _convert(
        self, region: RegionFile, key: str, pbf: Path, work: Path, built: dict[str, str]
    ) -> str:
        if region.slug in self.regions.failed:
            return f"skipped: {region.region} did not install"
        if not pbf.is_file():
            return self.ledger.fail(key, f"{region.region}: {pbf} is not installed")
        split, img = work / "split", work / "img"
        cleared = self.staging.clear(work)  # a failed run's leftovers, under the lock
        if cleared.returncode == REFUSED:
            return self.ledger.fail(key, f"{region.region}: {_refused('the build', cleared)}")
        if cleared.returncode != 0:
            return self.ledger.fail(
                key, f"{region.region}: could not clear {work}: {_tail(cleared.stderr)}"
            )
        refusal = self.staging.prepare(split, img)
        if refusal is not None:
            return self.ledger.fail(key, f"{region.region}: {refusal}")
        cut = self.staging.run(splitter_argv(pbf, split), cwd=work)
        if cut.returncode == REFUSED:
            return self.ledger.fail(key, f"{region.region}: {_refused('mkgmap-splitter', cut)}")
        if cut.returncode != 0 or self.staging.digest(split / "template.args") is None:
            self.staging.clear(work)
            return self.ledger.fail(
                key,
                f"{region.region}: mkgmap-splitter did not split {pbf.name} "
                f"(exit {cut.returncode}): {_tail(cut.stderr or cut.stdout)}",
            )
        made = self.staging.run(mkgmap_argv(split, img, self.jobs), cwd=split)
        if made.returncode == REFUSED:
            return self.ledger.fail(key, f"{region.region}: {_refused('mkgmap', made)}")
        digest = self.staging.digest(img / "gmapsupp.img")
        if made.returncode != 0 or digest is None:
            self.staging.clear(work)
            return self.ledger.fail(
                key,
                f"{region.region}: mkgmap wrote no Garmin map from {pbf.name} "
                f"(exit {made.returncode}): {_tail(made.stderr or made.stdout)}",
            )
        built["sha256"] = digest
        who = self.staging.who()
        return (
            f"built the Garmin map of {region.region}{' ' + who if who else ''} "
            f"(staged, {img / 'gmapsupp.img'})"
        )

    def _install(
        self,
        region: RegionFile,
        key: str,
        work: Path,
        dest: Path,
        built: dict[str, str],
        writer: PrefixWriter,
    ) -> str:
        if "sha256" not in built:
            return f"skipped: the Garmin map of {region.region} was not built"
        try:
            self.staging.publish(
                work / "img" / "gmapsupp.img", dest, digest=built["sha256"], writer=writer
            )
            writer.write_text(
                dest.with_name(dest.name + SOURCE), f"{region.snapshot}\nconverter: {CONVERTER}\n"
            )
        except (BackendError, OSError) as exc:
            return self.ledger.fail(key, f"{region.region}: {exc}")
        finally:
            self.staging.clear(work)
        return f"installed {dest}; cleared {work}"
