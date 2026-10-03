# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""tar1090 as a page on ``reference serve``'s loopback server.  D-071 (2026-10-02 amendment).

Stand-in files only: a tree shaped like the pinned archive's ``html/``, a
directory standing for readsb's ``/run/readsb``. What is checked here is the
server's half: which files are served and under what name, where ``data/``
points, the Host check, the headers that keep the page from calling out, the
basemap decision and the words that give its reason. The page itself, drawn
by headless Chromium over the real pinned files, is ``test_aircraft_render``.
"""

from __future__ import annotations

import http.client
import json
import os
from collections.abc import Iterator
from pathlib import Path
from threading import Thread

import pytest

from hammunition.aircraft_page import (
    ANCHOR,
    CONTENT_SECURITY_POLICY,
    HTML,
    SRC,
    UNIT,
    AircraftShelf,
    data_file,
    find_aircraft,
    landing_section,
    open_regular,
    receiver_document,
)
from hammunition.map_page import KIT_UNIT, REQUIRED, TILES_UNIT, find_map
from hammunition.reference import make_server

INDEX = (
    "<!doctype html><html><head><title>tar1090</title></head><body>"
    '<script src="libs/ol-custom.js"></script>\n'
    '<script src="early.js"></script>\n'
    '<script src="defaults.js"></script>\n'
    '<script src="config.js"></script>\n'
    f"{ANCHOR}\n"
    '<script src="script.js"></script></body></html>\n'
)
AIRCRAFT_JSON = b'{"now": 1, "aircraft": [{"hex": "a1b2c3", "flight": "TEST1"}]}'


def _tree(data: Path, *, index: str = INDEX) -> Path:
    html = data / UNIT / SRC / HTML
    (html / "libs").mkdir(parents=True)
    (html / "index.html").write_text(index)
    (html / "config.js").write_text("// upstream config, all comments\n")
    (html / "script.js").write_text("// script")
    (html / "style.css").write_text("body{}")
    (html / "libs" / "ol-custom.js").write_text("// ol")
    (html / "early.js").write_text("// early")
    (html / "defaults.js").write_text("// defaults")
    (html / "flags").mkdir()
    (html / "flags" / "us.svg").write_text("<svg/>")
    (data / UNIT / SRC / "LICENSE").write_text("GPL-2.0-or-later")
    return html


def _map(data: Path, *, kit: bool = True, regions: tuple[str, ...] = ("testville",)) -> None:
    if kit:
        for rel in REQUIRED:
            path = data / KIT_UNIT / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}" if rel.endswith(".json") else "stand-in")
    (data / TILES_UNIT).mkdir(parents=True, exist_ok=True)
    for region in regions:
        (data / TILES_UNIT / f"{region}.pmtiles").write_bytes(b"tiles")


@pytest.fixture
def readsb(tmp_path: Path) -> Path:
    directory = tmp_path / "run-readsb"
    directory.mkdir()
    (directory / "aircraft.json").write_bytes(AIRCRAFT_JSON)
    (directory / "receiver.json").write_text('{"version": "3.14", "lat": 0, "lon": 0}')
    return directory


def _shelf(tmp_path: Path, readsb: Path, *, basemap: bool = True) -> AircraftShelf:
    data = tmp_path / "data"
    _tree(data)
    if basemap:
        _map(data)
    shelf = find_aircraft(data, find_map(data), json_dir=readsb)
    assert shelf is not None
    return shelf


def _serve(
    tmp_path: Path, readsb: Path, *, basemap: bool = True
) -> Iterator[tuple[int, AircraftShelf]]:
    shelf = _shelf(tmp_path, readsb, basemap=basemap)
    data = tmp_path / "data"
    server = make_server(
        0, "<html>landing</html>", [], map_shelf=find_map(data), aircraft=shelf, position_port=1
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1], shelf
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def served(tmp_path: Path, readsb: Path) -> Iterator[tuple[int, AircraftShelf]]:
    yield from _serve(tmp_path, readsb)


@pytest.fixture
def served_bare(tmp_path: Path, readsb: Path) -> Iterator[tuple[int, AircraftShelf]]:
    yield from _serve(tmp_path, readsb, basemap=False)


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


# -- finding it -------------------------------------------------------------------------


def test_nothing_is_served_when_the_unit_is_not_installed(tmp_path: Path) -> None:
    assert find_aircraft(tmp_path, None) is None


def test_an_installed_tree_that_is_not_the_pinned_page_is_named_not_served(tmp_path: Path) -> None:
    """The page is rewritten at one anchor. A page without it is not what was
    pinned, and serving it unrewritten would let it ask for tiles online."""
    _tree(tmp_path, index="<html>a different page</html>")
    with pytest.raises(ValueError, match=r"layers\.js"):
        find_aircraft(tmp_path, None)


def test_a_tree_without_an_index_is_named(tmp_path: Path) -> None:
    (tmp_path / UNIT / SRC / HTML).mkdir(parents=True)
    with pytest.raises(ValueError, match=r"index\.html"):
        find_aircraft(tmp_path, None)


def test_the_files_are_the_trees_by_exact_name_and_not_the_replaced_ones(
    tmp_path: Path, readsb: Path
) -> None:
    html = tmp_path / "data" / UNIT / SRC / HTML
    shelf = _shelf(tmp_path, readsb)
    assert shelf.files["/aircraft/style.css"] == html / "style.css"
    assert shelf.files["/aircraft/libs/ol-custom.js"] == html / "libs" / "ol-custom.js"
    assert shelf.files["/aircraft/flags/us.svg"] == html / "flags" / "us.svg"
    # index.html and config.js are ours, never the tree's; the licence is not the page's.
    assert "/aircraft/index.html" not in shelf.files
    assert "/aircraft/config.js" not in shelf.files
    assert not any(k.endswith("LICENSE") for k in shelf.files)


def test_a_link_in_the_tree_is_not_served(tmp_path: Path, readsb: Path) -> None:
    data = tmp_path / "data"
    html = _tree(data)
    (html / "secret.js").symlink_to("/etc/hostname")
    shelf = find_aircraft(data, None, json_dir=readsb)
    assert shelf is not None and "/aircraft/secret.js" not in shelf.files


# -- the basemap decision ----------------------------------------------------------------


def test_with_the_map_installed_the_basemap_is_the_local_pmtiles(
    tmp_path: Path, readsb: Path
) -> None:
    shelf = _shelf(tmp_path, readsb)
    assert shelf.basemap and shelf.reason is None
    assert b"/map/kit/pmtiles/dist/pmtiles.js" in shelf.index
    assert b"/map/tiles/testville.pmtiles" in shelf.layers


@pytest.mark.parametrize(
    ("kit", "regions", "words"),
    [
        (False, (), "vector-map-kit"),
        (True, (), "no region map"),
    ],
)
def test_without_the_map_there_is_no_basemap_and_the_page_says_why(
    tmp_path: Path, readsb: Path, kit: bool, regions: tuple[str, ...], words: str
) -> None:
    data = tmp_path / "data"
    _tree(data)
    _map(data, kit=kit, regions=regions)
    shelf = find_aircraft(data, find_map(data), json_dir=readsb)
    assert shelf is not None and not shelf.basemap
    assert shelf.reason is not None and words in shelf.reason
    assert b"pmtiles.js" not in shelf.index
    assert words.encode() in shelf.layers  # the notice the page draws
    assert b"https://" not in shelf.layers  # and no address of anything else


def test_no_map_shelf_at_all_is_the_same_as_no_map(tmp_path: Path, readsb: Path) -> None:
    data = tmp_path / "data"
    _tree(data)
    shelf = find_aircraft(data, None, json_dir=readsb)
    assert shelf is not None and not shelf.basemap and shelf.reason


def test_the_generated_layers_script_carries_the_regions_as_data_not_as_code(
    tmp_path: Path, readsb: Path
) -> None:
    data = tmp_path / "data"
    _tree(data)
    _map(data, regions=("a'b", "testville"))
    shelf = find_aircraft(data, find_map(data), json_dir=readsb)
    assert shelf is not None
    # Percent-encoded by the map's own listing, then JSON-encoded: a quote in a
    # file name is never a quote in the script.
    assert b"/map/tiles/a%27b.pmtiles" in shelf.layers and b"a'b" not in shelf.layers


def test_the_config_turns_off_everything_that_calls_out(tmp_path: Path, readsb: Path) -> None:
    config = _shelf(tmp_path, readsb).config.decode()
    for line in (
        "planespottersAPI = false;",
        "planespottingAPI = false;",
        'routeApiUrl = "";',
        "showPictures = false;",
        "useRouteAPI = false;",
        "jetphotoLinks = false;",
        "planespottersLinks = false;",
        "tfrs = false;",
        "offlineMapDetail = 0;",
    ):
        assert line in config, line


def test_the_page_is_told_which_one_base_layer_it_has(tmp_path: Path, readsb: Path) -> None:
    """tar1090 picks its base layer by name from browser storage; a name this
    page does not have would leave it with none visible."""
    with_map = _shelf(tmp_path / "a", readsb).layers.decode()
    assert (
        "MapType_tar1090 = config.reason === null ? 'hammunition_pmtiles' : 'hammunition_none'"
        in with_map
    )
    assert "name: 'hammunition_pmtiles'" in with_map and "name: 'hammunition_none'" in with_map


# -- serving ------------------------------------------------------------------------------


def test_the_page_is_rewritten_and_the_support_files_are_served(
    served: tuple[int, AircraftShelf],
) -> None:
    port, _ = served
    status, headers, body = _get(port, "/aircraft/")
    assert status == 200 and headers["Content-Type"].startswith("text/html")
    text = body.decode()
    order = [
        text.index(n) for n in ("config.js", "layers.js", "hammunition-layers.js", "script.js")
    ]
    assert order == sorted(order), "ours comes after tar1090's own layers, before it builds them"
    assert '<script src="/map/kit/pmtiles/dist/pmtiles.js"></script>' in text
    status, headers, body = _get(port, "/aircraft/hammunition-layers.js")
    assert status == 200 and headers["Content-Type"] == "text/javascript"
    status, headers, body = _get(port, "/aircraft/config.js")
    assert status == 200 and b"planespottersAPI = false;" in body
    status, headers, _ = _get(port, "/aircraft/libs/ol-custom.js")
    assert status == 200 and headers["Content-Type"] == "text/javascript"
    status, headers, _ = _get(port, "/aircraft/flags/us.svg")
    assert status == 200 and headers["Content-Type"] == "image/svg+xml"


def test_the_bare_page_asks_for_no_map_kit(served_bare: tuple[int, AircraftShelf]) -> None:
    port, _ = served_bare
    body = _get(port, "/aircraft/")[2].decode()
    assert "pmtiles.js" not in body and "hammunition-layers.js" in body


def test_aircraft_without_the_slash_goes_to_the_page(served: tuple[int, AircraftShelf]) -> None:
    port, _ = served
    status, headers, _ = _get(port, "/aircraft")
    assert status == 301 and headers["Location"] == "/aircraft/"


def test_every_page_response_carries_the_policy_that_forbids_leaving_loopback(
    served: tuple[int, AircraftShelf],
) -> None:
    port, _ = served
    for path in (
        "/aircraft/",
        "/aircraft/config.js",
        "/aircraft/style.css",
        "/aircraft/data/aircraft.json",
        "/aircraft/data/nothing.json",
        "/aircraft/nothing",
    ):
        policy = _get(port, path)[1].get("Content-Security-Policy")
        assert policy == CONTENT_SECURITY_POLICY, path
    # the map page keeps its own rules; this policy is the aircraft page's
    assert "Content-Security-Policy" not in _get(port, "/")[1]
    policy = CONTENT_SECURITY_POLICY
    assert "connect-src 'self'" in policy and "img-src 'self' data: blob:" in policy
    assert "default-src 'self'" in policy and "form-action 'none'" in policy
    assert "frame-ancestors 'none'" in policy
    assert "http" not in policy  # no source names a host


def test_readsbs_json_is_read_from_its_directory_and_never_cached(
    served: tuple[int, AircraftShelf],
) -> None:
    port, _ = served
    status, headers, body = _get(port, "/aircraft/data/aircraft.json?_=123")
    assert status == 200 and body == AIRCRAFT_JSON
    assert headers["Content-Type"] == "application/json"
    assert headers["Cache-Control"] == "no-store"
    status, headers, body = _get(port, "/aircraft/data/receiver.json")
    assert status == 200 and headers["Cache-Control"] == "no-store"
    assert json.loads(body)["history"] == 0


def test_a_json_file_readsb_has_not_written_is_404(served: tuple[int, AircraftShelf]) -> None:
    assert _get(served[0], "/aircraft/data/stats.json")[0] == 404


@pytest.mark.parametrize(
    "path",
    [
        "/aircraft/data/../aircraft/index.html",
        "/aircraft/data/%2e%2e/receiver.json",
        "/aircraft/data/%2e%2e/%2e%2e/secret.json",
        "/aircraft/data/sub/x.json",
        "/aircraft/data/sub%2Fx.json",
        "/aircraft/data/chunks/chunks.json",
        "/aircraft/data/traces/00/trace_recent_a1b2c3.json",
        "/aircraft/data/.hidden.json",
        "/aircraft/data/aircraft.json.gz",
        "/aircraft/data/aircraft.txt",
        "/aircraft/data/dir.json",
        "/aircraft/data/",
        "/aircraft/data",
        "/aircraft/data/%00.json",
        "/aircraft/db2/anything.js",
        "/aircraft/upintheair.json",
        "/aircraft/../map/regions.json",
    ],
)
def test_only_a_plain_json_name_in_readsbs_directory_is_served(
    tmp_path: Path, readsb: Path, path: str
) -> None:
    """Every refused name has a real file where a loose guard would find it:
    the check is the guard, not the absence of a file."""
    (readsb / ".hidden.json").write_text("{}")
    (readsb / "aircraft.json.gz").write_bytes(b"gz")
    (readsb / "aircraft.txt").write_text("text")
    (readsb / "dir.json").mkdir()
    (readsb / "sub").mkdir()
    (readsb / "sub" / "x.json").write_text("{}")
    (readsb / "chunks").mkdir()
    (readsb / "chunks" / "chunks.json").write_text("{}")
    (tmp_path / "secret.json").write_text('{"secret": true}')  # beside readsb's directory
    (tmp_path / "receiver.json").write_text('{"secret": true}')
    for port, _ in _serve(tmp_path, readsb):
        status, _, body = _get(port, path)
        assert status in (301, 404), path
        assert b"secret" not in body


def test_a_link_in_readsbs_directory_is_not_followed(
    tmp_path: Path, readsb: Path, served: tuple[int, AircraftShelf]
) -> None:
    (readsb / "evil.json").symlink_to("/etc/hostname")
    assert _get(served[0], "/aircraft/data/evil.json")[0] == 404
    assert data_file(served[1], "evil.json") is None
    assert data_file(served[1], "aircraft.json") == readsb / "aircraft.json"


@pytest.mark.parametrize("host", ["evil.example:{port}", "127.0.0.1:1", "", "192.168.1.5:{port}"])
def test_a_request_that_does_not_name_this_server_on_loopback_is_refused(
    served: tuple[int, AircraftShelf], host: str
) -> None:
    """A page on another site whose name resolves to 127.0.0.1 would read
    the aircraft the operator's own receiver hears, and where it is."""
    port, _ = served
    for path in ("/aircraft/", "/aircraft/data/aircraft.json", "/aircraft/config.js"):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            conn.putrequest("GET", path, skip_host=True)
            if host:
                conn.putheader("Host", host.format(port=port))
            conn.endheaders()
            assert conn.getresponse().status == 403, path
        finally:
            conn.close()


def test_nothing_aircraft_is_served_when_the_unit_is_not_installed(tmp_path: Path) -> None:
    server = make_server(0, "<html>landing</html>", [])
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        assert _get(port, "/aircraft/")[0] == 404
        assert _get(port, "/aircraft/data/aircraft.json")[0] == 404
    finally:
        server.shutdown()
        server.server_close()


def test_the_server_is_still_bound_to_loopback(served: tuple[int, AircraftShelf]) -> None:
    from hammunition.listening import listening_addresses

    assert listening_addresses(served[0]) == {"0100007F"}


# -- receiver.json ----------------------------------------------------------------------


def test_receiver_json_is_reduced_to_what_a_plain_aircraft_json_page_needs(
    tmp_path: Path, readsb: Path
) -> None:
    """Debian's readsb writes ``aircraft.binCraft.zst`` too, and tar1090 asks for
    it, for globe-index files or for history chunks when this file says so:
    none is served, so none of those keys may reach the page."""
    (readsb / "receiver.json").write_text(
        json.dumps(
            {
                "version": "3.14.1630",
                "refresh": 1000,
                "history": 120,
                "readsb": True,
                "binCraft": True,
                "aircraft_binCraft": True,
                "zstd": True,
                "reapi": True,
                "haveTraces": True,
                "globeIndexGrid": 3,
                "globeIndexSpecialTiles": [{"north": 1, "south": 0, "east": 1, "west": 0}],
                "dbServer": True,
                "lat": 12.5,
                "lon": -45.25,
                "outlineJson": "x",
            }
        )
    )
    shelf = _shelf(tmp_path, readsb)
    document = receiver_document(shelf)
    assert document is not None
    assert json.loads(document) == {
        "version": "3.14.1630",
        "refresh": 1000.0,
        "history": 0,
        "readsb": True,
        "lat": 12.5,
        "lon": -45.25,
    }


def test_a_directory_with_only_aircraft_json_still_gets_a_receiver_document(
    tmp_path: Path, readsb: Path
) -> None:
    (readsb / "receiver.json").unlink()
    shelf = _shelf(tmp_path, readsb)
    assert json.loads(receiver_document(shelf) or b"") == {
        "version": "unknown",
        "refresh": 1000,
        "history": 0,
    }


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        "[1, 2]",
        '{"refresh": "fast", "lat": 91, "lon": 0, "version": 7}',
        '{"refresh": 5, "lat": true, "lon": true}',
        '{"refresh": NaN, "lat": NaN, "lon": 1}',
        "x" * (1 << 21),
    ],
)
def test_a_receiver_json_that_is_not_usable_is_replaced_by_the_defaults(
    tmp_path: Path, readsb: Path, text: str
) -> None:
    (readsb / "receiver.json").write_text(text)
    shelf = _shelf(tmp_path, readsb)
    assert json.loads(receiver_document(shelf) or b"") == {
        "version": "unknown",
        "refresh": 1000,
        "history": 0,
    }


def test_there_is_no_receiver_document_before_readsb_has_written_aircraft_json(
    tmp_path: Path, readsb: Path, served: tuple[int, AircraftShelf]
) -> None:
    (readsb / "aircraft.json").unlink()
    assert receiver_document(served[1]) is None
    assert _get(served[0], "/aircraft/data/receiver.json")[0] == 404


def test_a_receiver_json_that_is_a_link_is_not_read(tmp_path: Path, readsb: Path) -> None:
    target = tmp_path / "elsewhere.json"
    target.write_text('{"version": "from-a-link"}')
    (readsb / "receiver.json").unlink()
    (readsb / "receiver.json").symlink_to(target)
    document = receiver_document(_shelf(tmp_path, readsb))
    assert document is not None and b"from-a-link" not in document


# -- reading without following ------------------------------------------------------------


def test_open_regular_refuses_a_link_a_directory_and_a_fifo(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.write_text("x")
    (tmp_path / "link").symlink_to(plain)
    (tmp_path / "dir").mkdir()
    os.mkfifo(tmp_path / "fifo")
    handle = open_regular(plain)
    assert handle is not None
    with handle:
        assert handle.read() == b"x"
    assert open_regular(tmp_path / "link") is None
    assert open_regular(tmp_path / "dir") is None
    assert open_regular(tmp_path / "fifo") is None  # and does not block
    assert open_regular(tmp_path / "absent") is None


def test_a_tree_file_swapped_for_a_link_after_the_listing_is_not_served(
    tmp_path: Path, readsb: Path, served: tuple[int, AircraftShelf]
) -> None:
    port, shelf = served
    path = shelf.files["/aircraft/style.css"]
    path.unlink()
    path.symlink_to("/etc/hostname")
    assert _get(port, "/aircraft/style.css")[0] == 404


def test_an_unreadable_index_is_named_not_a_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _tree(tmp_path)

    def refuse(self: Path, *args: object, **kwargs: object) -> str:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(Path, "read_text", refuse)
    with pytest.raises(ValueError, match="cannot be read"):
        find_aircraft(tmp_path, None)


# -- the redirect, HEAD and ranges carry the same rules --------------------------------------


def test_the_redirect_head_and_a_range_carry_the_policy_and_the_host_check(
    served: tuple[int, AircraftShelf],
) -> None:
    port, _ = served
    for method, path, headers, want in (
        ("GET", "/aircraft", {}, 301),
        ("HEAD", "/aircraft/", {}, 200),
        ("HEAD", "/aircraft/data/aircraft.json", {}, 200),
        ("GET", "/aircraft/style.css", {"Range": "bytes=0-1"}, 206),
        ("GET", "/aircraft/style.css", {"Range": "bytes=999-"}, 416),
    ):
        status, response, body = _get(port, path, method=method, headers=headers)
        assert status == want, (method, path)
        assert response["Content-Security-Policy"] == CONTENT_SECURITY_POLICY, (method, path)
        if method == "HEAD":
            assert body == b""
    for method, path in (("GET", "/aircraft"), ("HEAD", "/aircraft/")):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            conn.putrequest(method, path, skip_host=True)
            conn.putheader("Host", "evil.example")
            conn.endheaders()
            response_ = conn.getresponse()
            assert response_.status == 403, (method, path)
        finally:
            conn.close()


# -- the landing page -------------------------------------------------------------------


def test_the_landing_page_links_the_page_and_says_where_the_data_comes_from(
    tmp_path: Path, readsb: Path
) -> None:
    text = landing_section(_shelf(tmp_path, readsb))
    assert 'href="/aircraft/"' in text and str(readsb) in text


def test_the_landing_page_says_when_readsbs_directory_is_not_there_yet(
    tmp_path: Path, readsb: Path
) -> None:
    data = tmp_path / "data"
    _tree(data)
    shelf = find_aircraft(data, None, json_dir=tmp_path / "absent")
    assert shelf is not None
    text = landing_section(shelf)
    assert "not there" in text and "readsb" in text


def test_the_landing_page_says_the_basemap_reason(tmp_path: Path, readsb: Path) -> None:
    data = tmp_path / "data"
    _tree(data)
    shelf = find_aircraft(data, None, json_dir=readsb)
    assert shelf is not None and shelf.reason is not None
    assert shelf.reason in landing_section(shelf).replace("&amp;", "&")


def test_the_landing_page_names_the_command_when_it_is_not_installed() -> None:
    assert "hammunition install tar1090" in landing_section(None)
