# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""`hammunition reference serve`: the offline reference on one loopback page.  D-066.

Three kinds of thing, kept apart as the catalog keeps them: the books are
ZIM files read by ``kiwix-serve``; the ICS forms are PDFs, which are just
files; the dictionaries are ``dictd`` on 127.0.0.1:2628, which speaks DICT,
not HTTP, and needs no page of its own beyond saying how to ask it.

So this runs two loopback servers behind one page:

* the landing page, from the standard library, on ``127.0.0.1:PORT``: every
  installed book with a link into kiwix, every form under ``/forms/``, and
  the dictionaries;
* ``kiwix-serve`` on ``127.0.0.1:PORT+1``, as a child. **Its argv always
  carries ``-i 127.0.0.1``**: without it kiwix-serve listens on every
  address of the machine (measured 2026-09-29, ``*:port``, and it prints its
  LAN URL), and its default port, 80, needs root. ``-a`` names this process,
  so kiwix-serve exits if this one is killed without the chance to stop it.

The library kiwix-serve reads is built here, by ``kiwix-manage``, in the
operator's cache, every time the verb starts: running a parser of downloaded
files is the reader's business and the operator's, never root's (D-057), and
a library rebuilt from what is on disk cannot go stale.

Ctrl-C stops both. A kiwix-serve that exits on its own stops the page too,
and the verb fails with the child's exit code in its message. Nothing is
reachable from another machine; ``--port`` moves the page, never the
address.

**Routes (D-076).** With the map and GraphHopper's route graph installed,
GraphHopper's own server is a third child, on 127.0.0.1 at a port the system
chooses, and the map asks for a route at ``/map/route`` on *this* server,
which checks the Host header, rebuilds the request
(:func:`hammunition.graphhopper.route_query`) and relays GraphHopper's
answer. GraphHopper sends ``Access-Control-Allow-Origin: *`` and checks no
Host header (measured), so the page never calls it directly. A GraphHopper
that exits is reported once, and the books and the map keep serving.
"""

from __future__ import annotations

import ctypes
import html
import http.client
import http.server
import json
import os
import re
import shutil
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import quote, unquote

from . import aircraft_page, tether_contract
from .aircraft_page import AircraftShelf
from .graphhopper import HOST as ROUTER_HOST
from .graphhopper import RouteRefused, RouterSpec, route_query
from .kiwix import Book
from .map_page import (
    MAP,
    OVERLAYS,
    REGIONS,
    ROUTE,
    MapShelf,
    landing_section,
    map_page,
    overlays_json,
    regions_json,
)

HOST = "127.0.0.1"
PORT = 8480
WIKI = "/wiki"
#: Where the GPS tether serves ``/position`` (D-071), the page's default.
POSITION_PORT = tether_contract.POSITION_PORT
FORMS = "/forms/"
LIBRARY_UNIT = "kiwix-library"
FORMS_UNIT = "ics-forms"
STOP_WAIT = 5.0
#: How long a route may take GraphHopper; the spike's slowest first query was 1 s.
ROUTE_TIMEOUT = 60.0
#: The largest answer relayed: a route's GeoJSON and instructions, not a map.
ROUTE_LIMIT = 32 << 20
#: Linux's prctl(PR_SET_PDEATHSIG).
PR_SET_PDEATHSIG = 1


def die_with_parent() -> None:
    """In a child, before it runs its program: receive SIGTERM when this
    process's parent dies. GraphHopper has no ``-a PID`` as kiwix-serve does,
    so a ``reference serve`` killed without the chance to stop it would
    otherwise leave GraphHopper running. Linux only; anywhere else, nothing."""
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        libc.prctl(PR_SET_PDEATHSIG, 15, 0, 0, 0)
    except (OSError, AttributeError):  # pragma: no cover - not Linux
        pass


@dataclass
class RouterState:
    """The GraphHopper child as the page's route handler sees it."""

    port: int
    profiles: tuple[str, ...]
    log: Path
    exited: int | None = None
    why: str | None = None
    """Why GraphHopper never started, when it did not (review, 2026-10-01)."""


def serve_port(text: str) -> int:
    """``--port``: 1024 to 65534, because kiwix-serve takes the port after it."""
    stripped = text.strip()
    if not stripped.isdigit():
        raise ValueError(f"--port {text}: not a port number; give a port from 1024 to 65534")
    number = int(stripped)
    if not 1024 <= number <= 65534:
        raise ValueError(
            f"--port {text}: give a port from 1024 to 65534 (below 1024 only root may "
            f"listen, and kiwix-serve takes the port after this one)"
        )
    return number


def position_port(text: str, *, flag: str = "--position-port") -> int:
    """``--position-port``: where the page asks the tether, 1024 to 65535.

    The tether, not this server, listens there, and it never runs as root.
    """
    stripped = text.strip()
    digits = stripped.removeprefix("-")
    number = int(digits) if digits.isascii() and digits.isdigit() else None
    if number is None:
        raise ValueError(f"{flag} {text}: not a number; give a port from 1024 to 65535")
    if stripped.startswith("-") or number < 1024:
        raise ValueError(
            f"{flag} {text}: below 1024, where only root may listen, and the tether "
            f"never runs as root; give a port from 1024 to 65535"
        )
    if number > 65535:
        raise ValueError(
            f"{flag} {text}: above 65535, the highest TCP port; give a port from 1024 to 65535"
        )
    return number


def kiwix_serve_argv(port: int, library: Path, *, pid: int) -> list[str]:
    """kiwix-serve on loopback only, behind ``/wiki``, external links blocked,
    the library watched for changes, and bound to this process's life."""
    return [
        "kiwix-serve",
        "--library",
        "-i",
        HOST,
        "-p",
        str(port),
        "-r",
        WIKI,
        "-b",
        "-M",
        "-a",
        str(pid),
        str(library),
    ]


@dataclass(frozen=True)
class ShelfBook:
    """An installed ZIM, with what the book list says of it when it says anything."""

    path: Path
    title: str
    licence: str | None
    licence_url: str | None

    @property
    def stem(self) -> str:
        return self.path.name.removesuffix(".zim")


@dataclass(frozen=True)
class Shelf:
    """What is installed to serve."""

    books: tuple[ShelfBook, ...]
    forms: tuple[Path, ...]
    dict_client: bool
    goldendict: bool


def _book_for(path: Path, books: Mapping[str, Book]) -> ShelfBook:
    stem = path.name.removesuffix(".zim")
    book_id = stem.rsplit("_", 1)[0] if "_" in stem else stem
    book = books.get(book_id)
    if book is None:
        return ShelfBook(path, stem, None, None)
    return ShelfBook(path, book.title, book.licence, book.licence_url)


def find_shelf(
    data: Path,
    books: Mapping[str, Book],
    *,
    which: Callable[[str], str | None] = shutil.which,
) -> Shelf:
    """The books under ``<data>/kiwix-library``, the PDFs under
    ``<data>/ics-forms``, and whether ``dict`` and goldendict-ng are here."""
    zims = sorted(
        p for p in (data / LIBRARY_UNIT).glob("*.zim") if p.is_file() and not p.is_symlink()
    )
    forms = sorted(
        p for p in (data / FORMS_UNIT).glob("*.pdf") if p.is_file() and not p.is_symlink()
    )
    return Shelf(
        books=tuple(_book_for(p, books) for p in zims),
        forms=tuple(forms),
        dict_client=which("dict") is not None,
        goldendict=which("goldendict") is not None or which("goldendict-ng") is not None,
    )


def landing_page(
    shelf: Shelf,
    *,
    kiwix_port: int,
    map_shelf: MapShelf | None = None,
    routes: str | None = None,
    aircraft: AircraftShelf | None = None,
) -> str:
    """The page. Every name that came from the disk is escaped."""
    e = html.escape
    wiki = f"http://{HOST}:{kiwix_port}{WIKI}"
    parts = [
        "<!doctype html>",
        '<html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>Offline reference</title>",
        "<style>body{font:16px/1.5 system-ui,sans-serif;max-width:48rem;margin:1rem auto;"
        + "padding:0 1rem}li{margin:.3rem 0}small{color:#555}code{background:#eee;padding:0 .2rem}"
        + "</style></head><body>",
        "<h1>Offline reference</h1>",
        "<p><small>Served on this machine only (127.0.0.1). Nothing here needs a network.</small></p>",
        "<h2>Books</h2>",
    ]
    if shelf.books:
        parts.append(f'<p><a href="{e(wiki)}/">Search every book</a> (Kiwix)</p><ul>')
        for book in shelf.books:
            licence = f" <small>{e(book.licence)}</small>" if book.licence else ""
            parts.append(
                f'<li><a href="{e(wiki)}/content/{e(book.stem)}">{e(book.title)}</a>{licence}</li>'
            )
        parts.append("</ul>")
    else:
        parts.append(
            "<p>No books are installed. Choose some with "
            "<code>hammunition station set --reference-books ID[,ID…]</code> "
            "(<code>hammunition reference books</code> lists them), then "
            "<code>hammunition install kiwix-library</code>.</p>"
        )
    parts.append("<h2>ICS forms</h2>")
    if shelf.forms:
        parts.append("<ul>")
        for form in shelf.forms:
            parts.append(f'<li><a href="{FORMS}{e(form.name)}">{e(form.name)}</a></li>')
        parts.append(
            "</ul><p><small>FEMA, US federal works: public domain (17 USC 105).</small></p>"
        )
    else:
        parts.append("<p>Not installed: <code>hammunition install ics-forms</code>.</p>")
    parts.append("<h2>Dictionaries</h2>")
    if shelf.dict_client:
        parts.append(
            "<p>In a terminal: <code>dict WORD</code> asks the local dictd (GCIDE, WordNet, "
            "FOLDOC, VERA acronyms). <code>dict -D</code> lists them.</p>"
        )
    else:
        parts.append("<p>Not installed: <code>hammunition install dictionaries</code>.</p>")
    if shelf.goldendict:
        parts.append(
            "<p>On the desktop: goldendict-ng looks words up in the same dictionaries.</p>"
        )
    if map_shelf is not None:
        parts.append(landing_section(map_shelf))
        if routes is not None:
            parts.append(f"<p>Routes: {e(routes)}</p>")
    parts.append(aircraft_page.landing_section(aircraft))
    parts.append("</body></html>")
    return "\n".join(parts) + "\n"


#: Content types by suffix for the map's files (D-071). A module script must be
#: served as JavaScript or the browser refuses to run it.
KINDS: dict[str, str] = {
    ".mjs": "text/javascript",
    ".js": "text/javascript",
    ".css": "text/css",
    ".json": "application/json",
    ".png": "image/png",
    ".pbf": "application/x-protobuf",
    ".pmtiles": "application/octet-stream",
    ".pdf": "application/pdf",
    # D-075: the infrastructure overlays and the style's licence notice.
    ".geojson": "application/geo+json",
    ".openinframap": "text/plain; charset=utf-8",
    # the aircraft page (tar1090's html/): its flags and icons, its page
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".gif": "image/gif",
    ".jpg": "image/jpeg",
    ".html": "text/html; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
}
_RANGE = re.compile(r"bytes=(\d{0,19})-(\d{0,19})")
CHUNK = 1 << 16


def byte_range(header: str | None, size: int) -> tuple[int, int] | str | None:
    """The (first, last) byte a ``Range`` header asks of a *size*-byte file.

    None when there is no header, or one this does not read (a list of
    ranges, another unit): the whole file is sent, which RFC 9110 allows.
    ``"unsatisfiable"`` when it starts past the end, which is a 416.
    """
    if header is None:
        return None
    match = _RANGE.fullmatch(header.strip())
    if match is not None and size == 0 and (match.group(1) or match.group(2)):
        return "unsatisfiable"  # no byte of an empty file can be asked for
    if match is None or not (match.group(1) or match.group(2)):
        return None
    first, last = match.group(1), match.group(2)
    if not first:  # the last N bytes
        count = int(last)
        if count == 0:
            return "unsatisfiable"
        return max(0, size - count), size - 1
    start = int(first)
    end = int(last) if last else size - 1
    if start >= size:
        return "unsatisfiable"
    if end < start:
        return None
    return start, min(end, size - 1)


class _Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    page: bytes
    forms: dict[str, Path]
    map_page: bytes | None
    regions: bytes
    overlays: bytes
    files: dict[str, Path]
    router: RouterState | None
    aircraft: AircraftShelf | None


class _Handler(http.server.BaseHTTPRequestHandler):
    server: _Server
    #: Headers added to every response of this request (the aircraft page's policy).
    extra: tuple[tuple[str, str], ...] = ()

    def end_headers(self) -> None:
        for name, value in self.extra:
            self.send_header(name, value)
        super().end_headers()

    def log_message(self, format: str, *args: object) -> None:
        """Quiet: the terminal is for what the operator needs."""

    def _send(self, status: int, body: bytes, kind: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, message: str) -> None:
        self._send(status, (json.dumps({"message": message}) + "\n").encode(), "application/json")

    def _route(self, query: str) -> None:
        """A route, asked of GraphHopper as :func:`route_query` rebuilds it,
        and its answer relayed (D-076)."""
        router = self.server.router
        assert router is not None
        if router.why is not None:
            self._json(503, f"routes are off: {router.why}")
            return
        if router.exited is not None:
            self._json(
                503,
                f"the router stopped (exit {router.exited}); its log is {router.log}. "
                f"Restart `hammunition reference serve`.",
            )
            return
        try:
            path = route_query(query, router.profiles)
        except RouteRefused as exc:
            self._json(400, str(exc))
            return
        conn = http.client.HTTPConnection(ROUTER_HOST, router.port, timeout=ROUTE_TIMEOUT)
        try:
            conn.request("GET", path, headers={"Accept": "application/json"})
            answer = conn.getresponse()
            body = answer.read(ROUTE_LIMIT + 1)
            status = answer.status
        except ConnectionRefusedError:
            self._json(503, "the router is still starting; try again in a few seconds")
            return
        except (OSError, http.client.HTTPException) as exc:
            self._json(502, f"the router did not answer: {exc}")
            return
        finally:
            conn.close()
        if len(body) > ROUTE_LIMIT:
            self._json(502, "the router's answer was too large to relay")
            return
        if status != 200 and not 400 <= status < 500:
            self._json(502, f"the router answered {status}")
            return
        self._send(status, body, "application/json")

    def _host_ok(self) -> bool:
        """The request names this server as 127.0.0.1 or localhost, on its
        own port. A page on another site whose name an attacker points at
        127.0.0.1 (DNS rebinding) sends its own name, and is refused: the map
        files say where the operator's regions are (D-071)."""
        port = self.server.server_address[1]
        host = (self.headers.get("Host") or "").strip().lower()
        return host in {f"{HOST}:{port}", f"localhost:{port}"}

    def _aircraft(self, path: str) -> None:
        """The aircraft page (tar1090), under a policy that names no host."""
        shelf = self.server.aircraft
        assert shelf is not None
        self.extra = (("Content-Security-Policy", aircraft_page.CONTENT_SECURITY_POLICY),)
        if path == aircraft_page.AIRCRAFT.rstrip("/"):
            self.send_response(301)
            self.send_header("Location", aircraft_page.AIRCRAFT)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if path in (aircraft_page.AIRCRAFT, aircraft_page.AIRCRAFT + "index.html"):
            self._send(200, shelf.index, "text/html; charset=utf-8")
            return
        if path == aircraft_page.AIRCRAFT + "config.js":
            self._send(200, shelf.config, "text/javascript")
            return
        if path == aircraft_page.AIRCRAFT + aircraft_page.LAYERS_FILE:
            self._send(200, shelf.layers, "text/javascript")
            return
        if path.startswith(aircraft_page.DATA):
            # readsb's output, one plain ``name.json`` at a time: nothing is
            # joined to a directory but a name of letters, digits, _ and -.
            name = unquote(path[len(aircraft_page.DATA) :])
            if name == aircraft_page.RECEIVER:
                document = aircraft_page.receiver_document(shelf)
                if document is None:
                    self._send(404, b"not found\n", "text/plain")
                    return
                self.extra = (*self.extra, ("Cache-Control", "no-store"))
                self._send(200, document, "application/json")
                return
            found = aircraft_page.data_file(shelf, name)
            if found is None:
                self._send(404, b"not found\n", "text/plain")
                return
            self.extra = (*self.extra, ("Cache-Control", "no-store"))
            self._send_file(found)
            return
        found = shelf.files.get(unquote(path))
        if found is None:
            self._send(404, b"not found\n", "text/plain")
            return
        self._send_file(found)

    def _send_file(self, path: Path) -> None:
        """A file, whole or the one byte range asked for, and HEAD its size."""
        kind = KINDS.get(path.suffix, "application/octet-stream")
        handle = aircraft_page.open_regular(path)
        if handle is None:
            self._send(404, b"not found\n", "text/plain")
            return
        with handle:
            size = os.fstat(handle.fileno()).st_size
            asked = byte_range(self.headers.get("Range"), size)
            if asked == "unsatisfiable":
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if isinstance(asked, tuple):
                first, last = asked
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {first}-{last}/{size}")
            else:
                first, last = 0, size - 1
                self.send_response(200)
            length = last - first + 1 if size else 0
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(length))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            if self.command == "HEAD":
                return
            handle.seek(first)
            left = length
            while left > 0:
                chunk = handle.read(min(CHUNK, left))
                if not chunk:
                    break
                self.wfile.write(chunk)
                left -= len(chunk)

    def do_GET(self) -> None:
        self.extra = ()
        if not self._host_ok():
            self._send(403, b"refused: ask for 127.0.0.1 or localhost\n", "text/plain")
            return
        path, _, query = self.path.partition("?")
        if self.server.aircraft is not None and (
            path == aircraft_page.AIRCRAFT.rstrip("/") or path.startswith(aircraft_page.AIRCRAFT)
        ):
            self._aircraft(path)
            return
        if path == ROUTE and self.server.router is not None and self.server.map_page is not None:
            self._route(query)
            return
        if path == "/":
            self._send(200, self.server.page, "text/html; charset=utf-8")
            return
        if self.server.map_page is not None:
            if path in (MAP, MAP.rstrip("/")):
                self._send(200, self.server.map_page, "text/html; charset=utf-8")
                return
            if path == REGIONS:
                self._send(200, self.server.regions, "application/json")
                return
            if path == OVERLAYS:
                self._send(200, self.server.overlays, "application/json")
                return
            # By its exact installed name only: decoded, then looked up.
            # Nothing is joined to a directory, so no path reaches anything else.
            found = self.server.files.get(unquote(path))
            if found is not None:
                self._send_file(found)
                return
        # A form is served only by its exact installed name: nothing is
        # decoded, joined or resolved, so no path can reach anything else.
        form = self.server.forms.get(path)
        if form is not None:
            try:
                body = form.read_bytes()
            except OSError:
                self._send(404, b"not found\n", "text/plain")
                return
            self._send(200, body, "application/pdf")
            return
        self._send(404, b"not found\n", "text/plain")

    do_HEAD = do_GET


def make_server(
    port: int,
    page: str,
    forms: Sequence[Path],
    *,
    map_shelf: MapShelf | None = None,
    position_port: int = POSITION_PORT,
    router: RouterState | None = None,
    aircraft: AircraftShelf | None = None,
) -> _Server:
    """The landing server, bound to 127.0.0.1 and nothing else; with
    *map_shelf*, the offline map beside it (D-071); with *router*, its route
    control and ``/map/route`` (D-076); with *aircraft*, tar1090 at
    ``/aircraft/``."""
    server = _Server((HOST, port), _Handler)
    server.page = page.encode("utf-8")
    server.forms = {f"{FORMS}{quote(p.name)}": p for p in forms}
    server.map_page = None
    server.regions = b"[]\n"
    server.overlays = b"[]\n"
    server.files = {}
    server.router = None
    server.aircraft = aircraft
    if map_shelf is not None and map_shelf.ready:
        server.router = router
        server.map_page = map_page(
            position_port=position_port, router=router.profiles if router else None
        ).encode("utf-8")
        server.regions = regions_json(map_shelf)
        server.overlays = overlays_json(map_shelf)
        server.files = dict(map_shelf.files)
    return server


class Child(Protocol):
    def poll(self) -> int | None: ...
    def terminate(self) -> None: ...
    def wait(self, timeout: float | None = None) -> int: ...
    def kill(self) -> None: ...


def _stop(child: Child) -> None:
    if child.poll() is not None:
        return
    child.terminate()
    try:
        child.wait(timeout=STOP_WAIT)
    except Exception:  # subprocess.TimeoutExpired, or anything a child raises
        child.kill()


def run(
    port: int,
    *,
    shelf: Shelf,
    library: Path,
    spawn: Callable[[Sequence[str]], Child],
    manage: Callable[[Path, Sequence[Path]], None],
    tick: Callable[[], None] = lambda: time.sleep(0.5),
    log: Callable[[str], None] = print,
    pid: int | None = None,
    map_shelf: MapShelf | None = None,
    position_port: int = POSITION_PORT,
    router: RouterSpec | None = None,
    start_router: Callable[[RouterSpec], Child] | None = None,
    routes_note: str | None = None,
    aircraft: AircraftShelf | None = None,
) -> int:
    """Serve until Ctrl-C (exit 0) or until kiwix-serve exits (exit 1).

    With *router* and *start_router*, GraphHopper is started first and
    stopped with the page; its exiting is reported once and serving goes on."""
    import os

    child: Child | None = None
    router_child: Child | None = None
    thread: threading.Thread | None = None
    kiwix_port = port + 1
    state = (
        RouterState(port=router.port, profiles=router.profiles, log=router.log)
        if router is not None and start_router is not None
        else None
    )
    routes = (
        f"the map's Route control (GraphHopper, {', '.join(state.profiles)})"
        if state is not None
        else routes_note
    )
    server = make_server(
        port,
        landing_page(
            shelf, kiwix_port=kiwix_port, map_shelf=map_shelf, routes=routes, aircraft=aircraft
        ),
        shelf.forms,
        map_shelf=map_shelf,
        position_port=position_port,
        router=state,
        aircraft=aircraft,
    )
    try:
        if shelf.books:
            library.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            library.unlink(missing_ok=True)
            manage(library, [b.path for b in shelf.books])
            child = spawn(
                kiwix_serve_argv(kiwix_port, library, pid=pid if pid is not None else os.getpid())
            )
        if router is not None and start_router is not None and server.router is not None:
            try:
                router_child = start_router(router)
            except OSError as exc:
                # Never the page's failure, and never reported as its port
                # (review, 2026-10-01): the books and the map go on.
                server.router.why = f"GraphHopper could not start: {exc}"
                server.page = landing_page(
                    shelf,
                    kiwix_port=kiwix_port,
                    map_shelf=map_shelf,
                    routes=f"off: {server.router.why}",
                    aircraft=aircraft,
                ).encode("utf-8")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        bound = server.server_address[1]
        log(f"Offline reference: http://{HOST}:{bound}/  (this machine only; Ctrl-C stops it)")
        if child is not None:
            log(f"  books: kiwix-serve on http://{HOST}:{kiwix_port}{WIKI}/")
        if server.map_page is not None and map_shelf is not None:
            log(
                f"  map: http://{HOST}:{bound}{MAP}  ({len(map_shelf.regions)} region(s); "
                f"your position from `hammunition maps gps-tether` on port {position_port})"
            )
        if aircraft is not None:
            log(
                f"  aircraft: http://{HOST}:{bound}{aircraft_page.AIRCRAFT}  (tar1090 over "
                f"readsb's JSON in {aircraft.json_dir}; "
                + (
                    "the basemap is your offline map)"
                    if aircraft.basemap
                    else f"{aircraft.reason})"
                )
            )
        if router_child is not None and router is not None:
            log(
                f"  routes: GraphHopper starting on {ROUTER_HOST}:{router.port}, asked through "
                f"this page only; its log is {router.log}"
            )
        elif server.router is not None and server.router.why is not None:
            log(f"  routes are off: {server.router.why}")
        elif routes_note is not None and server.map_page is not None:
            log(f"  {routes_note}")
        while True:
            if child is not None and (code := child.poll()) is not None:
                log(f"kiwix-serve exited ({code}); the page is stopped too.")
                return 1
            if (
                router_child is not None
                and server.router is not None
                and server.router.exited is None
                and (code := router_child.poll()) is not None
            ):
                server.router.exited = code
                log(
                    f"GraphHopper exited ({code}); routes are off and the page keeps serving. "
                    f"Its log: {server.router.log}"
                )
            tick()
    except KeyboardInterrupt:
        log("Stopped.")
        return 0
    finally:
        if thread is not None:
            server.shutdown()
        server.server_close()
        if child is not None:
            _stop(child)
        if router_child is not None:
            _stop(router_child)
