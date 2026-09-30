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
"""

from __future__ import annotations

import html
import http.server
import shutil
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .kiwix import Book

HOST = "127.0.0.1"
PORT = 8480
WIKI = "/wiki"
FORMS = "/forms/"
LIBRARY_UNIT = "kiwix-library"
FORMS_UNIT = "ics-forms"
STOP_WAIT = 5.0


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


def landing_page(shelf: Shelf, *, kiwix_port: int) -> str:
    """The page. Every name that came from the disk is escaped."""
    e = html.escape
    wiki = f"http://{HOST}:{kiwix_port}{WIKI}"
    parts = [
        "<!doctype html>",
        '<html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>Offline reference</title>",
        "<style>body{font:16px/1.5 system-ui,sans-serif;max-width:48rem;margin:1rem auto;"
        "padding:0 1rem}li{margin:.3rem 0}small{color:#555}code{background:#eee;padding:0 .2rem}"
        "</style></head><body>",
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
    parts.append("</body></html>")
    return "\n".join(parts) + "\n"


class _Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    page: bytes
    forms: dict[str, Path]


class _Handler(http.server.BaseHTTPRequestHandler):
    server: _Server

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

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/":
            self._send(200, self.server.page, "text/html; charset=utf-8")
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


def make_server(port: int, page: str, forms: Sequence[Path]) -> _Server:
    """The landing server, bound to 127.0.0.1 and nothing else."""
    from urllib.parse import quote

    server = _Server((HOST, port), _Handler)
    server.page = page.encode("utf-8")
    server.forms = {f"{FORMS}{quote(p.name)}": p for p in forms}
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
) -> int:
    """Serve until Ctrl-C (exit 0) or until kiwix-serve exits (exit 1)."""
    import os

    child: Child | None = None
    thread: threading.Thread | None = None
    kiwix_port = port + 1
    server = make_server(port, landing_page(shelf, kiwix_port=kiwix_port), shelf.forms)
    try:
        if shelf.books:
            library.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            library.unlink(missing_ok=True)
            manage(library, [b.path for b in shelf.books])
            child = spawn(
                kiwix_serve_argv(kiwix_port, library, pid=pid if pid is not None else os.getpid())
            )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        bound = server.server_address[1]
        log(f"Offline reference: http://{HOST}:{bound}/  (this machine only; Ctrl-C stops it)")
        if child is not None:
            log(f"  books: kiwix-serve on http://{HOST}:{kiwix_port}{WIKI}/")
        while True:
            if child is not None and (code := child.poll()) is not None:
                log(f"kiwix-serve exited ({code}); the page is stopped too.")
                return 1
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
