# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The ``gdal-dem`` converter: elevation and contours for QMapShack.  D-061.

Synthetic tiles near 0/0; fakes stand in for GDAL's programs.
"""

from __future__ import annotations

import fcntl
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from fake_tools import calls, install_fakes
from hammunition.backends import Action, Command
from hammunition.backends.dem import DemResolution, RegionTiles
from hammunition.backends.gdal_dem import (
    CONVERTER,
    RECORD,
    GdalDemConverter,
    buildvrt_argv,
    rasterize_argv,
)
from hammunition.backends.staging import REFUSED, Staging
from hammunition.backends.terrain import TerrainLedger, tile_key
from hammunition.manifest.schema import DerivedDataInstall, PackageManifest

#: The engine is not root, whoever runs the suite (``unshare -r`` included).
NOT_ROOT = 1000

A = "Copernicus_DSM_COG_10_N00_00_E000_00_DEM"
B = "Copernicus_DSM_COG_10_S01_00_W001_00_DEM"
RESOLUTION = DemResolution(
    regions=(RegionTiles("atlantis/oceania", "atlantis-oceania", (A, B), 0),)
)

FAKES = {
    "gdal_contour": 'for last; do :; done; printf lines > "$last"',
    "gdal_rasterize": 'for last; do :; done; printf raster > "$last"',
    "gdalbuildvrt": 'printf vrt > "$2"',
}


def manifest() -> PackageManifest:
    return PackageManifest.model_validate(
        {
            "name": "dem-qmapshack",
            "version": "station",
            "summary": "Elevation for a test",
            "categories": ["navigation-maps"],
            "depends": ["dem-copernicus", "gdal-bin"],
            "install": [
                {
                    "install": {
                        "method": "derived",
                        "converter": "gdal-dem",
                        "source": "dem-copernicus",
                        "licence": "Copernicus DEM licence",
                        "licence_url": "https://spacedata.copernicus.eu/",
                    }
                }
            ],
            "update": {"probe": {"method": "none"}},
            "documentation": {
                "what_it_does": "Elevation for a test, nothing more.",
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


def _install_tiles(tmp_path: Path, *names: str) -> Path:
    out = _data(tmp_path, "dem-copernicus")
    out.mkdir(parents=True, exist_ok=True)
    for name in names:
        (out / f"{name}.tif").write_bytes(b"elevation")
    return out


def _actions(steps: list[Action | Command]) -> list[Action]:
    assert all(isinstance(s, Action) for s in steps)
    return [s for s in steps if isinstance(s, Action)]


def _converter(tmp_path: Path, **kw: Any) -> GdalDemConverter:
    kw.setdefault("resolution", RESOLUTION)
    return GdalDemConverter(
        prefix=tmp_path, staging=Staging(tmp_path / "staging", euid=NOT_ROOT), **kw
    )


def _run(conv: GdalDemConverter) -> list[str]:
    m = manifest()
    return [s.perform() for s in _actions(conv.steps(m, _block(m)))]


def _work(tmp_path: Path) -> Path:
    return tmp_path / "staging" / "dem.work"


def test_each_tile_gets_contours_and_both_rasters_are_built_from_absolute_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = install_fakes(monkeypatch, tmp_path / "bin", FAKES)
    source = _install_tiles(tmp_path, A, B)
    conv = _converter(tmp_path)
    _run(conv)
    assert conv.ledger.failed == {}
    work = _work(tmp_path)
    logged = calls(log)
    assert {where for where, _ in logged} == {str(work)}, "every run in the one working directory"
    commands = [c for _, c in logged]
    assert commands[0] == (
        f"gdal_contour -q -i 20 -a elev {source / f'{A}.tif'} {work / f'{A}.gpkg'}"
    )
    assert commands[1] == (
        f"gdal_rasterize -q -l contour -burn 1 -init 0 -a_nodata 0 -ot Byte "
        f"-te 0 0 1 1 -ts 7200 7200 -co COMPRESS=DEFLATE -of GTiff "
        f"{work / f'{A}.gpkg'} {work / f'{A}.tif'}"
    )
    assert "-te -1 -1 0 0" in commands[3], "a tile south and west of 0/0 keeps its own square"
    out = _data(tmp_path, "dem-qmapshack")
    assert commands[4] == (
        f"gdalbuildvrt -q {work / 'dem.vrt'} {source / f'{A}.tif'} {source / f'{B}.tif'}"
    )
    tiles = out / "contours" / "tiles"
    assert commands[5] == (
        f"gdalbuildvrt -q {work / 'contours.vrt'} {tiles / f'{A}.tif'} {tiles / f'{B}.tif'}"
    )
    assert (out / "dem" / "dem.vrt").read_text() == "vrt"
    assert (out / "contours" / "contours.vrt").read_text() == "vrt"
    assert (tiles / f"{A}.tif").read_text() == "raster"
    assert (tiles / f"{A}.tif.source").read_text() == f"{A}\nconverter: {CONVERTER}\n"
    assert (out / RECORD).read_text() == f"{A}\n{B}\nconverter: {CONVERTER}\n"
    assert sorted(p.name for p in work.iterdir()) == [], "every GeoPackage and raster removed"
    assert sorted(p.name for p in (tmp_path / "staging").iterdir()) == [
        "dem.work",
        "dem.work.lock",
    ], "one working directory and one lock for the whole build"


def test_nothing_is_redrawn_when_every_tile_and_both_rasters_are_current(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fakes(monkeypatch, tmp_path / "bin", FAKES)
    _install_tiles(tmp_path, A, B)
    _run(_converter(tmp_path))
    m = manifest()
    assert _converter(tmp_path).steps(m, _block(m)) == []


def test_a_tile_whose_download_failed_is_skipped_and_the_rest_are_built(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fakes(monkeypatch, tmp_path / "bin", FAKES)
    _install_tiles(tmp_path, B)
    ledger = TerrainLedger()
    ledger.fail(tile_key(A), f"{A}: md5 did not match")
    conv = _converter(tmp_path, ledger=ledger)
    outcomes = _run(conv)
    assert outcomes[0].startswith("skipped")
    assert list(ledger.failed) == [tile_key(A)], "not reported twice"
    out = _data(tmp_path, "dem-qmapshack")
    assert (out / "dem" / "dem.vrt").exists()
    assert not (out / RECORD).exists(), "a missing tile is rebuilt next run"


def test_the_rasters_are_built_over_the_tiles_on_disk_not_the_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A tile the resolution names but that is not on disk is never handed to
    gdalbuildvrt: the VRT would reference a file that does not exist."""
    log = install_fakes(monkeypatch, tmp_path / "bin", FAKES)
    source = _install_tiles(tmp_path, B)
    conv = _converter(tmp_path)
    _run(conv)
    assert (
        f"gdal-dem:{A}" in conv.ledger.failed
        and "is not installed" in (conv.ledger.failed[f"gdal-dem:{A}"])
    )
    dem = [c for _, c in calls(log) if c.startswith("gdalbuildvrt") and "dem.vrt" in c]
    assert dem == [f"gdalbuildvrt -q {_work(tmp_path) / 'dem.vrt'} {source / f'{B}.tif'}"]


def test_contour_that_writes_nothing_fails_that_tile_by_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fakes(monkeypatch, tmp_path / "bin", {**FAKES, "gdal_contour": "exit 0"})
    _install_tiles(tmp_path, A, B)
    conv = _converter(tmp_path)
    _run(conv)
    assert set(conv.ledger.failed) == {f"gdal-dem:{A}", f"gdal-dem:{B}"}
    assert "gdal_contour drew no contours" in conv.ledger.failed[f"gdal-dem:{A}"]
    assert list(_work(tmp_path).iterdir()) == []


def test_rasterize_that_writes_nothing_fails_that_tile_and_clears_its_geopackage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fakes(monkeypatch, tmp_path / "bin", {**FAKES, "gdal_rasterize": "exit 1"})
    _install_tiles(tmp_path, A, B)
    conv = _converter(tmp_path)
    _run(conv)
    assert "gdal_rasterize wrote no contour raster" in conv.ledger.failed[f"gdal-dem:{A}"]
    assert list(_work(tmp_path).iterdir()) == [], "the GeoPackage does not outlive a failure"


def test_a_tile_no_region_needs_loses_its_contours(tmp_path: Path) -> None:
    tiles = _data(tmp_path, "dem-qmapshack") / "contours" / "tiles"
    tiles.mkdir(parents=True)
    for name in (A, B, "Copernicus_DSM_COG_10_N05_00_E005_00_DEM"):
        (tiles / f"{name}.tif").write_text("raster")
    m = manifest()
    steps = _actions(_converter(tmp_path).steps(m, _block(m)))
    removals = [s for s in steps if s.kind == "remove-data"]
    assert [s.detail for s in removals] == [
        str(tiles / "Copernicus_DSM_COG_10_N05_00_E005_00_DEM.tif")
    ]


def test_the_contour_step_states_its_measured_sizes(tmp_path: Path) -> None:
    m = manifest()
    (draw, *_rest) = _actions(_converter(tmp_path).steps(m, _block(m)))
    assert "20 m contours" in draw.description
    assert "measured on one region" in draw.description
    assert draw.requires_root is False


def test_a_geopackage_left_by_an_earlier_run_is_removed_before_contouring(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review focus: gdal_contour appends to an existing GeoPackage and exits
    0 (measured on 3.10.3), so a leftover would double the lines."""
    refuse_existing = 'for last; do :; done; test ! -e "$last" || exit 4; printf lines > "$last"'
    install_fakes(monkeypatch, tmp_path / "bin", {**FAKES, "gdal_contour": refuse_existing})
    _install_tiles(tmp_path, A, B)
    work = _work(tmp_path)
    work.mkdir(parents=True)
    (work / f"{A}.gpkg").write_text("half-written")
    conv = _converter(tmp_path)
    _run(conv)
    assert conv.ledger.failed == {}


def test_contours_from_another_converter_version_are_redrawn(tmp_path: Path) -> None:
    tiles = _data(tmp_path, "dem-qmapshack") / "contours" / "tiles"
    tiles.mkdir(parents=True)
    for name in (A, B):
        (tiles / f"{name}.tif").write_text("raster")
    (tiles / f"{A}.tif.source").write_text(f"{A}\nconverter: {CONVERTER}\n")
    (tiles / f"{B}.tif.source").write_text(f"{B}\nconverter: gdal-dem 0\n")
    assert _converter(tmp_path).pending(manifest()) == [B]


def test_a_record_from_another_converter_rebuilds_the_rasters(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fakes(monkeypatch, tmp_path / "bin", FAKES)
    _install_tiles(tmp_path, A, B)
    _run(_converter(tmp_path))
    out = _data(tmp_path, "dem-qmapshack")
    (out / RECORD).write_text(f"{A}\n{B}\n")  # from before the converter was recorded
    m = manifest()
    steps = _actions(_converter(tmp_path).steps(m, _block(m)))
    assert [s.detail for s in steps] == [str(out / RECORD)], "the rasters only, no redraw"


def test_a_busy_build_fails_by_name_and_deletes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Another conversion holding ``dem.work.lock``: every run and every clear
    is refused with 125 before it starts, and each part fails by name."""
    log = install_fakes(monkeypatch, tmp_path / "bin", FAKES)
    _install_tiles(tmp_path, A, B)
    conv = _converter(tmp_path)
    work = _work(tmp_path)
    work.mkdir(parents=True)
    theirs = work / "theirs.gpkg"
    theirs.write_text("another run's")
    with Staging.lockfile(work).open("w") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        _run(conv)
    assert calls(log) == []
    assert theirs.read_text() == "another run's", "a busy refusal deletes nothing"
    assert set(conv.ledger.failed) == {f"gdal-dem:{A}", f"gdal-dem:{B}", "gdal-dem"}
    assert "another conversion" in conv.ledger.failed[f"gdal-dem:{A}"]
    assert "another conversion" in conv.ledger.failed["gdal-dem"]


def test_every_run_holds_the_one_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_fakes(monkeypatch, tmp_path / "bin", FAKES)
    _install_tiles(tmp_path, A, B)
    locks: list[Path | None] = []
    real_run, real_clear = Staging.run, Staging.clear

    def run(self: Staging, argv: Any, *, cwd: Path, **kw: Any) -> Any:
        locks.append(kw.get("lock"))
        return real_run(self, argv, cwd=cwd, **kw)

    def clear(self: Staging, cwd: Path, **kw: Any) -> Any:
        locks.append(kw.get("lock"))
        return real_clear(self, cwd, **kw)

    monkeypatch.setattr(Staging, "run", run)
    monkeypatch.setattr(Staging, "clear", clear)
    _run(_converter(tmp_path))
    assert locks and set(locks) == {tmp_path / "staging" / "dem.work.lock"}


def test_a_clear_that_fails_fails_that_tile_and_says_scratch_was_not_cleared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fakes(monkeypatch, tmp_path / "bin", FAKES)
    _install_tiles(tmp_path, A, B)
    real = Staging.clear
    seen = [0]

    def clear(self: Staging, cwd: Path, **kw: Any) -> subprocess.CompletedProcess[str]:
        seen[0] += 1
        if seen[0] == 2:  # the clear after tile A's install
            return subprocess.CompletedProcess(["find"], 1, "", "find: cannot delete: boom")
        return real(self, cwd, **kw)

    monkeypatch.setattr(Staging, "clear", clear)
    outcomes = _run(_converter(tmp_path))
    assert "cleared" not in outcomes[1].replace("not cleared", "")
    assert "boom" in outcomes[1] and "not cleared" in outcomes[1]


def test_a_pre_clear_refused_runs_nothing_for_that_tile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = install_fakes(monkeypatch, tmp_path / "bin", FAKES)
    _install_tiles(tmp_path, A, B)

    def clear(self: Staging, cwd: Path, **kw: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(["find"], REFUSED, "", "held by another")

    monkeypatch.setattr(Staging, "clear", clear)
    conv = _converter(tmp_path)
    _run(conv)
    assert calls(log) == []
    assert "was not started" in conv.ledger.failed[f"gdal-dem:{A}"]
    assert "was not started" in conv.ledger.failed["gdal-dem"]


def test_the_outcome_says_who_drew_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_fakes(monkeypatch, tmp_path / "bin", FAKES)
    _install_tiles(tmp_path, A, B)
    monkeypatch.setattr(Staging, "who", lambda self: "as operator")
    outcomes = _run(_converter(tmp_path))
    assert outcomes[0].startswith(f"drew the contours of {A} as operator")


def test_root_with_nobody_to_run_as_fails_and_runs_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Deterministic, whoever runs the suite: in CI's container every component
    # of tmp_path really is root's, and root would rightly work there itself.
    monkeypatch.setattr(
        "hammunition.backends.staging._owner_uid",
        lambda path: 4242 if path == tmp_path else 0,
    )
    log = install_fakes(monkeypatch, tmp_path / "bin", FAKES)
    _install_tiles(tmp_path, A, B)
    conv = GdalDemConverter(
        prefix=tmp_path,
        resolution=RESOLUTION,
        staging=Staging(tmp_path / "staging", euid=0),
        privileged=False,
    )
    _run(conv)
    assert "refusing" in conv.ledger.failed[f"gdal-dem:{A}"]
    assert calls(log) == []


def test_the_argv_builders_are_fixed() -> None:
    assert rasterize_argv(Path("/s/x.gpkg"), Path("/s/x.tif"), B)[13:17] == [
        "-1",
        "-1",
        "0",
        "0",
    ]
    assert buildvrt_argv(Path("/s/d.vrt"), [Path("/t/a.tif")]) == [
        "gdalbuildvrt",
        "-q",
        "/s/d.vrt",
        "/t/a.tif",
    ]


@pytest.mark.skipif(
    shutil.which("gdalbuildvrt") is None or shutil.which("gdal_translate") is None,
    reason="gdal-bin is not installed on this machine; the fakes stand in for it",
)
def test_real_gdalbuildvrt_writes_absolute_sources(tmp_path: Path) -> None:
    """A smoke on a synthetic 2x2 GeoTIFF: the VRT names its source by an
    absolute path when the source is outside the VRT's own directory."""
    tiles, work = tmp_path / "tiles", tmp_path / "work"
    tiles.mkdir()
    work.mkdir()
    asc = tiles / "t.asc"
    asc.write_text("ncols 2\nnrows 2\nxllcorner 0\nyllcorner 0\ncellsize 0.5\n1 2\n3 4\n")
    tif = tiles / "t.tif"
    subprocess.run(["gdal_translate", "-q", str(asc), str(tif)], check=True)
    vrt = work / "dem.vrt"
    subprocess.run(buildvrt_argv(vrt, [tif]), check=True)
    text = vrt.read_text()
    assert f">{tif}<" in text and 'relativeToVRT="0"' in text
