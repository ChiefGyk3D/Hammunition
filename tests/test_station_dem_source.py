# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The ``dem_source`` station key.  D-068, amended 2026-10-01.

``copernicus`` (the default, also when unset) or ``3dep``: which elevation
QMapShack's hillshade, slope and contours are drawn from. Never a template
variable.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from hammunition.station import (
    DEM_PROVIDERS,
    STATION_FIELDS,
    Station,
    StationError,
    load_station,
    save_station,
)

cli = importlib.import_module("hammunition.cli.main")


def test_unset_means_copernicus() -> None:
    assert Station().elevation == "copernicus"
    assert Station(dem_source="3dep").elevation == "3dep"
    assert DEM_PROVIDERS == {"copernicus": "copernicus-glo30", "3dep": "usgs-3dep"}


def test_an_unknown_source_is_refused_naming_both() -> None:
    with pytest.raises(StationError, match="copernicus, 3dep"):
        Station(dem_source="srtm")


def test_it_is_not_a_template_variable_and_round_trips(tmp_path: Path) -> None:
    assert "dem_source" not in STATION_FIELDS
    path = tmp_path / "station.yml"
    save_station(Station(callsign="N0TST", dem_source="3dep"), path=path)
    assert load_station(path=path) == Station(callsign="N0TST", dem_source="3dep")
    assert Station(dem_source="3dep").as_dict() == {"dem_source": "3dep"}


def _env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("SUDO_USER", raising=False)
    monkeypatch.setenv("USER", "op")
    return tmp_path / "hammunition" / "station.yml"


def test_station_set_dem_source_alone_saves_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _env(monkeypatch, tmp_path)
    save_station(Station(callsign="N0TST"), path=path)
    assert cli.main(["station", "set", "--dem-source", "3dep"]) == 0
    assert load_station(path=path) == Station(callsign="N0TST", dem_source="3dep")
    assert "dem_source" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        cli.main(["station", "set", "--dem-source", "srtm"])


def test_station_show_prints_it_in_text_and_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _env(monkeypatch, tmp_path)
    save_station(Station(dem_source="3dep"), path=path)
    assert cli.main(["station", "show"]) == 0
    out = capsys.readouterr().out
    assert "dem_source" in out and "3dep" in out and "Nothing set" not in out
    assert cli.main(["station", "show", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["dem_source"] == "3dep"
    save_station(Station(callsign="N0TST"), path=path)
    assert cli.main(["station", "show", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["dem_source"] == "copernicus"
