# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``gdal-dem`` over USGS 3DEP tiles.  D-068, amended 2026-10-01.

The three changes the spike named: tiles named by the north-west corner,
their own unit and list, and contours rasterised at 10,812 pixels so the
1/3-arc-second detail is kept. A change of source rebuilds through the
record. Synthetic tiles near 0/0; fakes stand in for GDAL, except one real
run on a synthetic Float32 tile.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from fake_tools import install_fakes
from hammunition.backends import Action, Command
from hammunition.backends.dem import DemResolution, RegionTiles
from hammunition.backends.gdal_dem import (
    PIXELS,
    RECORD,
    GdalDemConverter,
    contour_argv,
    rasterize_argv,
    render_record,
)
from hammunition.backends.staging import Staging
from hammunition.backends.terrain import contour_bytes, contour_scratch
from test_gdal_dem import FAKES, NOT_ROOT, _block, manifest

C = "Copernicus_DSM_COG_10_N00_00_E000_00_DEM"
T = "USGS_13_n01e000"
COPERNICUS = DemResolution(regions=(RegionTiles("atlantis/oceania", "atlantis-oceania", (C,), 0),))
THREEDEP = DemResolution(regions=(RegionTiles("atlantis/oceania", "atlantis-oceania", (T,), 0),))


def _data(prefix: Path, unit: str) -> Path:
    return prefix / "share" / "hammunition" / "data" / unit


def _converter(tmp_path: Path, resolution: DemResolution, **kw: Any) -> GdalDemConverter:
    return GdalDemConverter(
        prefix=tmp_path,
        resolution=resolution,
        staging=Staging(tmp_path / "staging", euid=NOT_ROOT),
        **kw,
    )


def _three(tmp_path: Path) -> GdalDemConverter:
    return _converter(tmp_path, THREEDEP, source_unit="dem-3dep", provider="usgs-3dep")


def _actions(steps: list[Action | Command]) -> list[Action]:
    assert all(isinstance(s, Action) for s in steps)
    return [s for s in steps if isinstance(s, Action)]


def _run(conv: GdalDemConverter) -> list[str]:
    m = manifest()
    return [s.perform() for s in _actions(conv.steps(m, _block(m)))]


def test_a_3dep_tile_is_rasterised_on_its_own_degree_at_10812_pixels(tmp_path: Path) -> None:
    argv = rasterize_argv(tmp_path / "c.gpkg", tmp_path / "c.tif", "USGS_13_n39w079")
    te = argv.index("-te")
    assert argv[te + 1 : te + 5] == ["-79", "38", "-78", "39"]
    ts = argv.index("-ts")
    assert argv[ts + 1 : ts + 3] == ["10812", "10812"]


def test_a_copernicus_tile_s_argv_is_unchanged() -> None:
    argv = rasterize_argv(Path("/w/c.gpkg"), Path("/w/c.tif"), C)
    ts = argv.index("-ts")
    assert argv[ts + 1 : ts + 3] == [str(PIXELS), str(PIXELS)] == ["7200", "7200"]


def test_the_3dep_estimates_are_their_own() -> None:
    assert contour_bytes("usgs-3dep") > contour_bytes("copernicus-glo30")
    assert contour_scratch("usgs-3dep") > contour_scratch("copernicus-glo30")


def test_the_record_names_3dep_and_leaves_copernicus_byte_identical() -> None:
    assert render_record([C]) == f"{C}\nconverter: gdal-dem 1\n"
    assert render_record([T], "usgs-3dep") == f"{T}\nelevation: usgs-3dep\nconverter: gdal-dem 1\n"


def test_with_3dep_chosen_the_tiles_are_read_from_dem_3dep(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fakes(monkeypatch, tmp_path / "bin", FAKES)
    tiles = _data(tmp_path, "dem-3dep")
    tiles.mkdir(parents=True)
    (tiles / f"{T}.tif").write_bytes(b"elevation")
    conv = _three(tmp_path)
    m = manifest()
    steps = _actions(conv.steps(m, _block(m)))
    assert any(str(tiles / f"{T}.tif") in s.description for s in steps)
    assert any("10812" in s.description for s in steps)
    outcomes = [s.perform() for s in steps]
    assert conv.ledger.failed == {}, outcomes
    out = _data(tmp_path, "dem-qmapshack")
    assert (out / "contours" / "tiles" / f"{T}.tif").is_file()
    assert (out / RECORD).read_text() == render_record([T], "usgs-3dep")
    assert conv.current(m)


def test_switching_back_to_copernicus_redraws_and_removes_the_3dep_contours(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fakes(monkeypatch, tmp_path / "bin", FAKES)
    for unit, name in (("dem-3dep", T), ("dem-copernicus", C)):
        (_data(tmp_path, unit)).mkdir(parents=True)
        (_data(tmp_path, unit) / f"{name}.tif").write_bytes(b"elevation")
    _run(_three(tmp_path))
    back = _converter(tmp_path, COPERNICUS)
    m = manifest()
    assert not back.current(m)
    assert back.pending(m) == [C]
    _run(back)
    out = _data(tmp_path, "dem-qmapshack")
    assert not (out / "contours" / "tiles" / f"{T}.tif").exists()
    assert (out / "contours" / "tiles" / f"{C}.tif").is_file()
    assert (out / RECORD).read_text() == render_record([C])


@pytest.mark.skipif(
    shutil.which("gdal_contour") is None or shutil.which("gdal_translate") is None,
    reason="gdal-bin is not installed on this machine; the fakes stand in for it",
)
def test_real_gdal_draws_contours_on_a_north_west_named_tile(tmp_path: Path) -> None:
    """A synthetic Float32 tile on the square (38, -79), named n39w079 as
    3DEP names it: the contours land on that square, at 10,812 pixels."""
    asc = tmp_path / "t.asc"
    rows = "\n".join(" ".join(str(100 + 10 * (r + c)) for c in range(20)) for r in range(20))
    asc.write_text(f"ncols 20\nnrows 20\nxllcorner -79\nyllcorner 38\ncellsize 0.05\n{rows}\n")
    tile = tmp_path / "USGS_13_n39w079.tif"
    subprocess.run(
        ["gdal_translate", "-q", "-ot", "Float32", "-a_srs", "EPSG:4269", str(asc), str(tile)],
        check=True,
    )
    gpkg, out = tmp_path / "c.gpkg", tmp_path / "c.tif"
    subprocess.run(contour_argv(tile, gpkg), check=True)
    subprocess.run(rasterize_argv(gpkg, out, "USGS_13_n39w079"), check=True)
    info = json.loads(
        subprocess.run(
            ["gdalinfo", "-json", str(out)], check=True, capture_output=True, text=True
        ).stdout
    )
    assert info["size"] == [10812, 10812]
    corners = info["cornerCoordinates"]
    assert corners["upperLeft"] == pytest.approx([-79.0, 39.0])
    assert corners["lowerRight"] == pytest.approx([-78.0, 38.0])


def test_with_no_tile_left_both_rasters_and_the_record_are_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Final review I2: 3DEP chosen and every region outside the US -- the
    Copernicus contours go, and a VRT left behind would name them."""
    install_fakes(monkeypatch, tmp_path / "bin", FAKES)
    _data(tmp_path, "dem-copernicus").mkdir(parents=True)
    (_data(tmp_path, "dem-copernicus") / f"{C}.tif").write_bytes(b"elevation")
    _run(_converter(tmp_path, COPERNICUS))
    out = _data(tmp_path, "dem-qmapshack")
    assert (out / "dem" / "dem.vrt").is_file() and (out / "contours" / "contours.vrt").is_file()
    empty = DemResolution(regions=(RegionTiles("atlantis/lemuria", "atlantis-lemuria", (), 4),))
    outcomes = _run(_converter(tmp_path, empty, source_unit="dem-3dep", provider="usgs-3dep"))
    assert not (out / "contours" / "tiles" / f"{C}.tif").exists()
    assert not (out / "dem" / "dem.vrt").exists(), outcomes
    assert not (out / "contours" / "contours.vrt").exists()
    assert not (out / RECORD).exists()


def test_a_failed_rebuild_removes_a_vrt_naming_files_that_are_gone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Final review I2: switching back to Copernicus removed the 3DEP tiles
    before gdal-dem rebuilt; if the rebuild fails, dem.vrt must not keep
    naming them."""
    install_fakes(monkeypatch, tmp_path / "bin", {**FAKES, "gdalbuildvrt": "exit 1"})
    _data(tmp_path, "dem-copernicus").mkdir(parents=True)
    (_data(tmp_path, "dem-copernicus") / f"{C}.tif").write_bytes(b"elevation")
    out = _data(tmp_path, "dem-qmapshack")
    (out / "dem").mkdir(parents=True)
    gone = _data(tmp_path, "dem-3dep") / f"{T}.tif"
    (out / "dem" / "dem.vrt").write_text(
        f'<VRTDataset><VRTRasterBand><SimpleSource><SourceFilename relativeToVRT="0">'
        f"{gone}</SourceFilename></SimpleSource></VRTRasterBand></VRTDataset>"
    )
    conv = _converter(tmp_path, COPERNICUS)
    outcomes = _run(conv)
    assert conv.ledger.failed, outcomes
    assert not (out / "dem" / "dem.vrt").exists()
