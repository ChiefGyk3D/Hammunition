# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""One layer per source, side by side, and the all-sources file rebuilt
from them.  D-074.

Every row is synthetic: N0CALL, N0TST, Springfield IL.
"""

from __future__ import annotations

import json
import stat
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

import pytest

from hammunition import repeaters
from hammunition.repeaters import Layer, Repeater

GPX = "{http://www.topografix.com/GPX/1/1}"


def _row(source: str, **over: object) -> Repeater:
    base: dict[str, object] = {
        "callsign": "N0CALL",
        "output_hz": 146_940_000,
        "lat": 39.80,
        "lon": -89.64,
        "source": source,
    }
    base.update(over)
    return Repeater(**base)  # type: ignore[arg-type]


def _layer(name: str, day: date, *rows: Repeater) -> Layer:
    return Layer(name=name, description=f"licence of {name}", day=day, rows=rows)


def test_each_layer_has_its_own_stem_and_a_rows_file(tmp_path: Path) -> None:
    where = tmp_path / "repeaters"
    written = repeaters.write_layer(
        where, _layer("OR", date(2026, 9, 28), _row(repeaters.OPEN_REPEATER)), "open-repeater"
    )
    assert [p.name for p in written] == [
        "repeaters-open-repeater.gpx",
        "repeaters-open-repeater.poi",
        "repeaters-open-repeater.navit.txt",
        "repeaters-open-repeater.rows.json",
    ]
    for path in written:
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    data = json.loads(written[3].read_text())
    assert data["layer"] == "OR" and data["day"] == "2026-09-28"
    assert data["rows"][0]["callsign"] == "N0CALL"


def test_the_export_layer_keeps_d064s_names(tmp_path: Path) -> None:
    assert repeaters.layer_files("export")[:3] == (
        "repeaters.gpx",
        "repeaters.poi",
        "repeaters.navit.txt",
    )
    assert repeaters.layer_files("export") == repeaters.FILES


def test_an_unknown_layer_id_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no repeater layer"):
        repeaters.layer_files("bunker")


def test_writing_one_layer_leaves_another_and_remove_by_id_takes_one(tmp_path: Path) -> None:
    where = tmp_path / "repeaters"
    repeaters.write_layer(where, _layer("own", date(2026, 9, 1), _row(repeaters.HAND)))
    repeaters.write_layer(where, _layer("osm", date(2026, 9, 1), _row(repeaters.OSM)), "osm")
    assert repeaters.present_layers(where) == ("export", "osm")
    removed = repeaters.remove_layer(where, "osm")
    assert [p.name for p in removed] == list(repeaters.layer_files("osm"))
    assert repeaters.present_layers(where) == ("export",)
    repeaters.remove_layer(where)
    assert not where.exists()


def test_the_all_sources_file_joins_the_directory_layers_and_leaves_aprs_out(
    tmp_path: Path,
) -> None:
    where = tmp_path / "repeaters"
    repeaters.write_layer(
        where, _layer("own", date(2026, 9, 1), _row(repeaters.HAND, tone="100.0"))
    )
    assert repeaters.rebuild_all(where).path is None  # one layer: nothing to join
    repeaters.write_layer(
        where,
        _layer(
            "osm",
            date(2026, 8, 15),
            _row(repeaters.OSM, callsign="", label="146.940", lat=39.81),
            _row(repeaters.OSM, output_hz=147_000_000, callsign="N0TST"),
        ),
        "osm",
    )
    repeaters.write_layer(
        where,
        _layer("heard", date(2026, 10, 2), _row(repeaters.DIREWOLF, output_hz=145_290_000)),
        "aprs-heard",
    )
    result = repeaters.rebuild_all(where)
    assert result.path == where / repeaters.ALL_SOURCES
    assert result.layers == ("export", "osm") and result.merged == 1 and result.written == 2
    assert result.name == "Repeaters (all sources, 2026-08-15)"
    assert stat.S_IMODE(result.path.stat().st_mode) == 0o600
    root = ET.parse(result.path).getroot()
    names = [w.findtext(f"{GPX}name") for w in root.iter(f"{GPX}wpt")]
    assert names == ["N0CALL 146.940", "N0TST 147.000"]
    desc = root.find(f"{GPX}metadata/{GPX}desc")
    assert desc is not None and "licence of own" in (desc.text or "")
    assert "licence of osm" in (desc.text or "") and "licence of heard" not in (desc.text or "")
    first = next(root.iter(f"{GPX}wpt")).findtext(f"{GPX}desc") or ""
    assert "also listed by OpenStreetMap" in first
    # Down to one directory layer again: the file goes.
    repeaters.remove_layer(where, "osm")
    assert repeaters.rebuild_all(where).path is None
    assert not (where / repeaters.ALL_SOURCES).exists()


def test_a_layer_without_a_rows_file_is_named_not_guessed(tmp_path: Path) -> None:
    where = tmp_path / "repeaters"
    repeaters.write_layer(where, _layer("own", date(2026, 9, 1), _row(repeaters.HAND)))
    repeaters.write_layer(
        where, _layer("or", date(2026, 9, 1), _row(repeaters.OPEN_REPEATER)), "open-repeater"
    )
    repeaters.write_layer(
        where, _layer("bm", date(2026, 9, 1), _row(repeaters.BRANDMEISTER)), "brandmeister"
    )
    (where / repeaters.layer_files("export")[3]).unlink()  # as D-064 left it
    (where / repeaters.layer_files("brandmeister")[3]).write_text("{not json")
    result = repeaters.rebuild_all(where)
    assert result.layers == ("open-repeater",) and result.path is None
    reasons = dict(result.skipped)
    assert "re-import" in reasons["export"] and "cannot be read" in reasons["brandmeister"]


@pytest.mark.parametrize(
    ("field", "value", "says"),
    [
        ("lat", "39.8", "lat"),
        ("offset_hz", "x", "offset_hz"),
        ("output_hz", True, "output_hz"),
        ("callsign", 7, "callsign"),
        ("also", "hand-csv", "also"),
        ("also", ["nobody"], "'nobody'"),
    ],
)
def test_a_tampered_rows_file_is_skipped_by_name_never_a_traceback(
    tmp_path: Path, field: str, value: object, says: str
) -> None:
    """Final review: a string latitude crashed cross_merge, a string offset
    the GPX writer, and ``true`` was taken for 1 Hz."""
    where = tmp_path / "repeaters"
    repeaters.write_layer(where, _layer("own", date(2026, 9, 1), _row(repeaters.HAND)))
    repeaters.write_layer(where, _layer("osm", date(2026, 9, 1), _row(repeaters.OSM)), "osm")
    rows_path = where / repeaters.layer_files("osm")[3]
    data = json.loads(rows_path.read_text())
    data["rows"][0][field] = value
    rows_path.write_text(json.dumps(data))
    result = repeaters.rebuild_all(where)
    assert result.path is None and result.layers == ("export",)
    reason = dict(result.skipped)["osm"]
    assert "cannot be read" in reason and says in reason


def test_a_rebuild_that_deletes_the_file_says_so(tmp_path: Path) -> None:
    where = tmp_path / "repeaters"
    repeaters.write_layer(where, _layer("own", date(2026, 9, 1), _row(repeaters.HAND)))
    repeaters.write_layer(where, _layer("osm", date(2026, 9, 1), _row(repeaters.OSM)), "osm")
    assert repeaters.rebuild_all(where).removed is None
    repeaters.remove_layer(where, "osm")
    assert repeaters.rebuild_all(where).removed == where / repeaters.ALL_SOURCES
    assert repeaters.rebuild_all(where).removed is None  # nothing left to delete


def test_removing_everything_takes_the_all_sources_file_too(tmp_path: Path) -> None:
    where = tmp_path / "repeaters"
    repeaters.write_layer(where, _layer("own", date(2026, 9, 1), _row(repeaters.HAND)))
    repeaters.write_layer(where, _layer("osm", date(2026, 9, 1), _row(repeaters.OSM)), "osm")
    repeaters.rebuild_all(where)
    removed = {p.name for p in repeaters.remove_layer(where)}
    assert repeaters.ALL_SOURCES in removed and not where.exists()
