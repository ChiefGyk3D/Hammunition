# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The browser-keying gate (D-073 §11, ruling 8).

The spec asks one question outright: can a web page's HTTP request to
``rigctld`` on loopback key the transmitter? ``rigctld`` reads
newline-separated commands and a browser's POST body is newline-separated
text, so the question is real. The answer decides whether this sub-project
ships a loopback filter proxy.

Measured here against hamlib's dummy model (``-m 1``) on an ephemeral
loopback port, keying nothing: a browser-shaped HTTP POST, sent as one
write the way a browser's ``fetch``/form actually sends it, leaves PTT
unchanged, because the request line and the CRLF-folded headers never
leave ``rigctld``'s line parser resynchronised onto the body's ``T 1``.
The gate is therefore OPEN and **no proxy is built** (rigctld stays on
4532). The same test is falsified on purpose: a raw ``T 1`` with no
request line keys the dummy, proving the keying path is reached and the
first assertion is not passing for the trivial reason that nothing ever
reaches the parser.

If a future hamlib regresses this — if a browser-shaped POST begins to
key — this test goes red and ruling 8's response (a filter proxy on 4532
with ``rigctld`` moved to 4632) becomes required.
"""

from __future__ import annotations

import shutil
import socket
import subprocess
import time

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("rigctld") is None, reason="hamlib (rigctld) is not installed"
)


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait(port: int) -> None:
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            return
        except OSError:
            time.sleep(0.05)
    raise AssertionError("rigctld never started listening")


def _talk(port: int, data: bytes, settle: float = 0.3) -> bytes:
    conn = socket.create_connection(("127.0.0.1", port), timeout=2)
    conn.sendall(data)
    time.sleep(settle)
    conn.settimeout(0.3)
    out = b""
    try:
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            out += chunk
    except OSError:
        pass
    conn.close()
    return out


def test_browser_post_does_not_key_the_dummy_but_a_raw_command_does() -> None:
    port = _free_port()
    proc = subprocess.Popen(
        ["rigctld", "-m", "1", "-T", "127.0.0.1", "-t", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait(port)

        # A browser-shaped POST whose body is the keying command, sent as one
        # write — the framing a browser controls, not the attacker's JS.
        body = b"T 1\n"
        request = (
            b"POST / HTTP/1.1\r\n"
            b"Host: 127.0.0.1\r\n"
            b"Content-Type: text/plain\r\n"
            b"Content-Length: %d\r\n\r\n" % len(body)
        ) + body
        _talk(port, request, settle=1.0)
        # Gate OPEN: PTT is still 0 after the POST.
        assert _talk(port, b"t\n") == b"0\n"

        # Falsification: a raw command with no request line reaches the parser
        # and keys the dummy, so the assertion above is not passing merely
        # because nothing ever reached the keying path.
        assert b"RPRT 0" in _talk(port, b"T 1\n")
        assert _talk(port, b"t\n") == b"1\n"
    finally:
        proc.terminate()
        proc.wait()
