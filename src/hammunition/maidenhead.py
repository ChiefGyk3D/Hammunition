# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""A Maidenhead locator's centre as latitude and longitude.

Written for gpredict's ground-station file (``LAT``/``LON`` in decimal
degrees, north and east positive), which is the first catalog configuration
that needs a position rather than the locator itself. The station stores only
the locator (D-035), so a position is *derived* from it, never stored and
never asked for separately.

The answer is the centre of the square the locator names, and its precision is
the square's: a four-character locator is 1 degree of latitude by 2 of
longitude (roughly 110 by 160 km at mid latitudes), a six-character one 2.5 by
5 arc-minutes (roughly 4.6 by 6 km), an eight-character one a tenth of that.
Anything that needs better than the square has to be told the position by the
operator; nothing here pretends to more.

Pairs, alternating longitude then latitude:

========  =====================  ========================
pair      longitude step         latitude step
========  =====================  ========================
field     20 degrees (A-R)       10 degrees (A-R)
square    2 degrees (0-9)        1 degree (0-9)
subsquare 5 arc-minutes (A-X)    2.5 arc-minutes (A-X)
extended  30 arc-seconds (0-9)   15 arc-seconds (0-9)
========  =====================  ========================
"""

from __future__ import annotations

import re

__all__ = ["LocatorError", "centre"]

_LOCATOR = re.compile(r"^[A-R]{2}[0-9]{2}(?:[A-X]{2}(?:[0-9]{2})?)?$")


class LocatorError(ValueError):
    """Not a Maidenhead locator of four, six or eight characters."""


def centre(locator: str) -> tuple[float, float]:
    """(latitude, longitude) of the centre of *locator*'s square, in degrees.

    Case-insensitive; four, six or eight characters. North and east are
    positive, the convention gpredict's ``LAT``/``LON`` keys use.
    """
    text = locator.strip().upper()
    if not _LOCATOR.match(text):
        raise LocatorError(
            f"{locator!r} is not a Maidenhead locator (four, six or eight characters, "
            f"e.g. FN31 or FN31pr)"
        )
    lon = -180.0 + (ord(text[0]) - ord("A")) * 20.0
    lat = -90.0 + (ord(text[1]) - ord("A")) * 10.0
    lon += int(text[2]) * 2.0
    lat += int(text[3]) * 1.0
    lon_step, lat_step = 2.0, 1.0
    if len(text) >= 6:
        lon_step, lat_step = 2.0 / 24, 1.0 / 24
        lon += (ord(text[4]) - ord("A")) * lon_step
        lat += (ord(text[5]) - ord("A")) * lat_step
    if len(text) == 8:
        lon_step, lat_step = lon_step / 10, lat_step / 10
        lon += int(text[6]) * lon_step
        lat += int(text[7]) * lat_step
    return lat + lat_step / 2, lon + lon_step / 2
