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

It listens on 127.0.0.1 port 10110, the conventional NMEA-0183 port, or
another port the operator names, and on loopback only whatever the port: a
position is where the operator is, it is served without authentication, and
it is not served to the network. Another machine reaches it through
``ssh -L``. gpsd may be on this machine or another (a Pi, a phone, a shack
computer). Any number of clients may connect at once, and each receives
every sentence (fan-out): one gpsd watch is opened when the first client
connects, shared while any is connected, and closed when the last leaves,
so every client gets the same bytes and gpsd is not watched while nobody
listens. A client that stops reading is dropped alone. It runs only while
the operator runs it, in a terminal, and stops with Ctrl-C; nothing is
installed as a service, nothing runs as root, and it is the standard
library only. Navit needs none of this: it reads gpsd itself.
"""

from __future__ import annotations

import ipaddress
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
    "gpsd_address",
    "instructions",
    "listen",
    "sentences",
    "serve",
    "serve_port",
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


def _port_number(text: str) -> int | None:
    """*text* as a port number, or None; digits only, no sign or spaces."""
    return int(text) if text.isascii() and text.isdigit() else None


def serve_port(text: str) -> int:
    """``--port``: 1024 to 65535, refused by name otherwise.

    Below 1024 only root may bind, and the tether never runs as root.
    """
    stripped = text.strip()
    number = _port_number(stripped.removeprefix("-"))
    if number is None:
        raise ValueError(f"--port {text}: not a number; give a port from 1024 to 65535")
    if stripped.startswith("-") or number < 1024:
        raise ValueError(
            f"--port {text}: below 1024, where only root may listen, and the tether "
            f"never runs as root; give a port from 1024 to 65535"
        )
    if number > 65535:
        raise ValueError(
            f"--port {text}: above 65535, the highest TCP port; give a port from 1024 to 65535"
        )
    return number


def gpsd_address(text: str) -> tuple[str, int]:
    """``--gpsd HOST[:PORT]``: a host name, an IPv4 address, or an IPv6
    address in brackets, and gpsd's port, 2947 when none is given."""
    where = text.strip()
    rest = ""
    if where.startswith("["):
        close = where.find("]")
        if close == -1:
            raise ValueError(f"--gpsd {text}: an IPv6 address opened with [ is closed with ]")
        host, rest = where[1:close], where[close + 1 :]
        if not host:
            raise ValueError(f"--gpsd {text}: needs a host, as HOST or HOST:PORT")
        try:
            ipaddress.IPv6Address(host)
        except ValueError:
            raise ValueError(
                f"--gpsd {text}: {host} is not an IPv6 address; brackets are for one"
            ) from None
        if rest and not rest.startswith(":"):
            raise ValueError(f"--gpsd {text}: after ] comes nothing, or :PORT")
    elif where.count(":") > 1:
        raise ValueError(f"--gpsd {text}: an IPv6 address goes in brackets, as [::1] or [::1]:2947")
    else:
        host, colon, port_text = where.partition(":")
        rest = colon + port_text
        if not host:
            raise ValueError(f"--gpsd {text!r}: needs a host, as HOST or HOST:PORT")
        if any(char.isspace() for char in host):
            raise ValueError(f"--gpsd {text!r}: a host name has no whitespace")
    if not rest:
        return host, GPSD[1]
    number = _port_number(rest[1:])
    if number is None:
        raise ValueError(f"--gpsd {text}: {rest[1:]!r} is not a port number")
    if not 1 <= number <= 65535:
        raise ValueError(f"--gpsd {text}: gpsd's port is 1 to 65535")
    return host, number


def _where(address: tuple[str, int]) -> str:
    """``host port N``, an IPv6 address in brackets."""
    host, port = address
    return f"[{host}] port {port}" if ":" in host else f"{host} port {port}"


def listen(port: int = PORT) -> socket.socket:
    """The listening socket, on 127.0.0.1 only; *port* 0 is for the tests."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((HOST, port))
        listener.listen(8)
    except OSError:
        listener.close()
        raise
    return listener


class _Client:
    """One NMEA client. What it has not yet taken waits in :attr:`pending`;
    the loop never blocks on a send, and a client that lets more than
    :attr:`PENDING_LIMIT` pile up has stopped reading and is dropped."""

    PENDING_LIMIT = 64 * 1024

    def __init__(self, sock: socket.socket) -> None:
        self.sock = sock
        self.pending = b""

    def gone(self) -> bool:
        """Whether the client has closed, asked without consuming anything."""
        try:
            return self.sock.recv(1, socket.MSG_PEEK | socket.MSG_DONTWAIT) == b""
        except BlockingIOError:
            return False
        except OSError:
            return True


class _Upstream:
    """The one gpsd watch every connected client shares."""

    def __init__(self, sock: socket.socket) -> None:
        self.sock = sock
        self.feed = Feed()
        self.started = time.monotonic()
        self.sent = 0
        self.warned = False


def _connected(count: int) -> str:
    return f"{count} connected"


def serve(
    listener: socket.socket,
    *,
    gpsd: tuple[str, int] = GPSD,
    stop: threading.Event | None = None,
    log: Callable[[str], None] = print,
    poll: float = 0.5,
    quiet_after: float = 10.0,
) -> None:
    """Serve NMEA to every connected client until *stop* is set (or Ctrl-C).

    *log* gets one line per event the operator should see: a client served
    or gone, with how many are connected; a client dropped for not reading;
    gpsd unreachable, gone or silent.

    One gpsd connection is opened when the first client connects, shared by
    every client while any is connected, and closed when the last one
    leaves: each client gets the same sentences, and gpsd is watched only
    while someone is listening. If gpsd closes it, every client is closed
    and the next to connect opens a fresh watch.

    Every registration carries the object it belongs to, and an event for
    one that has ended is dropped: a file descriptor number reused by the
    next client can never be mistaken for the last one. In each batch of
    events the clients' and gpsd's are handled before a new connection, and
    a new connection first drops any client that has already closed, so a
    client that left is never counted as connected.
    """
    selector = selectors.DefaultSelector()
    listener.setblocking(False)
    selector.register(listener, selectors.EVENT_READ, None)
    clients: list[_Client] = []
    upstream: _Upstream | None = None

    def close_upstream() -> None:
        nonlocal upstream
        if upstream is not None:
            selector.unregister(upstream.sock)
            upstream.sock.close()
            upstream = None

    def drop(client: _Client, why: str) -> None:
        if client not in clients:
            return
        clients.remove(client)
        selector.unregister(client.sock)
        client.sock.close()
        if not clients:
            close_upstream()
        log(f"{why}; {_connected(len(clients))}.")

    def want_write(client: _Client) -> None:
        events = selectors.EVENT_READ | (selectors.EVENT_WRITE if client.pending else 0)
        selector.modify(client.sock, events, client)

    def flush(client: _Client) -> None:
        try:
            while client.pending:
                count = client.sock.send(client.pending)
                client.pending = client.pending[count:]
        except BlockingIOError:
            pass
        except OSError:
            drop(client, "A client disconnected")
            return
        if len(client.pending) > client.PENDING_LIMIT:
            drop(client, "A client is not reading and was dropped")
            return
        want_write(client)

    def open_upstream() -> bool:
        nonlocal upstream
        try:
            sock = socket.create_connection(gpsd, timeout=5)
        except OSError as exc:
            if gpsd[0] in ("127.0.0.1", "::1", "localhost"):
                hint = "Is gpsd running? `systemctl status gpsd` says."
            else:
                hint = (
                    "Is gpsd running there, listening beyond its own loopback, "
                    "and reachable from here?"
                )
            log(f"cannot reach gpsd at {_where(gpsd)}: {exc.strerror or exc}. {hint}")
            return False
        try:
            sock.sendall(WATCH)
        except OSError as exc:
            sock.close()
            log(f"gpsd refused the watch request: {exc.strerror or exc}.")
            return False
        sock.setblocking(False)
        upstream = _Upstream(sock)
        selector.register(sock, selectors.EVENT_READ, upstream)
        return True

    def accept() -> None:
        try:
            sock, _ = listener.accept()
        except BlockingIOError:
            return
        for client in list(clients):
            if client.gone():
                drop(client, "A client disconnected")
        if upstream is None and not open_upstream():
            sock.close()
            return
        sock.setblocking(False)
        client = _Client(sock)
        clients.append(client)
        selector.register(sock, selectors.EVENT_READ, client)
        log(f"A client connected; {_connected(len(clients))}, each sent gpsd's position.")

    def from_client(client: _Client) -> None:
        try:
            data = client.sock.recv(4096)  # what it sends is ignored
        except BlockingIOError:
            return
        except OSError:
            data = b""
        if not data:
            drop(client, "A client disconnected")

    def from_gpsd(current: _Upstream) -> None:
        try:
            data = current.sock.recv(65536)
        except BlockingIOError:
            return
        except OSError:
            data = b""
        if not data:
            close_upstream()
            for client in list(clients):
                clients.remove(client)
                selector.unregister(client.sock)
                client.sock.close()
            log("gpsd closed the connection; every client was closed, and may reconnect.")
            return
        lines = current.feed.push(data)
        if not lines:
            return
        current.sent += len(lines)
        batch = b"".join(lines)
        for client in list(clients):
            client.pending += batch
            flush(client)

    try:
        while stop is None or not stop.is_set():
            events = selector.select(timeout=poll)
            # Clients' and gpsd's events first, then any new connection.
            for key, mask in sorted(events, key=lambda event: event[0].data is None):
                owner = key.data
                if owner is None:
                    accept()
                elif isinstance(owner, _Upstream):
                    if owner is upstream:
                        from_gpsd(owner)
                elif owner in clients:
                    if mask & selectors.EVENT_READ:
                        from_client(owner)
                    if owner in clients and mask & selectors.EVENT_WRITE:
                        flush(owner)
            current = upstream
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
        for client in clients:
            client.sock.close()
        if upstream is not None:
            upstream.sock.close()
        selector.close()


def instructions(port: int = PORT, *, gpsd: tuple[str, int] = GPSD) -> str:
    return (
        f"Serving gpsd's position as NMEA on {HOST} port {port}, to this machine only.\n"
        f"In QMapShack: Realtime, Add source, GPS TCP/IP; host {HOST}, port {port}.\n"
        f"Reading gpsd at {_where(gpsd)}. Any number of NMEA programs may connect at once.\n"
        f"Options: --gpsd HOST[:PORT] for a gpsd on another machine, "
        f"--port N if {port} is taken.\n"
        f"Ctrl-C stops it. Navit reads gpsd directly and needs none of this."
    )
