# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The user_services manifest block.  D-073 §6."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from hammunition.manifest.schema import ManifestError, PackageManifest, UserService

_DOC = {
    "what_it_does": "Runs one shared rigctld for the station's rig over loopback.",
    "why_you_want_it": "So every program keys through one port instead of fighting for it.",
    "upstream_url": "https://hamlib.github.io/",
}


def _manifest(services: list[dict[str, object]]) -> dict[str, object]:
    return {
        "name": "rig-service",
        "version": "1.0",
        "summary": "One shared rigctld for the station's rig",
        "categories": ["rig-control"],
        "install": [{"install": {"method": "apt", "packages": ["libhamlib-utils"]}}],
        "update": {"probe": {"method": "apt_policy"}, "strategy": "apt_upgrade"},
        "documentation": _DOC,
        "user_services": services,
    }


_CAT = {
    "name": "hammunition-rigctld",
    "description": "hamlib rigctld for the station's rig",
    "when_station": {"rig_kind": "cat"},
    "unless_station": {"rig_owner": "flrig"},
    "exec": [
        "/usr/bin/rigctld",
        "-m",
        "{station.rig_hamlib_model}",
        "-r",
        "{station.rig_device}",
        "-s",
        "{station.rig_baud}",
        "-T",
        "127.0.0.1",
        "-t",
        "4532",
    ],
    "binds_to_device": "{station.rig_device}",
    "listens": [{"protocol": "tcp", "address": "127.0.0.1", "port": 4532}],
}


def test_a_cat_service_loads() -> None:
    manifest = PackageManifest.model_validate(_manifest([_CAT]))
    (svc,) = manifest.user_services
    assert svc.name == "hammunition-rigctld"
    assert "rig_device" in svc.station_variables
    assert "rig_hamlib_model" in svc.station_variables
    assert "rig_baud" in svc.station_variables


def test_a_non_loopback_listen_is_refused_at_load() -> None:
    bad = {**_CAT, "listens": [{"protocol": "tcp", "address": "0.0.0.0", "port": 4532}]}
    with pytest.raises((ManifestError, ValidationError)):
        PackageManifest.model_validate(_manifest([bad]))


def test_an_exec_element_with_a_space_is_refused() -> None:
    bad = {**_CAT, "exec": ["/usr/bin/rigctld -m 1"]}
    with pytest.raises((ManifestError, ValidationError)):
        PackageManifest.model_validate(_manifest([bad]))


def test_exec_first_element_must_be_absolute() -> None:
    bad = {**_CAT, "exec": ["rigctld", "-t", "4532"]}
    with pytest.raises((ManifestError, ValidationError)):
        PackageManifest.model_validate(_manifest([bad]))


def test_a_shell_metacharacter_in_exec_is_refused() -> None:
    bad = {**_CAT, "exec": ["/usr/bin/rigctld", ";reboot"]}
    with pytest.raises((ManifestError, ValidationError)):
        PackageManifest.model_validate(_manifest([bad]))


def test_two_entries_one_name_must_have_disjoint_conditions() -> None:
    ptt = {
        "name": "hammunition-rigctld",
        "description": "hamlib rigctld keying the PTT-only rig",
        "when_station": {"rig_kind": "ptt_only"},
        "unless_station": {"rig_ptt_line": "vox"},
        "exec": ["/usr/bin/rigctld", "-m", "1", "-t", "4532"],
        "listens": [{"protocol": "tcp", "address": "127.0.0.1", "port": 4532}],
    }
    # cat vs ptt_only cannot both hold: accepted.
    PackageManifest.model_validate(_manifest([_CAT, ptt]))
    # Two identical conditions on one name: refused.
    with pytest.raises((ManifestError, ValidationError)):
        PackageManifest.model_validate(_manifest([_CAT, {**_CAT}]))


def test_user_service_is_importable() -> None:
    assert UserService is not None
