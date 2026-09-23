# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The privileged artefacts ``hardware apply`` installs for power control. D-056."""

from __future__ import annotations

import os
import shlex
import stat as stat_module
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "ACTION_ID",
    "HELPER_PATH",
    "POLICY_PATH",
    "PolkitArtifacts",
    "plan_polkit",
    "policy_xml",
    "wrapper_script",
    "writable_by_non_root",
]

HELPER_PATH = "/usr/local/libexec/hammunition-devctl"
"""Where pkexec is pointed. A fixed path under the shared prefix, because a
polkit action annotates an absolute executable and a venv's path is not one
an operator's policy file should have to follow across an upgrade."""

ACTION_ID = "com.chiefgyk3d.hammunition.devctl"
POLICY_PATH = f"/usr/share/polkit-1/actions/{ACTION_ID}.policy"


def wrapper_script(interpreter: str) -> str:
    """A small POSIX shell wrapper that execs the helper's module.

    Needed because polkit annotates an *absolute executable path* and the
    package's own entry point may live in a venv that root's PATH knows
    nothing about, at a path that changes when the engine is reinstalled.
    The wrapper is the fixed thing the policy names; the interpreter inside it
    is rewritten by the next ``apply``.
    """
    return (
        "#!/bin/sh\n"
        "# Installed by `hammunition hardware apply` (D-056). Do not edit: the\n"
        "# polkit action at "
        + POLICY_PATH
        + "\n# authorises this exact path, and the next apply rewrites this file.\n"
        "exec " + shlex.quote(interpreter) + ' -m hammunition.cli.devctl "$@"\n'
    )


def policy_xml() -> str:
    """One action, authorising one executable. The battery applet's shape.

    ``auth_self_keep`` on an active session: the operator authenticates once
    and the session stays authorised, because a tray switch that asks for a
    password on every flip is a tray switch nobody uses. Inactive and remote
    sessions get ``auth_admin``, because parking someone else's GPS over SSH
    is not a thing a password prompt should make easy.
    """
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE policyconfig PUBLIC
 "-//freedesktop//DTD PolicyKit Policy Configuration 1.0//EN"
 "http://www.freedesktop.org/standards/PolicyKit/1.0/policyconfig.dtd">
<policyconfig>
  <vendor>Hammunition</vendor>
  <vendor_url>https://github.com/ChiefGyk3D/Hammunition</vendor_url>
  <action id="{ACTION_ID}">
    <description>Park or wake a radio device</description>
    <message>Authentication is required to change a device's power state</message>
    <icon_name>preferences-system-power</icon_name>
    <defaults>
      <allow_any>auth_admin</allow_any>
      <allow_inactive>auth_admin</allow_inactive>
      <allow_active>auth_self_keep</allow_active>
    </defaults>
    <annotate key="org.freedesktop.policykit.exec.path">{HELPER_PATH}</annotate>
    <annotate key="org.freedesktop.policykit.exec.allow_gui">true</annotate>
  </action>
</policyconfig>
"""


def writable_by_non_root(
    path: str | Path, *, stat_fn: Callable[[str], os.stat_result] = os.stat
) -> str | None:
    """The first component from ``path`` up to the filesystem root that a
    non-root account could modify, or ``None`` if every one of them is closed.

    ``stat_fn`` defaults to :func:`os.stat` and exists so this can be proven
    against a synthetic tree in a test — an unprivileged dev machine and an
    unprivileged CI run both lack any real root-owned file to test the "safe"
    answer against.

    D-056's ruling: the wrapper execs this path (or a path under the
    ``hammunition`` package directory) *as root*, through a polkit action that
    an active local session can satisfy once and keep for the rest of that
    session. If any component from the target up to ``/`` is owned by anyone
    but root, or is group- or other-writable, that account can replace what
    root runs the next time the action fires — which is the ordinary shape of
    a venv this project's own operator owns, not an exotic attack. Checked
    component by component, not only the leaf: a root-owned file inside a
    directory somebody else can write to is exactly as replaceable as the
    file itself.
    """
    current = Path(path)
    chain = [current, *current.parents]
    for component in chain:
        try:
            info = stat_fn(str(component))
        except OSError:
            # Cannot be stat'd, so cannot be proven safe either.
            return str(component)
        if info.st_uid != 0 or info.st_mode & (stat_module.S_IWGRP | stat_module.S_IWOTH):
            return str(component)
    return None


@dataclass(frozen=True)
class PolkitArtifacts:
    """The two files power control needs on the machine, and whether they are current."""

    helper_path: str
    helper_content: str
    policy_path: str
    policy_content: str
    helper_current: bool
    policy_current: bool

    interpreter: str
    """The interpreter path baked into the wrapper. Disclosed in the plan
    before it is ever written (D-056's ruling) — it is what the polkit action
    will let root run."""

    unsafe_interpreter: str | None
    """:func:`writable_by_non_root` on the interpreter's resolved real path,
    or ``None`` when every component up to ``/`` is closed to non-root."""

    unsafe_package: str | None
    """The same check against the ``hammunition`` package's own directory —
    the code the wrapper imports and runs as root, independent of which
    interpreter runs it."""

    @property
    def is_noop(self) -> bool:
        return self.helper_current and self.policy_current

    @property
    def needs_confirmation(self) -> bool:
        """True when installing the helper would authorise root to run code
        from a tree a non-root account can modify.

        D-056's ruling is explicit: this is never refused outright — it is
        the normal shape of a venv the operator owns — but it is never waved
        through by ``--yes`` either (D-021).
        """
        return self.unsafe_interpreter is not None or self.unsafe_package is not None


def _current(path: str, content: str) -> bool:
    try:
        return Path(path).read_text() == content
    except (OSError, UnicodeDecodeError):
        return False


def _package_dir() -> str:
    """The ``hammunition`` package's own directory — two parents up from this
    file (``.../hammunition/hardware/polkit.py`` → ``.../hammunition``)."""
    return str(Path(__file__).resolve().parent.parent)


def plan_polkit(interpreter: str | None = None) -> PolkitArtifacts:
    """What an apply would install, and whether it is already installed.

    ``interpreter`` defaults to the interpreter running this process, which is
    by construction the one that can import the package. The wrapper bakes in
    exactly what is passed (or ``sys.executable``) unresolved — what actually
    runs when the wrapper is exec'd — while the safety check below resolves
    symlinks first, because a symlink is exactly the kind of component that
    can make an unsafe target look closed.
    """
    python = interpreter or sys.executable
    helper = wrapper_script(python)
    policy = policy_xml()
    return PolkitArtifacts(
        helper_path=HELPER_PATH,
        helper_content=helper,
        policy_path=POLICY_PATH,
        policy_content=policy,
        helper_current=_current(HELPER_PATH, helper),
        policy_current=_current(POLICY_PATH, policy),
        interpreter=python,
        unsafe_interpreter=writable_by_non_root(os.path.realpath(python)),
        unsafe_package=writable_by_non_root(_package_dir()),
    )
