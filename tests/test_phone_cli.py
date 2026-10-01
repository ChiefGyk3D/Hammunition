# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The phone units through ``hammunition install --dry-run``.  D-067.

The same machine the terrain wiring tests use (no real apt, no network, an
unprivileged operator), with Vermont as the one region and the catalog's own
two phone manifests. Nothing is fetched, built or written.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from hammunition.backends.regions import MapResolution
from hammunition.station import Station, save_station
from test_mapsforge import VERMONT
from test_terrain_cli import _DOCS, _HEADER

REPO = Path(__file__).resolve().parent.parent


def _machine(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Any:
    from hammunition.backends.source import SourceBackend
    from test_json_install import _machine as json_machine
    from test_json_install import cli

    json_machine(monkeypatch, tmp_path)
    save_station(
        Station(callsign="N0TST", map_regions=(VERMONT.region,)),
        path=tmp_path / "xdg_config_home" / "hammunition" / "station.yml",
    )
    monkeypatch.setattr(
        cli,
        "SourceBackend",
        lambda fetcher, *, build_root, owner=None: SourceBackend(
            fetcher, build_root=build_root, prefix=tmp_path, owner=owner
        ),
    )
    monkeypatch.setattr(cli, "resolve_map_regions", lambda *a, **k: MapResolution(files=(VERMONT,)))
    return cli


def _catalog(tmp_path: Path) -> str:
    root = tmp_path / "catalog"
    (root / "packages").mkdir(parents=True)
    (root / "packages" / "osm-regions.yaml").write_text(
        _HEADER
        + """\
name: osm-regions
version: station
summary: Map regions for a test
categories: [navigation-maps]
install:
  - install:
      method: osm-regions
      provider: geofabrik
      licence: ODbL-1.0
      licence_url: https://www.openstreetmap.org/copyright
"""
        + _DOCS
    )
    for unit in ("mapsforge-map", "mapsforge-poi"):
        shutil.copy(REPO / "catalog" / "packages" / f"{unit}.yaml", root / "packages")
    return str(root)


def test_the_dry_run_shows_both_builds_and_the_writer_s_fetch_in_text_and_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli = _machine(monkeypatch, tmp_path)
    catalog = _catalog(tmp_path)
    argv = ["--catalog", catalog, "install", "--dry-run", "mapsforge-map", "mapsforge-poi"]
    assert cli.main(argv) == 0
    text = capsys.readouterr().out
    assert "Build the Mapsforge map of north-america/us/vermont" in text
    assert "Build the Mapsforge POI file of north-america/us/vermont" in text
    assert "Fetch the Mapsforge POI writer for mapsforge-poi" in text
    assert "sha256, pinned by Hammunition" in text
    assert text.count("[check-phone-maps]") == 1
    assert "Dry run: nothing above was executed." in text
    assert cli.main([*argv, "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    states = {u["name"]: u["state"] for u in doc["install"]["packages"]}
    assert states["mapsforge-map"] == states["mapsforge-poi"] == "will convert"
    assert not (tmp_path / "share").exists(), "a dry run writes nothing"


def test_a_disk_short_of_the_phone_needs_refuses_the_plan_naming_its_factors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from hammunition.backends.terrain import combined_shortfall

    cli = _machine(monkeypatch, tmp_path)
    monkeypatch.setattr(
        cli,
        "combined_shortfall",
        lambda maps, terrain, **kw: combined_shortfall(maps, terrain, free_at=lambda path: 0, **kw),
    )
    argv = ["--catalog", _catalog(tmp_path), "install", "--dry-run", "mapsforge-map"]
    assert cli.main(argv) == 2
    err = capsys.readouterr().err
    assert "Nothing was changed." in err
    assert "phone maps" in err and "measured on one region" in err
