# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""doctor's \\dump_state parse, checked against a dummy rigctld.  D-073 §9.

Never a radio and never a real serial port: ``rigctld -m 1`` is hamlib's dummy
model on an ephemeral loopback port, and only read commands are sent.
"""

from __future__ import annotations

import contextlib
import shutil
import socket
import subprocess
import time

import pytest

from hammunition.rig import parse_dump_state_model

pytestmark = pytest.mark.skipif(
    shutil.which("rigctld") is None, reason="hamlib (rigctld) is not installed"
)


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = int(s.getsockname()[1])
    s.close()
    return port


def test_dump_state_reply_yields_the_dummy_model() -> None:
    port = _free_port()
    proc = subprocess.Popen(
        ["rigctld", "-m", "1", "-T", "127.0.0.1", "-t", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(100):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.05)
        conn = socket.create_connection(("127.0.0.1", port), timeout=2)
        conn.sendall(b"\\dump_state\n")
        time.sleep(0.4)
        conn.settimeout(0.4)
        reply = b""
        with contextlib.suppress(OSError):
            while chunk := conn.recv(4096):
                reply += chunk
        conn.close()
        assert parse_dump_state_model(reply.decode(errors="replace")) == 1
    finally:
        proc.terminate()
        proc.wait()


def test_parse_dump_state_handles_an_empty_reply() -> None:
    assert parse_dump_state_model("") is None
