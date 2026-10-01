# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The GPS tether: NMEA made from gpsd's JSON, served on loopback only.  D-061.

Every coordinate here is synthetic. No test touches the network: gpsd is a
fake on a random loopback port.
"""

from __future__ import annotations

import contextlib
import json
import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
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
    gpsd_address,
    instructions,
    listen,
    sentences,
    serve,
    serve_port,
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
    assert "127.0.0.1" in text and "10110" in text and "GPS TCP/IP" in text
    assert "Ctrl-C" in text


def test_the_instructions_name_the_options_the_gpsd_and_another_port() -> None:
    text = instructions(10111, gpsd=("pi.example", 3000))
    assert "host 127.0.0.1, port 10111" in text
    assert "gpsd at pi.example port 3000" in text
    assert "--gpsd HOST[:PORT]" in text and "--port N" in text
    assert "any number" in text.lower()
    assert "[::1] port 2947" in instructions(gpsd=("::1", 2947))


# ------------------------------------------------------------------ options


@pytest.mark.parametrize(
    ("text", "address"),
    [
        ("127.0.0.1", ("127.0.0.1", 2947)),
        ("127.0.0.1:2947", ("127.0.0.1", 2947)),
        ("192.0.2.10:3000", ("192.0.2.10", 3000)),
        ("pi.local", ("pi.local", 2947)),
        ("shack-pc:2948", ("shack-pc", 2948)),
        ("[::1]", ("::1", 2947)),
        ("[2001:db8::7]:3000", ("2001:db8::7", 3000)),
        ("[::1]:65535", ("::1", 65535)),
    ],
)
def test_gpsd_takes_a_host_and_an_optional_port(text: str, address: tuple[str, int]) -> None:
    assert gpsd_address(text) == address


@pytest.mark.parametrize(
    ("text", "words"),
    [
        ("", "needs a host"),
        (":2947", "needs a host"),
        ("::1", "in brackets"),
        ("2001:db8::7:3000", "in brackets"),
        ("[::1", "closed with ]"),
        ("[]:2947", "needs a host"),
        ("[pi.local]:2947", "not an IPv6 address"),
        ("[::1]2947", "after ]"),
        ("pi.local:", "not a port number"),
        ("pi.local:gpsd", "not a port number"),
        ("pi.local:0", "1 to 65535"),
        ("pi.local:65536", "1 to 65535"),
        ("pi local", "whitespace"),
    ],
)
def test_a_gpsd_address_that_is_not_one_is_refused_by_name(text: str, words: str) -> None:
    with pytest.raises(ValueError, match="--gpsd") as caught:
        gpsd_address(text)
    assert words in str(caught.value)


@pytest.mark.parametrize(("text", "port"), [("1024", 1024), ("10111", 10111), ("65535", 65535)])
def test_port_takes_1024_to_65535(text: str, port: int) -> None:
    assert serve_port(text) == port


@pytest.mark.parametrize(
    ("text", "words"),
    [
        ("1023", "below 1024"),
        ("80", "below 1024"),
        ("0", "below 1024"),
        ("-1", "below 1024"),
        ("65536", "above 65535"),
        ("100000", "above 65535"),
        ("ten", "not a number"),
        ("", "not a number"),
        ("10110.5", "not a number"),
    ],
)
def test_a_port_out_of_range_is_refused_by_name(text: str, words: str) -> None:
    with pytest.raises(ValueError, match="--port") as caught:
        serve_port(text)
    assert words in str(caught.value)


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
    """A gpsd on a random loopback port (IPv4, or ``::1`` with *family*). Records the first line each client
    sends, writes *script*, then (with *repeat*) keeps writing it every
    *every* seconds, and counts the connections the tether closed."""

    def __init__(
        self,
        script: bytes,
        *,
        repeat: bool = False,
        every: float = 0.05,
        family: socket.AddressFamily = socket.AF_INET,
        settle: float = 0.0,
    ) -> None:
        self.script = script
        self.repeat = repeat
        self.every = every
        #: Seconds between writing the script and counting the watch open:
        #: a slow machine's scheduling, made certain for a test.
        self.settle = settle
        self.received: list[bytes] = []
        self.open: list[socket.socket] = []
        self.connections = 0
        self.closed_by_tether = 0
        self.server = socket.socket(family, socket.SOCK_STREAM)
        self.server.bind(("::1" if family == socket.AF_INET6 else "127.0.0.1", 0))
        self.server.listen(8)
        self.server.settimeout(0.1)
        self.address: tuple[str, int] = self.server.getsockname()[:2]
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
            conn.settimeout(0.02)
            line = b""
            try:
                while not line.endswith(b"\n") and not self.stop.is_set():
                    try:
                        chunk = conn.recv(1)
                    except TimeoutError:
                        continue
                    if not chunk:
                        return
                    line += chunk
                self.received.append(line)
                self._write(conn)
                time.sleep(self.settle)
                self.open.append(conn)
                while not self.stop.is_set():
                    try:
                        if conn.recv(1) == b"":
                            self.closed_by_tether += 1
                            return
                    except TimeoutError:
                        pass
                    if self.repeat:
                        self._write(conn)
                        time.sleep(self.every)
            except OSError:
                self.closed_by_tether += 1

    def _write(self, conn: socket.socket) -> None:
        """Write the script whole. The 0.02 s timeout is for the reads that
        watch for the tether closing; a flood of 2000 fixes takes longer than
        that to hand to a tether busy with a stalled client, and a timeout
        here would close the connection and read as gpsd going away."""
        conn.settimeout(5)
        try:
            conn.sendall(self.script)
        finally:
            conn.settimeout(0.02)

    def broadcast(self, data: bytes, *, watches: int = 1, within: float = 5.0) -> None:
        """Send *data* on every open connection, once, after *watches* are open.

        The tether logs a client connected as soon as its WATCH is sent, before
        this fake's thread has read it and counted the watch open; without the
        wait, a burst sent in that gap goes to no connection (issue #156)."""
        deadline = time.monotonic() + within
        while len(self.open) < watches:
            if time.monotonic() > deadline:
                raise AssertionError(f"{len(self.open)} of {watches} gpsd watches open")
            time.sleep(0.01)
        for conn in list(self.open):
            with contextlib.suppress(OSError):
                conn.sendall(data)

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


@contextmanager
def _tether_on(gpsd: FakeGpsd) -> Iterator[tuple[int, list[str]]]:
    logged: list[str] = []
    listener, stop, thread = _run_tether(gpsd.address, logged)
    try:
        yield listener.getsockname()[1], logged
    finally:
        stop.set()
        thread.join(timeout=5)
        assert not thread.is_alive(), "serve stops when asked"
        listener.close()
        gpsd.close()


@pytest.fixture
def tether(request: pytest.FixtureRequest) -> Iterator[Tether]:
    script = getattr(request, "param", _json({"class": "VERSION"}, FIX_3D))
    gpsd = FakeGpsd(script)
    with _tether_on(gpsd) as (port, logged):
        yield port, gpsd, logged


def _until_rmc_and_gga(client: socket.socket, within: float = 3.0) -> set[bytes]:
    """The sentence types seen until both have arrived; raw recv and no
    makefile, so closing the socket really closes it."""
    seen: set[bytes] = set()
    buffer = b""
    deadline = time.monotonic() + within
    client.settimeout(0.1)
    while not {b"$GPRMC", b"$GPGGA"} <= seen and time.monotonic() < deadline:
        try:
            data = client.recv(4096)
        except TimeoutError:
            continue
        if not data:
            break
        buffer += data
        *lines, buffer = buffer.split(b"\n")
        seen.update(line[:6] for line in lines)
    return seen


def _drain(client: socket.socket) -> None:
    """Read whatever is already queued, so what follows is fresh."""
    client.settimeout(0.01)
    deadline = time.monotonic() + 0.3
    with contextlib.suppress(TimeoutError, BlockingIOError):
        while time.monotonic() < deadline and client.recv(65536):
            pass


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


def _lines(client: socket.socket, count: int, within: float = 3.0) -> list[bytes]:
    """The next *count* whole lines, raw recv, so closing really closes."""
    buffer = b""
    deadline = time.monotonic() + within
    client.settimeout(0.1)
    while buffer.count(b"\n") < count and time.monotonic() < deadline:
        try:
            data = client.recv(4096)
        except TimeoutError:
            continue
        if not data:
            break
        buffer += data
    return buffer.split(b"\n")[:count]


def test_two_clients_at_once_each_receive_every_sentence_from_one_gpsd_watch() -> None:
    """Fan-out: QMapShack and a second NMEA client share one tether, and gpsd
    is watched once however many are connected."""
    script = _json({"class": "VERSION"}, FIX_3D)
    gpsd = FakeGpsd(script, repeat=True, every=0.1)
    with _tether_on(gpsd) as (port, logged):
        with (
            socket.create_connection(("127.0.0.1", port), timeout=5) as first,
            socket.create_connection(("127.0.0.1", port), timeout=5) as second,
        ):
            _wait_for(logged, "2 connected")
            for client in (first, second):
                assert _until_rmc_and_gga(client) >= {b"$GPRMC", b"$GPGGA"}
            assert gpsd.connections == 1, "one gpsd watch for every client"
        _wait_for(logged, "disconnected; 0 connected")
        for _ in range(250):
            if gpsd.closed_by_tether == 1:
                break
            time.sleep(0.02)
        assert gpsd.closed_by_tether == 1, "the watch closes when the last client goes"


def test_both_clients_get_the_same_sentences_byte_for_byte() -> None:
    """gpsd sends one burst after both have connected; both get all of it."""
    gpsd = FakeGpsd(_json({"class": "VERSION"}))
    tpvs = [{**FIX_3D, "time": f"2026-09-29T14:05:{second:02d}.000Z"} for second in range(10)]
    with (
        _tether_on(gpsd) as (port, logged),
        socket.create_connection(("127.0.0.1", port), timeout=5) as first,
        socket.create_connection(("127.0.0.1", port), timeout=5) as second,
    ):
        _wait_for(logged, "2 connected")
        gpsd.broadcast(_json(*tpvs))
        one, two = _lines(first, 20), _lines(second, 20)
    expected = [line.rstrip(b"\n") for tpv in tpvs for line in sentences(tpv)]
    assert one == two == expected


def test_a_burst_reaches_a_watch_the_fake_has_not_finished_opening() -> None:
    """Issue #156. The tether logs a client connected once its WATCH is
    sent, before the fake gpsd's thread has read it and counted the watch
    open; a burst sent in that gap went to no connection, and both clients
    of the byte-for-byte test read nothing. *settle* holds the gap open."""
    gpsd = FakeGpsd(_json({"class": "VERSION"}), settle=0.5)
    with (
        _tether_on(gpsd) as (port, logged),
        socket.create_connection(("127.0.0.1", port), timeout=5) as client,
    ):
        _wait_for(logged, "1 connected")
        gpsd.broadcast(_json(FIX_3D))
        assert _until_rmc_and_gga(client) >= {b"$GPRMC", b"$GPGGA"}


def test_one_client_leaving_keeps_the_watch_for_the_other() -> None:
    gpsd = FakeGpsd(_json({"class": "VERSION"}, FIX_3D), repeat=True)
    with (
        _tether_on(gpsd) as (port, logged),
        socket.create_connection(("127.0.0.1", port), timeout=5) as stays,
    ):
        with socket.create_connection(("127.0.0.1", port), timeout=5) as leaves:
            _wait_for(logged, "2 connected")
            assert _until_rmc_and_gga(leaves) >= {b"$GPRMC", b"$GPGGA"}
        _wait_for(logged, "disconnected; 1 connected")
        _drain(stays)
        assert _until_rmc_and_gga(stays) >= {b"$GPRMC", b"$GPGGA"}
        assert gpsd.connections == 1 and gpsd.closed_by_tether == 0


def test_a_stalled_client_is_dropped_and_the_other_keeps_receiving() -> None:
    """One client stops reading while gpsd floods: it alone is dropped, and
    the client that reads is served before, during and after."""
    flood = _json(*([{"class": "VERSION"}] + [FIX_3D] * 50))
    gpsd = FakeGpsd(flood, repeat=True, every=0.0)
    with _tether_on(gpsd) as (port, logged):
        stalled = socket.socket()
        stalled.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
        stalled.connect(("127.0.0.1", port))
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=5) as reader:
                reader.settimeout(0.1)
                received = 0
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline and not any(
                    "not reading" in line for line in logged
                ):
                    with contextlib.suppress(TimeoutError):
                        received += len(reader.recv(65536))
                assert any("not reading" in line for line in logged), logged
                assert received > 64 * 1024, "the reader was served all along"
                _drain(reader)
                assert _until_rmc_and_gga(reader) >= {b"$GPRMC", b"$GPGGA"}
            assert sum("not reading" in line for line in logged) == 1, logged
            assert gpsd.connections == 1, "dropping one client kept the gpsd watch"
        finally:
            stalled.close()


def test_a_remote_gpsd_on_ipv6_is_reached() -> None:
    """``--gpsd [::1]:PORT``: an IPv6 gpsd; the tether itself stays on 127.0.0.1."""
    if not socket.has_ipv6:
        pytest.skip("no IPv6 in this Python")
    try:
        gpsd = FakeGpsd(_json({"class": "VERSION"}, FIX_3D), family=socket.AF_INET6)
    except OSError:
        pytest.skip("no ::1 on this machine")
    with (
        _tether_on(gpsd) as (port, _),
        socket.create_connection(("127.0.0.1", port), timeout=5) as client,
    ):
        rmc, gga = _read_lines(client, 2)
    assert rmc.startswith(b"$GPRMC,140509.25,A,") and gga.startswith(b"$GPGGA,")
    assert gpsd.received == [WATCH]


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


def test_a_client_can_reconnect_again_and_again_at_once() -> None:
    """QMapShack reconnects; each client is served, and one that has gone is
    never counted alongside the next."""
    gpsd = FakeGpsd(_json({"class": "VERSION"}, FIX_3D), repeat=True)
    with _tether_on(gpsd) as (port, logged):
        for _ in range(5):
            with socket.create_connection(("127.0.0.1", port), timeout=5) as client:
                assert _until_rmc_and_gga(client) >= {b"$GPRMC", b"$GPGGA"}
        assert not any("2 connected" in line for line in logged), logged


def test_a_client_closing_mid_stream_ends_its_session_and_its_gpsd_watch() -> None:
    gpsd = FakeGpsd(_json({"class": "VERSION"}, FIX_3D), repeat=True)
    with _tether_on(gpsd) as (port, logged):
        with socket.create_connection(("127.0.0.1", port), timeout=5) as client:
            assert client.recv(7) == b"$GPRMC,"
        _wait_for(logged, "disconnected")
        for _ in range(250):
            if gpsd.closed_by_tether == 1:
                break
            time.sleep(0.02)
        assert gpsd.closed_by_tether == 1, "the session's gpsd socket is closed"
        with socket.create_connection(("127.0.0.1", port), timeout=5) as again:
            assert _until_rmc_and_gga(again) >= {b"$GPRMC", b"$GPGGA"}
        assert gpsd.connections == 2


def test_a_closed_client_is_noticed_before_the_next_is_counted() -> None:
    """gpsd silent, so no send reveals the close: the next accept must still
    find the old client gone rather than count it as connected."""
    gpsd = FakeGpsd(_json({"class": "VERSION"}))
    with _tether_on(gpsd) as (port, logged):
        for _ in range(5):
            with socket.create_connection(("127.0.0.1", port), timeout=5) as client:
                client.settimeout(0.3)
                with pytest.raises(TimeoutError):
                    client.recv(64)  # held open, not closed on us
        assert not any("2 connected" in line for line in logged), logged


def test_a_client_that_stops_reading_does_not_hold_the_loop() -> None:
    """gpsd floods and the first client never reads: a second connection is
    still answered at once, and the reader-less client is dropped."""
    flood = _json(*([{"class": "VERSION"}] + [FIX_3D] * 2000))
    gpsd = FakeGpsd(flood, repeat=True, every=0.0)
    with _tether_on(gpsd) as (port, logged):
        # A small receive window, set before connecting, so the kernel's
        # buffers do not absorb the flood on the reader's behalf: on a
        # default Linux they hold megabytes, and the tether's own limit
        # was never reached before the script ran out.
        idle = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        idle.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
        idle.settimeout(5)
        idle.connect(("127.0.0.1", port))
        try:
            time.sleep(0.3)
            started = time.monotonic()
            with socket.create_connection(("127.0.0.1", port), timeout=5) as second:
                second.settimeout(2)
                with contextlib.suppress(OSError):
                    second.recv(64)
            assert time.monotonic() - started < 1.0, "the loop answered promptly"
            _wait_for(logged, "not reading")
        finally:
            idle.close()


def test_a_close_and_a_new_connection_in_one_batch_serve_the_new_client() -> None:
    """The loop is held (inside its own log line) while the first client
    closes and the next connects, so one select returns both events. The
    next client must be served, and the one that left not counted."""
    gpsd = FakeGpsd(_json({"class": "VERSION"}, FIX_3D), repeat=True)
    release = threading.Event()
    logged: list[str] = []

    def log(line: str) -> None:
        logged.append(line)
        if line.startswith("A client connected") and len(logged) == 1:
            release.wait(5)

    stop = threading.Event()
    with listen(port=0) as listener:
        port = listener.getsockname()[1]
        thread = threading.Thread(
            target=serve,
            args=(listener,),
            kwargs={"gpsd": gpsd.address, "stop": stop, "log": log, "poll": 0.02},
            daemon=True,
        )
        thread.start()
        try:
            first = socket.create_connection(("127.0.0.1", port), timeout=5)
            _wait_for(logged, "A client connected")
            first.close()
            with socket.create_connection(("127.0.0.1", port), timeout=5) as second:
                time.sleep(0.1)  # both events are now pending
                release.set()
                assert _until_rmc_and_gga(second) >= {b"$GPRMC", b"$GPGGA"}
            assert not any("2 connected" in line for line in logged), logged
        finally:
            release.set()
            stop.set()
            thread.join(timeout=5)
            gpsd.close()


def test_stopping_closes_every_client_and_the_gpsd_watch() -> None:
    """Ctrl-C (here, *stop*) leaves nothing open: both clients see the close,
    and so does gpsd."""
    gpsd = FakeGpsd(_json({"class": "VERSION"}, FIX_3D), repeat=True)
    logged: list[str] = []
    listener, stop, thread = _run_tether(gpsd.address, logged)
    try:
        port = listener.getsockname()[1]
        first = socket.create_connection(("127.0.0.1", port), timeout=5)
        second = socket.create_connection(("127.0.0.1", port), timeout=5)
        _wait_for(logged, "2 connected")
        stop.set()
        thread.join(timeout=5)
        assert not thread.is_alive()
        for client in (first, second):
            client.settimeout(2)
            while client.recv(65536):
                pass  # what was queued, then the close
            client.close()
        for _ in range(250):
            if gpsd.closed_by_tether == 1:
                break
            time.sleep(0.02)
        assert gpsd.closed_by_tether == 1
    finally:
        listener.close()
        gpsd.close()
