# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The privileged artefacts ``hardware apply`` installs for power control. D-056."""

from __future__ import annotations

import shlex
import sys
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
]

HELPER_PATH = "/usr/local/libexec/hammunition-devctl"
"""Where pkexec is pointed. A fixed path under the shared prefix, because a
polkit action annotates an absolute executable and a venv's path is not one
an operator's policy file should have to follow across an upgrade."""

ACTION_ID = "com.chiefgyk3d.hammunition.devctl"
POLICY_PATH = f"/usr/share/polkit-1/actions/{ACTION_ID}.policy"


def wrapper_script(interpreter: str) -> str:
    """A three-line shell wrapper that execs the helper's module.

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


@dataclass(frozen=True)
class PolkitArtifacts:
    """The two files power control needs on the machine, and whether they are current."""

    helper_path: str
    helper_content: str
    policy_path: str
    policy_content: str
    helper_current: bool
    policy_current: bool

    @property
    def is_noop(self) -> bool:
        return self.helper_current and self.policy_current


def _current(path: str, content: str) -> bool:
    try:
        return Path(path).read_text() == content
    except (OSError, UnicodeDecodeError):
        return False


def plan_polkit(interpreter: str | None = None) -> PolkitArtifacts:
    """What an apply would install, and whether it is already installed.

    ``interpreter`` defaults to the interpreter running this process, which is
    by construction the one that can import the package.
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
    )
