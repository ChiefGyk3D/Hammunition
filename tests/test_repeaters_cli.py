# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``hammunition maps repeaters`` and ``maps navit``, end to end.  D-064.

Every run is against a scratch home, config and prefix; the hearham fetch
is served from 127.0.0.1 in this process. No GUI starts: ``execvp`` is
stubbed. Every row is synthetic (N0CALL, N0TST, Springfield IL).
"""

from __future__ import annotations

import http.server
import importlib
import json
import os
import shutil
import stat
import threading
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import NoReturn

import pytest

from hammunition import repeaters
from hammunition.interface import repeaters as repeater_docs
from hammunition.interface.repeaters import render_removed, render_repeaters
from hammunition.navit_config import rewrite
from json_support import assert_text_values_in_json, parse_one, validate

cli = importlib.import_module("hammunition.cli.main")

FIXTURES = Path(__file__).resolve().parent / "fixtures"
REPEATERS = FIXTURES / "repeaters"
NAVIT_STOCK = (FIXTURES / "navit.xml").read_text()

#: Nothing positional or personal may reach the terminal or the document.
PRIVATE = ("N0CALL", "N0TST", "39.8", "-89.6", "146.94", "Springfield")


class Exec(Exception):
    """Raised in place of replacing the test process."""


class Station:
    def __init__(self, tmp_path: Path) -> None:
        self.root = tmp_path
        self.data = tmp_path / "data"
        self.config = tmp_path / "config"
        self.prefix = tmp_path / "prefix"
        self.overlays = self.data / "hammunition" / "overlays"
        self.layer = self.overlays / "repeaters"
        self.qms = self.config / "QLandkarte" / "QMapShack.conf"
        self.generated = self.prefix / "share" / "hammunition" / "data" / "osm-navit" / "navit.xml"
        self.user_navit = self.overlays / "navit.xml"

    def copy(self, name: str) -> Path:
        dest = self.root / "in" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPEATERS / name, dest)
        return dest

    def install_navit(self) -> None:
        self.generated.parent.mkdir(parents=True, exist_ok=True)
        maps = [self.generated.parent / "atlantis-oceania.bin"]
        self.generated.write_text(rewrite(NAVIT_STOCK, maps))


@pytest.fixture
def station(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Station:
    here = Station(tmp_path)
    monkeypatch.setenv("XDG_DATA_HOME", str(here.data))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(here.config))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setattr(cli, "DEFAULT_PREFIX", here.prefix)
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    return here


def _record_exec(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    seen: list[list[str]] = []

    def execvp(file: str, argv: list[str]) -> NoReturn:
        seen.append([file, *argv])
        raise Exec

    monkeypatch.setattr(os, "execvp", execvp)
    return seen


def _no_private(text: str) -> None:
    leaked = [p for p in PRIVATE if p in text]
    assert not leaked, f"printed {leaked}"


# --- import ---------------------------------------------------------------------------


def test_import_writes_the_layer_registers_it_and_prints_only_counts(
    station: Station, capsys: pytest.CaptureFixture[str]
) -> None:
    station.install_navit()
    hand = station.copy("hand.csv")
    assert cli.main(["maps", "repeaters", "import", str(hand), "--exported", "2026-09-01"]) == 0
    out = capsys.readouterr().out
    assert repeaters.HAND_LICENCE in out
    assert "Repeaters (own export 2026-09-01, personal use)" in out
    assert "7 rows read, 4 skipped" in out
    assert "no usable position: 3 (lines 5, 7, 8)" in out
    assert "Merged: 0" in out and "Written: 3 repeaters" in out
    _no_private(out)
    for name in repeaters.FILES:
        path = station.layer / name
        assert stat.S_IMODE(path.stat().st_mode) == 0o600, name
    assert stat.S_IMODE(station.layer.stat().st_mode) == 0o700
    assert f"poiPaths={station.layer}" in station.qms.read_text()
    assert station.qms.read_text().startswith("[Canvas]\n")
    navit = station.user_navit.read_text()
    assert f'<map type="textfile" enabled="yes" data="{station.layer / repeaters.FILES[2]}"/>' in (
        navit
    )
    assert stat.S_IMODE(station.user_navit.stat().st_mode) == 0o600


def test_import_merges_across_inputs_and_dates_by_the_oldest(
    station: Station, capsys: pytest.CaptureFixture[str]
) -> None:
    rb = station.copy("rb.csv")
    hand = station.copy("hand.csv")
    os.utime(rb, (1_780_000_000, 1_780_000_000))
    assert cli.main(["maps", "repeaters", "import", str(rb), str(hand)]) == 0
    out = capsys.readouterr().out
    day = date.fromtimestamp(1_780_000_000).isoformat()
    assert f"Repeaters (own export {day}, personal use)" in out
    assert repeaters.REPEATERBOOK_LICENCE.split(".")[0] in out and repeaters.HAND_LICENCE in out
    # rb.csv's N0CALL 146.940 and hand.csv's first row are one repeater.
    assert "Merged: 1" in out and "Written: 4 repeaters" in out
    assert "Navit: no generated configuration" in out  # osm-navit not installed


def test_import_keeps_everything_else_in_qmapshacks_file(
    station: Station, capsys: pytest.CaptureFixture[str]
) -> None:
    station.qms.parent.mkdir(parents=True)
    before = "[Canvas]\nmapPath=/maps\n\n[Units]\ntype=metric\n"
    station.qms.write_text(before)
    assert cli.main(["maps", "repeaters", "import", str(station.copy("hand.csv"))]) == 0
    after = station.qms.read_text()
    assert after == f"[Canvas]\nmapPath=/maps\npoiPaths={station.layer}\n\n[Units]\ntype=metric\n"
    # Again: already there, the file is not rewritten.
    first = station.qms.stat()
    assert cli.main(["maps", "repeaters", "import", str(station.copy("hand.csv"))]) == 0
    assert station.qms.stat().st_mtime_ns == first.st_mtime_ns
    assert "already" in capsys.readouterr().out


def test_import_json_is_one_document_carrying_what_the_text_shows(
    station: Station, capsys: pytest.CaptureFixture[str]
) -> None:
    station.install_navit()
    hand = station.copy("hand.csv")
    argv = ["maps", "repeaters", "import", str(hand), "--exported", "2026-09-01"]
    assert cli.main(argv) == 0
    capsys.readouterr()
    assert cli.main([*argv, "--json"]) == 0
    raw = capsys.readouterr().out
    assert cli.main(argv) == 0  # the same state again: QMapShack's path already there
    text = capsys.readouterr().out
    doc = parse_one(raw)
    validate(doc)
    assert doc["kind"] == "repeaters"
    assert doc["exported"] == "2026-09-01" and doc["written"] == 3 and doc["merged"] == 0
    assert doc["inputs"][0]["format"] == "hand-csv" and doc["inputs"][0]["read"] == 7
    assert [r["program"] for r in doc["registered"]] == ["qmapshack", "navit"]
    assert_text_values_in_json(text, doc, render_repeaters, repeater_docs._registration)
    _no_private(raw)


@pytest.mark.parametrize(
    ("name", "says"),
    [("chirp.csv", "CHIRP CSV"), ("rb-nopos.csv", "no Lat and Long"), ("export.kml", "KML")],
)
def test_one_refused_input_refuses_the_whole_import(
    name: str, says: str, station: Station, capsys: pytest.CaptureFixture[str]
) -> None:
    good = station.copy("hand.csv")
    bad = station.copy(name)
    assert cli.main(["maps", "repeaters", "import", str(good), str(bad)]) == cli.EXIT_FAILED
    err = capsys.readouterr().err
    assert says in err and "Nothing was written" in err
    assert not station.layer.exists() and not station.qms.exists()


def test_a_refusal_under_json_is_one_error_document(
    station: Station, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = station.copy("chirp.csv")
    assert cli.main(["maps", "repeaters", "import", str(bad), "--json"]) == cli.EXIT_FAILED
    doc = parse_one(capsys.readouterr().out)
    assert doc["kind"] == "error" and doc["command"] == "maps repeaters import"
    assert "CHIRP CSV" in doc["message"]


def test_an_import_with_no_usable_row_writes_nothing(
    station: Station, capsys: pytest.CaptureFixture[str]
) -> None:
    empty = station.root / "empty.csv"
    empty.write_text(",".join(repeaters.HAND_HEADER) + "\nN0CALL,146.94,,,,x,y,,\n")
    assert cli.main(["maps", "repeaters", "import", str(empty)]) == cli.EXIT_FAILED
    assert "no repeater with a position" in capsys.readouterr().err
    assert not station.layer.exists()


def test_a_bad_exported_date_is_refused(
    station: Station, capsys: pytest.CaptureFixture[str]
) -> None:
    hand = station.copy("hand.csv")
    argv = ["maps", "repeaters", "import", str(hand), "--exported", "1/9/2026"]
    assert cli.main(argv) == cli.EXIT_FAILED
    assert "YYYY-MM-DD" in capsys.readouterr().err
    assert not station.layer.exists()


def test_import_refuses_root(
    station: Station, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    assert cli.main(["maps", "repeaters", "import", str(station.copy("hand.csv"))]) == 1
    assert "not as root" in capsys.readouterr().err
    assert not station.layer.exists()


def test_a_qmapshack_file_it_cannot_edit_is_named_and_the_layer_still_written(
    station: Station, capsys: pytest.CaptureFixture[str]
) -> None:
    station.qms.parent.mkdir(parents=True)
    real = station.root / "elsewhere.conf"
    real.write_text("[Canvas]\n")
    station.qms.symlink_to(real)
    assert cli.main(["maps", "repeaters", "import", str(station.copy("hand.csv"))]) == 1
    captured = capsys.readouterr()
    assert "symbolic link" in captured.out + captured.err
    assert (station.layer / repeaters.FILES[1]).is_file()
    assert real.read_text() == "[Canvas]\n"


# --- remove ----------------------------------------------------------------------------


def test_remove_deletes_the_layer_and_unregisters_it(
    station: Station, capsys: pytest.CaptureFixture[str]
) -> None:
    station.install_navit()
    station.qms.parent.mkdir(parents=True)
    station.qms.write_text("[Units]\ntype=metric\n")
    assert cli.main(["maps", "repeaters", "import", str(station.copy("hand.csv"))]) == 0
    capsys.readouterr()
    assert cli.main(["maps", "repeaters", "remove"]) == 0
    out = capsys.readouterr().out
    assert not station.layer.exists() and not station.user_navit.exists()
    assert station.qms.read_text() == "[Units]\ntype=metric\n\n[Canvas]\n"
    assert "Removed" in out
    # Idempotent.
    assert cli.main(["maps", "repeaters", "remove"]) == 0
    assert "Nothing to remove" in capsys.readouterr().out


def test_remove_json_validates_and_carries_the_text(
    station: Station, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["maps", "repeaters", "import", str(station.copy("hand.csv"))]) == 0
    capsys.readouterr()
    assert cli.main(["maps", "repeaters", "remove", "--json"]) == 0
    doc = parse_one(capsys.readouterr().out)
    validate(doc)
    assert doc["kind"] == "repeaters-removed"
    assert [Path(p).name for p in doc["removed"]] == list(repeaters.FILES)
    assert cli.main(["maps", "repeaters", "import", str(station.copy("hand.csv"))]) == 0
    capsys.readouterr()
    assert cli.main(["maps", "repeaters", "remove"]) == 0
    text = capsys.readouterr().out
    assert_text_values_in_json(text, doc, render_removed, repeater_docs._registration)


# --- maps qmapshack keeps poiPaths in step --------------------------------------------------


def test_maps_qmapshack_adds_the_collection_while_it_exists_and_drops_it_after(
    station: Station, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["maps", "repeaters", "import", str(station.copy("hand.csv"))]) == 0
    # A QMapShack open during the import wrote its own list back on exit.
    station.qms.write_text("[Canvas]\nmapPath=/maps\n")
    assert cli.main(["maps", "qmapshack", "--configure-only"]) == 0
    assert f"poiPaths={station.layer}" in station.qms.read_text()
    shutil.rmtree(station.layer)
    assert cli.main(["maps", "qmapshack", "--configure-only"]) == 0
    assert "poiPaths" not in station.qms.read_text()


# --- maps navit -------------------------------------------------------------------------------


def test_maps_navit_opens_the_operators_copy_when_there_is_a_layer(
    station: Station, monkeypatch: pytest.MonkeyPatch
) -> None:
    station.install_navit()
    assert cli.main(["maps", "repeaters", "import", str(station.copy("hand.csv"))]) == 0
    station.user_navit.unlink()  # rebuilt at every start
    seen = _record_exec(monkeypatch)
    with pytest.raises(Exec):
        cli.main(["maps", "navit"])
    assert seen == [["navit", "navit", str(station.user_navit)]]
    assert repeaters.FILES[2] in station.user_navit.read_text()


def test_maps_navit_opens_the_generated_file_with_no_layer_and_drops_a_stale_copy(
    station: Station, monkeypatch: pytest.MonkeyPatch
) -> None:
    station.install_navit()
    station.overlays.mkdir(parents=True)
    station.user_navit.write_text("<stale/>")
    seen = _record_exec(monkeypatch)
    with pytest.raises(Exec):
        cli.main(["maps", "navit"])
    assert seen == [["navit", "navit", str(station.generated)]]
    assert not station.user_navit.exists()


def test_maps_navit_as_root_opens_the_generated_file_and_writes_nothing(
    station: Station, monkeypatch: pytest.MonkeyPatch
) -> None:
    station.install_navit()
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    seen = _record_exec(monkeypatch)
    with pytest.raises(Exec):
        cli.main(["maps", "navit"])
    assert seen == [["navit", "navit", str(station.generated)]]
    assert not station.overlays.exists()


def test_maps_navit_without_osm_navit_says_what_to_install(
    station: Station, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen = _record_exec(monkeypatch)
    assert cli.main(["maps", "navit"]) == cli.EXIT_FAILED
    assert "osm-navit" in capsys.readouterr().err and seen == []


# --- fetch-hearham, from loopback only -------------------------------------------------------------


class _Handler(http.server.BaseHTTPRequestHandler):
    body = b""
    status = 200

    def do_GET(self) -> None:
        self.send_response(self.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(self.body)))
        self.end_headers()
        self.wfile.write(self.body)

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture
def hearham(monkeypatch: pytest.MonkeyPatch) -> Iterator[type[_Handler]]:
    handler = type("Handler", (_Handler,), {"body": (REPEATERS / "hearham.json").read_bytes()})
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(
        repeaters, "HEARHAM_URL", f"http://127.0.0.1:{server.server_address[1]}/api/repeaters/v1"
    )
    try:
        yield handler
    finally:
        server.shutdown()
        server.server_close()


def test_fetch_hearham_records_what_it_saw_and_marks_it_unverified(
    station: Station, hearham: type[_Handler], capsys: pytest.CaptureFixture[str]
) -> None:
    import hashlib

    digest = hashlib.sha256(hearham.body).hexdigest()
    assert cli.main(["maps", "repeaters", "fetch-hearham"]) == 0
    out = capsys.readouterr().out
    assert "life-and-death operations" in out and digest in out and "not verifiable" in out
    assert "Repeaters (hearham " in out and ", unverified)" in out
    assert out.index("fetches") < out.index("life-and-death")  # disclosed first
    gpx = (station.layer / repeaters.FILES[0]).read_text()
    assert digest in gpx and "hearham" in gpx
    _no_private(out)


@pytest.mark.parametrize(
    ("body", "status", "says"),
    [(b"<html>not json</html>", 200, "not an input"), (b"{}", 500, "could not fetch")],
)
def test_fetch_hearham_refuses_what_is_not_its_list(
    body: bytes,
    status: int,
    says: str,
    station: Station,
    hearham: type[_Handler],
    capsys: pytest.CaptureFixture[str],
) -> None:
    hearham.body, hearham.status = body, status
    assert cli.main(["maps", "repeaters", "fetch-hearham"]) == cli.EXIT_FAILED
    assert says in capsys.readouterr().err
    assert not station.layer.exists()


def test_fetch_hearham_refuses_an_oversized_answer(
    station: Station,
    hearham: type[_Handler],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(repeaters, "HEARHAM_LIMIT", 100)
    assert cli.main(["maps", "repeaters", "fetch-hearham"]) == cli.EXIT_FAILED
    assert "more than 100 bytes" in capsys.readouterr().err
    assert not station.layer.exists()


def test_fetch_hearham_has_no_json_form_and_names_its_whole_verb(
    station: Station, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["maps", "repeaters", "fetch-hearham", "--json"]) == cli.EXIT_UNPLANNABLE
    doc = json.loads(capsys.readouterr().out)
    assert doc["command"] == "maps repeaters fetch-hearham"
    assert "no --json form" in doc["message"]
    assert not station.layer.exists()


# --- an installed navit-offline is moved onto the engine by `menus apply` ---------------------


def test_menus_apply_rewrites_an_earlier_navit_offline_to_run_the_engine(tmp_path: Path) -> None:
    """The guide tells an operator with Navit already installed that
    `hammunition menus apply` updates the launcher; this is that claim."""
    from hammunition.launchers import wrapper_body
    from hammunition.manifest.load import load_catalog
    from hammunition.menus import missing_launcher_steps

    catalog = Path(__file__).resolve().parent.parent / "catalog" / "packages"
    navit = load_catalog(catalog)["navit"]
    assert navit.launchers[0].exec == "hammunition maps navit"
    earlier_launcher = navit.launchers[0].model_copy(
        update={"exec": "navit /usr/local/share/hammunition/data/osm-navit/navit.xml"}
    )
    earlier = navit.model_copy(update={"launchers": [earlier_launcher]})
    bin_dir, apps = tmp_path / "bin", tmp_path / "applications"
    bin_dir.mkdir()
    apps.mkdir()
    (bin_dir / "navit-offline").write_text(wrapper_body(earlier, earlier_launcher))
    (apps / "hammunition-navit-offline.desktop").write_text("[Desktop Entry]\n")
    engine = tmp_path / "venv" / "hammunition"
    engine.parent.mkdir()
    engine.write_text("#!/bin/sh\n")
    engine.chmod(0o755)
    steps = missing_launcher_steps(
        [navit],
        bin_dir=bin_dir,
        applications_dir=apps,
        prefix=tmp_path / "prefix",
        installed=lambda package: True,
        engine=engine,
    )
    assert len(steps) == 1 and steps[0].description.startswith("Rewrite")
    assert "maps navit" in wrapper_body(navit, navit.launchers[0], engine=engine)


# --- review findings 2 and 9: what the fetch refuses ---------------------------------------


def test_fetch_hearham_names_a_broken_http_answer(
    station: Station, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import socket

    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)

    def answer() -> None:
        conn, _ = listener.accept()
        conn.recv(65536)
        conn.sendall(b"garbage\r\n\r\n")
        conn.close()

    thread = threading.Thread(target=answer, daemon=True)
    thread.start()
    port = listener.getsockname()[1]
    monkeypatch.setattr(repeaters, "HEARHAM_URL", f"http://127.0.0.1:{port}/api/repeaters/v1")
    try:
        assert cli.main(["maps", "repeaters", "fetch-hearham"]) == cli.EXIT_FAILED
    finally:
        thread.join(5)
        listener.close()
    assert "could not fetch" in capsys.readouterr().err
    assert not station.layer.exists()


@pytest.mark.parametrize("location", ["http://127.0.0.1:9/elsewhere", "file:///etc/passwd"])
def test_fetch_hearham_follows_a_redirect_only_to_https(
    location: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Redirect(_Handler):
        def do_GET(self) -> None:
            self.send_response(302)
            self.send_header("Location", location)
            self.send_header("Content-Length", "0")
            self.end_headers()

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Redirect)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/api/repeaters/v1"
        # Ours refuses plain HTTP; urllib itself refuses file: before asking it.
        with pytest.raises(repeaters.RepeaterFetchError, match=r"not HTTPS|is not allowed"):
            repeaters.fetch_hearham(url, timeout=5)
    finally:
        server.shutdown()
        server.server_close()


def test_a_hearham_body_that_is_not_its_list_names_the_url(
    station: Station, hearham: type[_Handler], capsys: pytest.CaptureFixture[str]
) -> None:
    hearham.body = b"[1, 2]"
    code = cli.main(["maps", "repeaters", "fetch-hearham"])
    err = capsys.readouterr().err
    assert code == cli.EXIT_FAILED and "127.0.0.1" in err
