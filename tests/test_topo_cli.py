# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""US Topo end to end through `hammunition install --dry-run` and
`hammunition update` (D-068). Synthetic region, synthetic sheet, no network."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from hammunition.backends.regions import data_root
from test_json_plan_terrain import OCEANIA
from test_terrain_cli import _DOCS, _HEADER, _machine, _terrain_catalog

MD5 = "0123456789abcdef0123456789abcdef"
#: Inside the synthetic outline (0.2..0.8 degrees square).
ROW = f"0.25 0.25 0.375 0.375 9000000 {MD5}-2 ZZ/ZZ_Alpha_20240101"
USGS = """\
      licence: Public domain (USGS)
      licence_url: https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits
"""


class QuadProbe:
    def __init__(self) -> None:
        self.asked: list[str] = []

    def head(self, url: str) -> tuple[int, int, str | None]:
        self.asked.append(url)
        return 200, 9_000_000, f'"{MD5}-2"'


def _catalog(tmp_path: Path, *, index: bool = True) -> Path:
    root = _terrain_catalog(tmp_path)
    if index:
        (root / "data" / "ustopo-quads.txt").write_text(f"# test index\n{ROW}\n")
    (root / "packages" / "usgs-ustopo.yaml").write_text(
        _HEADER
        + """\
name: usgs-ustopo
version: station
summary: US Topo for a test
categories: [navigation-maps]
depends: [osm-regions]
install:
  - install:
      method: topo-quads
      provider: usgs-ustopo
"""
        + USGS
        + _DOCS
    )
    (root / "packages" / "ustopo-qmapshack.yaml").write_text(
        _HEADER
        + """\
name: ustopo-qmapshack
version: station
summary: The US Topo mosaic for a test
categories: [navigation-maps]
depends: [usgs-ustopo]
install:
  - install:
      method: derived
      converter: ustopo-mosaic
      source: usgs-ustopo
"""
        + USGS
        + _DOCS
    )
    return root


def _cli(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Any, QuadProbe]:
    cli = _machine(monkeypatch, tmp_path)
    probe = QuadProbe()
    monkeypatch.setattr(cli, "ustopo_probe", lambda: probe)
    return cli, probe


def test_the_dry_run_discloses_each_sheet_and_the_warp_and_changes_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli, probe = _cli(monkeypatch, tmp_path)
    catalog = str(_catalog(tmp_path))
    before = sorted(p for p in tmp_path.rglob("*") if "xdg_" not in str(p))
    assert cli.main(["--catalog", catalog, "install", "--dry-run", "ustopo-qmapshack"]) == 0
    text = capsys.readouterr().out
    assert "US Topo, USGS 7.5-minute quads (D-068):" in text
    assert f"{OCEANIA.region}  1 quad(s), 9.0 MB; 9.0 MB to download" in text
    assert "ZZ_Alpha_20240101" in text
    assert "MD5 from the publisher's object metadata; not pinned by Hammunition" in text
    assert "Fetch US Topo quad ZZ_Alpha_20240101" in text
    assert "Warp US Topo quad ZZ_Alpha_20240101" in text
    assert "gdalwarp -q -overwrite -t_srs EPSG:3857 -te_srs EPSG:4269 -te 0.25 0.25" in text
    assert "warped for QMapShack: 1 quad(s)" in text
    assert text.count("[check-terrain]") == 1, "one ledger step for terrain and US Topo"
    assert probe.asked == [
        "https://prd-tnm.s3.amazonaws.com/StagedProducts/Maps/USTopo/GeoTIFF/ZZ/"
        "ZZ_Alpha_20240101_TM_geo.tif"
    ]
    assert sorted(p for p in tmp_path.rglob("*") if "xdg_" not in str(p)) == before
    assert (
        cli.main(["--catalog", catalog, "install", "--dry-run", "--json", "ustopo-qmapshack"]) == 0
    )
    doc = json.loads(capsys.readouterr().out)
    topo = doc["install"]["maps"]["terrain"]["topo"]
    assert [q["quad"] for q in topo["fetch"]] == ["ZZ_Alpha_20240101"]
    assert topo["warp"] == 1 and topo["regions"][0]["quads"] == 1


def test_a_missing_index_refuses_the_plan_by_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli, _ = _cli(monkeypatch, tmp_path)
    catalog = str(_catalog(tmp_path, index=False))
    assert cli.main(["--catalog", catalog, "install", "--dry-run", "usgs-ustopo"]) == 2
    err = capsys.readouterr().err
    assert "ustopo-quads.txt" in err and "Nothing was changed." in err


def test_update_counts_sheets_and_names_none(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli, _ = _cli(monkeypatch, tmp_path)
    catalog = str(_catalog(tmp_path))
    out = data_root(tmp_path) / "usgs-ustopo"
    out.mkdir(parents=True)
    (out / "ZZ_Alpha_20240101.tif").write_bytes(b"q")
    (out / "ZZ_Alpha_20200101.tif").write_bytes(b"q")  # an edition the index replaced
    assert cli.main(["--catalog", catalog, "update", "usgs-ustopo", "ustopo-qmapshack"]) in (0, 1)
    text = capsys.readouterr().out
    assert "2 US Topo quad(s) installed; 1 of them have a newer edition" in text
    assert "ZZ_Alpha" not in text
    assert "hammunition install usgs-ustopo ustopo-qmapshack" in text
