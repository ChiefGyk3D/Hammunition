# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The station-set document consumed by local front ends (D-059)."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest

from hammunition.station import load_station
from json_support import parse_one, validate

cli = importlib.import_module("hammunition.cli.main")


def _set_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("SUDO_USER", raising=False)
    return tmp_path / "hammunition" / "station.yml"


def test_station_set_json_reports_saved_and_unchanged_values(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _set_env(monkeypatch, tmp_path)

    assert cli.main(["station", "set", "--dem-source", "3dep", "--json"]) == 0
    saved = parse_one(capsys.readouterr().out)
    validate(saved)
    assert saved["kind"] == "station-set"
    assert saved["saved"] == {"dem_source": "3dep"}
    assert saved["unchanged"] == {}
    assert saved["refused"] == []
    assert saved["file"] == str(path)

    assert cli.main(["station", "set", "--dem-source", "3dep", "--json"]) == 0
    unchanged = parse_one(capsys.readouterr().out)
    assert unchanged["saved"] == {}
    assert unchanged["unchanged"] == {"dem_source": "3dep"}
    assert load_station(path=path).dem_source == "3dep"


def test_station_set_json_reports_each_refusal_and_saves_valid_flags(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _set_env(monkeypatch, tmp_path)

    result = cli.main(
        [
            "station",
            "set",
            "--map-regions",
            ",",
            "--reference-books",
            "unknown-book-id",
            "--map-freshness",
            "monthly",
            "--json",
        ]
    )
    assert result == 2
    doc: dict[str, Any] = parse_one(capsys.readouterr().out)
    validate(doc)
    assert doc["kind"] == "station-set"
    assert doc["saved"] == {"map_freshness": "monthly"}
    assert doc["unchanged"] == {}
    assert [refusal["key"] for refusal in doc["refused"]] == [
        "map_regions",
        "reference_books",
    ]
    assert doc["refused"][0]["value"] == ","
    assert "give at least one region" in doc["refused"][0]["reason"]
    assert doc["refused"][1]["value"] == "unknown-book-id"
    assert "not in the catalog's book list" in doc["refused"][1]["reason"]
    assert doc["file"] == str(path)
    assert load_station(path=path).freshness == "monthly"


def test_station_set_text_success_is_unchanged(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _set_env(monkeypatch, tmp_path)

    assert cli.main(["station", "set", "--dem-source", "3dep"]) == 0

    assert capsys.readouterr().out == f"Saved to {path} (mode 0600).\n  dem_source     3dep\n"
