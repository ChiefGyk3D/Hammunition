# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""ETag and size-only downloads try the Bunker mirror first.  #381, Task 12.

The publisher route's checks are kept exactly: the size, and the S3 ETag for
``fetch_etag``; the size and a TIFF's first bytes for ``fetch_sized``. The
mirror is never trusted more than the publisher: its bytes pass the same
checks, a bad copy falls through to the publisher online and is a hard failure
offline, and no ``*.part.*`` file survives any path.
"""

from __future__ import annotations

import hashlib
import http.server
import threading
import urllib.request
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from typing import IO

import pytest

from hammunition.backends.base import BackendError
from hammunition.fetch import Fetcher, FetchResult, MirrorPath, UrllibTransport, mirror_url
from test_fetch_mirror import Routes

BODY = b"II*\x00example TIFF"
ETAG = hashlib.md5(BODY, usedforsecurity=False).hexdigest()
PUBLISHER = "https://example.invalid/Test.tif"
BUNKER = "http://bunker.invalid"
PATH = MirrorPath("usgs-ustopo", "DE/Test_20260101")
AT_MIRROR = mirror_url(BUNKER, PATH)
MIB = 1024 * 1024

Fetch = Callable[[Fetcher, bytes], FetchResult]


def _etag(fetcher: Fetcher, body: bytes = BODY) -> FetchResult:
    return fetcher.fetch_etag(PUBLISHER, ETAG, expected_size=len(body), mirror=PATH)


def _sized(fetcher: Fetcher, body: bytes = BODY) -> FetchResult:
    return fetcher.fetch_sized(PUBLISHER, expected_size=len(body), mirror=PATH)


KINDS = pytest.mark.parametrize("fetch", [_etag, _sized], ids=["etag", "sized"])


def _fetcher(tmp_path: Path, routes: Routes, *, offline: bool = False) -> Fetcher:
    return Fetcher(
        tmp_path / "cache",
        transport=routes,
        mirror=BUNKER,
        mirror_transport=routes,
        offline=offline,
    )


def _parts(tmp_path: Path) -> list[Path]:
    return list((tmp_path / "cache").glob("*.part.*"))


@KINDS
def test_mirror_good_and_corrupt_offline(tmp_path: Path, fetch: Fetch) -> None:
    routes = Routes({AT_MIRROR: BODY})
    fetcher = _fetcher(tmp_path, routes, offline=True)
    result = fetch(fetcher, BODY)
    assert result.path.read_bytes() == BODY and result.source == "mirror"
    assert result.url == AT_MIRROR and not result.from_cache
    result.path.unlink()
    routes.routes[AT_MIRROR] = b"x" * len(BODY)
    with pytest.raises(BackendError):
        fetch(fetcher, BODY)
    assert PUBLISHER not in routes.requested
    assert not _parts(tmp_path)


@KINDS
def test_offline_without_a_bunker_route_refuses_and_never_asks_the_publisher(
    tmp_path: Path, fetch: Fetch
) -> None:
    routes = Routes({PUBLISHER: BODY})
    fetcher = Fetcher(tmp_path / "cache", transport=routes, offline=True)
    with pytest.raises(BackendError, match="Bunker route"):
        fetch(fetcher, BODY)
    assert routes.requested == [] and not _parts(tmp_path)


@KINDS
def test_online_good_mirror_is_used_and_the_publisher_never_asked(
    tmp_path: Path, fetch: Fetch
) -> None:
    routes = Routes({AT_MIRROR: BODY, PUBLISHER: b"other"})
    result = fetch(_fetcher(tmp_path, routes), BODY)
    assert result.source == "mirror" and routes.requested == [AT_MIRROR]


@KINDS
def test_online_bad_mirror_falls_back_to_the_publisher(tmp_path: Path, fetch: Fetch) -> None:
    routes = Routes({AT_MIRROR: b"x" * len(BODY), PUBLISHER: BODY})
    result = fetch(_fetcher(tmp_path, routes), BODY)
    assert result.path.read_bytes() == BODY
    assert result.source == "publisher" and result.url == PUBLISHER
    assert result.mirror_failure is not None and AT_MIRROR in result.mirror_failure
    assert routes.requested == [AT_MIRROR, PUBLISHER]
    assert not _parts(tmp_path)


@KINDS
def test_a_missing_mirror_file_falls_back_and_says_why(tmp_path: Path, fetch: Fetch) -> None:
    routes = Routes({PUBLISHER: BODY})
    result = fetch(_fetcher(tmp_path, routes), BODY)
    assert result.source == "publisher" and "404" in (result.mirror_failure or "")


@KINDS
def test_when_both_fail_the_error_names_both_reasons(tmp_path: Path, fetch: Fetch) -> None:
    routes = Routes({AT_MIRROR: b"m" * len(BODY), PUBLISHER: b"p" * len(BODY)})
    with pytest.raises(BackendError) as err:
        fetch(_fetcher(tmp_path, routes), BODY)
    text = str(err.value)
    assert PUBLISHER in text
    assert "LAN mirror was tried first and passed over" in text and AT_MIRROR in text
    assert not _parts(tmp_path)


# -- the checks the publisher route already has, kept -------------------------------


@KINDS
def test_wrong_size_is_refused_on_either_route(tmp_path: Path, fetch: Fetch) -> None:
    short = BODY[:-1]
    routes = Routes({AT_MIRROR: short, PUBLISHER: short})
    with pytest.raises(BackendError, match="size"):
        fetch(_fetcher(tmp_path, routes), BODY)
    assert routes.requested == [AT_MIRROR, PUBLISHER] and not _parts(tmp_path)
    assert not list((tmp_path / "cache").glob("*Test.tif"))


def test_sized_without_tiff_magic_is_refused_though_the_size_matches(tmp_path: Path) -> None:
    page = b"<html>not a map</html>"
    routes = Routes({AT_MIRROR: page, PUBLISHER: page})
    with pytest.raises(BackendError, match="not a TIFF"):
        _sized(_fetcher(tmp_path, routes), page)
    assert routes.requested == [AT_MIRROR, PUBLISHER] and not _parts(tmp_path)


def test_etag_mismatch_with_the_right_size_is_refused(tmp_path: Path) -> None:
    other = b"x" * len(BODY)
    routes = Routes({AT_MIRROR: other, PUBLISHER: other})
    with pytest.raises(BackendError, match="ETag"):
        _etag(_fetcher(tmp_path, routes), BODY)
    assert not _parts(tmp_path)


def test_a_multipart_etag_is_reproduced_from_the_mirror(tmp_path: Path) -> None:
    body = b"II*\x00" + bytes(range(256)) * (6 * MIB // 256)
    first, second = body[: 5 * MIB], body[5 * MIB :]
    inner = hashlib.md5(usedforsecurity=False)
    for part in (first, second):
        inner.update(hashlib.md5(part, usedforsecurity=False).digest())
    etag = f"{inner.hexdigest()}-2"
    routes = Routes({AT_MIRROR: body})
    result = _fetcher(tmp_path, routes).fetch_etag(
        PUBLISHER, etag, expected_size=len(body), mirror=PATH
    )
    assert result.source == "mirror" and result.size == len(body)
    routes.routes[AT_MIRROR] = body[:-1] + b"?"
    result.path.unlink()
    routes.routes[PUBLISHER] = b"nope"
    with pytest.raises(BackendError, match="ETag"):
        _fetcher(tmp_path, routes).fetch_etag(
            PUBLISHER, etag, expected_size=len(body), mirror=PATH
        )
    assert not _parts(tmp_path)


def test_a_verified_cached_etag_copy_is_reverified_and_asks_nobody(tmp_path: Path) -> None:
    routes = Routes({AT_MIRROR: BODY})
    fetcher = _fetcher(tmp_path, routes)
    first = _etag(fetcher)
    assert first.source == "mirror"
    routes.requested.clear()
    again = _etag(fetcher)
    assert again.source == "cache" and again.from_cache and again.url is None
    assert routes.requested == []
    # A damaged cached copy of the right size is not trusted: it is fetched again.
    again.path.write_bytes(b"y" * len(BODY))
    healed = _etag(fetcher)
    assert healed.source == "mirror" and healed.path.read_bytes() == BODY


def test_a_size_only_cached_copy_is_never_reused(tmp_path: Path) -> None:
    routes = Routes({AT_MIRROR: BODY})
    fetcher = _fetcher(tmp_path, routes)
    first = _sized(fetcher)
    routes.requested.clear()
    second = _sized(fetcher)
    assert routes.requested == [AT_MIRROR]
    assert not second.from_cache and second.source == "mirror" and first.path == second.path


# -- the cap, mid-stream -------------------------------------------------------------


class _Endless:
    """Streams more than the cap allows, noting whether a temporary existed
    while it was being read (so the cap is hit mid-stream, not up front)."""

    def __init__(self, cache: Path, body: bytes) -> None:
        self.cache = cache
        self.body = body
        self.requested: list[str] = []
        self.part_seen_mid_stream = False

    @contextmanager
    def open(self, url: str) -> Iterator[IO[bytes]]:
        self.requested.append(url)
        outer = self

        class Stream(BytesIO):
            def read(self, size: int | None = -1) -> bytes:
                if self.tell() > 0 and list(outer.cache.glob("*.part.*")):
                    outer.part_seen_mid_stream = True
                return super().read(size)

        yield Stream(self.body)


@KINDS
def test_the_cap_hit_mid_stream_leaves_no_part_file(tmp_path: Path, fetch: Fetch) -> None:
    flood = BODY + b"z" * (2 * MIB)
    transport = _Endless(tmp_path / "cache", flood)
    fetcher = Fetcher(
        tmp_path / "cache", transport=transport, mirror=BUNKER, mirror_transport=transport
    )
    with pytest.raises(BackendError, match="byte limit"):
        fetch(fetcher, BODY)
    assert transport.requested == [AT_MIRROR, PUBLISHER]
    assert transport.part_seen_mid_stream
    assert not _parts(tmp_path)


@KINDS
def test_the_cap_hit_by_the_mirror_offline_is_a_hard_failure(tmp_path: Path, fetch: Fetch) -> None:
    transport = _Endless(tmp_path / "cache", BODY + b"z" * (2 * MIB))
    fetcher = Fetcher(
        tmp_path / "cache",
        transport=transport,
        mirror=BUNKER,
        mirror_transport=transport,
        offline=True,
    )
    with pytest.raises(BackendError, match="offline Bunker download failed"):
        fetch(fetcher, BODY)
    assert transport.requested == [AT_MIRROR] and transport.part_seen_mid_stream
    assert not _parts(tmp_path)


# -- size-only publisher requests keep the strict, no-redirect transport -------------

SHEET = "/geodata/Test.tif"
MOVED = "/elsewhere/Test.tif"
ON_MIRROR = "/usgs-ustopo/DE/Test_20260101"


@contextmanager
def _server(
    files: dict[str, bytes], redirects: dict[str, str]
) -> Iterator[tuple[str, list[str]]]:
    seen: list[str] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            seen.append(self.path)
            if self.path in redirects:
                self.send_response(302)
                self.send_header("Location", redirects[self.path])
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            body = files.get(self.path)
            if body is None:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: object) -> None:
            """Quiet."""

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}", seen
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def _follows_redirects(transport: object) -> bool:
    handlers = vars(vars(transport)["_opener"])["handlers"]
    return any(isinstance(h, urllib.request.HTTPRedirectHandler) for h in handlers)


def test_strict_transport_is_the_real_one_that_follows_no_redirect(tmp_path: Path) -> None:
    fetcher = Fetcher(tmp_path / "cache")
    assert isinstance(fetcher.strict_transport, UrllibTransport)
    assert fetcher.strict_transport is not fetcher.transport
    assert not _follows_redirects(fetcher.strict_transport)
    assert _follows_redirects(fetcher.transport)


def test_a_publisher_redirect_on_a_size_only_sheet_is_refused_not_followed(
    tmp_path: Path,
) -> None:
    with _server({MOVED: BODY}, {SHEET: MOVED}) as (base, seen):
        fetcher = Fetcher(
            tmp_path / "cache", mirror=base, mirror_transport=UrllibTransport(timeout=5.0)
        )
        with pytest.raises(BackendError, match="302") as err:
            fetcher.fetch_sized(f"{base}{SHEET}", expected_size=len(BODY), mirror=PATH)
    # The mirror missed (404), the publisher answered a redirect, nothing followed it.
    assert seen == [ON_MIRROR, SHEET] and MOVED not in seen
    assert "LAN mirror was tried first" in str(err.value)
    assert not _parts(tmp_path)
    assert not list((tmp_path / "cache").glob("sized-*"))


def test_the_same_redirect_is_followed_by_the_etag_route_as_before(tmp_path: Path) -> None:
    """The ETag route never had the strict transport; this pins that it still has
    the ordinary one, so the size-only test above is about the size-only route."""
    with _server({MOVED: BODY}, {SHEET: MOVED}) as (base, seen):
        fetcher = Fetcher(
            tmp_path / "cache", mirror=base, mirror_transport=UrllibTransport(timeout=5.0)
        )
        result = fetcher.fetch_etag(f"{base}{SHEET}", ETAG, expected_size=len(BODY), mirror=PATH)
    assert result.source == "publisher" and MOVED in seen


def test_a_size_only_mirror_hit_over_real_http_is_checked_like_the_publisher(
    tmp_path: Path,
) -> None:
    with _server({ON_MIRROR: BODY}, {}) as (base, seen):
        fetcher = Fetcher(
            tmp_path / "cache", mirror=base, mirror_transport=UrllibTransport(timeout=5.0)
        )
        result = fetcher.fetch_sized(f"{base}{SHEET}", expected_size=len(BODY), mirror=PATH)
    assert result.source == "mirror" and seen == [ON_MIRROR]
