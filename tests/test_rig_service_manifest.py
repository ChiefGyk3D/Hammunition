# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The rig-service carrying unit and its place in the station profile.  D-073 §5."""

from __future__ import annotations

from pathlib import Path

from hammunition.manifest.load import load_catalog, load_profiles
from hammunition.manifest.schema import PackageManifest, ProfileManifest

CATALOG = Path(__file__).resolve().parent.parent / "catalog"


def _catalog() -> tuple[dict[str, PackageManifest], dict[str, ProfileManifest]]:
    packages = load_catalog(CATALOG / "packages")
    profiles = load_profiles(CATALOG / "profiles", packages)
    return packages, profiles


def test_rig_service_carries_two_user_services() -> None:
    packages, _profiles = _catalog()
    rig = packages["rig-service"]
    assert len(rig.user_services) == 2
    kinds = {svc.when_station.get("rig_kind") for svc in rig.user_services}
    assert kinds == {"cat", "ptt_only"}
    assert "libhamlib-utils" in rig.depends


def test_both_services_listen_on_loopback_4532() -> None:
    packages, _profiles = _catalog()
    rig = packages["rig-service"]
    for svc in rig.user_services:
        (listen,) = svc.listens
        assert listen.address == "127.0.0.1"
        assert listen.port == 4532


def test_rig_service_is_in_the_station_profile() -> None:
    _packages, profiles = _catalog()
    assert "rig-service" in profiles["station"].packages
