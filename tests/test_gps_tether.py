# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The GPS tether: NMEA made from gpsd's JSON, served on loopback only.  D-061.

Every coordinate here is synthetic. No test touches the network: gpsd is a
fake on a random loopback port.
"""

from __future__ import annotations

import json
import socket
import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from hammunition.gps_tether import (
    GPSD,
    HOST,
    PORT,
    WATCH,
    Feed,
    checksum,
    instructions,
    listen,
    sentences,
    serve,
)

# ---------------------------------------------------------------- sentences


def test_the_checksum_is_the_xor_of_the_body() -> None:
    """The two textbook sentences, whose checksums are printed with them."""
    assert checksum("GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,") == "47"
    assert checksum("GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W") == "6A"


FIX_3D: dict[str, Any] = {
    "class": "TPV",
    "mode": 3,
    "time": "2026-09-29T14:05:09.250Z",
    "lat": 12.5,
    "lon": 34.75,
    "altMSL": 101.3,
    "alt": 999.0,
    "speed": 2.0,
    "track": 90.0,
}


def test_a_3d_fix_gives_rmc_then_gga() -> None:
    assert sentences(FIX_3D, satellites=7, hdop=0.9) == [
        b"$GPRMC,140509.25,A,1230.0000,N,03445.0000,E,3.9,90.0,290926,,,A*63\r\n",
        b"$GPGGA,140509.25,1230.0000,N,03445.0000,E,1,07,0.9,101.3,M,,M,,*77\r\n",
    ]


def test_dgps_is_quality_2_and_mode_d() -> None:
    assert sentences({**FIX_3D, "status": 2}, satellites=7, hdop=0.9) == [
        b"$GPRMC,140509.25,A,1230.0000,N,03445.0000,E,3.9,90.0,290926,,,D*66\r\n",
        b"$GPGGA,140509.25,1230.0000,N,03445.0000,E,2,07,0.9,101.3,M,,M,,*74\r\n",
    ]


def test_southern_and_western_hemispheres_and_missing_fields_are_empty() -> None:
    """A 2D fix: no altitude is given even if gpsd has one; nothing invented."""
    tpv = {
        "class": "TPV",
        "mode": 2,
        "time": "2026-01-02T03:04:05.000Z",
        "lat": -45.25,
        "lon": -123.125,
        "alt": 50.0,
    }
    assert sentences(tpv) == [
        b"$GPRMC,030405.00,A,4515.0000,S,12307.5000,W,,,020126,,,A*53\r\n",
        b"$GPGGA,030405.00,4515.0000,S,12307.5000,W,1,,,,M,,M,,*78\r\n",
    ]


def test_no_time_takes_the_system_clock_in_utc_and_minutes_never_reach_60(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import hammunition.gps_tether as tether

    monkeypatch.setattr(tether, "_now", lambda: datetime(2026, 3, 4, 5, 6, 7, 890_000, UTC))
    tpv = {"class": "TPV", "mode": 2, "lat": 10.99999999, "lon": 0.0}
    assert sentences(tpv) == [
        b"$GPRMC,050607.89,A,1100.0000,N,00000.0000,E,,,040326,,,A*58\r\n",
        b"$GPGGA,050607.89,1100.0000,N,00000.0000,E,1,,,,M,,M,,*77\r\n",
    ]


def test_the_clock_fallback_is_utc_whatever_the_local_zone() -> None:
    import hammunition.gps_tether as tether

    now = tether._now()
    assert now.utcoffset() == timedelta(0)
    assert abs((now - datetime.now(UTC)).total_seconds()) < 5


def test_alt_is_used_when_altmsl_is_absent() -> None:
    tpv = {k: v for k, v in FIX_3D.items() if k != "altMSL"}
    assert b",999.0,M," in sentences(tpv)[1]


@pytest.mark.parametrize(
    "tpv",
    [
        {**FIX_3D, "mode": 1},
        {**FIX_3D, "mode": 0},
        {k: v for k, v in FIX_3D.items() if k != "mode"},
        {k: v for k, v in FIX_3D.items() if k != "lat"},
        {k: v for k, v in FIX_3D.items() if k != "lon"},
        {**FIX_3D, "lat": "12.5"},
        {**FIX_3D, "lat": True},
        {**FIX_3D, "lat": float("nan")},
        {**FIX_3D, "lat": 91.0},
        {**FIX_3D, "lon": -180.5},
        {**FIX_3D, "mode": "3"},
    ],
)
def test_no_fix_or_no_usable_position_gives_no_sentence(tpv: dict[str, Any]) -> None:
    assert sentences(tpv) == []


def test_a_malformed_time_takes_the_clock_and_a_bad_speed_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import hammunition.gps_tether as tether

    monkeypatch.setattr(tether, "_now", lambda: datetime(2026, 3, 4, 5, 6, 7, 890_000, UTC))
    rmc, gga = sentences({**FIX_3D, "time": "yesterday", "speed": "fast"})
    assert rmc.startswith(b"$GPRMC,050607.89,A,1230.0000,N,03445.0000,E,,90.0,040326,")
    assert gga.startswith(b"$GPGGA,050607.89,1230")


def test_every_sentence_is_crlf_terminated_and_its_checksum_verifies() -> None:
    for line in sentences(FIX_3D, satellites=12, hdop=1.25):
        text = line.decode("ascii")
        assert text.endswith("\r\n") and text.startswith("$")
        body, star = text[1:-2].split("*")
        assert checksum(body) == star


# --------------------------------------------------------------------- feed


def _json(*docs: dict[str, Any]) -> bytes:
    return b"".join(json.dumps(doc).encode() + b"\r\n" for doc in docs)


def test_the_feed_takes_satellites_from_the_latest_sky() -> None:
    feed = Feed()
    sky_used = {
        "class": "SKY",
        "hdop": 0.9,
        "satellites": [{"used": True}, {"used": False}, {"used": True}],
    }
    out = feed.push(_json({"class": "VERSION"}, sky_used, FIX_3D))
    assert out[1].split(b",")[7:9] == [b"02", b"0.9"]
    out = feed.push(_json({"class": "SKY", "uSat": 9, "hdop": 1.4}, FIX_3D))
    assert out[1].split(b",")[7:9] == [b"09", b"1.4"]
    # A SKY without a satellite count keeps the count it had.
    out = feed.push(_json({"class": "SKY", "hdop": 2.0}, FIX_3D))
    assert out[1].split(b",")[7:9] == [b"09", b"2.0"]


def test_the_feed_joins_lines_split_across_reads_and_skips_garbage() -> None:
    feed = Feed()
    data = b"not json\n[1,2]\n" + _json(FIX_3D)
    assert feed.push(data[:20]) == []
    assert len(feed.push(data[20:])) == 2


def test_an_endless_line_is_dropped_not_buffered_forever() -> None:
    feed = Feed()
    assert feed.push(b"x" * (Feed.MAX_LINE + 10)) == []
    assert len(feed.push(b"\n" + _json(FIX_3D))) == 2


# ------------------------------------------------------------------- server


def test_the_constants_are_loopback_port_10110_and_gpsds_own_port() -> None:
    assert (HOST, PORT) == ("127.0.0.1", 10110)
    assert GPSD == ("127.0.0.1", 2947)
    assert WATCH == b'?WATCH={"enable":true,"json":true}\n'


def test_the_instructions_name_the_host_and_port() -> None:
    text = instructions()
    assert "127.0.0.1" in text and "10110" in text and "GPS Tether" in text
    assert "Ctrl-C" in text


def _listening_addresses(port: int) -> set[str]:
    """Local addresses of sockets listening on *port*, from /proc/net/tcp."""
    found: set[str] = set()
    for table in ("/proc/net/tcp", "/proc/net/tcp6"):
        path = Path(table)
        if not path.exists():
            continue
        for line in path.read_text().splitlines()[1:]:
            fields = line.split()
            address, port_hex = fields[1].rsplit(":", 1)
            if int(port_hex, 16) == port and fields[3] == "0A":  # TCP_LISTEN
                found.add(address)
    return found


def test_the_listener_is_bound_to_loopback_and_nowhere_else() -> None:
    with listen(port=0) as listener:
        host, port = listener.getsockname()
        assert host == "127.0.0.1"
        assert _listening_addresses(port) == {"0100007F"}, "127.0.0.1, little-endian hex"


class FakeGpsd:
    """A gpsd on a random loopback port: records the first line each client
    sends, then writes *script* and holds the connection open."""

    def __init__(self, script: bytes) -> None:
        self.script = script
        self.received: list[bytes] = []
        self.connections = 0
        self.server = socket.socket()
        self.server.bind(("127.0.0.1", 0))
        self.server.listen(4)
        self.server.settimeout(0.1)
        self.address: tuple[str, int] = self.server.getsockname()
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self) -> None:
        while not self.stop.is_set():
            try:
                conn, _ = self.server.accept()
            except TimeoutError:
                continue
            self.connections += 1
            threading.Thread(target=self._client, args=(conn,), daemon=True).start()

    def _client(self, conn: socket.socket) -> None:
        with conn:
            conn.settimeout(5)
            try:
                self.received.append(conn.makefile("rb").readline())
                conn.sendall(self.script)
                while not self.stop.is_set():
                    time.sleep(0.02)
            except OSError:
                pass

    def close(self) -> None:
        self.stop.set()
        self.thread.join(timeout=5)
        self.server.close()


Tether = tuple[int, FakeGpsd, list[str]]


def _run_tether(gpsd_address: tuple[str, int], logged: list[str]) -> tuple[Any, ...]:
    stop = threading.Event()
    listener = listen(port=0)
    thread = threading.Thread(
        target=serve,
        args=(listener,),
        kwargs={
            "gpsd": gpsd_address,
            "stop": stop,
            "log": logged.append,
            "poll": 0.02,
            "quiet_after": 0.2,
        },
        daemon=True,
    )
    thread.start()
    return listener, stop, thread


@pytest.fixture
def tether(request: pytest.FixtureRequest) -> Iterator[Tether]:
    script = getattr(request, "param", _json({"class": "VERSION"}, FIX_3D))
    gpsd = FakeGpsd(script)
    logged: list[str] = []
    listener, stop, thread = _run_tether(gpsd.address, logged)
    try:
        yield listener.getsockname()[1], gpsd, logged
    finally:
        stop.set()
        thread.join(timeout=5)
        assert not thread.is_alive(), "serve stops when asked"
        listener.close()
        gpsd.close()


def _read_lines(client: socket.socket, count: int) -> list[bytes]:
    reader = client.makefile("rb")
    return [reader.readline() for _ in range(count)]


def _wait_for(logged: list[str], words: str) -> None:
    for _ in range(250):
        if any(words in line for line in logged):
            return
        time.sleep(0.02)
    raise AssertionError(f"never logged {words!r}: {logged}")


def test_the_server_watches_gpsd_in_json_and_serves_nmea(tether: Tether) -> None:
    port, gpsd, _ = tether
    with socket.create_connection(("127.0.0.1", port), timeout=5) as client:
        rmc, gga = _read_lines(client, 2)
    assert rmc.startswith(b"$GPRMC,140509.25,A,1230.0000,N,") and rmc.endswith(b"\r\n")
    assert gga.startswith(b"$GPGGA,140509.25,1230.0000,N,")
    assert gpsd.received == [WATCH]


def test_one_client_at_a_time_the_second_is_turned_away(tether: Tether) -> None:
    port, gpsd, logged = tether
    with socket.create_connection(("127.0.0.1", port), timeout=5) as first:
        assert _read_lines(first, 1)[0].startswith(b"$GPRMC")
        with socket.create_connection(("127.0.0.1", port), timeout=5) as second:
            assert second.recv(64) == b"", "closed without a byte"
        assert gpsd.connections == 1
    _wait_for(logged, "one at a time")
    _wait_for(logged, "disconnected")
    # Once the first has gone, the next is served, on a fresh gpsd watch.
    with socket.create_connection(("127.0.0.1", port), timeout=5) as third:
        assert _read_lines(third, 1)[0].startswith(b"$GPRMC")
    assert gpsd.connections == 2


@pytest.mark.parametrize("tether", [_json({"class": "VERSION"})], indirect=True)
def test_gpsd_with_no_fix_sends_nothing_and_says_so(tether: Tether) -> None:
    port, _, logged = tether
    with socket.create_connection(("127.0.0.1", port), timeout=5) as client:
        client.settimeout(0.5)
        with pytest.raises(TimeoutError):
            client.recv(64)
        _wait_for(logged, "no position with a fix")


def test_an_unreachable_gpsd_is_named_and_the_client_closed() -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        dead = probe.getsockname()  # bound, never listening: refused
        logged: list[str] = []
        listener, stop, thread = _run_tether(dead, logged)
        try:
            port = listener.getsockname()[1]
            with socket.create_connection(("127.0.0.1", port), timeout=5) as client:
                assert client.recv(64) == b""
        finally:
            stop.set()
            thread.join(timeout=5)
            listener.close()
    _wait_for(logged, "cannot reach gpsd")
