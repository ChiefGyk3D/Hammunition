# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""A LAN mirror and a publisher, both real HTTP servers on 127.0.0.1,
through the real :class:`~hammunition.fetch.UrllibTransport`.  D-070.

The fakes in ``test_fetch_mirror.py`` prove the ordering; this proves it
over sockets, where a stopped mirror is a refused connection and a missing
file is a real 404. Nothing leaves loopback: the suite refuses any socket
that does.
"""

from __future__ import annotations

import hashlib
import http.server
import socket
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from hammunition.fetch import (
    Fetcher,
    MirrorPath,
    UrllibTransport,
    VerificationError,
)
from hammunition.manifest.schema import RemoteArtifact

PAYLOAD = b"vermont, as Geofabrik cut it\n" * 64
DIGEST = hashlib.sha256(PAYLOAD).hexdigest()
PATH = MirrorPath("osm-regions", "north-america/us/vermont")
ON_MIRROR = "/osm-regions/north-america/us/vermont"
ON_PUBLISHER = "/north-america/us/vermont-260101.osm.pbf"


class Server:
    def __init__(self, files: dict[str, bytes]) -> None:
        self.files = files
        self.requests: list[str] = []
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                outer.requests.append(self.path)
                body = outer.files.get(self.path)
                if body is None:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args: object) -> None:
                """Quiet."""

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    @contextmanager
    def running(self) -> Iterator[Server]:
        thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        thread.start()
        try:
            yield self
        finally:
            self.httpd.shutdown()
            self.httpd.server_close()
            thread.join(timeout=5)


def _closed_port() -> int:
    """A loopback port nothing listens on: bound, then released."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
    return port


@pytest.fixture
def publisher() -> Iterator[Server]:
    with Server({ON_PUBLISHER: PAYLOAD}).running() as server:
        yield server


def _fetcher(tmp_path: Path, mirror: str) -> Fetcher:
    transport = UrllibTransport(timeout=5.0)
    return Fetcher(
        tmp_path / "cache", transport=transport, mirror=mirror, mirror_transport=transport
    )


def _artifact(publisher: Server, suffix: str = "") -> RemoteArtifact:
    return RemoteArtifact(url=f"{publisher.base}{ON_PUBLISHER}{suffix}", sha256=DIGEST)


def test_the_mirror_serves_it_and_the_publisher_is_never_asked(
    tmp_path: Path, publisher: Server
) -> None:
    with Server({ON_MIRROR: PAYLOAD}).running() as mirror:
        result = _fetcher(tmp_path, mirror.base + "/").fetch(_artifact(publisher), mirror=PATH)
    assert (result.source, result.path.read_bytes()) == ("mirror", PAYLOAD)
    assert mirror.requests == [ON_MIRROR] and publisher.requests == []


def test_a_mirror_without_the_file_hands_over_to_the_publisher(
    tmp_path: Path, publisher: Server
) -> None:
    with Server({}).running() as mirror:
        result = _fetcher(tmp_path, mirror.base).fetch(_artifact(publisher), mirror=PATH)
    assert result.source == "publisher" and result.path.read_bytes() == PAYLOAD
    assert result.mirror_failure is not None and "404" in result.mirror_failure
    assert publisher.requests == [ON_PUBLISHER]


def test_a_mirror_serving_the_wrong_bytes_is_discarded(tmp_path: Path, publisher: Server) -> None:
    with Server({ON_MIRROR: b"not vermont\n"}).running() as mirror:
        result = _fetcher(tmp_path, mirror.base).fetch(_artifact(publisher), mirror=PATH)
    assert result.source == "publisher" and result.sha256 == DIGEST
    assert result.mirror_failure is not None and "does not match" in result.mirror_failure
    assert sorted(p.name for p in (tmp_path / "cache").iterdir()) == [result.path.name]


def test_a_stopped_mirror_is_asked_once_per_run(tmp_path: Path, publisher: Server) -> None:
    publisher.files[ON_PUBLISHER + ".2"] = PAYLOAD
    fetcher = _fetcher(tmp_path, f"http://127.0.0.1:{_closed_port()}")
    first = fetcher.fetch(_artifact(publisher), mirror=PATH)
    second = fetcher.fetch(
        _artifact(publisher, ".2"), mirror=MirrorPath("osm-regions", "north-america/us/delaware")
    )
    assert first.source == second.source == "publisher"
    assert second.mirror_failure is not None and "did not answer" in second.mirror_failure


def test_when_the_publisher_fails_too_the_refusal_names_both(
    tmp_path: Path, publisher: Server
) -> None:
    publisher.files[ON_PUBLISHER] = b"re-cut upstream\n"
    with (
        Server({ON_MIRROR: b"stale copy\n"}).running() as mirror,
        pytest.raises(VerificationError) as exc,
    ):
        _fetcher(tmp_path, mirror.base).fetch(_artifact(publisher), mirror=PATH)
    assert ON_MIRROR in str(exc.value) and ON_PUBLISHER in str(exc.value)
    assert list((tmp_path / "cache").iterdir()) == []
