# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The area of operations: ``active_areas``, ``maps activate`` and ``maps areas``.
D-082, D-059.

Every layer is built here from synthetic rows (N0CALL, Springfield) under a
scratch home, config and prefix; the example areas are OH, MI and FL. Nothing
reads the operator's real overlays, regions or station file.
"""

from __future__ import annotations

import importlib
import json
import os
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter

from hammunition import areas, infra, navit_config, repeaters
from hammunition.areas import Active
from hammunition.interface import areas as area_docs
from hammunition.interface.areas import AreasDocument
from hammunition.navit_config import rewrite
from hammunition.repeaters import Layer, Repeater
from hammunition.station import Station, StationError, load_station
from json_support import parse_one, validate

cli = importlib.import_module("hammunition.cli.main")

NAVIT_STOCK = (Path(__file__).resolve().parent / "fixtures" / "navit.xml").read_text()
OHIO = "north-america/us/ohio"
MICHIGAN = "north-america/us/michigan"
FLORIDA = "north-america/us/florida"


class Home:
    def __init__(self, tmp_path: Path) -> None:
        self.data = tmp_path / "data"
        self.config = tmp_path / "config"
        self.prefix = tmp_path / "prefix"
        self.overlays = self.data / "hammunition" / "overlays"
        self.layers = self.overlays / "repeaters"
        self.infra = self.overlays / "infra"
        self.links = self.overlays / "active-poi"
        self.qms = self.config / "QLandkarte" / "QMapShack.conf"
        self.station = self.config / "hammunition" / "station.yml"
        self.user_navit = self.overlays / "navit.xml"
        self.share = self.prefix / "share" / "hammunition" / "data"

    def layer(self, layer_id: str, name: str | None = None) -> None:
        row = Repeater(
            callsign="N0CALL", output_hz=146_940_000, lat=39.8, lon=-89.6, source=repeaters.HAND
        )
        layer = Layer(name or layer_id, "licence", date(2026, 10, 1), (row,))
        repeaters.write_layer(self.layers, layer, layer_id)

    def infra_layer(self) -> None:
        point = infra.Point("Testville Clinic", "clinic", 39.8, -89.6)
        infra.write_layer(
            self.infra,
            infra.InfraLayer(
                "osm-medical", "Medical", infra.OSM_LICENCE, "OSM", date(2026, 10, 1), (point,)
            ),
        )

    def region(
        self, region: str, *, pbf: bool = True, navit: bool = True, tiles: bool = True
    ) -> None:
        slug = region.replace("/", "-")
        for unit, suffix, wanted in (
            ("osm-regions", ".osm.pbf", pbf),
            ("osm-navit", ".bin", navit),
            ("osm-pmtiles", ".pmtiles", tiles),
        ):
            if wanted:
                folder = self.share / unit
                folder.mkdir(parents=True, exist_ok=True)
                (folder / f"{slug}{suffix}").write_bytes(b"x" * 100)

    def navit_config(self, *regions: str) -> None:
        folder = self.share / "osm-navit"
        folder.mkdir(parents=True, exist_ok=True)
        maps = [folder / f"{r.replace('/', '-')}.bin" for r in regions]
        (folder / "navit.xml").write_text(rewrite(NAVIT_STOCK, maps))

    def save(self, **values: Any) -> None:
        from hammunition.station import save_station

        save_station(Station(**values))

    def poi_paths(self) -> list[str]:
        for line in self.qms.read_text().splitlines():
            if line.startswith("poiPaths="):
                return [p.strip() for p in line.split("=", 1)[1].split(",")]
        return []


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Home:
    here = Home(tmp_path)
    monkeypatch.setenv("XDG_DATA_HOME", str(here.data))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(here.config))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setattr(cli, "DEFAULT_PREFIX", here.prefix)
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    return here


@pytest.fixture
def loaded(home: Home) -> Home:
    """Three states of repeaters, one layer of no area, three regions, Navit."""
    for state in ("OH", "MI", "FL"):
        home.layer(f"repeaterbook-{state}", f"RepeaterBook {state}")
    home.layer("export", "own")
    home.infra_layer()
    for region in (OHIO, MICHIGAN, FLORIDA):
        home.region(region)
    home.navit_config(OHIO, MICHIGAN, FLORIDA)
    home.save(map_regions=(OHIO, MICHIGAN, FLORIDA))
    return home


def _run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str]:
    code = cli.main(list(argv))
    return code, capsys.readouterr().out


def _json(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, dict[str, Any]]:
    code = cli.main([*argv, "--json"])
    doc = parse_one(capsys.readouterr().out)
    validate(doc)
    return code, doc


def _names(paths: list[str] | tuple[str, ...]) -> list[str]:
    return sorted(Path(p).name for p in paths)


# --- the station value --------------------------------------------------------------------


def test_active_areas_normalise_and_round_trip(home: Home) -> None:
    home.save(active_areas=("oh", "MI", OHIO, "ohio", "oh"))
    assert load_station().active_areas == ("OH", "MI", OHIO, "ohio")


def test_unset_is_none_and_empty_is_none_loaded_not_the_same(home: Home) -> None:
    assert load_station().active_areas is None
    home.save(active_areas=())
    assert load_station().active_areas == ()
    assert "active_areas: []" in home.station.read_text()
    home.save()
    assert "active_areas" not in home.station.read_text()


@pytest.mark.parametrize("bad", ["Ohio State", "north-america/", "OH!", "../etc", ""])
def test_a_bad_area_is_refused_by_name(bad: str) -> None:
    with pytest.raises(StationError, match="active area"):
        Station(active_areas=(bad,))


def test_a_malformed_file_value_is_refused(home: Home) -> None:
    home.station.parent.mkdir(parents=True)
    home.station.write_text("active_areas: OH\n")
    with pytest.raises(StationError, match="must be a list"):
        load_station()


def test_station_set_active_areas_and_clear(home: Home, capsys: pytest.CaptureFixture[str]) -> None:
    code, out = _run(capsys, "station", "set", "--active-areas", "oh", "MI")
    assert code == 0 and "2 set" in out
    assert load_station().active_areas == ("OH", "MI")
    # the saved line is a count; the note names what the operator just typed
    assert "active_areas   2 set" in out
    assert "note: not loaded yet" in out  # nothing is loaded in this home
    code, out = _run(capsys, "station", "set", "--clear-active-areas")
    assert code == 0 and load_station().active_areas is None


def test_station_set_refuses_a_bad_area_and_the_two_flags_together(
    home: Home, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["station", "set", "--active-areas", "Ohio State"]) != 0
    assert "active area" in capsys.readouterr().err
    assert cli.main(["station", "set", "--active-areas", "OH", "--clear-active-areas"]) != 0
    assert not home.station.exists()


def test_station_show_json_carries_the_value_and_text_a_count(
    home: Home, capsys: pytest.CaptureFixture[str]
) -> None:
    home.save(active_areas=("OH",))
    _, doc = _json(capsys, "station", "show")
    assert doc["active_areas"] == ["OH"]
    _, out = _run(capsys, "station", "show")
    assert "active areas" in out and "1 set" in out
    home.save()
    _, doc = _json(capsys, "station", "show")
    assert doc["active_areas"] is None


# --- the rule ---------------------------------------------------------------------------


def test_a_state_and_its_region_are_the_same_ground() -> None:
    active = Active(("OH", "florida", MICHIGAN))
    assert active.state("OH") and active.state("FL") and active.state("MI")
    assert not active.state("TX")
    universe = (OHIO, MICHIGAN, FLORIDA)
    assert active.region_slugs(universe) == {
        "north-america-us-ohio",
        "north-america-us-florida",
        "north-america-us-michigan",
        "florida",
    }
    assert active.region(OHIO) and not active.region("north-america/us/texas")
    assert active.area(None) and Active(()).area(None)  # no area: always
    assert Active().area("TX") and Active().region_slugs() is None
    assert not Active(()).state("OH")


def test_west_virginia_is_not_virginia() -> None:
    assert not Active(("virginia",)).region(
        "north-america/us/west-virginia", ("north-america/us/west-virginia",)
    )
    assert Active(("WV",)).region("north-america/us/west-virginia")


def test_an_infra_layer_with_a_region_joins_the_rule(home: Home) -> None:
    """The hook for #327: a region-named infra file is active with its region."""
    assert Active(("OH",)).area("north-america-us-ohio")
    assert not Active(("OH",)).area("north-america-us-michigan")
    assert Active(("OH",)).area(OHIO)
    assert infra.layer_area("osm-medical") is None  # every theme spans every region today


# --- maps areas -------------------------------------------------------------------------


def test_areas_lists_states_regions_layers_sizes_dates_and_activity(
    loaded: Home, capsys: pytest.CaptureFixture[str]
) -> None:
    code, doc = _json(capsys, "maps", "areas")
    assert code == 0 and doc["kind"] == "areas" and doc["active_areas"] is None
    by_area = {a["area"]: a for a in doc["areas"]}
    assert list(by_area) == ["FL", "MI", "OH", FLORIDA, MICHIGAN, OHIO]
    assert all(a["active"] for a in doc["areas"])  # unset: everything
    oh = by_area["OH"]
    assert oh["kind"] == "state" and oh["day"] == "2026-10-01"
    assert [layer["id"] for layer in oh["layers"]] == ["repeaterbook-OH"]
    assert oh["layers"][0]["rows"] == 1
    assert oh["size_bytes"] == sum(Path(f).stat().st_size for f in oh["layers"][0]["files"])
    region = by_area[OHIO]
    assert [layer["id"] for layer in region["layers"]] == ["extract", "navit", "tiles"]
    assert region["size_bytes"] == 300
    assert doc["always_active"] == ["export", "osm-medical"]
    assert doc["unloaded"] == []


def test_areas_text_renders_the_document(loaded: Home, capsys: pytest.CaptureFixture[str]) -> None:
    _, doc = _json(capsys, "maps", "areas")
    code, out = _run(capsys, "maps", "areas")
    assert code == 0
    assert "Active: everything loaded" in out and "Always active (no area)" in out
    for area in doc["areas"]:
        assert area["area"] in out
    # the text is the document's own rendering
    body = {k: v for k, v in doc.items() if k not in ("schema", "kind", "engine")}
    rebuilt = TypeAdapter(AreasDocument).validate_python(body)
    assert out.splitlines() == area_docs.render_areas(rebuilt)


def test_areas_follows_active_areas_and_names_what_is_not_loaded(
    loaded: Home, capsys: pytest.CaptureFixture[str]
) -> None:
    loaded.save(map_regions=(OHIO, MICHIGAN, FLORIDA), active_areas=("OH", "TX"))
    _, doc = _json(capsys, "maps", "areas")
    active = {a["area"]: a["active"] for a in doc["areas"]}
    # OH and its region are one ground; the others are not active
    assert active == {
        "FL": False,
        "MI": False,
        "OH": True,
        FLORIDA: False,
        MICHIGAN: False,
        OHIO: True,
    }
    assert doc["unloaded"] == ["TX"] and doc["active_areas"] == ["OH", "TX"]


def test_areas_with_nothing_loaded_is_empty_and_writes_nothing(
    home: Home, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out = _run(capsys, "maps", "areas")
    assert code == 0 and "No state or region is loaded." in out
    assert not home.overlays.exists() and not home.station.exists()


# --- maps activate ------------------------------------------------------------------------


def test_unset_means_everything_and_the_layer_directories_are_registered(
    loaded: Home, capsys: pytest.CaptureFixture[str]
) -> None:
    code, doc = _json(capsys, "maps", "activate", "--all")
    assert code == 0 and doc["after"] is None and doc["changed"] is False
    assert doc["poi_paths"] == [str(loaded.layers), str(loaded.infra)]
    assert _names(doc["poi_files"]) == sorted(
        [
            "infra-osm-medical.poi",
            "repeaters.poi",
            "repeaters-repeaterbook-FL.poi",
            "repeaters-repeaterbook-MI.poi",
            "repeaters-repeaterbook-OH.poi",
        ]
    )
    assert loaded.poi_paths() == [str(loaded.layers), str(loaded.infra)]
    assert not loaded.links.exists()


def test_activate_registers_only_the_active_areas_poi_files(
    loaded: Home, capsys: pytest.CaptureFixture[str]
) -> None:
    code, doc = _json(capsys, "maps", "activate", "OH")
    assert code == 0 and doc["after"] == ["OH"] and doc["changed"] and doc["before"] is None
    # QMapShack's conf: the one directory of links, neither layer directory
    assert loaded.poi_paths() == [str(loaded.links)]
    assert doc["poi_paths"] == [str(loaded.links)]
    assert sorted(p.name for p in loaded.links.iterdir()) == [
        "infra-osm-medical.poi",
        "repeaters-repeaterbook-OH.poi",
        "repeaters.poi",
    ]
    assert all(p.is_symlink() for p in loaded.links.iterdir())
    assert (loaded.links / "repeaters-repeaterbook-OH.poi").resolve() == (
        loaded.layers / "repeaters-repeaterbook-OH.poi"
    ).resolve()
    assert _names(doc["poi_files"]) == sorted(p.name for p in loaded.links.iterdir())
    assert load_station().active_areas == ("OH",)
    assert [r["program"] for r in doc["registered"]] == ["qmapshack", "navit"]


def test_activate_writes_the_conf_exactly_as_maps_qmapshack_does(
    loaded: Home, capsys: pytest.CaptureFixture[str]
) -> None:
    loaded.qms.parent.mkdir(parents=True)
    loaded.qms.write_text("[Canvas]\nmapPath=/maps\n\n[Units]\ntype=metric\n")
    assert cli.main(["maps", "activate", "MI", "OH"]) == 0
    after = loaded.qms.read_text()
    assert after == f"[Canvas]\nmapPath=/maps\npoiPaths={loaded.links}\n\n[Units]\ntype=metric\n"
    # `maps qmapshack` keeps the same list, with a QMapShack that rewrote it on exit
    loaded.qms.write_text("[Canvas]\nmapPath=/maps\n")
    assert cli.main(["maps", "qmapshack", "--configure-only"]) == 0
    assert loaded.poi_paths() == [str(loaded.links)]
    # and the links are still the two states'
    assert sorted(p.name for p in loaded.links.iterdir()) == [
        "infra-osm-medical.poi",
        "repeaters-repeaterbook-MI.poi",
        "repeaters-repeaterbook-OH.poi",
        "repeaters.poi",
    ]


def test_activate_is_idempotent(loaded: Home, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["maps", "activate", "OH", "MI"]) == 0
    first = (loaded.qms.stat().st_mtime_ns, loaded.user_navit.read_text())
    capsys.readouterr()
    code, doc = _json(capsys, "maps", "activate", "OH", "MI")
    assert code == 0 and doc["changed"] is False
    assert loaded.qms.stat().st_mtime_ns == first[0]  # not rewritten
    assert loaded.user_navit.read_text() == first[1]
    assert doc["links_added"] == [] and doc["links_dropped"] == []
    assert doc["registered"][0]["outcome"] == "already there"


def test_navit_gets_the_active_regions_and_overlays_only(
    loaded: Home, capsys: pytest.CaptureFixture[str]
) -> None:
    code, doc = _json(capsys, "maps", "activate", "OH", FLORIDA)
    assert code == 0
    text = loaded.user_navit.read_text()
    assert "north-america-us-ohio.bin" in text and "north-america-us-florida.bin" in text
    assert "north-america-us-michigan.bin" not in text
    assert doc["navit_regions"] == ["north-america-us-ohio", "north-america-us-florida"]
    assert doc["navit_left_out"] == ["north-america-us-michigan"]
    # overlays: the FL and OH layers, the own layer and the infrastructure theme; not MI
    assert _names(doc["navit_overlays"]) == [
        "infra-osm-medical.navit.txt",
        "repeaters-repeaterbook-FL.navit.txt",
        "repeaters-repeaterbook-OH.navit.txt",
        "repeaters.navit.txt",
    ]
    assert text.count('type="textfile"') == 4
    assert navit_config.binfile_stems(text) == (
        "north-america-us-ohio",
        "north-america-us-florida",
    )
    # the generated configuration, root's, is not touched
    assert "north-america-us-michigan.bin" in (loaded.share / "osm-navit" / "navit.xml").read_text()


def test_maps_navit_opens_the_filtered_copy(loaded: Home, monkeypatch: pytest.MonkeyPatch) -> None:
    assert cli.main(["maps", "activate", "OH"]) == 0
    seen: list[list[str]] = []

    class Exec(Exception):
        pass

    def execvp(file: str, argv: list[str]) -> None:
        seen.append(argv)
        raise Exec

    monkeypatch.setattr(os, "execvp", execvp)
    with pytest.raises(Exec):
        cli.main(["maps", "navit"])
    assert seen == [["navit", str(loaded.user_navit)]]
    assert "north-america-us-michigan.bin" not in loaded.user_navit.read_text()


def test_the_browser_list_is_the_active_regions(
    loaded: Home, capsys: pytest.CaptureFixture[str]
) -> None:
    from hammunition.map_page import find_map, regions_json

    assert find_map(loaded.share, loaded.infra).regions == (
        "north-america-us-florida",
        "north-america-us-michigan",
        "north-america-us-ohio",
    )
    _, doc = _json(capsys, "maps", "activate", "MI")
    assert doc["browser"]["regions"] == ["north-america-us-michigan"]
    assert doc["browser"]["overlays"] == ["osm-medical"]  # no area: always drawn
    shelf = find_map(
        loaded.share, loaded.infra, active=Active(("MI",)), universe=(OHIO, MICHIGAN, FLORIDA)
    )
    assert json.loads(regions_json(shelf)) == [
        {"name": "north-america-us-michigan", "url": "/map/tiles/north-america-us-michigan.pmtiles"}
    ]
    assert (
        "north-america-us-ohio.pmtiles" not in {k.rsplit("/", 1)[-1] for k in shelf.files} | set()
    )


def test_none_leaves_every_file_on_disk_and_all_brings_it_back(
    loaded: Home, capsys: pytest.CaptureFixture[str]
) -> None:
    def tree() -> dict[str, int]:
        return {
            str(p.relative_to(loaded.data.parent)): p.stat().st_size
            for root in (loaded.overlays, loaded.share)
            for p in root.rglob("*")
            if p.is_file() and not p.is_symlink() and p.name != "navit.xml"
        }

    before = tree()
    code, doc = _json(capsys, "maps", "activate", "--none")
    assert code == 0 and doc["after"] == []
    assert tree() == before  # nothing deleted
    # only what belongs to no area is registered
    assert sorted(p.name for p in loaded.links.iterdir()) == [
        "infra-osm-medical.poi",
        "repeaters.poi",
    ]
    assert doc["navit_regions"] == [] and len(doc["navit_left_out"]) == 3
    assert doc["browser"]["regions"] == []
    _, doc = _json(capsys, "maps", "activate", "--all")
    assert tree() == before
    assert not loaded.links.exists()  # derived, removed with the filter
    assert loaded.poi_paths() == [str(loaded.layers), str(loaded.infra)]
    assert load_station().active_areas is None
    assert len(doc["navit_regions"]) == 3


def test_dry_run_writes_nothing(loaded: Home, capsys: pytest.CaptureFixture[str]) -> None:
    station_before = loaded.station.read_text()
    code, doc = _json(capsys, "maps", "activate", "OH", "--dry-run")
    assert code == 0 and doc["dry_run"] and doc["after"] == ["OH"] and doc["changed"]
    assert doc["registered"] == []
    assert doc["links_added"] and _names(doc["poi_files"])
    assert loaded.station.read_text() == station_before
    assert not loaded.qms.exists() and not loaded.links.exists() and not loaded.user_navit.exists()
    _, out = _run(capsys, "maps", "activate", "OH", "--dry-run")
    assert "Would set the active areas to OH" in out and "Dry run: nothing was written." in out


def test_an_area_not_loaded_is_accepted_with_a_note(
    loaded: Home, capsys: pytest.CaptureFixture[str]
) -> None:
    code, doc = _json(capsys, "maps", "activate", "OH", "TX")
    assert code == 0 and doc["unloaded"] == ["TX"]
    assert load_station().active_areas == ("OH", "TX")
    code, out = _run(capsys, "maps", "activate", "OH", "TX")
    assert "Not loaded, accepted: TX" in out


def test_activate_refuses_a_bad_area_no_mode_two_modes_and_root(
    loaded: Home, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    for argv in (
        ["maps", "activate"],
        ["maps", "activate", "OH", "--all"],
        ["maps", "activate", "--all", "--none"],
    ):
        assert cli.main(argv) == 1, argv
        assert "name the areas" in capsys.readouterr().err
    assert cli.main(["maps", "activate", "Ohio State"]) == 1
    assert "active area" in capsys.readouterr().err
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    assert cli.main(["maps", "activate", "OH"]) == 1
    assert "per user" in capsys.readouterr().err
    assert load_station().active_areas is None


def test_activate_text_renders_the_document(
    loaded: Home, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out = _run(capsys, "maps", "activate", "OH")
    assert code == 0
    assert "Set the active areas to OH (was everything loaded)." in out
    assert "QMapShack POI files: 3" in out and "Browser map: 1 regions" in out
    assert "stay registered whichever areas are active" in out


def test_without_navit_or_regions_activate_still_works(
    home: Home, capsys: pytest.CaptureFixture[str]
) -> None:
    home.layer("repeaterbook-OH")
    home.layer("repeaterbook-MI")
    code, doc = _json(capsys, "maps", "activate", "MI")
    assert code == 0 and doc["navit_regions"] == [] and doc["navit_left_out"] == []
    assert _names(doc["poi_files"]) == ["repeaters-repeaterbook-MI.poi"]
    assert doc["registered"][0]["outcome"] == "added"


# --- the flag in the documents --------------------------------------------------------------


def test_repeaters_list_carries_active_per_layer(
    loaded: Home, capsys: pytest.CaptureFixture[str]
) -> None:
    _, doc = _json(capsys, "maps", "repeaters", "list")
    assert {layer["id"]: layer["active"] for layer in doc["layers"]} == {
        "export": True,
        "repeaterbook-FL": True,
        "repeaterbook-MI": True,
        "repeaterbook-OH": True,
    }
    assert cli.main(["maps", "activate", "OH"]) == 0
    capsys.readouterr()
    _, doc = _json(capsys, "maps", "repeaters", "list")
    assert {layer["id"]: layer["active"] for layer in doc["layers"]} == {
        "export": True,
        "repeaterbook-FL": False,
        "repeaterbook-MI": False,
        "repeaterbook-OH": True,
    }
    assert cli.main(["maps", "activate", "--none"]) == 0
    capsys.readouterr()
    _, doc = _json(capsys, "maps", "repeaters", "list")
    assert [layer["id"] for layer in doc["layers"] if layer["active"]] == ["export"]


def test_a_repeater_import_keeps_the_filter_in_step(
    loaded: Home, capsys: pytest.CaptureFixture[str]
) -> None:
    """Registering after an import does not put the layer directories back."""
    assert cli.main(["maps", "activate", "OH"]) == 0
    loaded.layer("repeaterbook-OH", "refreshed")
    registered = cli._register_repeaters(loaded.layers)
    assert registered[0].outcome == "already there"
    assert loaded.poi_paths() == [str(loaded.links)]
    # a new state's layer is not drawn until its area is
    loaded.layer("repeaterbook-TX")
    cli._register_repeaters(loaded.layers)
    assert "repeaters-repeaterbook-TX.poi" not in {p.name for p in loaded.links.iterdir()}


def test_infra_import_document_carries_active(
    loaded: Home, capsys: pytest.CaptureFixture[str]
) -> None:
    from hammunition.interface.infra import InfraLayerView

    view = InfraLayerView("osm-medical", "Medical", 1, (), (), True)
    assert view.active is True
    assert cli._layer_active(infra.layer_area("osm-medical")) is True
    assert cli.main(["maps", "activate", "--none"]) == 0
    assert cli._layer_active(infra.layer_area("osm-medical")) is True  # no area: always
    assert cli._layer_active("OH") is False


def test_links_are_the_only_thing_removed(loaded: Home) -> None:
    plan = areas.plan_poi_links(loaded.overlays, loaded.layers, loaded.infra, Active(("OH",)))
    areas.sync_poi_links(plan)
    (loaded.links / "keep-me.txt").write_text("mine")
    areas.sync_poi_links(
        areas.plan_poi_links(loaded.overlays, loaded.layers, loaded.infra, Active(()))
    )
    assert (loaded.links / "keep-me.txt").read_text() == "mine"
    assert (loaded.layers / "repeaters-repeaterbook-OH.poi").is_file()
    assert not (loaded.links / "repeaters-repeaterbook-OH.poi").exists()
