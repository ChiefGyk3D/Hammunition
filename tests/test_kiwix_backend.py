# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Kiwix books backend: fetch, verify, install, remove.  D-065.

A small fake ZIM is served from loopback, so the real fetcher, the real
sha256 check and the real verified copy into the prefix all run; only the
bytes are fake. The pins are built directly -- the loader would refuse a
loopback URL, which is its job.
"""

from __future__ import annotations

import hashlib
import http.server
import socketserver
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from hammunition.backends.apt import AptBackend
from hammunition.backends.base import Action, BackendError, RecordingRunner
from hammunition.backends.kiwix import KiwixBooksBackend, books_disk_needs
from hammunition.fetch import Fetcher
from hammunition.kiwix import Book, BookFile, BookPin
from hammunition.manifest.schema import PackageManifest

BODY = b"ZIM\x04" + b"offline reference " * 200
FILE = "ham.stackexchange.com_en_all_2026-08.zim"

BOOK = Book(
    id="ham.stackexchange.com_en_all",
    name="ham.stackexchange.com_en_all",
    flavour=None,
    category="stack_exchange",
    title="Amateur Radio Stack Exchange",
    licence="CC BY-SA",
    licence_url="https://stackoverflow.com/help/licensing",
)


def _manifest() -> PackageManifest:
    return PackageManifest.model_validate(
        {
            "name": "kiwix-library",
            "version": "station",
            "summary": "books",
            "categories": ["references"],
            "install": [{"install": {"method": "kiwix-books", "provider": "kiwix"}}],
            "update": {"probe": {"method": "kiwix"}},
            "documentation": {
                "what_it_does": "Keeps the chosen books on the machine.",
                "why_you_want_it": "Offline reading when the network is down.",
                "upstream_url": "https://kiwix.org/",
            },
        }
    )


@pytest.fixture
def base(tmp_path: Path) -> Iterator[str]:
    root = tmp_path / "www"
    root.mkdir()
    (root / FILE).write_bytes(BODY)

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, directory=str(root), **kwargs)  # type: ignore[arg-type]

        def log_message(self, *args: object) -> None:
            """Quiet."""

    with socketserver.TCPServer(("127.0.0.1", 0), Handler) as httpd:
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{httpd.server_address[1]}"
        finally:
            httpd.shutdown()
            thread.join(timeout=5)


def _book(base: str, *, size: int = len(BODY), sha: str | None = None) -> BookFile:
    return BookFile(
        BOOK,
        BookPin(
            id=BOOK.id,
            file=FILE,
            url=f"{base}/{FILE}",
            size=size,
            sha256=sha or hashlib.sha256(BODY).hexdigest(),
            published="2026-08",
            measured="2026-09-29",
        ),
    )


def _backend(tmp_path: Path, *files: BookFile) -> KiwixBooksBackend:
    return KiwixBooksBackend(
        fetcher=Fetcher(tmp_path / "cache"), prefix=tmp_path / "prefix", files=files
    )


def _steps(backend: KiwixBooksBackend) -> list[Action]:
    manifest = _manifest()
    steps: list[Any] = backend.steps(manifest, manifest.install[0].install)  # type: ignore[arg-type]
    assert all(isinstance(s, Action) for s in steps)
    return steps


def _dir(tmp_path: Path) -> Path:
    return tmp_path / "prefix" / "share" / "hammunition" / "data" / "kiwix-library"


def test_a_chosen_book_is_disclosed_fetched_verified_and_installed(
    base: str, tmp_path: Path
) -> None:
    backend = _backend(tmp_path, _book(base))
    steps = _steps(backend)
    assert [s.kind for s in steps] == ["fetch", "install-data", "prune-cache"]
    fetch = steps[0].description
    assert BOOK.id in fetch and "2026-08" in fetch and "CC BY-SA" in fetch
    assert "KB" in fetch  # the size, as a publisher quotes it
    dest = _dir(tmp_path) / FILE
    assert steps[1].detail == str(dest)
    outcomes = [s.perform() for s in steps]
    assert "verified" in outcomes[0]
    assert dest.read_bytes() == BODY
    assert oct(dest.stat().st_mode & 0o777) == "0o644"
    # The cached copy is not kept beside the installed one: a book can be 50 GB.
    assert not any((tmp_path / "cache").rglob(f"*{FILE}"))


def test_a_book_already_installed_at_its_pinned_size_is_not_fetched(
    base: str, tmp_path: Path
) -> None:
    _dir(tmp_path).mkdir(parents=True)
    (_dir(tmp_path) / FILE).write_bytes(BODY)
    backend = _backend(tmp_path, _book(base))
    assert _steps(backend) == []
    assert backend.pending(_manifest()) == []


def test_a_book_on_disk_at_the_wrong_size_is_fetched_again(base: str, tmp_path: Path) -> None:
    _dir(tmp_path).mkdir(parents=True)
    (_dir(tmp_path) / FILE).write_bytes(BODY[:100])
    backend = _backend(tmp_path, _book(base))
    assert [s.kind for s in _steps(backend)] == ["fetch", "install-data", "prune-cache"]


def test_a_book_no_longer_chosen_is_removed_as_its_own_step(tmp_path: Path) -> None:
    _dir(tmp_path).mkdir(parents=True)
    old = _dir(tmp_path) / "wikem_en_all_nopic_2026-07.zim"
    old.write_bytes(b"old")
    (_dir(tmp_path) / "notes.txt").write_text("not a book")
    steps = _steps(_backend(tmp_path))
    assert [(s.kind, s.detail) for s in steps] == [("remove-data", str(old))]
    assert "no longer among your reference books" in steps[0].description
    steps[0].perform()
    assert not old.exists()
    assert (_dir(tmp_path) / "notes.txt").exists()


def test_an_older_date_of_a_chosen_book_is_replaced(base: str, tmp_path: Path) -> None:
    _dir(tmp_path).mkdir(parents=True)
    older = _dir(tmp_path) / "ham.stackexchange.com_en_all_2026-02.zim"
    older.write_bytes(b"older")
    kinds = [(s.kind, s.detail) for s in _steps(_backend(tmp_path, _book(base)))]
    assert ("remove-data", str(older)) in kinds
    assert kinds[0][0] == "fetch"


def test_a_size_the_pin_did_not_promise_refuses(base: str, tmp_path: Path) -> None:
    steps = _steps(_backend(tmp_path, _book(base, size=len(BODY) + 1)))
    with pytest.raises(BackendError):
        steps[0].perform()


def test_a_digest_that_does_not_match_refuses_before_installing(base: str, tmp_path: Path) -> None:
    steps = _steps(_backend(tmp_path, _book(base, sha="0" * 64)))
    with pytest.raises(BackendError):
        steps[0].perform()
    assert not (_dir(tmp_path) / FILE).exists()


def test_disk_needs_count_each_download_in_the_cache_and_the_prefix(tmp_path: Path) -> None:
    book = _book("http://127.0.0.1:1")
    needs = books_disk_needs([book], cache=tmp_path / "cache", prefix=tmp_path / "prefix")
    assert needs == {tmp_path / "cache": len(BODY), tmp_path / "prefix": len(BODY)}


def _planned_books(tmp_path: Path) -> Any:
    from hammunition.station import Station
    from test_plan import _reference, _resolve

    catalog, _ = _reference()
    return _resolve(
        tmp_path,
        ["kiwix-library"],
        catalog=catalog,
        known={},
        station=Station(reference_books=(BOOK.id,)),
    )


def test_the_executor_refuses_books_with_no_books_backend(tmp_path: Path) -> None:
    """A planned book unit with no backend is a refusal, never a run that
    installed nothing and called it a success (D-031)."""
    from hammunition.execute import commands_for

    plan = _planned_books(tmp_path)
    with pytest.raises(BackendError, match="kiwix-library"):
        commands_for(plan, AptBackend(RecordingRunner()))


def test_the_executor_takes_the_books_steps_fetches_first(base: str, tmp_path: Path) -> None:
    from hammunition.execute import commands_for

    plan = _planned_books(tmp_path)
    steps = commands_for(plan, AptBackend(RecordingRunner()), books=_backend(tmp_path, _book(base)))
    kinds = [getattr(s, "kind", None) for s in steps]
    assert kinds.index("fetch") < kinds.index("install-data") < kinds.index("prune-cache")
