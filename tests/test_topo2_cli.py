# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""FSTopo and 3DEP end to end through `hammunition install --dry-run` and
`hammunition update` (D-068, amended 2026-10-01). Synthetic region,
synthetic sheet and tile, no network."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from hammunition.backends.regions import data_root
from hammunition.fstopo import GATEWAY, map_url
from hammunition.station import Station, save_station
from hammunition.usgs3dep import tile_url
from hammunition.ustopo import UNPINNED
from test_json_plan_terrain import OCEANIA
from test_terrain_cli import _DOCS, _HEADER, A
from test_topo_cli import MD5, QuadProbe
from test_topo_cli import _catalog as _ustopo_catalog
from test_topo_cli import _cli as _ustopo_cli

THREE = "USGS_13_n01e000"
SHEET = "ZZ_Alpha_1230000_11"
FILE = f"{GATEWAY}data3/00000/fstopo/FSTopo%20Alpha%201230000.tiff"
USGS = """\
      licence: Public domain (USGS)
      licence_url: https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits
"""
USFS = """\
      licence: Public domain (USDA Forest Service)
      licence_url: https://www.fs.usda.gov/
"""


class BucketProbe(QuadProbe):
    """US Topo's and 3DEP's bucket: a 3DEP tile answers its own size and ETag."""

    def head(self, url: str) -> tuple[int, int, str | None]:
        if url == tile_url(THREE):
            self.asked.append(url)
            return 200, 480_000_000, f'"{MD5}-92"'
        return super().head(url)


class Gateway:
    def __init__(self) -> None:
        self.asked: list[str] = []

    def __call__(self, url: str) -> tuple[int, int, str | None]:
        self.asked.append(url)
        if url == map_url(1230000):
            return 302, 0, f"{GATEWAY}data3/00000/fstopo/FSTopo Alpha 1230000.tiff"
        assert url == FILE
        return 200, 21_000_000, None


def _unit(name: str, body: str) -> str:
    return _HEADER + body + _DOCS


def _catalog(tmp_path: Path) -> Path:
    root = _ustopo_catalog(tmp_path)
    data = root / "data"
    (data / "usgs-3dep-tiles.txt").write_text(f"# test list\n{THREE} 480000000 {MD5}-92\n")
    (data / "fstopo-quads.txt").write_text(
        "# test index\n0.25 0.25 0.375 0.375 1230000 11 ZZ Alpha\n"
    )
    (data / "fstopo-pins.yaml").write_text("pins: []\n")
    packages = root / "packages"
    (packages / "dem-3dep.yaml").write_text(
        _unit(
            "dem-3dep",
            """\
name: dem-3dep
version: station
summary: 3DEP for a test
categories: [navigation-maps]
depends: [osm-regions]
install:
  - install:
      method: dem-tiles
      provider: usgs-3dep
"""
            + USGS,
        )
    )
    (packages / "usfs-fstopo.yaml").write_text(
        _unit(
            "usfs-fstopo",
            """\
name: usfs-fstopo
version: station
summary: FSTopo for a test
categories: [navigation-maps]
depends: [osm-regions]
install:
  - install:
      method: topo-quads
      provider: usfs-fstopo
"""
            + USFS,
        )
    )
    gdal = packages / "dem-qmapshack.yaml"
    gdal.write_text(
        gdal.read_text()
        .replace("depends: [dem-copernicus]", "depends: [dem-copernicus, dem-3dep]")
        .replace(
            "      source: dem-copernicus\n",
            "      source: dem-copernicus\n      alternative: dem-3dep\n",
        )
    )
    mosaic = packages / "ustopo-qmapshack.yaml"
    mosaic.write_text(
        mosaic.read_text().replace(
            "      source: usgs-ustopo\n", "      source: usgs-ustopo\n      fstopo: usfs-fstopo\n"
        )
    )
    return root


def _cli(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, source: str | None = None
) -> tuple[Any, BucketProbe, Gateway]:
    cli, _ = _ustopo_cli(monkeypatch, tmp_path)
    bucket, gateway = BucketProbe(), Gateway()
    monkeypatch.setattr(cli, "ustopo_probe", lambda: bucket)
    from hammunition.fstopo import GatewayProbe

    monkeypatch.setattr(cli, "GatewayProbe", lambda: GatewayProbe(gateway))
    save_station(
        Station(callsign="N0TST", map_regions=(OCEANIA.region,), dem_source=source),
        path=tmp_path / "xdg_config_home" / "hammunition" / "station.yml",
    )
    return cli, bucket, gateway


def _dry(cli: Any, catalog: Path, *units: str, json_out: bool = False) -> int:
    extra = ["--json"] if json_out else []
    return int(cli.main(["--catalog", str(catalog), "install", "--dry-run", *extra, *units]))


def test_with_copernicus_chosen_3dep_is_named_not_fetched_and_contours_stay_copernicus(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli, bucket, _ = _cli(monkeypatch, tmp_path)
    catalog = _catalog(tmp_path)
    assert _dry(cli, catalog, "dem-qmapshack") == 0
    text = capsys.readouterr().out
    assert "USGS 3DEP bare-earth elevation (D-068):" in text
    assert "not chosen: dem_source is copernicus" in text
    assert "dem-3dep: dem_source is copernicus (the default)" in text
    assert f"Fetch terrain tile {A}" in text and THREE not in text
    assert tile_url(THREE) not in bucket.asked
    assert _dry(cli, catalog, "dem-qmapshack", json_out=True) == 0
    terrain = json.loads(capsys.readouterr().out)["install"]["maps"]["terrain"]
    assert terrain["contours_from"] == "copernicus-glo30"
    assert terrain["bare_earth"]["chosen"] is False and terrain["bare_earth"]["fetch"] == []


def test_with_3dep_chosen_its_tile_is_sized_per_region_and_draws_the_contours(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli, bucket, _ = _cli(monkeypatch, tmp_path, source="3dep")
    catalog = _catalog(tmp_path)
    before = sorted(p for p in tmp_path.rglob("*") if "xdg_" not in str(p))
    assert _dry(cli, catalog, "dem-qmapshack") == 0
    text = capsys.readouterr().out
    assert f"{OCEANIA.region}  1 tile(s); 0.48 GB to download" in text
    assert f"Fetch 3DEP bare-earth tile {THREE}" in text
    assert UNPINNED in text
    assert "contours for 1 tile(s) of USGS 3DEP" in text
    assert "-ts 10812 10812" in text
    assert f"Fetch terrain tile {A}" in text, "Copernicus stays, for BRouter and abroad"
    assert tile_url(THREE) in bucket.asked
    assert sorted(p for p in tmp_path.rglob("*") if "xdg_" not in str(p)) == before
    assert _dry(cli, catalog, "dem-qmapshack", json_out=True) == 0
    terrain = json.loads(capsys.readouterr().out)["install"]["maps"]["terrain"]
    assert terrain["contours_from"] == "usgs-3dep"
    assert [t["tile"] for t in terrain["bare_earth"]["fetch"]] == [THREE]
    assert terrain["bare_earth"]["regions"][0]["download"] == 480_000_000


def test_switching_back_to_copernicus_plans_the_3dep_tiles_removal(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli, _, _ = _cli(monkeypatch, tmp_path)
    catalog = _catalog(tmp_path)
    data = data_root(tmp_path) / "dem-3dep"
    data.mkdir(parents=True)
    (data / f"{THREE}.tif").write_bytes(b"e")
    (data / f"{OCEANIA.slug}.tiles").write_text(f"# squares with no published tile: 0\n{THREE}\n")
    assert _dry(cli, catalog, "dem-qmapshack") == 0
    text = capsys.readouterr().out
    assert f"{data / THREE}.tif" in text and "Remove" in text


def test_fstopo_installed_by_name_is_disclosed_unverified_and_converted_into_a_second_map(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli, _, gateway = _cli(monkeypatch, tmp_path)
    catalog = _catalog(tmp_path)
    assert _dry(cli, catalog, "usfs-fstopo", "ustopo-qmapshack") == 0
    text = capsys.readouterr().out
    assert "FSTopo, Forest Service 7.5-minute quads (D-068):" in text
    assert f"{OCEANIA.region}  1 quad(s); 21.0 MB to download" in text
    assert "unverified: the Forest Service publishes no checksum" in text
    assert "warning: 1 quad(s) unverified" in text
    assert f"Fetch FSTopo quad {SHEET}" in text
    assert f"Convert FSTopo quad {SHEET}" in text and "gdal_translate -q -expand rgb" in text
    assert "FSTopo.vrt" in text
    assert gateway.asked == [map_url(1230000), FILE]
    assert text.count("[check-terrain]") == 1
    assert _dry(cli, catalog, "usfs-fstopo", "ustopo-qmapshack", json_out=True) == 0
    fstopo = json.loads(capsys.readouterr().out)["install"]["maps"]["terrain"]["fstopo"]
    assert [q["quad"] for q in fstopo["fetch"]] == [SHEET]
    assert fstopo["unverified"] == 1 and fstopo["convert"] == 1


def test_update_counts_fstopo_sheets_and_3dep_tiles_and_names_none(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli, _, _ = _cli(monkeypatch, tmp_path)
    catalog = _catalog(tmp_path)
    sheets = data_root(tmp_path) / "usfs-fstopo"
    sheets.mkdir(parents=True)
    (sheets / f"{SHEET}.tif").write_bytes(b"s")
    (sheets / "ZZ_Alpha_1230000_9.tif").write_bytes(b"s")  # a vintage the index replaced
    tiles = data_root(tmp_path) / "dem-3dep"
    tiles.mkdir(parents=True)
    (tiles / f"{THREE}.tif").write_bytes(b"e")
    assert cli.main(
        ["--catalog", str(catalog), "update", "usfs-fstopo", "ustopo-qmapshack", "dem-3dep"]
    ) in (0, 1)
    text = capsys.readouterr().out
    assert "2 FSTopo quad(s) installed; 1 of them have a newer edition" in text
    assert "1 3DEP tile(s) installed" in text
    assert "Alpha" not in text and THREE not in text
    assert "hammunition install usfs-fstopo ustopo-qmapshack" in text


def test_us_topo_alone_plans_no_fstopo_and_asks_no_gateway(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli, _, gateway = _cli(monkeypatch, tmp_path)
    catalog = _catalog(tmp_path)
    assert _dry(cli, catalog, "ustopo-qmapshack") == 0
    text = capsys.readouterr().out
    assert "usfs-fstopo" not in text and "FSTopo" not in text
    assert "Warp US Topo quad" in text
    assert gateway.asked == []


def test_installed_fstopo_sheets_are_mosaicked_when_the_unit_is_not_planned(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from hammunition.backends.fstopo import RegionSheets, render_record
    from hammunition.fstopo import parse_row

    cli, _, gateway = _cli(monkeypatch, tmp_path)
    catalog = _catalog(tmp_path)
    sheets = data_root(tmp_path) / "usfs-fstopo"
    sheets.mkdir(parents=True)
    quad = parse_row("0.25 0.25 0.375 0.375 1230000 11 ZZ Alpha")
    (sheets / f"{SHEET}.tif").write_bytes(b"II*\x00")
    (sheets / f"{OCEANIA.slug}.quads").write_text(
        render_record(RegionSheets(OCEANIA.region, OCEANIA.slug, (quad,)))
    )
    assert _dry(cli, catalog, "ustopo-qmapshack") == 0
    text = capsys.readouterr().out
    assert f"Convert FSTopo quad {SHEET}" in text and "FSTopo.vrt" in text
    assert "Fetch FSTopo quad" not in text and "Remove" not in text.split("FSTopo")[0][-200:]
    assert gateway.asked == []


def test_every_sheet_pinned_is_said_in_the_plan(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli, _, _ = _cli(monkeypatch, tmp_path)
    catalog = _catalog(tmp_path)
    (catalog / "data" / "fstopo-pins.yaml").write_text(
        f"pins:\n- secoord: 1230000\n  size: 21000000\n  sha256: {'a' * 64}\n"
    )
    assert _dry(cli, catalog, "usfs-fstopo") == 0
    text = capsys.readouterr().out
    assert "every FSTopo quad your regions need is pinned by Hammunition" in text
    assert "unverified" not in text
