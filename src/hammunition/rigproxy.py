# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""A loopback filter in front of ``rigctld``.  D-073 §11, ruling 8.

``rigctld`` reads newline-separated commands, and a web page can make the
browser open a connection to ``127.0.0.1`` and send newline-separated text.
Measured against hamlib's dummy model, such a request can reach the command
parser. ``rigctld`` has no password of its own (its ``-A`` option is "not
implemented"), so ruling 8 is: put a filter in front of it.

This is that filter — a few lines of standard library, no configuration. It
binds the shared loopback port and forwards every byte, in both directions,
unchanged, to ``rigctld`` on another loopback port — **except** that it drops,
unread, any connection whose first line is an HTTP request line. A real rig
client (WSJT-X, fldigi, ``rigctl``) never sends one; only something speaking
HTTP does. It parses nothing else and makes no decision beyond that one.

It is run by the operator's own ``rig-service`` as a second user service. It
needs no privilege and binds loopback only.
"""

from __future__ import annotations

import argparse
import contextlib
import re
import socket
import threading

__all__ = ["looks_like_http", "main", "serve"]

#: An HTTP request line: a method token, a space, a target, a space, and
#: ``HTTP/1.x``. A rig command is a single letter or short word and never
#: matches this, so a connection whose first line does is not a rig client.
_HTTP_REQUEST_LINE = re.compile(rb"^[A-Z]{3,10} \S+ HTTP/1\.[01]\r?\n")

#: How many bytes to read while deciding. A request line longer than this is
#: still not a rig command, so a connection that has sent this many bytes with
#: no newline is dropped too.
_PEEK = 8192


def looks_like_http(first_bytes: bytes) -> bool:
    """True when *first_bytes* begin an HTTP request — the one thing dropped.

    True also for a first line that runs past :data:`_PEEK` with no newline: a
    rig command is short, so anything that long is not one.
    """
    if _HTTP_REQUEST_LINE.match(first_bytes):
        return True
    return b"\n" not in first_bytes and len(first_bytes) >= _PEEK


def _pump(src: socket.socket, dst: socket.socket) -> None:
    try:
        while True:
            chunk = src.recv(65536)
            if not chunk:
                break
            dst.sendall(chunk)
    except OSError:
        pass
    finally:
        for sock in (src, dst):
            with contextlib.suppress(OSError):
                sock.shutdown(socket.SHUT_RDWR)


def _handle(client: socket.socket, target_host: str, target_port: int) -> None:
    client.settimeout(5.0)
    first = b""
    try:
        while b"\n" not in first and len(first) < _PEEK:
            chunk = client.recv(_PEEK - len(first))
            if not chunk:
                break
            first += chunk
            if _HTTP_REQUEST_LINE.match(first):
                break
    except OSError:
        client.close()
        return
    if looks_like_http(first):
        # An HTTP request: drop it, unread. Nothing of it reaches rigctld.
        client.close()
        return
    try:
        upstream = socket.create_connection((target_host, target_port), timeout=5.0)
    except OSError:
        client.close()
        return
    client.settimeout(None)
    if first:
        try:
            upstream.sendall(first)
        except OSError:
            client.close()
            upstream.close()
            return
    threading.Thread(target=_pump, args=(client, upstream), daemon=True).start()
    _pump(upstream, client)
    client.close()
    upstream.close()


def serve(
    listen_port: int,
    target_port: int,
    *,
    host: str = "127.0.0.1",
    ready: threading.Event | None = None,
) -> None:
    """Accept on ``host:listen_port`` and forward to ``host:target_port``.

    Loopback only. ``ready`` (if given) is set once the socket is bound and
    listening — the tests wait on it instead of sleeping.
    """
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, listen_port))
    server.listen(16)
    if ready is not None:
        ready.set()
    while True:
        try:
            client, _addr = server.accept()
        except OSError:
            break
        threading.Thread(target=_handle, args=(client, host, target_port), daemon=True).start()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="hammunition-rig-proxy",
        description="Loopback filter in front of rigctld: drops HTTP, forwards everything else.",
    )
    parser.add_argument("--listen", type=int, required=True, help="loopback port to bind")
    parser.add_argument("--target", type=int, required=True, help="rigctld's loopback port")
    args = parser.parse_args(argv)
    if args.listen == args.target:
        parser.error("--listen and --target must differ")
    serve(args.listen, args.target)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
