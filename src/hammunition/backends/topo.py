# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The topo-quads backend: USGS US Topo map sheets for the station's
regions.  D-068.

The sheets come from :func:`hammunition.topo_plan.resolve_topo`, run before
the plan prints, because each sheet's size and how it is verified are the
disclosure. Each is fetched into the shared cache, checked against the S3
ETag the carried index lists and the bucket confirmed at plan time
(:meth:`hammunition.fetch.Fetcher.fetch_etag`), installed as
``<data>/<unit>/<stem>_<date>.tif`` re-verified on the way in against the
sha256 measured as it arrived, and its cached copy deleted: a sheet's
object never changes (a new edition is a new name), so a second copy is
only disk.

``<data>/<unit>/<slug>.quads`` records which sheets a region needs -- the
answer from its outline, kept so a later plan needs no network to know it.
A sheet no region needs any more is removed, and so is the record of a
region no longer set; a kept region's (offline) are not.

One sheet failing does not stop the others: it is recorded in D-061's
:class:`~hammunition.backends.terrain.TerrainLedger`, which fails the
transaction naming it at the end. Nothing here is ever executed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import partial
from pathlib import Path

from ..fetch import Fetcher
from ..manifest.schema import PackageManifest, TopoQuadsInstall
from ..ustopo import PATH, Quad
from .base import Action, BackendError, Command, CommandRunner
from .data import human_size
from .regions import data_root, prefix_writer, removal_steps
from .terrain import TerrainLedger
from .verified import PrefixWriter

TIF = ".tif"
QUADS = ".quads"
_HEADER = "# US Topo quads: "


def quad_key(name: str) -> str:
    """The ledger key of a sheet: its name, which no slug or tile can be."""
    return f"quad {name}"


def no_quads_line(region: str) -> str:
    """How a region no US Topo sheet covers is named, in the plan and its step."""
    return f"no US Topo quad covers {region} (US Topo covers the United States and its territories)"


@dataclass(frozen=True)
class RegionQuads:
    """The sheets one region needs, by index path (``<ST>/<stem>_<date>``)."""

    region: str
    slug: str
    quads: tuple[str, ...]


def render_record(entry: RegionQuads) -> str:
    return f"{_HEADER}{len(entry.quads)}\n" + "".join(f"{path}\n" for path in entry.quads)


def read_record(path: Path, region: str, slug: str) -> RegionQuads | None:
    """A region's recorded sheets, or None when there is no readable record.

    A region no sheet covers records a header and nothing else: a complete
    record, or its outline would be fetched again on every plan. A record
    whose count does not match its lines, or that names something not a
    sheet path, is not trusted."""
    try:
        text = path.read_text()
    except OSError:
        return None
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines or not lines[0].startswith(_HEADER):
        return None
    count = lines[0][len(_HEADER) :]
    names = lines[1:]
    if not count.isdigit() or int(count) != len(names):
        return None
    if any(PATH.fullmatch(name) is None for name in names):
        return None
    return RegionQuads(region, slug, tuple(sorted(names)))


@dataclass(frozen=True)
class TopoResolution:
    """The station's US Topo sheets, resolved at plan time."""

    regions: tuple[RegionQuads, ...] = ()
    fetch: tuple[Quad, ...] = ()
    """Sheets not installed yet: downloaded this run."""
    current: tuple[Quad, ...] = ()
    """Sheets already installed; nothing happens to them."""

    @property
    def quads(self) -> tuple[Quad, ...]:
        """Every sheet any region needs, by path."""
        found = {q.path: q for q in (*self.fetch, *self.current)}
        return tuple(found[path] for path in sorted(found))


@dataclass(frozen=True)
class TopoQuadsBackend:
    """Turns a ``topo-quads`` block and the resolved sheets into steps."""

    fetcher: Fetcher
    prefix: Path
    resolution: TopoResolution
    keep: frozenset[str] = frozenset()
    """Slugs kept as installed because a newer map could not be checked for."""
    ledger: TerrainLedger = field(default_factory=TerrainLedger)
    runner: CommandRunner | None = None
    euid: int | None = None
    privileged: bool | None = None
    method = "topo-quads"

    @property
    def writer(self) -> PrefixWriter:
        return prefix_writer(self.prefix, self.privileged, self.runner, self.euid)

    def data_dir(self, manifest: PackageManifest) -> Path:
        return data_root(self.prefix) / manifest.name

    def steps(self, manifest: PackageManifest, block: TopoQuadsInstall) -> list[Action | Command]:
        out = self.data_dir(manifest)
        writer = self.writer
        steps: list[Action | Command] = []
        for quad in self.resolution.fetch:
            fetched: dict[str, str | Path] = {}
            steps.append(
                Action(
                    kind="fetch",
                    description=(
                        f"Fetch US Topo quad {quad.name} ({human_size(quad.size)}, "
                        f"{block.licence}) — {quad.verified_by}"
                    ),
                    detail=f"{quad.url} (ETag {quad.etag}, {quad.size} bytes)",
                    perform=partial(self._fetch, quad, fetched),
                )
            )
            dest = out / f"{quad.name}{TIF}"
            steps.append(
                Action(
                    kind="install-data",
                    description=(
                        f"Install US Topo quad {quad.name}, then delete its cached copy "
                        f"{self.fetcher.etag_path_for(quad.url, quad.etag)}"
                    ),
                    # The destination, verbatim, for uninstall's attribution replay.
                    detail=str(dest),
                    perform=partial(self._install, quad, fetched, dest, writer),
                    requires_root=writer.privileged,
                )
            )
        for entry in self.resolution.regions:
            record = out / f"{entry.slug}{QUADS}"
            if read_record(record, entry.region, entry.slug) == entry:
                continue
            description = (
                f"Record that {no_quads_line(entry.region)}, so nothing is installed for it"
                if not entry.quads
                else f"Record the {len(entry.quads)} US Topo quad(s) {entry.region} needs, "
                f"so a later plan knows them offline"
            )
            steps.append(
                Action(
                    kind="install-data",
                    description=description,
                    detail=str(record),
                    perform=partial(self._record, entry, record, writer),
                    requires_root=writer.privileged,
                )
            )
        slugs = {entry.slug for entry in self.resolution.regions} | set(self.keep)
        steps.extend(removal_steps(out, QUADS, slugs, writer))
        steps.extend(removal_steps(out, TIF, {q.name for q in self.resolution.quads}, writer))
        return steps

    @staticmethod
    def _record(entry: RegionQuads, record: Path, writer: PrefixWriter) -> str:
        writer.write_text(record, render_record(entry))
        if not entry.quads:
            return f"wrote {record}; {no_quads_line(entry.region)}"
        return f"wrote {record}"

    def _fetch(self, quad: Quad, fetched: dict[str, str | Path]) -> str:
        try:
            result = self.fetcher.fetch_etag(quad.url, quad.etag, expected_size=quad.size)
        except (BackendError, OSError) as exc:
            return self.ledger.fail(quad_key(quad.name), f"{quad.name}: {exc}")
        fetched["path"] = result.path
        fetched["sha256"] = result.sha256
        where = "cached" if result.from_cache else "downloaded"
        return (
            f"{where} {result.size} bytes, ETag {quad.etag} reproduced "
            f"(the publisher's, not pinned)"
        )

    def _install(
        self, quad: Quad, fetched: dict[str, str | Path], dest: Path, writer: PrefixWriter
    ) -> str:
        path, sha256 = fetched.get("path"), fetched.get("sha256")
        if quad_key(quad.name) in self.ledger.failed or not isinstance(path, Path):
            return f"skipped: {quad.name} did not verify"
        try:
            # Re-verified on the way in against the sha256 taken as the bytes
            # arrived, after the ETag matched: the cache is the operator's.
            writer.install_verified(path, dest, algorithm="sha256", digest=str(sha256))
        except (BackendError, OSError) as exc:
            return self.ledger.fail(quad_key(quad.name), f"{quad.name}: {exc}")
        path.unlink(missing_ok=True)
        return f"installed {dest} ({human_size(quad.size)}); deleted the cached copy"
