# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Installing something upstream already built.  D-004, D-014.

Measured, not assumed: **eight units in the catalog's dispositions wait on
this and nothing else** — QtTermTCP, QtSoundModem and Pi-APRS from D-008's
packet core, GARIM and ARDOPGUI, AntScope2 and GridTracker2 from AHRL, and
`sdrangel` on the five targets that do not package it. None is available from
apt on any of our six targets, which was checked rather than assumed. That is
the largest single group of units blocked on one missing backend, which is why
it is the one that got written.

Three formats, and the differences between them are the whole design.

**`deb` goes through apt, not dpkg.** ``apt-get install ./file.deb`` resolves
the package's dependencies; ``dpkg -i`` installs it and leaves them broken,
which is the classic way to wedge a machine with a vendor package. Using apt
also means the result is an ordinary installed package that ``apt`` knows
about, so removing it later is `apt remove` rather than archaeology.

**`tarball` and `zip` unpack and then install what the manifest names.** The
archive's own layout is upstream's business; `binaries` says which files matter
and what they should be called. This reuses the extraction the source backend
already does — same tar filter, same zip screening, same one-top-level-directory
rule — because a prebuilt archive is exactly as hostile as a source one.

**`executable` is a single file.** Fetch, verify, chmod, install.

**Nothing here is unverified.** :class:`~hammunition.manifest.schema.RemoteArtifact`
makes `sha256` mandatory and :mod:`hammunition.fetch` refuses a mismatch, so a
vendor binary that changed under us fails closed rather than installing. That
matters more here than for a source build: nobody is going to read a .deb.

**AppImage is deliberately not implemented.** `SCOPE.md` puts it post-1.0 and
its two consumers, HAMRS and Reticulum MeshChat, are both post-1.0 units. It is
refused by name so the gap stays visible (D-014).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from hammunition.fetch import Fetcher
from hammunition.manifest.schema import BinaryInstall, PackageManifest

from .base import Action, BackendError, Command, CommandRunner
from .source import (
    SourceLayout,
    extract,
    install_binary_commands,
    needs_root_for,
    prepare_tree,
    tree_install_commands,
)

__all__ = ["IMPLEMENTED_BINARY_FORMATS", "BinaryBackend"]

#: What this backend can install. `appimage` is a measured, deliberate absence.
IMPLEMENTED_BINARY_FORMATS = frozenset({"deb", "tarball", "zip", "executable"})

_ARCHIVE_FORMATS = frozenset({"tarball", "zip"})


@dataclass(frozen=True)
class BinaryBackend:
    """Turns a ``binary`` install block into the steps that install it."""

    fetcher: Fetcher
    runner: CommandRunner
    """Used by the .deb path, which shells out to apt. Going through the runner
    rather than :mod:`subprocess` keeps the one seam every other command uses."""

    build_root: Path
    """Archives unpack here. Named for the source backend's directory because it
    is the same directory: a prebuilt tree and a built one are both scratch."""

    prefix: Path

    method = "binary"

    def layout(self, manifest: PackageManifest, block: BinaryInstall) -> SourceLayout:
        """Where an archive unpacks. Pure — touches no disk.

        Keyed by the artifact digest, so a changed artifact unpacks somewhere
        new instead of over the previous one's files.
        """
        return SourceLayout(self.build_root / f"{manifest.name}-{block.artifact.sha256[:12]}")

    def steps(self, manifest: PackageManifest, block: BinaryInstall) -> list[Action | Command]:
        if block.format not in IMPLEMENTED_BINARY_FORMATS:
            raise BackendError(
                f"{manifest.name} is a {block.format!r} artifact and this backend does "
                f"not install one. Implemented: {', '.join(sorted(IMPLEMENTED_BINARY_FORMATS))}. "
                f"AppImage is post-1.0 (SCOPE.md) and is refused by name rather than "
                f"quietly skipped."
            )

        fetched: dict[str, Path] = {}

        def fetch() -> str:
            result = self.fetcher.fetch(block.artifact)
            fetched["path"] = result.path
            where = "cached" if result.from_cache else "downloaded"
            return f"{where} {result.size} bytes, sha256 {result.sha256[:12]}… verified"

        steps: list[Action | Command] = [
            Action(
                kind="fetch",
                description=f"Fetch {manifest.name}",
                detail=f"{block.artifact.url} (sha256 {block.artifact.sha256[:12]}…)",
                perform=fetch,
            )
        ]

        if block.format == "deb":
            # The path is not knowable until the fetch has run, so the install
            # is an Action that builds its own command rather than a Command
            # rendered at plan time. The plan still names the URL and digest
            # above, which is what an operator needs to see.
            steps.append(
                Action(
                    kind="install-deb",
                    description=f"Install {manifest.name} from the downloaded .deb",
                    detail="apt-get install on the file, so its dependencies resolve",
                    perform=lambda: self._install_deb(manifest.name, fetched),
                    requires_root=True,
                )
            )
            return steps

        if block.format in _ARCHIVE_FORMATS:
            layout = self.layout(manifest, block)
            if not manifest.binaries and not block.install_tree:
                raise BackendError(
                    f"{manifest.name} is a prebuilt archive and names no `binaries` "
                    f"and no `install_tree`. Unpacking it would leave a directory in "
                    f"a cache and install nothing — a run that reports success having "
                    f"done nothing."
                )
            steps.append(
                Action(
                    kind="prepare",
                    description=f"Clear any previous {manifest.name} unpack",
                    detail=f"{layout.src} (removed if present, then recreated)",
                    perform=lambda: prepare_tree(layout.src),
                )
            )
            steps.append(
                Action(
                    kind="extract",
                    description=f"Unpack {manifest.name}",
                    detail=f"into {layout.src}",
                    perform=lambda: extract(fetched["path"], layout.src),
                )
            )
            steps.extend(
                install_binary_commands(
                    name=manifest.name,
                    layout=layout,
                    prefix=self.prefix,
                    binaries=manifest.binaries,
                )
            )
            if block.install_tree:
                steps.extend(
                    tree_install_commands(
                        name=manifest.name, source_tree=layout.src, prefix=self.prefix
                    )
                )
            return steps

        # `executable`: one file, installed under the name the manifest gives it.
        if len(manifest.binaries) != 1:
            raise BackendError(
                f"{manifest.name} is a single prebuilt executable, so it must declare "
                f"exactly one `binaries` entry saying what to call it; it declares "
                f"{len(manifest.binaries)}."
            )
        target = self.prefix / "bin" / manifest.binaries[0].install_as
        steps.append(
            Action(
                kind="install-binary",
                description=f"Install {manifest.name} as {target}",
                # The detail is the destination path, verbatim: action_end
                # records it, and uninstall's file-attribution replay reads
                # it back — an Action leaves no argv for the replay to parse.
                detail=str(target),
                perform=lambda: self._install_executable(fetched, target),
                requires_root=needs_root_for(self.prefix),
            )
        )
        return steps

    def _install_deb(self, name: str, fetched: dict[str, Path]) -> str:
        """Hand the file to apt so its dependencies resolve."""
        path = fetched.get("path")
        if path is None:  # pragma: no cover - the fetch Action always runs first
            raise BackendError(f"{name}: the .deb was not fetched before the install step")
        result = self.runner.run(
            Command(
                argv=("apt-get", "install", "--yes", "--", str(path)),
                description=f"Install {name} from {path.name}",
                env={"DEBIAN_FRONTEND": "noninteractive"},
                requires_root=True,
            )
        )
        if not result.ok:
            raise BackendError(
                f"apt could not install {path.name}: {result.stderr.strip()[:400]}\n"
                f"A vendor .deb built for a different release is the usual cause, and "
                f"apt refusing it is the correct outcome — dpkg would have installed it "
                f"and left the dependencies broken."
            )
        return f"installed {path.name} through apt"

    def _install_executable(self, fetched: dict[str, Path], target: Path) -> str:
        path = fetched.get("path")
        if path is None:  # pragma: no cover
            raise BackendError("the executable was not fetched before the install step")
        target.parent.mkdir(parents=True, exist_ok=True)
        # Copy rather than move: the fetch cache is content-addressed and shared,
        # and moving out of it would make the next run re-download.
        target.write_bytes(path.read_bytes())
        os.chmod(target, 0o755)
        return f"installed {target} (mode 0755)"
