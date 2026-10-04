# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Repeater modes, bands, digital details, distance, and the per-mode QMapShack
categories.  D-074 (amended 2026-10-04), issue #313.

Every row is synthetic: N0CALL, N0TST, FN31pr.
"""

from __future__ import annotations

import importlib
import json
import math
import os
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from hammunition import repeater_sources as rs
from hammunition import repeaterbook, repeaters
from hammunition.repeaters import Layer, Repeater
from hammunition.station import Station, save_station
from json_support import parse_one, validate

cli = importlib.import_module("hammunition.cli.main")
FIXTURES = Path(__file__).parent / "fixtures" / "repeaters"


def _row(**over: object) -> Repeater:
    base: dict[str, object] = {
        "callsign": "N0CALL",
        "output_hz": 146_940_000,
        "lat": 41.80,
        "lon": -72.70,
        "source": repeaters.HAND,
    }
    base.update(over)
    return Repeater(**base)  # type: ignore[arg-type]


# --- the vocabulary ---------------------------------------------------------------


def test_the_vocabulary_is_the_issues_list() -> None:
    assert repeaters.MODES == (
        "FM",
        "DMR",
        "D-STAR",
        "YSF",
        "P25",
        "NXDN",
        "M17",
        "TETRA",
        "ATV",
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("FM", ("FM",)),
        ("FM Analog", ("FM",)),
        ("Analog", ("FM",)),
        ("NFM", ("FM",)),
        ("WFM", ("FM",)),
        ("dmr", ("DMR",)),
        ("D-Star", ("D-STAR",)),
        ("D-star    ", ("D-STAR",)),
        ("DSTAR", ("D-STAR",)),
        ("System Fusion", ("YSF",)),
        ("Fusion", ("YSF",)),
        ("C4FM", ("YSF",)),
        ("Yaesu", ("YSF",)),
        ("APCO P-25", ("P25",)),
        ("P-25", ("P25",)),
        ("P25", ("P25",)),
        ("NXDN", ("NXDN",)),
        ("M17", ("M17",)),
        ("Tetra", ("TETRA",)),
        ("ATV", ("ATV",)),
        ("digital ATV", ("ATV",)),
        # MODES order, deduplicated, whatever the source's order.
        ("Fusion, DMR, FM Analog, FM", ("FM", "DMR", "YSF")),
        ("DMR; D-Star / FM", ("FM", "DMR", "D-STAR")),
        ("", ()),
        ("   ", ()),
        ("SSB", ()),
        ("CW", ()),
        ("FM voice (F3E)", ("FM",)),
    ],
)
def test_normalise_modes_table(text: str, expected: tuple[str, ...]) -> None:
    assert repeaters.normalise_modes(text) == expected


def test_an_unknown_word_is_left_in_mode_and_out_of_modes() -> None:
    row = _row(mode="SSB")
    assert row.modes == () and row.mode == "SSB" and row.mode_text() == "SSB"
    assert _row(mode="FM voice (F3E)").mode_text() == "FM voice (F3E)"  # nothing dropped
    assert _row(mode="Fusion, FM Analog").mode_text() == "FM, YSF"


def test_explicit_modes_render_into_mode_text() -> None:
    row = _row(modes=("FM", "DMR"))
    assert row.mode_text() == "FM, DMR"
    assert _row(mode="").mode_text() == ""


# Spellings no parser's fixture may add silently: every mode text a fixture
# produces maps somewhere, or is named here, so a new source's unknown word
# fails this test instead of vanishing from a filter.
KNOWN_UNMAPPED: set[str] = set()


def _fixture_rows() -> list[Repeater]:
    rows: list[Repeater] = []
    rows += rs.read_open_repeater(FIXTURES / "open-repeater.json").rows
    rows += rs.parse_etcc((FIXTURES / "etcc.csv").read_bytes(), "https://example.invalid/e").rows
    rows += rs.parse_brandmeister(
        (FIXTURES / "brandmeister.json").read_bytes(), "https://example.invalid/b"
    ).rows
    rows += rs.read_osm_xml((FIXTURES / "osm-repeaters.osm").read_text(), Path("x.osm")).rows
    rows += repeaterbook.parse_export(
        (FIXTURES / "repeaterbook-api-de.json").read_bytes(), "https://example.invalid/r"
    ).rows
    for name in ("hearham.json", "hand.csv"):
        rows += repeaters.read_input(FIXTURES / name).rows
    return rows


def test_every_mode_spelling_in_the_fixtures_maps_somewhere() -> None:
    texts = {r.mode for r in _fixture_rows() if r.mode}
    assert texts, "the fixtures carry no mode text: this test would pass on nothing"
    nowhere = {t for t in texts if not repeaters.normalise_modes(t)}
    assert nowhere <= KNOWN_UNMAPPED, f"mode spellings that map to nothing: {sorted(nowhere)}"


def test_every_acma_emission_word_maps_or_is_named() -> None:
    for designator in ("16K0F3E", "16K0F1D", "16K0F9W", "16K0FXE", "6M00C3F", "16K0J3E", "16K0A1A"):
        text = rs._acma_mode(designator)
        assert text, designator
    assert repeaters.normalise_modes(rs._acma_mode("16K0F3E")) == ("FM",)
    assert repeaters.normalise_modes(rs._acma_mode("6M00C3F")) == ("ATV",)
    assert repeaters.normalise_modes(rs._acma_mode("16K0J3E")) == ()  # SSB: not a repeater mode


def test_each_parser_fills_modes_from_its_own_spelling() -> None:
    by_source: dict[str, list[Repeater]] = {}
    for row in _fixture_rows():
        by_source.setdefault(row.source, []).append(row)
    assert {r.modes for r in by_source[repeaters.BRANDMEISTER]} == {("DMR",)}
    etcc = {r.callsign: r.modes for r in by_source[repeaters.ETCC]}
    assert etcc["N0CALL"] == ("FM",) and "DMR" in etcc["N0TST"] and "D-STAR" in etcc["N0TST"]
    hearham = {(r.callsign, r.output_hz): r.modes for r in by_source[repeaters.HEARHAM]}
    assert hearham == {
        ("N0CALL", 146_940_000): ("FM",),
        ("N0TST", 444_100_000): ("D-STAR",),
        ("N0TST", 443_000_000): ("DMR",),
    }
    osm = by_source[repeaters.OSM]
    assert any(r.modes == ("FM",) for r in osm)
    api = by_source[repeaters.REPEATERBOOK_API]
    assert any(r.modes == ("FM",) for r in api)


def test_repeaterbook_api_modes_map_every_documented_key() -> None:
    item = {
        "Callsign": "N0CALL",
        "Frequency": "146.94000",
        "Input Freq": "146.34000",
        "Lat": "41.8",
        "Long": "-72.7",
        "Operational Status": "On-air",
        "FM Analog": "Yes",
        "DMR": "Yes",
        "D-Star": "Yes",
        "NXDN": "Yes",
        "APCO P-25": "Yes",
        "M17": "Yes",
        "System Fusion": "Yes",
        "Tetra": "Yes",
        "DMR Color Code": "1",
        "DMR ID": 310001,
        "P-25 NAC": "293",
    }
    raw = json.dumps({"count": 1, "results": [item]}).encode()
    (row,) = repeaterbook.parse_export(raw, "https://example.invalid/r").rows
    assert row.modes == ("FM", "DMR", "D-STAR", "YSF", "P25", "NXDN", "M17", "TETRA")
    assert row.digital == {"dmr_color_code": "1", "dmr_id": "310001", "p25_nac": "293"}


def test_repeaterbook_api_without_digital_values_carries_none() -> None:
    (row, *_) = repeaterbook.parse_export(
        (FIXTURES / "repeaterbook-api-de.json").read_bytes(), "https://example.invalid/r"
    ).rows
    assert row.digital == {}


def test_brandmeister_supplies_a_colour_code_and_an_id() -> None:
    parsed = rs.parse_brandmeister(
        (FIXTURES / "brandmeister.json").read_bytes(), "https://example.invalid/b"
    )
    first = parsed.rows[0]
    assert first.digital == {
        "dmr_color_code": "1",
        "dmr_id": "310001",
        "dmr_network": "Brandmeister",
    }
    assert all(set(r.digital) <= set(repeaters.DIGITAL_KEYS) for r in parsed.rows)


def test_digital_keys_are_a_closed_list() -> None:
    assert repeaters.DIGITAL_KEYS == (
        "dmr_color_code",
        "dmr_network",
        "dmr_id",
        "dstar_module",
        "dstar_gateway",
        "ysf_dgid",
        "p25_nac",
        "nxdn_ran",
    )


# --- bands --------------------------------------------------------------------------

EDGES = [
    (27_999_999, "other"),
    (28_000_000, "10m"),
    (29_700_000, "10m"),
    (29_700_001, "other"),
    (49_999_999, "other"),
    (50_000_000, "6m"),
    (54_000_000, "6m"),
    (54_000_001, "other"),
    (143_999_999, "other"),
    (144_000_000, "2m"),
    (146_940_000, "2m"),
    (148_000_000, "2m"),
    (148_000_001, "other"),
    (221_999_999, "other"),
    (222_000_000, "1.25m"),
    (225_000_000, "1.25m"),
    (225_000_001, "other"),
    (419_999_999, "other"),
    (420_000_000, "70cm"),
    (450_000_000, "70cm"),
    (450_000_001, "other"),
    (901_999_999, "other"),
    (902_000_000, "33cm"),
    (928_000_000, "33cm"),
    (928_000_001, "other"),
    (1_239_999_999, "other"),
    (1_240_000_000, "23cm"),
    (1_300_000_000, "23cm"),
    (1_300_000_001, "other"),
    (2_299_999_999, "other"),
    (2_300_000_000, "13cm"),
    (2_450_000_000, "13cm"),
    (2_450_000_001, "other"),
    (0, "other"),
]


@pytest.mark.parametrize(("hz", "band"), EDGES)
def test_band_of_at_every_edge(hz: int, band: str) -> None:
    assert repeaters.band_of(hz) == band


def test_the_band_names_are_the_filters() -> None:
    assert [b for b, _, _ in repeaters.BANDS] == [
        "10m",
        "6m",
        "2m",
        "1.25m",
        "70cm",
        "33cm",
        "23cm",
        "13cm",
    ]


# --- position and distance -------------------------------------------------------------


def test_a_grid_square_is_its_centre_and_lat_lon_is_decimal() -> None:
    lat, lon = repeaters.parse_position("FN31pr")
    assert lat == pytest.approx(41.729167, abs=1e-5) and lon == pytest.approx(-72.708333, abs=1e-5)
    assert repeaters.parse_position("fn31") == pytest.approx((41.5, -73.0))
    assert repeaters.parse_position("41.5,-72.25") == (41.5, -72.25)
    assert repeaters.parse_position(" 41.5 , -72.25 ") == (41.5, -72.25)
    for bad in ("", "nonsense", "91,0", "0,181", "1,2,3", "ZZ99"):
        with pytest.raises(ValueError):
            repeaters.parse_position(bad)


def test_distance_is_haversine_on_the_mean_radius() -> None:
    assert repeaters.distance_km(0, 0, 0, 1) == pytest.approx(
        math.radians(1) * 6371.0088, rel=1e-12
    )
    assert repeaters.distance_km(10, 20, 10, 20) == 0
    # A quarter of the meridian: pole to equator.
    assert repeaters.distance_km(90, 0, 0, 0) == pytest.approx(math.pi / 2 * 6371.0088, rel=1e-9)


@pytest.mark.parametrize(
    ("to", "bearing"), [((1, 0), 0.0), ((0, 1), 90.0), ((-1, 0), 180.0), ((0, -1), 270.0)]
)
def test_bearing_is_initial_and_zero_to_360(to: tuple[float, float], bearing: float) -> None:
    assert repeaters.bearing_deg(0, 0, *to) == pytest.approx(bearing)
    assert 0 <= repeaters.bearing_deg(41.7, -72.7, 40.0, -73.0) < 360


def test_the_compass_point_names_the_bearing() -> None:
    assert [repeaters.compass(b) for b in (0, 44, 46, 90, 180, 270, 359.9)] == [
        "N",
        "NE",
        "NE",
        "E",
        "S",
        "W",
        "N",
    ]


# --- rows as data -------------------------------------------------------------------------


def _layer(*rows: Repeater) -> Layer:
    return Layer(name="L", description="d", day=date(2026, 10, 1), rows=rows)


def test_rows_json_writes_modes_and_digital_and_reads_them_back(tmp_path: Path) -> None:
    row = _row(mode="DMR, FM Analog", digital={"dmr_color_code": "1"})
    repeaters.write_layer(tmp_path, _layer(row), "export")
    path = tmp_path / repeaters.layer_files("export")[3]
    data = json.loads(path.read_text())
    assert data["rows"][0]["modes"] == ["FM", "DMR"]
    assert data["rows"][0]["digital"] == {"dmr_color_code": "1"}
    (back,) = repeaters.read_layer_rows(path).rows
    assert back.modes == ("FM", "DMR") and back.digital == {"dmr_color_code": "1"}


def test_a_rows_file_written_before_modes_still_reads(tmp_path: Path) -> None:
    old = {
        "layer": "L",
        "description": "d",
        "day": "2026-10-01",
        "rows": [
            {
                "callsign": "N0CALL",
                "output_hz": 146_940_000,
                "lat": 41.8,
                "lon": -72.7,
                "source": "hearham-json",
                "offset_hz": -600000,
                "tone": "100.0",
                "mode": "D-star",
                "place": "",
                "notes": "",
                "use": "",
                "status": "",
                "updated": "",
                "label": "",
                "also": [],
            }
        ],
    }
    path = tmp_path / "old.rows.json"
    path.write_text(json.dumps(old))
    (row,) = repeaters.read_layer_rows(path).rows
    assert row.modes == ("D-STAR",) and row.digital == {}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("modes", "FM"),
        ("modes", [1]),
        ("modes", ["Betamax"]),
        ("digital", {"dmr_color_code": 1}),
        ("digital", {"made_up": "1"}),
        ("digital", ["a"]),
    ],
)
def test_the_rows_guard_checks_the_new_fields(tmp_path: Path, field: str, value: object) -> None:
    repeaters.write_layer(tmp_path, _layer(_row()), "export")
    path = tmp_path / repeaters.layer_files("export")[3]
    data = json.loads(path.read_text())
    data["rows"][0][field] = value
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match=field):
        repeaters.read_layer_rows(path)


def test_cross_merge_keeps_the_union_of_modes_and_the_first_digital() -> None:
    a = [_row(source=repeaters.OSM, modes=("FM",), digital={"dmr_color_code": "2"})]
    b = [
        _row(
            source=repeaters.OPEN_REPEATER,
            modes=("DMR", "FM"),
            digital={"dmr_color_code": "1", "dmr_id": "3"},
        )
    ]
    (row,), merged = rs.cross_merge([a, b])
    assert merged == 1
    assert row.source == repeaters.OPEN_REPEATER  # outranks osm
    assert row.modes == ("FM", "DMR")
    assert row.digital == {"dmr_color_code": "1", "dmr_id": "3"}
    c = [_row(source=repeaters.OSM, modes=("YSF",))]
    d = [_row(source=repeaters.OPEN_REPEATER, modes=("FM",))]
    (row2,), _ = rs.cross_merge([c, d])
    assert row2.modes == ("FM", "YSF") and row2.digital == {}
    e = [_row(source=repeaters.OSM, digital={"p25_nac": "293"})]
    f = [_row(source=repeaters.OPEN_REPEATER)]
    (row3,), _ = rs.cross_merge([e, f])
    assert row3.digital == {"p25_nac": "293"}


# --- names, GPX, Navit --------------------------------------------------------------------


def test_the_name_carries_the_tokens_a_text_search_finds() -> None:
    assert _row(modes=("FM", "DMR")).label_text() == "N0CALL 146.940 2m FM DMR"
    assert _row().label_text() == "N0CALL 146.940 2m"
    assert _row(output_hz=444_100_000, mode="D-star").label_text() == "N0CALL 444.100 70cm D-STAR"
    assert _row(output_hz=3_500_000).label_text() == "N0CALL 3.500 other"
    assert _row(callsign="", output_hz=0, label="Hilltop").label_text() == "Hilltop"


def test_gpx_and_navit_carry_the_same_tokens() -> None:
    row = _row(modes=("FM", "DMR"))
    gpx = repeaters.gpx_text("L", "d", (row,))
    assert "<name>N0CALL 146.940 2m FM DMR</name>" in gpx
    assert "FM, DMR" in gpx  # the description renders the modes too
    assert 'label="N0CALL 146.940 2m FM DMR"' in repeaters.navit_text((row,))


def test_the_description_names_the_digital_details() -> None:
    row = _row(modes=("DMR",), digital={"dmr_color_code": "1", "dmr_id": "310001"})
    assert "dmr_color_code 1" in row.description() and "dmr_id 310001" in row.description()


# --- QMapShack categories -------------------------------------------------------------------


def _categories(path: Path) -> list[tuple[int, str, int | None]]:
    return (
        sqlite3.connect(path)
        .execute("SELECT id, name, parent FROM poi_categories ORDER BY id")
        .fetchall()
    )


def _names_in(path: Path, category: str) -> list[str]:
    db = sqlite3.connect(path)
    got = db.execute(
        "SELECT d.data FROM poi_data d JOIN poi_category_map m ON m.id = d.id "
        "JOIN poi_categories c ON c.id = m.category WHERE c.name = ? ORDER BY d.id",
        (category,),
    ).fetchall()
    return [g[0].split("\r")[0].removeprefix("name=") for g in got]


def test_the_poi_has_a_category_per_mode_present_and_a_row_is_in_each_it_speaks(
    tmp_path: Path,
) -> None:
    rows = (
        _row(modes=("FM", "DMR")),
        _row(callsign="N0TST", lat=41.9, modes=("D-STAR",)),
        _row(callsign="N0ABC", lat=42.0),
    )
    path = tmp_path / "r.poi"
    repeaters.write_poi(path, "Layer", "comment", date(2026, 10, 4), rows)
    cats = _categories(path)
    names = {n: (i, p) for i, n, p in cats}
    layer_id = names["Amateur radio repeaters"][0]
    # QMapShack builds its tree from ids in descending order: a parent has a higher id
    # than its children (CPoiFilePOI::addTreeWidgetItems, V_1.17.1).
    assert all(i < layer_id for n, (i, p) in names.items() if p == layer_id)
    assert names["Amateur radio repeaters"][1] == 0 and names["root"] == (0, None)
    children = [n for i, n, p in cats if p == layer_id]
    assert children == ["FM", "DMR", "D-STAR", "Unknown mode"]  # vocabulary order
    assert _names_in(path, "FM") == ["N0CALL 146.940 2m FM DMR"]
    assert _names_in(path, "DMR") == ["N0CALL 146.940 2m FM DMR"]
    assert _names_in(path, "D-STAR") == ["N0TST 146.940 2m D-STAR"]
    assert _names_in(path, "Unknown mode") == ["N0ABC 146.940 2m"]
    # and every point is in the layer's own category too
    assert len(_names_in(path, "Amateur radio repeaters")) == 3


def test_only_modes_present_get_a_category(tmp_path: Path) -> None:
    path = tmp_path / "r.poi"
    repeaters.write_poi(path, "L", "c", date(2026, 10, 4), (_row(modes=("FM",)),))
    assert [n for _, n, _ in _categories(path)] == ["root", "FM", "Amateur radio repeaters"]


def test_qmapshacks_own_query_finds_a_point_through_its_mode_category(tmp_path: Path) -> None:
    path = tmp_path / "r.poi"
    row = _row(modes=("FM", "DMR"), lat=41.85, lon=-72.75)
    repeaters.write_poi(path, "L", "c", date(2026, 10, 4), (row,))
    db = sqlite3.connect(path)
    ids = {n: i for i, n, _ in _categories(path)}
    for category in ("FM", "DMR", "Amateur radio repeaters"):
        found = db.execute(
            "SELECT poi_category_map.id FROM poi_category_map WHERE category=? AND id IN "
            "(SELECT id FROM poi_index WHERE maxLat<? AND minLat>=? AND maxLon<? AND minLon>=?)",
            (ids[category], 41.9, 41.8, -72.7, -72.8),
        ).fetchall()
        assert found == [(1,)], category


def test_a_poi_without_subcategories_is_unchanged_for_the_infrastructure_layers(
    tmp_path: Path,
) -> None:
    path = tmp_path / "h.poi"
    point = repeaters.PoiPoint(38.9, -75.5, "Hospital", "a hospital", "amenity=hospital")
    repeaters.write_poi_points(path, "M", "c", date(2026, 9, 1), [point], category="Medical")
    assert _categories(path) == [(0, "root", None), (1, "Medical", 0)]


# --- the list command ------------------------------------------------------------------------


@pytest.fixture
def where(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    return tmp_path / "data" / "hammunition" / "overlays" / "repeaters"


def _fill(where: Path) -> None:
    near = _row(callsign="N0NEAR", lat=41.80, lon=-72.70, modes=("FM",), source=repeaters.OSM)
    far = _row(
        callsign="N0FAR",
        output_hz=442_100_000,
        lat=42.60,
        lon=-72.70,
        modes=("DMR",),
        digital={"dmr_color_code": "1"},
        source=repeaters.OSM,
    )
    mid = _row(
        callsign="N0MID",
        output_hz=147_000_000,
        lat=42.00,
        lon=-72.70,
        modes=("DMR", "FM"),
        source=repeaters.OSM,
    )
    repeaters.write_layer(where, _layer(far, near, mid), "osm")


def _list(capsys: pytest.CaptureFixture[str], *extra: str) -> tuple[int, dict[str, Any]]:
    code = cli.main(["maps", "repeaters", "list", "--json", *extra])
    doc = parse_one(capsys.readouterr().out)
    validate(doc)
    return code, doc


def test_near_a_grid_square_sorts_by_distance_with_bearing_band_and_modes(
    where: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _fill(where)
    code, doc = _list(capsys, "--near", "FN31pr")
    assert code == 0
    assert [r["callsign"] for r in doc["rows"]] == ["N0NEAR", "N0MID", "N0FAR"]
    assert doc["centre"]["source"] == "argument"
    assert doc["centre"]["lat"] == pytest.approx(41.729167, abs=1e-5)
    assert doc["within_km"] is None
    near, mid, far = doc["rows"]
    assert 5 < near["distance_km"] < 12 and 0 <= near["bearing_deg"] < 360
    assert near["bearing_deg"] == pytest.approx(
        repeaters.bearing_deg(41.729167, -72.708333, 41.80, -72.70), abs=0.1
    )
    assert near["band"] == "2m" and far["band"] == "70cm"
    assert near["modes"] == ["FM"] and mid["modes"] == ["DMR", "FM"]
    assert far["digital"] == {"dmr_color_code": "1"} and near["digital"] == {}
    assert near["distance_km"] < mid["distance_km"] < far["distance_km"]


def test_within_leaves_out_the_far_one(where: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _fill(where)
    _, doc = _list(capsys, "--near", "41.7292,-72.7083", "--within", "60")
    assert [r["callsign"] for r in doc["rows"]] == ["N0NEAR", "N0MID"]
    assert doc["within_km"] == 60
    assert doc["centre"]["source"] == "argument"


def test_mode_keeps_what_speaks_it_and_is_repeatable(
    where: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _fill(where)
    _, doc = _list(capsys, "--near", "FN31pr", "--mode", "DMR")
    assert [r["callsign"] for r in doc["rows"]] == ["N0MID", "N0FAR"]
    _, doc = _list(capsys, "--mode", "dmr", "--mode", "FM")
    assert {r["callsign"] for r in doc["rows"]} == {"N0NEAR", "N0MID", "N0FAR"}
    _, doc = _list(capsys, "--mode", "dstar")  # a source spelling is accepted
    assert doc["rows"] == []


def test_band_filters(where: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _fill(where)
    _, doc = _list(capsys, "--band", "70cm")
    assert [r["callsign"] for r in doc["rows"]] == ["N0FAR"]
    _, doc = _list(capsys, "--band", "2m", "--mode", "DMR", "--near", "FN31pr")
    assert [r["callsign"] for r in doc["rows"]] == ["N0MID"]


def test_no_centre_is_not_an_error_and_has_no_distance(
    where: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _fill(where)
    code, doc = _list(capsys)
    assert code == 0 and doc["centre"] is None and doc["within_km"] is None
    assert all(r["distance_km"] is None and r["bearing_deg"] is None for r in doc["rows"])
    assert len(doc["rows"]) == 3


def test_the_station_grid_square_is_the_default_centre(
    where: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _fill(where)
    save_station(Station(grid_square="FN31pr"))
    _, doc = _list(capsys)
    assert doc["centre"]["source"] == "station"
    assert [r["callsign"] for r in doc["rows"]] == ["N0NEAR", "N0MID", "N0FAR"]
    _, doc = _list(capsys, "--near", "41.0,-72.0")  # an argument wins
    assert doc["centre"]["source"] == "argument"


def test_within_without_any_centre_is_refused(
    where: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _fill(where)
    assert cli.main(["maps", "repeaters", "list", "--within", "50"]) == cli.EXIT_FAILED
    assert "--near" in capsys.readouterr().err


def test_a_bad_near_or_mode_is_refused(where: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _fill(where)
    assert cli.main(["maps", "repeaters", "list", "--near", "nonsense"]) == cli.EXIT_FAILED
    assert "nonsense" in capsys.readouterr().err
    with pytest.raises(SystemExit) as stop:
        cli.main(["maps", "repeaters", "list", "--mode", "Betamax"])
    assert stop.value.code == 2
    with pytest.raises(SystemExit):
        cli.main(["maps", "repeaters", "list", "--band", "99m"])
    capsys.readouterr()


def test_text_prints_the_nearest_first_when_asked_for_a_place_or_a_mode(
    where: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _fill(where)
    assert cli.main(["maps", "repeaters", "list", "--near", "FN31pr", "--mode", "DMR"]) == 0
    out = capsys.readouterr().out
    lines = [ln for ln in out.splitlines() if "N0" in ln]
    assert len(lines) == 2 and "N0MID" in lines[0] and "N0FAR" in lines[1]
    assert "km" in lines[0] and "2m" in lines[0] and "DMR, FM" in lines[0]
    assert "dmr_color_code 1" in lines[1]
    # a plain list stays the layers' summary and names no repeater
    assert cli.main(["maps", "repeaters", "list"]) == 0
    assert "N0MID" not in capsys.readouterr().out


def test_listing_writes_nothing(where: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _fill(where)
    before = sorted((p.name, p.stat().st_mtime_ns) for p in where.iterdir())
    _list(capsys, "--near", "FN31pr", "--mode", "FM")
    assert sorted((p.name, p.stat().st_mtime_ns) for p in where.iterdir()) == before
