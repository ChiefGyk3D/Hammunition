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
A ``.osm.pbf`` in that directory whose region is no longer in station config
is removed on the next install, as its own disclosed step.

Nothing is derived from a region string except its validated slug.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from ..fetch import Fetcher
from ..geofabrik import RegionFile
from ..manifest.schema import PackageManifest, RegionalDataInstall, RemoteArtifact
from .base import Action, BackendError, Command
from .data import human_size
from .source import needs_root_for

MIB = 1024 * 1024
PBF = ".osm.pbf"
SOURCE = ".source"

#: Navit's converted maps, relative to the downloads. An estimate until the
#: ratio is measured on real regions (the plan's Task 10); the plan says so.
DERIVED_FACTOR = 2


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


def remove_with_sidecar(path: Path) -> str:
    """Unlink a data file and its snapshot sidecar. Missing is not an error."""
    path.unlink(missing_ok=True)
    path.with_name(path.name + SOURCE).unlink(missing_ok=True)
    return f"removed {path}"


def removal_steps(
    directory: Path, suffix: str, keep: set[str], *, requires_root: bool
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
                perform=partial(remove_with_sidecar, path),
                requires_root=requires_root,
            )
        )
    return steps


def estimated_bytes(files: Sequence[RegionFile]) -> int:
    """The downloads plus Navit's converted maps, at :data:`DERIVED_FACTOR`."""
    total = sum(f.size for f in files)
    return total + DERIVED_FACTOR * total


def disk_shortfall(files: Sequence[RegionFile], *, free: int) -> str | None:
    """A refusal naming both numbers when *free* is below the estimate, else None."""
    need = estimated_bytes(files)
    if free >= need:
        return None
    return (
        f"the map regions need an estimated {human_size(need)} ({need} bytes: the "
        f"downloads plus {DERIVED_FACTOR}x that for Navit's maps, an estimate until "
        f"measured) and {human_size(free)} ({free} bytes) is free"
    )


def region_lines(files: Sequence[RegionFile]) -> list[str]:
    """One line per region for the plan: region, snapshot, size, how it is verified.

    Printed to the operator's own terminal. The regions are station data and
    this is the only place they are shown.
    """
    width = max((len(f.region) for f in files), default=0)
    return [
        f"  {f.region:<{width}}  {f.snapshot}  {human_size(f.size):>9}  {f.verified_by}"
        for f in files
    ]


@dataclass(frozen=True)
class RegionsBackend:
    """Turns an ``osm-regions`` block and the resolved regions into steps."""

    fetcher: Fetcher
    prefix: Path
    files: Sequence[RegionFile]
    method = "osm-regions"

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

    def steps(
        self, manifest: PackageManifest, block: RegionalDataInstall
    ) -> list[Action | Command]:
        out = self.data_dir(manifest)
        root = needs_root_for(self.prefix)
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
                    perform=partial(self._install, region, fetched, dest),
                    requires_root=root,
                )
            )
        steps.extend(removal_steps(out, PBF, {f.slug for f in self.files}, requires_root=root))
        return steps

    def _fetch(self, region: RegionFile, fetched: dict[str, Path]) -> str:
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
        fetched["path"] = result.path
        where = "cached" if result.from_cache else "downloaded"
        return f"{where} {result.size} bytes, {how}"

    def _install(self, region: RegionFile, fetched: dict[str, Path], dest: Path) -> str:
        path = fetched.get("path")
        if path is None:  # pragma: no cover
            raise BackendError("the map region was not fetched before the install step")
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Copy, never move: the cache is content-addressed and shared. Through
        # a temporary so a half-copied region never sits under its real name.
        temporary = dest.with_name(dest.name + f".part.{os.getpid()}")
        try:
            shutil.copyfile(path, temporary)
            os.chmod(temporary, 0o644)
            os.replace(temporary, dest)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
        sidecar = dest.with_name(dest.name + SOURCE)
        sidecar.write_text(f"{region.snapshot}\n")
        os.chmod(sidecar, 0o644)
        return f"installed {dest} ({human_size(region.size)}, snapshot {region.snapshot})"
