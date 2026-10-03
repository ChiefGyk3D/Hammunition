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
from hammunition.manifest.schema import UNPINNED_SHA256 as UNPINNED
from hammunition.manifest.schema import BinaryInstall, PackageManifest
from hammunition.station import Station
from hammunition.userservice import header_for, plan_user_services

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "catalog"


def _unit() -> PackageManifest:
    return load_catalog(CATALOG / "packages")["gps-tether"]


def _artifact() -> BinaryInstall:
    (alt,) = _unit().install
    assert isinstance(alt.install, BinaryInstall)
    return alt.install


def is_unpinned() -> bool:
    return _artifact().artifact.sha256 == UNPINNED


def test_it_is_the_tags_tarball_pinned_by_sha256_and_installed_as_a_tree() -> None:
    block = _artifact()
    assert block.format == "tarball" and block.install_tree
    assert block.tree_marker == "src/hammunition_gps_tether/__main__.py"
    assert block.artifact.url == (
        "https://github.com/ChiefGyk3D/hammunition-gps-tether/archive/refs/tags/v0.1.1.tar.gz"
    )
    assert re.fullmatch(r"[0-9a-f]{64}", block.artifact.sha256)
    assert not is_unpinned(), "the placeholder digest is still in the manifest"


def test_the_unit_names_the_tag_it_pins() -> None:
    unit = _unit()
    assert unit.version == "0.1.1"
    assert "/v0.1.1.tar.gz" in _artifact().artifact.url


def test_the_service_is_the_tethers_two_loopback_ports_with_no_device() -> None:
    (svc,) = _unit().user_services
    assert svc.name == "hammunition-gps-tether"
    assert svc.exec == [
        "/usr/bin/env",
        "PYTHONPATH=/usr/local/share/hammunition/gps-tether/src",
        "/usr/bin/python3",
        "-P",
        "-m",
        "hammunition_gps_tether",
    ]
    assert svc.restart_prevent_exit_status == [3]  # the tether's refusals; a crash (1) is retried
    assert [(lst.address, lst.port) for lst in svc.listens] == [
        ("127.0.0.1", 10110),
        ("127.0.0.1", 10111),
    ]
    assert svc.binds_to_device is None
    assert (svc.restart, svc.restart_sec) == ("on-failure", 5)
    assert svc.is_plain


def test_it_plans_a_user_unit_with_no_station_and_no_hardware_catalog() -> None:
    planned, deferrals, notes = plan_user_services(_unit(), Station(), None)
    assert not deferrals and not notes
    (svc,) = planned
    assert svc.unit == "gps-tether"
    assert svc.unit_body.startswith(header_for("gps-tether"))
    assert (
        "ExecStart=/usr/bin/env PYTHONPATH=/usr/local/share/hammunition/gps-tether/src "
        "/usr/bin/python3 -P -m hammunition_gps_tether\n"
    ) in svc.unit_body
    assert "RestartPreventExitStatus=3\n" in svc.unit_body
    assert "Restart=on-failure" in svc.unit_body and "RestartSec=5" in svc.unit_body
    assert "BindsTo" not in svc.unit_body


def test_the_docs_say_the_service_and_a_foreground_run_cannot_share_the_port() -> None:
    docs = _unit().documentation
    assert docs.known_problems is not None
    assert "10110" in docs.known_problems
    assert "foreground" in docs.known_problems
    assert docs.upstream_url == "https://github.com/ChiefGyk3D/hammunition-gps-tether"
    assert docs.prerequisites is not None and "gpsd" in docs.prerequisites


def _consistent(unpinned: bool, members: list[str], dependents: list[str]) -> bool:
    """The rule: an unpinned unit is in no profile and depended on by none; a
    pinned one is in `navigation`."""
    return (not members and not dependents) if unpinned else members == ["navigation"]


def test_the_rule_tells_a_pinned_unit_from_an_unpinned_one() -> None:
    """Falsifiable: each state accepts its own shape and rejects the other's."""
    assert _consistent(True, [], [])
    assert not _consistent(True, ["navigation"], [])
    assert not _consistent(True, [], ["qmapshack"])
    assert _consistent(False, ["navigation"], [])
    assert not _consistent(False, [], [])


def test_the_shipped_unit_obeys_the_rule_for_the_state_it_is_in() -> None:
    catalog = load_catalog(CATALOG / "packages")
    profiles = [load_profile(p) for p in sorted((CATALOG / "profiles").glob("*.yaml"))]
    members = [p.name for p in profiles if "gps-tether" in p.packages]
    dependents = [n for n, u in catalog.items() if "gps-tether" in u.depends]
    assert _consistent(is_unpinned(), members, dependents), (is_unpinned(), members, dependents)


def _wheel_unit(digest: str) -> PackageManifest:
    return PackageManifest.model_validate(
        {
            "name": "wheel-unit",
            "version": "0.1.0",
            "summary": "A venv unit for the unpinned check",
            "categories": ["navigation-maps"],
            "install": [
                {
                    "install": {
                        "method": "venv",
                        "requirements": [
                            f"https://example.invalid/x-0.1.0-py3-none-any.whl --hash=sha256:{digest}"
                        ],
                    }
                }
            ],
            "update": {"probe": {"method": "apt_policy"}, "strategy": "apt_upgrade"},
            "documentation": _unit().documentation.model_dump(mode="json", exclude_none=True),
        }
    )


def test_the_engine_refuses_the_zero_digest_at_plan_time_by_name() -> None:
    from hammunition.plan import _check_engine_capability

    unpinned = _wheel_unit(UNPINNED)
    found = _check_engine_capability(unpinned, unpinned.install[0])
    assert [b.subject for b in found] == ["wheel-unit"]
    assert "unpinned" in found[0].reason and "all-zero" in found[0].reason

    pinned = _wheel_unit("ab" * 32)
    assert _check_engine_capability(pinned, pinned.install[0]) == []


def test_the_three_places_that_name_the_tree_agree() -> None:
    """The manifest's PYTHONPATH, the engine's call-through and the backend's
    destination (<prefix>/share/hammunition/<unit>) are written separately; a
    change to one must fail here."""
    from hammunition.backends.source import DEFAULT_PREFIX
    from hammunition.cli.main import TETHER_TREE

    (svc,) = _unit().user_services
    installed = DEFAULT_PREFIX / "share" / "hammunition" / _unit().name
    assert installed == TETHER_TREE
    assert f"PYTHONPATH={installed}/src" in svc.exec
