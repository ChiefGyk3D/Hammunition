# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The regions backend: the operator's OpenStreetMap regions.  D-057.

The regions come from station config, resolved to dated Geofabrik files by
:func:`hammunition.geofabrik.resolve` before this backend is built -- the
resolution needs the network and the plan must print it before anything is
confirmed. Each region is fetched into the shared cache and verified by a
pinned sha256 where the catalog carries one, else by Geofabrik's MD5; the
step's description says which, every time.

Installed as ``<prefix>/share/hammunition/data/<unit>/<slug>.osm.pbf`` with
a ``<slug>.osm.pbf.source`` sidecar holding the snapshot, which is how a
re-run knows the region is current and how ``update`` reports a newer one.
The copy into the prefix is re-verified on the way in, without following a
symlink (:class:`~hammunition.backends.verified.PrefixWriter`). A
``.osm.pbf`` in that directory whose region is no longer in station config
is removed on the next install, as its own disclosed step; one the plan
kept because it could not check for a newer map (offline) is not. After a
region is installed at a new snapshot, its older cached snapshots are
deleted, disclosed by name.

**One region failing does not stop the others** (spec §8). A download that
does not verify, or an install that cannot be done, is recorded in the
:class:`MapLedger` and that region's later steps are skipped; the rest
install and convert. The ledger's own step, last in the transaction, then
fails it by name -- a partial map install is never reported as a success.

Nothing is derived from a region string except its validated slug.
"""

from __future__ import annotations

import os
import re
import shutil
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path

from ..fetch import Fetcher
from ..geofabrik import RegionFile
from ..manifest.schema import PackageManifest, RegionalDataInstall, RemoteArtifact
from .base import Action, BackendError, Command, CommandRunner
from .data import human_size
from .source import needs_root_for
from .verified import PrefixWriter

MIB = 1024 * 1024
PBF = ".osm.pbf"
SOURCE = ".source"

#: Navit's converted map, relative to its ``.osm.pbf``: Canada's 6.1 GB
#: became a 4.7 GB ``.bin`` on the field laptop. One region, so the plan
#: calls it an estimate (:data:`ESTIMATE`).
BIN_FACTOR = 0.8
#: maptool's scratch files (``*.tmp``, ``coords.tmp``) in its working
#: directory while it converts, relative to the input: Canada wrote more
#: than 12 GB of them. Freed when it finishes, but needed while it runs.
SCRATCH_FACTOR = 2
ESTIMATE = "estimate, measured on one region"


def bin_estimate(size: int) -> int:
    return round(size * BIN_FACTOR)


def data_root(prefix: Path) -> Path:
    """The namespace ``uninstall`` owns (D-049); nothing is written outside it."""
    return prefix / "share" / "hammunition" / "data"


def installed_snapshot(path: Path) -> str | None:
    """The snapshot recorded beside *path*, or None when there is no record."""
    sidecar = path.with_name(path.name + SOURCE)
    try:
        return sidecar.read_text().strip() or None
    except OSError:
        return None


def installed_slugs(directory: Path) -> dict[str, str]:
    """slug -> installed snapshot for every ``<slug>.osm.pbf`` under
    *directory* that carries a ``.source`` sidecar.

    Read by ``update`` to report regions behind the pin list (D-053):
    nothing is fetched and nothing is probed, only what is on disk now.
    """
    if not directory.is_dir():
        return {}
    out: dict[str, str] = {}
    for path in sorted(directory.glob(f"*{PBF}")):
        snapshot = installed_snapshot(path)
        if snapshot is not None:
            out[path.name[: -len(PBF)]] = snapshot
    return out


@dataclass
class MapLedger:
    """Which regions failed this run, shared by the regions and derived backends.

    Keyed by slug. A region recorded here has its later steps skipped --
    no install of a download that did not verify, no conversion of a region
    that did not install -- and :meth:`check`, run last, fails the
    transaction naming every one.
    """

    failed: dict[str, str] = field(default_factory=dict)

    def fail(self, slug: str, message: str) -> str:
        self.failed.setdefault(slug, message)
        return f"FAILED, the other regions continue: {message}"

    def check(self) -> str:
        if not self.failed:
            return "every map region installed"
        lines = "\n".join(f"  {message}" for message in self.failed.values())
        raise BackendError(
            f"{len(self.failed)} map region(s) did not install; every other region "
            f"did, and Navit's config lists only the maps that exist:\n{lines}"
        )

    def step(self) -> Action:
        return Action(
            kind="check-map-regions",
            description="Fail the transaction by name if any map region did not install",
            detail="map regions",
            perform=self.check,
        )


def prefix_writer(
    prefix: Path, privileged: bool | None, runner: CommandRunner | None, euid: int | None
) -> PrefixWriter:
    return PrefixWriter(
        privileged=needs_root_for(prefix) if privileged is None else privileged,
        runner=runner,
        euid=euid,
    )


def _remove(writer: PrefixWriter, path: Path) -> str:
    writer.remove([path, path.with_name(path.name + SOURCE)])
    return f"removed {path}"


def removal_steps(
    directory: Path, suffix: str, keep: set[str], writer: PrefixWriter
) -> list[Action | Command]:
    """A ``remove-data`` step for each ``<slug><suffix>`` in *directory* not in *keep*."""
    if not directory.is_dir():
        return []
    steps: list[Action | Command] = []
    for path in sorted(directory.glob(f"*{suffix}")):
        slug = path.name[: -len(suffix)]
        if slug in keep or not path.is_file():
            continue
        steps.append(
            Action(
                kind="remove-data",
                description=f"Remove {slug}: no longer in your map regions",
                # The path, verbatim: uninstall's attribution replay reads a
                # removed path back and stops attributing it.
                detail=str(path),
                perform=partial(_remove, writer, path),
                requires_root=writer.privileged,
            )
        )
    return steps


def disk_needs(
    downloads: Sequence[RegionFile],
    conversions: Sequence[RegionFile],
    *,
    cache: Path,
    staging: Path,
    prefix: Path,
) -> dict[Path, int]:
    """Bytes each location needs: each download once in the fetch cache and
    once under the prefix; each conversion's scratch
    (:data:`SCRATCH_FACTOR`) and staged ``.bin`` (:data:`BIN_FACTOR`) in the
    staging directory, and its ``.bin`` again under the prefix. A region
    already downloaded but not yet converted counts as a conversion only."""
    fetched = sum(f.size for f in downloads)
    converted = sum(f.size for f in conversions)
    bins = sum(bin_estimate(f.size) for f in conversions)
    needs: dict[Path, int] = {}
    for where, amount in (
        (cache, fetched),
        (staging, SCRATCH_FACTOR * converted + bins),
        (prefix, fetched + bins),
    ):
        needs[where] = needs.get(where, 0) + amount
    return needs


def _existing(path: Path) -> Path:
    for candidate in (path, *path.parents):
        if candidate.exists():
            return candidate
    return Path("/")  # pragma: no cover - "/" always exists


def free_bytes_at(path: Path) -> int:
    """Free space on the file system that *path* is, or will be, created on."""
    return shutil.disk_usage(_existing(path)).free


def device_at(path: Path) -> int:
    """The file system *path* is, or will be, created on."""
    return os.stat(_existing(path)).st_dev


def disk_shortfall(
    needs: Mapping[Path, int],
    *,
    free_at: Callable[[Path], int] = free_bytes_at,
    device_of: Callable[[Path], int] = device_at,
) -> str | None:
    """A refusal naming both numbers for every file system short of space, else None.

    Locations on one file system are summed against that file system's one
    free-space figure; the cache and the prefix are often the same disk.
    """
    by_device: dict[int, tuple[list[Path], int]] = {}
    for path, amount in needs.items():
        paths, total = by_device.get(device_of(path), ([], 0))
        by_device[device_of(path)] = ([*paths, path], total + amount)
    short: list[str] = []
    for paths, need in by_device.values():
        free = free_at(paths[0])
        if free < need:
            where = ", ".join(str(p) for p in paths)
            short.append(
                f"{where}: an estimated {human_size(need)} ({need} bytes) is needed and "
                f"{human_size(free)} ({free} bytes) is free"
            )
    if not short:
        return None
    return (
        "not enough disk space for the map regions (the downloads, their cached copy, "
        f"maptool's scratch at {SCRATCH_FACTOR}x and Navit's maps at {BIN_FACTOR}x the "
        f"input -- an {ESTIMATE}):\n  " + "\n  ".join(short)
    )


@dataclass(frozen=True)
class KeptRegion:
    """An installed region the plan could not check for a newer map (offline).

    Kept as installed: its files are neither replaced nor removed."""

    region: str
    slug: str
    snapshot: str | None
    reason: str


@dataclass(frozen=True)
class MapDisclosure:
    """What the plan says about the station's regions, split the way it happens."""

    fetch: Sequence[RegionFile]
    """Will be downloaded and installed this run."""
    current: Sequence[RegionFile]
    """Already installed at the resolved snapshot; nothing happens to them."""
    kept: Sequence[KeptRegion]
    """Could not be checked; the installed copy stays."""
    convert: Sequence[RegionFile] = ()
    """Converted for Navit this run: newly downloaded, or installed but not yet converted."""


@dataclass(frozen=True)
class MapResolution:
    """The station's regions, resolved at plan time."""

    files: tuple[RegionFile, ...] = ()
    kept: tuple[KeptRegion, ...] = ()
    notes: tuple[str, ...] = ()

    def disclosure(
        self, pending: Sequence[RegionFile], conversions: Sequence[RegionFile] = ()
    ) -> MapDisclosure:
        waiting = {f.slug for f in pending}
        return MapDisclosure(
            fetch=tuple(f for f in self.files if f.slug in waiting),
            current=tuple(f for f in self.files if f.slug not in waiting),
            kept=self.kept,
            convert=tuple(conversions),
        )


def region_lines(files: Sequence[RegionFile]) -> list[str]:
    """One line per region for the plan: region, snapshot, size, how it is verified.

    Printed to the operator's own terminal. The regions are station data and
    this is the only place they are shown.
    """
    width = max((len(f.region) for f in files), default=0)
    return [
        f"    {f.region:<{width}}  {f.snapshot}  {human_size(f.size):>9}  {f.verified_by}"
        for f in files
    ]


@dataclass(frozen=True)
class RegionsBackend:
    """Turns an ``osm-regions`` block and the resolved regions into steps."""

    fetcher: Fetcher
    prefix: Path
    files: Sequence[RegionFile]
    keep: frozenset[str] = frozenset()
    """Slugs kept as installed because a newer map could not be checked for."""
    ledger: MapLedger = field(default_factory=MapLedger)
    runner: CommandRunner | None = None
    euid: int | None = None
    privileged: bool | None = None
    """Whether the prefix needs root; None decides from the path."""
    method = "osm-regions"

    @property
    def writer(self) -> PrefixWriter:
        return prefix_writer(self.prefix, self.privileged, self.runner, self.euid)

    def data_dir(self, manifest: PackageManifest) -> Path:
        return data_root(self.prefix) / manifest.name

    def pending(self, manifest: PackageManifest) -> list[RegionFile]:
        """Regions not already installed at their resolved snapshot and size."""
        out = self.data_dir(manifest)
        return [f for f in self.files if not self._current(out / f"{f.slug}{PBF}", f)]

    @staticmethod
    def _current(dest: Path, region: RegionFile) -> bool:
        return (
            dest.is_file()
            and dest.stat().st_size == region.size
            and installed_snapshot(dest) == region.snapshot
        )

    def cache_path(self, region: RegionFile) -> Path:
        if region.sha256 is not None:
            return self.fetcher.path_for(RemoteArtifact(url=region.url, sha256=region.sha256))
        return self.fetcher.md5_path_for(region.url, region.md5 or "")

    def stale_cache(self, region: RegionFile) -> list[Path]:
        """Older cached snapshots of *region*: same URL-derived name, another date.

        The cache names a file by its basename only, so two regions with one
        basename (a US state and a country) look alike here; every file a
        region of this run needs is kept whatever it looks like, and the rest
        is a cache -- deleting one re-downloads it, nothing more.
        """
        cache = self.fetcher.cache_dir
        if not cache.is_dir():
            return []
        current = self.cache_path(region).name
        stem = re.sub(r"-\d{6}\.osm\.pbf$", "", current.split("-", 1)[1])
        if current.startswith("md5-"):
            stem = stem.split("-", 1)[1]
        pattern = re.compile(
            rf"(?:[0-9a-f]{{64}}|md5-[0-9a-f]{{32}})-{re.escape(stem)}-\d{{6}}\.osm\.pbf"
        )
        needed = {self.cache_path(f).name for f in self.files}
        return sorted(
            p
            for p in cache.iterdir()
            if pattern.fullmatch(p.name) and p.name not in needed and p.is_file()
        )

    def steps(
        self, manifest: PackageManifest, block: RegionalDataInstall
    ) -> list[Action | Command]:
        out = self.data_dir(manifest)
        writer = self.writer
        steps: list[Action | Command] = []
        for region in self.files:
            dest = out / f"{region.slug}{PBF}"
            if self._current(dest, region):
                continue
            fetched: dict[str, Path] = {}
            digest = (
                f"sha256 {region.sha256[:12]}…"
                if region.sha256
                else f"md5 {(region.md5 or '')[:12]}…"
            )
            steps.append(
                Action(
                    kind="fetch",
                    description=(
                        f"Fetch map region {region.region} ({region.snapshot}, "
                        f"{human_size(region.size)}, {block.licence}) — {region.verified_by}"
                    ),
                    detail=f"{region.url} ({digest}, {region.size} bytes)",
                    perform=partial(self._fetch, region, fetched),
                )
            )
            steps.append(
                Action(
                    kind="install-data",
                    description=f"Install map region {region.region} ({region.snapshot})",
                    # The destination, verbatim, for uninstall's attribution replay.
                    detail=str(dest),
                    perform=partial(self._install, region, fetched, dest, writer),
                    requires_root=writer.privileged,
                )
            )
            stale = self.stale_cache(region)
            if stale:
                steps.append(
                    Action(
                        kind="prune-cache",
                        description=(
                            f"Delete older cached snapshots of {region.region} once "
                            f"{region.snapshot} is installed"
                        ),
                        detail=", ".join(str(p) for p in stale),
                        perform=partial(self._prune, region, stale),
                    )
                )
        keep = {f.slug for f in self.files} | set(self.keep)
        steps.extend(removal_steps(out, PBF, keep, writer))
        return steps

    def _fetch(self, region: RegionFile, fetched: dict[str, Path]) -> str:
        try:
            if region.sha256 is not None:
                # The cap is raised to the declared size plus a margin, never
                # removed: California is 1.33 GB against the fetcher's 512 MB.
                result = self.fetcher.fetch(
                    RemoteArtifact(url=region.url, sha256=region.sha256),
                    max_bytes=region.size + MIB,
                )
                how = f"sha256 {result.sha256[:12]}… verified against the pin"
            elif region.md5 is not None:
                result = self.fetcher.fetch_md5(region.url, region.md5, expected_size=region.size)
                how = f"md5 {region.md5[:12]}… matched Geofabrik's (not pinned)"
            else:  # pragma: no cover - geofabrik.resolve always sets one
                raise BackendError(f"{region.url}: neither a sha256 pin nor an MD5 to verify it by")
            if result.size != region.size:
                raise BackendError(
                    f"{region.url}: {region.size} bytes were expected and {result.size} "
                    f"arrived; the digest matched, so the size the plan printed was wrong"
                )
        except (BackendError, OSError) as exc:
            return self.ledger.fail(region.slug, f"{region.region}: {exc}")
        fetched["path"] = result.path
        where = "cached" if result.from_cache else "downloaded"
        return f"{where} {result.size} bytes, {how}"

    def _install(
        self, region: RegionFile, fetched: dict[str, Path], dest: Path, writer: PrefixWriter
    ) -> str:
        if region.slug in self.ledger.failed:
            return f"skipped: {region.region} did not verify"
        path = fetched.get("path")
        if path is None:  # pragma: no cover
            return self.ledger.fail(region.slug, f"{region.region}: not fetched before install")
        algorithm, digest = (
            ("sha256", region.sha256) if region.sha256 else ("md5", region.md5 or "")
        )
        try:
            # Copy, never move: the cache is content-addressed and shared.
            writer.install_verified(path, dest, algorithm=algorithm, digest=digest)
            writer.write_text(dest.with_name(dest.name + SOURCE), f"{region.snapshot}\n")
        except (BackendError, OSError) as exc:
            return self.ledger.fail(region.slug, f"{region.region}: {exc}")
        return f"installed {dest} ({human_size(region.size)}, snapshot {region.snapshot})"

    def _prune(self, region: RegionFile, stale: Sequence[Path]) -> str:
        if region.slug in self.ledger.failed:
            return f"kept: {region.region} did not install, so its older copies stay"
        for path in stale:
            path.unlink(missing_ok=True)
        return f"deleted {len(stale)} older cached snapshot(s)"
