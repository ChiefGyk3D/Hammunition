# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The ``gps-tether`` catalog unit: the tether installed from its own project and
run as a user service.  D-073 amended 2026-10-02, D-071 note.

The unit's pin is either the release wheel's real sha256 or the all-zero value
:data:`UNPINNED`, which pip can never match, so an unpinned unit fails closed
at install. While it is unpinned it must be in no profile and depended on by no
unit; once pinned it must be in ``navigation``. A test that cannot tell the two
apart would let an uninstallable unit into a profile (or keep an installable one
out), which is the failure this file exists to catch.
"""

from __future__ import annotations

import re
from pathlib import Path

from hammunition.manifest.load import load_catalog, load_profile
from hammunition.manifest.schema import PackageManifest, VenvInstall
from hammunition.station import Station
from hammunition.userservice import header_for, plan_user_services

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "catalog"
UNPINNED = "0" * 64


def _unit() -> PackageManifest:
    return load_catalog(CATALOG / "packages")["gps-tether"]


def _line() -> str:
    (alt,) = _unit().install
    assert isinstance(alt.install, VenvInstall)
    (line,) = alt.install.requirements
    return line


def is_unpinned() -> bool:
    return f"--hash=sha256:{UNPINNED}" in _line()


def test_it_is_a_venv_of_one_hash_pinned_wheel_that_exposes_the_program() -> None:
    (alt,) = _unit().install
    block = alt.install
    assert isinstance(block, VenvInstall)
    assert block.expose == ["hammunition-gps-tether"]
    url = _line().split()[0]
    assert url.startswith(
        "https://github.com/ChiefGyk3D/hammunition-gps-tether/releases/download/v0.1.0/"
    )
    assert url.endswith(".whl")
    assert re.search(r"--hash=sha256:[0-9a-f]{64}$", _line())


def test_the_unit_names_the_tag_it_pins() -> None:
    unit = _unit()
    assert unit.version == "0.1.0"
    assert "v0.1.0" in _line()


def test_the_service_is_the_tethers_two_loopback_ports_with_no_device() -> None:
    (svc,) = _unit().user_services
    assert svc.name == "hammunition-gps-tether"
    assert svc.exec == ["{user_bin}/hammunition-gps-tether"]
    assert [(lst.address, lst.port) for lst in svc.listens] == [
        ("127.0.0.1", 10110),
        ("127.0.0.1", 10111),
    ]
    assert svc.binds_to_device is None
    assert (svc.restart, svc.restart_sec) == ("on-failure", 5)
    assert svc.is_plain


def test_it_plans_a_user_unit_with_no_station_and_no_hardware_catalog() -> None:
    planned, deferrals, notes = plan_user_services(
        _unit(), Station(), None, user_bin=Path("/home/op/.local/bin")
    )
    assert not deferrals and not notes
    (svc,) = planned
    assert svc.unit == "gps-tether"
    assert svc.unit_body.startswith(header_for("gps-tether"))
    assert "ExecStart=/home/op/.local/bin/hammunition-gps-tether\n" in svc.unit_body
    assert "Restart=on-failure" in svc.unit_body and "RestartSec=5" in svc.unit_body
    assert "BindsTo" not in svc.unit_body


def test_the_docs_say_the_service_and_a_foreground_run_cannot_share_the_port() -> None:
    docs = _unit().documentation
    assert docs.known_problems is not None
    assert "10110" in docs.known_problems
    assert "foreground" in docs.known_problems
    assert docs.upstream_url == "https://github.com/ChiefGyk3D/hammunition-gps-tether"
    assert docs.prerequisites is not None and "gpsd" in docs.prerequisites


def test_an_unpinned_unit_is_in_no_profile_and_a_pinned_one_is_in_navigation() -> None:
    profiles = {p.name: p for p in map(load_profile, sorted((CATALOG / "profiles").glob("*.yaml")))}
    members = [name for name, profile in profiles.items() if "gps-tether" in profile.packages]
    if is_unpinned():
        assert members == [], f"gps-tether is unpinned (the zero digest) but is in {members}"
        dependents = [
            name
            for name, unit in load_catalog(CATALOG / "packages").items()
            if "gps-tether" in unit.depends
        ]
        assert dependents == [], f"gps-tether is unpinned but {dependents} depend on it"
    else:
        assert members == ["navigation"]


def test_the_unpinned_marker_is_recognised_as_not_installable() -> None:
    """Falsifiable: the zero digest is what pip cannot match, and the check above
    keys on exactly that string."""
    assert re.fullmatch(r"[0-9a-f]{64}", UNPINNED)
    assert not any(UNPINNED[i] != "0" for i in range(64))
