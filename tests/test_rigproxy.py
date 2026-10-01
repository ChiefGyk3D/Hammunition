# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The loopback filter in front of rigctld.  D-073 §11, ruling 8.

Two halves: the pure predicate, and the filter end to end against a plain
echo-ish upstream (no rigctld needed for these). The gate test
(tests/test_rig_gate.py) exercises it against a real dummy rigctld.
"""

from __future__ import annotations

import socket
import threading
import time

from hammunition.rigproxy import looks_like_http, serve


def test_looks_like_http_predicate() -> None:
    assert looks_like_http(b"POST / HTTP/1.1\r\n")
    assert looks_like_http(b"GET /x?y HTTP/1.0\r\n")
    # A rig command is never an HTTP request line.
    assert not looks_like_http(b"T 1\n")
    assert not looks_like_http(b"f\n")
    assert not looks_like_http(b"\\dump_state\n")
    assert not looks_like_http(b"")


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = int(s.getsockname()[1])
    s.close()
    return port


def _echo_upstream(port: int, ready: threading.Event) -> None:
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", port))
    srv.listen(4)
    ready.set()
    conn, _ = srv.accept()
    data = conn.recv(65536)
    conn.sendall(b"got:" + data)
    conn.close()
    srv.close()


def _run_proxy(listen: int, target: int) -> threading.Event:
    ready = threading.Event()
    threading.Thread(
        target=serve, args=(listen, target), kwargs={"ready": ready}, daemon=True
    ).start()
    return ready


def test_a_plain_client_is_forwarded_both_ways() -> None:
    target = _free_port()
    listen = _free_port()
    up_ready = threading.Event()
    threading.Thread(target=_echo_upstream, args=(target, up_ready), daemon=True).start()
    up_ready.wait(2)
    _run_proxy(listen, target).wait(2)

    conn = socket.create_connection(("127.0.0.1", listen), timeout=2)
    conn.sendall(b"T 1\n")
    time.sleep(0.3)
    conn.settimeout(1.0)
    assert conn.recv(4096) == b"got:T 1\n"
    conn.close()


def test_an_http_request_is_dropped_and_never_reaches_upstream() -> None:
    target = _free_port()
    listen = _free_port()
    reached: list[bytes] = []

    def upstream(ready: threading.Event) -> None:
        srv = socket.socket()
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", target))
        srv.listen(4)
        srv.settimeout(1.5)
        ready.set()
        try:
            conn, _ = srv.accept()
            reached.append(conn.recv(65536))
            conn.close()
        except OSError:
            pass
        srv.close()

    up_ready = threading.Event()
    threading.Thread(target=upstream, args=(up_ready,), daemon=True).start()
    up_ready.wait(2)
    _run_proxy(listen, target).wait(2)

    conn = socket.create_connection(("127.0.0.1", listen), timeout=2)
    conn.sendall(b"POST / HTTP/1.1\r\nContent-Length: 4\r\n\r\nT 1\n")
    time.sleep(0.5)
    conn.close()
    time.sleep(0.5)
    # The proxy dropped it: the upstream accepted no bytes from this connection.
    assert reached == [] or reached == [b""]
