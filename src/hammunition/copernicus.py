# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Copernicus GLO-30 elevation tiles: which squares a region needs, and how
each tile is verified.  D-061.

One tile is one 1 x 1 degree square, named by its south-west corner
(``Copernicus_DSM_COG_10_N01_00_E001_00_DEM`` covers latitude 1 to 2 and
longitude 1 to 2), a Cloud Optimised GeoTIFF of about 39 MB at
``<bucket>/<name>/<name>.tif``. The bucket's ``tileList.txt`` names every tile
that exists; ocean squares are absent, so a square not in that list is *sea*,
never an error. The list is carried in the catalog
(``catalog/data/copernicus-glo30-tiles.txt``) so the plan needs no network to
know it.

A region's squares are the ones its Geofabrik ``.poly`` outline touches,
edge or interior. Measured 2026-09-28 on two installed regions: the
``.osm.pbf`` header's bounding box spanned hundreds of squares for one of
them where its outline touches tens, and did not even contain the outline's
own bounding box; the outline is what the extract was cut with.

Verified in D-057's two modes: a tile with a row in
``catalog/data/copernicus-glo30-pins.yaml`` by the sha256 Hammunition
measured (:data:`PINNED`); any other by the MD5 in the object's S3 ETag, a
single-part upload's MD5, measured equal to ``md5sum`` on one tile
(:data:`UNPINNED`). The plan says which, tile by tile.

Pure apart from the injected :class:`TileProbe`.
"""

from __future__ import annotations

import math
import re
import urllib.error
import urllib.request
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import yaml

BUCKET = "https://copernicus-dem-30m.s3.amazonaws.com"
PINNED = "sha256, pinned by Hammunition"
UNPINNED = "MD5 from the publisher's object metadata; not pinned by Hammunition"
TILE = re.compile(r"Copernicus_DSM_COG_10_([NS])(\d{2})_00_([EW])(\d{3})_00_DEM")
_ETAG = re.compile(r'"?([0-9a-f]{32})"?')

Square = tuple[int, int]
"""(latitude, longitude) of a square's south-west corner, in whole degrees."""
Point = tuple[float, float]
"""(longitude, latitude), the order a ``.poly`` file writes."""
Ring = tuple[Point, ...]


class CopernicusError(Exception):
    """A tile, an outline or a list could not be read or verified."""


def tile_name(square: Square) -> str:
    lat, lon = square
    ns = "N" if lat >= 0 else "S"
    ew = "E" if lon >= 0 else "W"
    return f"Copernicus_DSM_COG_10_{ns}{abs(lat):02d}_00_{ew}{abs(lon):03d}_00_DEM"


def square_of(name: str) -> Square:
    match = TILE.fullmatch(name)
    if match is None:
        raise CopernicusError(f"{name!r} is not a Copernicus GLO-30 tile name")
    ns, lat, ew, lon = match.groups()
    return (int(lat) * (1 if ns == "N" else -1), int(lon) * (1 if ew == "E" else -1))


def tile_url(name: str) -> str:
    square_of(name)  # refuses anything that is not a tile name
    return f"{BUCKET}/{name}/{name}.tif"


def _wrap(lon: int) -> int:
    """A whole-degree longitude folded into -180..179."""
    return (lon + 180) % 360 - 180


def parse_poly(text: str) -> tuple[list[Ring], list[Ring]]:
    """(outer rings, holes) of an Osmosis ``.poly`` outline.

    The format: a name line; then sections, each a name line (a leading
    ``!`` marks a hole), coordinate lines ``lon lat`` and ``END``; then a
    final ``END``. Refused by name when malformed: an outline that cannot be
    read would select no squares, and a region with no terrain would look
    like a region with nothing to do.
    """
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    if len(lines) < 2 or lines[-1] != "END":
        raise CopernicusError("the outline does not end with END")
    outer: list[Ring] = []
    holes: list[Ring] = []
    current: list[Point] | None = None
    hole = False
    for line in lines[1:-1]:
        if current is None:
            current, hole = [], line.startswith("!")
            continue
        if line == "END":
            if len(current) < 3:
                raise CopernicusError("an outline ring has fewer than three points")
            (holes if hole else outer).append(tuple(current))
            current = None
            continue
        parts = line.split()
        if len(parts) != 2:
            raise CopernicusError(f"not a coordinate line: {line[:60]!r}")
        try:
            lon, lat = float(parts[0]), float(parts[1])
        except ValueError as exc:
            raise CopernicusError(f"not a coordinate line: {line[:60]!r}") from exc
        if not (-360.0 <= lon <= 360.0 and -90.0 <= lat <= 90.0):
            raise CopernicusError(f"a coordinate is out of range: {line[:60]!r}")
        current.append((lon, lat))
    if current is not None:
        raise CopernicusError("an outline ring is not closed with END")
    if not outer:
        raise CopernicusError("the outline has no outer ring")
    return outer, holes


def bbox_ring(left: float, right: float, top: float, bottom: float) -> Ring:
    """A bounding box as a ring; one crossing the antimeridian (``left > right``)
    is unwrapped eastwards so its squares are the ones it covers."""
    if right < left:
        right += 360.0
    return ((left, bottom), (right, bottom), (right, top), (left, top))


def _edge_squares(a: Point, b: Point, out: set[Square]) -> None:
    (x1, y1), (x2, y2) = sorted((a, b))
    for column in range(math.floor(x1), math.floor(x2) + 1):
        if x2 == x1:
            ya, yb = y1, y2
        else:
            xa, xb = max(x1, column), min(x2, column + 1)
            ya = y1 + (y2 - y1) * (xa - x1) / (x2 - x1)
            yb = y1 + (y2 - y1) * (xb - x1) / (x2 - x1)
        for row in range(math.floor(min(ya, yb)), math.floor(max(ya, yb)) + 1):
            out.add((row, column))


def _inside(x: float, y: float, rings: Sequence[Ring]) -> bool:
    """Even-odd over every ring, so a square wholly inside a hole is outside."""
    crossings = False
    for ring in rings:
        for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1], strict=True):
            if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                crossings = not crossings
    return crossings


def squares_touching(outer: Sequence[Ring], holes: Sequence[Ring] = ()) -> frozenset[Square]:
    """Every square the outline touches: those its edges pass through, and
    those whose centre lies inside it. Longitudes are folded into -180..179,
    so an outline written past the antimeridian selects the squares it
    covers; latitudes are kept to -90..89, the squares that exist."""
    found: set[Square] = set()
    rings = [*outer, *holes]
    for ring in rings:
        for a, b in zip(ring, ring[1:] + ring[:1], strict=True):
            _edge_squares(a, b, found)
    xs = [x for ring in outer for x, _ in ring]
    ys = [y for ring in outer for _, y in ring]
    for row in range(math.floor(min(ys)), math.floor(max(ys)) + 1):
        for column in range(math.floor(min(xs)), math.floor(max(xs)) + 1):
            if _inside(column + 0.5, row + 0.5, rings):
                found.add((row, column))
    return frozenset((row, _wrap(column)) for row, column in found if -90 <= row <= 89)


def select(squares: Iterable[Square], tile_list: frozenset[str]) -> tuple[tuple[str, ...], int]:
    """(the tiles that exist for *squares*, sorted; how many squares are sea)."""
    names = {tile_name(s) for s in squares}
    tiles = tuple(sorted(names & tile_list))
    return tiles, len(names) - len(tiles)


def parse_tile_list(text: str) -> frozenset[str]:
    """The names in a tile list: one per line, ``#`` comments and blanks skipped."""
    names: set[str] = set()
    for number, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if TILE.fullmatch(line) is None:
            raise CopernicusError(f"line {number} is not a tile name: {line[:80]!r}")
        names.add(line)
    return frozenset(names)


def load_tile_list(path: Path) -> frozenset[str]:
    return parse_tile_list(path.read_text())


@dataclass(frozen=True)
class TilePin:
    name: str
    size: int
    sha256: str
    md5: str


def load_pins(path: Path) -> dict[str, TilePin]:
    data = yaml.safe_load(path.read_text()) or {}
    pins: dict[str, TilePin] = {}
    for row in data.get("pins") or []:
        pin = TilePin(str(row["tile"]), int(row["size"]), str(row["sha256"]), str(row["md5"]))
        pins[pin.name] = pin
    return pins


@dataclass(frozen=True)
class TileFile:
    name: str
    url: str
    size: int
    sha256: str | None
    md5: str | None

    @property
    def verified_by(self) -> str:
        return PINNED if self.sha256 else UNPINNED


class TileProbe(Protocol):
    def head(self, url: str) -> tuple[int, int, str | None]: ...


class S3Probe:
    """The real :class:`TileProbe`: a ``HEAD`` to the Copernicus bucket, its
    status, ``Content-Length`` and ``ETag``. The one part of this module that
    touches the network.

    Built the way :class:`hammunition.geofabrik.UrllibProbe` is: only the HTTP
    handlers, no redirect handler and no error processor, so a 404 or a 3xx
    comes back as a status rather than being followed; no ``file:`` URL is ever
    served, and nothing outside :data:`BUCKET` is asked. Nothing it returns is
    trusted: the size and MD5 become what the download is checked against.
    """

    def __init__(self, *, timeout: float = 30.0) -> None:
        self.timeout = timeout
        opener = urllib.request.OpenerDirector()
        opener.add_handler(urllib.request.HTTPHandler())
        opener.add_handler(urllib.request.HTTPSHandler())
        self._opener = opener

    def head(self, url: str) -> tuple[int, int, str | None]:
        if not url.startswith(BUCKET + "/"):
            raise CopernicusError(f"refusing {url!r}: only {BUCKET} is asked about tiles")
        request = urllib.request.Request(url, headers={"User-Agent": "hammunition"})
        request.method = "HEAD"
        try:
            response = self._opener.open(request, timeout=self.timeout)
        except (urllib.error.URLError, OSError) as exc:
            raise CopernicusError(f"{url} could not be reached: {exc}") from exc
        if response is None:  # pragma: no cover - no handler claimed the scheme
            raise CopernicusError(f"no handler would ask {url!r}")
        with response:
            length = response.headers.get("Content-Length")
            size = int(length) if length and length.isdigit() else 0
            return response.status, size, response.headers.get("ETag")


def resolve_tile(name: str, *, pins: Mapping[str, TilePin], probe: TileProbe) -> TileFile:
    """*name* as a verifiable download: from its pin, asking nothing, or from
    the bucket's ``HEAD`` -- its size and its ETag's MD5.

    An ETag that is not 32 hex digits (a multipart upload's is
    ``<hex>-<parts>``) is not an MD5 of the object, and the tile is refused
    by name rather than downloaded unverified.
    """
    url = tile_url(name)
    pin = pins.get(name)
    if pin is not None:
        return TileFile(name, url, pin.size, pin.sha256, None)
    status, size, etag = probe.head(url)
    if status != 200:
        raise CopernicusError(f"{url} answered HTTP {status}, not 200")
    if size <= 0:
        raise CopernicusError(
            f"{name}: the bucket reported no size for it, so the download cannot be "
            f"bounded or checked; try again later"
        )
    match = _ETAG.fullmatch((etag or "").strip())
    if match is None:
        raise CopernicusError(
            f"{name}: its ETag {etag!r} is not a single-part MD5, so there is nothing "
            f"to verify the download by; it needs a sha256 pin "
            f"(scripts/gen_copernicus_pins.py)"
        )
    return TileFile(name, url, size, None, match.group(1))
