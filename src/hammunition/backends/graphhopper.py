# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The ``graphhopper-import`` converter: one GraphHopper routing graph over
every region.  D-076.

GraphHopper routes over a graph it builds itself from an ``.osm.pbf`` with
``java -jar graphhopper-web-<version>.jar import config.yml``. One graph over
every region, never one per region, for the reason BRouter's routing files
are one set (D-063): a route must cross from one region into the next, and
``import`` reads one file, so two regions or more are merged first with
``osmium merge``. Built as the operator in ``graphhopper.work`` under the
staging directory, under one lock held by every phase and every clear:

1. check the jar and each region's file, then empty the working directory;
2. ``osmium merge`` the regions into ``merged.osm.pbf`` when there are two
   or more;
3. write ``config.yml`` (:func:`hammunition.graphhopper.import_config`, the
   engine's text, checked by its digest after the operator's ``sh`` wrote
   it), then run the import; the graph must hold ``properties``, and every
   file it wrote is digested (D-031: the output, not the exit status);
4. publish every graph file under a temporary name, rename them in, remove
   files no longer built, and write the record: all or none.

``<data>/graphhopper-graph/graph.source`` records the regions and their
snapshots, the jar (as the plan pins it, so a GraphHopper bumped in the same
run rebuilds the graph), the profiles, each graph file and, last,
:data:`~hammunition.graphhopper.CONVERTER`. The graph is current when that
record, less its ``file`` lines, is what this run would write and every file
named in it exists.
"""

from __future__ import annotations

import hashlib
import shlex
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path

from ..geofabrik import RegionFile
from ..graphhopper import (
    PROPERTIES,
    RECORD,
    find_jar,
    import_argv,
    import_config,
    parse_record,
    render_record,
    without_files,
)
from ..manifest.schema import DerivedDataInstall, PackageManifest
from .base import Action, BackendError, Command, CommandRunner
from .data import human_size
from .regions import PBF, MapLedger, data_root, installed_snapshot, prefix_writer
from .routino import _rename
from .source import tree_destination
from .staging import REFUSED, Staging
from .verified import PrefixWriter

WORKDIR = "graphhopper"
MERGED = "merged.osm.pbf"
CONFIG = "config.yml"
GRAPH = "graph"
#: The suffix a graph file is published under before the set is renamed in.
NEW = ".new"
MEASURED = "measured on one region"
#: The graph against the downloads it was built from: 78 MB from Delaware's
#: 22.1 MB (the routing spike, 2026-09-29), 3.5x, rounded up to 3.7 in case
#: the spike's MB were MiB.
FACTOR = 3.7
#: The import's memory, from the same single measurement.
MEMORY = (
    "about 1.2 GB of memory on Delaware's 22.1 MB, the one region measured; "
    "Java's heap is capped at 4 GB"
)
GRAPH_NOTE = (
    f"the route graph at {FACTOR}x all the downloads together ({MEASURED}), twice over "
    f"while it builds and installs"
)
#: How the operator's ``find`` marks each file it lists.
_FOUND = "found:"


def estimate(total: int) -> int:
    return round(total * FACTOR)


def _tail(text: str) -> str:
    return text.strip()[-300:]


def _who(who: str) -> str:
    return f", {who}" if who else ""


@dataclass
class GraphLedger:
    """Whether the route graph failed this run."""

    failed: dict[str, str] = field(default_factory=dict)

    def fail(self, key: str, message: str) -> str:
        self.failed.setdefault(key, message)
        return f"FAILED, the rest continues: {message}"

    def check(self) -> str:
        if not self.failed:
            return "the route graph installed"
        lines = "\n".join(f"  {message}" for message in self.failed.values())
        raise BackendError(f"the route graph did not install; everything else did:\n{lines}")

    def step(self) -> Action:
        return Action(
            kind="check-route-graph",
            description="Fail the transaction by name if the route graph did not install",
            detail="route graph",
            perform=self.check,
        )


@dataclass(frozen=True)
class Source:
    """One region the graph is built from."""

    region: str
    slug: str
    snapshot: str | None
    pbf: Path
    size: int

    @property
    def line(self) -> str:
        return f"{self.slug} {self.snapshot or '-'}"


@dataclass(frozen=True)
class GraphConverter:
    """Turns a ``derived`` block with ``converter: graphhopper-import`` into steps."""

    prefix: Path
    files: Sequence[RegionFile]
    staging: Staging
    keep: frozenset[str] = frozenset()
    """Slugs kept as installed because a newer map could not be checked for."""
    regions: MapLedger = field(default_factory=MapLedger)
    """Piece 1's ledger, read only: a region that did not install is not built."""
    ledger: GraphLedger = field(default_factory=GraphLedger)
    runner: CommandRunner | None = None
    euid: int | None = None
    privileged: bool | None = None
    jar: str | None = None
    """The jar the plan installs (the program unit's tree marker), so a
    GraphHopper bumped in this run rebuilds the graph in this run."""

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

    def _tree(self, block: DerivedDataInstall) -> Path:
        assert block.program is not None  # the schema requires it
        return tree_destination(self.prefix, block.program)

    def sources(self, block: DerivedDataInstall) -> list[Source]:
        """Every region the graph covers: this run's, then the kept ones."""
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
        """The regions the graph is rebuilt over this run, or none when it is current."""
        sources = self.sources(block)
        out = self.data_dir(manifest)
        try:
            recorded = (out / RECORD).read_text()
        except OSError:
            recorded = None
        on_disk = find_jar(self._tree(block))
        jar = self.jar or (on_disk.name if on_disk is not None else None)
        if sources and recorded is not None and jar is not None:
            expected = render_record([s.line for s in sources], jar, ())
            record = parse_record(recorded)
            if (
                without_files(recorded) == expected
                and record is not None
                and PROPERTIES in record.files
                and all((out / name).is_file() for name in record.files)
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
        steps: list[Action | Command] = [
            Action(
                kind="convert",
                description=(
                    f"Prepare GraphHopper's route graph over {len(sources)} region(s), as the "
                    f"operator, in {work}: check its jar ({tree}/graphhopper-web-*.jar) and the "
                    f"regions, then empty the working directory. The graph is built here from "
                    f"your own regions; nothing is downloaded"
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
                        f"Merge the {len(sources)} regions into one input for GraphHopper, "
                        f"as the operator, in {work}: {shlex.join(argv)}"
                    ),
                    detail=str(work / MERGED),
                    perform=partial(self._merge, argv, key, state),
                )
            )
        shown = shlex.join(import_argv(tree / "graphhopper-web-*.jar", work / CONFIG))
        steps.append(
            Action(
                kind="convert",
                description=(
                    f"Build GraphHopper's route graph (car, bike, foot and hike, the hike "
                    f"profile reading trail difficulty, sac_scale), as the operator, in "
                    f"{work}: write {work / CONFIG}, then {shown}; the graph about "
                    f"{human_size(estimate(total))} ({FACTOR}x the downloads together, "
                    f"{MEASURED}), built in the working directory first; {MEMORY}"
                ),
                detail=str(work / GRAPH),
                perform=partial(self._import, sources, block, key, state),
            )
        )
        steps.append(
            Action(
                kind="install-data",
                description=(
                    f"Install GraphHopper's route graph and its record under {out}, remove "
                    f"any file no longer built, then clear the scratch {work}"
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
        return self.ledger.fail(
            key, f"GraphHopper's route graph not built: {why}{self._scratch('; ')}"
        )

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

    def _begin(
        self, sources: Sequence[Source], block: DerivedDataInstall, key: str, state: dict[str, str]
    ) -> str:
        for source in sources:
            if source.slug in self.regions.failed:
                # The regions ledger reports the region; nothing here ran.
                state["failed"] = (
                    f"{source.region} did not install, and the route graph is built over "
                    f"every region or none; the installed one is left as it was"
                )
                return f"skipped: {state['failed']}"
        missing: list[str] = []
        tree = self._tree(block)
        jar = find_jar(tree)
        if jar is None:
            missing.append(f"exactly one graphhopper-web-*.jar in {tree}")
        missing.extend(f"{s.region}: {s.pbf}" for s in sources if not s.pbf.is_file())
        if missing:
            state["failed"] = "not installed: " + "; ".join(missing)
            return self.ledger.fail(key, f"GraphHopper's route graph not built: {state['failed']}")
        work = self.work
        refusal = self.staging.prepare(work)
        if refusal is not None:
            state["failed"] = refusal
            return self.ledger.fail(key, f"GraphHopper's route graph not built: {refusal}")
        cleared = self.staging.clear(work, lock=self.lock)
        if cleared.returncode != 0:
            # 125: another conversion holds the directory; nothing in it is deleted.
            state["failed"] = (
                f"the build was not started: {_tail(cleared.stderr) or 'refused'}"
                if cleared.returncode == REFUSED
                else f"could not clear {work}: {_tail(cleared.stderr) or 'no reason given'}"
            )
            return self.ledger.fail(key, f"GraphHopper's route graph not built: {state['failed']}")
        assert jar is not None
        state["jar"] = str(jar)
        state["input"] = str(sources[0].pbf)
        return f"prepared {work} for GraphHopper's build{_who(self.staging.who())}"

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

    def _listing(self, directory: Path) -> list[str] | None:
        """Non-empty regular files in *directory*, listed by the operator's
        own ``find``; None when the listing itself failed."""
        found = self._run(
            [
                "find",
                str(directory),
                "-maxdepth",
                "1",
                "-type",
                "f",
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

    def _import(
        self,
        sources: Sequence[Source],
        block: DerivedDataInstall,
        key: str,
        state: dict[str, str],
    ) -> str:
        if "failed" in state:
            return f"skipped: {state['failed']}"
        work = self.work
        config = work / CONFIG
        text = import_config(Path(state["input"]), work / GRAPH)
        wrote = self._run(["sh", "-c", 'printf "%s" "$1" > "$2"', "sh", text, str(config)])
        if (
            wrote.returncode != 0
            or self.staging.digest(config) != hashlib.sha256(text.encode("utf-8")).hexdigest()
        ):
            return self._fail(
                key,
                state,
                f"could not write {config} (exit {wrote.returncode}): "
                f"{_tail(wrote.stderr) or 'its content is not what was written'}",
            )
        result = self._run(import_argv(Path(state["jar"]), config))
        if result.returncode == REFUSED:
            return self._fail(key, state, f"the import was not started: {_tail(result.stderr)}")
        written = self._listing(work / GRAPH)
        if result.returncode != 0 or not written or PROPERTIES not in written:
            what = "no graph" if not written else f"a graph with no {PROPERTIES}"
            return self._fail(
                key,
                state,
                f"GraphHopper's import wrote {what} (exit {result.returncode}): "
                f"{_tail(result.stderr or result.stdout)}",
            )
        for name in written:
            digest = self.staging.digest(work / GRAPH / name)
            if digest is None:
                return self._fail(key, state, f"the graph's {name} could not be read back")
            state[f"file:{name}"] = digest
        return (
            f"built GraphHopper's route graph over {len(sources)} region(s), "
            f"{len(written)} file(s), staged{_who(self.staging.who())}"
        )

    def _install(
        self,
        sources: Sequence[Source],
        out: Path,
        key: str,
        state: dict[str, str],
        writer: PrefixWriter,
    ) -> str:
        built = {k.split(":", 1)[1]: v for k, v in state.items() if k.startswith("file:")}
        if "failed" in state or not built:
            return "skipped: GraphHopper's route graph was not built"
        record = render_record(
            [s.line for s in sources], self.jar or Path(state["jar"]).name, sorted(built)
        )
        failure = self._publish(built, out, record, writer)
        scratch = self._scratch("")
        if failure is not None:
            return self.ledger.fail(key, f"{failure}{'; ' + scratch if scratch else ''}")
        if scratch:
            return self.ledger.fail(
                key, f"installed GraphHopper's route graph under {out}, but {scratch}"
            )
        return f"installed GraphHopper's route graph ({len(built)} file(s)) under {out}; cleared {self.work}"

    def _publish(
        self, built: dict[str, str], out: Path, record: str, writer: PrefixWriter
    ) -> str | None:
        """Install every graph file and the record, all or none; why not, or None."""
        names = sorted(built)
        temporaries = [out / f"{name}{NEW}" for name in names]
        try:
            # Every other file in the graph's directory is the engine's own: an
            # older graph's, or a temporary a crashed publish left.
            stale = sorted(
                p for p in out.iterdir() if p.is_file() and p.name != RECORD and p.name not in built
            )
        except OSError:
            stale = []
        try:
            try:
                for name, temporary in zip(names, temporaries, strict=True):
                    self.staging.publish(
                        self.work / GRAPH / name, temporary, digest=built[name], writer=writer
                    )
            except (BackendError, OSError) as exc:
                writer.remove(temporaries)
                return (
                    f"GraphHopper's route graph not installed, the previous one left as it "
                    f"was: {exc}"
                )
            stale = [p for p in stale if p not in temporaries]
            try:
                writer.remove([out / RECORD])
                for name, temporary in zip(names, temporaries, strict=True):
                    _rename(writer, temporary, out / name)
                writer.remove(stale)
                writer.write_text(out / RECORD, record)
            except (BackendError, OSError) as exc:
                writer.remove([*temporaries, *(out / name for name in names), *stale, out / RECORD])
                return (
                    f"GraphHopper's route graph not installed, and removed rather than left "
                    f"mixed; the next run rebuilds it: {exc}"
                )
        except (BackendError, OSError) as exc:
            return f"GraphHopper's route graph not installed: {exc}"
        return None


__all__ = ["FACTOR", "GRAPH_NOTE", "GraphConverter", "GraphLedger", "estimate"]
