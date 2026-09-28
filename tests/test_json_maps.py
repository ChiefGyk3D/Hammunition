# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``maps regions --json``, and the never-name-a-region rule end to end
through ``update``.  D-057, D-059.

The plan's own map section (``MapSectionView``, ``InstallPlanView.maps`` and
``.region_notes``) and the station document's ``map_regions``/
``map_freshness`` fields are covered where they were built: Task 4's
``tests/test_json_plan.py`` (``plan-maps-text`` golden, ``build_install_view``)
and Task 5's ``tests/test_json_station_hardware.py`` (``station-regions``
golden, the never-in-text assertion). This file is what neither covers: the
``maps regions`` command's own document, and one end-to-end run of ``update``
against a real installed region, reached through :func:`cli.main` rather than
:func:`hammunition.update.report` directly (that unit-level check is
``test_no_region_name_appears_in_the_document_even_when_regions_are_installed``
in ``tests/test_json_update.py``).
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from hammunition.station import Station, save_station
from json_support import parse_one, validate

cli = importlib.import_module("hammunition.cli.main")

REGIONS_CATALOG = Path(__file__).resolve().parent / "fixtures" / "json" / "catalog-regions"


def test_maps_regions_text_is_unchanged(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class Index:
        def text(self, url: str) -> str:
            return "{}"

    monkeypatch.setattr(cli, "UrllibProbe", Index)
    monkeypatch.setattr(
        cli,
        "region_ids",
        lambda index_json: ["atlantis/oceania", "atlantis/oceania-north", "narnia/cair-paravel"],
    )
    assert cli.main(["maps", "regions", "atlantis/oceania"]) == 0
    out = capsys.readouterr().out
    assert out == "atlantis/oceania\natlantis/oceania-north\n"


def test_maps_regions_json_lists_the_filtered_regions(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class Index:
        def text(self, url: str) -> str:
            return "{}"

    monkeypatch.setattr(cli, "UrllibProbe", Index)
    monkeypatch.setattr(
        cli,
        "region_ids",
        lambda index_json: ["atlantis/oceania", "atlantis/oceania-north", "narnia/cair-paravel"],
    )
    assert cli.main(["maps", "regions", "atlantis/oceania", "--json"]) == 0
    doc = parse_one(capsys.readouterr().out)
    validate(doc)
    assert doc["kind"] == "regions" and doc["filter"] == "atlantis/oceania"
    assert doc["regions"] == ["atlantis/oceania", "atlantis/oceania-north"]


def test_maps_regions_json_with_no_filter_lists_every_region(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class Index:
        def text(self, url: str) -> str:
            return "{}"

    monkeypatch.setattr(cli, "UrllibProbe", Index)
    monkeypatch.setattr(cli, "region_ids", lambda index_json: ["atlantis/oceania", "narnia"])
    assert cli.main(["maps", "regions", "--json"]) == 0
    doc = parse_one(capsys.readouterr().out)
    validate(doc)
    assert doc["filter"] is None
    assert doc["regions"] == ["atlantis/oceania", "narnia"]


def test_maps_regions_json_reports_a_geofabrik_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A fetch failure still ends in exactly one document on stdout (D-059),
    same as any other command with no plan of its own to refuse."""
    from hammunition.geofabrik import GeofabrikError

    class Index:
        def text(self, url: str) -> str:
            raise GeofabrikError("could not reach Geofabrik")

    monkeypatch.setattr(cli, "UrllibProbe", Index)
    assert cli.main(["maps", "regions", "--json"]) == cli.EXIT_FAILED
    doc = parse_one(capsys.readouterr().out)
    assert doc["kind"] == "error"
    assert "could not reach Geofabrik" in doc["message"]


def test_update_end_to_end_with_an_installed_region_never_names_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """One region installed on disk, reached through `hammunition update`
    itself -- not `report()`/`build_update()` directly, which is already
    covered in `tests/test_json_update.py`. A placeholder region only
    (D-057: never a real one)."""
    from test_json_update import _machine

    _machine(monkeypatch, tmp_path)
    save_station(
        Station(callsign="N0TST", map_regions=("atlantis/oceania",)),
        path=tmp_path / "config" / "hammunition" / "station.yml",
    )
    # installed_slugs() reads `.source` sidecars under the data prefix; the
    # only thing the region's name proves here is that it never leaves this
    # test, so the disk is stood in for rather than actually written to.
    monkeypatch.setattr(cli, "installed_slugs", lambda directory: {"atlantis-oceania": "260101"})
    for argv in (
        ["update", "fixture-regions", "--json"],
        ["update", "fixture-regions"],
    ):
        rc = cli.main(["--catalog", str(REGIONS_CATALOG), *argv])
        out = capsys.readouterr().out
        assert rc == 0, out
        assert "atlantis" not in out and "oceania" not in out, f"{argv} named the region"
        assert "1 region" in out, f"{argv} lost the count"
