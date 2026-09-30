# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The ``ustopo-mosaic`` converter: US Topo sheets warped and mosaicked for
QMapShack.  D-068.

Synthetic sheets near 0/0; fakes stand in for GDAL's programs, and one test
runs the real ones on a tiny synthetic GeoTIFF where gdal-bin is installed.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from fake_tools import calls, install_fakes
from hammunition.backends import Action, Command
from hammunition.backends.staging import Staging
from hammunition.backends.terrain import TerrainLedger
from hammunition.backends.topo import RegionQuads, TopoResolution, quad_key
from hammunition.backends.topo_mosaic import (
    CONVERTER,
    RECORD,
    VRT,
    UstopoMosaicConverter,
    overviews_argv,
    warp_argv,
)
from hammunition.manifest.schema import DerivedDataInstall, PackageManifest
from hammunition.ustopo import Quad

NOT_ROOT = 1000
MD5 = "0123456789abcdef0123456789abcdef"
ALPHA = Quad(0.0, 0.0, 0.125, 0.125, 9_000_000, MD5, "ZZ/ZZ_Alpha_20240101")
BETA = Quad(-0.125, -0.125, 0.0, 0.0, 8_000_000, MD5, "ZZ/ZZ_Beta_20240101")
RESOLUTION = TopoResolution(
    regions=(RegionQuads("atlantis/oceania", "atlantis-oceania", (ALPHA.path, BETA.path)),),
    fetch=(ALPHA, BETA),
)

FAKES = {
    "gdalwarp": 'for last; do :; done; printf warped > "$last"',
    "gdaladdo": 'printf +overviews >> "${10}"',
    "gdalbuildvrt": 'printf vrt > "$2"',
}


def manifest() -> PackageManifest:
    return PackageManifest.model_validate(
        {
            "name": "ustopo-qmapshack",
            "version": "station",
            "summary": "US Topo for a test",
            "categories": ["navigation-maps"],
            "depends": ["usgs-ustopo", "gdal-bin"],
            "install": [
                {
                    "install": {
                        "method": "derived",
                        "converter": "ustopo-mosaic",
                        "source": "usgs-ustopo",
                        "licence": "Public domain (USGS)",
                        "licence_url": "https://www.usgs.gov/",
                    }
                }
            ],
            "update": {"probe": {"method": "none"}},
            "documentation": {
                "what_it_does": "US Topo for a test, nothing more.",
                "why_you_want_it": "Because the test suite needs a manifest.",
                "upstream_url": "https://gdal.org/",
            },
        }
    )


def _block(m: PackageManifest) -> DerivedDataInstall:
    block = m.install[0].install
    assert isinstance(block, DerivedDataInstall)
    return block


def _data(prefix: Path, unit: str) -> Path:
    return prefix / "share" / "hammunition" / "data" / unit


def _install_sheets(tmp_path: Path, *quads: Quad) -> Path:
    out = _data(tmp_path, "usgs-ustopo")
    out.mkdir(parents=True, exist_ok=True)
    for quad in quads:
        (out / f"{quad.name}.tif").write_bytes(b"sheet")
    return out


def _actions(steps: list[Action | Command]) -> list[Action]:
    assert all(isinstance(s, Action) for s in steps)
    return [s for s in steps if isinstance(s, Action)]


def _converter(tmp_path: Path, **kw: Any) -> UstopoMosaicConverter:
    kw.setdefault("resolution", RESOLUTION)
    return UstopoMosaicConverter(
        prefix=tmp_path, staging=Staging(tmp_path / "staging", euid=NOT_ROOT), **kw
    )


def _run(conv: UstopoMosaicConverter) -> list[str]:
    m = manifest()
    return [s.perform() for s in _actions(conv.steps(m, _block(m)))]


def _work(tmp_path: Path) -> Path:
    return tmp_path / "staging" / "ustopo.work"


def test_each_sheet_is_warped_cropped_to_its_box_and_one_vrt_built(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = install_fakes(monkeypatch, tmp_path / "bin", FAKES)
    source = _install_sheets(tmp_path, ALPHA, BETA)
    conv = _converter(tmp_path)
    _run(conv)
    assert conv.ledger.failed == {}
    work = _work(tmp_path)
    logged = calls(log)
    assert {where for where, _ in logged} == {str(work)}, "every run in the one working directory"
    commands = [c for _, c in logged]
    assert commands[0] == (
        f"gdalwarp -q -overwrite -t_srs EPSG:3857 -te_srs EPSG:4269 -te 0 0 0.125 0.125 "
        f"-r bilinear -co COMPRESS=JPEG -co PHOTOMETRIC=YCBCR -co TILED=YES "
        f"{source / 'ZZ_Alpha_20240101.tif'} {work / 'ZZ_Alpha_20240101.tif'}"
    )
    assert commands[1] == (
        f"gdaladdo -q -r average --config COMPRESS_OVERVIEW JPEG --config "
        f"PHOTOMETRIC_OVERVIEW YCBCR {work / 'ZZ_Alpha_20240101.tif'} 2 4 8 16"
    )
    assert "-te -0.125 -0.125 0 0" in commands[2], "a sheet south-west of 0/0 keeps its own box"
    out = _data(tmp_path, "ustopo-qmapshack")
    quads = out / "quads"
    assert commands[4] == (
        f"gdalbuildvrt -q {work / VRT} "
        f"{quads / 'ZZ_Alpha_20240101.tif'} {quads / 'ZZ_Beta_20240101.tif'}"
    )
    assert (quads / "ZZ_Alpha_20240101.tif").read_text() == "warped+overviews"
    assert (quads / "ZZ_Alpha_20240101.tif.source").read_text() == (
        f"ZZ_Alpha_20240101\nconverter: {CONVERTER}\n"
    )
    assert (out / VRT).read_text() == "vrt"
    assert (out / RECORD).read_text() == (
        f"ZZ_Alpha_20240101\nZZ_Beta_20240101\nconverter: {CONVERTER}\n"
    )
    assert list(work.iterdir()) == [], "the working directory is emptied"


def test_nothing_happens_when_every_sheet_and_the_vrt_are_current(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fakes(monkeypatch, tmp_path / "bin", FAKES)
    _install_sheets(tmp_path, ALPHA, BETA)
    conv = _converter(tmp_path)
    _run(conv)
    m = manifest()
    assert conv.pending(m) == []
    assert conv.current(m)
    assert conv.steps(m, _block(m)) == []


def test_a_sheet_whose_download_failed_is_skipped_and_the_rest_are_built(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fakes(monkeypatch, tmp_path / "bin", FAKES)
    _install_sheets(tmp_path, BETA)
    ledger = TerrainLedger()
    ledger.fail(quad_key(ALPHA.name), "did not verify")
    conv = _converter(tmp_path, ledger=ledger)
    outcomes = _run(conv)
    assert f"skipped: US Topo quad {ALPHA.name} did not install" in outcomes
    out = _data(tmp_path, "ustopo-qmapshack")
    assert (out / "quads" / "ZZ_Beta_20240101.tif").is_file()
    assert (out / VRT).is_file()
    assert not (out / RECORD).exists(), "not recorded: a sheet is missing, built next run"


def test_a_warp_that_writes_nothing_fails_that_sheet_by_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fakes(monkeypatch, tmp_path / "bin", {**FAKES, "gdalwarp": "exit 0"})
    _install_sheets(tmp_path, ALPHA, BETA)
    conv = _converter(tmp_path)
    _run(conv)
    assert set(conv.ledger.failed) == {
        f"ustopo-mosaic:{ALPHA.name}",
        f"ustopo-mosaic:{BETA.name}",
    }
    assert "gdalwarp wrote no warped quad" in conv.ledger.failed[f"ustopo-mosaic:{ALPHA.name}"]
    assert not (_data(tmp_path, "ustopo-qmapshack") / VRT).exists()


def test_an_overview_failure_fails_that_sheet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fakes(monkeypatch, tmp_path / "bin", {**FAKES, "gdaladdo": "exit 3"})
    _install_sheets(tmp_path, ALPHA)
    conv = _converter(tmp_path, resolution=TopoResolution(fetch=(ALPHA,)))
    _run(conv)
    assert (
        "gdaladdo did not add overviews (exit 3)"
        in conv.ledger.failed[f"ustopo-mosaic:{ALPHA.name}"]
    )


def test_a_sheet_no_region_needs_loses_its_warped_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fakes(monkeypatch, tmp_path / "bin", FAKES)
    _install_sheets(tmp_path, ALPHA, BETA)
    _run(_converter(tmp_path))
    conv = _converter(tmp_path, resolution=TopoResolution(current=(ALPHA,)))
    m = manifest()
    steps = _actions(conv.steps(m, _block(m)))
    removed = [Path(s.detail).name for s in steps if s.kind == "remove-data"]
    assert removed == ["ZZ_Beta_20240101.tif"]
    for step in steps:
        step.perform()
    out = _data(tmp_path, "ustopo-qmapshack")
    assert not (out / "quads" / "ZZ_Beta_20240101.tif").exists()
    assert (out / RECORD).read_text() == f"ZZ_Alpha_20240101\nconverter: {CONVERTER}\n"


def test_with_no_sheet_needed_the_vrt_goes_with_the_sheets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fakes(monkeypatch, tmp_path / "bin", FAKES)
    _install_sheets(tmp_path, ALPHA, BETA)
    _run(_converter(tmp_path))
    conv = _converter(tmp_path, resolution=TopoResolution())
    outcomes = _run(conv)
    out = _data(tmp_path, "ustopo-qmapshack")
    assert not (out / VRT).exists() and not (out / RECORD).exists()
    assert not list((out / "quads").glob("*.tif"))
    assert any("removed" in o and VRT in o for o in outcomes)
    assert (
        _converter(tmp_path, resolution=TopoResolution()).steps(manifest(), _block(manifest()))
        == []
    )


def test_sheets_from_another_converter_version_are_warped_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fakes(monkeypatch, tmp_path / "bin", FAKES)
    _install_sheets(tmp_path, ALPHA, BETA)
    _run(_converter(tmp_path))
    sidecar = _data(tmp_path, "ustopo-qmapshack") / "quads" / "ZZ_Alpha_20240101.tif.source"
    sidecar.write_text("ZZ_Alpha_20240101\nconverter: ustopo-mosaic 0\n")
    conv = _converter(tmp_path)
    assert [q.name for q in conv.pending(manifest())] == ["ZZ_Alpha_20240101"]


def test_the_warp_step_states_its_command_and_measured_size(tmp_path: Path) -> None:
    conv = _converter(tmp_path)
    m = manifest()
    first = _actions(conv.steps(m, _block(m)))[0]
    assert first.kind == "convert"
    assert "gdalwarp -q -overwrite -t_srs EPSG:3857" in first.description
    assert "9.0 MB" in first.description and "measured on one quad" in first.description


def test_the_argv_builders_are_fixed(tmp_path: Path) -> None:
    off_grid = Quad(69.0, -150.3, 69.125, -150.0, 1, MD5, "AK/AK_Chandler_Lake_D-1_NE_20200101")
    argv = warp_argv(off_grid, tmp_path / "in.tif", tmp_path / "out.tif")
    assert argv[argv.index("-te") + 1 : argv.index("-te") + 5] == [
        "-150.3",
        "69",
        "-150",
        "69.125",
    ]
    assert overviews_argv(tmp_path / "o.tif")[-5:] == [str(tmp_path / "o.tif"), "2", "4", "8", "16"]


@pytest.mark.skipif(
    shutil.which("gdalwarp") is None or shutil.which("gdal_translate") is None,
    reason="gdal-bin is not installed on this machine; the fakes stand in for it",
)
def test_real_gdal_crops_a_transverse_mercator_page_to_its_box(tmp_path: Path) -> None:
    """A synthetic 'page' in its own Transverse Mercator, larger than the
    sheet's box as a collar is; the warp crops it to the box in EPSG:3857."""
    asc = tmp_path / "page.asc"
    rows = "\n".join(" ".join(["100"] * 40) for _ in range(40))
    # 40 x 40 cells of 500 m: 20 km a side, centred on 0.0625/0.0625.
    asc.write_text(f"ncols 40\nnrows 40\nxllcorner -10000\nyllcorner -3100\ncellsize 500\n{rows}\n")
    page = tmp_path / "page.tif"
    subprocess.run(
        [
            "gdal_translate",
            "-q",
            "-ot",
            "Byte",
            "-b",
            "1",
            "-b",
            "1",
            "-b",
            "1",
            "-a_srs",
            "+proj=tmerc +lat_0=0 +lon_0=0.0625 +k=0.9999 +x_0=0 +y_0=0 +datum=NAD83",
            str(asc),
            str(page),
        ],
        check=True,
    )
    out = tmp_path / "warped.tif"
    subprocess.run(warp_argv(ALPHA, page, out), check=True)
    subprocess.run(overviews_argv(out), check=True)
    info = json.loads(
        subprocess.run(
            ["gdalinfo", "-json", str(out)], check=True, capture_output=True, text=True
        ).stdout
    )
    assert '"EPSG",3857' in info["coordinateSystem"]["wkt"].replace(" ", "")
    lon = [c[0] for c in info["wgs84Extent"]["coordinates"][0]]
    lat = [c[1] for c in info["wgs84Extent"]["coordinates"][0]]
    assert min(lon) == pytest.approx(0.0, abs=1e-4) and max(lon) == pytest.approx(0.125, abs=1e-4)
    assert min(lat) == pytest.approx(0.0, abs=1e-4) and max(lat) == pytest.approx(0.125, abs=1e-4)
    assert info["bands"][0]["overviews"], "overviews were added"
