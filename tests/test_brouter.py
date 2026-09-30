# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""BRouter's routing files from every region, with elevation.  D-063.

Synthetic regions and tiles only; fakes stand in for ``java``, ``osmium``,
``gdalbuildvrt`` and ``gdalwarp``. The real map creator was run on a
synthetic region with the argv these tests pin (D-063, measured 2026-09-29).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest

from fake_tools import calls, install_fakes
from hammunition.backends import Action, Command
from hammunition.backends.base import BackendError
from hammunition.backends.brouter import (
    CONVERTER,
    RECORD,
    BRouterConverter,
    hgt_name,
    render_record,
    square_of_tile,
    srtm_name,
    warp_argv,
    window_tiles,
)
from hammunition.backends.dem import DemResolution, RegionTiles
from hammunition.backends.regions import MapLedger
from hammunition.backends.staging import Staging
from hammunition.geofabrik import RegionFile
from hammunition.manifest.schema import DerivedDataInstall, PackageManifest

BODY = b"p" * 10
JAR = "brouter-1.7.10-all.jar"
#: The Copernicus tile over Wilmington, Delaware, a public example.
DELAWARE_TILE = "Copernicus_DSM_COG_10_N39_00_W076_00_DEM"
#: A tile in the same 5x5 square's ring, one degree west of it.
RING_TILE = "Copernicus_DSM_COG_10_N39_00_W081_00_DEM"


def _region(name: str) -> RegionFile:
    return RegionFile(
        f"atlantis/{name}",
        "260101",
        f"https://download.geofabrik.de/atlantis/{name}-260101.osm.pbf",
        10,
        hashlib.sha256(BODY).hexdigest(),
        None,
    )


OCEANIA, LEMURIA = _region("oceania"), _region("lemuria")

#: Each map-creator class writes what the next phase reads; FAIL_ON makes the
#: run whose argv contains it fail; RD5 names the routing files the linker writes.
JAVA = """
case "$*" in *"${FAIL_ON:-no-such-thing}"*) echo "java failed: $FAIL_ON" >&2; exit 1 ;; esac
for a; do case "$a" in btools.*) cls=$a ;; esac; done
while [ "$1" != "$cls" ]; do shift; done; shift
case "$cls" in
  *ElevationRasterTileConverter) ls "$2" | grep -q hgt && printf bef > "$3/$1.bef" ;;
  *OsmFastCutter) [ -n "${NO_NODES:-}" ] || printf n > "$4/W80_N35.n5d"; printf w > "$5/W80_N35.wt5"; printf r > "$7" ;;
  *PosUnifier) printf u > "$2/W80_N35.u5d"; printf b > "$4" ;;
  *WayLinker) for s in ${RD5-W80_N35 W75_N35}; do printf "seg-$s" > "$7/$s.rd5"; done ;;
esac
"""
OSMIUM = """
while [ "$1" != "-o" ]; do shift; done
printf merged > "$2"
"""
GDALBUILDVRT = 'printf vrt > "$2"'
GDALWARP = 'for a; do last=$a; done; printf hgt > "$last"'
TOOLS = {"java": JAVA, "osmium": OSMIUM, "gdalbuildvrt": GDALBUILDVRT, "gdalwarp": GDALWARP}

NOT_ROOT = 4242


def manifest(*, elevation: bool = True) -> PackageManifest:
    block: dict[str, Any] = {
        "method": "derived",
        "converter": "brouter-mapcreator",
        "source": "osm-regions",
        "program": "brouter",
        "profiles": "brouter-mapcreator-profiles",
        "licence": "ODbL-1.0",
        "licence_url": "https://www.openstreetmap.org/copyright",
    }
    depends = ["osm-regions", "brouter", "brouter-mapcreator-profiles"]
    if elevation:
        block["elevation"] = "dem-copernicus"
        depends.append("dem-copernicus")
    return PackageManifest.model_validate(
        {
            "name": "brouter-segments",
            "version": "station",
            "summary": "BRouter routing files for a test",
            "categories": ["navigation-maps"],
            "depends": depends,
            "install": [{"install": block}],
            "update": {"probe": {"method": "none"}},
            "documentation": {
                "what_it_does": "Routing files for a test, nothing more.",
                "why_you_want_it": "Because the test suite needs a manifest.",
                "upstream_url": "https://github.com/abrensch/brouter",
            },
        }
    )


def _block(m: PackageManifest) -> DerivedDataInstall:
    block = m.install[0].install
    assert isinstance(block, DerivedDataInstall)
    return block


def _data(prefix: Path, unit: str) -> Path:
    return prefix / "share" / "hammunition" / "data" / unit


def _tree(prefix: Path) -> Path:
    return prefix / "share" / "hammunition" / "brouter"


def _install_inputs(prefix: Path, *, jar: bool = True, brf: bool = True) -> None:
    tree = _tree(prefix)
    (tree / "profiles2").mkdir(parents=True)
    if jar:
        (tree / JAR).write_bytes(b"jar")
    (tree / "profiles2" / "lookups.dat").write_text("lookups")
    (tree / "profiles2" / "trekking.brf").write_text("trekking")
    profiles = _data(prefix, "brouter-mapcreator-profiles")
    profiles.mkdir(parents=True)
    if brf:
        (profiles / "all.brf").write_text("all")
        (profiles / "softaccess.brf").write_text("softaccess")


def _install_region(prefix: Path, region: RegionFile) -> Path:
    out = _data(prefix, "osm-regions")
    out.mkdir(parents=True, exist_ok=True)
    pbf = out / f"{region.slug}.osm.pbf"
    pbf.write_bytes(BODY)
    return pbf


def _install_tile(prefix: Path, name: str) -> Path:
    out = _data(prefix, "dem-copernicus")
    out.mkdir(parents=True, exist_ok=True)
    tile = out / f"{name}.tif"
    tile.write_bytes(b"tif")
    return tile


def _resolution(*tiles: str) -> DemResolution:
    return DemResolution(regions=(RegionTiles("atlantis/oceania", "atlantis-oceania", tiles, 0),))


def _converter(
    tmp_path: Path, files: list[RegionFile], tiles: tuple[str, ...] = (), **kw: Any
) -> BRouterConverter:
    return BRouterConverter(
        prefix=tmp_path,
        files=files,
        resolution=_resolution(*tiles),
        staging=Staging(tmp_path / "staging", euid=NOT_ROOT),
        euid=NOT_ROOT,
        privileged=False,
        **kw,
    )


def _run(conv: BRouterConverter, m: PackageManifest | None = None) -> list[str]:
    m = m or manifest()
    steps = conv.steps(m, _block(m))
    assert all(isinstance(s, Action) for s in steps)
    return [s.perform() for s in steps if isinstance(s, Action)]


def _work(tmp_path: Path) -> Path:
    return tmp_path / "staging" / "brouter.work"


# ---------------------------------------------------------------------------
# Names, mirrored from the map creator's own Java
# ---------------------------------------------------------------------------


def test_delawares_tile_is_in_the_square_brouter_calls_srtm_21_05() -> None:
    assert square_of_tile(DELAWARE_TILE) == (35, -80)
    assert srtm_name(35, -80) == "srtm_21_05"
    assert hgt_name(DELAWARE_TILE) == "N39W076.hgt"


@pytest.mark.parametrize(
    ("square", "name"),
    [
        ((-10, 15), "srtm_40_14"),  # southern hemisphere, east
        ((60, -150), "srtm_07_00"),
        ((65, -150), "srtm_07_-1"),  # north of 65: PosUnifier's own "-1"
        ((70, -165), "srtm_04_-2"),
    ],
)
def test_srtm_names_match_posunifier_everywhere(square: tuple[int, int], name: str) -> None:
    assert srtm_name(*square) == name


def test_a_southern_western_tile_names_its_hgt_by_its_south_west_corner() -> None:
    assert hgt_name("Copernicus_DSM_COG_10_S01_00_W078_00_DEM") == "S01W078.hgt"
    assert square_of_tile("Copernicus_DSM_COG_10_S01_00_W078_00_DEM") == (-5, -80)


def test_the_window_is_the_square_and_its_one_degree_ring() -> None:
    wanted = (DELAWARE_TILE, RING_TILE, "Copernicus_DSM_COG_10_N33_00_W076_00_DEM")
    assert window_tiles((35, -80), wanted) == (DELAWARE_TILE, RING_TILE)


def test_warp_samples_one_tile_at_one_arc_second_with_half_a_second_of_border() -> None:
    argv = warp_argv(Path("/w/window.vrt"), Path("/w/hgt/N39W076.hgt"), DELAWARE_TILE)
    assert argv == [
        "gdalwarp",
        "-q",
        "--config",
        "GDAL_PAM_ENABLED",
        "NO",
        "-te",
        "-76.000138889",
        "38.999861111",
        "-74.999861111",
        "40.000138889",
        "-ts",
        "3601",
        "3601",
        "-ot",
        "Int16",
        "-of",
        "SRTMHGT",
        "/w/window.vrt",
        "/w/hgt/N39W076.hgt",
    ]


# ---------------------------------------------------------------------------
# The build
# ---------------------------------------------------------------------------


def test_one_region_with_elevation_builds_and_installs_every_routing_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = install_fakes(monkeypatch, tmp_path / "bin", TOOLS)
    _install_inputs(tmp_path)
    pbf = _install_region(tmp_path, OCEANIA)
    tile = _install_tile(tmp_path, DELAWARE_TILE)
    conv = _converter(tmp_path, [OCEANIA], (DELAWARE_TILE,))
    outcomes = _run(conv)
    assert conv.ledger.failed == {}, outcomes
    work = _work(tmp_path)
    jar = _tree(tmp_path) / JAR
    p2 = _tree(tmp_path) / "profiles2"
    brf = _data(tmp_path, "brouter-mapcreator-profiles")
    run = [c for _, c in calls(log)]
    assert not any(c.startswith("osmium") for c in run), "one region is read as it is"
    assert run[0] == f"gdalbuildvrt -q {work}/window.vrt {tile}"
    assert run[1].startswith("gdalwarp -q --config GDAL_PAM_ENABLED NO -te -76.000138889")
    assert run[1].endswith(f"{work}/window.vrt {work}/hgt/N39W076.hgt")
    heap = "java -Xmx4000m"
    assert run[2:] == [
        f"{heap} -cp {jar} btools.mapcreator.ElevationRasterTileConverter "
        f"srtm_21_05 {work}/hgt {work}/bef 1",
        f"{heap} -DavoidMapPolling=true -DuseDenseMaps=true -Ddeletetmpfiles=true -cp {jar} "
        f"btools.mapcreator.OsmFastCutter {p2}/lookups.dat {work}/nodetiles {work}/waytiles "
        f"{work}/nodes55 {work}/waytiles55 {work}/bordernids.dat {work}/relations.dat "
        f"{work}/restrictions.dat {brf}/all.brf {p2}/trekking.brf {brf}/softaccess.brf {pbf}",
        f"{heap} -DuseDenseMaps=true -Ddeletetmpfiles=true -cp {jar} "
        f"btools.mapcreator.PosUnifier {work}/nodes55 {work}/unodes55 {work}/bordernids.dat "
        f"{work}/bordernodes.dat {work}/bef",
        f"{heap} -DuseDenseMaps=true -DskipEncodingCheck=true -cp {jar} "
        f"btools.mapcreator.WayLinker {work}/unodes55 {work}/waytiles55 "
        f"{work}/bordernodes.dat {work}/restrictions.dat {p2}/lookups.dat {brf}/all.brf "
        f"{work}/segments rd5",
    ]
    assert {where for where, _ in calls(log)} == {str(work)}
    out = _data(tmp_path, "brouter-segments")
    assert (out / "W80_N35.rd5").read_bytes() == b"seg-W80_N35"
    assert (out / "W75_N35.rd5").read_bytes() == b"seg-W75_N35"
    assert (out / RECORD).read_text() == (
        f"atlantis-oceania 260101\nelevation {DELAWARE_TILE}\nprogram {JAR}\n"
        f"segment W75_N35.rd5\nsegment W80_N35.rd5\nconverter: {CONVERTER}\n"
    )
    assert list(work.iterdir()) == [], "the scratch is cleared, the directory kept"


def test_two_regions_are_merged_into_one_input_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = install_fakes(monkeypatch, tmp_path / "bin", TOOLS)
    _install_inputs(tmp_path)
    one, two = _install_region(tmp_path, OCEANIA), _install_region(tmp_path, LEMURIA)
    conv = _converter(tmp_path, [OCEANIA, LEMURIA])
    _run(conv, manifest(elevation=False))
    assert conv.ledger.failed == {}
    work = _work(tmp_path)
    run = [c for _, c in calls(log)]
    assert run[0] == f"osmium merge {one} {two} -o {work}/merged.osm.pbf --overwrite"
    cutter = next(c for c in run if "OsmFastCutter" in c)
    assert cutter.endswith(f"{work}/merged.osm.pbf")
    assert not any(c.startswith("gdal") for c in run), "no elevation block, no elevation"
    record = (_data(tmp_path, "brouter-segments") / RECORD).read_text()
    assert record.startswith("atlantis-lemuria 260101\natlantis-oceania 260101\nprogram ")
    assert "elevation" not in record


def test_with_no_tile_installed_the_build_runs_flat_with_an_empty_bef_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = install_fakes(monkeypatch, tmp_path / "bin", TOOLS)
    _install_inputs(tmp_path)
    _install_region(tmp_path, OCEANIA)
    conv = _converter(tmp_path, [OCEANIA], (DELAWARE_TILE,))  # wanted, not on disk
    outcomes = _run(conv)
    assert conv.ledger.failed == {}, outcomes
    assert not any(c.startswith("gdal") for _, c in calls(log))
    assert any("no terrain tile is installed" in o for o in outcomes)
    record = (_data(tmp_path, "brouter-segments") / RECORD).read_text()
    assert "elevation" not in record


def test_the_build_is_current_until_a_region_tile_jar_or_converter_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fakes(monkeypatch, tmp_path / "bin", TOOLS)
    _install_inputs(tmp_path)
    _install_region(tmp_path, OCEANIA)
    _install_tile(tmp_path, DELAWARE_TILE)
    m = manifest()
    _run(_converter(tmp_path, [OCEANIA], (DELAWARE_TILE,)), m)
    assert _converter(tmp_path, [OCEANIA], (DELAWARE_TILE,)).pending(m, _block(m)) == []
    assert _converter(tmp_path, [OCEANIA], (DELAWARE_TILE,)).steps(m, _block(m)) == []
    newer = RegionFile(**{**OCEANIA.__dict__, "snapshot": "260901"})
    assert _converter(tmp_path, [newer], (DELAWARE_TILE,)).pending(m, _block(m))
    assert _converter(tmp_path, [OCEANIA], (DELAWARE_TILE, RING_TILE)).pending(m, _block(m))
    assert _converter(tmp_path, [OCEANIA, LEMURIA], (DELAWARE_TILE,)).pending(m, _block(m))
    (_tree(tmp_path) / JAR).rename(_tree(tmp_path) / "brouter-1.7.11-all.jar")
    assert _converter(tmp_path, [OCEANIA], (DELAWARE_TILE,)).pending(m, _block(m))


def test_a_record_from_an_older_converter_rebuilds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fakes(monkeypatch, tmp_path / "bin", TOOLS)
    _install_inputs(tmp_path)
    _install_region(tmp_path, OCEANIA)
    out = _data(tmp_path, "brouter-segments")
    out.mkdir(parents=True)
    (out / "W80_N35.rd5").write_bytes(b"old")
    record = render_record(["atlantis-oceania 260101"], (), JAR, ["W80_N35.rd5"])
    (out / RECORD).write_text(record.replace(CONVERTER, "brouter-mapcreator 0"))
    m = manifest(elevation=False)
    assert _converter(tmp_path, [OCEANIA]).pending(m, _block(m))


def test_a_missing_segment_file_rebuilds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_fakes(monkeypatch, tmp_path / "bin", TOOLS)
    _install_inputs(tmp_path)
    _install_region(tmp_path, OCEANIA)
    m = manifest(elevation=False)
    _run(_converter(tmp_path, [OCEANIA]), m)
    (_data(tmp_path, "brouter-segments") / "W75_N35.rd5").unlink()
    assert _converter(tmp_path, [OCEANIA]).pending(m, _block(m))


def test_a_routing_file_no_longer_built_is_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fakes(monkeypatch, tmp_path / "bin", TOOLS)
    _install_inputs(tmp_path)
    _install_region(tmp_path, OCEANIA)
    m = manifest(elevation=False)
    _run(_converter(tmp_path, [OCEANIA]), m)
    monkeypatch.setenv("RD5", "W80_N35")
    newer = RegionFile(**{**OCEANIA.__dict__, "snapshot": "260901"})
    conv = _converter(tmp_path, [newer])
    _run(conv, m)
    assert conv.ledger.failed == {}
    out = _data(tmp_path, "brouter-segments")
    assert sorted(p.name for p in out.iterdir()) == sorted([RECORD, "W80_N35.rd5"])


@pytest.mark.parametrize(
    ("fail_on", "phase"),
    [
        ("ElevationRasterTileConverter", "elevation"),
        ("OsmFastCutter", "OsmFastCutter"),
        ("PosUnifier", "PosUnifier"),
        ("WayLinker", "WayLinker"),
    ],
)
def test_a_failed_phase_fails_the_build_by_name_and_keeps_the_installed_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fail_on: str, phase: str
) -> None:
    monkeypatch.setenv("FAIL_ON", fail_on)
    log = install_fakes(monkeypatch, tmp_path / "bin", TOOLS)
    _install_inputs(tmp_path)
    _install_region(tmp_path, OCEANIA)
    _install_tile(tmp_path, DELAWARE_TILE)
    out = _data(tmp_path, "brouter-segments")
    out.mkdir(parents=True)
    (out / "W80_N35.rd5").write_bytes(b"old")
    conv = _converter(tmp_path, [OCEANIA], (DELAWARE_TILE,))
    outcomes = _run(conv)
    message = conv.ledger.failed["brouter-segments"]
    assert phase in message and "java failed" in message
    assert outcomes[-1].startswith("skipped")
    assert (out / "W80_N35.rd5").read_bytes() == b"old"
    later = [c for _, c in calls(log)]
    assert later[-1].count(fail_on) == 1, "nothing ran after the failed phase"
    assert list(_work(tmp_path).iterdir()) == []


def test_a_linker_that_writes_no_routing_file_fails_the_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RD5", "")
    install_fakes(monkeypatch, tmp_path / "bin", TOOLS)
    _install_inputs(tmp_path)
    _install_region(tmp_path, OCEANIA)
    conv = _converter(tmp_path, [OCEANIA])
    _run(conv, manifest(elevation=False))
    assert "no routing file" in conv.ledger.failed["brouter-segments"]


def test_a_cutter_that_writes_no_node_tiles_fails_the_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NO_NODES", "1")
    log = install_fakes(monkeypatch, tmp_path / "bin", TOOLS)
    _install_inputs(tmp_path)
    _install_region(tmp_path, OCEANIA)
    conv = _converter(tmp_path, [OCEANIA])
    _run(conv, manifest(elevation=False))
    assert "OsmFastCutter" in conv.ledger.failed["brouter-segments"]
    assert not any("PosUnifier" in c for _, c in calls(log))


@pytest.mark.parametrize(
    ("jar", "brf", "named"), [(False, True, "brouter-*-all.jar"), (True, False, "all.brf")]
)
def test_a_missing_jar_or_filter_fails_by_name_before_anything_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, jar: bool, brf: bool, named: str
) -> None:
    log = install_fakes(monkeypatch, tmp_path / "bin", TOOLS)
    _install_inputs(tmp_path, jar=jar, brf=brf)
    _install_region(tmp_path, OCEANIA)
    conv = _converter(tmp_path, [OCEANIA])
    _run(conv, manifest(elevation=False))
    assert named in conv.ledger.failed["brouter-segments"]
    assert calls(log) == []


def test_a_region_that_did_not_install_skips_the_build_without_double_reporting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = install_fakes(monkeypatch, tmp_path / "bin", TOOLS)
    _install_inputs(tmp_path)
    _install_region(tmp_path, OCEANIA)
    regions = MapLedger()
    regions.fail(LEMURIA.slug, "atlantis/lemuria: md5 did not match")
    conv = _converter(tmp_path, [OCEANIA, LEMURIA], regions=regions)
    outcomes = _run(conv, manifest(elevation=False))
    assert conv.ledger.failed == {}
    assert all(o.startswith("skipped") for o in outcomes)
    assert calls(log) == []


def test_a_publish_failing_partway_leaves_the_previous_set_whole(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fakes(monkeypatch, tmp_path / "bin", TOOLS)
    _install_inputs(tmp_path)
    _install_region(tmp_path, OCEANIA)
    out = _data(tmp_path, "brouter-segments")
    out.mkdir(parents=True)
    (out / "W80_N35.rd5").write_bytes(b"old")
    (out / RECORD).write_text("old record\n")
    real = Staging.publish
    count = {"n": 0}

    def publish(self: Staging, staged: Path, dest: Path, **kw: Any) -> None:
        count["n"] += 1
        if count["n"] == 2:
            raise BackendError(f"{dest}: no space left on device")
        real(self, staged, dest, **kw)

    monkeypatch.setattr(Staging, "publish", publish)
    conv = _converter(tmp_path, [OCEANIA])
    _run(conv, manifest(elevation=False))
    assert "no space left on device" in conv.ledger.failed["brouter-segments"]
    assert sorted(p.name for p in out.iterdir()) == sorted([RECORD, "W80_N35.rd5"])
    assert (out / "W80_N35.rd5").read_bytes() == b"old"
    assert (out / RECORD).read_text() == "old record\n"


def test_the_plan_text_names_every_phase_and_says_brouter_de_is_not_used(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_inputs(tmp_path)
    _install_region(tmp_path, OCEANIA)
    _install_region(tmp_path, LEMURIA)
    m = manifest()
    steps = _converter(tmp_path, [OCEANIA, LEMURIA], (DELAWARE_TILE,)).steps(m, _block(m))
    text = "\n".join(s.description for s in steps if isinstance(s, Action | Command))
    for phrase in (
        "osmium merge",
        "srtm_21_05",
        "OsmFastCutter",
        "PosUnifier",
        "WayLinker",
        "as the operator",
        "never downloaded from brouter.de",
    ):
        assert phrase in text, phrase
