# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The grid-square-to-position converter gpredict's ground station reads.

Checked against locators whose centres are worked out by hand from the
definition (field 20x10 degrees, square 2x1, subsquare 5x2.5 arc-minutes,
extended 30x15 arc-seconds), including the four corners of the grid, because
an off-by-one in a letter offset moves a station by a whole field -- 1100 km
-- and still looks like a plausible number.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from hammunition.maidenhead import LocatorError, centre  # noqa: E402


@pytest.mark.parametrize(
    ("locator", "lat", "lon"),
    [
        # F=5 -> -80, 3 -> -74, p=15 -> -72.75, +2.5' ; N=13 -> 40, 1 -> 41, r=17 -> 41.7083, +1.25'
        ("FN31pr", 41.729167, -72.708333),
        ("FN31", 41.5, -73.0),
        ("IO91wm", 51.520833, -0.125),
        ("JN03ql", 43.479167, 1.375),
        # Southern and western hemispheres, where a sign error would hide.
        ("QF22le", -37.8125, 144.958333),
        ("GG66", -23.5, -47.0),
        # The corners of the grid.
        ("AA00aa", -89.979167, -179.958333),
        ("RR99xx", 89.979167, 179.958333),
        # Eight characters: a tenth of the subsquare.
        ("FN31pr00", 41.710417, -72.745833),
    ],
)
def test_the_centre_of_a_square(locator: str, lat: float, lon: float) -> None:
    got_lat, got_lon = centre(locator)
    assert got_lat == pytest.approx(lat, abs=1e-5), f"{locator} latitude"
    assert got_lon == pytest.approx(lon, abs=1e-5), f"{locator} longitude"


def test_case_does_not_matter() -> None:
    assert centre("fn31PR") == centre("FN31pr")


@pytest.mark.parametrize(
    "bad", ["", "FN3", "FN31p", "SN31", "FN31py", "FN31pr0", "12AB", "FN31pr0a"]
)
def test_a_non_locator_is_refused(bad: str) -> None:
    with pytest.raises(LocatorError):
        centre(bad)


def test_the_centre_lies_inside_its_own_square() -> None:
    """Round trip through the definition: re-encoding the centre gives the
    locator back, for every subsquare of one square."""
    for a in range(24):
        for b in range(24):
            loc = f"FN31{chr(65 + a)}{chr(65 + b)}"
            lat, lon = centre(loc)
            assert int((lon + 180) // 20) == 5 and int((lat + 90) // 10) == 13
            assert int(((lon + 180) % 20) // 2) == 3 and int((lat + 90) % 10) == 1
            assert int(((lon + 180) % 2) * 12) == a, loc
            assert int(((lat + 90) % 1) * 24) == b, loc
