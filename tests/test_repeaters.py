# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Repeater overlays: the parsers, the merge, the three writers and the
store.  D-064.

Every row is synthetic: N0CALL, N0TST, Springfield IL.
"""

from __future__ import annotations

import os
import sqlite3
import stat
import struct
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

import pytest

from hammunition import repeaters
from hammunition.repeaters import (
    Repeater,
    RepeaterInputError,
    merge,
    read_input,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "repeaters"


def _row(**over: object) -> Repeater:
    base: dict[str, object] = {
        "callsign": "N0CALL",
        "output_hz": 146_940_000,
        "lat": 39.8017,
        "lon": -89.6436,
        "source": repeaters.HAND,
    }
    base.update(over)
    return Repeater(**base)  # type: ignore[arg-type]


# --- formats -----------------------------------------------------------------


def test_a_hand_csv_is_read_and_its_bad_rows_are_counted_by_reason() -> None:
    parsed = read_input(FIXTURES / "hand.csv")
    assert parsed.format == repeaters.HAND
    assert parsed.read == 7
    calls = [(r.callsign, r.output_hz) for r in parsed.rows]
    assert calls == [("N0CALL", 146_940_000), ("N0TST", 442_500_000), ("N0CALL", 146_940_000)]
    first = parsed.rows[0]
    assert first.offset_hz == -600_000 and first.tone == "100.0" and first.mode == "FM"
    assert first.place == "Springfield" and first.notes == "synthetic"
    assert parsed.rows[1].offset_hz == 5_000_000 and parsed.rows[1].tone == ""
    reasons = {s.reason: (s.count, s.first) for s in parsed.skipped}
    assert reasons == {
        "no usable position": (3, (5, 7, 8)),
        "no callsign": (1, (6,)),
    }


def test_a_repeaterbook_csv_with_lat_and_long_is_read() -> None:
    parsed = read_input(FIXTURES / "rb.csv")
    assert parsed.format == repeaters.REPEATERBOOK_CSV
    assert parsed.read == 3 and len(parsed.rows) == 2
    one, two = parsed.rows
    assert (one.callsign, one.output_hz, one.offset_hz) == ("N0CALL", 146_940_000, -600_000)
    assert one.tone == "100.0" and one.use == "OPEN" and one.status == "On-air"
    assert one.place == "Springfield, Water tower" and one.updated == "2026-01-02"
    assert two.offset_hz == 5_000_000 and two.tone == "123.0"
    assert [s.reason for s in parsed.skipped] == ["no usable position"]


def test_a_gpx_waypoint_gives_callsign_and_frequency_from_name_then_desc() -> None:
    parsed = read_input(FIXTURES / "export.gpx")
    assert parsed.format == repeaters.REPEATERBOOK_GPX
    assert parsed.read == 4
    one, two, three = parsed.rows
    assert (one.callsign, one.output_hz) == ("N0CALL", 146_940_000)
    assert (two.callsign, two.output_hz) == ("N0TST", 444_100_000)
    # No callsign and no frequency: keyed and labelled on its own name.
    assert three.callsign == "" and three.output_hz == 0
    assert three.label == "Springfield hilltop"
    assert one.notes == "146.940 MHz -0.600 PL 100.0 Springfield"
    assert [(s.reason, s.first) for s in parsed.skipped] == [("no usable position", (4,))]


def test_gpx_1_0_is_read_too() -> None:
    parsed = read_input(FIXTURES / "export10.gpx")
    assert [(r.callsign, r.output_hz) for r in parsed.rows] == [("N0CALL", 146_940_000)]


def test_hearham_json_as_served_is_read() -> None:
    parsed = read_input(FIXTURES / "hearham.json")
    assert parsed.format == repeaters.HEARHAM
    assert parsed.read == 4 and len(parsed.rows) == 3
    one, two, four = parsed.rows
    assert one.offset_hz == -600_000 and one.tone == "100.0" and one.status == "operational"
    assert two.mode == "D-STAR" and two.tone == "" and two.status == "not operational"
    assert four.mode == "DMR" and four.tone == "123 (decode 88.5)"
    assert four.lat == 40.0 and four.lon == -89.0
    assert [(s.reason, s.first) for s in parsed.skipped] == [("no usable position", (3,))]


# --- refusals ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "says"),
    [
        ("chirp.csv", "CHIRP CSV"),
        ("radio.bin", "CHIRP radio image"),
        ("rb-nopos.csv", "no Lat and Long"),
        ("export.kml", "KML"),
        ("entity.gpx", "DOCTYPE"),
    ],
)
def test_inputs_without_coordinates_or_not_yet_read_are_refused_by_name(
    name: str, says: str
) -> None:
    with pytest.raises(RepeaterInputError, match=says):
        read_input(FIXTURES / name)


def test_a_chirp_img_is_refused_by_its_suffix(tmp_path: Path) -> None:
    img = tmp_path / "radio.img"
    img.write_bytes(b"\x00\x01\x02")
    with pytest.raises(RepeaterInputError, match="CHIRP radio image"):
        read_input(img)


def test_an_unknown_csv_is_refused_naming_what_is_read(tmp_path: Path) -> None:
    other = tmp_path / "x.csv"
    other.write_text("a,b\n1,2\n")
    with pytest.raises(RepeaterInputError, match="callsign,output_mhz,offset_mhz"):
        read_input(other)


def test_an_unreadable_file_is_refused(tmp_path: Path) -> None:
    with pytest.raises(RepeaterInputError, match="cannot read"):
        read_input(tmp_path / "absent.gpx")


# --- merge ---------------------------------------------------------------------


def test_the_same_repeater_twice_merges_and_the_same_pair_elsewhere_is_kept() -> None:
    a = _row()
    b = _row(lat=39.8019, lon=-89.6433, tone="100.0")  # same 0.01 degree cell
    far = _row(lat=40.90, lon=-89.10)  # 120 km away
    kept, merged = merge([a, b, far])
    assert merged == 1
    assert kept == (a, far)


def test_a_merge_keeps_the_newer_last_update() -> None:
    old = _row(updated="2025-06-01", tone="88.5")
    new = _row(updated="2026-01-02", tone="100.0")
    kept, merged = merge([old, new])
    assert merged == 1 and kept == (new,)
    kept, _ = merge([new, old])
    assert kept == (new,)


def test_a_merge_with_no_dates_keeps_the_first() -> None:
    first, second = _row(tone="88.5"), _row(tone="100.0")
    assert merge([first, second]) == ((first,), 1)


# --- the layer's date and name ------------------------------------------------------


def test_the_layer_is_dated_by_the_oldest_input_unless_told(tmp_path: Path) -> None:
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    a.write_text("x")
    b.write_text("x")
    os.utime(a, (1_780_000_000, 1_780_000_000))
    os.utime(b, (1_790_000_000, 1_790_000_000))
    assert repeaters.export_date([a, b], None) == date.fromtimestamp(1_780_000_000)
    assert repeaters.export_date([a, b], date(2026, 9, 1)) == date(2026, 9, 1)
    assert repeaters.layer_name(date(2026, 9, 1)) == (
        "Repeaters (own export 2026-09-01, personal use)"
    )
    assert repeaters.hearham_layer_name(date(2026, 9, 29)) == (
        "Repeaters (hearham 2026-09-29, unverified)"
    )


@pytest.mark.parametrize("text", ["2026-09-01", "2026-9-1"])
def test_exported_parses_an_iso_date(text: str) -> None:
    if text == "2026-9-1":
        with pytest.raises(ValueError, match="YYYY-MM-DD"):
            repeaters.parse_exported(text)
    else:
        assert repeaters.parse_exported(text) == date(2026, 9, 1)


# --- writers ------------------------------------------------------------------


def test_the_label_is_callsign_and_frequency() -> None:
    assert _row().label_text() == "N0CALL 146.940"
    assert _row(output_hz=146_942_500).label_text() == "N0CALL 146.9425"
    assert _row(callsign="", output_hz=0, label="Springfield hilltop").label_text() == (
        "Springfield hilltop"
    )


def test_the_gpx_carries_the_layer_name_and_each_waypoint() -> None:
    rows = (
        _row(offset_hz=-600_000, tone="100.0", mode="FM", place="Springfield"),
        _row(callsign="N0TST", output_hz=442_500_000, source=repeaters.REPEATERBOOK_GPX),
    )
    text = repeaters.gpx_text("Repeaters (own export 2026-09-01, personal use)", "about", rows)
    root = ET.fromstring(text)
    ns = {"g": "http://www.topografix.com/GPX/1/1"}
    assert root.findtext("g:metadata/g:name", namespaces=ns) == (
        "Repeaters (own export 2026-09-01, personal use)"
    )
    assert root.findtext("g:metadata/g:desc", namespaces=ns) == "about"
    wpts = root.findall("g:wpt", ns)
    assert [w.findtext("g:name", namespaces=ns) for w in wpts] == [
        "N0CALL 146.940",
        "N0TST 442.500",
    ]
    assert {w.findtext("g:sym", namespaces=ns) for w in wpts} == {"Tall Tower"}
    desc = wpts[0].findtext("g:desc", namespaces=ns) or ""
    assert "offset -0.600 MHz" in desc and "tone 100.0" in desc and "FM" in desc
    assert "Springfield" in desc and "your own list" in desc
    assert "Data courtesy of RepeaterBook.com" in (wpts[1].findtext("g:desc", namespaces=ns) or "")
    assert wpts[0].get("lat") == "39.80170" and wpts[0].get("lon") == "-89.64360"


def test_the_gpx_escapes_markup() -> None:
    text = repeaters.gpx_text("L", "d", (_row(notes='<b>"x" & y</b>'),))
    root = ET.fromstring(text)
    ns = {"g": "http://www.topografix.com/GPX/1/1"}
    desc = root.findtext("g:wpt/g:desc", namespaces=ns) or ""
    assert '<b>"x" & y</b>' in desc


def test_the_navit_textfile_has_one_labelled_tower_per_repeater() -> None:
    text = repeaters.navit_text((_row(), _row(callsign="N0TST", label='a"b')))
    assert text.splitlines() == [
        '-89.64360 39.80170 type=poi_custom0 label="N0CALL 146.940" '
        'icon_src="/usr/share/navit/icons/tower.png"',
        '-89.64360 39.80170 type=poi_custom0 label="N0TST 146.940" '
        'icon_src="/usr/share/navit/icons/tower.png"',
    ]


# QMapShack 1.17.1, CPoiFilePOI::loadPOIsFromFile, verbatim (spike copy).
QMS_QUERY = (
    "SELECT main.poi_index.maxLat, main.poi_index.maxLon, main.poi_index.minLat, "
    "main.poi_index.minLon, main.poi_data.data, main.poi_data.id "
    "FROM main.poi_data, main.poi_index "
    "WHERE main.poi_data.id IN "
    "(SELECT main.poi_category_map.id FROM main.poi_category_map "
    " WHERE main.poi_category_map.id IN "
    " (SELECT main.poi_index.id FROM main.poi_index "
    "  WHERE main.poi_index.maxLat<:maxLat AND main.poi_index.minLat>=:minLat "
    "  AND main.poi_index.maxLon<:maxLon AND main.poi_index.minLon>=:minLon) "
    " AND main.poi_category_map.category=:categoryID) "
    "AND main.poi_data.id = main.poi_index.id"
)


def _tiles_holding(db: sqlite3.Connection, lat: float, lon: float, poi: int = 1) -> int:
    """How many 0.1-degree tiles around (lat, lon) QMapShack finds POI *poi* in."""
    import math

    found = 0
    for dlat in (-1, 0, 1):
        for dlon in (-1, 0, 1):
            lat10 = math.floor(lat * 10) + dlat
            lon10 = math.floor(lon * 10) + dlon
            params = {
                # QMapShack binds these as text: QString::number(x, 'f').
                "maxLat": f"{(lat10 + 1) / 10.0:f}",
                "minLat": f"{lat10 / 10.0:f}",
                "maxLon": f"{(lon10 + 1) / 10.0:f}",
                "minLon": f"{lon10 / 10.0:f}",
                "categoryID": 1,
            }
            found += sum(1 for r in db.execute(QMS_QUERY, params).fetchall() if r[5] == poi)
    return found


def test_every_poi_is_found_by_qmapshacks_own_query_in_exactly_one_tile(tmp_path: Path) -> None:
    rows = (
        _row(),
        _row(callsign="N0TST", lat=39.8, lon=-89.6),  # on a tile corner
        _row(callsign="N0TST", output_hz=444_100_000, lat=38.55, lon=-60.1),
    )
    path = tmp_path / "r.poi"
    repeaters.write_poi(path, "Layer", "comment", date(2026, 9, 1), rows)
    db = sqlite3.connect(path)
    for number, row in enumerate(rows, start=1):
        assert _tiles_holding(db, row.lat, row.lon, number) == 1, row
    meta = dict(db.execute("SELECT name, value FROM metadata").fetchall())
    min_lat, min_lon, max_lat, max_lon = (float(x) for x in meta["bounds"].split(","))
    assert min_lat < 38.55 < 39.8017 < max_lat and min_lon < -89.6436 < -60.1 < max_lon
    assert meta["comment"] == "Layer. comment"
    assert meta["writer"] == "hammunition"
    cats = db.execute("SELECT id, name, parent FROM poi_categories ORDER BY id").fetchall()
    assert cats == [(0, "root", None), (1, "Amateur radio repeaters", 0)]
    data = db.execute("SELECT data FROM poi_data WHERE id=1").fetchone()[0]
    assert data.split("\r")[0] == "name=N0CALL 146.940"


def test_without_the_nudge_a_point_on_a_tile_line_is_lost(tmp_path: Path) -> None:
    """Falsified: the check above fails when the nudge is off."""
    path = tmp_path / "r.poi"
    row = _row(lat=38.55, lon=-60.1)
    repeaters.write_poi(path, "L", "c", date(2026, 9, 1), (row,), nudge=False)
    assert _tiles_holding(sqlite3.connect(path), row.lat, row.lon) == 0


def test_the_nudge_moves_only_points_on_a_line_and_stays_in_range() -> None:
    assert repeaters.nudge(39.8017, 90.0) == 39.8017
    moved = repeaters.nudge(-60.1, 180.0)
    assert moved != -60.1 and abs(moved + 60.1) < 1e-4
    # float32, as the rtree holds it, lands inside one tile.
    stored = struct.unpack("f", struct.pack("f", moved))[0]
    assert -60.1 <= stored < -60.0 or -60.2 <= stored < -60.1
    assert repeaters.nudge(89.9, 90.0) != 89.9
    assert repeaters.nudge(179.9, 180.0) <= 180.0


# Review finding 1: the float32 rounding grows with the coordinate, so a
# fixed band that worked at Springfield lost points past about 64 degrees.
LINES = (-179.9, -155.1, -122.4, -89.9, -60.1, -0.1, 0.0, 0.1, 12.3, 39.8, 150.3, 179.9)
OFFSETS = tuple(n * 1e-6 for n in range(-30, 31))


@pytest.mark.parametrize("axis", ["lat", "lon"])
def test_every_point_near_any_tile_line_is_found_in_exactly_one_tile(
    axis: str, tmp_path: Path
) -> None:
    limit = 90.0 if axis == "lat" else 180.0
    rows = []
    for line in LINES:
        if abs(line) > limit - 0.05:
            continue
        for offset in OFFSETS:
            value = line + offset
            if axis == "lat":
                rows.append(_row(lat=value, lon=-89.65))
            else:
                rows.append(_row(lat=45.05, lon=value))
    rows.append(_row(lat=89.99999, lon=179.99999))  # the edge of the world
    path = tmp_path / "r.poi"
    repeaters.write_poi(path, "L", "c", date(2026, 9, 1), rows)
    db = sqlite3.connect(path)
    lost = [
        (row.lat, row.lon)
        for number, row in enumerate(rows, start=1)
        if _tiles_holding(db, row.lat, row.lon, number) != 1
    ]
    assert not lost, f"{len(lost)} of {len(rows)} not in exactly one tile: {lost[:5]}"


# --- the store ------------------------------------------------------------------


def test_the_overlay_directory_follows_xdg_data_home(tmp_path: Path) -> None:
    got = repeaters.overlay_dir({"XDG_DATA_HOME": str(tmp_path / "d")}, home=tmp_path)
    assert got == tmp_path / "d" / "hammunition" / "overlays" / "repeaters"
    got = repeaters.overlay_dir({}, home=tmp_path)
    assert got == tmp_path / ".local" / "share" / "hammunition" / "overlays" / "repeaters"


def test_write_layer_writes_three_private_files_atomically(tmp_path: Path) -> None:
    where = tmp_path / "overlays" / "repeaters"
    layer = repeaters.Layer(
        name="Repeaters (own export 2026-09-01, personal use)",
        description="about",
        day=date(2026, 9, 1),
        rows=(_row(),),
    )
    written = repeaters.write_layer(where, layer)
    assert [p.name for p in written] == ["repeaters.gpx", "repeaters.poi", "repeaters.navit.txt"]
    assert stat.S_IMODE(where.stat().st_mode) == 0o700
    for path in written:
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert sorted(p.name for p in where.iterdir()) == sorted(p.name for p in written)
    # Again: replaced, nothing left behind.
    repeaters.write_layer(where, layer)
    assert sorted(p.name for p in where.iterdir()) == sorted(p.name for p in written)


def test_write_layer_refuses_a_symlinked_directory(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "repeaters"
    link.symlink_to(real)
    layer = repeaters.Layer(name="L", description="d", day=date(2026, 9, 1), rows=(_row(),))
    with pytest.raises(OSError, match="symbolic link"):
        repeaters.write_layer(link, layer)
    assert list(real.iterdir()) == []


def test_remove_layer_is_idempotent(tmp_path: Path) -> None:
    where = tmp_path / "repeaters"
    layer = repeaters.Layer(name="L", description="d", day=date(2026, 9, 1), rows=(_row(),))
    written = repeaters.write_layer(where, layer)
    assert repeaters.remove_layer(where) == tuple(written)
    assert not where.exists()
    assert repeaters.remove_layer(where) == ()


def test_remove_layer_keeps_a_file_that_is_not_ours(tmp_path: Path) -> None:
    where = tmp_path / "repeaters"
    layer = repeaters.Layer(name="L", description="d", day=date(2026, 9, 1), rows=(_row(),))
    repeaters.write_layer(where, layer)
    (where / "mine.txt").write_text("keep")
    repeaters.remove_layer(where)
    assert [p.name for p in where.iterdir()] == ["mine.txt"]


# --- licence text ----------------------------------------------------------------


def test_the_licence_texts_are_the_approved_wording() -> None:
    rb = repeaters.licence_text(repeaters.REPEATERBOOK_GPX)
    assert rb.startswith("Data courtesy of RepeaterBook.com.")
    assert "may not be redistributed in any form" in rb
    assert "repeaterbook.com/about/legal" in rb
    assert "do not use them to visit a repeater site" in rb
    assert repeaters.licence_text(repeaters.HAND) == (
        "Your own data. Hammunition adds nothing to it and sends it nowhere."
    )
    hh = repeaters.hearham_licence("Fetched 2026-09-29T20:00:00Z", "ab" * 32)
    assert "life-and-death operations" in hh and "not verifiable" in hh and "D-033" in hh
    assert ("ab" * 32) in hh


# --- review findings 3, 4, 5 and 8 ------------------------------------------------------


def _gpx(tmp_path: Path, *waypoints: str) -> Path:
    path = tmp_path / "x.gpx"
    body = "".join(f'<wpt lat="39.7817" lon="-89.6436">{w}</wpt>' for w in waypoints)
    path.write_text(f'<gpx xmlns="http://www.topografix.com/GPX/1/1">{body}</gpx>')
    return path


def test_a_tone_or_a_coordinate_in_desc_is_not_taken_for_the_frequency(tmp_path: Path) -> None:
    parsed = read_input(
        _gpx(
            tmp_path,
            "<name>N0CALL</name><desc>PL 100.0 at 39.7817</desc>",
            "<name>N0TST</name><desc>PL 100.0, 147.000 MHz +0.600</desc>",
        )
    )
    first, second = parsed.rows
    assert first.output_hz == 0 and first.label_text() == "N0CALL"
    assert second.output_hz == 147_000_000


def test_a_waypoint_with_no_name_and_no_frequency_keeps_its_callsign(tmp_path: Path) -> None:
    parsed = read_input(_gpx(tmp_path, "<desc>N0CALL club</desc>", "<desc>nothing</desc>"))
    assert [r.label_text() for r in parsed.rows] == ["N0CALL"]
    assert [(s.reason, s.first) for s in parsed.skipped] == [("no callsign", (2,))]


def test_a_frequency_outside_1_to_10000_mhz_is_skipped(tmp_path: Path) -> None:
    hand = tmp_path / "h.csv"
    hand.write_text(
        ",".join(repeaters.HAND_HEADER) + "\n"
        "N0CALL,146940000,,,FM,39.8017,-89.6436,,\n"
        "N0TST,462.550,+5.000,,FM,39.75,-89.60,GMRS,\n"
    )
    parsed = read_input(hand)
    assert [r.output_hz for r in parsed.rows] == [462_550_000]
    assert [(s.reason, s.first) for s in parsed.skipped] == [("no usable output frequency", (2,))]


def test_one_odd_hearham_entry_is_skipped_not_the_whole_list(tmp_path: Path) -> None:
    import json

    rows = json.loads((FIXTURES / "hearham.json").read_text())
    path = tmp_path / "h.json"
    path.write_text(json.dumps([*rows, {"id": 9}, "junk"]))
    parsed = read_input(path)
    assert parsed.format == repeaters.HEARHAM and len(parsed.rows) == 3
    assert ("not a repeater entry", 2, (5, 6)) in [
        (s.reason, s.count, s.first) for s in parsed.skipped
    ]
    nothing = tmp_path / "n.json"
    nothing.write_text(json.dumps([{"id": 9}]))
    with pytest.raises(RepeaterInputError, match="not hearham"):
        read_input(nothing)


def test_remove_layer_also_clears_temporaries_an_interrupted_import_left(tmp_path: Path) -> None:
    where = tmp_path / "repeaters"
    layer = repeaters.Layer(name="L", description="d", day=date(2026, 9, 1), rows=(_row(),))
    repeaters.write_layer(where, layer)
    (where / ".repeaters.gpx.abc123").write_text("half")
    repeaters.remove_layer(where)
    assert not where.exists()
