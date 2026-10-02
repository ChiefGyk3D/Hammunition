# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""What the engine must agree on with the GPS tether, and nothing else.  D-071 note.

The tether is its own project (hammunition-gps-tether, installed by the
``gps-tether`` catalog unit). The engine runs none of its code; it only shares
these values with it. Each is copied from the tether's source, and
``tests/test_tether_contract.py`` asserts they still equal it:

- ``POSITION_PORT`` and ``NMEA_PORT``: ``hammunition_gps_tether/tether.py``
  (``POSITION_PORT``, ``PORT``);
- the GeoClue four: ``hammunition_gps_tether/geoclue.py`` (``DROPIN``,
  ``HEADER``, ``SOCKET``, ``GROUP``).
"""

from __future__ import annotations

__all__ = [
    "GEOCLUE_DROPIN",
    "GEOCLUE_GROUP",
    "GEOCLUE_HEADER",
    "GEOCLUE_SOCKET",
    "NMEA_PORT",
    "POSITION_PORT",
]

NMEA_PORT = 10110
"""The conventional NMEA-0183 port the tether serves QMapShack on, loopback only."""

POSITION_PORT = 10111
"""Where the tether's ``GET /position`` event stream is, loopback only."""

GEOCLUE_DROPIN = "/etc/geoclue/conf.d/90-hammunition-gps.conf"
GEOCLUE_HEADER = "# Written by `hammunition hardware apply` (D-069)."
GEOCLUE_SOCKET = "/run/hammunition-gps/nmea.sock"
GEOCLUE_GROUP = "geoclue"
