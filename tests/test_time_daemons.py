# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The chrony unit: GPS time where the daemon is not ntpsec.  D-072.

docs/reference/time-daemons.md is the evidence: chrony, ntpsec and
systemd-timesyncd each Provide and Conflict with `time-daemon` on every
target, so installing one removes the other, and the engine refuses any
removal (D-022). These tests hold the three consequences the ruling rests on.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from hammunition.manifest.load import load_catalog, load_profiles

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOG = load_catalog(REPO_ROOT / "catalog" / "packages")


def test_chrony_declares_both_daemons_it_displaces() -> None:
    """Declared, so the refusal names chrony as the unit that displaces them
    rather than calling the removal a catalog defect."""
    chrony = CATALOG["chrony"]
    assert set(chrony.conflicts_with_repo_package) == {"systemd-timesyncd", "ntpsec"}
    assert "gpsd" in chrony.depends


def test_chrony_is_in_no_profile() -> None:
    """D-022 rule 5: what displaces a distribution's choice is never in a base
    profile. As a member of `station` it would refuse the whole profile on every
    machine with a time daemon, the field laptop's ntpsec included."""
    profiles = load_profiles(REPO_ROOT / "catalog" / "profiles")
    holding = sorted(name for name, profile in profiles.items() if "chrony" in profile.packages)
    assert holding == [], f"chrony is a member of {holding}; D-072 keeps it out of every profile"


def test_chrony_writes_its_two_files_without_a_station_value() -> None:
    """Neither file needs a callsign or a grid, so neither is ever deferred (D-035),
    and neither is a conffile another package owns."""
    by_path = {c.path: c for c in CATALOG["chrony"].config_files}
    assert set(by_path) == {
        "/etc/chrony/conf.d/hammunition-gps.conf",
        "/etc/systemd/system/gpsd.service.d/hammunition-gps.conf",
    }
    assert all(not c.station_variables for c in by_path.values())
    refclock = by_path["/etc/chrony/conf.d/hammunition-gps.conf"].template
    assert "refclock SHM 0 refid GPS" in refclock
    dropin = by_path["/etc/systemd/system/gpsd.service.d/hammunition-gps.conf"].template
    assert "[Service]" in dropin and "Environment=OPTIONS=-n" in dropin


@pytest.mark.parametrize(
    ("installed", "version"),
    [("systemd-timesyncd", "257.13-1~deb13u1"), ("ntpsec", "1.2.3+dfsg1-8")],
)
def test_installing_chrony_over_another_daemon_is_refused_by_name(
    tmp_path: Path, installed: str, version: str
) -> None:
    """The simulation measured on Debian 13 (`Remv systemd-timesyncd`, `Remv
    ntpsec`) becomes a refusal naming chrony, the package, its version and the
    `apt-get remove` the operator runs deliberately."""
    from hammunition.backends.apt import AptSimulation
    from hammunition.distro import Target
    from hammunition.plan import PlanError, resolve
    from test_plan import _apt

    apt = _apt(tmp_path, {"chrony": None, "gpsd": None, "pps-tools": None, installed: version})

    class SimulatingApt(type(apt)):  # type: ignore[misc]
        def simulate(
            self, packages: Any, *, release: str | None = None, no_recommends: bool = False
        ) -> Any:
            return AptSimulation(
                ok=True,
                installs={
                    "chrony": frozenset({"stable"}),
                    "gpsd": frozenset({"stable"}),
                    "pps-tools": frozenset({"stable"}),
                },
                removes={installed: version},
            )

    apt.__class__ = SimulatingApt
    with pytest.raises(PlanError) as excinfo:
        resolve(
            ["chrony"],
            catalog=CATALOG,
            profiles={},
            target=Target(distro="debian", version="13", arch="x86_64"),
            apt=apt,
            user="op",
        )
    text = str(excinfo.value)
    assert "chrony" in text
    assert f"{installed} ({version})" in text
    assert f"sudo apt-get remove {installed}" in text
    assert "Breaks or Conflicts" in text
