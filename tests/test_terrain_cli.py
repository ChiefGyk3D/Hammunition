# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Piece 2 wired into ``install`` and ``update``.  D-061.

Synthetic regions (``atlantis/*``) and synthetic tiles near 0/0 only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from hammunition.backends import Action, AptBackend, DerivedBackend, RecordingRunner, RegionsBackend
from hammunition.backends.dem import TIF, DemResolution, RegionTiles, render_record
from hammunition.backends.garmin import MKGMAP_HEAP, SPLITTER_HEAP
from hammunition.backends.gdal_dem import CONVERTER, RECORD
from hammunition.backends.gdal_dem import render_record as render_gdal_record
from hammunition.backends.regions import KeptRegion, MapLedger, MapResolution, data_root
from hammunition.copernicus import CopernicusError, TileFile, tile_url
from hammunition.distro import Target
from hammunition.execute import commands_for
from hammunition.fetch import Fetcher
from hammunition.plan import InstallPlan, PlannedPackage
from hammunition.terrain_plan import (
    SPLITTER_ENV,
    build_terrain_run,
    poly_url,
    resolve_station_terrain,
)
from hammunition.update import NOT_INSTALLED, UP_TO_DATE, rebuild_command, render, report
from test_json_plan_terrain import COP, LEMURIA, OCEANIA, _derived, _unit, terrain_plan

A = "Copernicus_DSM_COG_10_N00_00_E000_00_DEM"
OUTLINE = "o\n1\n 0.2 0.2\n 0.8 0.2\n 0.8 0.8\nEND\nEND\n"
TARGET = Target(distro="debian", version="13", arch="x86_64")


class RegionProbe:
    def __init__(self, texts: dict[str, str]) -> None:
        self.texts = texts
        self.asked: list[str] = []

    def head(self, url: str) -> tuple[int, int, str | None]:  # pragma: no cover
        raise AssertionError("not asked")

    def text(self, url: str) -> str:
        from hammunition.geofabrik import GeofabrikError

        self.asked.append(url)
        if url not in self.texts:
            raise GeofabrikError(f"{url}: offline")
        return self.texts[url]


class TileProbe:
    def head(self, url: str) -> tuple[int, int, str | None]:
        return 200, 39_000_000, '"0123456789abcdef0123456789abcdef"'


def _catalog(tmp_path: Path, *, tiles: bool = True) -> Path:
    root = tmp_path / "catalog"
    (root / "data").mkdir(parents=True)
    if tiles:
        (root / "data" / "copernicus-glo30-tiles.txt").write_text(f"# test list\n{A}\n")
    return root


def _plan(*units: Any) -> InstallPlan:
    return InstallPlan(
        target=TARGET,
        packages=tuple(
            PlannedPackage(manifest=u, block=u.install[0], apt_packages=()) for u in units
        ),
    )


def _dem() -> Any:
    return _unit("dem-copernicus", {"method": "dem-tiles", "provider": "copernicus-glo30", **COP})


def test_the_plan_s_regions_and_kept_regions_are_resolved_to_tiles(tmp_path: Path) -> None:
    plan, _maps, _terrain = terrain_plan()
    kept = KeptRegion(LEMURIA.region, LEMURIA.slug, "250101", "offline")
    dem_dir = tmp_path / "share" / "hammunition" / "data" / "dem-copernicus"
    dem_dir.mkdir(parents=True)
    (dem_dir / f"{LEMURIA.slug}.tiles").write_text(
        render_record(RegionTiles(LEMURIA.region, LEMURIA.slug, (A,), 0))
    )
    probe = RegionProbe({poly_url(OCEANIA.region): OUTLINE})
    got = resolve_station_terrain(
        plan,
        MapResolution(files=(OCEANIA,), kept=(kept,)),
        _catalog(tmp_path),
        prefix=tmp_path,
        region_probe=probe,
        tile_probe=TileProbe(),
    )
    assert [r.slug for r in got.regions] == [OCEANIA.slug, LEMURIA.slug]
    assert [t.name for t in got.fetch] == [A]
    assert got.fetch[0].url == tile_url(A)
    # The kept region answered from its record: only the new one's outline was asked for.
    assert probe.asked == [poly_url(OCEANIA.region)]


def test_a_missing_tile_list_is_refused_by_name_not_read_as_all_unpublished(tmp_path: Path) -> None:
    plan, _maps, _terrain = terrain_plan()
    with pytest.raises(CopernicusError, match=r"copernicus-glo30-tiles\.txt"):
        resolve_station_terrain(
            plan,
            MapResolution(files=(OCEANIA,)),
            _catalog(tmp_path, tiles=False),
            prefix=tmp_path,
            region_probe=RegionProbe({}),
            tile_probe=TileProbe(),
        )


def test_an_unreachable_outline_is_refused_as_a_copernicus_error(tmp_path: Path) -> None:
    plan, _maps, _terrain = terrain_plan()
    with pytest.raises(CopernicusError, match="atlantis/oceania"):
        resolve_station_terrain(
            plan,
            MapResolution(files=(OCEANIA,)),
            _catalog(tmp_path),
            prefix=tmp_path,
            region_probe=RegionProbe({}),
            tile_probe=TileProbe(),
        )


def test_a_plan_without_a_dem_unit_asks_nothing(tmp_path: Path) -> None:
    plan = InstallPlan(target=TARGET, packages=())
    got = resolve_station_terrain(
        plan,
        MapResolution(files=(OCEANIA,)),
        tmp_path / "no-catalog",
        prefix=tmp_path,
        region_probe=RegionProbe({}),
        tile_probe=TileProbe(),
    )
    assert got == DemResolution()


def _run(tmp_path: Path, resolution: DemResolution, fetcher: Fetcher | None = None) -> Any:
    return build_terrain_run(
        prefix=tmp_path,
        builds=tmp_path / "builds",
        owner=None,
        runner=None,
        fetcher=fetcher or Fetcher(tmp_path / "cache"),
        files=[OCEANIA],
        keep=frozenset(),
        regions=MapLedger(),
        resolution=resolution,
    )


def test_the_run_discloses_each_converter_s_pending_work(tmp_path: Path) -> None:
    plan, _maps, _terrain = terrain_plan()
    resolution = DemResolution(regions=(RegionTiles(OCEANIA.region, OCEANIA.slug, (A,), 0),))
    run = _run(tmp_path, resolution)
    disclosed = run.disclosure(plan)
    assert disclosed is not None
    assert [f.slug for f in disclosed.garmin] == [OCEANIA.slug]
    assert disclosed.routino_regions == 1 and disclosed.contours == 1 and disclosed.drawing
    assert disclosed.licence == "Copernicus DEM licence"
    needs = run.needs(plan, cache=tmp_path / "cache", prefix=tmp_path)
    assert needs[tmp_path / "builds" / "osm-garmin"] > 0
    assert set(run.converters) == {
        "mkgmap",
        "routino-planetsplitter",
        "gdal-dem",
        "ustopo-mosaic",
        "brouter-mapcreator",
        "splat-sdf",
    }


def _contours_installed(tmp_path: Path, *, rasters: bool) -> None:
    out = data_root(tmp_path) / "dem-qmapshack"
    tiles = out / "contours" / "tiles"
    tiles.mkdir(parents=True)
    (tiles / f"{A}{TIF}").write_bytes(b"c")
    (tiles / f"{A}{TIF}.source").write_text(f"{A}\nconverter: {CONVERTER}\n")
    (out / RECORD).write_text(render_gdal_record((A,)))
    if rasters:
        (out / "dem").mkdir()
        (out / "dem" / "dem.vrt").write_text("v")
        (out / "contours" / "contours.vrt").write_text("v")


@pytest.mark.parametrize(("rasters", "drawing"), [(True, False), (False, True)])
def test_drawing_is_pending_contours_or_rasters_not_current(
    tmp_path: Path, rasters: bool, drawing: bool
) -> None:
    """Every contour drawn: ``drawing`` is whether the two rasters need
    building, read from the record and the files, not from a step count."""
    _contours_installed(tmp_path, rasters=rasters)
    plan = _plan(_derived("dem-qmapshack", "gdal-dem", "dem-copernicus"))
    resolution = DemResolution(regions=(RegionTiles(OCEANIA.region, OCEANIA.slug, (A,), 0),))
    disclosed = _run(tmp_path, resolution).disclosure(plan)
    assert disclosed is not None
    assert disclosed.contours == 0 and disclosed.drawing is drawing


def test_the_garmin_staging_gives_splitter_and_mkgmap_each_their_heap(tmp_path: Path) -> None:
    """Debian's mkgmap wrapper ignores ``JAVA_OPTS``; its heap goes through
    ``JAVA_TOOL_OPTIONS`` (Task 6 review, I2)."""
    assert SPLITTER_ENV == {"JAVA_OPTS": SPLITTER_HEAP, "JAVA_TOOL_OPTIONS": MKGMAP_HEAP}
    run = _run(tmp_path, DemResolution())
    assert dict(run.garmin.staging.environ) == SPLITTER_ENV


def test_a_plan_with_no_piece_2_unit_discloses_nothing(tmp_path: Path) -> None:
    plan = InstallPlan(target=TARGET, packages=())
    run = _run(tmp_path, DemResolution())
    assert run.disclosure(plan) is None
    assert run.needs(plan, cache=tmp_path / "cache", prefix=tmp_path) == {}


def test_a_tiles_only_plan_still_ends_with_the_terrain_check(tmp_path: Path) -> None:
    """The dem-tiles unit without gdal-dem: its ledger is still checked, once, last."""
    from test_dem_backend import FakeFetcher

    tile = TileFile(A, tile_url(A), 4, None, "0" * 32)
    resolution = DemResolution(
        regions=(RegionTiles(OCEANIA.region, OCEANIA.slug, (A,), 0),), fetch=(tile,)
    )
    run = _run(tmp_path, resolution, FakeFetcher(tmp_path / "cache"))
    derived = DerivedBackend(
        prefix=tmp_path, files=(), staging=tmp_path / "navit", converters=run.converters
    )
    steps = commands_for(_plan(_dem()), AptBackend(RecordingRunner()), derived=derived, dem=run.dem)
    kinds = [s.kind for s in steps if isinstance(s, Action)]
    assert kinds[-1] == "check-terrain" and kinds.count("check-terrain") == 1


def test_map_work_counts_navit_conversions_only(tmp_path: Path) -> None:
    from hammunition.cli.main import map_work

    garmin = _derived("osm-garmin", "mkgmap", "osm-regions")
    plan = _plan(garmin)
    regions = RegionsBackend(fetcher=Fetcher(tmp_path / "c"), prefix=tmp_path, files=[OCEANIA])
    derived = DerivedBackend(prefix=tmp_path, files=[OCEANIA], staging=tmp_path / "s")
    assert map_work(plan, regions, derived) == ([], [])


def test_the_leftover_note_sees_piece_2_s_files(tmp_path: Path) -> None:
    from hammunition.cli.main import leftover_maps_note
    from hammunition.plan import NO_MAP_REGIONS, Deferral

    (data_root(tmp_path) / "dem-copernicus").mkdir(parents=True)
    (data_root(tmp_path) / "dem-copernicus" / f"{A}{TIF}").write_bytes(b"t")
    plan = InstallPlan(
        target=TARGET,
        packages=(),
        deferrals=(Deferral(subject="dem-copernicus", what="-", why=NO_MAP_REGIONS, remedy="-"),),
    )
    note = leftover_maps_note(plan, tmp_path)
    assert note is not None and "hammunition uninstall dem-copernicus" in note


def _tile_counted_report(tmp_path: Path) -> Any:
    from hammunition.cli.main import installed_tile_counts

    dem = _dem()
    plan = _plan(dem)
    out = data_root(tmp_path) / "dem-copernicus"
    out.mkdir(parents=True)
    for lat in range(3):
        (out / f"Copernicus_DSM_COG_10_N0{lat}_00_E000_00_DEM{TIF}").write_bytes(b"t")
    # The region's record sits beside the tiles; it is never read for the count.
    (out / f"{OCEANIA.slug}.tiles").write_text(
        render_record(RegionTiles(OCEANIA.region, OCEANIA.slug, (A,), 0))
    )
    tiles = installed_tile_counts(plan, tmp_path)
    assert tiles == {"dem-copernicus": 3}
    return report(plan, apt_states={}, present={}, built=(), tiles=tiles)


def test_update_reports_a_tile_count_and_never_a_tile_or_region_name(tmp_path: Path) -> None:
    result = _tile_counted_report(tmp_path)
    (row,) = result.rows
    assert row.state == UP_TO_DATE and "3 terrain tile(s)" in row.detail
    text = render(result, lists_note="fresh")
    assert "Copernicus_DSM" not in text
    assert "atlantis" not in text and OCEANIA.slug not in text
    (row,) = report(_plan(_dem()), apt_states={}, present={}, built=()).rows
    assert row.state == NOT_INSTALLED


def test_the_rebuild_footer_names_qmapshack_s_maps_when_they_are_installed() -> None:
    from hammunition.update import BEHIND_PIN, UpdateReport, UpdateRow

    rows = (
        UpdateRow("osm-regions", BEHIND_PIN, "1 region installed; 1 behind the pin", "reinstall"),
        UpdateRow("osm-garmin", "unknown", "no comparison for this method", "reinstall"),
    )
    assert rebuild_command(UpdateReport(rows=rows, upstream_declared=())) == (
        "hammunition install osm-regions osm-navit osm-garmin"
    )


# ---------------------------------------------------------------------------
# End to end through `hammunition install --dry-run` and `hammunition update`
# ---------------------------------------------------------------------------

_HEADER = """\
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: CC0-1.0
"""
_DOCS = """\
update:
  probe:
    method: none
  strategy: reinstall
documentation:
  what_it_does: Stands in for a piece-2 unit in the CLI wiring tests.
  why_you_want_it: The dry run needs a terrain unit to disclose.
  upstream_url: https://example.invalid/
"""


def _terrain_catalog(tmp_path: Path, *, tiles: bool = True) -> Path:
    root = _catalog(tmp_path, tiles=tiles)
    (root / "packages").mkdir()
    (root / "packages" / "osm-regions.yaml").write_text(
        _HEADER
        + """\
name: osm-regions
version: station
summary: Map regions for a test
categories: [navigation-maps]
install:
  - install:
      method: osm-regions
      provider: geofabrik
      licence: ODbL-1.0
      licence_url: https://www.openstreetmap.org/copyright
"""
        + _DOCS
    )
    # As the catalog's own dem-copernicus does: its regions are osm-regions'.
    (root / "packages" / "dem-copernicus.yaml").write_text(
        _HEADER
        + """\
name: dem-copernicus
version: station
summary: Terrain tiles for a test
categories: [navigation-maps]
depends: [osm-regions]
install:
  - install:
      method: dem-tiles
      provider: copernicus-glo30
      licence: Copernicus DEM licence
      licence_url: https://spacedata.copernicus.eu/
"""
        + _DOCS
    )
    (root / "packages" / "dem-qmapshack.yaml").write_text(
        _HEADER
        + """\
name: dem-qmapshack
version: station
summary: Contours for a test
categories: [navigation-maps]
depends: [dem-copernicus]
install:
  - install:
      method: derived
      converter: gdal-dem
      source: dem-copernicus
      licence: Copernicus DEM licence
      licence_url: https://spacedata.copernicus.eu/
"""
        + _DOCS
    )
    return root


def _machine(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Any:
    """The JSON install harness's machine, the station's regions set, the data
    prefix under *tmp_path*, and every network probe stood in for."""
    from hammunition.backends.source import SourceBackend
    from hammunition.station import Station, save_station
    from test_json_install import _machine as json_machine
    from test_json_install import cli

    json_machine(monkeypatch, tmp_path)
    save_station(
        Station(callsign="N0TST", map_regions=(OCEANIA.region,)),
        path=tmp_path / "xdg_config_home" / "hammunition" / "station.yml",
    )
    monkeypatch.setattr(
        cli,
        "SourceBackend",
        lambda fetcher, *, build_root, owner=None: SourceBackend(
            fetcher, build_root=build_root, prefix=tmp_path, owner=owner
        ),
    )
    monkeypatch.setattr(cli, "resolve_map_regions", lambda *a, **k: MapResolution(files=(OCEANIA,)))
    monkeypatch.setattr(
        cli, "UrllibProbe", lambda: RegionProbe({poly_url(OCEANIA.region): OUTLINE})
    )
    monkeypatch.setattr(cli, "S3Probe", TileProbe)
    return cli


def test_the_dry_run_discloses_terrain_in_text_and_json_and_changes_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import json

    cli = _machine(monkeypatch, tmp_path)
    catalog = str(_terrain_catalog(tmp_path))
    before = sorted(p for p in tmp_path.rglob("*") if "xdg_" not in str(p))
    assert cli.main(["--catalog", catalog, "install", "--dry-run", "dem-qmapshack"]) == 0
    text = capsys.readouterr().out
    assert "Terrain, Copernicus GLO-30 elevation (D-061):" in text
    assert f"{OCEANIA.region}  1 tile(s)" in text
    assert "contours for 1 tile(s)" in text
    assert f"Fetch terrain tile {A}" in text
    assert text.count("[check-terrain]") == 1
    assert "fetched again" in text
    # The regions are shown under their own licence, not the contour unit's.
    regions_part = text.split("Terrain, Copernicus")[0]
    assert "licence: ODbL-1.0" in regions_part and "Copernicus DEM" not in regions_part
    assert sorted(p for p in tmp_path.rglob("*") if "xdg_" not in str(p)) == before
    assert cli.main(["--catalog", catalog, "install", "--dry-run", "--json", "dem-qmapshack"]) == 0
    doc = json.loads(capsys.readouterr().out)
    terrain = doc["install"]["maps"]["terrain"]
    assert [t["tile"] for t in terrain["fetch"]] == [A] and terrain["contours"] == 1


def test_an_unresolvable_terrain_refuses_the_plan_and_changes_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli = _machine(monkeypatch, tmp_path)
    catalog = str(_terrain_catalog(tmp_path, tiles=False))
    assert cli.main(["--catalog", catalog, "install", "--dry-run", "dem-qmapshack"]) == 2
    err = capsys.readouterr().err
    assert "copernicus-glo30-tiles.txt" in err and "Nothing was changed." in err


def test_a_disk_short_of_terrain_s_needs_refuses_the_plan(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from hammunition.backends.terrain import combined_shortfall

    cli = _machine(monkeypatch, tmp_path)
    monkeypatch.setattr(
        cli,
        "combined_shortfall",
        lambda maps, terrain, **kw: combined_shortfall(maps, terrain, free_at=lambda path: 0, **kw),
    )
    catalog = str(_terrain_catalog(tmp_path))
    assert cli.main(["--catalog", catalog, "install", "--dry-run", "dem-qmapshack"]) == 2
    err = capsys.readouterr().err
    assert "Nothing was changed." in err and "terrain" in err


def test_update_end_to_end_counts_tiles_and_names_none(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli = _machine(monkeypatch, tmp_path)
    catalog = str(_terrain_catalog(tmp_path))
    out_dir = data_root(tmp_path) / "dem-copernicus"
    out_dir.mkdir(parents=True)
    (out_dir / f"{A}{TIF}").write_bytes(b"t")
    (out_dir / f"{OCEANIA.slug}.tiles").write_text(
        render_record(RegionTiles(OCEANIA.region, OCEANIA.slug, (A,), 0))
    )
    for argv in (["update", "dem-copernicus"], ["update", "dem-copernicus", "--json"]):
        assert cli.main(["--catalog", catalog, *argv]) == 0
        out = capsys.readouterr().out
        assert "1 terrain tile(s)" in out, argv
        assert "Copernicus_DSM" not in out and "atlantis" not in out, argv


def test_update_counts_regions_with_no_published_tile_and_names_none(tmp_path: Path) -> None:
    """Final review, I1: a region Copernicus publishes nothing for is counted,
    never called sea and never named."""
    from hammunition.cli.main import installed_tile_counts, no_terrain_counts

    plan = _plan(_dem())
    out = data_root(tmp_path) / "dem-copernicus"
    out.mkdir(parents=True)
    (out / f"{OCEANIA.slug}.tiles").write_text(
        render_record(RegionTiles(OCEANIA.region, OCEANIA.slug, (), 4))
    )
    assert no_terrain_counts(plan, tmp_path) == {"dem-copernicus": 1}
    result = report(
        plan,
        apt_states={},
        present={},
        built=(),
        tiles=installed_tile_counts(plan, tmp_path),
        no_terrain=no_terrain_counts(plan, tmp_path),
    )
    (row,) = result.rows
    assert row.state == NOT_INSTALLED
    assert row.detail == (
        "no terrain tiles installed; 1 region(s) with no published tile at "
        "Copernicus GLO-30 (sea, or land it does not release)"
    )
    text = render(result, lists_note="fresh")
    assert "atlantis" not in text and OCEANIA.slug not in text


@pytest.mark.parametrize(
    "shape",
    ["pins: [\n  {tile: x\n", f"pins:\n  - tile: {A}\n", "pins: 3\n"],
    ids=["yaml-syntax", "missing-key", "not-a-list"],
)
def test_a_malformed_pins_file_refuses_the_plan_in_text_and_json(
    shape: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Final review, M1: exit 2, "Nothing was changed", and under --json one
    document -- never a traceback."""
    import json

    cli = _machine(monkeypatch, tmp_path)
    catalog = _terrain_catalog(tmp_path)
    (catalog / "data" / "copernicus-glo30-pins.yaml").write_text(shape)
    argv = ["--catalog", str(catalog), "install", "--dry-run", "dem-qmapshack"]
    assert cli.main(argv) == 2
    err = capsys.readouterr().err
    assert "copernicus-glo30-pins.yaml" in err and "Nothing was changed." in err
    assert "Traceback" not in err
    assert cli.main([*argv, "--json"]) == 2
    captured = capsys.readouterr()
    doc = json.loads(captured.out)  # one document, nothing else on stdout
    assert doc["outcome"] == "refused"
    assert any("copernicus-glo30-pins.yaml" in b["reason"] for b in doc["blockers"])
