# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""How many US Topo sheets (and FSTopo sheets, and 3DEP tiles) the station
asks for.  D-068, amended 2026-10-02 (issue #232).

A region is a Geofabrik extract, and for an operator whose regions are whole
states "every sheet of every region" was 7,284 sheets, about 55 GB of
download and 111 GB of disk (measured 2026-10-02). The selection is bounded,
and the bound is the station's:

* **radius** (the default): the sheets whose box comes within
  ``topo_radius_km`` of the centre of the station's grid square, of the
  station's regions. 100 km when unset; ``0`` selects none.
* **regions**: ``topo_regions``, a subset of ``map_regions``. With no radius
  set, those regions are taken whole; with a radius, the circle is cut to
  them.
* **all**: ``topo_all``, every sheet of every region, as before. It is always
  disclosed with its size and asked for by a typed ``yes`` that ``--yes`` does
  not answer (:data:`CONSENT_BYTES`).

Copernicus terrain is not bounded: it is a tenth of the size and BRouter
needs every region whole.

Pure. No network, no filesystem.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol, TypeVar

from .maidenhead import LocatorError, centre

__all__ = [
    "ALL",
    "CONSENT_BYTES",
    "DEFAULT_RADIUS_KM",
    "BoundUnavailable",
    "Boxed",
    "TopoBound",
    "bound_line",
    "distance_km",
    "make_bound",
    "split_bound",
]

DEFAULT_RADIUS_KM = 100
#: Above this many bytes (the download plus the warped copies, decimal), or
#: whenever ``topo_all`` is set, the install asks a typed ``yes``.
CONSENT_BYTES = 10 * 10**9
_EARTH_KM = 6371.0088
_PREFIX = "# bound: "

T = TypeVar("T", bound="Boxed")
Mode = Literal["all", "regions", "radius", "none"]


class BoundUnavailable(Exception):
    """The bound cannot be computed: a radius needs the station's grid square."""


class Boxed(Protocol):
    @property
    def south(self) -> float: ...
    @property
    def west(self) -> float: ...
    @property
    def north(self) -> float: ...
    @property
    def east(self) -> float: ...


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres (haversine)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * _EARTH_KM * math.asin(min(1.0, math.sqrt(a)))


@dataclass(frozen=True)
class TopoBound:
    """The station's bound on the topographic selection."""

    mode: Mode
    radius_km: int = 0
    centre: tuple[float, float] | None = None
    regions: frozenset[str] = frozenset()

    @property
    def token(self) -> str:
        """What a region's record says it was selected under. ``all`` for a
        whole region (the ``all`` and ``regions`` modes alike: the same
        sheets), ``none`` for nothing, else a digest of the circle -- never
        the position itself, which is nobody's business but the station's."""
        if self.mode in ("all", "regions"):
            return "all"
        if self.mode == "none":
            return "none"
        assert self.centre is not None
        text = f"{self.radius_km}|{self.centre[0]:.6f}|{self.centre[1]:.6f}"
        return "r" + hashlib.sha256(text.encode()).hexdigest()[:12]

    def wants_region(self, region: str) -> bool:
        """Whether *region* is among those asked for (all of them unless
        ``topo_regions`` narrowed it)."""
        return not self.regions or region in self.regions

    def keeps(self, box: Boxed) -> bool:
        """Whether a sheet or tile with *box* is selected."""
        if self.mode in ("all", "regions"):
            return True
        if self.mode == "none" or self.centre is None:
            return False
        lat, lon = self.centre
        # The nearest point of the box to the centre, by clamping: exact on a
        # plane and within a few hundred metres at these sizes. The box never
        # wraps the antimeridian (an index row is west < east).
        near_lat = min(max(lat, box.south), box.north)
        near_lon = min(max(lon, box.west), box.east)
        return distance_km(lat, lon, near_lat, near_lon) <= self.radius_km

    def select(self, items: Sequence[T]) -> tuple[T, ...]:
        return tuple(item for item in items if self.keeps(item))

    def describe(self) -> str:
        """The mode in the operator's words, for the plan's note."""
        if self.mode == "all":
            return "every sheet of every region (--topo-all)"
        if self.mode == "regions":
            return f"every sheet of the {len(self.regions)} region(s) chosen with --topo-regions"
        if self.mode == "none":
            return "no sheets (--topo-radius-km 0)"
        where = " within the chosen --topo-regions" if self.regions else ""
        return f"a {self.radius_km} km radius around your grid square{where}"


def make_bound(
    *,
    radius_km: int | None,
    regions: Sequence[str],
    everything: bool | None,
    grid_square: str | None,
) -> TopoBound:
    """The bound a station's three values and grid square make.

    Precedence: ``topo_all``; then ``topo_regions`` alone (taken whole);
    then a radius of 0 (none); then the circle, which needs the grid square
    (:class:`BoundUnavailable` without one -- D-035: the unit defers by name,
    nothing is invented)."""
    chosen = frozenset(regions)
    if everything:
        return TopoBound("all")
    if chosen and radius_km is None:
        return TopoBound("regions", regions=chosen)
    radius = DEFAULT_RADIUS_KM if radius_km is None else radius_km
    if radius == 0:
        return TopoBound("none", regions=chosen)
    if not grid_square:
        raise BoundUnavailable(
            "US Topo is bounded to a radius around your grid square and none is set"
        )
    try:
        here = centre(grid_square)
    except LocatorError as exc:  # pragma: no cover -- Station validates it
        raise BoundUnavailable(str(exc)) from exc
    return TopoBound("radius", radius, here, chosen)


def bound_line(token: str) -> str:
    """The record line naming a bound; nothing for a whole region, which is
    what every record before this carried."""
    return "" if token == "all" else f"{_PREFIX}{token}\n"


def split_bound(lines: Sequence[str]) -> tuple[str, list[str]]:
    """(the bound token a record names, its other lines)."""
    token = "all"
    rest: list[str] = []
    for line in lines:
        if line.startswith(_PREFIX):
            token = line[len(_PREFIX) :].strip() or "all"
        else:
            rest.append(line)
    return token, rest


#: The unbounded selection: every sheet of every region.
ALL = TopoBound("all")
