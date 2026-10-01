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

With ``--nmea-socket PATH`` (D-069) it also listens on a unix stream socket,
mode 0660, in the group GeoClue runs as, and serves it exactly what it serves
TCP: the same sentences from the same gpsd watch, with the same rules for a
client that stops reading or goes. GeoClue's network-NMEA source reads it, and
CoMaps reads GeoClue. ``hardware apply`` makes the setgid directory the socket
lives in; the socket is removed when the tether stops.
"""

from __future__ import annotations

import contextlib
import errno
import grp
import ipaddress
import json
import math
import os
import selectors
import socket
import stat
import threading
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

__all__ = [
    "GPSD",
    "HOST",
    "PORT",
    "POSITION_PATH",
    "POSITION_PORT",
    "WATCH",
    "Feed",
    "checksum",
    "close_unix",
    "gpsd_address",
    "instructions",
    "listen",
    "listen_unix",
    "sentences",
    "serve",
    "serve_port",
]

HOST = "127.0.0.1"
PORT = 10110
#: The browser map's position stream (D-071): Server-Sent Events on HTTP.
POSITION_PORT = 10111
POSITION_PATH = "/position"
#: The most of a request head the position listener reads before it gives up.
REQUEST_LIMIT = 8 * 1024
#: Seconds a connection to the position listener has to send its request.
REQUEST_DEADLINE = 5.0
#: Unfinished requests held at once; a connection beyond it is closed at once.
REQUEST_CAP = 16
GPSD = ("127.0.0.1", 2947)
#: The unix socket's mode: its owner and GeoClue's group, nobody else (D-069).
SOCKET_MODE = 0o660
#: The longest path a unix socket can have: sun_path's 108 bytes, less the NUL.
UNIX_PATH_MAX = 107
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
        #: The latest fix, as the browser map's event carries it (D-071).
        self.position: dict[str, Any] | None = None

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
            out = sentences(message, satellites=self.satellites, hdop=self.hdop)
            if out:
                when = message.get("time")
                self.position = {
                    "lat": float(message["lat"]),
                    "lon": float(message["lon"]),
                    "mode": message["mode"],
                    "time": when if isinstance(when, str) else None,
                }
            return out
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


def serve_port(text: str, *, flag: str = "--port") -> int:
    """``--port`` (or *flag*): 1024 to 65535, refused by name otherwise.

    Below 1024 only root may bind, and the tether never runs as root.
    """
    stripped = text.strip()
    number = _port_number(stripped.removeprefix("-"))
    if number is None:
        raise ValueError(f"{flag} {text}: not a number; give a port from 1024 to 65535")
    if stripped.startswith("-") or number < 1024:
        raise ValueError(
            f"{flag} {text}: below 1024, where only root may listen, and the tether "
            f"never runs as root; give a port from 1024 to 65535"
        )
    if number > 65535:
        raise ValueError(
            f"{flag} {text}: above 65535, the highest TCP port; give a port from 1024 to 65535"
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


def _clear_stale(path: str) -> None:
    """Remove a socket nobody is listening on, as a crashed tether leaves;
    refuse a live one, and anything at *path* that is not a socket."""
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return
    if not stat.S_ISSOCK(st.st_mode):
        raise ValueError(f"--nmea-socket {path}: it exists and is not a socket; it is left alone")
    # The probe is a real connection: a live tether on the other end logs it as a
    # client that came and went, and that one line is the price of not removing
    # a socket somebody is serving.
    probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    probe.settimeout(1)
    try:
        probe.connect(path)
    except ConnectionRefusedError:
        os.unlink(path)
        return
    finally:
        probe.close()
    raise OSError(errno.EADDRINUSE, f"another tether is serving {path}")


def listen_unix(
    path: str, *, group: str = "geoclue", log: Callable[[str], None] = print
) -> tuple[socket.socket, tuple[int, int]]:
    """A unix stream listener at *path*, mode 0660, and the (device, inode) it
    was bound as, for :func:`close_unix`.  D-069.

    The group is the directory's when that directory is setgid *group*, as the
    one ``hardware apply`` makes is; otherwise the socket is moved to *group* if
    this account may, and when it may not, or *group* does not exist, *log*
    says GeoClue cannot read it. The directory, not the socket's brief default
    mode, is what keeps other accounts out while it is created.
    """
    if not os.path.isabs(path):
        raise ValueError(f"--nmea-socket {path}: give an absolute path")
    size = len(os.fsencode(path))
    if size > UNIX_PATH_MAX:
        raise ValueError(
            f"--nmea-socket {path}: {size} bytes, and a unix socket path is at most {UNIX_PATH_MAX}"
        )
    _clear_stale(path)
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    bound = False
    try:
        listener.bind(path)
        bound = True
        os.chmod(path, SOCKET_MODE)
        st = os.lstat(path)
        listener.listen(8)
    except OSError:
        listener.close()
        if bound:
            with contextlib.suppress(OSError):
                os.unlink(path)
        raise
    try:
        wanted: int | None = grp.getgrnam(group).gr_gid
    except KeyError:
        wanted = None
    mine = _group_name(st.st_gid)
    if wanted is None:
        log(
            f"No `{group}` group here, so {path} keeps your group ({mine}) and GeoClue "
            f"cannot read it. Is GeoClue (geoclue-2.0) installed?"
        )
    elif st.st_gid != wanted:
        try:
            os.chown(path, -1, wanted)
        except PermissionError:
            log(
                f"{path} is in group {mine}, not {group}, so GeoClue cannot read it: its "
                f"directory is not the setgid one `hammunition hardware apply` makes."
            )
    return listener, (st.st_dev, st.st_ino)


def _group_name(gid: int) -> str:
    try:
        return grp.getgrgid(gid).gr_name
    except KeyError:
        return str(gid)


def close_unix(listener: socket.socket, path: str, identity: tuple[int, int]) -> None:
    """Close *listener* and remove its socket file, only if *path* is still the
    inode it bound: another tether's socket there is left alone."""
    listener.close()
    with contextlib.suppress(OSError):
        st = os.lstat(path)
        if stat.S_ISSOCK(st.st_mode) and (st.st_dev, st.st_ino) == identity:
            os.unlink(path)


def position_event(position: Mapping[str, Any]) -> bytes:
    """One Server-Sent Event carrying *position* as JSON."""
    return b"data: " + json.dumps(dict(position)).encode("ascii") + b"\n\n"


def _loopback_origin(origin: str) -> bool:
    """``http://127.0.0.1[:port]`` or ``http://localhost[:port]``: a page this
    machine serves to itself. Any other origin is a web page from elsewhere."""
    for base in (f"http://{HOST}", "http://localhost"):
        if origin == base:
            return True
        if origin.startswith(base + ":") and origin[len(base) + 1 :].isdigit():
            return True
    return False


def position_response(head: bytes, port: int) -> tuple[bytes, bool]:
    """(what to send, whether it starts an event stream) for one request
    *head* to the position listener on *port*.

    Only ``GET /position`` is answered. A ``Host`` other than
    ``127.0.0.1:port`` or ``localhost:port`` is refused, so a web page whose
    name an attacker points at 127.0.0.1 (DNS rebinding) cannot read it; a
    request carrying a non-loopback ``Origin`` is refused, and
    ``Access-Control-Allow-Origin`` is sent only to a loopback one, so no
    page on the internet can read the stream from the operator's own
    browser. The position is where the operator is (D-061, D-071).
    """

    def reply(status: str, body: str) -> tuple[bytes, bool]:
        data = body.encode("ascii")
        return (
            f"HTTP/1.1 {status}\r\nContent-Type: text/plain\r\n"
            f"Content-Length: {len(data)}\r\nConnection: close\r\n\r\n".encode("ascii")
            + data,
            False,
        )

    text = head.decode("latin-1")
    first, _, rest = text.partition("\r\n")
    parts = first.split(" ")
    if len(parts) != 3 or not parts[2].startswith("HTTP/1."):
        return reply("400 Bad Request", "bad request\n")
    method, target, _ = parts
    headers: dict[str, str] = {}
    for line in rest.split("\r\n"):
        name, colon, value = line.partition(":")
        if colon:
            headers[name.strip().lower()] = value.strip()
    if headers.get("host", "").lower() not in {f"{HOST}:{port}", f"localhost:{port}"}:
        return reply("403 Forbidden", "refused: ask for 127.0.0.1 or localhost\n")
    origin = headers.get("origin")
    if origin is not None and not _loopback_origin(origin):
        return reply("403 Forbidden", "refused: a page from elsewhere may not read the position\n")
    if origin is None and "text/event-stream" not in headers.get("accept", ""):
        # An <img> or <script> on any web page sends no Origin; it could not
        # read the stream, but it would hold gpsd watched. The map page's
        # EventSource always sends its Origin; `curl -H 'Accept:
        # text/event-stream'` is the way to test from a terminal.
        return reply(
            "403 Forbidden",
            "refused: ask as an event stream (Accept: text/event-stream) or from a loopback page\n",
        )
    if method != "GET":
        return reply("405 Method Not Allowed", "GET only\n")
    if target.split("?", 1)[0] != POSITION_PATH:
        return reply("404 Not Found", "not found\n")
    allow = f"Access-Control-Allow-Origin: {origin}\r\nVary: Origin\r\n" if origin else ""
    return (
        (
            "HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n"
            "Cache-Control: no-store\r\nX-Content-Type-Options: nosniff\r\n"
            f"{allow}\r\n"
        ).encode("ascii")
        + b": gpsd's position, from hammunition maps gps-tether\n\n",
        True,
    )


class _Request:
    """A connection to the position listener that has not finished its request."""

    def __init__(self, sock: socket.socket) -> None:
        self.sock = sock
        self.head = b""
        self.since = time.monotonic()


class _Client:
    """One NMEA client. What it has not yet taken waits in :attr:`pending`;
    the loop never blocks on a send, and a client that lets more than
    :attr:`PENDING_LIMIT` pile up has stopped reading and is dropped."""

    PENDING_LIMIT = 64 * 1024

    def __init__(self, sock: socket.socket, *, events: bool = False) -> None:
        self.sock = sock
        self.pending = b""
        #: A browser map's event stream (D-071), sent positions, not NMEA.
        self.events = events

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
    http: socket.socket | None = None,
    unix: socket.socket | None = None,
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

    *http*, when given, is a second loopback listener for the browser map
    (D-071): a ``GET /position`` there (:func:`position_response`) becomes a
    client like any other, sent one Server-Sent Event per fix instead of NMEA,
    and counted in the same fan-out, so gpsd is watched while the page is open.

    *unix*, when given, is a unix stream listener (:func:`listen_unix`, D-069)
    whose clients are NMEA clients exactly like TCP's: the same sentences, the
    same fan-out, dropped for the same reasons.
    """
    selector = selectors.DefaultSelector()
    listener.setblocking(False)
    selector.register(listener, selectors.EVENT_READ, None)
    http_port = 0
    if http is not None:
        http.setblocking(False)
        http_port = http.getsockname()[1]
        selector.register(http, selectors.EVENT_READ, "http")
    if unix is not None:
        unix.setblocking(False)
        selector.register(unix, selectors.EVENT_READ, "unix")
    requests: list[_Request] = []
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

    def admit(
        sock: socket.socket, *, events: bool = False, greeting: bytes = b"", what: str = ""
    ) -> None:
        for client in list(clients):
            if client.gone():
                drop(client, "A client disconnected")
        if upstream is None and not open_upstream():
            if events:
                # Say so, or the page would read it as no tether at all.
                with contextlib.suppress(OSError):
                    sock.setblocking(True)
                    sock.settimeout(1)
                    sock.sendall(
                        b"HTTP/1.1 503 Service Unavailable\r\nContent-Type: text/plain\r\n"
                        b"Content-Length: 24\r\nConnection: close\r\n\r\n"
                        b"gpsd cannot be reached\r\n"
                    )
            sock.close()
            return
        sock.setblocking(False)
        client = _Client(sock, events=events)
        clients.append(client)
        selector.register(sock, selectors.EVENT_READ, client)
        what = what or ("A map page" if events else "A client")
        log(f"{what} connected; {_connected(len(clients))}, each sent gpsd's position.")
        if greeting:
            client.pending += greeting
            flush(client)

    def accept(source: socket.socket = listener, what: str = "") -> None:
        try:
            sock, _ = source.accept()
        except BlockingIOError:
            return
        except OSError as exc:  # out of descriptors, say: the tether keeps running
            log(f"could not accept a connection: {exc.strerror or exc}")
            return
        admit(sock, what=what)

    def accept_http() -> None:
        assert http is not None
        try:
            sock, _ = http.accept()
        except BlockingIOError:
            return
        except OSError as exc:
            log(f"could not accept a connection: {exc.strerror or exc}")
            return
        if len(requests) >= REQUEST_CAP:
            sock.close()
            return
        sock.setblocking(False)
        request = _Request(sock)
        requests.append(request)
        selector.register(sock, selectors.EVENT_READ, request)

    def end_request(request: _Request) -> None:
        requests.remove(request)
        selector.unregister(request.sock)

    def from_request(request: _Request) -> None:
        try:
            data = request.sock.recv(4096)
        except BlockingIOError:
            return
        except OSError:
            data = b""
        if not data:
            end_request(request)
            request.sock.close()
            return
        request.head += data
        if b"\r\n\r\n" not in request.head:
            if len(request.head) > REQUEST_LIMIT:
                end_request(request)
                request.sock.close()
            return
        end_request(request)
        answer, stream = position_response(request.head.split(b"\r\n\r\n", 1)[0], http_port)
        if not stream:
            with contextlib.suppress(OSError):
                request.sock.setblocking(True)
                request.sock.settimeout(1)
                request.sock.sendall(answer)
            request.sock.close()
            return
        admit(request.sock, events=True, greeting=answer)

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
        position = current.feed.position
        event = position_event(position) if position is not None else b""
        for client in list(clients):
            client.pending += event if client.events else batch
            flush(client)

    try:
        while stop is None or not stop.is_set():
            events = selector.select(timeout=poll)
            # Clients' and gpsd's events first, then any new connection.
            for key, mask in sorted(
                events, key=lambda event: event[0].data in (None, "http", "unix")
            ):
                owner = key.data
                if owner is None:
                    accept()
                elif owner == "unix":
                    assert unix is not None
                    accept(unix, "A client on the socket")
                elif owner == "http":
                    accept_http()
                elif isinstance(owner, _Request):
                    if owner in requests:
                        from_request(owner)
                elif isinstance(owner, _Upstream):
                    if owner is upstream:
                        from_gpsd(owner)
                elif owner in clients:
                    if mask & selectors.EVENT_READ:
                        from_client(owner)
                    if owner in clients and mask & selectors.EVENT_WRITE:
                        flush(owner)
            now = time.monotonic()
            for request in [r for r in requests if now - r.since > REQUEST_DEADLINE]:
                end_request(request)
                request.sock.close()
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
        for request in requests:
            request.sock.close()
        for client in clients:
            client.sock.close()
        if upstream is not None:
            upstream.sock.close()
        selector.close()


def instructions(
    port: int = PORT,
    *,
    gpsd: tuple[str, int] = GPSD,
    position_port: int | None = POSITION_PORT,
    nmea_socket: str | None = None,
) -> str:
    page = (
        f"The offline browser map (`hammunition reference serve`) reads it from "
        f"http://{HOST}:{position_port}{POSITION_PATH}.\n"
        if position_port is not None
        else ""
    )
    if nmea_socket is not None:
        page += (
            f'Serving it to GeoClue on {nmea_socket} too, for CoMaps\' "you are here" (D-069).\n'
        )
    return (
        f"Serving gpsd's position as NMEA on {HOST} port {port}, to this machine only.\n"
        f"In QMapShack: Realtime, Add source, GPS TCP/IP; host {HOST}, port {port}.\n"
        f"{page}"
        f"Reading gpsd at {_where(gpsd)}. Any number of NMEA programs may connect at once.\n"
        f"Options: --gpsd HOST[:PORT] for a gpsd on another machine, "
        f"--port N if {port} is taken, --position-port N for the map's.\n"
        f"Ctrl-C stops it. Navit reads gpsd directly and needs none of this."
    )
