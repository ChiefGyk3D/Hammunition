# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The GPS tether: NMEA made from gpsd's JSON, served on loopback.  D-061.

QMapShack has no gpsd client. Its Realtime source *GPS TCP/IP* (the source list's "Add source") reads NMEA (RMC
and GGA) from a TCP host. The first tether piped ``gpspipe -r`` through ``socat``.
On the bench on 2026-09-29, with it connected, no NMEA reached the client;
gpsd's JSON watch was sending no TPV at the same time (``?POLL`` answered
``active: 0``), so no cause for that silence is established, and
``gpspipe(1)`` says ``-r`` emits pseudo-NMEA built from binary data. This
version stands on its own: no socat or gpspipe, the loopback bind made and
tested in code, sentences built from the JSON feed every gpsd client (xgps,
Navit) reads, and a plain message when gpsd has no fix. It asks gpsd for
JSON itself, ``?WATCH={"enable":true,"json":true}`` on
127.0.0.1 port 2947, and writes ``$GPRMC`` and ``$GPGGA`` for every ``TPV``
with a 2D or 3D fix. A field gpsd did not give is an empty field, with one
exception: a TPV with no time (or one that does not parse) is stamped with
the system clock in UTC, because a reader may drop a sentence without one.

It listens on 127.0.0.1 port 10110, the conventional NMEA-0183 port, and
nowhere else: a position is where the operator is, and it is not served to
the network. One client at a time; a second is closed at once and the
operator told. Each client gets its own gpsd watch, opened when it connects
and closed when it leaves. It runs only while the operator runs it, in a
terminal, and stops with Ctrl-C; nothing is installed as a service, nothing
runs as root, and it is the standard library only. Navit needs none of
this: it reads gpsd itself.
"""

from __future__ import annotations

import json
import math
import selectors
import socket
import threading
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

__all__ = [
    "GPSD",
    "HOST",
    "PORT",
    "WATCH",
    "Feed",
    "checksum",
    "instructions",
    "listen",
    "sentences",
    "serve",
]

HOST = "127.0.0.1"
PORT = 10110
GPSD = ("127.0.0.1", 2947)
WATCH = b'?WATCH={"enable":true,"json":true}\n'

#: m/s to knots: 3600 / 1852.
KNOTS_PER_MPS = 3600 / 1852


def checksum(body: str) -> str:
    """NMEA's checksum: the XOR of every character between ``$`` and ``*``."""
    value = 0
    for char in body:
        value ^= ord(char)
    return f"{value:02X}"


def _sentence(body: str) -> bytes:
    return f"${body}*{checksum(body)}\r\n".encode("ascii")


def _number(value: object) -> float | None:
    """A finite JSON number, or None; ``True`` is not a number here."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _degrees_minutes(value: float, width: int, positive: str, negative: str) -> tuple[str, str]:
    """``ddmm.mmmm`` (``dddmm.mmmm`` for longitude) and the hemisphere.

    Rounded once, in ten-thousandths of a minute, so a value just under a
    whole degree becomes the next degree, never ``60.0000`` minutes.
    """
    total = round(abs(value) * 60 * 10_000)
    degrees, rest = divmod(total, 60 * 10_000)
    minutes, fraction = divmod(rest, 10_000)
    hemisphere = negative if value < 0 else positive
    return f"{degrees:0{width}d}{minutes:02d}.{fraction:04d}", hemisphere


def _now() -> datetime:
    """The system clock in UTC; a seam for the tests."""
    return datetime.now(UTC)


def _time_fields(value: object) -> tuple[str, str]:
    """``hhmmss.ss`` and ``ddmmyy`` in UTC from gpsd's ISO 8601 time.

    A TPV with no time, or one that does not parse, takes the system clock
    in UTC instead: a reader such as QMapShack may drop a sentence with an
    empty time, and a fix without gpsd's time is rare and brief.
    """
    when = None
    if isinstance(value, str):
        try:
            when = datetime.fromisoformat(value)
        except ValueError:
            when = None
    if when is None:
        when = _now()
    elif when.tzinfo is not None:
        when = when.astimezone(UTC)
    return f"{when:%H%M%S}.{when.microsecond // 10_000:02d}", f"{when:%d%m%y}"


def _fixed(value: float | None, places: int) -> str:
    return "" if value is None else f"{value:.{places}f}"


def sentences(
    tpv: Mapping[str, Any], *, satellites: int | None = None, hdop: float | None = None
) -> list[bytes]:
    """``$GPRMC`` then ``$GPGGA`` for a gpsd ``TPV`` with a fix, else none.

    *satellites* and *hdop* come from the latest ``SKY``; a TPV carries
    neither. Altitude is given for a 3D fix only, from ``altMSL`` or, from an
    older gpsd, ``alt``. gpsd's ``status`` 2 (DGPS) is fix quality 2 and
    RMC mode ``D``; every other fix is quality 1, mode ``A``.
    """
    mode = tpv.get("mode")
    if isinstance(mode, bool) or not isinstance(mode, int) or mode < 2:
        return []
    lat, lon = _number(tpv.get("lat")), _number(tpv.get("lon"))
    if lat is None or lon is None or abs(lat) > 90 or abs(lon) > 180:
        return []
    hms, dmy = _time_fields(tpv.get("time"))
    latitude, north_south = _degrees_minutes(lat, 2, "N", "S")
    longitude, east_west = _degrees_minutes(lon, 3, "E", "W")
    speed = _number(tpv.get("speed"))
    knots = None if speed is None else speed * KNOTS_PER_MPS
    track = _number(tpv.get("track"))
    dgps = tpv.get("status") == 2
    altitude = None
    if mode >= 3:
        altitude = _number(tpv.get("altMSL"))
        if altitude is None:
            altitude = _number(tpv.get("alt"))
    geoid = _number(tpv.get("geoidSep"))
    used = "" if satellites is None else f"{satellites:02d}"
    position = f"{latitude},{north_south},{longitude},{east_west}"
    rmc = (
        f"GPRMC,{hms},A,{position},{_fixed(knots, 1)},{_fixed(track, 1)},{dmy},,,"
        f"{'D' if dgps else 'A'}"
    )
    gga = (
        f"GPGGA,{hms},{position},{2 if dgps else 1},{used},{_fixed(hdop, 1)},"
        f"{_fixed(altitude, 1)},M,{_fixed(geoid, 1)},M,,"
    )
    return [_sentence(rmc), _sentence(gga)]


class Feed:
    """gpsd's JSON stream in, NMEA out; remembers the latest SKY."""

    #: A line longer than this is not gpsd's and is dropped, not buffered.
    MAX_LINE = 1 << 20

    def __init__(self) -> None:
        self._buffer = b""
        self._skipping = False
        self.satellites: int | None = None
        self.hdop: float | None = None

    def push(self, data: bytes) -> list[bytes]:
        out: list[bytes] = []
        self._buffer += data
        while True:
            line, newline, rest = self._buffer.partition(b"\n")
            if not newline:
                if len(self._buffer) > self.MAX_LINE:
                    self._buffer, self._skipping = b"", True
                return out
            self._buffer = rest
            if self._skipping:
                self._skipping = False
                continue
            out.extend(self._line(line))

    def _line(self, line: bytes) -> list[bytes]:
        try:
            message = json.loads(line)
        except ValueError:
            return []
        if not isinstance(message, dict):
            return []
        kind = message.get("class")
        if kind == "SKY":
            self._sky(message)
            return []
        if kind == "TPV":
            return sentences(message, satellites=self.satellites, hdop=self.hdop)
        return []

    def _sky(self, sky: Mapping[str, Any]) -> None:
        used = sky.get("uSat")
        listed = sky.get("satellites")
        if isinstance(used, int) and not isinstance(used, bool) and 0 <= used < 100:
            self.satellites = used
        elif isinstance(listed, list):
            count = sum(1 for sat in listed if isinstance(sat, dict) and sat.get("used") is True)
            self.satellites = min(99, count)
        hdop = _number(sky.get("hdop"))
        if hdop is not None:
            self.hdop = hdop


def listen(port: int = PORT) -> socket.socket:
    """The listening socket, on 127.0.0.1 only; *port* 0 is for the tests."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((HOST, port))
        listener.listen(1)
    except OSError:
        listener.close()
        raise
    return listener


class _Session:
    """One client and its own gpsd watch.

    Both sockets are non-blocking. What the client has not yet taken waits
    in :attr:`pending`, and the loop never blocks on a send; a client that
    lets more than :attr:`PENDING_LIMIT` pile up has stopped reading and is
    dropped.
    """

    PENDING_LIMIT = 64 * 1024

    def __init__(self, client: socket.socket, upstream: socket.socket) -> None:
        self.client = client
        self.upstream = upstream
        self.feed = Feed()
        self.pending = b""
        self.started = time.monotonic()
        self.sent = 0
        self.warned = False

    def client_gone(self) -> bool:
        """Whether the client has closed, asked without consuming anything."""
        try:
            return self.client.recv(1, socket.MSG_PEEK | socket.MSG_DONTWAIT) == b""
        except BlockingIOError:
            return False
        except OSError:
            return True

    def close(self) -> None:
        self.client.close()
        self.upstream.close()


def serve(
    listener: socket.socket,
    *,
    gpsd: tuple[str, int] = GPSD,
    stop: threading.Event | None = None,
    log: Callable[[str], None] = print,
    poll: float = 0.5,
    quiet_after: float = 10.0,
) -> None:
    """Serve NMEA to one client at a time until *stop* is set (or Ctrl-C).

    *log* gets one line per event the operator should see: a client served,
    turned away or gone; gpsd unreachable, gone or silent.

    Every registration carries the session it belongs to, and an event for
    a session that has ended is dropped: a file descriptor number reused by
    the next client can never be mistaken for the last one. In each batch of
    events the current session's are handled before a new connection, and a
    new connection first checks whether the current client has already
    closed, so a client that left is never counted as connected.
    """
    selector = selectors.DefaultSelector()
    listener.setblocking(False)
    selector.register(listener, selectors.EVENT_READ, None)
    session: _Session | None = None

    def end(current: _Session, why: str) -> None:
        nonlocal session
        if session is not current:
            return
        selector.unregister(current.client)
        selector.unregister(current.upstream)
        current.close()
        session = None
        log(f"{why}; waiting for the next client.")

    def want_write(current: _Session) -> None:
        events = selectors.EVENT_READ | (selectors.EVENT_WRITE if current.pending else 0)
        selector.modify(current.client, events, current)

    def flush(current: _Session) -> None:
        try:
            while current.pending:
                count = current.client.send(current.pending)
                current.pending = current.pending[count:]
        except BlockingIOError:
            pass
        except OSError:
            end(current, "The client disconnected")
            return
        want_write(current)

    def accept() -> None:
        nonlocal session
        try:
            client, _ = listener.accept()
        except BlockingIOError:
            return
        if session is not None and session.client_gone():
            end(session, "The client disconnected")
        if session is not None:
            client.close()
            log("Turned away a second client: one at a time.")
            return
        try:
            upstream = socket.create_connection(gpsd, timeout=5)
        except OSError as exc:
            client.close()
            log(
                f"cannot reach gpsd at {gpsd[0]} port {gpsd[1]}: {exc.strerror or exc}. "
                f"Is gpsd running? `systemctl status gpsd` says."
            )
            return
        try:
            upstream.sendall(WATCH)
        except OSError as exc:
            client.close()
            upstream.close()
            log(f"gpsd refused the watch request: {exc.strerror or exc}.")
            return
        client.setblocking(False)
        upstream.setblocking(False)
        session = _Session(client, upstream)
        selector.register(client, selectors.EVENT_READ, session)
        selector.register(upstream, selectors.EVENT_READ, session)
        log("A client connected; passing on gpsd's position.")

    def from_client(current: _Session) -> None:
        try:
            data = current.client.recv(4096)  # what it sends is ignored
        except BlockingIOError:
            return
        except OSError:
            data = b""
        if not data:
            end(current, "The client disconnected")

    def from_gpsd(current: _Session) -> None:
        try:
            data = current.upstream.recv(65536)
        except BlockingIOError:
            return
        except OSError:
            data = b""
        if not data:
            end(current, "gpsd closed the connection")
            return
        for line in current.feed.push(data):
            current.pending += line
            current.sent += 1
        if len(current.pending) > current.PENDING_LIMIT:
            end(current, "The client is not reading")
            return
        flush(current)

    try:
        while stop is None or not stop.is_set():
            events = selector.select(timeout=poll)
            # The current session's events first, then any new connection.
            for key, mask in sorted(events, key=lambda event: event[0].data is None):
                owner: _Session | None = key.data
                if owner is None:
                    accept()
                    continue
                if owner is not session:
                    continue  # left over from a session that has ended
                if key.fileobj is owner.upstream:
                    from_gpsd(owner)
                    continue
                if mask & selectors.EVENT_READ:
                    from_client(owner)
                if session is owner and mask & selectors.EVENT_WRITE:
                    flush(owner)
            current = session
            if (
                current is not None
                and not current.warned
                and current.sent == 0
                and time.monotonic() - current.started > quiet_after
            ):
                current.warned = True
                log(
                    f"gpsd has sent no position with a fix in {quiet_after:g} s; "
                    f"`xgps` shows whether the receiver has one."
                )
    finally:
        if session is not None:
            session.close()
        selector.close()


def instructions(port: int = PORT) -> str:
    return (
        f"Serving gpsd's position as NMEA on {HOST} port {port}, to this machine only.\n"
        f"In QMapShack: Realtime, Add source, GPS TCP/IP; host {HOST}, port {port}.\n"
        f"Ctrl-C stops it. Navit reads gpsd directly and needs none of this."
    )
