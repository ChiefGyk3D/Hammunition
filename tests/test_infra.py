# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The infrastructure layers: OpenStreetMap's tag sets, the writers and the
store.  D-075.

Every object is synthetic (``Testville``, near the Delaware example the
spike measured). osmium is stubbed except where a test says it runs the
real one; no GUI starts and nothing is fetched.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import stat
import subprocess
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

import pytest

from hammunition import infra
from hammunition.infra import (
    LAYERS,
    OSM_LAYERS,
    SHELTER_NOTE,
    InfraLayer,
    Point,
    geojson_text,
    gpx_text,
    navit_text,
    read_osm_xml,
)
from test_osm_pbf import pbf

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "infra" / "osm-infra.osm"

#: QMapShack 1.17.1's built-in waypoint symbols: every distinct name
#: ``helpers/CWptIconManager.cpp`` assigns (the source D-064 measured
#: ``Tall Tower`` from). A name outside it is drawn as ``Default``.
QMS_SYMBOLS = frozenset(
    (
        "1st Category", "2nd Category", "3rd Category", "4th Category", "Airport", "Bank",
        "Bar", "Beach", "Block, Blue", "Block, Green", "Block, Red", "Blue Diamond",
        "Boat Ramp", "Campground", "Car Rental", "Car Repair", "Church", "City (Capitol)",
        "City Hall", "City (Large)", "City (Medium)", "City (Small)", "Convenience Store",
        "Dam", "Danger", "Default", "Department Store", "Drinking Water", "End", "Fast Food",
        "First Aid", "Fitness Center", "Flag, Blue", "Flag, Green", "Flag, Red", "Food",
        "Forest", "Gas Station", "Generic", "Ghost Town", "Green Diamond",
        "Ground Transportation", "Heliport", "Hors Category", "Information", "Left",
        "LeftFork", "Library", "Live Theater", "Lodge", "Lodging", "Medical Facility",
        "MiddleFork", "Mine", "Museum", "Parking Area", "Parking, Pay", "Pharmacy",
        "Picnic Area", "Pin, Blue", "Pin, Green", "Pin, Red", "Pizza", "Post Office",
        "Railway", "Red Diamond", "Residence", "Restaurant", "Restroom", "Right", "RightFork",
        "RV Park", "Scales", "Scenic Area", "School", "SharpLeft", "SharpRight", "Shipwreck",
        "Shopping Center", "Short Tower", "SlightLeft", "SlightRight", "Sprint", "Stadium",
        "Start", "Straight", "Summit", "Swimming Area", "Tall Tower", "Telephone",
        "Trailhead", "UTurn", "Valley", "Water", "Waypoint", "Winery", "Zoo",
    )
)  # fmt: skip
#: The icons the navit package (0.5.6) ships in /usr/share/navit/icons/.
NAVIT_ICONS = frozenset(
    (
        "hospital.png", "firebrigade.png", "shopping.png", "townhall.png", "airport.png",
        "danger.png", "communication.png", "drinking_water.png", "tower.png",
        "information.png",
    )
)  # fmt: skip


def _read(*wanted: str) -> infra.OsmRead:
    return read_osm_xml(FIXTURE.read_text(), wanted=wanted or tuple(OSM_LAYERS))


def _names(points: list[Point]) -> list[str]:
    return [p.name for p in points]


# --- the tag sets -------------------------------------------------------------------


def test_the_eight_layers_are_the_spikes_and_in_its_order() -> None:
    assert tuple(OSM_LAYERS) == (
        "medical",
        "responders",
        "supply",
        "shelter-candidates",
        "transport",
        "power",
        "telecom",
        "water",
    )


def test_each_object_lands_in_its_layer() -> None:
    got = _read()
    assert _names(got.points["medical"]) == [
        "Testville General Hospital",
        "Pharmacy",
        "Testville Clinic",
    ]
    assert _names(got.points["responders"]) == [
        "Testville Police",
        "Testville Ambulance",
        "Testville Fire Company",
    ]
    assert _names(got.points["supply"]) == ["TestFuel", "Testville Market"]
    assert _names(got.points["shelter-candidates"]) == [
        "Testville Elementary",
        "Place of worship",
        "Testville Town Hall",
    ]
    assert _names(got.points["transport"]) == ["Helipad", "Testville Halt", "Testville Airport"]
    assert _names(got.points["power"]) == ["Substation", "Testville Solar"]
    assert _names(got.points["telecom"]) == ["Communications mast", "Communications mast"]
    assert _names(got.points["water"]) == ["Water tower", "Testville Wastewater"]


def test_what_the_spike_ruled_out_lands_nowhere() -> None:
    """amenity=shelter (a picnic shelter), a mast with no communication
    tag, a rooftop generator and a hydrant are not POIs."""
    got = _read()
    every = [p for points in got.points.values() for p in points]
    where = {(round(p.lat, 4), round(p.lon, 4)) for p in every}
    for lat, lon in ((38.7707, -75.5707), (38.8617, -75.6617), (38.9024, -75.4024)):
        assert (lat, lon) not in where
    assert (38.9125, -75.4125) not in where


def test_a_way_is_placed_at_its_nodes_and_a_relation_at_its_ways_nodes() -> None:
    got = _read("medical", "responders")
    clinic = got.points["medical"][2]
    # The closing node is not counted twice (D-074's rule for a way).
    assert (clinic.lat, clinic.lon) == pytest.approx((38.601, -75.401))
    fire = got.points["responders"][2]
    assert (fire.lat, fire.lon) == pytest.approx((38.6506667, -75.4513333))


def test_an_object_with_no_position_is_skipped_by_reading_number_never_by_id() -> None:
    got = _read("medical")
    assert got.read == 4
    assert got.skipped == {infra.NO_POSITION: [4]}


def test_only_the_wanted_layers_are_read() -> None:
    got = _read("water")
    assert set(got.points) == {"water"}
    assert got.read == 2


def test_details_carry_what_an_operator_needs() -> None:
    got = _read()
    hospital = got.points["medical"][0]
    assert "emergency department" in hospital.details
    fuel = got.points["supply"][0]
    assert fuel.kind == "fuel" and "diesel" in fuel.details
    substation = got.points["power"][0]
    assert "voltage 69 kV, 12.47 kV" in substation.details
    assert "operator Test Power" in substation.details


def test_every_shelter_candidate_says_it_is_not_a_designated_shelter() -> None:
    got = _read("shelter-candidates")
    for point in got.points["shelter-candidates"]:
        assert SHELTER_NOTE in point.description("OpenStreetMap")
    assert SHELTER_NOTE == "candidate, not a designated shelter"
    assert SHELTER_NOTE in infra.osm_layer_name("shelter-candidates", date(2026, 9, 30))


def test_a_doctype_is_refused() -> None:
    with pytest.raises(infra.InfraInputError, match="DOCTYPE"):
        read_osm_xml('<!DOCTYPE x [<!ENTITY a "b">]><osm/>', wanted=("medical",))


def test_osmium_is_asked_for_every_wanted_layers_keys_in_one_run(tmp_path: Path) -> None:
    argv = infra.osmium_argv(tmp_path / "x.osm.pbf", tmp_path / "out.osm", ("medical", "telecom"))
    assert argv[:3] == ["osmium", "tags-filter", str(tmp_path / "x.osm.pbf")]
    assert "nwr/amenity=hospital,clinic,doctors,pharmacy" in argv
    assert "nwr/man_made=mast,tower,communications_tower" in argv
    assert "nwr/tower:type=communication" in argv
    assert argv[-5:] == ["-f", "osm", "-o", str(tmp_path / "out.osm"), "--overwrite"]


# --- the layer table ---------------------------------------------------------------


def test_every_layer_has_a_builtin_symbol_a_navit_icon_and_its_own_type() -> None:
    assert list(LAYERS) == [
        *(f"osm-{k}" for k in OSM_LAYERS),
        "faa-airports",
        "eia-plants",
        "wri-plants",
        "fcc-towers",
        "nwr",
    ]
    types = [spec.navit_type for spec in LAYERS.values()]
    assert len(set(types)) == len(types)
    assert "poi_custom0" not in types  # the repeaters'
    for spec in LAYERS.values():
        assert spec.symbol in QMS_SYMBOLS, spec
        assert Path(spec.navit_icon).name in NAVIT_ICONS, spec
        assert spec.navit_icon.startswith("/usr/share/navit/icons/")
        assert spec.navit_type.startswith("poi_custom")


# --- the writers -------------------------------------------------------------------


def _layer(points: tuple[Point, ...] | None = None) -> InfraLayer:
    got = _read("medical")
    return InfraLayer(
        layer_id="osm-medical",
        name="Medical (OpenStreetMap, ODbL, 2026-09-30)",
        licence=infra.OSM_LICENCE,
        source="OpenStreetMap contributors, ODbL",
        day=date(2026, 9, 30),
        points=points if points is not None else tuple(got.points["medical"]),
    )


def test_the_gpx_names_the_layer_and_each_point_with_the_layers_symbol() -> None:
    root = ET.fromstring(gpx_text(_layer()))
    ns = {"g": "http://www.topografix.com/GPX/1/1"}
    assert root.findtext("g:metadata/g:name", namespaces=ns) == (
        "Medical (OpenStreetMap, ODbL, 2026-09-30)"
    )
    assert root.findtext("g:metadata/g:desc", namespaces=ns) == infra.OSM_LICENCE
    wpts = root.findall("g:wpt", ns)
    assert wpts[0].findtext("g:name", namespaces=ns) == "Testville General Hospital"
    assert {w.findtext("g:sym", namespaces=ns) for w in wpts} == {"Medical Facility"}
    assert {w.findtext("g:type", namespaces=ns) for w in wpts} == {"osm-medical"}
    desc = wpts[0].findtext("g:desc", namespaces=ns) or ""
    assert desc.startswith("hospital; emergency department")
    assert desc.endswith("Source: OpenStreetMap contributors, ODbL")


def test_the_licence_line_is_exact() -> None:
    assert infra.OSM_LICENCE == "© OpenStreetMap contributors, ODbL 1.0"


def test_the_navit_textfile_uses_the_layers_type_and_icon() -> None:
    lines = navit_text(_layer()).splitlines()
    assert len(lines) == 3
    spec = LAYERS["osm-medical"]
    assert lines[0] == (
        f'-75.51010 38.71010 type={spec.navit_type} label="Testville General Hospital" '
        f'icon_src="{spec.navit_icon}"'
    )


def test_the_geojson_is_a_feature_collection_with_the_licence() -> None:
    data = json.loads(geojson_text(_layer()))
    assert data["type"] == "FeatureCollection"
    assert data["name"] == "Medical (OpenStreetMap, ODbL, 2026-09-30)"
    assert data["licence"] == infra.OSM_LICENCE
    assert data["layer"] == "osm-medical"
    first = data["features"][0]
    assert first["geometry"] == {"type": "Point", "coordinates": [-75.5101, 38.7101]}
    assert first["properties"]["name"] == "Testville General Hospital"
    assert first["properties"]["kind"] == "hospital"


# --- the store ---------------------------------------------------------------------


def test_a_layer_is_four_files_0600_in_a_0700_directory(tmp_path: Path) -> None:
    where = tmp_path / "overlays" / "infra"
    written = infra.write_layer(where, _layer())
    assert [p.name for p in written] == [
        "infra-osm-medical.gpx",
        "infra-osm-medical.poi",
        "infra-osm-medical.navit.txt",
        "infra-osm-medical.geojson",
    ]
    assert stat.S_IMODE(os.stat(where).st_mode) == 0o700
    for path in written:
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    db = sqlite3.connect(written[1])
    assert db.execute("SELECT name FROM poi_categories WHERE id=1").fetchone() == (
        LAYERS["osm-medical"].category,
    )
    data = db.execute("SELECT data FROM poi_data WHERE id=1").fetchone()[0]
    assert data.split("\r")[2] == "hammunition:infra=osm-medical"
    assert infra.present_layers(where) == ("osm-medical",)


def test_writing_one_layer_leaves_the_others(tmp_path: Path) -> None:
    where = tmp_path / "infra"
    infra.write_layer(where, _layer())
    water = InfraLayer(
        "osm-water",
        "Water",
        infra.OSM_LICENCE,
        "OSM",
        date(2026, 9, 30),
        (Point("W", "water tower", 38.7, -75.5),),
    )
    infra.write_layer(where, water)
    assert infra.present_layers(where) == ("osm-medical", "osm-water")


def test_an_empty_layer_is_refused_by_the_writer(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no point"):
        infra.write_layer(tmp_path / "infra", _layer(points=()))


def test_remove_one_layer_then_all_and_the_empty_directory(tmp_path: Path) -> None:
    where = tmp_path / "infra"
    infra.write_layer(where, _layer())
    other = InfraLayer(
        "nwr", "NWR", "x", "NWS", date(2026, 10, 1), (Point("WXJ00", "transmitter", 38.7, -75.5),)
    )
    infra.write_layer(where, other)
    (where / "notes.txt").write_text("the operator's")
    removed = infra.remove_layer(where, "osm-medical")
    assert len(removed) == 4 and infra.present_layers(where) == ("nwr",)
    removed = infra.remove_layer(where, None)
    assert removed[0].name == "infra-nwr.gpx"
    assert (where / "notes.txt").is_file()  # anything else stays
    (where / "notes.txt").unlink()
    assert infra.remove_layer(where, None) == ()
    assert not where.exists()


def test_an_unknown_layer_is_refused_by_name(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no infrastructure layer 'osm-shelters'"):
        infra.layer_files("osm-shelters")


def test_a_symlinked_directory_is_left_alone(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "infra"
    link.symlink_to(real)
    with pytest.raises(OSError, match="symbolic link"):
        infra.write_layer(link, _layer())
    with pytest.raises(OSError, match="symbolic link"):
        infra.remove_layer(link, None)


def test_the_directory_is_under_xdg_data_home(tmp_path: Path) -> None:
    got = infra.overlay_dir({"XDG_DATA_HOME": str(tmp_path / "d")})
    assert got == tmp_path / "d" / "hammunition" / "overlays" / "infra"


# --- region boxes and the extracts (Task 3) -----------------------------------------


def _region(folder: Path, slug: str, body: bytes) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{slug}.osm.pbf"
    path.write_bytes(body)
    return path


def test_each_extracts_header_box_is_a_filter(tmp_path: Path) -> None:
    folder = tmp_path / "share" / "hammunition" / "data" / "osm-regions"
    _region(folder, "a-delaware", pbf((-75.79, -74.96, 40.03, 38.45)))
    _region(folder, "b-vermont", pbf((-73.44, -71.46, 45.18, 42.72)))
    boxes, notes = infra.region_boxes(tmp_path)
    assert boxes == [
        pytest.approx((-75.79, 38.45, -74.96, 40.03)),
        pytest.approx((-73.44, 42.72, -71.46, 45.18)),
    ]
    assert notes == []
    assert infra.in_boxes(39.0, -75.5, boxes)
    assert not infra.in_boxes(41.0, -75.5, boxes)
    assert infra.in_boxes(40.5, -75.5, boxes, pad=1.0)


def test_an_extract_without_a_box_is_named_by_number_and_left_out(tmp_path: Path) -> None:
    folder = tmp_path / "share" / "hammunition" / "data" / "osm-regions"
    _region(folder, "a-delaware", pbf((-75.79, -74.96, 40.03, 38.45)))
    _region(folder, "b-secret", pbf(None))
    _region(folder, "c-broken", b"not a pbf")
    boxes, notes = infra.region_boxes(tmp_path)
    assert len(boxes) == 1
    assert notes == [
        "region extract 2 of 3 has no bounding box in its header; left out",
        "region extract 3 of 3 could not be read; left out",
    ]
    assert not any("secret" in n or "broken" in n for n in notes)


def test_no_extract_means_no_box(tmp_path: Path) -> None:
    assert infra.region_boxes(tmp_path) == ([], [])


def test_a_box_across_the_antimeridian_holds_both_sides(tmp_path: Path) -> None:
    folder = tmp_path / "share" / "hammunition" / "data" / "osm-regions"
    _region(folder, "fiji", pbf((177.0, -178.0, -15.0, -20.0)))
    boxes, _ = infra.region_boxes(tmp_path)
    assert infra.in_boxes(-17.0, 178.0, boxes)
    assert infra.in_boxes(-17.0, -179.0, boxes)
    assert not infra.in_boxes(-17.0, 170.0, boxes)


def test_filter_extract_names_the_extract_by_label_only(tmp_path: Path) -> None:
    pbf_path = tmp_path / "secret-county.osm.pbf"

    def failing(argv: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, 1, "", f"Open failed for '{pbf_path}'")

    with pytest.raises(infra.InfraInputError) as caught:
        infra.filter_extract(
            pbf_path, tmp_path, ("medical",), run=failing, label="region extract 1 of 1"
        )
    assert "secret" not in str(caught.value)
    assert "region extract 1 of 1" in str(caught.value)


def test_filter_extract_reads_what_osmium_wrote_and_deletes_it(tmp_path: Path) -> None:
    def stub(argv: list[str]) -> subprocess.CompletedProcess[str]:
        Path(argv[argv.index("-o") + 1]).write_text(FIXTURE.read_text())
        return subprocess.CompletedProcess(argv, 0, "", "")

    got = infra.filter_extract(tmp_path / "x.osm.pbf", tmp_path, ("water",), run=stub, label="l")
    assert _names(got.points["water"]) == ["Water tower", "Testville Wastewater"]
    assert list(tmp_path.iterdir()) == []


@pytest.mark.skipif(shutil.which("osmium") is None, reason="osmium is not installed")
def test_the_real_osmium_keeps_ways_and_relations_placeable(tmp_path: Path) -> None:
    """osmium over an extract built from the fixture: the referenced nodes
    of matched ways and of a matched relation's member ways come with them."""
    built = tmp_path / "testville.osm.pbf"
    subprocess.run(["osmium", "cat", str(FIXTURE), "-o", str(built)], check=True)
    got = infra.filter_extract(built, tmp_path, tuple(OSM_LAYERS), label="region extract 1 of 1")
    assert sum(len(v) for v in got.points.values()) == 20
    # osmium writes nodes, then ways, then relations: the hospital way whose
    # nodes are missing is read 20th of 21, before the fire station relation.
    assert got.read == 21
    assert got.skipped == {infra.NO_POSITION: [20]}
    assert _names(got.points["responders"])[-1] == "Testville Fire Company"
