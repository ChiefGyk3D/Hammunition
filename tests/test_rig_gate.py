# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The browser-keying gate and the filter it requires.  D-073 §11, ruling 8.

Ruling 8: if a web page's request to ``rigctld`` on loopback can reach the
command parser, put a filter in front of it. Measured against hamlib's dummy
model, such a request can, so the filter (:mod:`hammunition.rigproxy`) is
shipped and this test guards it: with the filter in front, an HTTP request
does not reach ``rigctld``, while a real rig command passes straight through.

Everything here keys nothing real: ``rigctld -m 1`` is hamlib's dummy model on
an ephemeral loopback port, and ``t`` only *reads* PTT.
"""

from __future__ import annotations

import contextlib
import shutil
import socket
import subprocess
import threading
import time

import pytest

from hammunition.rigproxy import serve

pytestmark = pytest.mark.skipif(
    shutil.which("rigctld") is None, reason="hamlib (rigctld) is not installed"
)


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = int(s.getsockname()[1])
    s.close()
    return port


def _wait(port: int) -> None:
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            return
        except OSError:
            time.sleep(0.05)
    raise AssertionError("port never came up")


def _send(port: int, data: bytes, close_after: float = 0.1) -> None:
    conn = socket.create_connection(("127.0.0.1", port), timeout=2)
    conn.sendall(data)
    time.sleep(close_after)
    conn.close()


def _ptt(port: int) -> bytes:
    conn = socket.create_connection(("127.0.0.1", port), timeout=2)
    conn.sendall(b"t\n")
    time.sleep(0.2)
    conn.settimeout(0.3)
    out = b""
    with contextlib.suppress(OSError):
        while chunk := conn.recv(4096):
            out += chunk
    conn.close()
    return out


def _ptt_within(port: int, want: bytes, seconds: float) -> bool:
    """Poll PTT for *seconds*; True as soon as it reads *want*.

    A single read is not enough: rigctld takes a second or more to work
    through the lines of a rejected HTTP request before it would act on any
    that followed, so a short settle hides the hazard this guards against.
    """
    deadline = time.time() + seconds
    while time.time() < deadline:
        if _ptt(port) == want:
            return True
        time.sleep(0.5)
    return False


def test_the_filter_blocks_an_http_request_but_passes_a_real_command() -> None:
    rig_port = _free_port()
    proxy_port = _free_port()
    proc = subprocess.Popen(
        ["rigctld", "-m", "1", "-T", "127.0.0.1", "-t", str(rig_port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait(rig_port)
        ready = threading.Event()
        threading.Thread(
            target=serve, args=(proxy_port, rig_port), kwargs={"ready": ready}, daemon=True
        ).start()
        assert ready.wait(2)

        # An HTTP POST whose body is the keying line, through the filter: the
        # filter drops the connection, so nothing of it reaches rigctld. PTT
        # stays 0 across a long window (not a single early read).
        body = b"T 1\n" * 40
        request = (
            b"POST / HTTP/1.1\r\nHost: 127.0.0.1\r\n"
            b"Content-Type: text/plain\r\nContent-Length: %d\r\n\r\n" % len(body)
        ) + body
        _send(proxy_port, request)
        assert not _ptt_within(proxy_port, b"1\n", 15.0), "the filter let an HTTP request key PTT"

        # A real rig command, through the same filter, reaches rigctld and keys
        # the dummy — the filter is transparent to a genuine client.
        _send(proxy_port, b"T 1\n", close_after=0.3)
        assert _ptt_within(proxy_port, b"1\n", 5.0), "the filter blocked a real command"
    finally:
        proc.terminate()
        proc.wait()
