# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The browser map's position: ``GET /position`` on the tether.  D-071.

A browser cannot open the NMEA socket, so the tether gains a second loopback
listener that answers ``GET /position`` as Server-Sent Events. **SSE, not a
JSON poll**: the tether watches gpsd only while a client is connected, and an
event stream is a connected client, so it rides the existing fan-out; a poll
would need a gpsd connection per request, or a watch left open on a timer.

The position is where the operator is. A request that does not name
127.0.0.1 or localhost on this port (DNS rebinding) is refused, and so is
one from a page on another origin; ``Access-Control-Allow-Origin`` is sent to
a loopback page only. The fake gpsd is the tether tests' own.
"""

from __future__ import annotations

import json
import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from hammunition.gps_tether import (
    POSITION_PATH,
    POSITION_PORT,
    Feed,
    listen,
    position_event,
    position_response,
    serve,
)
from test_gps_tether import FIX_3D, FakeGpsd, _json, _lines

PORT = 10111


def _head(*lines: str) -> bytes:
    return "\r\n".join(lines).encode("latin-1")


def test_the_defaults_are_10111_and_slash_position() -> None:
    assert (POSITION_PORT, POSITION_PATH) == (10111, "/position")


def test_a_loopback_request_opens_an_event_stream() -> None:
    answer, stream = position_response(
        _head("GET /position HTTP/1.1", f"Host: 127.0.0.1:{PORT}", "Accept: text/event-stream"),
        PORT,
    )
    assert stream
    assert answer.startswith(b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n")
    assert b"Access-Control-Allow-Origin" not in answer


def test_a_loopback_page_is_allowed_by_its_exact_origin() -> None:
    answer, stream = position_response(
        _head(
            "GET /position HTTP/1.1",
            f"Host: localhost:{PORT}",
            "Origin: http://127.0.0.1:8480",
        ),
        PORT,
    )
    assert stream and b"Access-Control-Allow-Origin: http://127.0.0.1:8480\r\n" in answer


@pytest.mark.parametrize(
    ("lines", "status"),
    [
        (["GET /position HTTP/1.1", "Host: evil.example:10111"], b"403"),
        (["GET /position HTTP/1.1"], b"403"),
        (
            ["GET /position HTTP/1.1", "Host: 127.0.0.1:10111", "Origin: https://evil.example"],
            b"403",
        ),
        (
            ["GET /position HTTP/1.1", "Host: 127.0.0.1:10111", "Origin: http://127.0.0.1.evil"],
            b"403",
        ),
        (
            ["POST /position HTTP/1.1", "Host: 127.0.0.1:10111", "Accept: text/event-stream"],
            b"405",
        ),
        (["GET /other HTTP/1.1", "Host: 127.0.0.1:10111", "Accept: text/event-stream"], b"404"),
        # An <img> on any web page: no Origin, an image Accept. It could not
        # read the stream, and it may not hold gpsd watched either.
        (["GET /position HTTP/1.1", "Host: 127.0.0.1:10111", "Accept: image/*"], b"403"),
        (["garbage"], b"400"),
    ],
)
def test_anything_else_is_refused_and_no_stream_starts(lines: list[str], status: bytes) -> None:
    answer, stream = position_response(_head(*lines), PORT)
    assert not stream and answer.startswith(b"HTTP/1.1 " + status)
    assert b"Access-Control-Allow-Origin" not in answer


def test_the_feed_keeps_the_latest_fix_as_the_event_carries_it() -> None:
    feed = Feed()
    feed.push(_json(FIX_3D))
    assert feed.position == {"lat": 12.5, "lon": 34.75, "mode": 3, "time": FIX_3D["time"]}
    event = position_event(feed.position)
    assert event.startswith(b"data: ") and event.endswith(b"\n\n")
    assert json.loads(event[6:]) == feed.position


def test_no_fix_leaves_no_position() -> None:
    feed = Feed()
    feed.push(_json({"class": "TPV", "mode": 1}))
    assert feed.position is None


# -- end to end, against the fake gpsd --------------------------------------------------


@contextmanager
def _tether(gpsd: FakeGpsd) -> Iterator[tuple[int, int, list[str]]]:
    logged: list[str] = []
    stop = threading.Event()
    nmea, http = listen(port=0), listen(port=0)
    thread = threading.Thread(
        target=serve,
        args=(nmea,),
        kwargs={
            "http": http,
            "gpsd": gpsd.address,
            "stop": stop,
            "log": logged.append,
            "poll": 0.02,
            "quiet_after": 5.0,
        },
        daemon=True,
    )
    thread.start()
    try:
        yield nmea.getsockname()[1], http.getsockname()[1], logged
    finally:
        stop.set()
        thread.join(timeout=5)
        assert not thread.is_alive()
        nmea.close()
        http.close()
        gpsd.close()


def _read_until(sock: socket.socket, marker: bytes, within: float = 3.0) -> bytes:
    buffer = b""
    deadline = time.monotonic() + within
    sock.settimeout(0.1)
    while marker not in buffer and time.monotonic() < deadline:
        try:
            data = sock.recv(4096)
        except TimeoutError:
            continue
        if not data:
            break
        buffer += data
    return buffer


def test_a_map_page_receives_the_position_as_an_event() -> None:
    gpsd = FakeGpsd(_json({"class": "VERSION"}, FIX_3D), repeat=True, every=0.05)
    with _tether(gpsd) as (_, http, logged):
        with socket.create_connection(("127.0.0.1", http), timeout=5) as page:
            page.sendall(
                f"GET /position HTTP/1.1\r\nHost: 127.0.0.1:{http}\r\n"
                f"Origin: http://127.0.0.1:8480\r\n\r\n".encode()
            )
            got = _read_until(page, b"data: ")
            got += _read_until(page, b"\n\n", within=1.0)
        assert b"HTTP/1.1 200 OK" in got and b"text/event-stream" in got
        data = got.split(b"data: ", 1)[1].split(b"\n\n", 1)[0]
        assert json.loads(data)["lat"] == 12.5
        assert any("A map page connected" in line for line in logged)


def test_a_page_and_an_nmea_client_share_one_gpsd_watch() -> None:
    gpsd = FakeGpsd(_json({"class": "VERSION"}, FIX_3D), repeat=True, every=0.05)
    with _tether(gpsd) as (nmea, http, _):
        client = socket.create_connection(("127.0.0.1", nmea), timeout=5)
        page = socket.create_connection(("127.0.0.1", http), timeout=5)
        with client, page:
            assert _lines(client, 2)[0].startswith(b"$GPRMC")
            page.sendall(
                f"GET /position HTTP/1.1\r\nHost: localhost:{http}\r\n"
                f"Accept: text/event-stream\r\n\r\n".encode()
            )
            assert b"data: " in _read_until(page, b"data: ")
            assert gpsd.connections == 1


def test_a_rebinding_page_is_refused_and_gpsd_is_never_asked() -> None:
    gpsd = FakeGpsd(_json(FIX_3D))
    with _tether(gpsd) as (_, http, _):
        with socket.create_connection(("127.0.0.1", http), timeout=5) as page:
            page.sendall(b"GET /position HTTP/1.1\r\nHost: evil.example:10111\r\n\r\n")
            got = _read_until(page, b"refused")
        assert got.startswith(b"HTTP/1.1 403")
        assert gpsd.connections == 0


def test_the_position_listener_is_bound_to_loopback() -> None:
    from test_gps_tether import _listening_addresses

    with listen(port=0) as http:
        assert _listening_addresses(http.getsockname()[1]) == {"0100007F"}


def test_a_request_that_never_finishes_is_closed_after_the_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import hammunition.gps_tether as tether

    monkeypatch.setattr(tether, "REQUEST_DEADLINE", 0.2)
    gpsd = FakeGpsd(_json(FIX_3D))
    with _tether(gpsd) as (_, http, _):
        with socket.create_connection(("127.0.0.1", http), timeout=5) as idle:
            idle.sendall(b"GET /position HTTP/1.1\r\n")  # and nothing more
            idle.settimeout(3)
            assert idle.recv(1) == b"", "the tether closed it"
        assert gpsd.connections == 0


def test_an_unreachable_gpsd_is_a_503_not_silence() -> None:
    gpsd = FakeGpsd(b"")
    address = gpsd.address
    gpsd.close()
    logged: list[str] = []
    stop = threading.Event()
    nmea, http = listen(port=0), listen(port=0)
    thread = threading.Thread(
        target=serve,
        args=(nmea,),
        kwargs={"http": http, "gpsd": address, "stop": stop, "log": logged.append, "poll": 0.02},
        daemon=True,
    )
    thread.start()
    try:
        port = http.getsockname()[1]
        with socket.create_connection(("127.0.0.1", port), timeout=5) as page:
            page.sendall(
                f"GET /position HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
                f"Origin: http://127.0.0.1:8480\r\n\r\n".encode()
            )
            got = _read_until(page, b"reached")
        assert got.startswith(b"HTTP/1.1 503") and b"gpsd cannot be reached" in got
    finally:
        stop.set()
        thread.join(timeout=5)
        nmea.close()
        http.close()
