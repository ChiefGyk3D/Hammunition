# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Building from a verified source archive.  DESIGN.md §6, D-004.

**This is the backend the project exists for.** 57 of AHRL's 95 units cannot be
satisfied by apt and 35 of those are source builds from bundled tarballs; an
apt-only tool covers roughly 40% of the parity target and the missing 60% is
precisely what users cannot install for themselves.

The build systems implemented here are the ones the catalog actually needs,
counted rather than assumed (**D-014**): **cmake 11, autotools 9, make 4,
qmake 3, qmake6 1** across the twenty-eight `source` and `git` blocks in the
catalog today. ``qmake6`` is a separate entry rather than a flag on ``qmake``
because it is a different binary: Debian 13 with only ``qt6-base-dev``
installed has no ``/usr/bin/qmake`` at all, and installing ``qt5-qmake`` to
supply the name would hand a Qt6 project the Qt5 tool.
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
archive exists.** Extraction strips a single top-level directory into
``<build>/src`` when the archive has exactly one — nearly every release tarball
does — and unpacks as-is when it does not, which some zips (linrad's, for one)
require. Either way the source root is ``<build>/src``, so ``./configure`` and
``cmake -S`` can be rendered with real
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
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from hammunition.fetch import Fetcher
from hammunition.manifest.schema import Binary, PackageManifest, Patch, SourceInstall

from .base import Action, BackendError, Command

__all__ = [
    "DEFAULT_PREFIX",
    "IMPLEMENTED_BUILD_SYSTEMS",
    "SourceBackend",
    "SourceLayout",
    "build_commands",
    "extract",
    "install_binary_commands",
    "needs_root_for",
    "patch_steps",
    "prepare_tree",
    "tree_destination",
    "tree_install_commands",
]

#: FHS: locally-built software goes in /usr/local, where it does not collide
#: with anything the distribution's package manager owns.
DEFAULT_PREFIX = Path("/usr/local")

#: Counted from the catalog, not assumed (D-014). `custom` is a measured zero
#: and is refused by name.
IMPLEMENTED_BUILD_SYSTEMS = frozenset({"autotools", "cmake", "qmake", "qmake6", "make"})

_TAR_SUFFIXES = (".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tbz", ".tar.xz", ".txz", ".tar")


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


def _sniff(archive: Path) -> str | None:
    """``"tar"``, ``"zip"``, or None — from the bytes, not the name.

    The artifact cache names files by digest plus whatever the URL ended in,
    and a SourceForge URL ends in ``/download`` — MSHV's fetch verified
    cleanly and then could not be unpacked because the *name* said nothing
    (found 2026-08-30). The content is the authority; the suffix check
    remains only as the fallback for a bare uncompressed tar, whose 257-byte
    magic offset an empty-ish file may not reach.
    """
    with archive.open("rb") as handle:
        head = handle.read(6)
        handle.seek(257)
        ustar = handle.read(5)
    if head[:4] == b"PK\x03\x04":
        return "zip"
    if head[:2] == b"\x1f\x8b" or head[:3] == b"BZh" or head[:6] == b"\xfd7zXZ\x00":
        return "tar"
    if ustar == b"ustar":
        return "tar"
    return None


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


def prepare_tree(destination: Path) -> str:
    """Remove any previous tree at *destination* and recreate it empty.

    Idempotent (CLAUDE.md): a re-run builds from a clean tree rather than
    layering a new checkout or archive over a half-built one, where a stale
    object file outlives the source it came from.
    """
    existed = destination.exists()
    if existed:
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    return f"{'cleared and recreated' if existed else 'created'} {destination}"


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
        kind = _sniff(archive)
        if kind == "tar" or (kind is None and _is_tar(archive.name)):
            with tarfile.open(archive) as tar:
                # PEP 706. Refuses absolute paths, `..`, links pointing outside
                # the destination, device nodes, and setuid/setgid bits.
                tar.extractall(staging, filter="data")
                count = len(tar.getnames())
        elif kind == "zip" or (kind is None and _is_zip(archive.name)):
            with zipfile.ZipFile(archive) as archive_zip:
                names = archive_zip.namelist()
                _safe_members(names, staging)
                archive_zip.extractall(staging)
                count = len(names)
                # Python's zipfile discards the unix mode bits a zip records
                # in external_attr, so an executable `configure` arrives
                # unrunnable (linrad's zip proved it -- AHRL's script chmods
                # by hand for the same reason). Restore what the archive
                # actually recorded; never invent a bit it did not carry.
                for info in archive_zip.infolist():
                    mode = (info.external_attr >> 16) & 0o777
                    if mode:
                        os.chmod(staging / info.filename, mode)
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
        steps.extend(patch_steps(manifest.name, block.patches, layout))
        steps.extend(self._build_commands(manifest, block, layout))
        return steps

    def _fetch(self, manifest: PackageManifest, block: SourceInstall) -> str:
        result = self.fetcher.fetch(block.source)
        where = "cached" if result.from_cache else "downloaded"
        return f"{where} {result.size} bytes, sha256 {result.sha256[:12]}… verified"

    def _build_commands(
        self,
        manifest: PackageManifest,
        block: SourceInstall,
        layout: SourceLayout,
    ) -> list[Command]:
        commands = build_commands(
            name=manifest.name,
            build_system=block.build_system,
            layout=layout,
            prefix=self.prefix,
            jobs=self.jobs,
            configure_args=block.configure_args,
            compiler_flags=block.compiler_flags,
            project_file=block.project_file,
            build_args=block.build_args,
            provides_install_target=block.provides_install_target,
            binaries=manifest.binaries,
            autoreconf=block.autoreconf,
        )
        if block.install_tree:
            commands.extend(
                tree_install_commands(
                    name=manifest.name, source_tree=layout.src, prefix=self.prefix
                )
            )
        return commands


#: Directories where installing is a system-wide change. FHS, plus /opt.
SYSTEM_ROOTS = (Path("/usr"), Path("/opt"), Path("/srv"), Path("/etc"), Path("/var"))


def needs_root_for(prefix: Path) -> bool:
    """Whether installing into *prefix* is a privileged, system-wide change.

    A property of the **destination**, not of the process asking. That
    distinction is the whole point, and the first version of this function got
    it wrong: it asked ``os.access(prefix, W_OK)``, which answers "can *I* write
    here" — so under sudo, and in every one of our root-running target
    containers, ``/usr/local`` came back writable and the install step declared
    it needed no privilege. Six container jobs caught it that the dev machine
    could not, because the dev machine is not root.

    :class:`Command` already states the rule this restores: *already being root
    is not the same as not needing root*, so the flag stays true and only the
    ``sudo`` prefix disappears when the euid is 0.

    Deciding from the path also makes the answer the same on every machine,
    which a plan that must be printed and compared needs it to be.
    """
    resolved = prefix.resolve()
    return any(resolved == root or root in resolved.parents for root in SYSTEM_ROOTS)


def _compiler_env(compiler_flags: Sequence[str]) -> dict[str, str]:
    """``compiler_flags`` as CFLAGS/CXXFLAGS/CPPFLAGS in the environment.

    Six AHRL units need ``-Wno-*`` to build against a modern toolchain, and AHRL
    carries them as shell string-mangling. Declaring them means the flags are
    catalog data a reviewer can see, and the day a compiler stops needing one it
    is deleted from a manifest rather than hunted for in a script.

    All three variables, because make's precedence makes any single one a
    gamble: a Makefile that assigns ``CFLAGS = -g`` (ardopcf does) silently
    discards the environment's CFLAGS, but the same Makefile *appends* with
    ``CPPFLAGS += -Isrc``, and an appended variable starts from the
    environment — so the flag arrives through CPPFLAGS with the include path
    intact. Found when ardopcf's first real engine build failed on Parrot with
    the exact error its flag exists to silence. Passing flags as command-line
    ``make`` arguments instead would override appends entirely and drop
    upstream's own values, which is worse.
    """
    if not compiler_flags:
        return {}
    flags = " ".join(compiler_flags)
    return {"CFLAGS": flags, "CXXFLAGS": flags, "CPPFLAGS": flags}


def install_binary_commands(
    *,
    name: str,
    layout: SourceLayout,
    prefix: Path,
    binaries: Sequence[Binary],
) -> list[Command]:
    """Install named build outputs, for a project whose build has no install rule.

    Two of the catalog's qmake units -- MSHV and Coil64 -- ship a ``.pro`` with
    no ``INSTALLS``, so ``make install`` has nothing to do and fails. AHRL's
    answer is to leave the binary in the build tree and generate a launcher
    that ``cd``s into it, which is why its menu entries carry working
    directories. Copying the declared binary into the prefix is the better
    answer and it is what makes the `binaries` field mean something rather than
    being documentation.

    `install -D` creates the target directory, so no separate mkdir is needed.
    """
    return [
        Command(
            argv=(
                "install",
                "-D",
                "-m",
                "0755",
                str(layout.src / binary.produced),
                str(prefix / "bin" / binary.install_as),
            ),
            description=f"Install {name}'s {binary.produced} as {binary.install_as}",
            requires_root=needs_root_for(prefix),
        )
        for binary in binaries
    ]


def tree_install_commands(*, name: str, source_tree: Path, prefix: Path) -> list[Command]:
    """Install the whole tree to ``<prefix>/share/hammunition/<name>``.

    For software that reads settings, resources or data beside its executable
    (source-build-gaps #6 and #8 -- MSHV, run-in-place Python and Java
    trees). ``cp -aT`` replaces content in place; the target is wholly ours,
    under our own share/ namespace, so clearing it first is safe and keeps a
    re-run from accumulating files upstream deleted.
    """
    destination = prefix / "share" / "hammunition" / name
    privileged = needs_root_for(prefix)
    return [
        Command(
            argv=("rm", "-rf", "--", str(destination)),
            description=f"Clear any previous {name} tree",
            requires_root=privileged,
        ),
        Command(
            argv=("install", "-d", str(destination.parent)),
            description=f"Ensure {destination.parent} exists",
            requires_root=privileged,
        ),
        Command(
            argv=("cp", "-aT", str(source_tree), str(destination)),
            description=f"Install the {name} tree into {destination}",
            requires_root=privileged,
        ),
    ]


def tree_destination(prefix: Path, name: str) -> Path:
    """Where :func:`tree_install_commands` puts *name*'s tree."""
    return prefix / "share" / "hammunition" / name


def write_patch(path: Path, diff: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(diff if diff.endswith("\n") else diff + "\n")
    return f"staged patch at {path}"


def patch_steps(
    name: str,
    patches: Sequence[Patch],
    layout: SourceLayout,
) -> list[Action | Command]:
    """Stage each declared diff and apply it with patch(1), in order.

    Implemented the day the measured zero ended: linrad's Makefile bakes
    -Werror into a literal flag string with no variable to override, so it
    cannot ship without an in-tree edit (source-build-gaps #2). AHRL does
    these edits with sed at install time; a declared unified diff is
    reviewable in the catalog and fails loudly when upstream moves the code
    it touches. Idempotent the same way builds are: the tree is cleared and
    re-extracted every run, so a patch never applies twice. Manifests with
    patches must carry `patch` in build_depends.
    """
    from functools import partial

    steps: list[Action | Command] = []
    for index, declared in enumerate(patches):
        if not declared.unified_diff:
            raise BackendError(
                f"{name}: patch for {declared.file!r} declares no unified_diff — a "
                f"description alone cannot be applied, and building unpatched source "
                f"would produce a binary the manifest does not describe"
            )
        staged = layout.root / "patches" / f"{index:02d}-{Path(declared.file).name}.diff"
        steps.append(
            Action(
                kind="patch",
                description=f"Stage the {declared.file} patch: {declared.description}",
                detail=str(staged),
                perform=partial(write_patch, staged, declared.unified_diff),
            )
        )
        steps.append(
            Command(
                argv=("patch", "-p1", "-i", str(staged)),
                description=f"Apply it to {declared.file}",
                cwd=layout.src,
            )
        )
    return steps


def build_commands(
    *,
    name: str,
    build_system: str,
    layout: SourceLayout,
    prefix: Path,
    jobs: int,
    configure_args: Sequence[str] = (),
    compiler_flags: Sequence[str] = (),
    project_file: str | None = None,
    build_args: Sequence[str] = (),
    provides_install_target: bool = True,
    binaries: Sequence[Binary] = (),
    autoreconf: bool = False,
) -> list[Command]:
    """Configure, compile and install, for one build system.

    Shared by the source and git backends, because how a tree *arrived* — an
    archive verified by digest, or a clone pinned to a revision — says nothing
    about how it is built. Keeping one copy is what stops the two drifting into
    subtly different builds of the same software.

    Only the final command is privileged. CLAUDE.md drops to the operator
    wherever possible, and a build run wholly as root would leave a tree of
    root-owned objects in the operator's cache for no benefit.
    """
    env = _compiler_env(compiler_flags)
    args = list(configure_args)
    jobs_arg = str(jobs)
    privileged = needs_root_for(prefix)
    # A project with no install rule gets an explicit copy of what it emits
    # instead of a `make install` that would fail. The schema refuses the
    # combination of no-install-target and no declared binaries.
    explicit = (
        install_binary_commands(name=name, layout=layout, prefix=prefix, binaries=binaries)
        if not provides_install_target
        else None
    )
    if build_system == "cmake":
        return [
            Command(
                argv=(
                    "cmake",
                    "-S",
                    str(layout.src),
                    "-B",
                    str(layout.build),
                    f"-DCMAKE_INSTALL_PREFIX={prefix}",
                    "-DCMAKE_BUILD_TYPE=Release",
                    *args,
                ),
                description=f"Configure {name} with cmake",
                env=env,
                # cwd matters even with -S/-B: execute_process() children in
                # the project's CMakeLists inherit it, and rtlsdr-airband's
                # version script runs `git describe` from wherever that is.
                # Undefined cwd made the answer depend on where the engine
                # happened to be started (measured 2026-08-30).
                cwd=layout.src,
            ),
            Command(
                argv=("cmake", "--build", str(layout.build), "--parallel", jobs_arg),
                description=f"Compile {name}",
                env=env,
            ),
            *(
                explicit
                if explicit is not None
                else [
                    Command(
                        argv=("cmake", "--install", str(layout.build)),
                        description=f"Install {name} into {prefix}",
                        requires_root=privileged,
                    )
                ]
            ),
        ]

    if build_system == "autotools":
        return [
            *(
                [
                    Command(
                        argv=("autoreconf", "-fi"),
                        description=f"Generate {name}'s configure (autoreconf -fi)",
                        env=env,
                        cwd=layout.src,
                    )
                ]
                if autoreconf
                else []
            ),
            Command(
                argv=("./configure", f"--prefix={prefix}", *args),
                description=f"Configure {name}",
                env=env,
                cwd=layout.src,
            ),
            Command(
                # build_args reach make here too (gap #1: linrad's build is
                # ./configure then `make xlinrad64` -- a bare make prints usage
                # and stops).
                argv=("make", "-j", jobs_arg, *build_args),
                description=f"Compile {name}",
                env=env,
                cwd=layout.src,
            ),
            *(
                explicit
                if explicit is not None
                else [
                    Command(
                        argv=("make", "install"),
                        description=f"Install {name} into {prefix}",
                        requires_root=privileged,
                        cwd=layout.src,
                    )
                ]
            ),
        ]

    if build_system in {"qmake", "qmake6"}:
        # `project_file` exists because MSHV needs a different .pro per
        # architecture; without it qmake picks the only one in the tree.
        #
        # qmake6 is a separate build system rather than a detail, because it is
        # a different binary and the choice is a fact about the project. On
        # Debian 13 with only qt6-base-dev installed there is no `qmake` at all
        # -- only `/usr/bin/qmake6` -- and installing `qt5-qmake` to provide the
        # name would hand a Qt6 project the Qt5 tool. Measured 2026-08-28.
        project = [project_file] if project_file else []
        return [
            Command(
                argv=(build_system, *project, f"PREFIX={prefix}", *args),
                description=f"Configure {name} with {build_system}",
                env=env,
                cwd=layout.src,
            ),
            Command(
                # build_args reach make here too (gap #1: linrad's build is
                # ./configure then `make xlinrad64` -- a bare make prints usage
                # and stops).
                argv=("make", "-j", jobs_arg, *build_args),
                description=f"Compile {name}",
                env=env,
                cwd=layout.src,
            ),
            *(
                explicit
                if explicit is not None
                else [
                    Command(
                        argv=("make", "install"),
                        description=f"Install {name} into {prefix}",
                        requires_root=privileged,
                        cwd=layout.src,
                    )
                ]
            ),
        ]

    # `make`: no configure step at all.
    return [
        Command(
            argv=("make", "-j", jobs_arg, *build_args),
            description=f"Compile {name}",
            env=env,
            cwd=layout.src,
        ),
        *(
            explicit
            if explicit is not None
            else [
                Command(
                    argv=("make", "install", f"PREFIX={prefix}"),
                    description=f"Install {name} into {prefix}",
                    requires_root=privileged,
                    cwd=layout.src,
                )
            ]
        ),
    ]
