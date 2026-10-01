# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The map page, drawn by headless Chromium with no network.  D-071.

The property: the page renders with no request anywhere but 127.0.0.1. The
page and its files are served by ``reference serve``'s own server; the tile
is a synthetic one (``pmtiles_fixture``); the kit is built from the pinned
archives themselves, each checked against the manifest's sha256 first.
Chromium runs headless with every host but 127.0.0.1 made unresolvable, and
its net log is read back: every URL it requested must be on 127.0.0.1. The
credit the OpenMapTiles licence requires must be drawn on the map.

The suite downloads nothing, so it needs the pinned files already on disk, and CI
has neither them nor Chromium: this check is local. It last passed on the
development host on 2026-09-30 (Chromium 154).
``HAMMUNITION_MAP_KIT_DIR`` names a directory holding them under their
published names (``tilemaker_3.0.0.orig.tar.gz``, ``dist.zip``,
``pmtiles-4.5.0.tgz``, the four sprite files). Without that directory, or
without ``chromium`` on PATH, the test is skipped by name. No GUI is
launched: Chromium runs ``--headless``, and only against 127.0.0.1.
"""

from __future__ import annotations

import hashlib
import http.server
import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from hammunition.backends.source import extract
from hammunition.manifest.load import load_catalog
from hammunition.manifest.schema import DataInstall
from hammunition.map_page import KIT_UNIT, TILES_UNIT, find_map
from hammunition.reference import RouterState, make_server
from pmtiles_fixture import write_pmtiles

REPO = Path(__file__).resolve().parent.parent
#: How long the page's load event is held while the map draws.
DRAW_SECONDS = 12
#: What the page needs of the kit: the three archives and the sprite.
PAGE_ARTIFACTS = {"into": ("tilemaker", "maplibre", "pmtiles"), "files": ("sprite",)}


def _chromium() -> str | None:
    return shutil.which("chromium") or shutil.which("chromium-browser")


def _kit_dir() -> Path | None:
    value = os.environ.get("HAMMUNITION_MAP_KIT_DIR")
    return Path(value) if value else None


def _build_kit(source: Path, kit: Path) -> None:
    block = load_catalog(REPO / "catalog" / "packages")[KIT_UNIT].install[0].install
    assert isinstance(block, DataInstall)
    for artifact in block.artifacts:
        wanted = artifact.into in PAGE_ARTIFACTS["into"] or (artifact.install_as or "").startswith(
            PAGE_ARTIFACTS["files"]
        )
        if not wanted:
            continue
        name = artifact.url.rsplit("/", 1)[-1]
        path = source / name
        if not path.is_file():
            pytest.skip(f"HAMMUNITION_MAP_KIT_DIR has no {name}: the pinned kit is not on disk")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == artifact.sha256, f"{name} is not the pinned file"
        if artifact.install_as:
            kit.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, kit / artifact.install_as)
        else:
            assert artifact.into is not None
            kit.mkdir(parents=True, exist_ok=True)
            extract(path, kit / artifact.into, members=artifact.members)


def _page_requests(net_log: Path) -> tuple[set[str], set[str]]:
    """(every URL the page asked for, every URL Chromium asked for itself).

    A request the page makes starts with the page's site in its network
    isolation key, or with the page as its initiator; Chromium's own
    background requests (update checks, a spelling dictionary) carry
    ``null`` or their own site and no origin. Those are unresolvable under
    the resolver rule anyway, and are not the page's."""
    log = json.loads(net_log.read_text())
    kinds = {v: k for k, v in log["constants"]["logEventTypes"].items()}
    page: set[str] = set()
    browser: set[str] = set()
    for event in log.get("events", []):
        if kinds.get(event.get("type")) != "URL_REQUEST_START_JOB":
            continue
        params = event.get("params") or {}
        url = params.get("url", "")
        key = str(params.get("network_isolation_key", ""))
        initiator = str(params.get("initiator", ""))
        if key.startswith("http://127.0.0.1") or initiator.startswith("http://127.0.0.1"):
            page.add(url)
        else:
            browser.add(url)
    return page, browser


class _Delay(http.server.BaseHTTPRequestHandler):
    """Holds the page's load event while the map draws: ``--dump-dom`` dumps
    at the load event, and without this it dumps before MapLibre has run
    (the spike's harness did the same). Loopback, test-only."""

    def do_GET(self) -> None:
        time.sleep(DRAW_SECONDS)
        self.send_response(404)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        """Quiet."""


def _render(
    tmp_path: Path,
    data: Path,
    *,
    fragment: str = "",
    router: RouterState | None = None,
) -> tuple[str, str, Path]:
    """The page from *data*, drawn by headless Chromium with every host but
    127.0.0.1 unresolvable: (the DOM at the load event, Chromium's stderr,
    its net log)."""
    shelf = find_map(data)
    assert shelf.ready, shelf.missing
    server = make_server(0, "<html></html>", [], map_shelf=shelf, position_port=1, router=router)
    delay = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Delay)
    delay.daemon_threads = True
    assert server.map_page is not None
    held = f'<img alt="" src="http://127.0.0.1:{delay.server_address[1]}/hold"></body>'
    server.map_page = server.map_page.replace(b"</body>", held.encode())
    for each in (server, delay):
        threading.Thread(target=each.serve_forever, daemon=True).start()
    port = server.server_address[1]
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
                "--use-angle=swiftshader",
                "--enable-unsafe-swiftshader",
                f"--user-data-dir={tmp_path / 'profile'}",
                "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1",
                f"--log-net-log={net_log}",
                "--window-size=800,600",
                "--dump-dom",
                f"http://127.0.0.1:{port}/map/{fragment}",
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    finally:
        for each in (server, delay):
            each.shutdown()
            each.server_close()
    return result.stdout, result.stderr, net_log


@pytest.mark.skipif(_chromium() is None, reason="no chromium on PATH: the render is not checked")
@pytest.mark.skipif(
    _kit_dir() is None,
    reason="HAMMUNITION_MAP_KIT_DIR is not set: the pinned kit is not on disk (nothing is fetched)",
)
def test_the_map_renders_with_no_request_off_loopback_and_draws_the_credit(
    tmp_path: Path,
) -> None:
    source = _kit_dir()
    assert source is not None
    data = tmp_path / "data"
    _build_kit(source, data / KIT_UNIT)
    (data / TILES_UNIT).mkdir(parents=True)
    write_pmtiles(data / TILES_UNIT / "testville.pmtiles")
    dom, stderr, net_log = _render(tmp_path, data)
    result_stderr = stderr
    assert 'data-state="idle"' in dom, (dom[-2000:], result_stderr[-2000:])
    assert 'data-errors="0"' in dom, dom[-2000:]
    attribution = dom.split("maplibregl-ctrl-attrib-inner", 1)[1][:600]
    assert "© OpenMapTiles" in attribution and "© OpenStreetMap contributors" in attribution
    page, browser = _page_requests(net_log)
    assert page, "the net log recorded the page's requests"
    off = sorted(u for u in page if urlsplit(u).hostname != "127.0.0.1")
    assert off == [], f"the page asked for something off loopback: {off}"
    assert all(urlsplit(u).hostname != "127.0.0.1" for u in browser), (
        "a loopback request was not attributed to the page; the split is wrong"
    )
    assert any(u.endswith("/map/tiles/testville.pmtiles") for u in page)
    assert any("/fonts/" in u and u.endswith(".pbf") for u in page), "a label asked for glyphs"


@pytest.mark.skipif(_chromium() is None, reason="no chromium on PATH: the render is not checked")
@pytest.mark.skipif(
    _kit_dir() is None,
    reason="HAMMUNITION_MAP_KIT_DIR is not set: the pinned kit is not on disk (nothing is fetched)",
)
def test_a_route_is_asked_through_this_server_and_drawn_with_no_request_off_loopback(
    tmp_path: Path,
) -> None:
    """D-076: ``#route=`` asks ``/map/route`` on the page's own server, which
    asks a loopback stand-in for GraphHopper; the line is drawn and its
    summary shown, and nothing leaves 127.0.0.1."""
    from hammunition.graphhopper import PROFILES
    from test_reference_router import ROUTE_ANSWER, _FakeGraphHopper

    source = _kit_dir()
    assert source is not None
    data = tmp_path / "data"
    _build_kit(source, data / KIT_UNIT)
    (data / TILES_UNIT).mkdir(parents=True)
    write_pmtiles(data / TILES_UNIT / "testville.pmtiles")
    _FakeGraphHopper.asked = []
    fake = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _FakeGraphHopper)
    threading.Thread(target=fake.serve_forever, daemon=True).start()
    router = RouterState(
        port=fake.server_address[1], profiles=PROFILES, log=tmp_path / "graphhopper.log"
    )
    try:
        dom, stderr, net_log = _render(
            tmp_path, data, fragment="#route=44.255,-72.547;44.29,-72.547;hike", router=router
        )
    finally:
        fake.shutdown()
        fake.server_close()
    assert 'data-route="drawn"' in dom, (dom[-2000:], stderr[-2000:])
    assert 'data-errors="0"' in dom, dom[-2000:]
    distance = ROUTE_ANSWER["paths"][0]["distance"]  # type: ignore[index]
    assert f"{distance / 1000:.1f} km" in dom and "(hike)" in dom
    assert "Continue onto Trail 19" in dom
    assert len(_FakeGraphHopper.asked) == 1 and "profile=hike" in _FakeGraphHopper.asked[0]
    page, _browser = _page_requests(net_log)
    off = sorted(u for u in page if urlsplit(u).hostname != "127.0.0.1")
    assert off == [], f"the page asked for something off loopback: {off}"
    assert any("/map/route?" in u for u in page)
    assert not any(urlsplit(u).port == fake.server_address[1] for u in page), (
        "the page never calls GraphHopper itself"
    )
