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
from collections.abc import Callable
from pathlib import Path

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
    *, name: str, placements: list[Placement], src: Path, prefix: Path
) -> list[Action | Command]:
    """One privileged ``install`` per placed file, from the unpacked tree."""
    steps: list[Action | Command] = []
    for placement in placements:
        dest = under_prefix(placement.dest, prefix)
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
    staging.mkdir(parents=True, exist_ok=True)
    os.chmod(staging, 0o700)
    for name, body in (("wrapper", wrapper), ("policy", policy)):
        target = staging / name
        target.unlink(missing_ok=True)
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "w") as handle:
            handle.write(body)
    return f"staged the wrapper and the polkit action in {staging} (mode 0600, read by the next commands)"


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
) -> list[Action | Command]:
    """The steps that install the helper, or the one that says it is left alone.

    *src* is the unpacked archive's root. *policy_dest* defaults to the polkit
    action's fixed path and exists so a test can write it somewhere it may.
    """
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
