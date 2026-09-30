# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The topo-quads backend: fetch, verify, install, record, remove.  D-068.

Synthetic sheets near 0/0 and synthetic regions only.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from hammunition.backends import Action, Command
from hammunition.backends.topo import (
    TIF,
    RegionQuads,
    TopoQuadsBackend,
    TopoResolution,
    no_quads_line,
    read_record,
    render_record,
)
from hammunition.fetch import Fetcher, FetchResult, VerificationError
from hammunition.manifest.schema import PackageManifest, TopoQuadsInstall
from hammunition.ustopo import UNPINNED, Quad

BODY = b"q" * 10
MD5 = hashlib.md5(BODY, usedforsecurity=False).hexdigest()
ALPHA = Quad(0.0, 0.0, 0.125, 0.125, 10, MD5, "ZZ/ZZ_Alpha_20240101")
BETA = Quad(0.0, 0.125, 0.125, 0.25, 10, f"{MD5}-2", "ZZ/ZZ_Beta_20240101")
OCEANIA = RegionQuads("atlantis/oceania", "atlantis-oceania", (ALPHA, BETA))
LEMURIA = RegionQuads("atlantis/lemuria", "atlantis-lemuria", ())


class FakeFetcher(Fetcher):
    """The real cache layout, no network. A URL in *bad* fails verification."""

    def __init__(self, cache: Path, *, bad: Sequence[str] = ()) -> None:
        super().__init__(cache)
        self.bad = set(bad)
        self.calls: list[tuple[str, str, int]] = []

    def fetch_etag(self, url: str, etag: str, *, expected_size: int) -> FetchResult:
        self.calls.append((url, etag, expected_size))
        if url in self.bad:
            raise VerificationError(f"{url} does not match the ETag its publisher lists")
        path = self.etag_path_for(url, etag)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(BODY)
        return FetchResult(path, hashlib.sha256(BODY).hexdigest(), False, 10)


def manifest() -> PackageManifest:
    return PackageManifest.model_validate(
        {
            "name": "usgs-ustopo",
            "version": "station",
            "summary": "US Topo sheets for a test",
            "categories": ["navigation-maps"],
            "install": [
                {
                    "install": {
                        "method": "topo-quads",
                        "provider": "usgs-ustopo",
                        "licence": "Public domain (USGS)",
                        "licence_url": "https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits",
                    }
                }
            ],
            "update": {"probe": {"method": "none"}},
            "documentation": {
                "what_it_does": "US Topo sheets for a test, nothing more.",
                "why_you_want_it": "Because the test suite needs a manifest.",
                "upstream_url": "https://www.usgs.gov/programs/national-geospatial-program/us-topo-maps-america",
            },
        }
    )


def _block(m: PackageManifest) -> TopoQuadsInstall:
    block = m.install[0].install
    assert isinstance(block, TopoQuadsInstall)
    return block


def _data(prefix: Path) -> Path:
    return prefix / "share" / "hammunition" / "data" / "usgs-ustopo"


def _actions(steps: list[Action | Command]) -> list[Action]:
    assert all(isinstance(s, Action) for s in steps)
    return [s for s in steps if isinstance(s, Action)]


def _backend(tmp_path: Path, resolution: TopoResolution, **kw: Any) -> TopoQuadsBackend:
    kw.setdefault("fetcher", FakeFetcher(tmp_path / "cache"))
    return TopoQuadsBackend(prefix=tmp_path, resolution=resolution, **kw)


def _run(backend: TopoQuadsBackend) -> list[str]:
    m = manifest()
    return [s.perform() for s in _actions(backend.steps(m, _block(m)))]


def test_each_sheet_is_fetched_says_how_it_is_verified_and_is_installed(tmp_path: Path) -> None:
    fetcher = FakeFetcher(tmp_path / "cache")
    backend = _backend(
        tmp_path, TopoResolution(regions=(OCEANIA,), fetch=(ALPHA, BETA)), fetcher=fetcher
    )
    m = manifest()
    steps = _actions(backend.steps(m, _block(m)))
    fetches = [s for s in steps if s.kind == "fetch"]
    assert len(fetches) == 2
    assert all(UNPINNED in s.description for s in fetches)
    assert "Public domain (USGS)" in fetches[0].description
    outcomes = [s.perform() for s in steps]
    assert fetcher.calls == [(ALPHA.url, MD5, 10), (BETA.url, f"{MD5}-2", 10)]
    for quad in (ALPHA, BETA):
        installed = _data(tmp_path) / f"{quad.name}{TIF}"
        assert installed.read_bytes() == BODY
        # The cached copy is deleted once installed.
        assert not fetcher.etag_path_for(quad.url, quad.etag).exists()
    assert any("ETag" in o and "not pinned" in o for o in outcomes)
    record = read_record(
        _data(tmp_path) / "atlantis-oceania.quads", "atlantis/oceania", "atlantis-oceania"
    )
    assert record == OCEANIA
    assert backend.ledger.failed == {}


def test_a_sheet_that_does_not_verify_is_named_and_the_others_install(tmp_path: Path) -> None:
    fetcher = FakeFetcher(tmp_path / "cache", bad=[ALPHA.url])
    backend = _backend(
        tmp_path, TopoResolution(regions=(OCEANIA,), fetch=(ALPHA, BETA)), fetcher=fetcher
    )
    outcomes = _run(backend)
    assert any(o.startswith("FAILED, the rest continues") for o in outcomes)
    assert any(o == f"skipped: {ALPHA.name} did not verify" for o in outcomes)
    assert not (_data(tmp_path) / f"{ALPHA.name}{TIF}").exists()
    assert (_data(tmp_path) / f"{BETA.name}{TIF}").is_file()
    assert list(backend.ledger.failed) == [f"quad {ALPHA.name}"]


def test_a_region_no_sheet_covers_records_so_and_fetches_nothing(tmp_path: Path) -> None:
    fetcher = FakeFetcher(tmp_path / "cache")
    backend = _backend(tmp_path, TopoResolution(regions=(LEMURIA,)), fetcher=fetcher)
    m = manifest()
    steps = _actions(backend.steps(m, _block(m)))
    assert [s.kind for s in steps] == ["install-data"]
    assert no_quads_line("atlantis/lemuria") in steps[0].description
    assert "United States" in steps[0].description
    steps[0].perform()
    assert fetcher.calls == []
    assert (
        read_record(
            _data(tmp_path) / "atlantis-lemuria.quads", "atlantis/lemuria", "atlantis-lemuria"
        )
        == LEMURIA
    )


def test_a_current_record_is_not_rewritten_and_an_installed_sheet_not_fetched(
    tmp_path: Path,
) -> None:
    data = _data(tmp_path)
    data.mkdir(parents=True)
    (data / "atlantis-oceania.quads").write_text(render_record(OCEANIA))
    for quad in (ALPHA, BETA):
        (data / f"{quad.name}{TIF}").write_bytes(BODY)
    backend = _backend(tmp_path, TopoResolution(regions=(OCEANIA,), current=(ALPHA, BETA)))
    m = manifest()
    assert backend.steps(m, _block(m)) == []


def test_a_sheet_and_a_record_no_region_needs_are_removed(tmp_path: Path) -> None:
    data = _data(tmp_path)
    data.mkdir(parents=True)
    (data / "atlantis-gone.quads").write_text(render_record(LEMURIA))
    (data / "ZZ_Old_20100101.tif").write_bytes(BODY)
    (data / f"{ALPHA.name}{TIF}").write_bytes(BODY)
    lone = RegionQuads("atlantis/oceania", "atlantis-oceania", (ALPHA,))
    backend = _backend(tmp_path, TopoResolution(regions=(lone,), current=(ALPHA,)))
    m = manifest()
    removals = [s for s in _actions(backend.steps(m, _block(m))) if s.kind == "remove-data"]
    assert sorted(Path(s.detail).name for s in removals) == [
        "ZZ_Old_20100101.tif",
        "atlantis-gone.quads",
    ]


def test_a_kept_regions_record_stays(tmp_path: Path) -> None:
    data = _data(tmp_path)
    data.mkdir(parents=True)
    (data / "atlantis-lemuria.quads").write_text(render_record(LEMURIA))
    backend = _backend(tmp_path, TopoResolution(), keep=frozenset({"atlantis-lemuria"}))
    m = manifest()
    assert backend.steps(m, _block(m)) == []


def test_a_record_that_is_not_a_record_is_not_trusted(tmp_path: Path) -> None:
    path = tmp_path / "r.quads"
    for text in (
        "",
        "ZZ/ZZ_Alpha_20240101\n",
        f"# US Topo quads: 2\n0 0 0.125 0.125 10 {MD5} ZZ/ZZ_Alpha_20240101\n",
        f"# US Topo quads: 1\n0 0 0.125 0.125 10 {MD5} ../../etc/passwd\n",
    ):
        path.write_text(text)
        assert read_record(path, "r", "r") is None
    assert read_record(tmp_path / "missing.quads", "r", "r") is None
