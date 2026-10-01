# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The FSTopo half of the topo-quads backend: fetch, check, install, record,
remove.  D-068, amended 2026-10-01. Synthetic sheets near 0/0."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest

from hammunition.backends import Action, BackendError
from hammunition.backends.fstopo import (
    FsTopoBackend,
    FsTopoResolution,
    RegionSheets,
    no_sheets_line,
    read_record,
)
from hammunition.backends.topo import TIF, TopoQuadsBackend, TopoResolution
from hammunition.fetch import Fetcher, FetchResult, VerificationError
from hammunition.fstopo import PINNED, UNVERIFIED, FsQuadFile, parse_row
from hammunition.manifest.schema import PackageManifest, TopoQuadsInstall

BODY = b"II*\x00" + b"f" * 12
SHA = hashlib.sha256(BODY).hexdigest()
ALPHA = parse_row("0 0 0.125 0.125 1230000 11 ZZ Alpha")
BETA = parse_row("0 0.125 0.125 0.25 1230001 0 ZZ Beta Knob")
ALPHA_NEW = parse_row("0 0 0.125 0.125 1230000 12 ZZ Alpha")
URL_A = "https://data.fs.usda.gov/geodata/rastergateway/data3/a.tiff"
URL_B = "https://data.fs.usda.gov/geodata/rastergateway/data3/b.tiff"
OCEANIA = RegionSheets("atlantis/oceania", "atlantis-oceania", (ALPHA, BETA))
LEMURIA = RegionSheets("atlantis/lemuria", "atlantis-lemuria", ())


class FakeFetcher(Fetcher):
    def __init__(self, cache: Path, *, bad: tuple[str, ...] = ()) -> None:
        super().__init__(cache)
        self.bad = set(bad)
        self.calls: list[tuple[str, str]] = []

    def _land(self, path: Path) -> FetchResult:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(BODY)
        return FetchResult(path, SHA, False, len(BODY))

    def fetch_sized(self, url: str, *, expected_size: int) -> FetchResult:
        self.calls.append(("sized", url))
        if url in self.bad:
            raise VerificationError(f"{url} is not a TIFF")
        return self._land(self.sized_path_for(url, expected_size))

    def fetch(
        self, artifact: Any, *, max_bytes: int | None = None, mirror: Any = None
    ) -> FetchResult:
        self.calls.append(("sha256", artifact.url))
        return self._land(self.path_for(artifact))


def manifest() -> PackageManifest:
    return PackageManifest.model_validate(
        {
            "name": "usfs-fstopo",
            "version": "station",
            "summary": "FSTopo sheets for a test",
            "categories": ["navigation-maps"],
            "install": [
                {
                    "install": {
                        "method": "topo-quads",
                        "provider": "usfs-fstopo",
                        "licence": "Public domain (USDA Forest Service)",
                        "licence_url": "https://www.fs.usda.gov/",
                    }
                }
            ],
            "update": {"probe": {"method": "none"}},
            "documentation": {
                "what_it_does": "FSTopo sheets for a test, nothing more.",
                "why_you_want_it": "Because the test suite needs a manifest.",
                "upstream_url": "https://data.fs.usda.gov/geodata/rastergateway/",
            },
        }
    )


def _data(prefix: Path) -> Path:
    return prefix / "share" / "hammunition" / "data" / "usfs-fstopo"


def _steps(backend: TopoQuadsBackend | FsTopoBackend) -> list[Action]:
    m = manifest()
    block = m.install[0].install
    assert isinstance(block, TopoQuadsInstall)
    steps = backend.steps(m, block)
    assert all(isinstance(s, Action) for s in steps)
    return [s for s in steps if isinstance(s, Action)]


def _pair(tmp_path: Path, resolution: FsTopoResolution, **kw: Any) -> TopoQuadsBackend:
    fetcher = kw.pop("fetcher", FakeFetcher(tmp_path / "cache"))
    fs = FsTopoBackend(fetcher=fetcher, prefix=tmp_path, resolution=resolution, **kw)
    return TopoQuadsBackend(
        fetcher=fetcher, prefix=tmp_path, resolution=TopoResolution(), fstopo=fs, ledger=fs.ledger
    )


def test_a_pinned_sheet_is_checked_by_sha256_an_unpinned_one_is_disclosed_unverified(
    tmp_path: Path,
) -> None:
    fetcher = FakeFetcher(tmp_path / "cache")
    backend = _pair(
        tmp_path,
        FsTopoResolution(
            regions=(OCEANIA,),
            fetch=(
                FsQuadFile(ALPHA, URL_A, len(BODY), SHA),
                FsQuadFile(BETA, URL_B, len(BODY), None),
            ),
        ),
        fetcher=fetcher,
    )
    steps = _steps(backend)
    fetches = [s for s in steps if s.kind == "fetch"]
    assert PINNED in fetches[0].description and UNVERIFIED in fetches[1].description
    assert ALPHA.name in fetches[0].description
    outcomes = [s.perform() for s in steps]
    assert fetcher.calls == [("sha256", URL_A), ("sized", URL_B)]
    for quad in (ALPHA, BETA):
        assert (_data(tmp_path) / f"{quad.name}{TIF}").read_bytes() == BODY
    assert any("unverified" in o for o in outcomes)
    assert (
        read_record(_data(tmp_path) / "atlantis-oceania.quads", OCEANIA.region, OCEANIA.slug)
        == OCEANIA
    )
    assert backend.ledger.failed == {}


def test_a_sheet_that_fails_is_named_and_the_others_install(tmp_path: Path) -> None:
    fetcher = FakeFetcher(tmp_path / "cache", bad=(URL_A,))
    backend = _pair(
        tmp_path,
        FsTopoResolution(
            regions=(OCEANIA,),
            fetch=(
                FsQuadFile(ALPHA, URL_A, len(BODY), None),
                FsQuadFile(BETA, URL_B, len(BODY), None),
            ),
        ),
        fetcher=fetcher,
    )
    outcomes = [s.perform() for s in _steps(backend)]
    assert any(o.startswith("FAILED, the rest continues") for o in outcomes)
    assert not (_data(tmp_path) / f"{ALPHA.name}{TIF}").exists()
    assert (_data(tmp_path) / f"{BETA.name}{TIF}").is_file()
    assert list(backend.ledger.failed) == [f"quad {ALPHA.name}"]


def test_a_new_vintage_replaces_the_old_sheet_only_once_it_is_on_disk(tmp_path: Path) -> None:
    data = _data(tmp_path)
    data.mkdir(parents=True)
    (data / f"{ALPHA.name}{TIF}").write_bytes(BODY)
    region = RegionSheets("atlantis/oceania", "atlantis-oceania", (ALPHA_NEW,))
    backend = _pair(
        tmp_path,
        FsTopoResolution(regions=(region,), fetch=(FsQuadFile(ALPHA_NEW, URL_A, len(BODY), None),)),
    )
    [s.perform() for s in _steps(backend)]
    assert (data / f"{ALPHA_NEW.name}{TIF}").is_file()
    assert not (data / f"{ALPHA.name}{TIF}").exists()


def test_a_region_with_no_sheet_records_an_empty_set_and_says_so(tmp_path: Path) -> None:
    backend = _pair(tmp_path, FsTopoResolution(regions=(LEMURIA,)))
    steps = _steps(backend)
    assert any(no_sheets_line(LEMURIA.region) in s.description for s in steps)
    [s.perform() for s in steps]
    assert (
        read_record(_data(tmp_path) / "atlantis-lemuria.quads", LEMURIA.region, LEMURIA.slug)
        == LEMURIA
    )


def test_a_sheet_no_region_needs_is_removed(tmp_path: Path) -> None:
    data = _data(tmp_path)
    data.mkdir(parents=True)
    (data / f"{BETA.name}{TIF}").write_bytes(BODY)
    (data / "atlantis-gone.quads").write_text("# FSTopo quads: 0\n")
    [s.perform() for s in _steps(_pair(tmp_path, FsTopoResolution()))]
    assert not (data / f"{BETA.name}{TIF}").exists()
    assert not (data / "atlantis-gone.quads").exists()


def test_without_an_fstopo_backend_the_block_is_refused(tmp_path: Path) -> None:
    lone = TopoQuadsBackend(
        fetcher=FakeFetcher(tmp_path), prefix=tmp_path, resolution=TopoResolution()
    )
    with pytest.raises(BackendError, match="usfs-fstopo"):
        _steps(lone)
