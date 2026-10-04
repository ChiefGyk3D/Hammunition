# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
import socket

import pytest

from .helpers import PACKAGE_DIR


def test_a_test_cannot_reach_the_network() -> None:
    """The engine's conftest blocks every non-loopback connection for the whole suite."""
    with socket.socket() as sock, pytest.raises(RuntimeError, match="blocked a connection"):
        sock.settimeout(1)
        sock.connect(
            ("93.184.216.34", 80)
        )  # closed on exit: create_connection leaks the socket it failed to connect


def test_the_package_has_no_network_imports() -> None:
    forbidden = (
        "import socket",
        "import urllib",
        "import http",
        "import requests",
        "import ssl",
        "from urllib",
        "from http",
    )
    hits = [
        f"{p.name}: {tok}"
        for p in PACKAGE_DIR.rglob("*.py")
        for tok in forbidden
        if tok in p.read_text()
    ]
    assert hits == [], "the console fetches nothing; the engine does"
