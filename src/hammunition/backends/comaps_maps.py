# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The mwm-regions backend: CoMaps' own maps for the station's regions.  D-069.

The maps come from station config through the region table in
``catalog/data/comaps-pins.yaml`` (:func:`resolve_station_maps`), resolved
before the plan prints, because each map's size, licence and check are the
disclosure (D-049 rule 2). The fetch step's description is that disclosure.

Each map is fetched into the shared cache, checked against the SHA-1 and exact
size in CoMaps' own index at the pinned commit -- the publisher's check, said
so on the line -- and copied to
``<prefix>/share/hammunition/data/<unit>/<version>/<id>.mwm``, re-hashed on
the way in by the sha256 the fetch measured, which the step's outcome puts in
the transaction log. The cached download is then deleted: a US state is tens
of megabytes and the whole country 15.7 GB, and the installed copy answers a
re-install. A map already installed at its pinned size is not fetched again.
A ``.mwm`` in the directory that no chosen region needs -- a region dropped,
or an older version -- is removed as its own step.

The version directory is CoMaps' own layout: the app scans
``<writable>/<version>/*.mwm``, and ``hammunition maps comaps`` links these
files there for the operator. Nothing here is ever executed.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from ..comaps import (
    REGENERATE,
    VERIFIED_BY,
    ComapsError,
    MapFile,
    gone,
    load_pins,
    published,
    resolve_regions,
    sha1_hex,
)
from ..fetch import Fetcher, MirrorPath, fetch_disclosure, record_fetch
from ..manifest.schema import MwmRegionsInstall, PackageManifest
from .base import Action, Command, CommandRunner
from .data import human_size
from .regions import data_root, device_at, free_bytes_at
from .source import needs_root_for
from .verified import PrefixWriter

MWM = ".mwm"


def map_current(dest: Path, f: MapFile) -> bool:
    """Whether *dest* holds this map at its pin: a regular file at its exact size.
    The directory names the version and the size is exact; the hash was
    checked on the way in and is not re-read on every plan."""
    return dest.is_file() and not dest.is_symlink() and dest.stat().st_size == f.pin.size


def map_dest(data_dir: Path, f: MapFile) -> Path:
    return data_dir / str(f.version) / f.file


def mirror_path(unit: str, f: MapFile) -> MirrorPath:
    """Where a LAN mirror serves this map (D-070): ``<unit>/<version>/<id>.mwm``,
    the installed layout, so two versions never share a name."""
    return MirrorPath(unit, f"{f.version}/{f.file}")


def maps_disk_needs(pending: Sequence[MapFile], *, cache: Path, prefix: Path) -> dict[Path, int]:
    """Each download once in the fetch cache and once under the prefix: both
    exist between the install and the cache prune."""
    total = sum(f.pin.size for f in pending)
    return {cache: total, prefix: total} if total else {}


def maps_shortfall(
    needs: Mapping[Path, int],
    others: Mapping[Path, int] | None = None,
    *,
    free_at: Callable[[Path], int] = free_bytes_at,
    device_of: Callable[[Path], int] = device_at,
) -> str | None:
    """A refusal naming both numbers for every file system short of room for
    the maps, counting the same run's other map data (*others*) on it too."""
    merged: dict[Path, int] = dict(others or {})
    for path, amount in needs.items():
        merged[path] = merged.get(path, 0) + amount
    by_device: dict[int, tuple[list[Path], int]] = {}
    for path, amount in merged.items():
        paths, total = by_device.get(device_of(path), ([], 0))
        by_device[device_of(path)] = ([*paths, path], total + amount)
    short: list[str] = []
    for paths, need in by_device.values():
        free = free_at(paths[0])
        if free < need:
            short.append(
                f"{', '.join(str(p) for p in paths)}: {human_size(need)} ({need} bytes) is "
                f"needed and {human_size(free)} ({free} bytes) is free"
            )
    if not short:
        return None
    return (
        "not enough disk space for CoMaps' maps (each counted twice: the verified "
        "download in the cache and the installed copy; other map data in the same run "
        "is counted too):\n  " + "\n  ".join(short)
    )


@dataclass(frozen=True)
class ComapsMapsBackend:
    """Turns the station's CoMaps maps into fetch, install, prune and remove steps."""

    fetcher: Fetcher
    prefix: Path
    files: Sequence[MapFile]
    runner: CommandRunner | None = None
    """Escalates the copy into a root-owned prefix when the engine is not root."""
    method = "mwm-regions"

    def data_dir(self, manifest: PackageManifest) -> Path:
        return data_root(self.prefix) / manifest.name

    @property
    def writer(self) -> PrefixWriter:
        return PrefixWriter(privileged=needs_root_for(self.prefix), runner=self.runner)

    def pending(self, manifest: PackageManifest) -> list[MapFile]:
        """The maps not installed at their pin: what this run downloads."""
        out = self.data_dir(manifest)
        return [f for f in self.files if not map_current(map_dest(out, f), f)]

    def steps(self, manifest: PackageManifest, block: MwmRegionsInstall) -> list[Action | Command]:
        out = self.data_dir(manifest)
        writer = self.writer
        steps: list[Action | Command] = []
        for f in self.pending(manifest):
            fetched: dict[str, str] = {}
            facts: dict[str, str] = {}
            dest = map_dest(out, f)
            where = mirror_path(manifest.name, f)
            note, urls, sources = fetch_disclosure(self.fetcher, f.url, where, "SHA-1")
            steps.append(
                Action(
                    kind="fetch",
                    description=(
                        f"Fetch CoMaps map {f.id} ({human_size(f.pin.size)}, {block.licence}) "
                        f"— {VERIFIED_BY}{note}"
                    ),
                    detail=(
                        f"{urls} (SHA-1 {sha1_hex(f.pin.sha1)[:12]}…, {f.pin.size} bytes; "
                        f"its sha256 is recorded)"
                    ),
                    perform=partial(self._fetch, f, fetched, where, facts),
                    sources=sources,
                    facts=facts,
                )
            )
            steps.append(
                Action(
                    kind="install-data",
                    description=f"Install CoMaps map {f.id} (version {f.version})",
                    # The destination, verbatim, for uninstall's attribution replay.
                    detail=str(dest),
                    perform=partial(self._install, f, fetched, dest, writer),
                    requires_root=writer.privileged,
                )
            )
            steps.append(
                Action(
                    kind="prune-cache",
                    description=f"Delete the cached download of {f.id} once it is installed",
                    detail=str(self.fetcher.sha1_path_for(f.url, sha1_hex(f.pin.sha1))),
                    perform=partial(self._prune, fetched, dest),
                )
            )
        wanted = {map_dest(out, f) for f in self.files}
        if out.is_dir():
            for path in sorted(out.glob(f"*/*{MWM}")):
                if path in wanted or not path.is_file() or path.is_symlink():
                    continue
                steps.append(
                    Action(
                        kind="remove-data",
                        description=(
                            f"Remove CoMaps map {path.parent.name}/{path.name}: no longer "
                            f"needed by your map regions at this version"
                        ),
                        # The path, verbatim: uninstall stops attributing it.
                        detail=str(path),
                        perform=partial(_remove, writer, path),
                        requires_root=writer.privileged,
                    )
                )
        return steps

    def _fetch(
        self, f: MapFile, fetched: dict[str, str], where: MirrorPath, facts: dict[str, str]
    ) -> str:
        result = self.fetcher.fetch_sha1(
            f.url, sha1_hex(f.pin.sha1), expected_size=f.pin.size, mirror=where
        )
        fetched["path"] = str(result.path)
        fetched["sha256"] = result.sha256
        source = record_fetch(result, facts, mirrored=bool(self.fetcher.mirror))
        state = "cached" if result.from_cache else "downloaded"
        return (
            f"{state} {result.size} bytes; SHA-1 and size match CoMaps' index; "
            f"sha256 {result.sha256}{source}"
        )

    def _install(
        self, f: MapFile, fetched: dict[str, str], dest: Path, writer: PrefixWriter
    ) -> str:
        path = fetched.get("path")
        digest = fetched.get("sha256")
        if path is None or digest is None:  # pragma: no cover - a failed fetch stops the run
            raise ComapsError(f"{f.id} was not fetched before its install step")
        # Copy, never move: the cache is shared. Re-hashed on the way in by
        # the sha256 the verified download measured.
        writer.install_verified(Path(path), dest, algorithm="sha256", digest=digest)
        return f"installed {dest} ({human_size(f.pin.size)}, mode 0644, sha256 {digest})"

    @staticmethod
    def _prune(fetched: dict[str, str], dest: Path) -> str:
        path = fetched.get("path")
        if path is None or not dest.is_file():  # pragma: no cover - a failed step stops the run
            return "kept: the map did not install"
        Path(path).unlink(missing_ok=True)
        return f"deleted {path}"


def _remove(writer: PrefixWriter, path: Path) -> str:
    writer.remove([path])
    return f"removed {path}"


UNMAPPED = (
    "no CoMaps map is mapped for {region}, so nothing is fetched for it; the region "
    "table (catalog/data/comaps-pins.yaml) places Geofabrik regions by name, and one "
    "CoMaps spells differently is left out rather than guessed"
)


def resolve_station_maps(
    regions: Sequence[str],
    catalog_root: Path,
    *,
    installed: Path,
    head: Callable[[str], tuple[int, int]],
) -> tuple[list[MapFile], list[str]]:
    """The station's regions as pinned maps, checked before the plan prints;
    and a note naming each region the table cannot place.

    A map installed at its pin asks nothing of the network. Every other one is
    asked for once, by ``HEAD``, and must answer 200 **with the pinned size**:
    a mirror answers a missing map with 200 and a web page. A pin the CDN has
    dropped refuses the plan here, naming the regeneration, rather than
    failing a fetch after apt has run; so does a map that cannot be reached.
    Every such map is named together.
    """
    pins = load_pins(catalog_root)
    files, unmapped = resolve_regions(regions, pins)
    notes = [UNMAPPED.format(region=region) for region in unmapped]
    if unmapped and not files:
        notes.append(
            "none of your map regions has a CoMaps map, so CoMaps' maps install nothing "
            "this run; CoMaps itself shows only its world overview"
        )
    problems: list[str] = []
    for f in files:
        if map_current(map_dest(installed, f), f):
            continue
        try:
            status, size = head(f.url)
        except ComapsError as exc:
            problems.append(f"  {f.id}: {exc}")
            continue
        if gone(status, size, f.pin):
            problems.append(
                f"  {f.id}: pin expired: {f.url} answered HTTP {status} with {size} bytes, "
                f"not the pinned {f.pin.size}. CoMaps' CDN keeps a map version for months, "
                f"not forever; {REGENERATE}. A newer version is not taken in its place: "
                f"its checks come from a newer CoMaps index."
            )
        elif not published(status, size, f.pin):
            problems.append(
                f"  {f.id}: {f.url} answered HTTP {status}, not 200; the server did not say "
                f"whether the map is still published. Try again later."
            )
    if problems:
        raise ComapsError(
            f"{len(problems)} CoMaps map(s) cannot be fetched and are not installed "
            f"already:\n" + "\n".join(problems)
        )
    return files, notes
