# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The shipped ``navigation`` profile through the engine's dry run.  D-061.

The catalog is the real one; the machine, apt, the station's regions and
every network probe are stood in for. The region is synthetic
(``atlantis/oceania``) and its outline a synthetic square in the Sahara, so
no maintainer region, tile or size appears here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from hammunition.backends.regions import MapResolution
from hammunition.manifest.load import load_catalog, load_profile
from hammunition.manifest.schema import ProfileManifest
from hammunition.terrain_plan import poly_url
from test_json_plan_terrain import OCEANIA
from test_terrain_cli import RegionProbe, TileProbe

CATALOG = Path(__file__).resolve().parents[1] / "catalog"
# One land square, N20 E010, in the publisher's tile list; poly is lon lat.
TILE = "Copernicus_DSM_COG_10_N20_00_E010_00_DEM"
OUTLINE = "o\n1\n 10.2 20.2\n 10.8 20.2\n 10.8 20.8\nEND\nEND\n"

PIECE_2 = {
    "qmapshack",
    "routino",
    "gdal-bin",
    "mkgmap",
    "mkgmap-splitter",
    "osm-garmin",
    "osm-routino",
    "dem-copernicus",
    "dem-qmapshack",
}


def _profile() -> ProfileManifest:
    return load_profile(CATALOG / "profiles" / "navigation.yaml")


def test_navigation_names_every_piece_2_unit_and_keeps_piece_1() -> None:
    members = set(_profile().packages)
    assert members >= PIECE_2
    assert {"gpsd", "gpsd-clients", "navit", "osm-regions", "country-boundaries", "osm-navit"} <= (
        members
    )


def test_dem_copernicus_keeps_osm_regions_as_a_dependency() -> None:
    """Without it the plan never carries the regions the tiles follow and the
    Terrain block never renders (ledger ruling, Task 13)."""
    assert "osm-regions" in load_catalog(CATALOG / "packages")["dem-copernicus"].depends


def test_socat_left_the_catalog_with_the_old_tether() -> None:
    """The tether makes its own NMEA (D-061, amended 2026-09-29); nothing
    else in the catalog used socat."""
    assert "socat" not in load_catalog(CATALOG / "packages")
    assert "socat" not in _profile().packages


def test_qmapshack_carries_both_launchers() -> None:
    launchers = {
        launcher.name for launcher in load_catalog(CATALOG / "packages")["qmapshack"].launchers
    }
    assert launchers == {"qmapshack-offline", "gps-tether"}


def _machine(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Any:
    from hammunition.backends.source import SourceBackend
    from hammunition.station import Station, save_station
    from test_json_install import _machine as json_machine
    from test_json_install import cli

    json_machine(monkeypatch, tmp_path)
    save_station(
        Station(callsign="N0TST", map_regions=(OCEANIA.region,)),
        path=tmp_path / "xdg_config_home" / "hammunition" / "station.yml",
    )
    monkeypatch.setattr(
        cli,
        "SourceBackend",
        lambda fetcher, *, build_root, owner=None: SourceBackend(
            fetcher, build_root=build_root, prefix=tmp_path, owner=owner
        ),
    )
    monkeypatch.setattr(cli, "resolve_map_regions", lambda *a, **k: MapResolution(files=(OCEANIA,)))
    monkeypatch.setattr(
        cli, "UrllibProbe", lambda: RegionProbe({poly_url(OCEANIA.region): OUTLINE})
    )
    monkeypatch.setattr(cli, "S3Probe", TileProbe)
    return cli


def test_the_shipped_profile_resolves_whole_and_discloses_terrain(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli = _machine(monkeypatch, tmp_path)
    argv = ["--catalog", str(CATALOG), "install", "--dry-run", "navigation"]
    assert cli.main(argv) == 0
    text = capsys.readouterr().out
    assert "Terrain, Copernicus GLO-30 elevation (D-061):" in text
    assert f"{OCEANIA.region}  1 tile(s)" in text
    assert f"Fetch terrain tile {TILE}" in text
    assert text.count("[check-terrain]") == 1

    assert cli.main([*argv, "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    install = doc["install"]
    planned = {p["name"] for p in install["packages"]}
    assert set(_profile().packages) <= planned, "a navigation member did not resolve"
    assert install["deferrals"] == [], install["deferrals"]
    assert [t["tile"] for t in install["maps"]["terrain"]["fetch"]] == [TILE]
