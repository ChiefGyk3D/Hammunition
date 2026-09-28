# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The dem-tiles backend: fetch, verify, install, record, remove.  D-061.

Synthetic tiles near 0/0 and synthetic regions only.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from hammunition.backends import Action, Command
from hammunition.backends.dem import (
    DemResolution,
    DemTilesBackend,
    RegionTiles,
    read_record,
    render_record,
)
from hammunition.copernicus import PINNED, UNPINNED, TileFile, tile_url
from hammunition.fetch import Fetcher, FetchResult, VerificationError
from hammunition.manifest.schema import DemTilesInstall, PackageManifest, RemoteArtifact

BODY = b"t" * 10
A = "Copernicus_DSM_COG_10_N00_00_E000_00_DEM"
B = "Copernicus_DSM_COG_10_N00_00_E001_00_DEM"
C = "Copernicus_DSM_COG_10_N01_00_E000_00_DEM"
PINNED_A = TileFile(A, tile_url(A), 10, hashlib.sha256(BODY).hexdigest(), None)
UNPINNED_B = TileFile(
    B, tile_url(B), 10, None, hashlib.md5(BODY, usedforsecurity=False).hexdigest()
)
OCEANIA = RegionTiles("atlantis/oceania", "atlantis-oceania", (A, B), 2)


class FakeFetcher(Fetcher):
    """The real cache layout, no network. A URL in *bad* fails verification."""

    def __init__(self, cache: Path, *, bad: Sequence[str] = ()) -> None:
        super().__init__(cache)
        self.bad = set(bad)
        self.calls: list[tuple[str, str, Any]] = []

    def _file(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(BODY)
        return path

    def fetch(self, artifact: RemoteArtifact, *, max_bytes: int | None = None) -> FetchResult:
        self.calls.append(("sha256", artifact.url, max_bytes))
        if artifact.url in self.bad:
            raise VerificationError(f"{artifact.url} does not match the digest")
        return FetchResult(self._file(self.path_for(artifact)), artifact.sha256, False, 10)

    def fetch_md5(self, url: str, md5: str, *, expected_size: int) -> FetchResult:
        self.calls.append(("md5", url, expected_size))
        if url in self.bad:
            raise VerificationError(f"{url} does not match the md5 its publisher lists")
        return FetchResult(self._file(self.md5_path_for(url, md5)), "c" * 64, False, 10)


def manifest() -> PackageManifest:
    return PackageManifest.model_validate(
        {
            "name": "dem-copernicus",
            "version": "station",
            "summary": "Elevation tiles for a test",
            "categories": ["navigation-maps"],
            "install": [
                {
                    "install": {
                        "method": "dem-tiles",
                        "provider": "copernicus-glo30",
                        "licence": "Copernicus DEM licence",
                        "licence_url": "https://spacedata.copernicus.eu/",
                    }
                }
            ],
            "update": {"probe": {"method": "none"}},
            "documentation": {
                "what_it_does": "Elevation tiles for a test, nothing more.",
                "why_you_want_it": "Because the test suite needs a manifest.",
                "upstream_url": "https://spacedata.copernicus.eu/",
            },
        }
    )


def _block(m: PackageManifest) -> DemTilesInstall:
    block = m.install[0].install
    assert isinstance(block, DemTilesInstall)
    return block


def _data(prefix: Path) -> Path:
    return prefix / "share" / "hammunition" / "data" / "dem-copernicus"


def _actions(steps: list[Action | Command]) -> list[Action]:
    assert all(isinstance(s, Action) for s in steps)
    return [s for s in steps if isinstance(s, Action)]


def _backend(tmp_path: Path, resolution: DemResolution, **kw: Any) -> DemTilesBackend:
    kw.setdefault("fetcher", FakeFetcher(tmp_path / "cache"))
    return DemTilesBackend(prefix=tmp_path, resolution=resolution, **kw)


def _run(backend: DemTilesBackend) -> list[str]:
    m = manifest()
    return [s.perform() for s in _actions(backend.steps(m, _block(m)))]


def test_each_tile_is_fetched_says_how_it_is_verified_and_is_installed(tmp_path: Path) -> None:
    fetcher = FakeFetcher(tmp_path / "cache")
    backend = _backend(
        tmp_path,
        DemResolution(regions=(OCEANIA,), fetch=(PINNED_A, UNPINNED_B)),
        fetcher=fetcher,
    )
    m = manifest()
    steps = _actions(backend.steps(m, _block(m)))
    fetches = [s for s in steps if s.kind == "fetch"]
    assert PINNED in fetches[0].description and UNPINNED in fetches[1].description
    assert "Copernicus DEM licence" in fetches[0].description
    for step in steps:
        step.perform()
    assert backend.ledger.failed == {}
    assert [(kind, cap) for kind, _, cap in fetcher.calls] == [
        ("sha256", 10 + 1024 * 1024),
        ("md5", 10),
    ]
    out = _data(tmp_path)
    assert (out / f"{A}.tif").read_bytes() == BODY
    assert (out / f"{B}.tif").read_bytes() == BODY
    assert list((tmp_path / "cache").iterdir()) == [], "a tile's cached copy is deleted"
    assert read_record(out / "atlantis-oceania.tiles", OCEANIA.region, OCEANIA.slug) == OCEANIA


def test_one_bad_tile_does_not_stop_the_others(tmp_path: Path) -> None:
    fetcher = FakeFetcher(tmp_path / "cache", bad=[PINNED_A.url])
    backend = _backend(
        tmp_path, DemResolution(regions=(OCEANIA,), fetch=(PINNED_A, UNPINNED_B)), fetcher=fetcher
    )
    outcomes = _run(backend)
    assert any("FAILED" in o and A in o for o in outcomes)
    assert list(backend.ledger.failed) == [f"tile {A}"]
    assert not (_data(tmp_path) / f"{A}.tif").exists()
    assert (_data(tmp_path) / f"{B}.tif").exists()


def test_a_tile_no_region_needs_and_a_dropped_region_s_record_are_removed(tmp_path: Path) -> None:
    out = _data(tmp_path)
    out.mkdir(parents=True)
    for name in (A, B, C):
        (out / f"{name}.tif").write_bytes(BODY)
    (out / "atlantis-oceania.tiles").write_text(render_record(OCEANIA))
    (out / "atlantis-sunk.tiles").write_text(render_record(OCEANIA))
    backend = _backend(tmp_path, DemResolution(regions=(OCEANIA,), current=(A, B)))
    m = manifest()
    steps = _actions(backend.steps(m, _block(m)))
    assert [s.kind for s in steps] == ["remove-data", "remove-data"]
    for step in steps:
        step.perform()
    assert sorted(p.name for p in out.iterdir()) == [
        f"{A}.tif",
        f"{B}.tif",
        "atlantis-oceania.tiles",
    ]


def test_a_kept_region_s_record_is_not_removed(tmp_path: Path) -> None:
    out = _data(tmp_path)
    out.mkdir(parents=True)
    (out / "atlantis-lemuria.tiles").write_text(render_record(OCEANIA))
    backend = _backend(
        tmp_path, DemResolution(regions=(OCEANIA,)), keep=frozenset({"atlantis-lemuria"})
    )
    m = manifest()
    kinds = [s.kind for s in _actions(backend.steps(m, _block(m)))]
    assert "remove-data" not in kinds


def test_the_record_round_trips_with_its_sea_count(tmp_path: Path) -> None:
    path = tmp_path / "r.tiles"
    path.write_text(render_record(OCEANIA))
    assert read_record(path, OCEANIA.region, OCEANIA.slug) == OCEANIA
    path.write_text("not a tile\n")
    assert read_record(path, OCEANIA.region, OCEANIA.slug) is None
    assert read_record(tmp_path / "absent", "x", "x") is None


def test_the_resolution_lists_every_tile_once_sorted() -> None:
    other = RegionTiles("atlantis/lemuria", "atlantis-lemuria", (B, C), 0)
    assert DemResolution(regions=(OCEANIA, other)).tiles == (A, B, C)
