# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The reference books the operator chose, in station config.  D-065.

A book id says what somebody reads, not where they are, so unlike a map
region it is printed by `station show`. It is checked against the catalog's
book list when it is set, so a mistyped id is refused at the moment it is
typed rather than at the next install.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from hammunition.station import (
    STATION_FIELDS,
    Station,
    StationError,
    load_station,
    prompt_for,
    save_station,
)

cli = importlib.import_module("hammunition.cli.main")


def test_books_round_trip_through_the_station_file(tmp_path: Path) -> None:
    path = tmp_path / "station.yml"
    save_station(Station(reference_books=("ham.stackexchange.com_en_all",)), path=path)
    assert load_station(path).reference_books == ("ham.stackexchange.com_en_all",)


def test_books_are_not_a_template_variable() -> None:
    assert "reference_books" not in STATION_FIELDS


@pytest.mark.parametrize("bad", ["Wikipedia", "two words", "../x", ""])
def test_a_malformed_book_id_is_refused(bad: str) -> None:
    with pytest.raises(StationError, match="book"):
        Station(reference_books=(bad,))


def test_the_prompt_keeps_the_books(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _q: "N0TST")
    station = prompt_for(["callsign"], Station(reference_books=("wikem_en_all_nopic",)))
    assert station.reference_books == ("wikem_en_all_nopic",)
    assert station.callsign == "N0TST"


def _set(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *argv: str) -> tuple[int, Path]:
    target = tmp_path / "station.yml"
    monkeypatch.setattr("hammunition.station.config_path", lambda owner=None: target)
    return cli.main(["station", "set", *argv]), target


def test_station_set_saves_and_prints_the_books(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rc, target = _set(
        monkeypatch,
        tmp_path,
        "--reference-books",
        "ham.stackexchange.com_en_all, wikipedia_en_medicine_nopic",
    )
    assert rc == 0
    assert load_station(target).reference_books == (
        "ham.stackexchange.com_en_all",
        "wikipedia_en_medicine_nopic",
    )
    out = capsys.readouterr().out
    assert "ham.stackexchange.com_en_all" in out and "wikipedia_en_medicine_nopic" in out


def test_a_book_outside_the_catalog_list_is_refused_at_set_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rc, target = _set(monkeypatch, tmp_path, "--reference-books", "wikipedia_en_simple_all_nopic")
    assert rc != 0
    assert not target.exists()
    err = capsys.readouterr().err
    assert "wikipedia_en_simple_all_nopic" in err
    assert "hammunition reference books" in err


@pytest.mark.parametrize("value", ["", ",", " , "])
def test_an_empty_book_list_is_refused(
    value: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rc, target = _set(monkeypatch, tmp_path, "--reference-books", value)
    assert rc != 0
    assert not target.exists()
    assert "uninstall kiwix-library" in capsys.readouterr().err


def test_setting_books_keeps_the_other_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "station.yml"
    save_station(Station(callsign="N0TST", map_regions=("atlantis/oceania",)), path=target)
    rc, _ = _set(monkeypatch, tmp_path, "--reference-books", "wikem_en_all_nopic")
    assert rc == 0
    station = load_station(target)
    assert station.callsign == "N0TST"
    assert station.map_regions == ("atlantis/oceania",)


def test_station_show_prints_the_books(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("SUDO_USER", raising=False)
    save_station(
        Station(reference_books=("wikem_en_all_nopic",)),
        path=tmp_path / "hammunition" / "station.yml",
    )
    assert cli.main(["station", "show"]) == 0
    out = capsys.readouterr().out
    assert "reference books" in out and "wikem_en_all_nopic" in out
    assert "Nothing set" not in out
