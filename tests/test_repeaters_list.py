# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``maps repeaters list``: the layers as data for a front end.  D-074 (amended
2026-10-04), D-059, D-081.

Read-only, partial lists exit 0. Every row is synthetic: N0CALL, N0TST.
"""

from __future__ import annotations

import importlib
import os
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from hammunition import repeater_sources, repeaters
from hammunition.interface import repeaters as repeater_docs
from hammunition.repeaters import Layer, Repeater
from json_support import parse_one, validate

cli = importlib.import_module("hammunition.cli.main")


@pytest.fixture
def where(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    return tmp_path / "data" / "hammunition" / "overlays" / "repeaters"


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


def _write(where: Path, layer_id: str, name: str, *rows: Repeater) -> None:
    layer = Layer(name=name, description=f"licence of {name}", day=date(2026, 10, 1), rows=rows)
    repeaters.write_layer(where, layer, layer_id)


def _list(capsys: pytest.CaptureFixture[str], *extra: str) -> tuple[int, dict[str, Any]]:
    code = cli.main(["maps", "repeaters", "list", "--json", *extra])
    doc = parse_one(capsys.readouterr().out)
    validate(doc)
    assert doc["kind"] == "repeaters-list"
    return code, doc


def test_no_directory_is_an_empty_document_and_exit_zero(
    where: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["maps", "repeaters", "list"]) == 0
    assert "No repeater layers" in capsys.readouterr().out
    code, doc = _list(capsys)
    assert code == 0
    assert doc["layers"] == [] and doc["skipped"] == [] and doc["rows"] == []
    assert doc["merged"] == 0 and doc["credits"] == [] and doc["directory"] == str(where)
    assert not where.exists()  # read-only: nothing created


def test_two_layers_merge_across_sources_and_carry_flags_and_credits(
    where: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(where, "repeaterbook", "RB", _row(repeaters.REPEATERBOOK_API, place="Springfield"))
    _write(
        where,
        "open-repeater",
        "OR",
        _row(repeaters.OPEN_REPEATER, tone="88.5"),
        _row(repeaters.OPEN_REPEATER, callsign="N0TST", output_hz=442_100_000, lat=40.1),
    )
    code, doc = _list(capsys)
    assert code == 0
    layers = {v["id"]: v for v in doc["layers"]}
    assert list(layers) == ["open-repeater", "repeaterbook"]  # LAYERS order
    rb, orp = layers["repeaterbook"], layers["open-repeater"]
    assert rb["personal_use"] is True and rb["unverified"] is True
    assert orp["personal_use"] is False and orp["unverified"] is False
    assert rb["rows"] == 1 and orp["rows"] == 2 and rb["day"] == "2026-10-01"
    assert rb["sources"] == ["repeaterbook-api"] and rb["name"] == "RB"
    assert rb["description"] == "licence of RB"
    assert [Path(f).suffix for f in rb["files"]] == [".gpx", ".poi", ".txt", ".json"]
    rows = doc["rows"]
    assert len(rows) == 2 and doc["merged"] == 1
    joined = next(r for r in rows if r["callsign"] == "N0CALL")
    assert joined["source"] == "repeaterbook-api" and joined["also"] == ["open-repeater-json"]
    assert joined["layer"] == "repeaterbook" and joined["personal_use"] is True
    assert joined["tone"] == "88.5"  # filled from the joining row
    other = next(r for r in rows if r["callsign"] == "N0TST")
    assert other["layer"] == "open-repeater" and other["personal_use"] is False
    credits = doc["credits"]
    assert repeaters.SOURCE_NAMES[repeaters.OPEN_REPEATER] in credits
    assert repeaters.REPEATERBOOK_LICENCE in credits
    assert len(credits) == len(set(credits))


def test_an_open_row_that_only_joins_is_personal_use_by_its_also(
    where: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The kept row is the best source; make it the open one by using hearham-less data:
    _write(where, "open-repeater", "OR", _row(repeaters.OPEN_REPEATER))
    _write(where, "osm", "OSM", _row(repeaters.OSM, callsign=""))
    _, doc = _list(capsys)
    assert doc["merged"] == 1
    row = doc["rows"][0]
    assert row["personal_use"] is False


def test_a_layer_without_rows_is_skipped_with_the_reason_and_the_rest_returned(
    where: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(where, "open-repeater", "OR", _row(repeaters.OPEN_REPEATER))
    _write(where, "osm", "OSM", _row(repeaters.OSM))
    (where / repeaters.layer_files("osm")[3]).unlink()
    _write(where, "etcc", "ETCC", _row(repeaters.ETCC))
    (where / repeaters.layer_files("etcc")[3]).write_text("{not json")
    code, doc = _list(capsys)
    assert code == 0
    assert [v["id"] for v in doc["layers"]] == ["open-repeater"]
    skipped = {s["layer"]: s["reason"] for s in doc["skipped"]}
    assert "written before D-074" in skipped["osm"]
    assert "cannot be read" in skipped["etcc"]
    assert len(doc["rows"]) == 1
    assert cli.main(["maps", "repeaters", "list"]) == 0


def test_layer_narrows_and_an_unknown_id_is_skipped(
    where: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(where, "open-repeater", "OR", _row(repeaters.OPEN_REPEATER))
    _write(where, "osm", "OSM", _row(repeaters.OSM, callsign="N0TST", output_hz=442_100_000))
    code, doc = _list(capsys, "--layer", "osm", "--layer", "nonsense", "--layer", "etcc")
    assert code == 0
    assert [v["id"] for v in doc["layers"]] == ["osm"]
    assert len(doc["rows"]) == 1 and doc["merged"] == 0
    skipped = {s["layer"]: s["reason"] for s in doc["skipped"]}
    assert "no repeater layer" in skipped["nonsense"]
    assert "not present" in skipped["etcc"]


def test_a_heard_layer_is_a_view_but_its_rows_are_not_merged(
    where: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(where, "open-repeater", "OR", _row(repeaters.OPEN_REPEATER))
    _write(where, "aprs-heard", "Heard", _row(repeaters.DIREWOLF, callsign="N0TST"))
    code, doc = _list(capsys)
    assert code == 0
    assert [v["id"] for v in doc["layers"]] == ["open-repeater", "aprs-heard"]
    assert [r["callsign"] for r in doc["rows"]] == ["N0CALL"]
    assert doc["merged"] == 0
    assert repeaters.SOURCE_NAMES[repeaters.DIREWOLF] in doc["credits"]


def test_text_is_for_a_person(where: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write(where, "repeaterbook", "RB", _row(repeaters.REPEATERBOOK_API))
    _write(where, "open-repeater", "OR", _row(repeaters.OPEN_REPEATER))
    (where / repeaters.layer_files("osm")[0]).write_text("<gpx/>")
    assert cli.main(["maps", "repeaters", "list"]) == 0
    out = capsys.readouterr().out
    assert str(where) in out
    assert "repeaterbook" in out and "personal use" in out and "unverified" in out
    assert "osm" in out and "written before D-074" in out
    assert "1 repeaters across 2 layers (1 merged across sources)" in out
    assert "Data courtesy of RepeaterBook.com" in out
    assert "N0CALL" not in out  # no callsign in the text


def test_an_unreadable_directory_is_a_failure(
    where: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    where.parent.mkdir(parents=True)
    where.write_text("a file where the directory should be")
    assert cli.main(["maps", "repeaters", "list", "--json"]) == cli.EXIT_FAILED


def test_it_writes_nothing(where: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write(where, "repeaterbook", "RB", _row(repeaters.REPEATERBOOK_API))
    _write(where, "open-repeater", "OR", _row(repeaters.OPEN_REPEATER))
    before = sorted((p.name, p.stat().st_mtime_ns) for p in where.iterdir())
    assert cli.main(["maps", "repeaters", "list", "--json"]) == 0
    capsys.readouterr()
    assert sorted((p.name, p.stat().st_mtime_ns) for p in where.iterdir()) == before
    assert not (where / repeaters.ALL_SOURCES).exists()


def test_every_source_is_classified() -> None:
    assert set(repeaters.SOURCE_TRAITS) == set(repeaters.SOURCE_NAMES)
    assert {s for s, (personal, _) in repeaters.SOURCE_TRAITS.items() if personal} == {
        repeaters.REPEATERBOOK_API,
        repeaters.REPEATERBOOK_GPX,
        repeaters.REPEATERBOOK_CSV,
    }
    assert {s for s, (_, unverified) in repeaters.SOURCE_TRAITS.items() if unverified} == {
        repeaters.HEARHAM,
        repeaters.ETCC,
        repeaters.BRANDMEISTER,
        repeaters.ACMA,
        repeaters.REPEATERBOOK_API,
    }


def test_cross_merge_reports_where_each_kept_row_came_from() -> None:
    a = [_row(repeaters.OSM)]
    b = [_row(repeaters.OPEN_REPEATER), _row(repeaters.OPEN_REPEATER, callsign="N0TST", lat=41.0)]
    rows, merged, origin = repeater_sources.cross_merge_origins([a, b])
    assert merged == 1 and len(rows) == len(origin) == 2
    assert origin[0] == 1  # open-repeater outranks osm, and it is layer index 1
    assert repeater_sources.cross_merge([a, b]) == (rows, merged)


def test_the_document_is_registered_and_rendered() -> None:
    assert repeater_docs.RepeatersListDocument.KIND == "repeaters-list"
    assert callable(repeater_docs.render_repeaters_list)
