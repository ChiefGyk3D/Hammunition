# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The data backend: offline datasets whose payload is the point (D-049).

A map tileset, a Wikipedia ZIM, the DX-cluster country file. Each artifact
is fetched into the shared cache and verified against its sha256 like every
other download; the declared ``size`` is checked against the bytes received,
so a manifest that says 0.69 GB and fetches something else is refused rather
than trusted. A ``file`` is copied under the unit's data directory; a ``zip``
or ``tarball`` is extracted into it, or into its own subdirectory ``into``,
through the same guarded extraction the source backend uses, and only its
listed ``members`` when it lists any (D-071). Nothing here is executed, ever.

The install directory is ``<prefix>/share/hammunition/data/<name>/`` -- a
namespace only this engine writes, which is what lets ``uninstall`` remove
it whole from the log's ``install-data`` records without guessing.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from ..fetch import Fetcher, MirrorPath, fetch_disclosure, record_fetch, safe_name
from ..manifest.schema import DataArtifact, DataInstall, PackageManifest
from .base import Action, BackendError, Command, CommandRunner
from .source import extract, needs_root_for
from .verified import PrefixWriter


def human_size(size: int) -> str:
    """``353536`` -> ``354 KB``; ``690000000`` -> ``0.69 GB``. Decimal, as publishers quote."""
    if size >= 100_000_000:
        # Publishers quote a 690 MB tileset as 0.69 GB; so does Q-021.
        return f"{size / 1e9:.2f} GB"
    if size >= 1_000_000:
        return f"{size / 1e6:.1f} MB"
    return f"{size / 1e3:.0f} KB"


def data_name(artifact: DataArtifact) -> str:
    """The artifact's stable name within its unit, as ``hammunition
    artifacts`` lists it and a LAN mirror serves it (D-070): the name it is
    installed under, or for an archive the file name its URL ends in."""
    return artifact.install_as or safe_name(artifact.url)


@dataclass(frozen=True)
class DataBackend:
    """Turns a ``data`` install block into fetch-and-install steps."""

    fetcher: Fetcher
    prefix: Path
    runner: CommandRunner | None = None
    """Escalates the copy into a root-owned prefix when the engine is not root."""
    method = "data"

    def data_dir(self, manifest: PackageManifest) -> Path:
        return self.prefix / "share" / "hammunition" / "data" / manifest.name

    def steps(self, manifest: PackageManifest, block: DataInstall) -> list[Action | Command]:
        steps: list[Action | Command] = []
        target_dir = self.data_dir(manifest)
        for artifact in block.artifacts:
            fetched: dict[str, Path] = {}
            facts: dict[str, str] = {}
            where = MirrorPath(manifest.name, data_name(artifact))
            note, urls, sources = fetch_disclosure(self.fetcher, artifact.url, where, "sha256")
            steps.append(
                Action(
                    kind="fetch",
                    description=(
                        f"Fetch {manifest.name} data ({human_size(artifact.size)}, "
                        f"{block.licence}){note}"
                    ),
                    detail=f"{urls} (sha256 {artifact.sha256[:12]}…, {artifact.size} bytes)",
                    perform=partial(self._fetch, artifact, fetched, where, facts),
                    sources=sources,
                    facts=facts,
                )
            )
            if artifact.format == "file":
                assert artifact.install_as is not None  # the schema requires it
                dest = target_dir / artifact.install_as
                description = f"Install {manifest.name} data file {artifact.install_as}"
            else:
                dest = target_dir if artifact.into is None else target_dir / artifact.into
                target = "its data directory" if artifact.into is None else str(dest)
                which = (
                    f", only the listed members ({len(artifact.members)})"
                    if artifact.members is not None
                    else ""
                )
                description = (
                    f"Extract {manifest.name} data ({artifact.format}) into {target}{which}"
                )
            steps.append(
                Action(
                    kind="install-data",
                    description=description,
                    # The destination, verbatim: uninstall's attribution replay
                    # reads it back, as it does install-binary's.
                    detail=str(dest),
                    perform=partial(self._install, artifact, fetched, dest),
                    requires_root=needs_root_for(self.prefix),
                )
            )
        return steps

    def _fetch(
        self,
        artifact: DataArtifact,
        fetched: dict[str, Path],
        where: MirrorPath,
        facts: dict[str, str],
    ) -> str:
        result = self.fetcher.fetch(artifact, mirror=where)
        source = record_fetch(result, facts, mirrored=bool(self.fetcher.mirror))
        if result.size != artifact.size:
            raise BackendError(
                f"{artifact.url}: the manifest declares {artifact.size} bytes and the "
                f"download is {result.size}; the digest matched, so the declaration is "
                f"wrong -- fix the manifest, the plan printed a size that was not true"
            )
        fetched["path"] = result.path
        how = "cached" if result.from_cache else "downloaded"
        return f"{how} {result.size} bytes, sha256 {result.sha256[:12]}… verified{source}"

    def _install(self, artifact: DataArtifact, fetched: dict[str, Path], dest: Path) -> str:
        path = fetched.get("path")
        if path is None:  # pragma: no cover
            raise BackendError("the data artifact was not fetched before the install step")
        if artifact.format == "file":
            # Copy, never move: the cache is content-addressed and shared. And
            # never trusted for having verified once -- the cache is the
            # operator's and the prefix is root's, so the copy is opened
            # without following a symlink and re-hashed on the way in.
            writer = PrefixWriter(privileged=needs_root_for(self.prefix), runner=self.runner)
            writer.install_verified(path, dest, algorithm="sha256", digest=artifact.sha256)
            return f"installed {dest} ({human_size(artifact.size)}, mode 0644, sha256 re-verified)"
        if artifact.into is not None:
            # The unit's own directory, which a first archive with `into` makes.
            dest.parent.mkdir(parents=True, exist_ok=True)
            os.chmod(dest.parent, 0o755)
        outcome = extract(path, dest, members=artifact.members)
        installed = sorted(p for p in dest.rglob("*") if p.is_file())
        for p in installed:
            os.chmod(p, 0o644)
        for d in (p for p in dest.rglob("*") if p.is_dir()):
            os.chmod(d, 0o755)
        os.chmod(dest, 0o755)
        return f"{outcome}; {len(installed)} file(s) under {dest}"
