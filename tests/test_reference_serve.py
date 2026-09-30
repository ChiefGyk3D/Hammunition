# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""`hammunition reference serve` and `reference books`.  D-065.

The property that matters most is the one a person would never see:
kiwix-serve listens on every address unless it is told otherwise (measured
2026-09-29, ``*:port``), so its argv must always carry ``-i 127.0.0.1``. The
landing server is exercised for real on loopback; kiwix-serve is a fake
child, since the suite runs nothing from the machine.
"""

from __future__ import annotations

import importlib
import urllib.error
import urllib.request
from collections.abc import Iterator, Sequence
from pathlib import Path
from threading import Thread

import pytest

from hammunition.kiwix import Book
from hammunition.reference import (
    HOST,
    PORT,
    Shelf,
    find_shelf,
    kiwix_serve_argv,
    landing_page,
    make_server,
    run,
    serve_port,
)
from json_support import parse_one, validate

cli = importlib.import_module("hammunition.cli.main")

HAM = Book(
    id="ham.stackexchange.com_en_all",
    name="ham.stackexchange.com_en_all",
    flavour=None,
    category="stack_exchange",
    title="Amateur Radio Stack Exchange",
    licence="CC BY-SA",
    licence_url="https://stackoverflow.com/help/licensing",
)
ZIM = "ham.stackexchange.com_en_all_2026-08.zim"
FORM = "ics-205-incident-radio-communications-plan-v3.1.pdf"


def _data(tmp_path: Path, *, books: bool = True) -> Path:
    root = tmp_path / "data"
    (root / "kiwix-library").mkdir(parents=True)
    (root / "ics-forms").mkdir()
    if books:
        (root / "kiwix-library" / ZIM).write_bytes(b"ZIM")
    (root / "ics-forms" / FORM).write_bytes(b"%PDF-1.7 form")
    return root


def _shelf(tmp_path: Path, *, books: bool = True) -> Shelf:
    return find_shelf(
        _data(tmp_path, books=books), {HAM.id: HAM}, which=lambda name: f"/usr/bin/{name}"
    )


# -- the argv -------------------------------------------------------------------


@pytest.mark.parametrize("port", [1025, 8481, 65535])
def test_kiwix_serve_is_always_told_to_listen_on_loopback_only(port: int) -> None:
    argv = kiwix_serve_argv(port, Path("/c/library.xml"), pid=4242)
    assert argv[0] == "kiwix-serve"
    index = argv.index("-i")
    assert argv[index + 1] == "127.0.0.1"
    assert argv.count("-i") == 1 and "--address" not in argv
    assert argv[argv.index("-p") + 1] == str(port)
    assert argv[argv.index("-r") + 1] == "/wiki"
    assert argv[argv.index("-a") + 1] == "4242"
    assert "-b" in argv and "-M" in argv and "--library" in argv
    assert argv[-1] == "/c/library.xml"


@pytest.mark.parametrize("text", ["1024", "8480", "65534"])
def test_a_port_from_1024_to_65534_is_taken(text: str) -> None:
    assert serve_port(text) == int(text)


@pytest.mark.parametrize("text", ["1023", "80", "65535", "70000", "-1", "http"])
def test_a_port_outside_the_range_is_refused_by_name(text: str) -> None:
    with pytest.raises(ValueError, match="1024 to 65534"):
        serve_port(text)


# -- the page -------------------------------------------------------------------


def test_the_shelf_names_books_forms_and_dictionaries(tmp_path: Path) -> None:
    shelf = _shelf(tmp_path)
    [book] = shelf.books
    assert (book.title, book.licence, book.stem) == (
        HAM.title,
        "CC BY-SA",
        "ham.stackexchange.com_en_all_2026-08",
    )
    assert [f.name for f in shelf.forms] == [FORM]
    assert shelf.dict_client and shelf.goldendict


def test_a_zim_the_book_list_does_not_name_is_served_under_its_file_name(tmp_path: Path) -> None:
    root = _data(tmp_path)
    (root / "kiwix-library" / "own-book.zim").write_bytes(b"ZIM")
    shelf = find_shelf(root, {HAM.id: HAM}, which=lambda _n: None)
    titles = {b.title for b in shelf.books}
    assert "own-book" in titles
    assert not shelf.dict_client and not shelf.goldendict


def test_the_page_lists_every_book_form_and_dictionary(tmp_path: Path) -> None:
    page = landing_page(_shelf(tmp_path), kiwix_port=8481)
    assert "Amateur Radio Stack Exchange" in page and "CC BY-SA" in page
    assert "http://127.0.0.1:8481/wiki/content/ham.stackexchange.com_en_all_2026-08" in page
    assert f"/forms/{FORM}" in page
    assert "dict " in page and "goldendict" in page


def test_the_page_escapes_what_it_did_not_write(tmp_path: Path) -> None:
    root = _data(tmp_path, books=False)
    (root / "kiwix-library" / "<script>x.zim").write_bytes(b"ZIM")
    page = landing_page(find_shelf(root, {}, which=lambda _n: None), kiwix_port=8481)
    assert "<script>x" not in page and "&lt;script&gt;x" in page


def test_with_no_books_the_page_says_how_to_choose_some(tmp_path: Path) -> None:
    page = landing_page(_shelf(tmp_path, books=False), kiwix_port=8481)
    assert "hammunition station set --reference-books" in page


# -- the landing server, on loopback ---------------------------------------------


@pytest.fixture
def served(tmp_path: Path) -> Iterator[str]:
    shelf = _shelf(tmp_path)
    server = make_server(0, landing_page(shelf, kiwix_port=8481), shelf.forms)
    assert server.server_address[0] == HOST
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://{HOST}:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _get(url: str) -> tuple[int, bytes, str]:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return response.status, response.read(), response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        return exc.code, b"", ""


def test_the_landing_page_is_served(served: str) -> None:
    status, body, kind = _get(f"{served}/")
    assert status == 200 and b"Amateur Radio Stack Exchange" in body
    assert kind.startswith("text/html")


def test_a_form_is_served_as_a_pdf(served: str) -> None:
    status, body, kind = _get(f"{served}/forms/{FORM}")
    assert status == 200 and body == b"%PDF-1.7 form" and kind == "application/pdf"


@pytest.mark.parametrize(
    "path",
    ["/forms/../kiwix-library/x.zim", "/forms/%2e%2e/secret", "/forms/nope.pdf", "/etc/passwd"],
)
def test_nothing_but_the_page_and_the_forms_is_served(served: str, path: str) -> None:
    status, _body, _kind = _get(f"{served}{path}")
    assert status == 404


# -- run: the child, Ctrl-C, and a child that dies ----------------------------------


class FakeChild:
    def __init__(self, exits_after: int | None = None) -> None:
        self.polls = 0
        self.exits_after = exits_after
        self.terminated = False

    def poll(self) -> int | None:
        self.polls += 1
        if self.terminated:
            return -15
        if self.exits_after is not None and self.polls > self.exits_after:
            return 1
        return None

    def terminate(self) -> None:
        self.terminated = True

    def wait(self, timeout: float | None = None) -> int:
        return -15

    def kill(self) -> None:  # pragma: no cover - terminate always works here
        self.terminated = True


def _run(
    tmp_path: Path,
    child: FakeChild | None,
    *,
    books: bool = True,
    interrupt_after: int | None = None,
) -> tuple[int, list[Sequence[str]], list[str]]:
    spawned: list[Sequence[str]] = []
    managed: list[str] = []
    ticks = {"n": 0}

    def spawn(argv: Sequence[str]) -> FakeChild:
        spawned.append(argv)
        assert child is not None
        return child

    def manage(library: Path, zims: Sequence[Path]) -> None:
        managed.extend(str(z) for z in zims)
        library.write_text("<library/>")

    def tick() -> None:
        ticks["n"] += 1
        if interrupt_after is not None and ticks["n"] >= interrupt_after:
            raise KeyboardInterrupt

    rc = run(
        0,
        shelf=_shelf(tmp_path, books=books),
        library=tmp_path / "cache" / "library.xml",
        spawn=spawn,
        manage=manage,
        tick=tick,
        log=lambda _line: None,
    )
    return rc, spawned, managed


def test_ctrl_c_stops_the_child_and_returns_zero(tmp_path: Path) -> None:
    child = FakeChild()
    rc, spawned, managed = _run(tmp_path, child, interrupt_after=3)
    assert rc == 0 and child.terminated
    [argv] = spawned
    assert argv[argv.index("-i") + 1] == "127.0.0.1"
    assert managed == [str(tmp_path / "data" / "kiwix-library" / ZIM)]


def test_a_child_that_dies_stops_the_page_and_fails(tmp_path: Path) -> None:
    rc, _spawned, _managed = _run(tmp_path, FakeChild(exits_after=2))
    assert rc == 1


def test_with_no_books_no_child_is_started(tmp_path: Path) -> None:
    rc, spawned, managed = _run(tmp_path, None, books=False, interrupt_after=2)
    assert rc == 0 and spawned == [] and managed == []


# -- the CLI ------------------------------------------------------------------------


def test_serve_refuses_root(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli.os, "geteuid", lambda: 0)
    assert cli.main(["reference", "serve"]) != 0
    assert "not as root" in capsys.readouterr().err


def test_serve_refuses_a_bad_port(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["reference", "serve", "--port", "80"]) != 0
    assert "1024 to 65534" in capsys.readouterr().err


def test_serve_has_no_json_form(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["--json", "reference", "serve"])
    doc = parse_one(capsys.readouterr().out)
    assert rc == 2 and doc["kind"] == "error"


def test_the_default_port_is_8480() -> None:
    assert PORT == 8480


def test_reference_books_lists_every_book_with_its_licence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("hammunition.station.config_path", lambda owner=None: tmp_path / "s.yml")
    assert cli.main(["reference", "books"]) == 0
    out = capsys.readouterr().out
    assert "ham.stackexchange.com_en_all" in out and "CC BY-NC-SA 3.0 — non-commercial" in out
    assert "75.9 MB" in out


def test_reference_books_json_validates_and_marks_the_chosen(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from hammunition.station import Station, save_station

    target = tmp_path / "s.yml"
    save_station(Station(reference_books=("ham.stackexchange.com_en_all",)), path=target)
    monkeypatch.setattr("hammunition.station.config_path", lambda owner=None: target)
    assert cli.main(["reference", "books", "--json"]) == 0
    doc = parse_one(capsys.readouterr().out)
    validate(doc)
    assert doc["kind"] == "books"
    rows = {b["id"]: b for b in doc["books"]}
    assert rows["ham.stackexchange.com_en_all"]["chosen"] is True
    assert rows["wikipedia_en_all_maxi"]["chosen"] is False
    assert rows["ifixit_en_all"]["licence"] == "CC BY-NC-SA 3.0 — non-commercial"
    assert rows["ham.stackexchange.com_en_all"]["size"] == 75931239
