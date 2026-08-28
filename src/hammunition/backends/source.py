# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Building from a verified source archive.  DESIGN.md §6, D-004.

**This is the backend the project exists for.** 57 of AHRL's 95 units cannot be
satisfied by apt and 35 of those are source builds from bundled tarballs; an
apt-only tool covers roughly 40% of the parity target and the missing 60% is
precisely what users cannot install for themselves.

The build systems implemented here are the ones the catalog actually needs,
counted rather than assumed (**D-014**): **cmake 6, autotools 2, qmake 2,
make 2** across the twelve `source` and `git` blocks in the catalog today.
Two fields are **measured zeros** and are refused by name rather than
speculatively implemented — no manifest uses ``custom``, and none carries
``patches``. Recording the zero is the point: it stops either being re-added
by convention, and it means the refusal names a real gap if one ever arrives.

Three properties worth stating up front.

**Nothing is built from bytes that were not verified.** The archive arrives
through :mod:`hammunition.fetch`, which refuses anything whose digest does not
match the manifest and leaves nothing usable behind when it does. The build
steps below take a path that verification already vouched for.

**The tree lands in a predictable place, so the plan can be printed before the
archive exists.** Extraction always strips a single top-level directory into
``<build>/src``, so ``./configure`` and ``cmake -S`` can be rendered with real
paths at plan time rather than described in prose. A dry run that said "then
configure in whatever directory the tarball unpacks to" would be the
approximate dry run CLAUDE.md forbids.

**Extraction is done here, not by ``tar``.** An archive member named
``../../etc/cron.d/x``, an absolute path, or a symlink pointing out of the tree
is a well-known way to turn "unpack this" into "write anywhere", and the
defaults of the extractor decide whether that works. :func:`extract` uses
Python's ``data`` filter for tar and screens every zip member itself, then
verifies that what landed is inside the destination — checking the result and
not only the intent (**D-031**).
"""

from __future__ import annotations

import os
import shutil
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

from hammunition.fetch import Fetcher
from hammunition.manifest.schema import PackageManifest, SourceInstall

from .base import Action, BackendError, Command

__all__ = [
    "DEFAULT_PREFIX",
    "IMPLEMENTED_BUILD_SYSTEMS",
    "SourceBackend",
    "SourceLayout",
    "extract",
]

#: FHS: locally-built software goes in /usr/local, where it does not collide
#: with anything the distribution's package manager owns.
DEFAULT_PREFIX = Path("/usr/local")

#: Counted from the catalog, not assumed (D-014). `custom` is a measured zero
#: and is refused by name.
IMPLEMENTED_BUILD_SYSTEMS = frozenset({"autotools", "cmake", "qmake", "make"})

_TAR_SUFFIXES = (".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz", ".tar")


@dataclass(frozen=True)
class SourceLayout:
    """Where one package's build happens. Derived, so it is knowable at plan time."""

    root: Path
    """``<cache>/build/<package>-<digest8>``."""

    @property
    def src(self) -> Path:
        """The extracted tree. Always this path — see the module docstring."""
        return self.root / "src"

    @property
    def build(self) -> Path:
        """Out-of-tree build directory. cmake uses it; autotools builds in ``src``."""
        return self.root / "build"


def _is_tar(name: str) -> bool:
    return name.lower().endswith(_TAR_SUFFIXES)


def _is_zip(name: str) -> bool:
    return name.lower().endswith(".zip")


def _safe_members(names: list[str], destination: Path) -> None:
    """Refuse any archive member that would land outside *destination*.

    Used for zip, where there is no equivalent of tar's ``data`` filter. An
    absolute path, a ``..`` component, or a drive-style prefix is refused for
    the whole archive rather than skipped: a partially-extracted tree is not a
    thing to build from, and quietly dropping members would produce a build
    failure that says nothing about why.
    """
    for name in names:
        if name.startswith("/") or name.startswith("\\") or ":" in name.split("/", 1)[0]:
            raise BackendError(
                f"refusing to extract {name!r}: an archive member with an absolute "
                f"path would write outside the build directory"
            )
        target = (destination / name).resolve()
        if target != destination.resolve() and destination.resolve() not in target.parents:
            raise BackendError(
                f"refusing to extract {name!r}: it resolves outside the build "
                f"directory, which is how an archive turns 'unpack' into "
                f"'write anywhere'"
            )


def extract(archive: Path, destination: Path) -> str:
    """Unpack *archive* into *destination*, stripping one top-level directory.

    Returns a one-line outcome. Raises :class:`BackendError` on anything it
    will not unpack — an unknown format, or a member that would escape.

    The strip is what makes the source root predictable: nearly every release
    tarball contains exactly one top-level directory whose name carries the
    version, so keeping it would put the version in every subsequent path and
    make the plan unprintable before the download. When an archive has more
    than one top-level entry it is unpacked as-is, and the root is still
    ``destination``.
    """
    if destination.exists():
        # Idempotent: a re-run rebuilds from a clean tree rather than layering a
        # new archive over a half-built one, where a stale object file outlives
        # the source it came from.
        shutil.rmtree(destination)
    staging = destination.parent / (destination.name + ".unpack")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    try:
        if _is_tar(archive.name):
            with tarfile.open(archive) as tar:
                # PEP 706. Refuses absolute paths, `..`, links pointing outside
                # the destination, device nodes, and setuid/setgid bits.
                tar.extractall(staging, filter="data")
                count = len(tar.getnames())
        elif _is_zip(archive.name):
            with zipfile.ZipFile(archive) as archive_zip:
                names = archive_zip.namelist()
                _safe_members(names, staging)
                archive_zip.extractall(staging)
                count = len(names)
        else:
            raise BackendError(
                f"{archive.name} is not an archive this backend unpacks. "
                f"Supported: {', '.join(_TAR_SUFFIXES)}, .zip"
            )

        entries = list(staging.iterdir())
        if len(entries) == 1 and entries[0].is_dir():
            os.replace(entries[0], destination)
            stripped = entries[0].name
        else:
            os.replace(staging, destination)
            stripped = ""
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)

    # D-031: check what landed, not that the extractor returned. A filter that
    # silently dropped everything and one that worked both "succeed".
    if not destination.exists() or not any(destination.iterdir()):
        raise BackendError(
            f"{archive.name} unpacked to nothing. The archive is empty, or every "
            f"member was refused by the extraction filter."
        )
    note = f", stripped {stripped}/" if stripped else ""
    return f"unpacked {count} entries{note}"


class SourceBackend:
    """Turns a ``source`` install block into the steps that build it."""

    method = "source"

    def __init__(
        self,
        fetcher: Fetcher,
        *,
        build_root: Path,
        prefix: Path = DEFAULT_PREFIX,
        jobs: int | None = None,
    ) -> None:
        self.fetcher = fetcher
        self.build_root = build_root
        self.prefix = prefix
        self.jobs = jobs if jobs is not None else (os.cpu_count() or 1)

    def layout(self, manifest: PackageManifest, block: SourceInstall) -> SourceLayout:
        """Where this package builds. Pure — touches no disk, so the plan can
        print every path before anything is fetched."""
        return SourceLayout(self.build_root / f"{manifest.name}-{block.source.sha256[:8]}")

    def steps(self, manifest: PackageManifest, block: SourceInstall) -> list[Action | Command]:
        """Fetch, verify, unpack, configure, build, install — in that order.

        Only the final install needs root. CLAUDE.md drops to the operator
        wherever possible, and a build that ran wholly as root would leave a
        tree of root-owned objects in the operator's cache for no benefit.
        """
        if block.build_system not in IMPLEMENTED_BUILD_SYSTEMS:
            raise BackendError(
                f"{manifest.name} declares build_system {block.build_system!r}, which "
                f"this engine build does not implement (it implements "
                f"{', '.join(sorted(IMPLEMENTED_BUILD_SYSTEMS))}). No manifest in the "
                f"catalog uses it, so it is an unimplemented gap rather than a "
                f"regression — D-014 records the zero rather than building for it."
            )
        if block.patches:
            raise BackendError(
                f"{manifest.name} declares {len(block.patches)} patch(es), and applying "
                f"them is not implemented. No manifest in the catalog carries a patch "
                f"today, so this is a named gap rather than a silent skip — building "
                f"unpatched source would produce a binary the manifest did not describe."
            )

        layout = self.layout(manifest, block)
        artifact = block.source
        steps: list[Action | Command] = [
            Action(
                kind="fetch",
                description=f"Download and verify the {manifest.name} source archive",
                detail=f"{artifact.url} -> {self.fetcher.path_for(artifact)} (sha256 verified)",
                perform=lambda: self._fetch(manifest, block),
            ),
            Action(
                kind="extract",
                description=f"Unpack the {manifest.name} source",
                detail=f"{self.fetcher.path_for(artifact)} -> {layout.src}",
                perform=lambda: extract(self.fetcher.path_for(artifact), layout.src),
            ),
        ]
        steps.extend(self._build_commands(manifest, block, layout))
        return steps

    def _fetch(self, manifest: PackageManifest, block: SourceInstall) -> str:
        result = self.fetcher.fetch(block.source)
        where = "cached" if result.from_cache else "downloaded"
        return f"{where} {result.size} bytes, sha256 {result.sha256[:12]}… verified"

    def _compiler_env(self, block: SourceInstall) -> dict[str, str]:
        """``compiler_flags`` as CFLAGS/CXXFLAGS.

        Six AHRL units need ``-Wno-*`` to build against a modern toolchain, and
        AHRL carries them as shell string-mangling. Declaring them means the
        flags are catalog data a reviewer can see, and the day a compiler stops
        needing one it is deleted from a manifest rather than hunted for in a
        script.
        """
        if not block.compiler_flags:
            return {}
        flags = " ".join(block.compiler_flags)
        return {"CFLAGS": flags, "CXXFLAGS": flags}

    def _build_commands(
        self,
        manifest: PackageManifest,
        block: SourceInstall,
        layout: SourceLayout,
    ) -> list[Command]:
        env = self._compiler_env(block)
        args = list(block.configure_args)
        name = manifest.name
        jobs = str(self.jobs)

        if block.build_system == "cmake":
            return [
                Command(
                    argv=(
                        "cmake",
                        "-S",
                        str(layout.src),
                        "-B",
                        str(layout.build),
                        f"-DCMAKE_INSTALL_PREFIX={self.prefix}",
                        "-DCMAKE_BUILD_TYPE=Release",
                        *args,
                    ),
                    description=f"Configure {name} with cmake",
                    env=env,
                ),
                Command(
                    argv=("cmake", "--build", str(layout.build), "--parallel", jobs),
                    description=f"Compile {name}",
                    env=env,
                ),
                Command(
                    argv=("cmake", "--install", str(layout.build)),
                    description=f"Install {name} into {self.prefix}",
                    requires_root=True,
                ),
            ]

        if block.build_system == "autotools":
            return [
                Command(
                    argv=("./configure", f"--prefix={self.prefix}", *args),
                    description=f"Configure {name}",
                    env=env,
                    cwd=layout.src,
                ),
                Command(
                    argv=("make", "-j", jobs),
                    description=f"Compile {name}",
                    env=env,
                    cwd=layout.src,
                ),
                Command(
                    argv=("make", "install"),
                    description=f"Install {name} into {self.prefix}",
                    requires_root=True,
                    cwd=layout.src,
                ),
            ]

        if block.build_system == "qmake":
            # `project_file` exists because MSHV needs a different .pro per
            # architecture; without it qmake picks the only one in the tree.
            project = [block.project_file] if block.project_file else []
            return [
                Command(
                    argv=("qmake", *project, f"PREFIX={self.prefix}", *args),
                    description=f"Configure {name} with qmake",
                    env=env,
                    cwd=layout.src,
                ),
                Command(
                    argv=("make", "-j", jobs),
                    description=f"Compile {name}",
                    env=env,
                    cwd=layout.src,
                ),
                Command(
                    argv=("make", "install"),
                    description=f"Install {name} into {self.prefix}",
                    requires_root=True,
                    cwd=layout.src,
                ),
            ]

        # `make`: no configure step at all.
        return [
            Command(
                argv=("make", "-j", jobs, *block.build_args),
                description=f"Compile {name}",
                env=env,
                cwd=layout.src,
            ),
            Command(
                argv=("make", "install", f"PREFIX={self.prefix}"),
                description=f"Install {name} into {self.prefix}",
                requires_root=True,
                cwd=layout.src,
            ),
        ]
