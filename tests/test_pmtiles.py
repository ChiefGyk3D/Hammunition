# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The ``tilemaker-pmtiles`` converter: one PMTiles file per region.  D-071.

Public example regions only (Vermont, Delaware), each a synthetic ``.osm.pbf``
whose header carries a bbox. A fake ``tilemaker`` and a fake ``ogr2ogr`` on
PATH record their argv and working directory and write what the real ones'
output starts with; tilemaker is not installed on the development host, so
nothing here runs it. The kit is a directory of stand-in files laid out as
``vector-map-kit`` installs them.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from fake_tools import calls, install_fakes
from hammunition.backends import Action, Command
from hammunition.backends.base import BackendError
from hammunition.backends.pmtiles import (
    CONFIG,
    CONVERTER,
    LANDCOVER,
    OCEAN,
    PAD,
    PROCESS,
    SHAPE_PARTS,
    TilesConverter,
    TilesLedger,
    clip_box,
    tilemaker_argv,
)
from hammunition.backends.regions import MapLedger
from hammunition.backends.staging import Staging
from hammunition.geofabrik import RegionFile
from hammunition.manifest.schema import DerivedDataInstall, PackageManifest
from test_osm_pbf import pbf

NOT_ROOT = 1000
#: A stand-in for the kit's config-openmaptiles.json: its shape, two layers.
KIT_CONFIG = json.dumps(
    {
        "layers": {
            "place": {"minzoom": 0, "maxzoom": 14},
            "water": {"minzoom": 6, "maxzoom": 14},
        },
        "settings": {"minzoom": 0, "maxzoom": 14, "basezoom": 14},
    }
)
VERMONT_BOX = (-73.44, -71.46, 45.02, 42.72)  # left, right, top, bottom
BODY = pbf(VERMONT_BOX)


def _region(path: str, snapshot: str = "260101") -> RegionFile:
    return RegionFile(
        path,
        snapshot,
        f"https://download.geofabrik.de/{path}-{snapshot}.osm.pbf",
        len(BODY),
        hashlib.sha256(BODY).hexdigest(),
        None,
    )


VERMONT = _region("north-america/us/vermont")
DELAWARE = _region("north-america/us/delaware")

_OUT = 'o=$(echo "$*" | sed -n "s/.*--output \\([^ ]*\\).*/\\1/p")'
TILEMAKER_OK = f'{_OUT}; printf "PMTiles\\003rest of the archive" > "$o"'
#: ogr2ogr's destination is the argument after the layer name.
_DST = 'd=$(echo "$*" | sed -n "s/.*-nln water_polygons \\([^ ]*\\).*/\\1/p")'
OGR_OK = f'{_DST}; b="${{d%.shp}}"; for e in shp shx dbf prj; do printf x > "$b.$e"; done'


def manifest() -> PackageManifest:
    return PackageManifest.model_validate(
        {
            "name": "osm-pmtiles",
            "version": "station",
            "summary": "Vector tiles for a test",
            "categories": ["navigation-maps"],
            "depends": ["osm-regions", "vector-map-kit", "tilemaker", "gdal-bin"],
            "install": [
                {
                    "install": {
                        "method": "derived",
                        "converter": "tilemaker-pmtiles",
                        "source": "osm-regions",
                        "kit": "vector-map-kit",
                        "licence": "ODbL-1.0",
                        "licence_url": "https://www.openstreetmap.org/copyright",
                    }
                }
            ],
            "update": {"probe": {"method": "none"}},
            "documentation": {
                "what_it_does": "Vector tiles for a test, nothing more.",
                "why_you_want_it": "Because the test suite needs a manifest.",
                "upstream_url": "https://github.com/systemed/tilemaker",
            },
        }
    )


def _block(m: PackageManifest) -> DerivedDataInstall:
    block = m.install[0].install
    assert isinstance(block, DerivedDataInstall)
    return block


def _data(prefix: Path, unit: str) -> Path:
    return prefix / "share" / "hammunition" / "data" / unit


def _install_region(prefix: Path, region: RegionFile, body: bytes = BODY) -> Path:
    out = _data(prefix, "osm-regions")
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{region.slug}.osm.pbf"
    path.write_bytes(body)
    return path


def _kit(prefix: Path, *, skip: str | None = None) -> Path:
    kit = _data(prefix, "vector-map-kit")
    for rel in (CONFIG, PROCESS):
        (kit / rel).parent.mkdir(parents=True, exist_ok=True)
        (kit / rel).write_text("stand-in")
    (kit / CONFIG).write_text(KIT_CONFIG)
    for layer in (OCEAN, *LANDCOVER):
        for part in SHAPE_PARTS:
            name = f"{layer}.{part}"
            if name != skip:
                (kit / name).write_bytes(b"x")
    return kit


def _converter(tmp_path: Path, files: list[RegionFile], **kw: Any) -> TilesConverter:
    _kit(tmp_path, skip=kw.pop("skip", None))
    return TilesConverter(
        prefix=tmp_path,
        files=files,
        staging=Staging(tmp_path / "staging" / "osm-pmtiles", euid=NOT_ROOT),
        **kw,
    )


def _actions(steps: list[Action | Command]) -> list[Action]:
    assert all(isinstance(s, Action) for s in steps)
    return [s for s in steps if isinstance(s, Action)]


def _run(conv: TilesConverter) -> list[str]:
    m = manifest()
    return [step.perform() for step in _actions(conv.steps(m, _block(m)))]


@pytest.fixture
def fakes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    return install_fakes(
        monkeypatch, tmp_path / "bin", {"tilemaker": TILEMAKER_OK, "ogr2ogr": OGR_OK}
    )


# -- the argv ---------------------------------------------------------------------


def test_tilemaker_runs_the_infra_profile_written_in_the_workdir_with_a_store() -> None:
    """D-075: the kit's profile plus the infra layer, as two files the
    converter writes beside the store; the kit's own files are unchanged."""
    kit, work = Path("/kit"), Path("/w/vermont.work")
    argv = tilemaker_argv(Path("/d/vermont.osm.pbf"), work / "vermont.pmtiles", kit, work)
    assert argv == [
        "tilemaker",
        "--input",
        "/d/vermont.osm.pbf",
        "--output",
        "/w/vermont.work/vermont.pmtiles",
        "--config",
        "/w/vermont.work/config-infra.json",
        "--process",
        "/w/vermont.work/process-infra.lua",
        "--store",
        "/w/vermont.work/store",
    ]


def test_the_converter_version_forces_one_rebuild_for_the_infra_layer() -> None:
    assert CONVERTER == "tilemaker-pmtiles 2"


def test_the_infra_profile_is_written_as_the_operator_before_tilemaker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = tmp_path / "seen"
    seen.mkdir()
    keep = (
        'c=$(echo "$*" | sed -n "s/.*--config \\([^ ]*\\).*/\\1/p"); '
        'p=$(echo "$*" | sed -n "s/.*--process \\([^ ]*\\).*/\\1/p"); '
        f'cp "$c" "$p" {seen}/; '
    )
    fakes = install_fakes(
        monkeypatch, tmp_path / "bin", {"tilemaker": keep + TILEMAKER_OK, "ogr2ogr": OGR_OK}
    )
    _install_region(tmp_path, VERMONT)
    conv = _converter(tmp_path, [VERMONT])
    outcomes = _run(conv)
    assert conv.ledger.failed == {}, outcomes
    config = json.loads((seen / "config-infra.json").read_text())
    assert config["layers"]["infra"] == {"minzoom": 10, "maxzoom": 14}
    assert config["layers"]["place"] == json.loads(KIT_CONFIG)["layers"]["place"]
    lua = (seen / "process-infra.lua").read_text()
    kit = _data(tmp_path, "vector-map-kit")
    assert f"dofile([==[{kit / PROCESS}]==])" in lua
    assert len([line for _, line in calls(fakes) if line.startswith("tilemaker ")]) == 1


def test_a_kit_config_that_is_not_json_fails_the_region_by_name(
    tmp_path: Path, fakes: Path
) -> None:
    _install_region(tmp_path, VERMONT)
    conv = _converter(tmp_path, [VERMONT])
    (_data(tmp_path, "vector-map-kit") / CONFIG).write_text("stand-in")
    outcomes = _run(conv)
    assert "config-openmaptiles.json is not the profile's JSON" in " ".join(outcomes)
    assert not any(line.startswith("tilemaker ") for _, line in calls(fakes))


def test_the_clip_box_is_the_header_box_plus_a_margin_inside_the_globe() -> None:
    box = clip_box(VERMONT_BOX)
    assert box is not None
    west, south, east, north = box
    assert (west, south, east, north) == pytest.approx(
        (-73.44 - PAD, 42.72 - PAD, -71.46 + PAD, 45.02 + PAD)
    )
    assert clip_box((-180.0, 180.0, 90.0, -90.0)) == (-180.0, -90.0, 180.0, 90.0)
    assert clip_box((170.0, -170.0, 10.0, 0.0)) is None  # crosses the antimeridian


# -- a region, end to end -----------------------------------------------------------


def test_a_region_is_clipped_linked_converted_and_published(tmp_path: Path, fakes: Path) -> None:
    _install_region(tmp_path, VERMONT)
    conv = _converter(tmp_path, [VERMONT])
    outcomes = _run(conv)
    assert conv.ledger.failed == {}, outcomes
    dest = _data(tmp_path, "osm-pmtiles") / f"{VERMONT.slug}.pmtiles"
    assert dest.read_bytes().startswith(b"PMTiles")
    assert (dest.parent / f"{dest.name}.source").read_text() == f"260101\nconverter: {CONVERTER}\n"
    work = tmp_path / "staging" / "osm-pmtiles" / f"{VERMONT.slug}.work"
    ran = [(Path(where), line) for where, line in calls(fakes)]
    ogr = [line for where, line in ran if line.startswith("ogr2ogr ")]
    assert len(ogr) == 1 and all(where == work for where, _ in ran)
    assert "-clipsrc -73.540000 42.620000 -71.360000 45.120000" in ogr[0]
    assert ogr[0].endswith(
        f"coastline/water_polygons.shp {_data(tmp_path, 'vector-map-kit')}/{OCEAN}.shp"
    )
    tm = [line for _, line in ran if line.startswith("tilemaker ")]
    assert len(tm) == 1 and "--store" in tm[0]
    assert list(work.iterdir()) == []  # scratch cleared after the publish


def test_the_land_cover_layers_are_linked_where_the_profile_looks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pinned config names ``landcover/<layer>/<layer>.shp``; the fake
    tilemaker checks every part is there when it runs."""
    parts = " ".join(f"landcover/{layer}/{layer}.{p}" for layer in LANDCOVER for p in SHAPE_PARTS)
    check = f'for f in {parts} coastline/water_polygons.shp; do test -e "$f" || exit 9; done'
    install_fakes(
        monkeypatch, tmp_path / "bin", {"tilemaker": f"{check}; {TILEMAKER_OK}", "ogr2ogr": OGR_OK}
    )
    _install_region(tmp_path, VERMONT)
    conv = _converter(tmp_path, [VERMONT])
    _run(conv)
    assert conv.ledger.failed == {}


def test_a_header_without_a_box_uses_the_whole_ocean_and_says_so(
    tmp_path: Path, fakes: Path
) -> None:
    _install_region(tmp_path, VERMONT, pbf(None))
    conv = _converter(tmp_path, [VERMONT])
    outcomes = _run(conv)
    assert conv.ledger.failed == {}
    assert not [c for _, c in calls(fakes) if c.startswith("ogr2ogr")]
    assert any("whole" in o and "ocean" in o for o in outcomes)


def test_a_missing_kit_file_fails_the_region_by_name_before_anything_runs(
    tmp_path: Path, fakes: Path
) -> None:
    _install_region(tmp_path, VERMONT)
    conv = _converter(tmp_path, [VERMONT], skip=f"{OCEAN}.shx")
    _run(conv)
    assert f"{OCEAN}.shx" in conv.ledger.failed[f"osm-pmtiles:{VERMONT.slug}"]
    assert "hammunition install vector-map-kit" in conv.ledger.failed[f"osm-pmtiles:{VERMONT.slug}"]
    assert calls(fakes) == []


def test_tilemaker_exiting_zero_without_a_pmtiles_file_fails_the_region(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fakes(
        monkeypatch,
        tmp_path / "bin",
        {"tilemaker": f'{_OUT}; printf "SQLite format 3" > "$o"', "ogr2ogr": OGR_OK},
    )
    _install_region(tmp_path, VERMONT)
    _install_region(tmp_path, DELAWARE)
    conv = _converter(tmp_path, [VERMONT, DELAWARE])
    _run(conv)
    assert set(conv.ledger.failed) == {
        f"osm-pmtiles:{VERMONT.slug}",
        f"osm-pmtiles:{DELAWARE.slug}",
    }
    assert "PMTiles" in conv.ledger.failed[f"osm-pmtiles:{VERMONT.slug}"]
    assert not (_data(tmp_path, "osm-pmtiles") / f"{VERMONT.slug}.pmtiles").exists()


def test_a_failed_ocean_clip_fails_that_region_and_the_next_one_builds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ogr = f'case "$*" in *-73.54*) echo "ERROR 1: clip" >&2; exit 1;; esac; {OGR_OK}'
    install_fakes(monkeypatch, tmp_path / "bin", {"tilemaker": TILEMAKER_OK, "ogr2ogr": ogr})
    _install_region(tmp_path, VERMONT)
    _install_region(tmp_path, DELAWARE, pbf((-75.79, -74.96, 40.03, 38.45)))
    conv = _converter(tmp_path, [VERMONT, DELAWARE])
    _run(conv)
    assert list(conv.ledger.failed) == [f"osm-pmtiles:{VERMONT.slug}"]
    assert "ERROR 1: clip" in conv.ledger.failed[f"osm-pmtiles:{VERMONT.slug}"]
    assert (_data(tmp_path, "osm-pmtiles") / f"{DELAWARE.slug}.pmtiles").is_file()


def test_a_region_piece_one_failed_is_skipped(tmp_path: Path, fakes: Path) -> None:
    _install_region(tmp_path, VERMONT)
    regions = MapLedger()
    regions.fail(VERMONT.slug, "did not verify")
    conv = _converter(tmp_path, [VERMONT], regions=regions)
    outcomes = _run(conv)
    assert any(o.startswith("skipped") for o in outcomes)
    assert conv.ledger.failed == {} and calls(fakes) == []


def test_a_current_region_is_not_converted_again(tmp_path: Path, fakes: Path) -> None:
    _install_region(tmp_path, VERMONT)
    conv = _converter(tmp_path, [VERMONT])
    _run(conv)
    m = manifest()
    assert conv.pending(m, _block(m)) == []
    assert conv.steps(m, _block(m)) == []
    newer = _region("north-america/us/vermont", "260901")
    again = TilesConverter(prefix=tmp_path, files=[newer], staging=conv.staging)
    assert again.pending(m, _block(m)) == [newer]


def test_a_region_dropped_from_the_station_is_removed(tmp_path: Path, fakes: Path) -> None:
    _install_region(tmp_path, VERMONT)
    _run(_converter(tmp_path, [VERMONT]))
    m = manifest()
    later = TilesConverter(
        prefix=tmp_path, files=[], staging=Staging(tmp_path / "s", euid=NOT_ROOT)
    )
    steps = _actions(later.steps(m, _block(m)))
    assert [s.kind for s in steps] == ["remove-data"]
    steps[0].perform()
    assert not (_data(tmp_path, "osm-pmtiles") / f"{VERMONT.slug}.pmtiles").exists()


def test_the_step_says_what_it_runs_what_it_costs_and_that_it_is_measured_once(
    tmp_path: Path,
) -> None:
    conv = _converter(tmp_path, [VERMONT])
    m = manifest()
    convert = _actions(conv.steps(m, _block(m)))[0]
    assert convert.kind == "convert"
    for words in ("tilemaker --input", "ogr2ogr", "Natural Earth", "measured on one region"):
        assert words in convert.description


def test_the_ledger_fails_the_run_naming_every_failure() -> None:
    ledger = TilesLedger()
    assert ledger.check() == "every vector-tile map installed"
    ledger.fail("osm-pmtiles:a", "a: no")
    ledger.fail("osm-pmtiles:b", "b: no")
    with pytest.raises(BackendError, match=r"2 vector-tile map\(s\)"):
        ledger.check()
    assert ledger.step().kind == "check-vector-tiles"


# -- the run: disk and idleness -------------------------------------------------------


def test_the_run_counts_the_largest_scratch_and_every_output(tmp_path: Path) -> None:
    from hammunition.backends.pmtiles import FACTOR, SCRATCH_FACTOR
    from hammunition.distro import Target
    from hammunition.plan import InstallPlan, PlannedPackage
    from hammunition.tiles_plan import build_tiles_run

    m = manifest()
    plan = InstallPlan(
        target=Target(distro="debian", version="13", arch="x86_64"),
        packages=(PlannedPackage(manifest=m, block=m.install[0], apt_packages=()),),
    )
    big = RegionFile("north-america/us/vermont", "260101", "https://x/v", 1000, "a" * 64, None)
    small = RegionFile("north-america/us/delaware", "260101", "https://x/d", 10, "b" * 64, None)
    run = build_tiles_run(
        prefix=tmp_path / "p",
        builds=tmp_path / "b",
        owner=None,
        runner=None,
        files=[big, small],
        keep=frozenset(),
        regions=MapLedger(),
    )
    needs = run.needs(plan, prefix=tmp_path / "p")
    # Scratch and the staged output of the largest region, both in staging.
    assert needs[tmp_path / "b" / "osm-pmtiles"] == round((SCRATCH_FACTOR + FACTOR) * 1000)
    assert needs[tmp_path / "p"] == round(1000 * FACTOR) + round(10 * FACTOR)
    assert run.idle(plan) == frozenset()
    assert set(run.converters) == {"tilemaker-pmtiles"}
