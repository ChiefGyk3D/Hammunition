# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The aircraft page (tar1090), drawn by headless Chromium with no network.  D-071 (2026-10-02).

The properties: with a synthetic ``aircraft.json`` the aircraft appear, and
**no request leaves 127.0.0.1**, and the policy that forbids it never has to
fire (a refused request means the page tried; the settings and the layer
replacement are what keep it from trying, the policy is the backstop).

Chromium runs headless with every host but 127.0.0.1 made unresolvable and
its net log is read back, as in ``test_map_render``. The check is shown able
to fail: the same page served as upstream ships it, with no policy, does ask
other hosts (``test_the_check_can_fail``).

The pinned files are not fetched, so they must be on disk and CI has neither
them nor Chromium: this check is local, and is skipped by name without them.
``HAMMUNITION_TAR1090_DIR`` holds ``<commit>.tar.gz`` (the manifest's
archive, sha256-checked); ``HAMMUNITION_MAP_KIT_DIR`` holds
``pmtiles-4.5.0.tgz`` for the variant with a basemap (the other kit files are
stand-ins; the page reads only pmtiles.js).
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from hammunition import aircraft_page
from hammunition.aircraft_page import AIRCRAFT, HTML, SRC, UNIT, find_aircraft
from hammunition.backends.source import extract
from hammunition.manifest.load import load_catalog
from hammunition.manifest.schema import DataArtifact, DataInstall
from hammunition.map_page import KIT_UNIT, REQUIRED, TILES_UNIT, find_map
from hammunition.reference import make_server
from pmtiles_fixture import write_pmtiles
from test_map_render import _chromium, _page_requests

REPO = Path(__file__).resolve().parent.parent
PMTILES_ARCHIVE = "pmtiles-4.5.0.tgz"
#: Chromium runs the page this long in virtual time before the DOM is read.
DRAW_MS = 15000

needs_chromium = pytest.mark.skipif(
    _chromium() is None, reason="no chromium on PATH: the render is not checked"
)


def _dir(variable: str) -> Path | None:
    value = os.environ.get(variable)
    return Path(value) if value else None


def _artifact(unit: str, suffix: str) -> DataArtifact:
    block = load_catalog(REPO / "catalog" / "packages")[unit].install[0].install
    assert isinstance(block, DataInstall)
    return next(a for a in block.artifacts if a.url.endswith(suffix))


def _checked(directory: Path | None, variable: str, name: str, sha256: str) -> Path:
    if directory is None:
        pytest.skip(f"{variable} is not set: the pinned file is not on disk (nothing is fetched)")
    path = directory / name
    if not path.is_file():
        pytest.skip(f"{variable} has no {name}")
    assert hashlib.sha256(path.read_bytes()).hexdigest() == sha256, f"{name} is not the pinned file"
    return path


def _install_tar1090(data: Path) -> None:
    artifact = _artifact(UNIT, ".tar.gz")
    archive = _checked(
        _dir("HAMMUNITION_TAR1090_DIR"),
        "HAMMUNITION_TAR1090_DIR",
        artifact.url.rsplit("/", 1)[-1],
        artifact.sha256,
    )
    assert artifact.into == SRC
    extract(archive, data / UNIT / SRC, members=artifact.members)


def _install_map(data: Path) -> None:
    """A kit of stand-ins but the one real file the aircraft page reads, and
    one synthetic region."""
    artifact = _artifact(KIT_UNIT, PMTILES_ARCHIVE)
    archive = _checked(
        _dir("HAMMUNITION_MAP_KIT_DIR"), "HAMMUNITION_MAP_KIT_DIR", PMTILES_ARCHIVE, artifact.sha256
    )
    for rel in REQUIRED:
        path = data / KIT_UNIT / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("stand-in")
    assert artifact.into is not None
    extract(archive, data / KIT_UNIT / artifact.into, members=artifact.members)
    (data / TILES_UNIT).mkdir(parents=True)
    write_pmtiles(data / TILES_UNIT / "testville.pmtiles")


def _readsb(directory: Path) -> None:
    directory.mkdir()
    now = time.time()
    aircraft = [
        {
            "hex": "a1b2c3",
            "flight": "TEST123 ",
            "lat": 0.4,
            "lon": 0.5,
            "alt_baro": 35000,
            "gs": 450.0,
            "track": 90.0,
            "seen": 0.2,
            "seen_pos": 0.2,
            "messages": 120,
            "type": "adsb_icao",
        },
        {
            "hex": "d4e5f6",
            "flight": "TEST456 ",
            "lat": 0.2,
            "lon": -0.3,
            "alt_baro": 12000,
            "gs": 250.0,
            "track": 270.0,
            "seen": 0.4,
            "seen_pos": 0.4,
            "messages": 80,
            "type": "adsb_icao",
        },
    ]
    (directory / "aircraft.json").write_text(
        json.dumps({"now": now, "messages": 200, "aircraft": aircraft})
    )
    (directory / "receiver.json").write_text(
        json.dumps({"version": "test", "refresh": 1000, "history": 0, "lat": 0.0, "lon": 0.0})
    )


def _render(
    tmp_path: Path, shelf: aircraft_page.AircraftShelf, *, query: str = ""
) -> tuple[str, str, Path]:
    """/aircraft/ drawn by headless Chromium: (the DOM at the load event,
    Chromium's console on stderr, its net log)."""
    server = make_server(
        0, "<html></html>", [], map_shelf=find_map(tmp_path / "data"), aircraft=shelf
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    net_log = tmp_path / "net.json"
    chromium = _chromium()
    assert chromium is not None
    try:
        result = subprocess.run(
            [
                chromium,
                "--headless=new",
                "--no-sandbox",
                "--no-first-run",
                "--disable-background-networking",
                "--disable-component-update",
                "--disable-sync",
                "--disable-default-apps",
                "--disable-extensions",
                # Chromium's own form-autofill lookup (Google's service, started
                # by the browser because the page has inputs), not the page's.
                "--disable-features=AutofillServerCommunication",
                "--use-angle=swiftshader",
                "--enable-unsafe-swiftshader",
                "--enable-logging=stderr",
                "--v=0",
                f"--user-data-dir={tmp_path / 'profile'}",
                "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1",
                f"--log-net-log={net_log}",
                "--window-size=1000,700",
                f"--virtual-time-budget={DRAW_MS}",
                "--dump-dom",
                f"http://127.0.0.1:{server.server_address[1]}{AIRCRAFT}{query}",
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    finally:
        server.shutdown()
        server.server_close()
    return result.stdout, result.stderr, net_log


def _off_loopback(net_log: Path) -> list[str]:
    page, _browser = _page_requests(net_log)
    assert page, "the net log recorded the page's requests"
    return sorted(u for u in page if urlsplit(u).hostname != "127.0.0.1")


def _setup(tmp_path: Path, *, basemap: bool) -> aircraft_page.AircraftShelf:
    data = tmp_path / "data"
    _install_tar1090(data)
    if basemap:
        _install_map(data)
    _readsb(tmp_path / "run-readsb")
    shelf = find_aircraft(data, find_map(data), json_dir=tmp_path / "run-readsb")
    assert shelf is not None and shelf.basemap is basemap
    return shelf


def _assert_aircraft_drawn(dom: str, stderr: str) -> None:
    assert "TEST123" in dom and "TEST456" in dom, (dom[-3000:], stderr[-2000:])
    assert "Content Security Policy" not in stderr, (
        "the policy refused a request: the page tried to leave loopback, and "
        "the settings or the layer replacement no longer stop it first\n" + stderr[-3000:]
    )


@needs_chromium
def test_the_aircraft_appear_over_the_offline_map_and_nothing_leaves_loopback(
    tmp_path: Path,
) -> None:
    shelf = _setup(tmp_path, basemap=True)
    # The synthetic region has one tile, zoom 0: open the page on the whole world (tar1090 reads zoom=0 as 8).
    dom, stderr, net_log = _render(tmp_path, shelf, query="?zoom=0.4")
    _assert_aircraft_drawn(dom, stderr)
    assert "data-basemap-error" not in dom
    match = re.search(r'data-basemap-features="(\d+)"', dom)
    assert match is not None and int(match.group(1)) > 0, (
        "the PMTiles tile was decoded and has features"
    )
    off = _off_loopback(net_log)
    assert off == [], f"the page asked for something off loopback: {off}"
    page, _ = _page_requests(net_log)
    assert any(u.endswith("/aircraft/data/aircraft.json") or "aircraft.json" in u for u in page)
    assert any(u.endswith("/map/tiles/testville.pmtiles") for u in page), "the basemap was read"
    assert 'id="hammunition-notice"' not in dom


@needs_chromium
def test_without_the_map_the_aircraft_still_appear_and_the_page_says_why(tmp_path: Path) -> None:
    shelf = _setup(tmp_path, basemap=False)
    dom, stderr, net_log = _render(tmp_path, shelf)
    _assert_aircraft_drawn(dom, stderr)
    assert _off_loopback(net_log) == []
    assert 'id="hammunition-notice"' in dom and "No basemap" in dom
    assert "never loads a map from the internet" in dom


@needs_chromium
def test_selecting_an_aircraft_asks_no_photograph_or_route_service(tmp_path: Path) -> None:
    """tar1090's detail panel fetches a photograph and a route for the
    selected aircraft by default; here nothing is asked of anyone."""
    shelf = _setup(tmp_path, basemap=False)
    dom, stderr, net_log = _render(tmp_path, shelf, query="?icao=a1b2c3")  # the page opens on it
    assert "TEST123" in dom and 'id="selected_icao"' in dom and "A1B2C3" in dom, dom[-3000:]
    assert "Content Security Policy" not in stderr, stderr[-3000:]
    assert _off_loopback(net_log) == []


@needs_chromium
def test_the_check_can_fail(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The same page as upstream ships it (its own config, no replaced layers,
    no policy) does ask other hosts: so an empty ``off`` above means something."""
    shelf = _setup(tmp_path, basemap=False)
    html = tmp_path / "data" / UNIT / SRC / HTML
    upstream = dataclasses.replace(
        shelf,
        index=(html / "index.html").read_bytes(),
        config=(html / "config.js").read_bytes(),
    )
    monkeypatch.setattr(aircraft_page, "CONTENT_SECURITY_POLICY", "")
    _dom, _stderr, net_log = _render(tmp_path, upstream, query="?icao=a1b2c3")
    off = _off_loopback(net_log)
    assert off, "upstream's own page made no request off loopback: this test measures nothing"
    hosts = {urlsplit(u).hostname or "" for u in off}
    assert any(
        "openfreemap" in h or "arcgis" in h or "carto" in h or "openstreetmap" in h for h in hosts
    ), hosts
    assert "api.planespotters.net" in hosts, hosts  # the selected aircraft's photograph


@needs_chromium
def test_the_policy_alone_stops_upstreams_own_page(tmp_path: Path) -> None:
    """The backstop, shown to hold on its own: upstream's page and config, with
    only the policy header, are refused every request off loopback by the
    browser (the console says so; the network log has none)."""
    shelf = _setup(tmp_path, basemap=False)
    html = tmp_path / "data" / UNIT / SRC / HTML
    upstream = dataclasses.replace(
        shelf, index=(html / "index.html").read_bytes(), config=(html / "config.js").read_bytes()
    )
    _dom, stderr, net_log = _render(tmp_path, upstream, query="?icao=a1b2c3")
    assert _off_loopback(net_log) == []
    assert "Content Security Policy" in stderr and "connect-src" in stderr, stderr[-3000:]
