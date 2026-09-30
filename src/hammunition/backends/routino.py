# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The ``routino-planetsplitter`` converter: one Routino database over every
region, for QMapShack's offline routing on foot.  D-061.

One database, not one per region, so a route may cross from one region into
the next -- QMapShack's own help says Routino cannot route across two
databases. Built as the operator in one working directory under the staging directory,
``routino.work``, for the whole multi-region build:
``planetsplitter --parse-only`` for the first region and ``--parse-only
--append`` for each after it, then one ``--process-only``, prefix
``hammunition``. Measured on 2026-09-28 on one region with Debian's
routino 3.4.3: parse 22 s, process 83 s, the four ``hammunition-*.mem``
files 0.67 times the ``.osm.pbf``, the intermediate files gone when the
process step finishes.

The trade, stated in the plan: a region that fails to parse fails the
database, not only itself, and the step says which region and why. The
installed database is left as it was.

``<data>/<unit>/hammunition.source`` records the regions and snapshots the
database was built from; the database is current when that record matches
this run's regions, and only then is nothing rebuilt.

The four ``.mem`` files are one database, so they install all four or none:
each is published and verified under a temporary name beside its place
(``<name>.new``), and only when all four are there is the old record
removed, the four renamed into place and the new record written. A publish
that fails partway removes the temporaries and leaves the previous database,
record included, exactly as it was. A rename failing after that (one
directory, so only a failing disk) removes the database and its record
rather than leave QMapShack a mixed set, and the next run rebuilds.

Scratch is only ever cleared by :meth:`Staging.clear`, which empties
``routino.work`` as the operator under the build's one lock,
``routino.work.lock`` -- the lock every parse and the process step hold --
so nothing clears the database while a phase is building it. Root never
removes a working directory itself; a refused run (125) removes nothing, the
refusal proving another conversion owns it; and a clear that fails is named
in the database's failure, never a silent "cleared".

Routino's ``foot`` profile from ``routino-common`` is used unchanged; it
does not read ``sac_scale`` (spec section 7).
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path

from ..geofabrik import RegionFile
from ..manifest.schema import DerivedDataInstall, PackageManifest
from .base import Action, BackendError, Command, CommandRunner
from .data import human_size
from .regions import PBF, MapLedger, data_root, installed_snapshot, prefix_writer
from .staging import REFUSED, Staging
from .terrain import MEASURED, ROUTINO_FACTOR, ROUTINO_SCRATCH_FACTOR, TerrainLedger
from .verified import PrefixWriter

DB_PREFIX = "hammunition"
DB_FILES = tuple(f"{DB_PREFIX}-{part}.mem" for part in ("nodes", "segments", "ways", "relations"))
RECORD = f"{DB_PREFIX}.source"
#: The suffix a database file is published under before all four are renamed in.
NEW = ".new"
TAGGING = Path("/usr/share/routino/tagging.xml")


def parse_argv(work: Path, pbf: Path, *, append: bool) -> list[str]:
    """The fixed argv that parses one region. Nothing in it comes from a manifest."""
    return [
        "planetsplitter",
        f"--dir={work}",
        f"--prefix={DB_PREFIX}",
        f"--tagging={TAGGING}",
        "--parse-only",
        *(["--append"] if append else []),
        str(pbf),
    ]


def process_argv(work: Path) -> list[str]:
    return ["planetsplitter", f"--dir={work}", f"--prefix={DB_PREFIX}", "--process-only"]


@dataclass(frozen=True)
class Source:
    """One region the database is built from."""

    region: str
    slug: str
    snapshot: str | None
    pbf: Path
    size: int


def record_of(sources: Sequence[Source]) -> str:
    return "".join(f"{s.slug} {s.snapshot or '-'}\n" for s in sorted(sources, key=lambda s: s.slug))


def _tail(result_text: str) -> str:
    return result_text.strip()[-300:]


def _refused(result: subprocess.CompletedProcess[str]) -> str:
    """A run :meth:`Staging.run` refused (125): nothing started, nothing removed."""
    return f"planetsplitter was not started: {_tail(result.stderr) or 'refused'}"


def _outcome(text: str, who: str) -> str:
    """*text*, with who ran it when the engine is root (D-043)."""
    return f"{text}, {who}" if who else text


@dataclass(frozen=True)
class RoutinoConverter:
    """Turns a ``derived`` block with ``converter: routino-planetsplitter`` into steps."""

    prefix: Path
    files: Sequence[RegionFile]
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

    def data_dir(self, manifest: PackageManifest) -> Path:
        return data_root(self.prefix) / manifest.name

    def sources(self, block: DerivedDataInstall) -> list[Source]:
        """Every region the database covers: this run's, then the kept ones."""
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

    def pending(self, manifest: PackageManifest, block: DerivedDataInstall) -> list[Source]:
        """The regions the database is rebuilt over this run, or none when it is current."""
        sources = self.sources(block)
        out = self.data_dir(manifest)
        try:
            recorded = (out / RECORD).read_text()
        except OSError:
            recorded = None
        present = all((out / name).is_file() for name in DB_FILES)
        if sources and present and recorded == record_of(sources):
            return []
        return sources

    @property
    def work(self) -> Path:
        """The one working directory every parse and the process step share."""
        return self.staging.workdir("routino")

    @property
    def lock(self) -> Path:
        """The build's one lock, held by every parse, the process step and every clear."""
        return self.staging.lockfile(self.work)

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
        steps: list[Action | Command] = []
        for index, source in enumerate(sources):
            argv = parse_argv(work, source.pbf, append=index > 0)
            steps.append(
                Action(
                    kind="convert",
                    description=(
                        f"Parse {source.region} into the Routino database, as the "
                        f"operator, in {work}: {' '.join(argv)}"
                    ),
                    detail=str(work),
                    perform=partial(self._parse, source, argv, index == 0, key, state),
                )
            )
        steps.append(
            Action(
                kind="convert",
                description=(
                    f"Build one Routino database over {len(sources)} region(s) for "
                    f"QMapShack's routing on foot, as the operator: "
                    f"{' '.join(process_argv(work))}; output about "
                    f"{human_size(round(total * ROUTINO_FACTOR))} ({ROUTINO_FACTOR}x the "
                    f"downloads together) and up to "
                    f"{human_size(ROUTINO_SCRATCH_FACTOR * total)} of scratch while it runs "
                    f"({MEASURED}). A region that fails to parse fails the database"
                ),
                detail=str(work),
                perform=partial(self._process, key, state),
            )
        )
        steps.append(
            Action(
                kind="install-data",
                description=(
                    f"Install the Routino database ({', '.join(DB_FILES)}) and its record "
                    f"of regions, then clear its scratch {work}"
                ),
                detail=str(out / RECORD),
                perform=partial(self._install, sources, out, key, state, writer),
                requires_root=writer.privileged,
            )
        )
        return steps

    def _parse(
        self, source: Source, argv: list[str], first: bool, key: str, state: dict[str, str]
    ) -> str:
        if "failed" in state:
            return f"skipped: {state['failed']}"
        work = self.work
        if source.slug in self.regions.failed:
            state["failed"] = (
                f"{source.region} did not install, and the database is built over every "
                f"region or none; the installed one is left as it was"
            )
            # This run's own parsed regions; the regions ledger reports the
            # region, so only a clear that failed is this ledger's to report.
            scratch = "" if first else self._scratch("")
            if scratch:
                return self.ledger.fail(key, f"Routino database not built: {scratch}")
            return f"skipped: {state['failed']}"
        if not source.pbf.is_file():
            state["failed"] = f"{source.region}: {source.pbf} is not installed"
            scratch = "" if first else self._scratch("; ")
            return self.ledger.fail(key, f"Routino database not built: {state['failed']}{scratch}")
        if first:
            refusal = self.staging.prepare(work)
            if refusal is not None:
                state["failed"] = refusal
                return self.ledger.fail(key, f"Routino database not built: {refusal}")
            # A crashed run's leftovers, under the lock: 125 means another
            # conversion holds the directory, and nothing in it is deleted.
            cleared = self.staging.clear(work, lock=self.lock)
            if cleared.returncode != 0:
                state["failed"] = (
                    _refused(cleared)
                    if cleared.returncode == REFUSED
                    else f"could not clear {work}: {_tail(cleared.stderr) or 'no reason given'}"
                )
                return self.ledger.fail(
                    key, f"Routino database not built: {source.region}: {state['failed']}"
                )
        result = self.staging.run(argv, cwd=work, lock=self.lock)
        if result.returncode == REFUSED:
            # 125 started nothing: the directory is another run's, left alone.
            state["failed"] = f"{source.region}: {_refused(result)}"
            return self.ledger.fail(key, f"Routino database not built: {state['failed']}")
        if result.returncode != 0:
            state["failed"] = (
                f"planetsplitter could not parse {source.region} "
                f"(exit {result.returncode}): {_tail(result.stderr or result.stdout)}"
            )
            scratch = self._scratch("; ")
            return self.ledger.fail(key, f"Routino database not built: {state['failed']}{scratch}")
        return _outcome(f"parsed {source.region}", self.staging.who())

    def _process(self, key: str, state: dict[str, str]) -> str:
        if "failed" in state:
            return f"skipped: {state['failed']}"
        work = self.work
        result = self.staging.run(process_argv(work), cwd=work, lock=self.lock)
        if result.returncode == REFUSED:
            state["failed"] = f"planetsplitter did not build the database: {_refused(result)}"
            return self.ledger.fail(key, f"Routino database not built: {state['failed']}")
        digests = {name: self.staging.digest(work / name) for name in DB_FILES}
        missing = sorted(name for name, digest in digests.items() if digest is None)
        if result.returncode != 0 or missing:
            state["failed"] = (
                f"planetsplitter did not build the database (exit {result.returncode}"
                f"{', missing ' + ', '.join(missing) if missing else ''}): "
                f"{_tail(result.stderr or result.stdout)}"
            )
            scratch = self._scratch("; ")
            return self.ledger.fail(key, f"Routino database not built: {state['failed']}{scratch}")
        for name, digest in digests.items():
            assert digest is not None
            state[name] = digest
        return _outcome(
            f"built the Routino database ({len(DB_FILES)} files, staged)", self.staging.who()
        )

    def _install(
        self,
        sources: Sequence[Source],
        out: Path,
        key: str,
        state: dict[str, str],
        writer: PrefixWriter,
    ) -> str:
        if "failed" in state or not all(name in state for name in DB_FILES):
            return "skipped: the Routino database was not built"
        failure = self._publish(sources, out, state, writer)
        scratch = self._scratch("")
        if failure is not None:
            return self.ledger.fail(key, f"{failure}{'; ' + scratch if scratch else ''}")
        if scratch:
            return self.ledger.fail(
                key, f"installed the Routino database under {out}, but {scratch}"
            )
        return f"installed the Routino database under {out}; cleared {self.work}"

    def _publish(
        self,
        sources: Sequence[Source],
        out: Path,
        state: dict[str, str],
        writer: PrefixWriter,
    ) -> str | None:
        """Install the four files and the record, all or none; why not, or None."""
        work = self.work
        temporaries = [out / f"{name}{NEW}" for name in DB_FILES]
        try:
            try:
                for name, temporary in zip(DB_FILES, temporaries, strict=True):
                    self.staging.publish(work / name, temporary, digest=state[name], writer=writer)
            except (BackendError, OSError) as exc:
                writer.remove(temporaries)
                return f"Routino database not installed, the previous one left as it was: {exc}"
            try:
                writer.remove([out / RECORD])
                for name, temporary in zip(DB_FILES, temporaries, strict=True):
                    _rename(writer, temporary, out / name)
                writer.write_text(out / RECORD, record_of(sources))
            except (BackendError, OSError) as exc:
                writer.remove([*temporaries, *(out / name for name in DB_FILES), out / RECORD])
                return (
                    f"Routino database not installed, and removed rather than left "
                    f"mixed; the next run rebuilds it: {exc}"
                )
        except (BackendError, OSError) as exc:
            return f"Routino database not installed: {exc}"
        return None


def _rename(writer: PrefixWriter, source: Path, dest: Path) -> None:
    """Rename *source* over *dest* within one directory, escalated as the
    writer is. :class:`PrefixWriter` publishes, writes and removes, and has no
    rename of its own."""
    if writer.direct:
        os.replace(source, dest)
        return
    if writer.runner is None:
        raise BackendError(
            f"Install {dest}: the destination needs root and no runner was supplied "
            f"to escalate the step"
        )
    result = writer.runner.run(
        Command(
            argv=("mv", "-f", "-T", "--", str(source), str(dest)),
            description=f"Install {dest}",
            requires_root=True,
        )
    )
    if not result.ok:
        raise BackendError(f"Install {dest} failed: {result.stderr.strip()[:300]}")
