# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The privileged artefacts ``hardware apply`` installs for power control. D-056."""

from __future__ import annotations

import enum
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
    "WritabilityFinding",
    "WritabilityRisk",
    "describe_refusal",
    "plan_polkit",
    "policy_xml",
    "wrapper_script",
    "writable_by_non_root",
    "writable_including_symlink_target",
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


class WritabilityRisk(enum.Enum):
    """Two different facts, deliberately not collapsed into one boolean.

    Fix round 2's ruling: the round 1 gate treated "owned by a non-root
    account" and "writable by any local account" as the same risk, and a
    devctl startup check that hard-refused on either broke the project's own
    documented install -- a venv under ``$HOME`` is *always* owned by a
    non-root account. Only one of these two facts is the actual escalation.
    """

    OWNED_BY_NON_ROOT = "owned_by_non_root"
    """The tree belongs to one specific non-root account -- the ordinary
    shape of a venv the operator's own account created. Confirmable, never
    refused outright."""

    GROUP_OR_OTHER_WRITABLE = "group_or_other_writable"
    """*Any* local account, not just the owner, can modify the tree -- the
    real escalation. Refused outright, never merely confirmed."""


@dataclass(frozen=True)
class WritabilityFinding:
    """What :func:`writable_by_non_root` found, and how serious it is."""

    path: str
    risk: WritabilityRisk
    unstatable: bool = False
    """True when ``path`` was classified :attr:`WritabilityRisk.GROUP_OR_OTHER_WRITABLE`
    only because it could not be `stat()`'d at all (fail-closed, since it
    cannot be proven safe either) -- not because it is actually writable.
    Different fact, and the message shown for it should say so (fix round
    3): "is writable by any local account" is simply false of a component
    that could not be read at all, typically a permission problem on the way
    down rather than a loose one."""


def writable_by_non_root(
    path: str | Path, *, stat_fn: Callable[[str], os.stat_result] = os.stat
) -> WritabilityFinding | None:
    """The first offending component from ``path`` up to the filesystem
    root, classified by :class:`WritabilityRisk`, or ``None`` if every one of
    them is closed to non-root.

    ``stat_fn`` defaults to :func:`os.stat` and exists so this can be proven
    against a synthetic tree in a test — an unprivileged dev machine and an
    unprivileged CI run both lack any real root-owned file to test the "safe"
    answer against.

    D-056's ruling: the wrapper execs this path (or a path under the
    ``hammunition`` package directory) *as root*, through a polkit action that
    an active local session can satisfy once and keep for the rest of that
    session. A component that is group- or other-writable is checked across
    the *whole* chain first, and wins over a merely non-root-owned one
    regardless of which is nearer the leaf — the real escalation must never
    be masked by a nearer, milder finding. Only once nothing in the chain is
    writable by everyone does the nearest merely-non-root-owned component
    become the (confirmable) answer. A component that cannot be stat'd at all
    is treated as the severe case (:attr:`WritabilityFinding.unstatable`):
    it cannot be proven safe either, but it is a different fact from actually
    being writable, and is reported as one.
    """
    current = Path(path)
    chain = [current, *current.parents]
    stats: list[tuple[str, os.stat_result | None]] = []
    for component in chain:
        try:
            stats.append((str(component), stat_fn(str(component))))
        except OSError:
            stats.append((str(component), None))

    for name, info in stats:
        if info is None:
            return WritabilityFinding(
                name, WritabilityRisk.GROUP_OR_OTHER_WRITABLE, unstatable=True
            )
        if info.st_mode & (stat_module.S_IWGRP | stat_module.S_IWOTH):
            return WritabilityFinding(name, WritabilityRisk.GROUP_OR_OTHER_WRITABLE)

    for name, info in stats:
        if info is not None and info.st_uid != 0:
            return WritabilityFinding(name, WritabilityRisk.OWNED_BY_NON_ROOT)

    return None


def writable_including_symlink_target(
    path: str | Path,
    *,
    stat_fn: Callable[[str], os.stat_result] = os.stat,
    realpath_fn: Callable[[str], str] = os.path.realpath,
) -> WritabilityFinding | None:
    """:func:`writable_by_non_root` over ``path`` exactly as given, unioned
    with the same check over its resolved real path -- the severe class
    winning across both, exactly as it already wins within one chain.

    Fix round 3's regression: every call site checked only
    ``os.path.realpath(path)``, which resolves *through* a symlink and so
    never looks at the directory the symlink itself sits in. The wrapper
    ``exec``s (and the package is imported from) the path exactly as given,
    unresolved -- if that path is a symlink, a 0777 directory holding a
    clean symlink to an otherwise root-owned target passed the resolved-only
    check as safe, because resolution hid the one directory an attacker
    would actually use: retarget the symlink, not the root-owned file it
    used to point to. Checking only the unresolved path would just as
    wrongly miss a writable *target* the symlink already trusts (a clean
    symlink pointing at a file someone else can overwrite). Both checked;
    worse of the two wins.

    ``realpath_fn`` defaults to :func:`os.path.realpath` and, like
    ``stat_fn``, exists so this can be proven against a synthetic tree
    without touching the real filesystem at all (fix round 4: a test that
    depended on a real system path's real ownership measured the host it
    happened to run on, not the code -- true here, false inside an
    unprivileged user namespace, and would have been just as environment-
    dependent inside the seven target containers).
    """
    direct = writable_by_non_root(path, stat_fn=stat_fn)
    resolved = writable_by_non_root(realpath_fn(str(path)), stat_fn=stat_fn)
    findings = [f for f in (direct, resolved) if f is not None]
    for finding in findings:
        if finding.risk is WritabilityRisk.GROUP_OR_OTHER_WRITABLE:
            return finding
    return findings[0] if findings else None


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

    unsafe_interpreter: WritabilityFinding | None
    """:func:`writable_including_symlink_target` on the interpreter path --
    both as given and its resolved real path -- or ``None`` when every
    component of both chains is closed to non-root."""

    unsafe_package: WritabilityFinding | None
    """The same check against the ``hammunition`` package's own directory —
    the code the wrapper imports and runs as root, independent of which
    interpreter runs it."""

    @property
    def is_noop(self) -> bool:
        return self.helper_current and self.policy_current

    @property
    def _findings(self) -> tuple[WritabilityFinding, ...]:
        return tuple(f for f in (self.unsafe_interpreter, self.unsafe_package) if f is not None)

    @property
    def must_refuse(self) -> bool:
        """True when any component is group- or other-writable: *any* local
        account, not just the tree's owner, could replace what root runs
        next. That is the actual escalation, refused outright (fix round 2)."""
        return any(f.risk is WritabilityRisk.GROUP_OR_OTHER_WRITABLE for f in self._findings)

    @property
    def needs_confirmation(self) -> bool:
        """True when installing the helper would authorise root to run code
        from a tree owned by one specific non-root account -- the ordinary
        shape of a venv the operator's own account created.

        D-056's ruling is explicit: never refused outright for this alone —
        but never waved through by ``--yes`` either (D-021). Distinct from
        :attr:`must_refuse`, which is the group/other-writable case: fix
        round 1 conflated the two and broke the project's own documented
        install, which is always non-root-owned.
        """
        return any(f.risk is WritabilityRisk.OWNED_BY_NON_ROOT for f in self._findings)

    @property
    def confirmable_paths(self) -> list[str]:
        """Every path flagged :attr:`WritabilityRisk.OWNED_BY_NON_ROOT`, for
        disclosing all of them even though only the first is typed back."""
        return [f.path for f in self._findings if f.risk is WritabilityRisk.OWNED_BY_NON_ROOT]

    @property
    def refusing_paths(self) -> list[str]:
        """Every path flagged :attr:`WritabilityRisk.GROUP_OR_OTHER_WRITABLE`."""
        return [f.path for f in self._findings if f.risk is WritabilityRisk.GROUP_OR_OTHER_WRITABLE]

    @property
    def refusing_findings(self) -> list[WritabilityFinding]:
        """The full findings behind :attr:`refusing_paths`, so a caller can
        tell "actually writable" from "could not be checked at all" apart
        when it renders the refusal (fix round 3, item 6) rather than
        reporting the stronger claim for both."""
        return [f for f in self._findings if f.risk is WritabilityRisk.GROUP_OR_OTHER_WRITABLE]


def describe_refusal(findings: list[WritabilityFinding]) -> str:
    """One clause per finding, said accurately: "writable by any local
    account" only for a finding that really is, "could not be checked" for
    one that is refused merely because it could not be proven safe (fix
    round 3, item 6 -- the two are different facts, and were reported with
    the same, stronger sentence for both)."""
    clauses = []
    for finding in findings:
        if finding.unstatable:
            clauses.append(
                f"{finding.path} could not be checked (a stat failure), and is treated as unsafe until it can be"
            )
        else:
            clauses.append(f"{finding.path} is writable by any local account, not only its owner")
    return "; ".join(clauses)


def _current(path: str, content: str) -> bool:
    try:
        return Path(path).read_text() == content
    except (OSError, UnicodeDecodeError):
        return False


def _package_dir() -> str:
    """The ``hammunition`` package's own directory — two parents up from this
    file (``.../hammunition/hardware/polkit.py`` → ``.../hammunition``).

    Deliberately *not* resolved here: :func:`writable_including_symlink_target`
    checks this path and its resolved real path both, and resolving it first
    would throw away exactly the symlink-holding directory that check exists
    to catch."""
    return str(Path(os.path.abspath(__file__)).parent.parent)


def plan_polkit(interpreter: str | None = None) -> PolkitArtifacts:
    """What an apply would install, and whether it is already installed.

    ``interpreter`` defaults to the interpreter running this process, which is
    by construction the one that can import the package. The wrapper bakes in
    exactly what is passed (or ``sys.executable``) unresolved — what actually
    runs when the wrapper is exec'd. The safety check below is not "resolve
    symlinks first": it checks the unresolved path *and* its resolved real
    path, and takes the worse answer, because checking only the resolved
    path hides the directory a symlink itself sits in (fix round 3) and
    checking only the unresolved one would just as wrongly miss an unsafe
    resolved target.
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
        unsafe_interpreter=writable_including_symlink_target(python),
        unsafe_package=writable_including_symlink_target(_package_dir()),
    )
