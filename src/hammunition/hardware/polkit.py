# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The privileged artefacts ``hardware apply`` installs for power control. D-056."""

from __future__ import annotations

import enum
import grp
import os
import pwd
import re
import shlex
import signal
import stat as stat_module
import subprocess
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
    "group_is_private_to",
    "installed_helper_version",
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

    ``-I`` (isolated mode) is load-bearing, not tidiness — do not remove it
    for looking like noise. ``python -m <pkg>`` inserts ``os.getcwd()`` at
    ``sys.path[0]``. ``pkexec`` normally masks that by ``chdir()``-ing to the
    target user's home before it execs the authorised program, **but
    ``pkexec --keep-cwd`` does not**, and the polkit action here pins an
    executable *path*, not an argument list — nothing stops a caller from
    adding that flag. Without ``-I``, a local user with an active session can
    ``cd`` to a directory holding their own ``hammunition/cli/devctl.py``,
    run ``pkexec --keep-cwd /usr/local/libexec/hammunition-devctl state``,
    authenticate with *their own* password (``auth_self_keep``), and have
    their module imported and run as root instead of the real one — the
    working directory is a second value crossing the privilege boundary
    that D-056 says nothing but a device name should cross. ``-I`` drops
    ``sys.path[0]`` entirely (and ``PYTHONPATH``, ``PYTHONHOME`` and user
    site-packages with it) while still resolving ``hammunition`` from the
    interpreter's own venv, so the hijack import fails instead of
    succeeding. ``cd /`` before the ``exec`` is defence in depth on top of
    it, in case a future edit ever runs something cwd-sensitive first.
    """
    return (
        "#!/bin/sh\n"
        "# Installed by `hammunition hardware apply` (D-056). Do not edit: the\n"
        "# polkit action at "
        + POLICY_PATH
        + "\n# authorises this exact path, and the next apply rewrites this file.\n"
        "cd /\n"
        "exec " + shlex.quote(interpreter) + ' -I -m hammunition.cli.devctl "$@"\n'
    )


def policy_xml() -> str:
    """One action, authorising one executable. The battery applet's shape.

    **The text is hammunition-tray's, byte for byte** (``policy_xml`` in its
    ``hammunition_devctl/polkit.py``, contract 1; the description and message
    name the system services it can now control). This engine's own copy exists
    only until the next release, for a machine where no helper answers
    ``--version``, and must never read as drift against the tray's file.

    ``auth_self_keep`` on an active session: the operator authenticates once
    and stays authorised for a few minutes afterwards (polkit's own manual
    page: "a brief period (e.g. five minutes)", not the rest of the
    session), because a tray switch that asks for a password on every single
    flip is a tray switch nobody uses. Inactive and remote sessions get
    ``auth_admin``, because parking someone else's GPS over SSH is not a
    thing a password prompt should make easy.
    """
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE policyconfig PUBLIC
 "-//freedesktop//DTD PolicyKit Policy Configuration 1.0//EN"
 "http://www.freedesktop.org/standards/PolicyKit/1.0/policyconfig.dtd">
<policyconfig>
  <vendor>Hammunition</vendor>
  <vendor_url>https://github.com/Renegade-Penguin/Hammunition</vendor_url>
  <action id="{ACTION_ID}">
    <description>Park or wake a radio device, set the clock's time source, control a system service Hammunition manages, or keep your services running after you log out</description>
    <message>Authentication is required to change a radio device's power state, the clock's time source, a system service Hammunition manages, or whether your services keep running after you log out</message>
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


def group_is_private_to(
    gid: int,
    uid: int,
    *,
    getgrgid: Callable[[int], grp.struct_group] = grp.getgrgid,
    getpwall: Callable[[], list[pwd.struct_passwd]] = pwd.getpwall,
) -> bool:
    """True when ``gid`` is ``uid``'s user-private group: nobody is listed in
    it, and ``uid`` is the only account holding it as a primary group. Group
    write on such a group grants nobody anything the owner lacks.

    Measured on the field laptop, 2026-09-27: Parrot 7's stock session umask
    is 0002 with ``USERGROUPS_ENAB``, so every checkout and venv the operator
    makes is group-writable by exactly this kind of group, and the gate that
    read group-write as "any local account" refused the documented install.

    Fails closed: an unknown gid is not private. ``getpwall`` sees the local
    account database and whatever NSS enumerates; a directory service that
    does not enumerate could hold an account this cannot see, which is the
    residual risk the D-056 amendment records.
    """
    try:
        group = getgrgid(gid)
    except KeyError:
        return False
    if group.gr_mem:
        return False
    holders = {account.pw_uid for account in getpwall() if account.pw_gid == gid}
    return holders == {uid}


def writable_by_non_root(
    path: str | Path,
    *,
    stat_fn: Callable[[str], os.stat_result] = os.stat,
    private_group_fn: Callable[[int, int], bool] = group_is_private_to,
) -> WritabilityFinding | None:
    """The first offending component from ``path`` up to the filesystem
    root, classified by :class:`WritabilityRisk`, or ``None`` if every one of
    them is closed to non-root.

    ``stat_fn`` defaults to :func:`os.stat` and exists so this can be proven
    against a synthetic tree in a test — an unprivileged dev machine and an
    unprivileged CI run both lack any real root-owned file to test the "safe"
    answer against.

    D-056's ruling: the wrapper execs this path (or a path under the
    ``hammunition`` package directory) *as root*, through a polkit action
    that an active local session can satisfy once and keep for a few minutes
    afterwards (``auth_self_keep``, not the rest of the session). A
    component that is group- or other-writable is checked across
    the *whole* chain first, and wins over a merely non-root-owned one
    regardless of which is nearer the leaf — the real escalation must never
    be masked by a nearer, milder finding. Only once nothing in the chain is
    writable by everyone does the nearest merely-non-root-owned component
    become the (confirmable) answer. A component that cannot be stat'd at all
    is treated as the severe case (:attr:`WritabilityFinding.unstatable`):
    it cannot be proven safe either, but it is a different fact from actually
    being writable, and is reported as one.

    Group write by the owner's own user-private group (``private_group_fn``,
    :func:`group_is_private_to` by default) is not the severe class: nobody
    but the owner is in that group, so the component falls through to the
    ownership pass and is confirmable like any other operator-owned tree.
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
        if info.st_mode & stat_module.S_IWOTH:
            return WritabilityFinding(name, WritabilityRisk.GROUP_OR_OTHER_WRITABLE)
        if info.st_mode & stat_module.S_IWGRP and not private_group_fn(info.st_gid, info.st_uid):
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
    private_group_fn: Callable[[int, int], bool] = group_is_private_to,
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
    direct = writable_by_non_root(path, stat_fn=stat_fn, private_group_fn=private_group_fn)
    resolved = writable_by_non_root(
        realpath_fn(str(path)), stat_fn=stat_fn, private_group_fn=private_group_fn
    )
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

    handed_over: str | None = None
    """What the installed helper answered to ``--version``, when it answered:
    the helper is hammunition-tray's and ``hardware apply`` writes neither its
    wrapper nor its policy (D-056, amended 2026-10-02). None means the helper,
    if any, is this engine's own."""

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


_CONTRACT_LINE = re.compile(r"hammunition-devctl contract (?P<number>[0-9]+)")
"""The one line contract 1 says ``--version`` prints (hammunition-tray's
``docs/contract.md``): the word ``contract`` and an integer."""


def _probe_identity(
    *,
    euid: int | None = None,
    sudo_uid: str | None = None,
    sudo_gid: str | None = None,
) -> tuple[int, int] | None:
    """The (uid, gid) to run the version probe as, or None to run as ourselves.

    Planning must not run an operator-owned tree as root: the writability gate
    that decides whether the engine's own wrapper may be trusted comes *after*
    this probe. Under ``sudo`` the probe runs as the invoking operator; as root
    with no sudo it runs as ``nobody``, never as root.
    """
    effective = os.geteuid() if euid is None else euid
    if effective != 0:
        return None
    uid_text = os.environ.get("SUDO_UID") if sudo_uid is None else sudo_uid
    gid_text = os.environ.get("SUDO_GID") if sudo_gid is None else sudo_gid
    if uid_text and uid_text.isdigit() and int(uid_text) != 0:
        gid = int(gid_text) if gid_text and gid_text.isdigit() else int(uid_text)
        return int(uid_text), gid
    try:
        nobody = pwd.getpwnam("nobody")
        return nobody.pw_uid, nobody.pw_gid
    except KeyError:
        return 65534, 65534


def installed_helper_version(path: str = HELPER_PATH, timeout: float = 10.0) -> str | None:
    """What the installed helper answers to ``--version``, or None.

    The hand-over test (D-056, amended 2026-10-02): the engine's own wrapper
    execs a module whose argparse has no ``--version``, so it exits 2 and is not
    a hand-over; the tray's helper answers its contract version. One argument,
    no shell, a fixed environment, its own process group (a wrapper that hangs
    is killed with whatever it spawned), and never as root (:func:`_probe_identity`).
    Anything but a zero exit whose first line is contract 1's own
    (``hammunition-devctl contract N``, N at least 1) is None.

    **A weak identity test, on purpose.** Any executable at the helper's path
    that exits 0 printing that line passes: the path is root-owned, and the
    probe decides only whether the engine should *stop writing its own copy*,
    never whether anything is trusted. Nobody should later read this as
    authentication; the polkit action and the root-owned path are what bound
    what runs as root.
    """
    identity = _probe_identity()
    try:
        proc = subprocess.Popen(
            [path, "--version"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd="/",
            env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
            start_new_session=True,
            user=identity[0] if identity is not None else None,
            group=identity[1] if identity is not None else None,
            # Without this the child keeps root's supplementary groups (gid 0
            # among them) and "never as root" would be true of the uid only.
            # setgroups needs root, so an unprivileged probe asks for nothing.
            extra_groups=[] if identity is not None else None,
        )
    except (OSError, ValueError):
        return None
    try:
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            proc.kill()
        proc.communicate()
        return None
    if proc.returncode != 0:
        return None
    for line in out.splitlines():
        if line.strip():
            match = _CONTRACT_LINE.fullmatch(line.strip())
            return line.strip() if match is not None and int(match["number"]) >= 1 else None
    return None


_probe_helper_version = installed_helper_version
"""The real probe under a second name, so a test can restore it after the
suite-wide stub replaces ``installed_helper_version`` (no test may run the
host's installed helper)."""


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
    version = installed_helper_version()
    if version is not None:
        # D-056, amended 2026-10-02: the helper that answers is hammunition-tray's.
        # Its wrapper is never rewritten, its policy only written where absent,
        # and the interpreter the engine would have baked in is nobody's
        # concern here, so there is nothing to gate.
        return PolkitArtifacts(
            helper_path=HELPER_PATH,
            helper_content=helper,
            policy_path=POLICY_PATH,
            policy_content=policy,
            helper_current=True,
            policy_current=Path(POLICY_PATH).exists(),
            interpreter=python,
            unsafe_interpreter=None,
            unsafe_package=None,
            handed_over=version,
        )
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
