# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The privileged artefacts ``hardware apply`` installs for power control. D-056."""

from __future__ import annotations

# Declared whole here although Task 6 supplies the last four names: ruff's
# RUF022 wants one sorted literal, and `__all__ += [...]` later is not one.
# The four are undefined until Task 6 lands them, which is exactly what F822
# exists to catch elsewhere; noqa'd here on purpose rather than widening the
# ignore list, so a real forgotten export anywhere else in the tree still fails.
__all__ = [
    "ACTION_ID",
    "HELPER_PATH",
    "POLICY_PATH",
    "PolkitArtifacts",  # noqa: F822 -- Task 6
    "plan_polkit",  # noqa: F822 -- Task 6
    "policy_xml",  # noqa: F822 -- Task 6
    "wrapper_script",  # noqa: F822 -- Task 6
]

HELPER_PATH = "/usr/local/libexec/hammunition-devctl"
"""Where pkexec is pointed. A fixed path under the shared prefix, because a
polkit action annotates an absolute executable and a venv's path is not one
an operator's policy file should have to follow across an upgrade."""

ACTION_ID = "com.chiefgyk3d.hammunition.devctl"
POLICY_PATH = f"/usr/share/polkit-1/actions/{ACTION_ID}.policy"
