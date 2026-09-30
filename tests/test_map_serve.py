# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The offline map on ``reference serve``'s loopback server.  D-071.

pmtiles.js reads a ``.pmtiles`` file with HTTP byte ranges, and a server
that answers a range with the whole file makes it fail (Python's own
``http.server``, measured by the spike). So every file answers ``Range``
with 206, ``HEAD`` with its size, and a range past the end with 416. Files
are served by exact installed name only, and a request that does not name
this server as 127.0.0.1 or localhost is refused: the map says where the
operator's regions are. Stand-in files only; the real kit is not needed.
"""

from __future__ import annotations

import http.client
import json
from collections.abc import Iterator
from pathlib import Path
from threading import Thread

import pytest

from hammunition.map_page import (
    CREDIT,
    KIT_UNIT,
    REQUIRED,
    TILES_UNIT,
    find_map,
    landing_section,
    map_page,
)
from hammunition.reference import byte_range, make_server

BODY = bytes(range(256)) * 40  # 10,240 bytes, every offset distinct enough


def _data(tmp_path: Path, *, kit: bool = True, regions: tuple[str, ...] = ("vermont",)) -> Path:
    data = tmp_path / "data"
    if kit:
        for rel in REQUIRED:
            path = data / KIT_UNIT / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}" if rel.endswith(".json") else "stand-in")
        fonts = data / KIT_UNIT / "tilemaker/server/static/fonts/KlokanTech Noto Sans Regular"
        fonts.mkdir(parents=True)
        (fonts / "0-255.pbf").write_bytes(b"glyphs")
        (data / KIT_UNIT / "tilemaker" / "resources").mkdir(parents=True)
        (data / KIT_UNIT / "tilemaker" / "resources" / "process-openmaptiles.lua").write_text("--")
    (data / TILES_UNIT).mkdir(parents=True)
    for region in regions:
        (data / TILES_UNIT / f"{region}.pmtiles").write_bytes(BODY)
    return data


@pytest.fixture
def served(tmp_path: Path) -> Iterator[int]:
    shelf = find_map(_data(tmp_path))
    server = make_server(0, "<html>landing</html>", [], map_shelf=shelf, position_port=10111)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()


def _get(
    port: int, path: str, *, method: str = "GET", headers: dict[str, str] | None = None
) -> tuple[int, dict[str, str], bytes]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request(method, path, headers=headers or {})
        response = conn.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        conn.close()


# -- ranges ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("header", "want"),
    [
        (None, None),
        ("bytes=0-99", (0, 99)),
        ("bytes=100-", (100, 999)),
        ("bytes=-10", (990, 999)),
        ("bytes=900-5000", (900, 999)),
        ("bytes=1000-", "unsatisfiable"),
        ("bytes=-0", "unsatisfiable"),
        ("bytes=0-1,5-6", None),
        ("items=0-1", None),
        ("bytes=5-2", None),
    ],
)
def test_a_range_header_is_read_as_rfc_9110_says(
    header: str | None, want: tuple[int, int] | str | None
) -> None:
    assert byte_range(header, 1000) == want


def test_a_tile_file_answers_a_range_with_206_and_exactly_those_bytes(served: int) -> None:
    status, headers, body = _get(
        served, "/map/tiles/vermont.pmtiles", headers={"Range": "bytes=127-16510"}
    )
    assert status == 206
    assert headers["Content-Range"] == f"bytes 127-{len(BODY) - 1}/{len(BODY)}"
    assert body == BODY[127:]
    assert headers["Accept-Ranges"] == "bytes"


def test_head_gives_the_size_and_no_body(served: int) -> None:
    status, headers, body = _get(served, "/map/tiles/vermont.pmtiles", method="HEAD")
    assert status == 200 and body == b""
    assert headers["Content-Length"] == str(len(BODY))
    assert headers["Accept-Ranges"] == "bytes"


def test_a_range_past_the_end_is_416_with_the_size(served: int) -> None:
    status, headers, _ = _get(
        served, "/map/tiles/vermont.pmtiles", headers={"Range": f"bytes={len(BODY)}-"}
    )
    assert status == 416 and headers["Content-Range"] == f"bytes */{len(BODY)}"


def test_the_whole_file_without_a_range(served: int) -> None:
    status, _, body = _get(served, "/map/tiles/vermont.pmtiles")
    assert status == 200 and body == BODY


# -- what is served ---------------------------------------------------------------------


def test_the_page_regions_and_kit_files_are_served_with_their_types(served: int) -> None:
    status, headers, body = _get(served, "/map/")
    assert status == 200 and headers["Content-Type"].startswith("text/html")
    assert CREDIT.encode() in body or "© OpenMapTiles".encode() in body
    status, _, body = _get(served, "/map/regions.json")
    assert json.loads(body) == [{"name": "vermont", "url": "/map/tiles/vermont.pmtiles"}]
    status, headers, _ = _get(served, "/map/kit/maplibre/maplibre-gl.mjs")
    assert status == 200 and headers["Content-Type"] == "text/javascript"
    status, _, body = _get(
        served,
        "/map/kit/tilemaker/server/static/fonts/KlokanTech%20Noto%20Sans%20Regular/0-255.pbf",
    )
    assert status == 200 and body == b"glyphs"
    status, _, _ = _get(served, "/map/kit/sprite@2x.png")
    assert status == 200


@pytest.mark.parametrize(
    "path",
    [
        "/map/kit/tilemaker/resources/process-openmaptiles.lua",  # the converter's, not the page's
        "/map/kit/../osm-pmtiles/vermont.pmtiles",
        "/map/tiles/%2e%2e/vector-map-kit/sprite.png",
        "/map/tiles/nowhere.pmtiles",
        "/etc/passwd",
    ],
)
def test_nothing_but_the_installed_names_is_served(served: int, path: str) -> None:
    assert _get(served, path)[0] == 404


@pytest.mark.parametrize("host", ["evil.example:{port}", "127.0.0.1:1", "", "192.168.1.5:{port}"])
def test_a_request_that_does_not_name_this_server_on_loopback_is_refused(
    served: int, host: str
) -> None:
    """DNS rebinding: a page on another site whose name resolves to
    127.0.0.1 sends its own name as Host, and reads nothing."""
    conn = http.client.HTTPConnection("127.0.0.1", served, timeout=5)
    try:
        conn.putrequest("GET", "/map/regions.json", skip_host=True)
        if host:
            conn.putheader("Host", host.format(port=served))
        conn.endheaders()
        assert conn.getresponse().status == 403
    finally:
        conn.close()


def test_localhost_is_as_good_as_127_0_0_1(served: int) -> None:
    status, _, _ = _get(served, "/map/regions.json", headers={"Host": f"localhost:{served}"})
    assert status == 200


def test_the_server_is_bound_to_loopback(served: int) -> None:
    from test_gps_tether import _listening_addresses

    assert _listening_addresses(served) == {"0100007F"}


# -- the page ------------------------------------------------------------------------------


def test_the_page_carries_the_credit_the_licence_requires_and_names_only_loopback() -> None:
    page = map_page(position_port=10111)
    assert "© OpenMapTiles" in page and "© OpenStreetMap contributors" in page
    assert "attributionControl: {compact: false}" in page
    assert "http://127.0.0.1:10111/position" in page
    # The only absolute URLs are the credit's links, followed only if clicked.
    import re

    urls = set(re.findall(r"https?://[^'\"\\\s<>)]+", page))
    assert urls == {
        "https://openmaptiles.org/",
        "https://www.openstreetmap.org/copyright",
        "http://127.0.0.1:10111/position",
    }


def test_without_the_kit_there_is_no_map_page_and_the_landing_page_says_so(
    tmp_path: Path,
) -> None:
    shelf = find_map(_data(tmp_path, kit=False))
    assert not shelf.ready and "maplibre/maplibre-gl.mjs" in shelf.missing
    server = make_server(0, "x", [], map_shelf=shelf)
    try:
        assert server.map_page is None and server.files == {}
    finally:
        server.server_close()
    assert "hammunition install osm-pmtiles" in landing_section(shelf)


def test_with_regions_the_landing_page_links_the_map(tmp_path: Path) -> None:
    shelf = find_map(_data(tmp_path, regions=("vermont", "delaware")))
    assert shelf.regions == ("delaware", "vermont")
    section = landing_section(shelf)
    assert 'href="/map/"' in section and "2 region(s)" in section


def test_reference_serve_takes_a_position_port(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import importlib
    import os

    cli = importlib.import_module("hammunition.cli.main")
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    assert cli.main(["reference", "serve", "--position-port", "80"]) == cli.EXIT_FAILED
    assert "--position-port 80" in capsys.readouterr().err
