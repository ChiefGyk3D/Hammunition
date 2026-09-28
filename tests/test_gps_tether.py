# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The GPS tether binds loopback only.  D-061."""

from __future__ import annotations

import shutil
import socket
import subprocess
import time
from pathlib import Path

import pytest

from hammunition.gps_tether import HOST, PORT, instructions, tether_argv


def test_the_argv_listens_on_loopback_port_10110_only() -> None:
    argv = tether_argv()
    assert argv == [
        "socat",
        "TCP-LISTEN:10110,bind=127.0.0.1,reuseaddr,fork,max-children=1",
        "EXEC:gpspipe -r",
    ]
    assert "0.0.0.0" not in " ".join(argv)
    assert (HOST, PORT) == ("127.0.0.1", 10110)


def test_a_source_with_a_comma_is_refused() -> None:
    with pytest.raises(ValueError, match="comma"):
        tether_argv(source="printf a,b")


def test_the_instructions_name_the_host_and_port() -> None:
    text = instructions()
    assert "127.0.0.1" in text and "10110" in text and "GPS Tether" in text


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
        return port


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


@pytest.mark.skipif(shutil.which("socat") is None, reason="socat is not installed here")
def test_socat_really_serves_the_source_on_loopback_and_nowhere_else() -> None:
    port = _free_port()
    child = subprocess.Popen(tether_argv(port=port, source="echo GPRMC-TEST"))
    try:
        for _ in range(50):
            if _listening_addresses(port):
                break
            time.sleep(0.1)
        assert _listening_addresses(port) == {"0100007F"}, "127.0.0.1, little-endian hex"
        with socket.create_connection(("127.0.0.1", port), timeout=5) as client:
            assert client.makefile().readline().strip() == "GPRMC-TEST"
    finally:
        child.terminate()
        child.wait(timeout=5)
