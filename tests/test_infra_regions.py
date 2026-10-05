# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Infrastructure layers kept per region.  D-075 amended, D-082, issue #327.

Scratch homes only; osmium is stubbed with the synthetic OSM file, and no
test touches the network or the maintainer's own directories. The regions are
``delaware`` and ``vermont``.
"""

# ruff: noqa: F811
from __future__ import annotations

import importlib
from datetime import date
from pathlib import Path

import pytest

import test_infra_sources as sources_test
from hammunition import infra
from hammunition.areas import Active
from hammunition.map_page import find_overlays
from json_support import parse_one, validate
from test_areas import Home, home  # noqa: F401
from test_infra_cli import (  # noqa: F401
    Station,
    _install_unit,
    _run,
    osmium,
    station,
)

cli = importlib.import_module("hammunition.cli.main")

DELAWARE = "delaware"
VERMONT = "vermont"
VERMONT_BOX = (-73.44, -71.46, 45.02, 42.73)  # left, right, top, bottom
OHIO = "north-america-us-ohio"
MICHIGAN = "north-america-us-michigan"


def _import(station: Station, capsys: pytest.CaptureFixture[str], *argv: str) -> dict[str, object]:
    code, out, err = _run(["maps", "infra", "import", *argv, "--json"], capsys)
    assert code == 0, err
    doc = parse_one(out)
    validate(doc)
    return doc


def _two_regions(station: Station) -> None:
    station.install_navit()
    station.install_region(DELAWARE)
    station.install_region(VERMONT, box=VERMONT_BOX)


# --- ids and areas ------------------------------------------------------------------


def test_layer_area_for_both_shapes() -> None:
    assert infra.layer_area("osm-medical") is None  # merged: every region
    assert infra.layer_area(f"osm-medical-{DELAWARE}") == DELAWARE
    assert infra.layer_area(f"faa-airports-{OHIO}") == OHIO
    assert infra.layer_base(f"osm-shelter-candidates-{OHIO}") == "osm-shelter-candidates"
    assert infra.layer_files(f"osm-water-{VERMONT}")[1] == f"infra-osm-water-{VERMONT}.poi"
    for bad in ("osm-medical-", "osm-medical-Ohio", "nonsense", f"-{DELAWARE}"):
        assert not infra.is_layer_id(bad)
        with pytest.raises(ValueError):
            infra.layer_area(bad)


def test_the_region_slug_is_the_extract_slug_areas_uses() -> None:
    from hammunition import areas

    slug = areas._slug("north-america/us/ohio")
    assert slug == OHIO
    assert infra.layer_area(infra.region_layer_id("osm-power", slug)) == slug
    assert Active(("OH",)).area(infra.layer_area(f"osm-power-{OHIO}"))
    assert not Active(("OH",)).area(infra.layer_area(f"osm-power-{MICHIGAN}"))


# --- import ---------------------------------------------------------------------------


def test_two_regions_write_two_files_per_theme(
    station: Station, capsys: pytest.CaptureFixture[str], osmium: list[list[str]]
) -> None:
    _two_regions(station)
    doc = _import(station, capsys, "--from-osm")
    assert len(osmium) == 2
    layers = doc["layers"]
    assert isinstance(layers, list) and len(layers) == 16
    ids = [layer["layer_id"] for layer in layers]
    assert len(set(ids)) == 16
    assert {layer["area"] for layer in layers} == {DELAWARE, VERMONT}
    assert all(layer["active"] for layer in layers)  # active_areas unset
    medical = [layer for layer in layers if layer["layer_id"].startswith("osm-medical-")]
    assert sorted(layer["layer_id"] for layer in medical) == [
        f"osm-medical-{DELAWARE}",
        f"osm-medical-{VERMONT}",
    ]
    assert all(layer["name"].endswith(f"[{layer['area']}]") for layer in medical)
    for layer_id in ids:
        for name in infra.layer_files(layer_id):
            assert (station.layer / name).is_file()
    assert infra.present_layers(station.layer) == tuple(ids)
    assert not (station.layer / "infra-osm-medical.gpx").exists()


def test_merged_keeps_todays_shape(
    station: Station, capsys: pytest.CaptureFixture[str], osmium: list[list[str]]
) -> None:
    _two_regions(station)
    doc = _import(station, capsys, "--from-osm", "--merged")
    assert [layer["area"] for layer in doc["layers"]] == [None] * 8  # type: ignore[attr-defined]
    assert infra.present_layers(station.layer) == tuple(f"osm-{k}" for k in infra.OSM_LAYERS)
    assert doc["notes"] == [
        "filtered on this machine from the region extracts already here; nothing downloaded"
    ]


def test_data_unit_layers_are_clipped_to_each_regions_box(
    station: Station, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    _two_regions(station)
    _install_unit(station, "nasr", sources_test._nasr(tmp_path, sources_test.NASR_ROWS))
    doc = _import(station, capsys, "--from-nasr")
    by_area = {layer["area"]: layer for layer in doc["layers"]}  # type: ignore[attr-defined]
    assert by_area[DELAWARE]["written"] == 3 and by_area[DELAWARE]["layer_id"] == (
        f"faa-airports-{DELAWARE}"
    )
    assert by_area[VERMONT]["written"] == 1 and len(by_area[VERMONT]["files"]) == 4
    assert doc["outside"] == 0  # the fourth row lies in the second region's box
    assert infra.present_layers(station.layer) == (
        f"faa-airports-{DELAWARE}",
        f"faa-airports-{VERMONT}",
    )


# --- activation -----------------------------------------------------------------------


def _region_infra(home: Home, slug: str) -> None:
    point = infra.Point("Testville Clinic", "clinic", 39.8, -89.6)
    layer = infra.InfraLayer(
        "osm-medical", "Medical", infra.OSM_LICENCE, "OSM", date(2026, 10, 1), (point,)
    )
    infra.write_layer(home.infra, infra.region_layer(layer, slug, [point]))


def test_activating_one_region_registers_only_that_regions_infra(
    home: Home, capsys: pytest.CaptureFixture[str]
) -> None:
    for slug in (OHIO, MICHIGAN):
        _region_infra(home, slug)
        home.region(slug.replace("north-america-us-", "north-america/us/"))
    home.infra_layer()  # a merged layer: no area, always active
    home.save(map_regions=("north-america/us/ohio", "north-america/us/michigan"))
    assert cli.main(["maps", "activate", "OH"]) == 0
    capsys.readouterr()
    assert sorted(p.name for p in home.links.iterdir()) == [
        f"infra-osm-medical-{OHIO}.poi",
        "infra-osm-medical.poi",
    ]
    navit = {p.name for p in cli._overlay_navit_maps(Active(("OH",)))}
    assert navit == {f"infra-osm-medical-{OHIO}.navit.txt", "infra-osm-medical.navit.txt"}
    shown = {o.layer_id for o in find_overlays(home.infra, Active(("OH",)))}
    assert shown == {f"osm-medical-{OHIO}", "osm-medical"}
    assert {o.layer_id for o in find_overlays(home.infra, None)} == {
        f"osm-medical-{OHIO}",
        f"osm-medical-{MICHIGAN}",
        "osm-medical",
    }


def test_maps_areas_lists_a_regions_infra_under_that_region(
    home: Home, capsys: pytest.CaptureFixture[str]
) -> None:
    _region_infra(home, OHIO)
    home.region("north-america/us/ohio")
    home.save(map_regions=("north-america/us/ohio",))
    assert cli.main(["maps", "areas", "--json"]) == 0
    doc = parse_one(capsys.readouterr().out)
    validate(doc)
    ohio = next(a for a in doc["areas"] if a["area"] == "north-america/us/ohio")
    assert [layer["id"] for layer in ohio["layers"]] == [
        f"osm-medical-{OHIO}",
        "extract",
        "navit",
        "tiles",
    ]
    assert doc["always_active"] == []


# --- migration ------------------------------------------------------------------------


def test_the_migration_note_appears_only_while_a_merged_layer_exists(
    station: Station, capsys: pytest.CaptureFixture[str], osmium: list[list[str]]
) -> None:
    _two_regions(station)
    first = _import(station, capsys, "--from-osm", "--layers", "medical")
    assert not any("earlier merged" in n for n in first["notes"])  # type: ignore[attr-defined]
    _import(station, capsys, "--from-osm", "--layers", "medical", "--merged")
    again = _import(station, capsys, "--from-osm", "--layers", "medical")
    notes = [n for n in again["notes"] if "earlier merged" in n]  # type: ignore[attr-defined]
    assert len(notes) == 1 and "(osm-medical)" in notes[0] and "nothing was deleted" in notes[0]
    assert (station.layer / "infra-osm-medical.gpx").is_file()  # never deleted by the engine
    code, _, err = _run(["maps", "infra", "remove", "--layer", "osm-medical"], capsys)
    assert code == 0, err
    last = _import(station, capsys, "--from-osm", "--layers", "medical")
    assert not any("earlier merged" in n for n in last["notes"])  # type: ignore[attr-defined]


def test_the_note_is_text_too(
    station: Station, capsys: pytest.CaptureFixture[str], osmium: list[list[str]]
) -> None:
    _two_regions(station)
    assert cli.main(["maps", "infra", "import", "--from-osm", "--merged"]) == 0
    capsys.readouterr()
    code, out, _ = _run(["maps", "infra", "import", "--from-osm"], capsys)
    assert code == 0 and out.count("Note: the earlier merged layers (") == 1


# --- remove ---------------------------------------------------------------------------


def test_remove_one_regions_layer_leaves_the_other(
    station: Station, capsys: pytest.CaptureFixture[str], osmium: list[list[str]]
) -> None:
    _two_regions(station)
    assert cli.main(["maps", "infra", "import", "--from-osm", "--layers", "water"]) == 0
    capsys.readouterr()
    code, out, err = _run(
        ["maps", "infra", "remove", "--layer", f"osm-water-{DELAWARE}", "--json"], capsys
    )
    assert code == 0, err
    doc = parse_one(out)
    validate(doc)
    assert doc["layers"] == [f"osm-water-{DELAWARE}"]
    assert infra.present_layers(station.layer) == (f"osm-water-{VERMONT}",)
    with pytest.raises(SystemExit):  # argparse refuses an id that is no layer
        cli.main(["maps", "infra", "remove", "--layer", "osm-water-Nowhere"])
    capsys.readouterr()
    code, out, _ = _run(["maps", "infra", "remove", "--json"], capsys)
    doc = parse_one(out)
    assert f"osm-water-{VERMONT}" in doc["layers"] and len(doc["removed"]) == 4
    assert infra.present_layers(station.layer) == ()


def test_a_themes_id_removes_only_the_merged_layer(
    station: Station, capsys: pytest.CaptureFixture[str], osmium: list[list[str]]
) -> None:
    _two_regions(station)
    assert cli.main(["maps", "infra", "import", "--from-osm", "--layers", "water", "--merged"]) == 0
    assert cli.main(["maps", "infra", "import", "--from-osm", "--layers", "water"]) == 0
    capsys.readouterr()
    assert cli.main(["maps", "infra", "remove", "--layer", "osm-water"]) == 0
    assert infra.present_layers(station.layer) == (
        f"osm-water-{DELAWARE}",
        f"osm-water-{VERMONT}",
    )
