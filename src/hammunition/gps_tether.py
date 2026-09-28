# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The GPS tether: gpsd's NMEA, served on loopback for QMapShack.  D-061.

QMapShack has no gpsd client. Its *Realtime -> GPS Tether* reads NMEA
(RMC and GGA) from a TCP host, so the ``gps-tether`` launcher runs
``gpspipe -r`` -- gpsd's raw NMEA -- behind ``socat``, listening on
127.0.0.1 port 10110, the conventional NMEA-0183 port, and nowhere else: a
position is where the operator is, and it is not served to the network.
One client at a time (``max-children=1``); a new connection gets a fresh
``gpspipe``. It runs only while the operator runs it, in a terminal, and
stops with Ctrl-C; nothing is installed as a service. Navit needs none of
this: it reads gpsd itself.
"""

from __future__ import annotations

HOST = "127.0.0.1"
PORT = 10110
SOURCE = "gpspipe -r"


def tether_argv(*, port: int = PORT, source: str = SOURCE) -> list[str]:
    """The fixed argv; *source* is a parameter for the tests only, and may
    hold no comma (socat's option separator)."""
    if "," in source:
        raise ValueError(f"{source!r}: socat would read the comma as an option separator")
    return [
        "socat",
        f"TCP-LISTEN:{port},bind={HOST},reuseaddr,fork,max-children=1",
        f"EXEC:{source}",
    ]


def instructions(port: int = PORT) -> str:
    return (
        f"Serving gpsd's NMEA on {HOST} port {port}, to this machine only.\n"
        f"In QMapShack: Realtime, then GPS Tether; host {HOST}, port {port}.\n"
        f"Ctrl-C stops it. Navit reads gpsd directly and needs none of this."
    )
