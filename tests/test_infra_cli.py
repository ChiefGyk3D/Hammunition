# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``maps infra``, end to end.  D-075.

Every run is against a scratch home, config and prefix. osmium is stubbed
with the synthetic OSM file; the federal files are built by the tests;
the fetches are served from 127.0.0.1 in this process. No GUI starts. The
extracts' region is called ``testville``, and no region, place name or
coordinate may reach the terminal or a document.
"""

from __future__ import annotations

import hashlib
import http.server
import importlib
import os
import shutil
import subprocess
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import ClassVar

import pytest

import test_infra_sources as sources_test
from hammunition import infra, infra_sources, repeaters
from hammunition.interface.infra import render_infra
from hammunition.navit_config import rewrite
from json_support import assert_text_values_in_json, parse_one, validate
from test_osm_pbf import pbf

cli = importlib.import_module("hammunition.cli.main")

FIXTURES = Path(__file__).resolve().parent / "fixtures"
OSM = FIXTURES / "infra" / "osm-infra.osm"
NAVIT_STOCK = (FIXTURES / "navit.xml").read_text()
#: The fixture's region box: Delaware's, as the spike's extract carried it.
DELAWARE = (-75.79, -74.96, 40.03, 38.45)  # left, right, top, bottom
#: Nothing named or placed may reach the terminal or a document (D-057).
PRIVATE = ("Testville", "testville", "boxless", "38.7", "-75.5", "38.45", "-75.79")


class Station:
    def __init__(self, tmp_path: Path) -> None:
        self.root = tmp_path
        self.data = tmp_path / "data"
        self.config = tmp_path / "config"
        self.prefix = tmp_path / "prefix"
        self.overlays = self.data / "hammunition" / "overlays"
        self.layer = self.overlays / "infra"
        self.repeaters = self.overlays / "repeaters"
        self.qms = self.config / "QLandkarte" / "QMapShack.conf"
        self.share = self.prefix / "share" / "hammunition" / "data"
        self.generated = self.share / "osm-navit" / "navit.xml"
        self.user_navit = self.overlays / "navit.xml"

    def install_navit(self) -> None:
        self.generated.parent.mkdir(parents=True, exist_ok=True)
        self.generated.write_text(rewrite(NAVIT_STOCK, [self.generated.parent / "a.bin"]))

    def install_region(
        self,
        slug: str = "testville",
        snapshot: str = "260930",
        box: tuple[float, float, float, float] | None = DELAWARE,
    ) -> Path:
        folder = self.share / "osm-regions"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{slug}.osm.pbf"
        path.write_bytes(pbf(box))
        (folder / f"{slug}.osm.pbf.source").write_text(f"{snapshot}\n")
        return path

    def text(self) -> str:
        return "".join(
            p.read_text(errors="replace") for p in self.layer.iterdir() if p.suffix != ".poi"
        )


@pytest.fixture
def station(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Station:
    here = Station(tmp_path)
    monkeypatch.setenv("XDG_DATA_HOME", str(here.data))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(here.config))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setattr(cli, "DEFAULT_PREFIX", here.prefix)
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    return here


@pytest.fixture
def osmium(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """osmium stubbed: every extract filters to the synthetic OSM file."""
    seen: list[list[str]] = []

    def run(argv: list[str]) -> subprocess.CompletedProcess[str]:
        seen.append(argv)
        Path(argv[argv.index("-o") + 1]).write_text(OSM.read_text())
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(infra, "_run", run)
    return seen


def _run(argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    code = cli.main(argv)
    out, err = capsys.readouterr()
    return code, out, err


def _no_private(text: str) -> None:
    leaked = [p for p in PRIVATE if p in text]
    assert not leaked, f"printed {leaked}"


# --- OpenStreetMap -----------------------------------------------------------------


def test_from_osm_writes_the_eight_layers_and_registers_them(
    station: Station, capsys: pytest.CaptureFixture[str], osmium: list[list[str]]
) -> None:
    station.install_navit()
    station.install_region()
    code, out, err = _run(["maps", "infra", "import", "--from-osm"], capsys)
    assert code == 0, err
    assert len(osmium) == 1
    assert infra.OSM_LICENCE in out
    assert infra.present_layers(station.layer) == tuple(f"osm-{k}" for k in infra.OSM_LAYERS)
    assert "Medical (OpenStreetMap, ODbL, 2026-09-30): 3 points" in out
    assert (
        "Shelter candidates (OpenStreetMap, ODbL, 2026-09-30; candidate, not a designated "
        "shelter): 3 points" in out
    )
    assert "Read: 21 objects, 1 skipped (no usable position: 1)" in out
    assert "nothing downloaded" in out
    assert f"poiPaths={station.layer}" in station.qms.read_text()
    navit = station.user_navit.read_text()
    assert "infra-osm-medical.navit.txt" in navit and "infra-osm-water.navit.txt" in navit
    _no_private(out + err)


def test_layers_picks_some_and_leaves_the_others(
    station: Station, capsys: pytest.CaptureFixture[str], osmium: list[list[str]]
) -> None:
    station.install_region()
    assert cli.main(["maps", "infra", "import", "--from-osm"]) == 0
    capsys.readouterr()
    code, out, _ = _run(
        ["maps", "infra", "import", "--from-osm", "--layers", "medical,water"], capsys
    )
    assert code == 0
    assert "nwr/amenity=hospital,clinic,doctors,pharmacy" in osmium[-1]
    assert not any("power" in a for a in osmium[-1])
    assert len(infra.present_layers(station.layer)) == 8
    assert "Supply" not in out


def test_an_unknown_layer_is_refused_by_name(
    station: Station, capsys: pytest.CaptureFixture[str], osmium: list[list[str]]
) -> None:
    station.install_region()
    code, _, err = _run(
        ["maps", "infra", "import", "--from-osm", "--layers", "medical,shelters"], capsys
    )
    assert code == cli.EXIT_FAILED
    assert "no OpenStreetMap layer 'shelters'" in err and "shelter-candidates" in err
    assert osmium == [] and not station.layer.exists()


def test_layers_only_with_from_osm(station: Station, capsys: pytest.CaptureFixture[str]) -> None:
    code, _, err = _run(["maps", "infra", "import", "--from-nasr", "--layers", "medical"], capsys)
    assert code == cli.EXIT_FAILED and "--layers picks OpenStreetMap layers" in err


def test_a_layer_that_empties_is_removed_and_said(
    station: Station,
    capsys: pytest.CaptureFixture[str],
    osmium: list[list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    station.install_region()
    assert cli.main(["maps", "infra", "import", "--from-osm"]) == 0
    capsys.readouterr()
    no_water = OSM.read_text().replace('v="water_tower"', 'v="nothing"')
    no_water = no_water.replace('v="wastewater_plant"', 'v="nothing"')

    def run(argv: list[str]) -> subprocess.CompletedProcess[str]:
        Path(argv[argv.index("-o") + 1]).write_text(no_water)
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(infra, "_run", run)
    code, out, _ = _run(["maps", "infra", "import", "--from-osm", "--json"], capsys)
    assert code == 0
    doc = parse_one(out)
    water = next(v for v in doc["layers"] if v["layer_id"] == "osm-water")
    assert water["written"] == 0 and water["files"] == []
    assert len(water["removed"]) == 4
    assert "osm-water" not in infra.present_layers(station.layer)


def test_an_import_that_finds_nothing_changes_nothing(
    station: Station,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    osmium: list[list[str]],
) -> None:
    station.install_region()
    assert cli.main(["maps", "infra", "import", "--from-osm"]) == 0
    capsys.readouterr()

    def empty(argv: list[str]) -> subprocess.CompletedProcess[str]:
        Path(argv[argv.index("-o") + 1]).write_text('<osm version="0.6"/>')
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(infra, "_run", empty)
    code, _, err = _run(["maps", "infra", "import", "--from-osm"], capsys)
    assert code == cli.EXIT_FAILED and "Nothing was changed" in err
    assert len(infra.present_layers(station.layer)) == 8


def test_overlapping_extracts_keep_a_place_once(
    station: Station, capsys: pytest.CaptureFixture[str], osmium: list[list[str]]
) -> None:
    station.install_region("a-testville")
    station.install_region("b-testville")
    code, out, _ = _run(["maps", "infra", "import", "--from-osm", "--json"], capsys)
    assert code == 0 and len(osmium) == 2
    doc = parse_one(out)
    assert doc["merged"] == 20
    medical = next(v for v in doc["layers"] if v["layer_id"] == "osm-medical")
    assert medical["written"] == 3


def test_from_osm_with_no_region_installed_says_what_to_install(
    station: Station, capsys: pytest.CaptureFixture[str], osmium: list[list[str]]
) -> None:
    code, _, err = _run(["maps", "infra", "import", "--from-osm"], capsys)
    assert code == cli.EXIT_FAILED and "hammunition install osm-regions" in err


def test_a_failing_osmium_names_the_extract_by_number(
    station: Station, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    path = station.install_region()

    def fails(argv: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, 1, "", f"Open failed for '{path}'")

    monkeypatch.setattr(infra, "_run", fails)
    code, out, err = _run(["maps", "infra", "import", "--from-osm"], capsys)
    assert code == cli.EXIT_FAILED and "region extract 1 of 1" in err
    _no_private(out + err)


def test_the_json_document_validates_and_carries_nothing_private(
    station: Station, capsys: pytest.CaptureFixture[str], osmium: list[list[str]]
) -> None:
    station.install_region()
    code = cli.main(["maps", "infra", "import", "--from-osm", "--json"])
    raw = capsys.readouterr().out
    assert code == 0
    doc = parse_one(raw)
    validate(doc)
    assert doc["kind"] == "infra" and doc["route"] == "osm"
    assert doc["licences"] == [infra.OSM_LICENCE]
    (only,) = doc["inputs"]
    assert only["path"].endswith("osm-regions") and only["sha256"] == ""
    _no_private(raw)
    assert cli.main(["maps", "infra", "import", "--from-osm"]) == 0
    text = capsys.readouterr().out
    assert_text_values_in_json(text, doc, render_infra)


def test_root_is_refused(
    station: Station, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    for argv in (["import", "--from-osm"], ["remove"], ["fetch-nwr"], ["fetch-fcc-asr"]):
        code, _, err = _run(["maps", "infra", *argv], capsys)
        assert code == cli.EXIT_FAILED and "not as root" in err


# --- remove -------------------------------------------------------------------------


def test_remove_one_layer_then_all_idempotently(
    station: Station, capsys: pytest.CaptureFixture[str], osmium: list[list[str]]
) -> None:
    station.install_navit()
    station.install_region()
    assert cli.main(["maps", "infra", "import", "--from-osm"]) == 0
    capsys.readouterr()
    code, out, _ = _run(["maps", "infra", "remove", "--layer", "osm-medical", "--json"], capsys)
    assert code == 0
    doc = parse_one(out)
    validate(doc)
    assert doc["kind"] == "infra-removed" and doc["layers"] == ["osm-medical"]
    assert len(doc["removed"]) == 4
    assert "infra-osm-medical" not in station.user_navit.read_text()
    assert cli.main(["maps", "infra", "remove"]) == 0
    assert not station.layer.exists()
    assert f"poiPaths={station.layer}" not in station.qms.read_text()
    assert not station.user_navit.exists()
    code, out, _ = _run(["maps", "infra", "remove"], capsys)
    assert code == 0 and "Nothing to remove" in out


# --- registration shared with the repeaters (Task 8) --------------------------------


def test_repeater_and_infra_layers_share_the_navit_copy_and_both_stay(
    station: Station, capsys: pytest.CaptureFixture[str], osmium: list[list[str]]
) -> None:
    station.install_navit()
    station.install_region()
    hand = station.root / "hand.csv"
    hand.write_text(
        "callsign,output_mhz,offset_mhz,tone,mode,lat,lon,name,notes\n"
        "N0CALL,146.940,-0.6,100.0,FM,38.7,-75.5,Test,\n"
    )
    assert cli.main(["maps", "repeaters", "import", str(hand)]) == 0
    assert cli.main(["maps", "infra", "import", "--from-osm"]) == 0
    navit = station.user_navit.read_text()
    assert repeaters.FILES[2] in navit and "infra-osm-power.navit.txt" in navit
    conf = station.qms.read_text()
    assert str(station.layer) in conf and str(station.repeaters) in conf
    assert cli.main(["maps", "infra", "remove"]) == 0
    navit = station.user_navit.read_text()
    assert repeaters.FILES[2] in navit and "infra-" not in navit
    assert str(station.repeaters) in station.qms.read_text()
    assert cli.main(["maps", "infra", "import", "--from-osm", "--layers", "power"]) == 0
    assert cli.main(["maps", "repeaters", "remove"]) == 0
    navit = station.user_navit.read_text()
    assert "infra-osm-power.navit.txt" in navit and repeaters.FILES[2] not in navit
    capsys.readouterr()


def test_maps_qmapshack_keeps_both_directories(
    station: Station, capsys: pytest.CaptureFixture[str], osmium: list[list[str]]
) -> None:
    station.install_region()
    assert cli.main(["maps", "infra", "import", "--from-osm"]) == 0
    station.qms.write_text("[Canvas]\nmapPath=/elsewhere\n")
    assert cli.main(["maps", "qmapshack", "--configure-only"]) == 0
    assert str(station.layer) in station.qms.read_text()
    capsys.readouterr()


# --- the data units (Task 5) ---------------------------------------------------------


def _install_unit(station: Station, route: str, built: Path) -> Path:
    unit = infra_sources.UNITS[route]
    dest = station.share / unit.file
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(built, dest)
    return dest


def test_from_nasr_reads_the_installed_unit_into_its_own_layer(
    station: Station, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    station.install_region()
    _install_unit(station, "nasr", sources_test._nasr(tmp_path, sources_test.NASR_ROWS))
    code, out, err = _run(["maps", "infra", "import", "--from-nasr"], capsys)
    assert code == 0, err
    assert "FAA NASR 2026-10-01, public domain" in out
    assert "Airports and heliports (FAA NASR 2026-10-01): 3 points" in out
    assert "Outside your regions' boxes: 1" in out
    assert infra.present_layers(station.layer) == ("faa-airports",)
    _no_private(out + err)


def test_from_nasr_skips_an_extract_without_a_box_and_names_it_by_number(
    station: Station, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    station.install_region("a-testville")
    station.install_region("b-boxless", box=None)
    _install_unit(station, "nasr", sources_test._nasr(tmp_path, sources_test.NASR_ROWS))
    code, out, err = _run(["maps", "infra", "import", "--from-nasr"], capsys)
    assert code == 0, err
    assert "region extract 2 of 2 has no bounding box in its header; left out" in out
    assert infra.present_layers(station.layer) == ("faa-airports",)
    _no_private(out + err)


def test_from_nasr_json_notes_an_extract_without_a_box(
    station: Station, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    station.install_region("a-testville")
    station.install_region("b-boxless", box=None)
    _install_unit(station, "nasr", sources_test._nasr(tmp_path, sources_test.NASR_ROWS))
    code, out, err = _run(["maps", "infra", "import", "--from-nasr", "--json"], capsys)
    assert code == 0, err
    doc = parse_one(out)
    validate(doc)
    assert "region extract 2 of 2 has no bounding box in its header; left out" in doc["notes"]
    assert infra.present_layers(station.layer) == ("faa-airports",)
    _no_private(out + err)


@pytest.mark.parametrize(
    ("flag", "unit"),
    [
        ("--from-nasr", "faa-nasr-airports"),
        ("--from-eia", "eia-860m"),
        ("--from-wri", "wri-power-plants"),
    ],
)
def test_a_unit_not_installed_is_named(
    flag: str, unit: str, station: Station, capsys: pytest.CaptureFixture[str]
) -> None:
    station.install_region()
    code, _, err = _run(["maps", "infra", "import", flag], capsys)
    assert code == cli.EXIT_FAILED and f"hammunition install {unit}" in err
    assert not station.layer.exists()


def test_a_data_import_needs_a_region_with_a_box(
    station: Station, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    station.install_region(box=None)
    _install_unit(station, "nasr", sources_test._nasr(tmp_path, sources_test.NASR_ROWS))
    code, _, err = _run(["maps", "infra", "import", "--from-nasr"], capsys)
    assert code == cli.EXIT_FAILED and "hammunition install osm-regions" in err


def test_from_eia_and_wri_json_validate_and_say_what_covers_the_us(
    station: Station, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    station.install_region()
    _install_unit(station, "eia", sources_test._xlsx(tmp_path, sources_test.EIA_ROWS))
    assert cli.main(["maps", "infra", "import", "--from-eia", "--json"]) == 0
    doc = parse_one(capsys.readouterr().out)
    validate(doc)
    assert doc["route"] == "eia" and doc["layers"][0]["written"] == 1
    assert doc["licences"] == [
        "Source: U.S. Energy Information Administration (Aug 2026), public domain"
    ]
    wri = sources_test._wri(
        tmp_path,
        ["USA,United States of America,Testville Dam,USA1,5.0,38.9,-75.4,Hydro,,,,1950,X,src"],
    )
    _install_unit(station, "wri", wri)
    code, _, err = _run(["maps", "infra", "import", "--from-wri"], capsys)
    assert code == cli.EXIT_FAILED and "Nothing was changed" in err
    assert infra.present_layers(station.layer) == ("eia-plants",)


# --- the fetches (Task 6) ---------------------------------------------------------------


class _Handler(http.server.BaseHTTPRequestHandler):
    bodies: ClassVar[dict[str, bytes]] = {}
    asked: ClassVar[list[str]] = []

    def do_GET(self) -> None:
        type(self).asked.append(self.path)
        body = type(self).bodies.get(self.path, b"")
        self.send_response(200 if body else 404)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        """Quiet."""


@pytest.fixture
def served(monkeypatch: pytest.MonkeyPatch) -> Iterator[type[_Handler]]:
    handler = type("Handler", (_Handler,), {"bodies": {}, "asked": []})
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    monkeypatch.setattr(infra_sources, "FCC_ASR_URL", f"{base}/r_tower.zip")
    monkeypatch.setattr(infra_sources, "NWR_URL", f"{base}/ccl-data.js")
    try:
        yield handler
    finally:
        server.shutdown()
        server.server_close()


def test_fetch_fcc_asr_discloses_first_and_carries_no_owner_contact(
    station: Station, served: type[_Handler], capsys: pytest.CaptureFixture[str]
) -> None:
    station.install_navit()
    station.install_region()
    served.bodies["/r_tower.zip"] = sources_test.ASR
    code, out, err = _run(["maps", "infra", "fetch-fcc-asr"], capsys)
    assert code == 0, err
    assert out.index("This fetches the FCC's") < out.index("FCC Antenna Structure Registration,")
    assert "FCC towers (unverified, 2026-09-27): 2 points" in out
    assert "sha256 " + hashlib.sha256(sources_test.ASR).hexdigest() in out
    assert sources_test.CANARY not in out + err + station.text()
    _no_private(out + err)


def test_fetch_nwr_drops_the_live_status(
    station: Station, served: type[_Handler], capsys: pytest.CaptureFixture[str]
) -> None:
    station.install_region()
    served.bodies["/ccl-data.js"] = sources_test.NWR
    code, out, err = _run(["maps", "infra", "fetch-nwr"], capsys)
    assert code == 0, err
    assert "NOAA/NWS, public domain, not an official NWS product" in out
    text = station.text()
    assert "162.475 MHz" in text and "010001 Kent DE" in text
    for status in ("OUT OF SERVICE", "DEGRADED"):
        assert status not in text + out


def test_a_fetch_with_no_region_fetches_nothing(
    station: Station, served: type[_Handler], capsys: pytest.CaptureFixture[str]
) -> None:
    code, _, err = _run(["maps", "infra", "fetch-nwr"], capsys)
    assert code == cli.EXIT_FAILED and "Nothing was fetched" in err
    assert served.asked == []


def test_a_fetch_that_answers_wrong_writes_nothing(
    station: Station, served: type[_Handler], capsys: pytest.CaptureFixture[str]
) -> None:
    station.install_region()
    served.bodies["/r_tower.zip"] = b"<html>maintenance</html>"
    code, _, err = _run(["maps", "infra", "fetch-fcc-asr"], capsys)
    assert code == cli.EXIT_FAILED and "not a zip" in err
    assert not station.layer.exists()


@pytest.mark.parametrize("verb", ["fetch-nwr", "fetch-fcc-asr"])
def test_the_fetches_have_no_json_form(
    verb: str, station: Station, served: type[_Handler], capsys: pytest.CaptureFixture[str]
) -> None:
    station.install_region()
    assert cli.main(["maps", "infra", verb, "--json"]) == cli.EXIT_UNPLANNABLE
    assert served.asked == []
    capsys.readouterr()


class _Agent(_Handler):
    agents: ClassVar[list[str]] = []

    def do_GET(self) -> None:
        type(self).agents.append(self.headers.get("User-Agent", ""))
        super().do_GET()


def test_the_fetches_send_a_descriptive_user_agent(
    station: Station, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """data.fcc.gov refused a bare `hammunition` (403) and served this one."""
    handler: type[_Agent] = type(
        "Agent",
        (_Agent,),
        {"bodies": {"/ccl-data.js": sources_test.NWR}, "asked": [], "agents": []},
    )
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(
        infra_sources, "NWR_URL", f"http://127.0.0.1:{server.server_address[1]}/ccl-data.js"
    )
    station.install_region()
    try:
        assert cli.main(["maps", "infra", "fetch-nwr"]) == 0
    finally:
        server.shutdown()
        server.server_close()
    assert handler.agents == [infra_sources.USER_AGENT]
    capsys.readouterr()
