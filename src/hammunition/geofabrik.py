# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Which Geofabrik file a region and a freshness mode mean, and how it is
verified.  D-057.

Measured 2026-09-27: Geofabrik keeps a dated extract every 1 January, the
1st of the last three months, and the last seven days; ``-latest`` is a 302
to today's dated file; every file has a ``.md5`` beside it. A pinned region
is verified by the sha256 the catalog carries; anything else by Geofabrik's
MD5, and the plan says which, per region, every time.

Pure apart from the injected :class:`Probe`, so every branch is testable
without the network.
"""

from __future__ import annotations

import re
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Protocol

import yaml

BASE = "https://download.geofabrik.de"
PINNED = "sha256, pinned by Hammunition"
UNPINNED = "MD5 from Geofabrik only; not pinned"
_MD5 = re.compile(r"([0-9a-f]{32})\s+\S+\s*")


class GeofabrikError(Exception):
    """A region could not be resolved to a verifiable file."""


@dataclass(frozen=True)
class Pin:
    region: str
    snapshot: str
    size: int
    sha256: str


@dataclass(frozen=True)
class RegionFile:
    region: str
    snapshot: str
    url: str
    size: int
    sha256: str | None
    md5: str | None

    @property
    def verified_by(self) -> str:
        return PINNED if self.sha256 else UNPINNED

    @property
    def slug(self) -> str:
        return self.region.replace("/", "-")


class Probe(Protocol):
    def head(self, url: str) -> tuple[int, int, str | None]: ...
    def text(self, url: str) -> str: ...


class UrllibProbe:
    """The real :class:`Probe`: HTTPS to Geofabrik via :mod:`urllib`.  The one
    part of this module that touches the network.

    ``head`` is built with no redirect handler and no error processor, so a
    302's status and ``Location`` come back as they are -- that redirect is how
    ``latest`` names its dated file -- and a 404 is a status, not an exception.
    ``text`` follows redirects and refuses a non-2xx answer by name. Built from
    :class:`~urllib.request.OpenerDirector` with only the HTTP handlers, as
    :class:`hammunition.fetch.UrllibTransport` is, so no ``file:`` URL is ever
    served. Nothing fetched here is trusted: sizes and MD5s become what the
    download is checked against, and a wrong one fails that check.
    """

    #: Enough for an ``.md5`` line or Geofabrik's region index; bounded so a
    #: misbehaving server cannot be read into memory without limit.
    MAX_TEXT = 8 * 1024 * 1024

    def __init__(self, *, timeout: float = 30.0) -> None:
        self.timeout = timeout
        head = urllib.request.OpenerDirector()
        head.add_handler(urllib.request.HTTPHandler())
        head.add_handler(urllib.request.HTTPSHandler())
        self._head = head
        text = urllib.request.OpenerDirector()
        for handler in (
            urllib.request.HTTPHandler(),
            urllib.request.HTTPSHandler(),
            urllib.request.HTTPRedirectHandler(),
            urllib.request.HTTPErrorProcessor(),
            urllib.request.HTTPDefaultErrorHandler(),
        ):
            text.add_handler(handler)
        self._text = text

    @staticmethod
    def _checked(url: str) -> urllib.request.Request:
        if not url.startswith(BASE + "/"):
            raise GeofabrikError(f"refusing {url!r}: only {BASE} is asked about map regions")
        return urllib.request.Request(url, headers={"User-Agent": "hammunition"})

    def head(self, url: str) -> tuple[int, int, str | None]:
        request = self._checked(url)
        request.method = "HEAD"
        try:
            response = self._head.open(request, timeout=self.timeout)
        except (urllib.error.URLError, OSError) as exc:
            raise GeofabrikError(f"{url} could not be reached: {exc}") from exc
        if response is None:  # pragma: no cover - no handler claimed the scheme
            raise GeofabrikError(f"no handler would ask {url!r}")
        with response:
            length = response.headers.get("Content-Length")
            size = int(length) if length and length.isdigit() else 0
            return response.status, size, response.headers.get("Location")

    def text(self, url: str) -> str:
        request = self._checked(url)
        try:
            response = self._text.open(request, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            raise GeofabrikError(f"{url} returned HTTP {exc.code} ({exc.reason})") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise GeofabrikError(f"{url} could not be fetched: {exc}") from exc
        if response is None:  # pragma: no cover
            raise GeofabrikError(f"no handler would fetch {url!r}")
        with response:
            body: bytes = response.read(self.MAX_TEXT + 1)
        if len(body) > self.MAX_TEXT:
            raise GeofabrikError(f"{url} is larger than {self.MAX_TEXT} bytes; refusing to read it")
        return body.decode("utf-8", errors="replace")


def snapshot_for(freshness: str, today: date) -> str:
    if freshness == "yearly":
        return f"{today:%y}0101"
    if freshness == "monthly":
        return f"{today:%y%m}01"
    raise GeofabrikError(f"{freshness!r} has no fixed snapshot")


def _previous(freshness: str, snapshot: str) -> str:
    # Real date arithmetic, not string slicing: a two-digit year of '00' is
    # 2000, and 2000 - 1 must be 1999 ('99'), not the digit -1.
    when = date(2000 + int(snapshot[:2]), int(snapshot[2:4]), int(snapshot[4:6]))
    if freshness == "yearly":
        previous = when.replace(year=when.year - 1)
    elif when.month == 1:
        previous = when.replace(year=when.year - 1, month=12)
    else:
        previous = when.replace(month=when.month - 1)
    return f"{previous:%y%m%d}"


def _url(region: str, snapshot: str) -> str:
    # `region` is interpolated as given; callers must pass an
    # already-validated region (station config validates it) since the host
    # is fixed and a bad region only ever 404s here, never anything worse.
    return f"{BASE}/{region}-{snapshot}.osm.pbf"


def _md5(probe: Probe, url: str) -> str:
    body = probe.text(url + ".md5").strip()
    match = _MD5.fullmatch(body)
    if match is None:
        raise GeofabrikError(f"{url}.md5 is not an md5 line: {body[:60]!r}")
    return match.group(1)


def resolve(
    region: str,
    freshness: str,
    *,
    today: date,
    pins: Mapping[tuple[str, str], Pin],
    probe: Probe,
) -> RegionFile:
    if freshness == "latest":
        status, _, location = probe.head(f"{BASE}/{region}-latest.osm.pbf")
        found = re.search(r"-(\d{6})\.osm\.pbf$", location or "")
        if status not in (301, 302, 303, 307, 308) or found is None:
            raise GeofabrikError(
                f"{region}-latest.osm.pbf did not redirect to a dated file (HTTP {status}); "
                f"is {region!r} a Geofabrik region? `hammunition maps regions` lists them."
            )
        candidates = [found.group(1)]
    else:
        first = snapshot_for(freshness, today)
        candidates = [first, _previous(freshness, first)]

    for snapshot in candidates:
        pin = pins.get((region, snapshot))
        if pin is not None:
            return RegionFile(region, snapshot, _url(region, snapshot), pin.size, pin.sha256, None)
        url = _url(region, snapshot)
        status, size, _ = probe.head(url)
        if status == 200:
            return RegionFile(region, snapshot, url, size, None, _md5(probe, url))
    raise GeofabrikError(
        f"no {freshness} extract for {region!r}: tried "
        + ", ".join(f"{region}-{s}.osm.pbf" for s in candidates)
        + ". Check the region with `hammunition maps regions`, and the machine's clock."
    )


def load_pins(path: Path) -> dict[tuple[str, str], Pin]:
    data = yaml.safe_load(path.read_text()) or {}
    pins: dict[tuple[str, str], Pin] = {}
    for row in data.get("pins", []):
        pin = Pin(str(row["region"]), str(row["snapshot"]), int(row["size"]), str(row["sha256"]))
        pins[(pin.region, pin.snapshot)] = pin
    return pins
