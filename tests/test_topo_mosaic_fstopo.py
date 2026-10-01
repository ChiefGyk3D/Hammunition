# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The FSTopo half of ``ustopo-mosaic``: each sheet expanded to RGB, tiled
with overviews, and one ``FSTopo.vrt`` beside ``ustopo.vrt``.  D-068,
amended 2026-10-01.

Measured offline on 2026-10-01: an FSTopo sheet is paletted, stripped and
has no overviews, and ``gdalbuildvrt`` over sheets whose palettes differ
keeps the first palette for all of them. Fakes stand in for GDAL, and one
test runs the real programs on two synthetic paletted sheets.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from fake_tools import install_fakes
from hammunition.backends import Action, Command
from hammunition.backends.fstopo import FsTopoResolution, RegionSheets
from hammunition.backends.staging import Staging
from hammunition.backends.terrain import TerrainLedger
from hammunition.backends.topo import RegionQuads, TopoResolution
from hammunition.backends.topo_mosaic import (
    FSTOPO_CONVERTER,
    FSTOPO_RECORD,
    FSTOPO_VRT,
    VRT,
    UstopoMosaicConverter,
    buildvrt_argv,
    overviews_argv,
    translate_argv,
)
from hammunition.fstopo import FsQuadFile, parse_row
from hammunition.manifest.schema import DerivedDataInstall, PackageManifest
from hammunition.ustopo import Quad

NOT_ROOT = 1000
MD5 = "0123456789abcdef0123456789abcdef"
ALPHA = parse_row("0 0 0.125 0.125 1230000 11 ZZ Alpha")
BETA = parse_row("0 0.125 0.125 0.25 1230001 0 ZZ Beta")
SHEETS = FsTopoResolution(
    regions=(RegionSheets("atlantis/oceania", "atlantis-oceania", (ALPHA, BETA)),),
    fetch=(FsQuadFile(ALPHA, "u", 21_000_000, None), FsQuadFile(BETA, "v", 20_000_000, None)),
)
US = Quad(0.0, 0.0, 0.125, 0.125, 9_000_000, MD5, "ZZ/ZZ_Alpha_20240101")
USTOPO = TopoResolution(
    regions=(RegionQuads("atlantis/oceania", "atlantis-oceania", (US,)),), fetch=(US,)
)
FAKES = {
    "gdalwarp": 'for last; do :; done; printf warped > "$last"',
    "gdal_translate": 'for last; do :; done; printf rgb > "$last"',
    "gdaladdo": 'printf +overviews >> "${10}"',
    "gdalbuildvrt": 'printf vrt > "$2"',
}


def manifest(*, fstopo: bool = True) -> PackageManifest:
    block: dict[str, Any] = {
        "method": "derived",
        "converter": "ustopo-mosaic",
        "source": "usgs-ustopo",
        "licence": "Public domain (USGS)",
        "licence_url": "https://www.usgs.gov/",
    }
    depends = ["usgs-ustopo", "gdal-bin"]
    if fstopo:
        block["fstopo"] = "usfs-fstopo"
        depends.append("usfs-fstopo")
    return PackageManifest.model_validate(
        {
            "name": "ustopo-qmapshack",
            "version": "station",
            "summary": "Official topo for a test",
            "categories": ["navigation-maps"],
            "depends": depends,
            "install": [{"install": block}],
            "update": {"probe": {"method": "none"}},
            "documentation": {
                "what_it_does": "Official topo for a test, nothing more.",
                "why_you_want_it": "Because the test suite needs a manifest.",
                "upstream_url": "https://gdal.org/",
            },
        }
    )


def _data(prefix: Path, unit: str) -> Path:
    return prefix / "share" / "hammunition" / "data" / unit


def _install(tmp_path: Path, unit: str, *names: str) -> None:
    out = _data(tmp_path, unit)
    out.mkdir(parents=True, exist_ok=True)
    for name in names:
        (out / f"{name}.tif").write_bytes(b"II*\x00sheet")


def _converter(tmp_path: Path, **kw: Any) -> UstopoMosaicConverter:
    kw.setdefault("resolution", TopoResolution())
    kw.setdefault("fstopo", SHEETS)
    return UstopoMosaicConverter(
        prefix=tmp_path, staging=Staging(tmp_path / "staging", euid=NOT_ROOT), **kw
    )


def _steps(conv: UstopoMosaicConverter, m: PackageManifest | None = None) -> list[Action]:
    m = m or manifest()
    block = m.install[0].install
    assert isinstance(block, DerivedDataInstall)
    steps: list[Action | Command] = conv.steps(m, block)
    assert all(isinstance(s, Action) for s in steps)
    return [s for s in steps if isinstance(s, Action)]


def test_the_translate_argv_expands_the_palette_into_tiled_jpeg() -> None:
    assert translate_argv(Path("/d/a.tif"), Path("/w/a.tif")) == [
        "gdal_translate",
        "-q",
        "-expand",
        "rgb",
        "-co",
        "TILED=YES",
        "-co",
        "COMPRESS=JPEG",
        "-co",
        "PHOTOMETRIC=YCBCR",
        "/d/a.tif",
        "/w/a.tif",
    ]


def test_each_sheet_is_converted_and_one_fstopo_vrt_is_built(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fakes(monkeypatch, tmp_path / "bin", FAKES)
    _install(tmp_path, "usfs-fstopo", ALPHA.name, BETA.name)
    conv = _converter(tmp_path)
    steps = _steps(conv)
    assert sum(1 for s in steps if s.kind == "convert") == 2
    assert any("gdal_translate -q -expand rgb" in s.description for s in steps)
    outcomes = [s.perform() for s in steps]
    assert conv.ledger.failed == {}, outcomes
    out = _data(tmp_path, "ustopo-qmapshack")
    for quad in (ALPHA, BETA):
        assert (out / "fstopo" / f"{quad.name}.tif").read_bytes() == b"rgb+overviews"
        assert (
            (out / "fstopo" / f"{quad.name}.tif.source")
            .read_text()
            .endswith(f"converter: {FSTOPO_CONVERTER}\n")
        )
    assert (out / FSTOPO_VRT).read_text() == "vrt"
    assert (out / FSTOPO_RECORD).read_text() == (
        f"{ALPHA.name}\n{BETA.name}\nconverter: {FSTOPO_CONVERTER}\n"
    )
    assert not (out / VRT).exists(), "no US Topo sheet, no ustopo.vrt"
    assert _steps(conv) == [], "nothing to do the second time"
    assert conv.fstopo_pending(manifest()) == []


def test_a_region_with_us_topo_and_no_fstopo_builds_no_fstopo_vrt_and_removes_an_old_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fakes(monkeypatch, tmp_path / "bin", FAKES)
    _install(tmp_path, "usgs-ustopo", US.name)
    out = _data(tmp_path, "ustopo-qmapshack")
    out.mkdir(parents=True)
    (out / FSTOPO_VRT).write_text("old")
    (out / FSTOPO_RECORD).write_text("old\n")
    empty = FsTopoResolution(regions=(RegionSheets("atlantis/delaware", "atlantis-delaware", ()),))
    conv = _converter(tmp_path, resolution=USTOPO, fstopo=empty)
    outcomes = [s.perform() for s in _steps(conv)]
    assert conv.ledger.failed == {}, outcomes
    assert (out / VRT).read_text() == "vrt"
    assert not (out / FSTOPO_VRT).exists() and not (out / FSTOPO_RECORD).exists()


def test_without_the_fstopo_input_no_fstopo_step_is_planned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fakes(monkeypatch, tmp_path / "bin", FAKES)
    _install(tmp_path, "usfs-fstopo", ALPHA.name)
    assert _steps(_converter(tmp_path), manifest(fstopo=False)) == []


def test_a_sheet_that_did_not_install_is_skipped_and_the_vrt_names_the_rest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fakes(monkeypatch, tmp_path / "bin", FAKES)
    _install(tmp_path, "usfs-fstopo", BETA.name)
    ledger = TerrainLedger()
    ledger.fail(f"quad {ALPHA.name}", "did not arrive")
    conv = _converter(tmp_path, ledger=ledger)
    outcomes = [s.perform() for s in _steps(conv)]
    assert any(o.startswith("skipped") and ALPHA.name in o for o in outcomes)
    out = _data(tmp_path, "ustopo-qmapshack")
    assert (out / FSTOPO_VRT).is_file()
    assert not (out / FSTOPO_RECORD).exists(), "not recorded as complete"


def _paletted(path: Path, west: float, green: int) -> None:
    """A 20 x 20 paletted GeoTIFF in EPSG:4269 whose palette maps every
    index to (index, green, 255 - index)."""
    asc = path.with_suffix(".asc")
    rows = "\n".join(" ".join(["7"] * 20) for _ in range(20))
    asc.write_text(f"ncols 20\nnrows 20\nxllcorner {west}\nyllcorner 0\ncellsize 0.00625\n{rows}\n")
    entries = "".join(f'<Entry c1="{i}" c2="{green}" c3="{255 - i}" c4="255"/>' for i in range(256))
    vrt = path.with_suffix(".src.vrt")
    vrt.write_text(
        f'<VRTDataset rasterXSize="20" rasterYSize="20"><SRS>EPSG:4269</SRS>'
        f"<GeoTransform>{west}, 0.00625, 0, 0.125, 0, -0.00625</GeoTransform>"
        f'<VRTRasterBand dataType="Byte" band="1"><ColorInterp>Palette</ColorInterp>'
        f"<ColorTable>{entries}</ColorTable><SimpleSource>"
        f'<SourceFilename relativeToVRT="1">{asc.name}</SourceFilename>'
        f"<SourceBand>1</SourceBand></SimpleSource></VRTRasterBand></VRTDataset>"
    )
    subprocess.run(["gdal_translate", "-q", str(vrt), str(path)], check=True)


def _pixel(dataset: Path, lon: float, lat: float) -> list[int]:
    out = subprocess.run(
        ["gdallocationinfo", "-valonly", "-wgs84", str(dataset), str(lon), str(lat)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return [int(v) for v in out.split()]


@pytest.mark.skipif(
    any(shutil.which(t) is None for t in ("gdal_translate", "gdaladdo", "gdallocationinfo")),
    reason="gdal-bin is not installed on this machine; the fakes stand in for it",
)
def test_real_gdal_keeps_each_sheet_s_own_palette_in_the_mosaic(tmp_path: Path) -> None:
    a, b = tmp_path / "a.tif", tmp_path / "b.tif"
    _paletted(a, 0.0, 10)
    _paletted(b, 0.125, 200)
    converted = []
    for sheet in (a, b):
        out = tmp_path / f"rgb-{sheet.name}"
        subprocess.run(translate_argv(sheet, out), check=True)
        subprocess.run(overviews_argv(out), check=True)
        converted.append(out)
    vrt = tmp_path / "FSTopo.vrt"
    subprocess.run(buildvrt_argv(vrt, converted), check=True)
    # JPEG is lossy: the green channel is near each sheet's own, not exact.
    assert abs(_pixel(vrt, 0.06, 0.06)[1] - 10) < 12
    assert abs(_pixel(vrt, 0.19, 0.06)[1] - 200) < 12
