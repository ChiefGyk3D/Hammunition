# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The terrain readers in the catalog.  D-061, amended 2026-10-02.

`splat-sdf` and `signal-server` join `antenna`, where `splat` is; with no
map regions set the terrain is deferred by name and the rest installs.
"""

from __future__ import annotations

from pathlib import Path

from hammunition.manifest.load import load_catalog, load_profile
from hammunition.manifest.schema import DerivedDataInstall, GitInstall
from hammunition.station import Station
from test_plan import _resolve

CATALOG = Path(__file__).resolve().parents[1] / "catalog"


def test_both_units_join_antenna_beside_splat() -> None:
    profile = load_profile(CATALOG / "profiles" / "antenna.yaml")
    assert {"splat", "splat-sdf", "signal-server"} <= set(profile.packages)


def test_splat_sdf_reads_copernicus_or_3dep_and_needs_splat_s_tools() -> None:
    catalog = load_catalog(CATALOG / "packages")
    block = catalog["splat-sdf"].install[0].install
    assert isinstance(block, DerivedDataInstall)
    assert (block.converter, block.source, block.alternative) == (
        "splat-sdf",
        "dem-copernicus",
        "dem-3dep",
    )
    assert {"splat", "gdal-bin", "bzip2"} <= set(catalog["splat-sdf"].depends)


def test_signal_server_is_pinned_with_a_review_and_built_without_ndebug() -> None:
    catalog = load_catalog(CATALOG / "packages")
    block = catalog["signal-server"].install[0].install
    assert isinstance(block, GitInstall)
    assert block.repo == "https://github.com/W3AXL/Signal-Server"
    assert block.ref == "7f6242afb3685ff31d9ad14062b80d692ee56327"
    assert block.pin_review is not None and block.pin_review.basis == "own_choice"
    assert block.project_file == "src"
    # Release adds -DNDEBUG, which compiles out the allocation inside
    # ITWOM's assert() and crashes every plot (measured 2026-10-01).
    assert "-DCMAKE_CXX_FLAGS_RELEASE=-O2" in block.configure_args
    # One program choosing its resolution by the name it runs under.
    names = {b.install_as for b in catalog["signal-server"].binaries}
    assert names == {"signalserver", "signalserverHD", "signalserverLIDAR"}


def test_without_regions_the_terrain_is_deferred_and_the_programs_plan(tmp_path: Path) -> None:
    catalog = load_catalog(CATALOG / "packages")
    profile = load_profile(CATALOG / "profiles" / "antenna.yaml")
    small = profile.model_copy(update={"packages": ["splat", "splat-sdf", "signal-server"]})
    plan = _resolve(
        tmp_path,
        ["antenna"],
        catalog=catalog,
        profiles={"antenna": small},
        known={
            "splat": None,
            "build-essential": "12.12",
            "cmake": "3.31.6-2",
            "libspdlog-dev": "1:1.15.2+ds-2",
            "libbz2-dev": "1.0.8-6",
            "zlib1g-dev": "1:1.3.dfsg+really1.3.1-1",
            "git": "1:2.47.3-0+deb13u1",
        },
        station=Station(),
    )
    assert sorted(p.name for p in plan.packages) == ["signal-server", "splat"]
    deferred = {d.subject: d.why for d in plan.deferrals}
    assert deferred.get("splat-sdf") == "no map regions set"
