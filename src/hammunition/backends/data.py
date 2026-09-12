# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The data backend: offline datasets whose payload is the point (D-049).

A map tileset, a Wikipedia ZIM, the DX-cluster country file. Each artifact
is fetched into the shared cache and verified against its sha256 like every
other download; the declared ``size`` is checked against the bytes received,
so a manifest that says 0.69 GB and fetches something else is refused rather
than trusted. A ``file`` is copied under the unit's data directory; a ``zip``
or ``tarball`` is extracted into it, through the same guarded extraction the
source backend uses. Nothing here is executed, ever.

The install directory is ``<prefix>/share/hammunition/data/<name>/`` -- a
namespace only this engine writes, which is what lets ``uninstall`` remove
it whole from the log's ``install-data`` records without guessing.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from ..fetch import Fetcher
from ..manifest.schema import DataArtifact, DataInstall, PackageManifest
from .base import Action, BackendError, Command
from .source import extract, needs_root_for


def human_size(size: int) -> str:
    """``353536`` -> ``354 KB``; ``690000000`` -> ``0.69 GB``. Decimal, as publishers quote."""
    if size >= 100_000_000:
        # Publishers quote a 690 MB tileset as 0.69 GB; so does Q-021.
        return f"{size / 1e9:.2f} GB"
    if size >= 1_000_000:
        return f"{size / 1e6:.1f} MB"
    return f"{size / 1e3:.0f} KB"


@dataclass(frozen=True)
class DataBackend:
    """Turns a ``data`` install block into fetch-and-install steps."""

    fetcher: Fetcher
    prefix: Path
    method = "data"

    def data_dir(self, manifest: PackageManifest) -> Path:
        return self.prefix / "share" / "hammunition" / "data" / manifest.name

    def steps(self, manifest: PackageManifest, block: DataInstall) -> list[Action | Command]:
        steps: list[Action | Command] = []
        target_dir = self.data_dir(manifest)
        for artifact in block.artifacts:
            fetched: dict[str, Path] = {}
            steps.append(
                Action(
                    kind="fetch",
                    description=f"Fetch {manifest.name} data ({human_size(artifact.size)}, {block.licence})",
                    detail=f"{artifact.url} (sha256 {artifact.sha256[:12]}…, {artifact.size} bytes)",
                    perform=partial(self._fetch, artifact, fetched),
                )
            )
            if artifact.format == "file":
                assert artifact.install_as is not None  # the schema requires it
                dest = target_dir / artifact.install_as
                description = f"Install {manifest.name} data file {artifact.install_as}"
            else:
                dest = target_dir
                description = (
                    f"Extract {manifest.name} data ({artifact.format}) into its data directory"
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

    def _fetch(self, artifact: DataArtifact, fetched: dict[str, Path]) -> str:
        result = self.fetcher.fetch(artifact)
        if result.size != artifact.size:
            raise BackendError(
                f"{artifact.url}: the manifest declares {artifact.size} bytes and the "
                f"download is {result.size}; the digest matched, so the declaration is "
                f"wrong -- fix the manifest, the plan printed a size that was not true"
            )
        fetched["path"] = result.path
        where = "cached" if result.from_cache else "downloaded"
        return f"{where} {result.size} bytes, sha256 {result.sha256[:12]}… verified"

    def _install(self, artifact: DataArtifact, fetched: dict[str, Path], dest: Path) -> str:
        path = fetched.get("path")
        if path is None:  # pragma: no cover
            raise BackendError("the data artifact was not fetched before the install step")
        if artifact.format == "file":
            dest.parent.mkdir(parents=True, exist_ok=True)
            # Copy, never move: the cache is content-addressed and shared.
            shutil.copyfile(path, dest)
            os.chmod(dest, 0o644)
            return f"installed {dest} ({human_size(artifact.size)}, mode 0644)"
        outcome = extract(path, dest)
        installed = sorted(p for p in dest.rglob("*") if p.is_file())
        for p in installed:
            os.chmod(p, 0o644)
        for d in (p for p in dest.rglob("*") if p.is_dir()):
            os.chmod(d, 0o755)
        os.chmod(dest, 0o755)
        return f"{outcome}; {len(installed)} file(s) under {dest}"
