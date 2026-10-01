# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The ``splat-sdf`` converter: SPLAT's terrain from the elevation tiles.
D-061, amended 2026-10-02.

Synthetic tiles near 0/0 and fakes for GDAL, SPLAT's tools and bzip2; one
test runs the real programs over a synthetic GeoTIFF where they are
installed. No network, no maintainer region.
"""

from __future__ import annotations

import bz2
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from fake_tools import calls, install_fakes
from hammunition.backends import Action, Command
from hammunition.backends.dem import DemResolution, RegionTiles
from hammunition.backends.splat_sdf import (
    CONVERTER,
    SplatSdfConverter,
    convert_argv,
    hgt_name,
    ring,
    sdf_name,
    signal_server_name,
    warp_argv,
)
from hammunition.backends.staging import Staging
from hammunition.backends.terrain import TerrainLedger, tile_key
from hammunition.manifest.schema import DerivedDataInstall, PackageManifest

NOT_ROOT = 1000

A = "Copernicus_DSM_COG_10_N00_00_E000_00_DEM"
B = "Copernicus_DSM_COG_10_N00_00_W001_00_DEM"
FAR = "Copernicus_DSM_COG_10_N10_00_E010_00_DEM"


def _resolution(*tiles: str) -> DemResolution:
    return DemResolution(regions=(RegionTiles("atlantis/oceania", "atlantis-oceania", tiles, 0),))


def _fakes(*tiles: str) -> dict[str, str]:
    """Fakes writing what each real tool writes, under the measured names."""
    cases_hd = "".join(
        f'  {hgt_name(t)}) printf "sdf-hd {t}" > "{sdf_name(t, hd=True)[:-4]}";;\n' for t in tiles
    )
    cases_sd = "".join(
        f'  {hgt_name(t)}) printf "sdf {t}" > "{sdf_name(t, hd=False)[:-4]}";;\n' for t in tiles
    )
    return {
        "gdalbuildvrt": 'printf vrt > "$4"',
        "gdalwarp": 'for last; do :; done; printf hgt > "$last"',
        "srtm2sdf-hd": f'case "$5" in\n{cases_hd}esac',
        "srtm2sdf": f'case "$5" in\n{cases_sd}esac',
        "bzip2": 'cat "$3" > "$3.bz2" && rm -- "$3"',
    }


def manifest() -> PackageManifest:
    return PackageManifest.model_validate(
        {
            "name": "splat-sdf",
            "version": "station",
            "summary": "SPLAT terrain for a test",
            "categories": ["propagation"],
            "depends": ["dem-copernicus", "splat"],
            "install": [
                {
                    "install": {
                        "method": "derived",
                        "converter": "splat-sdf",
                        "source": "dem-copernicus",
                        "licence": "Copernicus DEM licence",
                        "licence_url": "https://spacedata.copernicus.eu/",
                    }
                }
            ],
            "update": {"probe": {"method": "none"}},
            "documentation": {
                "what_it_does": "SPLAT terrain for a test, nothing more.",
                "why_you_want_it": "Because the test suite needs a manifest.",
                "upstream_url": "https://www.qsl.net/kd2bd/splat.html",
            },
        }
    )


def _block(m: PackageManifest) -> DerivedDataInstall:
    block = m.install[0].install
    assert isinstance(block, DerivedDataInstall)
    return block


def _data(prefix: Path, unit: str) -> Path:
    return prefix / "share" / "hammunition" / "data" / unit


def _install_tiles(tmp_path: Path, *names: str, unit: str = "dem-copernicus") -> Path:
    out = _data(tmp_path, unit)
    out.mkdir(parents=True, exist_ok=True)
    for name in names:
        (out / f"{name}.tif").write_bytes(b"elevation")
    return out


def _converter(tmp_path: Path, *tiles: str, **kw: Any) -> SplatSdfConverter:
    return SplatSdfConverter(
        prefix=tmp_path,
        resolution=_resolution(*tiles),
        staging=Staging(tmp_path / "staging", euid=NOT_ROOT),
        **kw,
    )


def _actions(steps: list[Action | Command]) -> list[Action]:
    assert all(isinstance(s, Action) for s in steps)
    return [s for s in steps if isinstance(s, Action)]


def _run(conv: SplatSdfConverter) -> list[str]:
    m = manifest()
    return [s.perform() for s in _actions(conv.steps(m, _block(m)))]


# -- names, measured from srtm2sdf on 2026-10-01 ------------------------------


@pytest.mark.parametrize(
    ("square", "name"),
    [
        ("N00_00_E000_00", "0:1:359:0"),
        ("N00_00_E179_00", "0:1:180:181"),
        ("N00_00_W001_00", "0:1:0:1"),
        ("N00_00_W180_00", "0:1:179:180"),
        ("N10_00_E010_00", "10:11:349:350"),
        ("N36_00_W117_00", "36:37:116:117"),
        ("N65_00_W150_00", "65:66:149:150"),
        ("S01_00_W001_00", "-1:0:0:1"),
        ("S34_00_E151_00", "-34:-33:208:209"),
    ],
)
def test_names_are_the_ones_srtm2sdf_writes(square: str, name: str) -> None:
    tile = f"Copernicus_DSM_COG_10_{square}_DEM"
    assert sdf_name(tile, hd=True) == f"{name}-hd.sdf.bz2"
    assert sdf_name(tile, hd=False) == f"{name}.sdf.bz2"


def test_signal_server_names_use_underscores_and_never_wrap() -> None:
    assert signal_server_name("Copernicus_DSM_COG_10_N36_00_W117_00_DEM", hd=True) == (
        "36_37_116_117-hd.sdf.bz2"
    )
    # Its LoadTopoData asks for min_west + 1; SPLAT's file says 0.
    assert signal_server_name(A, hd=False) == "0_1_359_360.sdf.bz2"


def test_a_3dep_tile_names_the_same_square() -> None:
    assert sdf_name("USGS_13_n37w117", hd=True) == "36:37:116:117-hd.sdf.bz2"
    assert hgt_name("USGS_13_n37w117") == "N36W117.hgt"


def test_ring_is_the_eight_squares_around() -> None:
    assert ring(A, [A, B, FAR]) == (B,)
    assert ring(FAR, [A, B, FAR]) == ()


# -- argv ---------------------------------------------------------------------


def test_the_converter_keeps_elevations_below_sea_level() -> None:
    """srtm2sdf's -n defaults to 0 and replaces everything below it
    (measured: -50 m came out 104 m); -d /dev/null stops it reading
    ~/.splat_path, which would be this converter's own output."""
    assert convert_argv("N36W117.hgt", hd=True) == [
        "srtm2sdf-hd",
        "-d",
        "/dev/null",
        "-n",
        "-32767",
        "N36W117.hgt",
    ]
    assert convert_argv("N36W117.hgt", hd=False)[0] == "srtm2sdf"


def test_the_warp_is_centred_on_whole_samples_and_marks_voids() -> None:
    argv = warp_argv(Path("w.vrt"), Path("N00E000.hgt"), A, 3601)
    te = argv[argv.index("-te") + 1 : argv.index("-te") + 5]
    assert te == ["-0.000138889", "-0.000138889", "1.000138889", "1.000138889"]
    assert argv[argv.index("-ts") + 1 : argv.index("-ts") + 3] == ["3601", "3601"]
    assert argv[argv.index("-dstnodata") + 1] == "-32768"
    assert argv[argv.index("-r") + 1] == "average"
    assert argv[argv.index("-of") + 1] == "SRTMHGT"
    standard = warp_argv(Path("w.vrt"), Path("x.hgt"), A, 1201)
    assert standard[standard.index("-te") + 1] == "-0.000416667"


# -- the run ------------------------------------------------------------------


def test_each_tile_gets_both_files_sidecars_and_signal_server_links(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = install_fakes(monkeypatch, tmp_path / "bin", _fakes(A, B))
    source = _install_tiles(tmp_path, A, B)
    conv = _converter(tmp_path, A, B)
    outcomes = _run(conv)
    assert conv.ledger.failed == {}, outcomes
    work = tmp_path / "staging" / "splat.work"
    logged = calls(log)
    assert {where for where, _ in logged} == {str(work)}, "one working directory"
    commands = [c for _, c in logged]
    # A's window holds B, its neighbour to the west.
    assert commands[0] == (
        f"gdalbuildvrt -q -resolution highest {work / 'window.vrt'} "
        f"{source / f'{A}.tif'} {source / f'{B}.tif'}"
    )
    assert commands[2] == "srtm2sdf-hd -d /dev/null -n -32767 N00E000.hgt"
    assert commands[3] == "bzip2 -9 -- 0:1:359:0-hd.sdf"
    assert commands[5] == "srtm2sdf -d /dev/null -n -32767 N00E000.hgt"
    out = _data(tmp_path, "splat-sdf")
    hd = out / "0:1:359:0-hd.sdf.bz2"
    assert hd.read_bytes() == f"sdf-hd {A}".encode()
    assert (out / "0:1:359:0.sdf.bz2").read_bytes() == f"sdf {A}".encode()
    sidecar = (out / "0:1:359:0-hd.sdf.bz2.source").read_text()
    assert sidecar == f"{A}\nwindow: {B}\nconverter: {CONVERTER}\n"
    link = out / "0_1_359_360-hd.sdf.bz2"
    assert link.is_symlink() and link.readlink() == Path(hd.name)
    assert (out / "0_1_0_1.sdf.bz2").resolve() == (out / "0:1:0:1.sdf.bz2").resolve()
    assert list(work.iterdir()) == [], "scratch emptied after the last tile"
    # Current: the next run has nothing to do.
    assert conv.current(manifest())
    assert conv.steps(manifest(), _block(manifest())) == []


def test_a_change_of_elevation_source_rebuilds_the_square(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fakes(monkeypatch, tmp_path / "bin", _fakes(FAR, "USGS_13_n11e010"))
    _install_tiles(tmp_path, FAR)
    _run(_converter(tmp_path, FAR))
    _install_tiles(tmp_path, "USGS_13_n11e010", unit="dem-3dep")
    three = _converter(tmp_path, "USGS_13_n11e010", source_unit="dem-3dep")
    assert three.pending(manifest()) == ["USGS_13_n11e010"]
    _run(three)
    out = _data(tmp_path, "splat-sdf")
    assert (out / "10:11:349:350-hd.sdf.bz2.source").read_text().startswith("USGS_13_n11e010\n")
    assert three.current(manifest())


def test_a_neighbour_gained_rebuilds_the_edge_it_supplies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fakes(monkeypatch, tmp_path / "bin", _fakes(A, B))
    _install_tiles(tmp_path, A)
    _run(_converter(tmp_path, A))
    _install_tiles(tmp_path, B)
    assert _converter(tmp_path, A, B).pending(manifest()) == [A, B]


def test_a_tool_that_exits_zero_and_writes_nothing_fails_the_tile_by_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fakes = _fakes(A)
    fakes["srtm2sdf-hd"] = "exit 0"
    install_fakes(monkeypatch, tmp_path / "bin", fakes)
    _install_tiles(tmp_path, A)
    conv = _converter(tmp_path, A)
    outcomes = _run(conv)
    assert "srtm2sdf-hd did not write 0:1:359:0-hd.sdf" in conv.ledger.failed[f"splat-sdf:{A}"]
    assert any(o.startswith("skipped") for o in outcomes)
    assert not _data(tmp_path, "splat-sdf").exists()
    assert list((tmp_path / "staging" / "splat.work").iterdir()) == []


def test_a_tile_that_did_not_install_is_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = install_fakes(monkeypatch, tmp_path / "bin", _fakes(A))
    _install_tiles(tmp_path, A)
    ledger = TerrainLedger()
    ledger.fail(tile_key(A), "did not verify")
    conv = _converter(tmp_path, A, ledger=ledger)
    assert _run(conv)[0].startswith("skipped")
    assert calls(log) == []


def test_a_square_no_region_needs_loses_its_files_sidecars_and_links(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fakes(monkeypatch, tmp_path / "bin", _fakes(A, FAR))
    _install_tiles(tmp_path, A, FAR)
    _run(_converter(tmp_path, A, FAR))
    conv = _converter(tmp_path, FAR)
    out = _data(tmp_path, "splat-sdf")
    removed = {s.detail for s in _actions(conv.steps(manifest(), _block(manifest())))}
    assert removed == {
        str(out / n)
        for n in (
            "0:1:359:0-hd.sdf.bz2",
            "0:1:359:0.sdf.bz2",
            "0_1_359_360-hd.sdf.bz2",
            "0_1_359_360.sdf.bz2",
        )
    }
    _run(conv)
    assert sorted(p.name for p in out.iterdir()) == sorted(
        [
            "10:11:349:350-hd.sdf.bz2",
            "10:11:349:350-hd.sdf.bz2.source",
            "10:11:349:350.sdf.bz2",
            "10:11:349:350.sdf.bz2.source",
            "10_11_349_350-hd.sdf.bz2",
            "10_11_349_350.sdf.bz2",
        ]
    )


# -- the real programs, where they are installed ------------------------------

REAL = ("gdal_translate", "gdalbuildvrt", "gdalwarp", "srtm2sdf", "srtm2sdf-hd", "bzip2")


@pytest.mark.skipif(
    any(shutil.which(tool) is None for tool in REAL), reason="GDAL, SPLAT or bzip2 absent"
)
def test_the_real_tools_keep_a_basin_below_sea_level(tmp_path: Path) -> None:
    """A synthetic 360 x 360 tile on N36W117's square, with a basin at -60 m
    in one corner: the SDF keeps it. Without -n -32767, srtm2sdf would write
    its neighbours' average there (measured)."""
    tile = "Copernicus_DSM_COG_10_N36_00_W117_00_DEM"
    source = _data(tmp_path, "dem-copernicus")
    source.mkdir(parents=True)
    n = 360
    rows = [" ".join("-60" if r > 300 and c < 60 else "500" for c in range(n)) for r in range(n)]
    grid = tmp_path / "tile.asc"
    grid.write_text(
        f"ncols {n}\nnrows {n}\nxllcorner -117\nyllcorner 36\ncellsize {1 / n}\n"
        + "\n".join(rows)
        + "\n"
    )
    subprocess.run(
        [
            "gdal_translate",
            "-q",
            "-a_srs",
            "EPSG:4326",
            "-ot",
            "Float32",
            str(grid),
            str(source / f"{tile}.tif"),
        ],
        check=True,
    )
    conv = _converter(tmp_path, tile)
    outcomes = _run(conv)
    assert conv.ledger.failed == {}, outcomes
    out = _data(tmp_path, "splat-sdf")
    for name, samples in (("36:37:116:117-hd.sdf.bz2", 3600), ("36:37:116:117.sdf.bz2", 1200)):
        values = [int(v) for v in bz2.decompress((out / name).read_bytes()).split()]
        assert values[:4] == [117, 36, 116, 37]
        body = values[4:]
        assert len(body) == samples * samples
        assert min(body) == -60, "the basin survived"
        assert max(body) == 500
