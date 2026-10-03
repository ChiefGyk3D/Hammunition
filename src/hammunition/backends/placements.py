# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Spreading an unpacked archive's files, and installing the tray's helper.

The steps behind ``placements`` and ``devctl_helper`` on a ``binary`` block
(hammunition-tray 0.5.0, whose release published no ``.deb``). Everything is a
printed command in the engine's one vocabulary: ``install -D -m MODE SRC DEST``
for a file (which is exactly the argv the uninstall attribution replays, so
removal rests on the log), ``install -d`` for a directory, and an in-process
action only for what has no honest argv -- rendering the wrapper and policy
into a staging directory, and reading the helper's answer back.
"""

from __future__ import annotations

import os
import tarfile
import zipfile
from collections.abc import Callable, Collection, Mapping
from pathlib import Path

from hammunition import devctl_helper
from hammunition.devctl_helper import (
    ENTRY_NAME,
    HELPER_PATH,
    LIBDIR,
    PACKAGE_DIR,
    POLICY_PATH,
    HelperPlan,
    under_prefix,
    wrapper_script,
)
from hammunition.manifest.schema import DevctlHelper, Placement

from .base import Action, BackendError, Command
from .source import needs_root_for

__all__ = ["helper_steps", "placement_steps"]


def placement_steps(
    *,
    name: str,
    placements: list[Placement],
    src: Path,
    prefix: Path,
    owners: Callable[[Collection[str]], Mapping[str, str]] | None = None,
) -> list[Action | Command]:
    """One privileged ``install`` per placed file, from the unpacked tree.

    A file some package already owns is never written over (CLAUDE.md, D-022):
    ``dpkg-query -S`` is asked about every destination first, and the step list
    is refused by name, with the remedy, rather than leaving a file two owners
    fight over. The 0.4.0 tray units were ``.deb``s, so a machine that installed
    one meets this exactly once.
    """
    steps: list[Action | Command] = []
    dests = {placement.dest: under_prefix(placement.dest, prefix) for placement in placements}
    owned = (owners or devctl_helper.dpkg_owners)([str(d) for d in dests.values()])
    clashes = {str(dest): owned[str(dest)] for dest in dests.values() if str(dest) in owned}
    if clashes:
        packages = sorted(set(clashes.values()))
        raise BackendError(
            f"{name} would write over files that the {', '.join(packages)} package"
            f"{'s' if len(packages) > 1 else ''} owns "
            f"({', '.join(sorted(clashes)[:3])}{', ...' if len(clashes) > 3 else ''}): this "
            f"engine never overwrites a package's file. Remove the package first "
            f"(`sudo apt-get remove {' '.join(packages)}`), then install {name} again."
        )
    for placement in placements:
        dest = dests[placement.dest]
        steps.append(
            Command(
                argv=(
                    "install",
                    "-D",
                    "-m",
                    placement.mode,
                    str(src / placement.source),
                    str(dest),
                ),
                description=f"Install {name}'s {placement.source} at {dest}",
                requires_root=needs_root_for(dest.parent)
                or not os.access(_existing(dest), os.W_OK),
            )
        )
    return steps


def _existing(path: Path) -> Path:
    """The nearest ancestor of *path* that exists."""
    probe = path.parent
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    return probe


def _stage(staging: Path, wrapper: str, policy: str) -> str:
    """Write the two rendered files into a fresh directory only this process made.

    The directory is removed and recreated through the descriptor of its parent
    (the engine's own safe removal), then opened ``O_NOFOLLOW`` and written by
    descriptor, so a symlink put where the directory was cannot send a root
    process's write, or its ``unlink``, anywhere else.
    """
    from hammunition.fetch import operator_dir, remove_tree

    with operator_dir(staging.parent) as parent_fd:
        if staging.is_symlink():
            # The link goes, never what it points at.
            if parent_fd is None:
                staging.unlink()
            else:
                os.unlink(staging.name, dir_fd=parent_fd)
        remove_tree(staging.parent, parent_fd, staging.name)
        if parent_fd is None:
            staging.mkdir(mode=0o700)
        else:
            os.mkdir(staging.name, 0o700, dir_fd=parent_fd)
    directory = os.open(staging, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        # Semgrep: a deliberate mode (0755/0644 on installed files and launchers, 0700 private); nothing group- or world-writable.
        # nosemgrep: python.lang.security.audit.insecure-file-permissions.insecure-file-permissions
        os.fchmod(directory, 0o700)
        for name, body in (("wrapper", wrapper), ("policy", policy)):
            descriptor = os.open(
                name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=directory,
            )
            with os.fdopen(descriptor, "w") as handle:
                handle.write(body)
    finally:
        os.close(directory)
    return f"staged the wrapper and the polkit action in {staging} (mode 0600, read by the next commands)"


def _archive_member(archive: Path, relative: str) -> bytes:
    """The bytes of *relative* in *archive*, where the archive's one top-level
    directory (stripped on unpacking) is not part of the name."""

    def matches(name: str) -> bool:
        return name == relative or name.split("/", 1)[-1] == relative

    if tarfile.is_tarfile(archive):
        with tarfile.open(archive) as tar:
            for member in tar.getmembers():
                if member.isfile() and matches(member.name):
                    handle = tar.extractfile(member)
                    if handle is not None:
                        return handle.read()
    elif zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as bundle:
            for name in bundle.namelist():
                if matches(name):
                    return bundle.read(name)
    raise BackendError(f"{relative} is not in the verified archive {archive.name}")


def _verify_installed_code(archive: Path, helper: DevctlHelper, entry: Path, package: Path) -> str:
    """The root-owned copies are the verified archive's bytes, file for file.

    The archive is hash-checked when it is fetched; what root copies is the
    unpacked tree in the operator's cache, which is not. Reading each installed
    file back against the archive closes that gap, and it runs before the wrapper
    polkit authorises is installed, so a mismatch leaves nothing that can be run
    through the action.
    """
    pairs = [(entry, f"{helper.source}/{ENTRY_NAME}")] + [
        (package / module, f"{helper.source}/{PACKAGE_DIR}/{module}") for module in helper.modules
    ]
    for installed, relative in pairs:
        if installed.read_bytes() != _archive_member(archive, relative):
            raise BackendError(
                f"{installed} differs from {relative} in the verified archive "
                f"{archive.name}: the unpacked tree changed between unpacking and the copy. "
                f"The wrapper was not installed; remove {installed.parent} and run again."
            )
    return f"{len(pairs)} installed files equal the verified archive's"


def helper_steps(
    *,
    name: str,
    helper: DevctlHelper,
    plan: HelperPlan,
    src: Path,
    staging: Path,
    prefix: Path,
    policy_dest: Path | None = None,
    probe: Callable[[str], str | None] | None = None,
    archive: Callable[[], Path] | None = None,
) -> list[Action | Command]:
    """The steps that install the helper, or the one that says it is left alone.

    *src* is the unpacked archive's root. *policy_dest* defaults to the polkit
    action's fixed path and exists so a test can write it somewhere it may.
    *archive* names the verified archive on disk once it is fetched; with it the
    installed code is compared with the archive's own bytes before the wrapper
    is installed.
    """
    if plan.problem is not None:
        raise BackendError(plan.problem)
    if not plan.install:
        message = (
            f"left alone: the helper at {HELPER_PATH} is owned by {plan.owner}"
            + (f" and answers {plan.version!r}" if plan.version else "")
            + "; this unit installs nothing of it"
        )
        return [
            Action(
                kind="devctl-helper-kept",
                description=f"Leave the device helper where it is ({name})",
                detail=message,
                perform=lambda: message,
            )
        ]

    from hammunition.hardware.polkit import policy_xml

    libdir = under_prefix(LIBDIR, prefix)
    wrapper_dest = under_prefix(HELPER_PATH, prefix)
    policy = policy_dest if policy_dest is not None else Path(POLICY_PATH)
    entry = libdir / ENTRY_NAME
    package = libdir / PACKAGE_DIR
    code = src / helper.source
    wrapper_text = wrapper_script(plan.interpreter, str(entry))
    policy_text = policy_xml()

    def root(path: Path) -> bool:
        return needs_root_for(path) or not os.access(_existing(path), os.W_OK)

    steps: list[Action | Command] = [
        Action(
            kind="devctl-stage",
            description=f"Render the device helper's wrapper and polkit action ({name})",
            detail=(
                f"staged in {staging}; the wrapper runs {plan.interpreter} as root through "
                f"{HELPER_PATH}, so it is disclosed here before it is written"
            ),
            perform=lambda: _stage(staging, wrapper_text, policy_text),
        ),
        Command(
            argv=("rm", "-rf", "--", str(package)),
            description=(
                f"Clear the helper's old modules ({plan.owner}); a module an older pin "
                f"shipped and this one does not must not survive"
            ),
            requires_root=root(package),
        ),
        Command(
            argv=("install", "-d", "-m", "0755", str(libdir), str(package)),
            description=f"Create the helper's root-owned code directory {libdir}",
            requires_root=root(libdir),
        ),
        Command(
            argv=("install", "-D", "-m", "0755", str(code / ENTRY_NAME), str(entry)),
            description=f"Install the helper's entry script as {entry}",
            requires_root=root(entry),
        ),
    ]
    for module in helper.modules:
        steps.append(
            Command(
                argv=(
                    "install",
                    "-D",
                    "-m",
                    "0644",
                    str(code / PACKAGE_DIR / module),
                    str(package / module),
                ),
                description=f"Install the helper module {module} (copied, never run from the unpack)",
                requires_root=root(package),
            )
        )
    if archive is not None:
        steps.append(
            Action(
                kind="devctl-source-verify",
                description=f"Compare the installed helper code with the verified archive ({name})",
                detail=(
                    f"{entry} and {package}/*.py against the archive's own bytes, before the "
                    f"wrapper that polkit authorises is installed"
                ),
                perform=lambda: _verify_installed_code(archive(), helper, entry, package),
            )
        )
    steps.append(
        Command(
            argv=("install", "-D", "-m", "0755", str(staging / "wrapper"), str(wrapper_dest)),
            description=(
                f"Install the wrapper polkit authorises at {wrapper_dest} "
                f"(runs {plan.interpreter} -I {entry} as root)"
            ),
            requires_root=root(wrapper_dest),
        )
    )
    steps.append(
        Command(
            argv=("install", "-D", "-m", "0644", str(staging / "policy"), str(policy)),
            description=f"Install the polkit action com.chiefgyk3d.hammunition.devctl at {policy}",
            requires_root=root(policy),
        )
    )

    def verify() -> str:
        from hammunition.hardware import polkit

        for installed, expected in ((wrapper_dest, wrapper_text), (policy, policy_text)):
            if installed.read_text() != expected:
                raise BackendError(
                    f"{installed} is not what was staged for it: it changed between the "
                    f"staging step and the install. Remove it and run again."
                )
        answer = (probe or polkit.installed_helper_version)(str(wrapper_dest))
        if answer is None:
            raise BackendError(
                f"{wrapper_dest} was installed but does not answer --version with "
                f"`hammunition-devctl contract N`: the wrapper's interpreter "
                f"({plan.interpreter}) or the helper's code did not start. Run "
                f"`{wrapper_dest} --version` to see why."
            )
        return f"{wrapper_dest} --version answers {answer!r}"

    steps.append(
        Action(
            kind="devctl-verify",
            description=f"Read the installed helper's contract back ({name})",
            detail=f"{wrapper_dest} --version, unprivileged, one argument",
            perform=verify,
        )
    )
    return steps
