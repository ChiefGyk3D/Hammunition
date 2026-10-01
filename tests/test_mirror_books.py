# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Kiwix books through the LAN mirror (D-070, D-066; issue #159).

Books are the largest data the catalog fetches -- English Wikipedia with
pictures is 127 GB -- so they are the mirror's most valuable case. A mirror
and a publisher, both real HTTP servers on 127.0.0.1, through the real
:class:`~hammunition.fetch.UrllibTransport`: the books backend asks
``<mirror>/kiwix-library/<book id>`` first, checks the same pinned sha256
either way, says so in the plan and records where the bytes came from.
Nothing leaves loopback: the suite refuses any socket that does.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from hammunition.backends.base import Action
from hammunition.backends.kiwix import KiwixBooksBackend, book_mirror_path
from hammunition.fetch import Fetcher, MirrorPath, UrllibTransport
from hammunition.kiwix import BookFile, BookPin
from test_kiwix_backend import BODY, BOOK, FILE, _manifest
from test_mirror_loopback import Server

ON_MIRROR = f"/kiwix-library/{BOOK.id}"
ON_PUBLISHER = f"/zim/stack_exchange/{FILE}"


def _book(publisher: Server) -> BookFile:
    return BookFile(
        BOOK,
        BookPin(
            id=BOOK.id,
            file=FILE,
            url=f"{publisher.base}{ON_PUBLISHER}",
            size=len(BODY),
            sha256=hashlib.sha256(BODY).hexdigest(),
            published="2026-08",
            measured="2026-09-29",
        ),
    )


def _steps(tmp_path: Path, publisher: Server, mirror: str | None) -> list[Action]:
    transport = UrllibTransport(timeout=5.0)
    fetcher = Fetcher(
        tmp_path / "cache", transport=transport, mirror=mirror, mirror_transport=transport
    )
    backend = KiwixBooksBackend(
        fetcher=fetcher, prefix=tmp_path / "prefix", files=[_book(publisher)]
    )
    manifest = _manifest()
    steps: list[Any] = backend.steps(manifest, manifest.install[0].install)  # type: ignore[arg-type]
    assert [s.kind for s in steps] == ["fetch", "install-data", "prune-cache"]
    return steps


def _installed(tmp_path: Path) -> Path:
    return tmp_path / "prefix" / "share" / "hammunition" / "data" / "kiwix-library" / FILE


def test_a_book_is_asked_of_the_mirror_by_its_id(tmp_path: Path) -> None:
    """``<unit>/<book id>``, the id as the pin file names it: the name
    ``hammunition artifacts`` lists, so a Bunker keeps one path per book
    across Kiwix's dated republications."""
    with Server({}).running() as publisher:
        book = _book(publisher)
    assert book_mirror_path("kiwix-library", book) == MirrorPath("kiwix-library", BOOK.id)


def test_the_mirror_serves_the_book_and_the_publisher_is_never_asked(tmp_path: Path) -> None:
    with (
        Server({ON_PUBLISHER: BODY}).running() as publisher,
        Server({ON_MIRROR: BODY}).running() as mirror,
    ):
        fetch, install, prune = _steps(tmp_path, publisher, mirror.base + "/")
        assert fetch.sources == (f"{mirror.base}{ON_MIRROR}", f"{publisher.base}{ON_PUBLISHER}")
        assert "LAN mirror first" in fetch.description
        assert "sha256 is checked either way" in fetch.description
        assert fetch.detail.startswith(f"{mirror.base}{ON_MIRROR}, then {publisher.base}")
        outcome = fetch.perform()
        install.perform()
        prune.perform()
    assert "from the LAN mirror" in outcome
    assert fetch.facts == {"source": "mirror", "fetched_from": f"{mirror.base}{ON_MIRROR}"}
    assert mirror.requests == [ON_MIRROR] and publisher.requests == []
    assert _installed(tmp_path).read_bytes() == BODY


def test_a_mirror_serving_the_wrong_bytes_falls_back_to_the_publisher(tmp_path: Path) -> None:
    with (
        Server({ON_PUBLISHER: BODY}).running() as publisher,
        Server({ON_MIRROR: b"ZIM\x04 a stale copy of another date"}).running() as mirror,
    ):
        fetch, install, _ = _steps(tmp_path, publisher, mirror.base)
        outcome = fetch.perform()
        install.perform()
    assert "from the publisher" in outcome and "does not match" in outcome
    assert fetch.facts["source"] == "publisher"
    assert fetch.facts["fetched_from"] == f"{publisher.base}{ON_PUBLISHER}"
    assert "does not match" in fetch.facts["mirror_failure"]
    assert mirror.requests == [ON_MIRROR] and publisher.requests == [ON_PUBLISHER]
    # Nothing the mirror sent survives: only the verified publisher bytes.
    assert _installed(tmp_path).read_bytes() == BODY
    cached = list((tmp_path / "cache").iterdir())
    assert len(cached) == 1 and cached[0].read_bytes() == BODY


def test_without_a_mirror_the_book_step_reads_as_it_did(tmp_path: Path) -> None:
    with Server({ON_PUBLISHER: BODY}).running() as publisher:
        fetch, _, _ = _steps(tmp_path, publisher, None)
        outcome = fetch.perform()
    assert fetch.sources == (f"{publisher.base}{ON_PUBLISHER}",)
    assert "mirror" not in fetch.description
    assert fetch.detail.startswith(f"{publisher.base}{ON_PUBLISHER} (")
    assert "mirror" not in outcome and "publisher" not in outcome
    assert fetch.facts == {"source": "publisher", "fetched_from": f"{publisher.base}{ON_PUBLISHER}"}
