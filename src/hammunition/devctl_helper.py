# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The tray's device helper, installed by the engine from the tray's own archive.

D-056, amended 2026-10-02: the privileged helper that parks and wakes a device,
drives a service or a radio and sets the clock's time source lives in
hammunition-tray, which publishes it with a contract (``docs/contract.md`` at
its tag). The engine is the installer of the suite, so a tray unit installs it:
the files below, root-owned, printed in the plan, removed on uninstall.

hammunition-tray 0.5.0 published no ``.deb`` (the release workflow's mirror
returned 502), so the units pin the tag's tarball and this module does what the
tray's own ``install.sh --helper-only --interpreter`` does, from the same
archive:

``/usr/local/lib/hammunition-devctl/hammunition-devctl``
    the entry script, 0755
``/usr/local/lib/hammunition-devctl/hammunition_devctl/*.py``
    the package, 0644, **copied** and never run from the unpack: the wrapper
    runs as root and root must not run a tree an account can still edit
``/usr/local/libexec/hammunition-devctl``
    the ``/bin/sh`` wrapper polkit authorises, with the engine's own venv
    interpreter baked in so the helper's ``time`` verbs can import the engine
``/usr/share/polkit-1/actions/com.chiefgyk3d.hammunition.devctl.policy``
    the one polkit action

**It does not fight another owner.** A helper that already answers
``--version`` with the contract this pin needs is left alone, and the plan says
whose it is: a ``.deb`` (dpkg owns the policy), the tray's own installer or an
earlier tray unit (both carry the tray's mark, and the engine tells its own by
its log), or some other installer. A wrapper that answers nothing and was
written by the engine's old ``hardware apply`` is replaced; one written by
anything else is left, by name.

The wrapper's text is the tray's ``wrapper_script`` byte for byte and the
policy is :func:`hammunition.hardware.polkit.policy_xml`, which carries the
tray's text; both are compared with the pinned archive's own rendering in
``tests/test_devctl_helper.py``.
"""

from __future__ import annotations

import re
import shlex
import subprocess
import sys
from collections.abc import Callable, Collection
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from hammunition.manifest.schema import DevctlHelper

if TYPE_CHECKING:
    # Type-only, and `polkit` is imported inside the functions that call it:
    # `hammunition.hardware` imports the backends, which import this module, so
    # a module-level import here closes the cycle (tests/test_import_isolation.py
    # imports every module alone to catch exactly that).
    from hammunition.hardware.polkit import WritabilityFinding

__all__ = [
    "ENTRY_NAME",
    "HELPER_PATH",
    "LIBDIR",
    "PACKAGE_DIR",
    "POLICY_PATH",
    "WRAPPER_MARK",
    "HelperPlan",
    "dpkg_owner",
    "dpkg_owners",
    "helper_destinations",
    "plan_helper",
    "under_prefix",
    "wrapper_script",
]

HELPER_PATH = "/usr/local/libexec/hammunition-devctl"
"""The wrapper polkit authorises; ``hammunition.hardware.polkit.HELPER_PATH`` is the
same string (a test holds them equal; it is repeated here so this module stays
a leaf the backends can import)."""

POLICY_PATH = "/usr/share/polkit-1/actions/com.chiefgyk3d.hammunition.devctl.policy"

LIBDIR = "/usr/local/lib/hammunition-devctl"
"""Where the helper's code lives for a source or tarball install (the tray's
``install.sh`` uses the same path; the ``.deb`` uses /usr/share instead)."""

ENTRY_NAME = "hammunition-devctl"
PACKAGE_DIR = "hammunition_devctl"

WRAPPER_MARK = "# Installed by hammunition-tray (hammunition-devctl, D-056).\n"
"""The tray's mark, in every wrapper it writes. Its own installer and its
``.deb``'s postinst leave a wrapper without it alone, and so does this."""

_ENGINE_OLD_WRAPPER = "Installed by `hammunition hardware apply` (D-056)"
"""A phrase of the wrapper this engine wrote before the helper moved to the
tray. It answers nothing to ``--version``; replacing it is the hand-over."""

_CONTRACT = re.compile(r"hammunition-devctl contract (?P<number>[0-9]+)")


def wrapper_script(interpreter: str, entry: str = f"{LIBDIR}/{ENTRY_NAME}") -> str:
    """The tray's wrapper, byte for byte (``polkit.wrapper_script`` at its tag).

    ``-I`` is load-bearing: without it ``pkexec --keep-cwd`` would let a local
    user's working directory onto root's import path. The tray's docstring says
    why at length; the text below is the file's, not a paraphrase.
    """
    return (
        "#!/bin/sh\n"
        + WRAPPER_MARK
        + "# Do not edit: the polkit action at "
        + POLICY_PATH
        + "\n# authorises this exact path, and the next install rewrites this file.\n"
        "cd /\n"
        "exec " + shlex.quote(interpreter) + " -I " + shlex.quote(entry) + ' "$@"\n'
    )


def under_prefix(path: str, prefix: Path) -> Path:
    """*path*, with a leading ``/usr/local/`` following the engine's prefix.

    The helper's paths are fixed by the tray's contract; in production the
    prefix is ``/usr/local`` and this is the identity. A test (or a prefix the
    operator chose) maps the same layout somewhere it can write.
    """
    root = "/usr/local/"
    if path.startswith(root):
        return prefix / path[len(root) :]
    return Path(path)


def dpkg_owner(path: str) -> str | None:
    """The package dpkg says owns *path*, or None.

    ``dpkg-query -S`` exits 1 for a path no package owns and prints
    ``package: path`` for one that is; a machine without dpkg owns nothing.
    """
    try:
        proc = subprocess.run(
            ["dpkg-query", "-S", path], capture_output=True, text=True, check=False, timeout=30
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0 or ":" not in proc.stdout:
        return None
    return proc.stdout.splitlines()[0].split(":", 1)[0].strip() or None


def dpkg_owners(paths: Collection[str]) -> dict[str, str]:
    """The package that owns each of *paths*, for the ones some package does.

    One ``dpkg-query -S`` for all of them. It exits 1 when any path is unowned
    but still prints the owned ones as ``package[, package]: path``; a diversion
    line (``diversion by ...``) names no owner and is ignored.
    """
    wanted = [p for p in paths if p]
    if not wanted:
        return {}
    try:
        proc = subprocess.run(
            ["dpkg-query", "-S", "--", *wanted],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {}
    found: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        owners, sep, path = line.partition(": ")
        if sep and path in wanted and not owners.startswith("diversion by"):
            found[path] = owners.split(",")[0].strip()
    return found


@dataclass(frozen=True)
class HelperPlan:
    """What installing the helper would do here, and whose files are in the way."""

    install: bool
    owner: str
    """Who owns the helper that is (or would be) at the fixed path, in the
    words the plan prints: a package, the tray's installer, an earlier run of
    this engine, or nobody yet."""

    interpreter: str
    """The interpreter the wrapper would run as root. Disclosed in the plan
    before anything is written (D-056); relevant only when ``install``."""

    version: str | None
    """What a present helper answered to ``--version``, else None."""

    refresh: bool = False
    """True when the files at the fixed path are this engine's own earlier
    install and are replaced by this pin's."""

    problem: str | None = None
    """Why the helper that is left alone cannot serve this pin, when it cannot
    (a package's helper that answers no contract at all). A plan with a problem
    is refused by name where its steps are built, never discovered afterwards."""

    unsafe_interpreter: WritabilityFinding | None = None
    unsafe_package: WritabilityFinding | None = None

    @property
    def _findings(self) -> tuple[WritabilityFinding, ...]:
        if not self.install:
            return ()
        return tuple(f for f in (self.unsafe_interpreter, self.unsafe_package) if f is not None)

    @property
    def refusing_findings(self) -> list[WritabilityFinding]:
        """A component any local account can write: the escalation, refused."""
        from hammunition.hardware.polkit import WritabilityRisk

        return [f for f in self._findings if f.risk is WritabilityRisk.GROUP_OR_OTHER_WRITABLE]

    @property
    def must_refuse(self) -> bool:
        return bool(self.refusing_findings)

    @property
    def confirmable_paths(self) -> list[str]:
        """Components owned by one non-root account (the ordinary venv shape),
        confirmed at the keyboard and never by ``--yes`` (D-021, D-056)."""
        from hammunition.hardware.polkit import WritabilityRisk

        return [f.path for f in self._findings if f.risk is WritabilityRisk.OWNED_BY_NON_ROOT]

    @property
    def needs_confirmation(self) -> bool:
        return bool(self.confirmable_paths) and not self.must_refuse


def helper_destinations(helper: DevctlHelper, prefix: Path) -> tuple[Path, ...]:
    """Every file the helper install writes, for the effect check and the log."""
    libdir = under_prefix(LIBDIR, prefix)
    return (
        libdir / ENTRY_NAME,
        *(libdir / PACKAGE_DIR / module for module in helper.modules),
        under_prefix(HELPER_PATH, prefix),
        Path(POLICY_PATH),
    )


def _read(path: Path) -> str | None:
    try:
        return path.read_text()
    except (OSError, UnicodeDecodeError):
        return None


def plan_helper(
    helper: DevctlHelper,
    *,
    attributed_files: Collection[str] = (),
    interpreter: str | None = None,
    wrapper_path: Path | None = None,
    policy_path: str = POLICY_PATH,
    owner_of: Callable[[str], str | None] | None = None,
) -> HelperPlan:
    """Decide: install the helper, or leave what is there and say whose it is.

    ``interpreter`` defaults to the interpreter running the engine, which is by
    construction one that can import it. The safety gates are the ones
    ``hardware apply`` applies to the same wrapper (D-056): the interpreter and
    the ``hammunition`` package the helper's ``time`` verbs import are both
    checked, as given and resolved.
    """
    from hammunition.hardware import polkit

    python = interpreter or sys.executable
    wrapper = wrapper_path if wrapper_path is not None else Path(HELPER_PATH)
    package = (owner_of or dpkg_owner)(policy_path)
    if package is not None:
        answered = polkit.installed_helper_version(str(wrapper))
        match = _CONTRACT.fullmatch(answered) if answered else None
        enough = match is not None and int(match["number"]) >= helper.min_contract
        return HelperPlan(
            install=False,
            owner=f"the {package} package (apt), which owns {policy_path}",
            interpreter=python,
            version=answered,
            problem=None
            if enough
            else (
                f"the {package} package owns {policy_path} and the helper at {wrapper} does "
                f"not answer contract {helper.min_contract} or newer ({answered or 'no answer'}); "
                f"this engine never writes over a package's file -- upgrade or remove "
                f"{package} (apt), then install again"
            ),
        )

    text = _read(wrapper)
    version = polkit.installed_helper_version(str(wrapper))
    number = None
    if version is not None:
        match = _CONTRACT.fullmatch(version)
        number = int(match["number"]) if match else None

    if text is not None and number is not None and number >= helper.min_contract:
        if WRAPPER_MARK in text and str(wrapper) in attributed_files:
            return _install(python, version, refresh=True, owner="an earlier run of this engine")
        if WRAPPER_MARK in text:
            return HelperPlan(
                install=False,
                owner=(
                    "hammunition-tray's own installer (its install.sh), which marks the "
                    "wrapper it writes"
                ),
                interpreter=python,
                version=version,
            )
        return HelperPlan(
            install=False,
            owner="an installer that did not mark its wrapper as the tray's",
            interpreter=python,
            version=version,
        )

    if text is not None and _ENGINE_OLD_WRAPPER not in text and WRAPPER_MARK not in text:
        return HelperPlan(
            install=False,
            owner=(
                f"something other than the tray or this engine (it answers no contract "
                f"{helper.min_contract}); not replaced"
            ),
            interpreter=python,
            version=version,
        )

    owner = (
        "this engine's earlier `hardware apply`, replaced by the tray's helper"
        if text is not None and _ENGINE_OLD_WRAPPER in text
        else "nobody yet"
        if text is None
        else "an older helper of the tray's that answers no contract, replaced"
    )
    return _install(python, version, refresh=text is not None, owner=owner)


def _install(python: str, version: str | None, *, refresh: bool, owner: str) -> HelperPlan:
    from hammunition.hardware import polkit

    return HelperPlan(
        install=True,
        owner=owner,
        interpreter=python,
        version=version,
        refresh=refresh,
        unsafe_interpreter=polkit.writable_including_symlink_target(python),
        unsafe_package=polkit.writable_including_symlink_target(polkit._package_dir()),
    )
