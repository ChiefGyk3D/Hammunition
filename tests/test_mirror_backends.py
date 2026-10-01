# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The data backends ask the mirror for ``<unit>/<name>``, say so in the
plan, and record where the bytes came from.  D-070."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from typing import IO, Any

from hammunition.backends import Action, DataBackend, RegionsBackend
from hammunition.backends.dem import DemResolution, DemTilesBackend
from hammunition.fetch import Fetcher, MirrorPath
from hammunition.manifest.schema import DataInstall, RegionalDataInstall
from test_data_backend import _manifest as data_manifest
from test_dem_backend import OCEANIA, PINNED_A, UNPINNED_B
from test_dem_backend import FakeFetcher as TileFetcher
from test_dem_backend import _block as dem_block
from test_dem_backend import manifest as dem_manifest
from test_regions_backend import NH, VT, regions_manifest
from test_regions_backend import FakeFetcher as RegionFetcher

MIRROR = "http://bunker.lan:8080/"
CTY = b"cty\n"
CTY_URL = "https://www.country-files.com/cty.dat"


class Routes:
    def __init__(self, routes: dict[str, bytes]) -> None:
        self.routes = routes
        self.requested: list[str] = []

    @contextmanager
    def open(self, url: str) -> Iterator[IO[bytes]]:
        from hammunition.backends import BackendError

        self.requested.append(url)
        if url not in self.routes:
            raise BackendError(f"{url} returned HTTP 404 (Not Found)")
        yield BytesIO(self.routes[url])


def _data(tmp_path: Path, routes: Routes, mirror: str | None) -> tuple[DataBackend, Any, Any]:
    m = data_manifest(
        [
            {
                "url": CTY_URL,
                "sha256": hashlib.sha256(CTY).hexdigest(),
                "size": len(CTY),
                "install_as": "cty.dat",
            }
        ]
    )
    block = m.install[0].install
    assert isinstance(block, DataInstall)
    fetcher = Fetcher(tmp_path / "cache", transport=routes, mirror=mirror)
    return DataBackend(fetcher=fetcher, prefix=tmp_path / "prefix"), m, block


def _fetches(steps: list[Any]) -> list[Action]:
    return [s for s in steps if isinstance(s, Action) and s.kind == "fetch"]


def test_a_data_fetch_asks_the_mirror_first_and_says_so(tmp_path: Path) -> None:
    at_mirror = "http://bunker.lan:8080/country-files/cty.dat"
    routes = Routes({at_mirror: CTY})
    backend, m, block = _data(tmp_path, routes, MIRROR)
    (fetch,) = _fetches(backend.steps(m, block))
    assert fetch.sources == (at_mirror, CTY_URL)
    assert "LAN mirror first" in fetch.description
    assert "checked either way" in fetch.description
    assert fetch.detail.startswith(f"{at_mirror}, then {CTY_URL} (")
    outcome = fetch.perform()
    assert "from the LAN mirror" in outcome
    assert fetch.facts == {"source": "mirror", "fetched_from": at_mirror}
    assert routes.requested == [at_mirror]


def test_a_data_fetch_passed_over_by_the_mirror_records_why(tmp_path: Path) -> None:
    routes = Routes({CTY_URL: CTY})
    backend, m, block = _data(tmp_path, routes, MIRROR)
    (fetch,) = _fetches(backend.steps(m, block))
    outcome = fetch.perform()
    assert "from the publisher" in outcome and "404" in outcome
    assert fetch.facts["source"] == "publisher"
    assert fetch.facts["fetched_from"] == CTY_URL
    assert "404" in fetch.facts["mirror_failure"]


def test_without_a_mirror_the_step_reads_as_it_did(tmp_path: Path) -> None:
    routes = Routes({CTY_URL: CTY})
    backend, m, block = _data(tmp_path, routes, None)
    (fetch,) = _fetches(backend.steps(m, block))
    assert fetch.sources == (CTY_URL,)
    assert "mirror" not in fetch.description and fetch.detail.startswith(f"{CTY_URL} (")
    outcome = fetch.perform()
    assert "mirror" not in outcome and "publisher" not in outcome
    assert fetch.facts == {"source": "publisher", "fetched_from": CTY_URL}


def test_regions_are_asked_for_by_region_path(tmp_path: Path) -> None:
    fetcher = RegionFetcher(tmp_path / "cache")
    fetcher.mirror = MIRROR
    m = regions_manifest()
    block = m.install[0].install
    assert isinstance(block, RegionalDataInstall)
    steps = RegionsBackend(prefix=tmp_path, files=[VT, NH], fetcher=fetcher).steps(m, block)
    fetches = _fetches(steps)
    assert fetches[0].sources == (
        "http://bunker.lan:8080/osm-regions/north-america/us/vermont",
        VT.url,
    )
    assert all("LAN mirror first" in f.description for f in fetches)
    assert "sha256 is checked either way" in fetches[0].description
    assert "md5 is checked either way" in fetches[1].description
    for step in fetches:
        step.perform()
    assert fetcher.mirrors == [
        MirrorPath("osm-regions", "north-america/us/vermont"),
        MirrorPath("osm-regions", "north-america/us/new-hampshire"),
    ]
    assert fetches[0].facts["source"] == "publisher"


def test_tiles_are_asked_for_by_tile_name(tmp_path: Path) -> None:
    fetcher = TileFetcher(tmp_path / "cache")
    fetcher.mirror = MIRROR
    resolution = DemResolution(regions=(OCEANIA,), fetch=(PINNED_A, UNPINNED_B))
    backend = DemTilesBackend(prefix=tmp_path, resolution=resolution, fetcher=fetcher)
    m = dem_manifest()
    fetches = _fetches(backend.steps(m, dem_block(m)))
    assert fetches[0].sources[0] == f"http://bunker.lan:8080/dem-copernicus/{PINNED_A.name}"
    for step in fetches:
        step.perform()
    assert fetcher.mirrors == [
        MirrorPath("dem-copernicus", PINNED_A.name),
        MirrorPath("dem-copernicus", UNPINNED_B.name),
    ]
