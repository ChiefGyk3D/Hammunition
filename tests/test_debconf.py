# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""debconf preseeding and post-install reconfigure — the wireshark case.

Non-root packet capture on Debian needs three things a non-interactive apt
install does not do on its own: the install-setuid debconf answer preseeded so
the postinst creates the wireshark group and setcaps dumpcap, libcap2-bin
present so setcap exists, and a reconfigure after the transaction so setcap
runs regardless of apt's within-transaction order. These hold the plan to that.
"""

from __future__ import annotations

from typing import Any

import pytest

from hammunition.backends import AptBackend, Command, RecordingRunner
from hammunition.distro import Target
from hammunition.execute import commands_for
from hammunition.manifest.schema import ManifestError, PackageManifest
from hammunition.plan import InstallPlan, PlannedPackage

TARGET = Target(distro="debian", version="13", arch="x86_64")


def manifest(name: str, **extra: Any) -> PackageManifest:
    return PackageManifest.model_validate(
        {
            "name": name,
            "version": "1.0",
            "summary": "Fixture for the debconf mechanism suite",
            "categories": ["rf-security"],
            "install": [{"install": {"method": "apt", "packages": [name]}}],
            "update": {"probe": {"method": "apt_policy"}, "strategy": "apt_upgrade"},
            "documentation": {
                "what_it_does": "Exists so the debconf suite has a unit.",
                "why_you_want_it": "You do not; the suite does.",
                "prerequisites": "Nothing.",
                "known_problems": "None.",
                "upstream_url": "https://example.org",
                "upstream_support": "test fixture",
            },
            **extra,
        }
    )


def plan_for(m: PackageManifest, *, installed: tuple[str, ...] = ()) -> InstallPlan:
    planned = PlannedPackage(
        manifest=m,
        block=m.install[0],
        apt_packages=tuple(m.install[0].install.packages),  # type: ignore[union-attr]
        already_installed=installed,
    )
    return InstallPlan(target=TARGET, packages=(planned,))


def test_malformed_preseed_is_refused_at_the_schema() -> None:
    with pytest.raises((ManifestError, ValueError), match="malformed"):
        manifest("wireshark", debconf_selections=["too few fields"])


def test_selections_and_reconfigure_come_from_installs_only() -> None:
    m = manifest(
        "wireshark",
        debconf_selections=["wireshark-common wireshark-common/install-setuid boolean true"],
        reconfigure_after=["wireshark-common"],
    )
    fresh = plan_for(m)
    assert fresh.debconf_selections == (
        "wireshark-common wireshark-common/install-setuid boolean true",
    )
    assert fresh.reconfigure_after == ("wireshark-common",)

    # Already installed: nothing outstanding, so no preseed and no reconfigure —
    # the question was answered at its original install.
    already = plan_for(m, installed=("wireshark",))
    assert already.debconf_selections == ()
    assert already.reconfigure_after == ()


def test_commands_are_ordered_preseed_then_install_then_reconfigure() -> None:
    m = manifest(
        "wireshark",
        debconf_selections=["wireshark-common wireshark-common/install-setuid boolean true"],
        reconfigure_after=["wireshark-common"],
    )
    apt = AptBackend(RecordingRunner([]))
    commands = commands_for(plan_for(m), apt=apt, refresh=False)
    argv0s = [c.argv[0] for c in commands if isinstance(c, Command)]
    assert argv0s[:3] == ["debconf-set-selections", "apt-get", "dpkg-reconfigure"]

    preseed = commands[0]
    assert isinstance(preseed, Command)
    assert preseed.stdin is not None and "install-setuid boolean true" in preseed.stdin
    assert preseed.requires_root

    # The preseed does not leak its bytes into an argv; it rides on stdin.
    assert "install-setuid" not in " ".join(preseed.argv)


def test_no_preseed_command_without_selections() -> None:
    apt = AptBackend(RecordingRunner([]))
    commands = commands_for(plan_for(manifest("plain")), apt=apt, refresh=False)
    assert not any(
        isinstance(c, Command) and c.argv[0] == "debconf-set-selections" for c in commands
    )
