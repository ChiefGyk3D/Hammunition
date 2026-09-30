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
from hammunition.manifest.schema import BinaryInstall, DataInstall, ProfileManifest
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
#: D-063: BRouter, its map-creator filters and the routing files.
BROUTER = {"brouter", "brouter-mapcreator-profiles", "brouter-segments"}


def _profile() -> ProfileManifest:
    return load_profile(CATALOG / "profiles" / "navigation.yaml")


def test_navigation_names_every_piece_2_unit_and_keeps_piece_1() -> None:
    members = set(_profile().packages)
    assert members >= PIECE_2
    assert members >= BROUTER
    assert {"gpsd", "gpsd-clients", "navit", "osm-regions", "country-boundaries", "osm-navit"} <= (
        members
    )


def test_dem_copernicus_keeps_osm_regions_as_a_dependency() -> None:
    """Without it the plan never carries the regions the tiles follow and the
    Terrain block never renders (ledger ruling, Task 13)."""
    assert "osm-regions" in load_catalog(CATALOG / "packages")["dem-copernicus"].depends


def test_socat_is_retired_with_the_old_tether_and_still_uninstallable(tmp_path: Path) -> None:
    """The tether makes its own NMEA (D-061, amended 2026-09-29). socat stays
    in the catalog as retired, so a v0.14.0 machine can still remove it."""
    from hammunition.backends.apt import AptPackageState
    from hammunition.manifest.schema import Status
    from hammunition.state import RemovalPaths, plan_removal
    from test_plan import TARGET

    catalog = load_catalog(CATALOG / "packages")
    assert catalog["socat"].status is Status.retired
    assert "socat" not in _profile().packages
    assert not any("socat" in m.depends for m in catalog.values())
    plan = plan_removal(
        ["socat"],
        catalog=catalog,
        profiles={"navigation": _profile()},
        target=TARGET,
        attributed=frozenset({"socat"}),
        states={"socat": AptPackageState("socat", installed="1.8.0.3", candidate="1.8.0.3")},
        paths=RemovalPaths(
            prefix=tmp_path / "prefix",
            venv_root=tmp_path / "venvs",
            bin_dir=tmp_path / "bin",
            applications_dir=tmp_path / "apps",
        ),
    )
    assert plan.apt_packages == ("socat",)


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
    assert "BRouter routing files over 1 region(s)" in text
    assert "elevation from 1 tile(s)" in text
    assert "never downloaded from brouter.de" in text

    assert cli.main([*argv, "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    install = doc["install"]
    planned = {p["name"] for p in install["packages"]}
    assert set(_profile().packages) <= planned, "a navigation member did not resolve"
    assert install["deferrals"] == [], install["deferrals"]
    assert [t["tile"] for t in install["maps"]["terrain"]["fetch"]] == [TILE]
    assert install["maps"]["terrain"]["brouter_regions"] == 1


def test_brouter_s_pins_are_the_measured_ones() -> None:
    """D-063: the zip by GitHub's asset digest, the two filters by the
    sha256 of the v1.7.10 source tarball's members, fetched by commit."""
    catalog = load_catalog(CATALOG / "packages")
    zip_block = catalog["brouter"].install[0].install
    assert isinstance(zip_block, BinaryInstall)
    assert zip_block.artifact.sha256 == (
        "023fec3ba997758e8cd7ab9e1bae52e962af3f00b57683e3de86b84ffad01532"
    )
    assert zip_block.tree_marker == "brouter-1.7.10-all.jar"
    assert "default-jre-headless" in catalog["brouter"].depends
    filters = catalog["brouter-mapcreator-profiles"].install[0].install
    assert isinstance(filters, DataInstall)
    assert {a.install_as: (a.sha256[:8], a.size) for a in filters.artifacts} == {
        "all.brf": ("87d49d6a", 511),
        "softaccess.brf": ("0c04a588", 631),
    }
    assert all("/4d2639af77ea5ed9c30d3e400764eb6f9e8522da/" in a.url for a in filters.artifacts)


def test_nothing_in_the_catalog_fetches_from_brouter_de() -> None:
    """brouter.de publishes no checksum; D-063 builds the routing files instead."""
    for path in (CATALOG / "packages").glob("*.yaml"):
        body = [line for line in path.read_text().splitlines() if not line.lstrip().startswith("#")]
        assert not any("url:" in line and "brouter.de" in line for line in body), path.name
