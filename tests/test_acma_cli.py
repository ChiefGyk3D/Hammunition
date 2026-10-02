# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``maps repeaters import --from-acma``, end to end.  D-074, amended 2026-10-01.

A scratch home, config and prefix (``test_repeater_sources_cli``'s
fixture); a synthetic register (:mod:`acma_support`); region extracts that
are real PBF headers around a synthetic bounding box
(``test_osm_pbf.pbf``). The region is installed as `springfield`, a name
that must appear in no output; the box is Tasmania's, a public example.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from acma_support import CLIENT_NAME, CLIENT_STREET, TASMANIA, write_register
from hammunition import repeater_sources, repeaters
from hammunition.interface import repeaters as repeater_docs
from hammunition.interface.repeaters import render_repeaters
from json_support import assert_text_values_in_json, parse_one, validate
from test_osm_pbf import pbf
from test_repeater_sources_cli import Station, station  # noqa: F401

cli = importlib.import_module("hammunition.cli.main")

VICTORIA = (140.9, 150.0, -33.9, -39.2)
VERMONT = (-73.5, -71.4, 45.1, 42.7)


def _region(station: Station, box: tuple[float, float, float, float] | None, slug: str) -> None:  # noqa: F811
    folder = station.share / "osm-regions"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{slug}.osm.pbf").write_bytes(pbf(box))
    (folder / f"{slug}.osm.pbf.source").write_text("260901\n")


def _install_register(station: Station) -> Path:  # noqa: F811
    return write_register(station.share / "acma-register" / "spectra_rrl.zip")


def _run(argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    code = cli.main(argv)
    out, err = capsys.readouterr()
    return code, out, err


def _private(text: str) -> None:
    leaked = [p for p in ("springfield", CLIENT_NAME, CLIENT_STREET) if p in text]
    assert not leaked, f"printed {leaked}"


def test_the_installed_register_becomes_its_own_attributed_layer(
    station: Station,  # noqa: F811
    capsys: pytest.CaptureFixture[str],
) -> None:
    station.install_navit()
    _install_register(station)
    _region(station, TASMANIA, "springfield")
    code, out, err = _run(["maps", "repeaters", "import", "--from-acma"], capsys)
    assert code == 0, err
    assert "Repeaters (ACMA, 2026-10-02)" in out
    flat = " ".join(out.split())
    assert "Based on Australian Communications and Media Authority information." in flat
    assert "Written: 2 repeaters" in out
    assert f"{repeater_sources.ACMA_OUTSIDE}: 1" in out
    _private(out + err)
    for name in repeaters.layer_files("acma"):
        assert (station.layer / name).is_file()
    gpx = (station.layer / repeaters.layer_files("acma")[0]).read_text()
    assert "Based on Australian Communications and Media Authority information" in gpx
    assert "VK7RZZ 146.700" in gpx and "VK3RZZ" not in gpx
    _private(station.layer_text())
    assert repeaters.layer_files("acma")[2] in station.user_navit.read_text()


def test_two_regions_widen_the_layer(
    station: Station,  # noqa: F811
    capsys: pytest.CaptureFixture[str],
) -> None:
    _install_register(station)
    _region(station, TASMANIA, "springfield")
    _region(station, VICTORIA, "shelbyville")
    code, out, _ = _run(["maps", "repeaters", "import", "--from-acma"], capsys)
    assert code == 0 and "Written: 3 repeaters" in out
    assert "shelbyville" not in out


def test_regions_outside_australia_say_the_layer_would_be_empty(
    station: Station,  # noqa: F811
    capsys: pytest.CaptureFixture[str],
) -> None:
    _install_register(station)
    _region(station, VERMONT, "springfield")
    code, _, err = _run(["maps", "repeaters", "import", "--from-acma"], capsys)
    assert code == cli.EXIT_FAILED
    assert "the ACMA layer would be empty" in err and "covers Australia only" in err
    assert "Nothing was written" in err
    assert not station.layer.exists()
    _private(err)


def test_no_region_installed_says_what_comes_first(
    station: Station,  # noqa: F811
    capsys: pytest.CaptureFixture[str],
) -> None:
    _install_register(station)
    code, _, err = _run(["maps", "repeaters", "import", "--from-acma"], capsys)
    assert code == cli.EXIT_FAILED and "hammunition install osm-regions" in err


def test_an_extract_without_a_box_is_named_by_number(
    station: Station,  # noqa: F811
    capsys: pytest.CaptureFixture[str],
) -> None:
    _install_register(station)
    _region(station, None, "springfield")
    code, _, err = _run(["maps", "repeaters", "import", "--from-acma"], capsys)
    assert code == cli.EXIT_FAILED and "region extract 1 of 1" in err
    _private(err)


def test_a_damaged_extract_is_named_by_number_never_by_file(
    station: Station,  # noqa: F811
    capsys: pytest.CaptureFixture[str],
) -> None:
    _install_register(station)
    station.install_region()  # "not read: osmium is stubbed": no header at all
    code, _, err = _run(["maps", "repeaters", "import", "--from-acma"], capsys)
    assert code == cli.EXIT_FAILED and "region extract 1 of 1" in err
    _private(err)


def test_not_installed_names_the_unit(
    station: Station,  # noqa: F811
    capsys: pytest.CaptureFixture[str],
) -> None:
    _region(station, TASMANIA, "springfield")
    code, _, err = _run(["maps", "repeaters", "import", "--from-acma"], capsys)
    assert code == cli.EXIT_FAILED and "hammunition install acma-register" in err
    assert "unverified" in err


def test_a_downloaded_copy_is_read_the_same(
    station: Station,  # noqa: F811
    capsys: pytest.CaptureFixture[str],
) -> None:
    copy = write_register(station.root / "in" / "spectra_rrl.zip")
    _region(station, TASMANIA, "springfield")
    code, out, _ = _run(["maps", "repeaters", "import", "--from-acma", str(copy)], capsys)
    assert code == 0 and "Repeaters (ACMA, 2026-10-02)" in out


def test_one_source_per_import(
    station: Station,  # noqa: F811
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, _, err = _run(["maps", "repeaters", "import", "--from-acma", "--from-osm"], capsys)
    assert code == cli.EXIT_FAILED and "--from-acma" in err and "one source per import" in err


def test_the_json_document_validates_and_carries_the_layer(
    station: Station,  # noqa: F811
    capsys: pytest.CaptureFixture[str],
) -> None:
    _install_register(station)
    _region(station, TASMANIA, "springfield")
    # Once first, so both runs below find the layer already registered.
    assert cli.main(["maps", "repeaters", "import", "--from-acma"]) == 0
    capsys.readouterr()
    assert cli.main(["maps", "repeaters", "import", "--from-acma", "--json"]) == 0
    raw = capsys.readouterr().out
    doc = parse_one(raw)
    validate(doc)
    assert doc["layer_id"] == "acma" and doc["layer"] == "Repeaters (ACMA, 2026-10-02)"
    (entry,) = doc["inputs"]
    assert entry["format"] == "acma-register" and entry["read"] == 7
    outside = [s for s in entry["skipped"] if s["reason"] == repeater_sources.ACMA_OUTSIDE]
    assert outside and outside[0]["first"] == []
    _private(raw)
    assert cli.main(["maps", "repeaters", "import", "--from-acma"]) == 0
    text = capsys.readouterr().out
    assert_text_values_in_json(
        text, doc, render_repeaters, repeater_docs.render_all_sources, repeater_docs._registration
    )


def test_acma_and_an_export_join_with_the_regulator_kept(
    station: Station,  # noqa: F811
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    _install_register(station)
    _region(station, TASMANIA, "springfield")
    hand = tmp_path / "mine.csv"
    hand.write_text(
        "callsign,output_mhz,offset_mhz,tone,mode,lat,lon,name,notes\n"
        "VK7RZZ,146.700,-0.6,123.0,FM,-42.90,147.24,Mt Wellington,mine\n"
    )
    assert cli.main(["maps", "repeaters", "import", str(hand)]) == 0
    assert cli.main(["maps", "repeaters", "import", "--from-acma"]) == 0
    out = capsys.readouterr().out
    assert "All sources: 2 repeaters from layers export, acma, 1 joined" in out
    gpx = (station.layer / repeaters.ALL_SOURCES).read_text()
    # The operator's own row is kept first; the regulator is named beside it.
    assert "Source: your own list" in gpx and "also listed by ACMA" in gpx


def test_remove_takes_the_acma_layer_alone(
    station: Station,  # noqa: F811
    capsys: pytest.CaptureFixture[str],
) -> None:
    _install_register(station)
    _region(station, TASMANIA, "springfield")
    assert cli.main(["maps", "repeaters", "import", "--from-acma"]) == 0
    capsys.readouterr()
    code, _, _ = _run(["maps", "repeaters", "remove", "--layer", "acma"], capsys)
    assert code == 0
    assert repeaters.present_layers(station.layer) == ()
