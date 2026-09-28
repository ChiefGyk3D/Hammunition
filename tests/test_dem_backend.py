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

import pytest

from hammunition.backends import Action, BackendError, Command
from hammunition.backends.dem import (
    TIF,
    DemResolution,
    DemTilesBackend,
    RegionTiles,
    read_record,
    render_record,
)
from hammunition.copernicus import (
    PINNED,
    UNPINNED,
    CopernicusError,
    TileFile,
    TilePin,
    resolve_tile,
    select,
    square_of,
    tile_url,
)
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


# ---------------------------------------------------------------------------
# Resolution into the backend: pins, ETags, the sea, and refusals
# ---------------------------------------------------------------------------


class FakeProbe:
    """A HEAD answer per URL; anything unlisted is 'offline'."""

    def __init__(self, answers: dict[str, tuple[int, int, str | None]]) -> None:
        self.answers = answers
        self.asked: list[str] = []

    def head(self, url: str) -> tuple[int, int, str | None]:
        self.asked.append(url)
        if url not in self.answers:
            raise CopernicusError(f"{url} could not be reached: offline")
        return self.answers[url]


def test_a_pinned_tile_asks_nothing_and_an_etag_tile_carries_its_md5() -> None:
    md5 = hashlib.md5(BODY, usedforsecurity=False).hexdigest()
    probe = FakeProbe({tile_url(B): (200, 10, f'"{md5}"')})
    pins = {A: TilePin(A, 10, PINNED_A.sha256 or "", md5)}
    assert resolve_tile(A, pins=pins, probe=probe) == PINNED_A
    assert probe.asked == []
    assert resolve_tile(B, pins=pins, probe=probe) == UNPINNED_B
    assert UNPINNED_B.verified_by == UNPINNED and PINNED_A.verified_by == PINNED


def test_a_multipart_etag_is_refused_by_name() -> None:
    probe = FakeProbe({tile_url(B): (200, 10, '"abc-3"')})
    with pytest.raises(CopernicusError, match=f"{B}: its ETag .*not a single-part MD5"):
        resolve_tile(B, pins={}, probe=probe)


def test_offline_is_refused_naming_the_tile_s_url() -> None:
    with pytest.raises(CopernicusError, match="could not be reached"):
        resolve_tile(B, pins={}, probe=FakeProbe({}))


def test_a_sea_square_is_skipped_and_counted() -> None:
    squares = [square_of(A), square_of(B), square_of(C)]
    tiles, sea = select(squares, frozenset({A, B}))
    assert tiles == (A, B) and sea == 1


def test_a_tile_with_neither_digest_is_never_fetched() -> None:
    with pytest.raises(CopernicusError, match="nothing verifies it"):
        _ = TileFile(C, tile_url(C), 10, None, None).verified_by


def test_a_mismatched_download_installs_nothing_and_fails_the_transaction(
    tmp_path: Path,
) -> None:
    fetcher = FakeFetcher(tmp_path / "cache", bad=[PINNED_A.url, UNPINNED_B.url])
    backend = _backend(
        tmp_path, DemResolution(regions=(OCEANIA,), fetch=(PINNED_A, UNPINNED_B)), fetcher=fetcher
    )
    outcomes = _run(backend)
    assert sum("skipped" in o for o in outcomes) == 2
    assert not list(_data(tmp_path).glob(f"*{TIF}"))
    with pytest.raises(BackendError, match=f"(?s)2 part.*{A}.*{B}"):
        backend.ledger.check()


def test_a_cached_copy_that_changed_after_the_fetch_is_not_installed(tmp_path: Path) -> None:
    class Tampered(FakeFetcher):
        def _file(self, path: Path) -> Path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"x" * 10)  # arrives "verified", differs on re-hash
            return path

    backend = _backend(
        tmp_path,
        DemResolution(regions=(OCEANIA,), fetch=(PINNED_A,)),
        fetcher=Tampered(tmp_path / "cache"),
    )
    outcomes = _run(backend)
    assert any("FAILED" in o and "Nothing was installed" in o for o in outcomes)
    assert list(backend.ledger.failed) == [f"tile {A}"]
    assert not (_data(tmp_path) / f"{A}{TIF}").exists()


def test_the_plan_names_every_destination_before_anything_runs(tmp_path: Path) -> None:
    backend = _backend(tmp_path, DemResolution(regions=(OCEANIA,), fetch=(PINNED_A, UNPINNED_B)))
    m = manifest()
    steps = _actions(backend.steps(m, _block(m)))
    assert [s.kind for s in steps] == ["fetch", "install-data"] * 2 + ["install-data"]
    details = [s.detail for s in steps if s.kind == "install-data"]
    assert details == [
        str(_data(tmp_path) / f"{A}{TIF}"),
        str(_data(tmp_path) / f"{B}{TIF}"),
        str(_data(tmp_path) / "atlantis-oceania.tiles"),
    ]
    assert str(backend.cache_path(PINNED_A)) in steps[1].description
    assert not (tmp_path / "cache").exists(), "building the plan touched nothing"


# ---------------------------------------------------------------------------
# Uninstall
# ---------------------------------------------------------------------------


def test_a_removed_tile_is_no_longer_attributed(tmp_path: Path) -> None:
    import json

    from hammunition.state import TransactionLog
    from hammunition.state.uninstall import files_installed_by_hammunition

    a = f"/usr/local/share/hammunition/data/dem-copernicus/{A}{TIF}"
    b = f"/usr/local/share/hammunition/data/dem-copernicus/{B}{TIF}"
    entries = [
        {"event": "action_end", "version": 1, "kind": "install-data", "detail": a},
        {"event": "action_end", "version": 1, "kind": "install-data", "detail": b},
        {"event": "action_end", "version": 1, "kind": "remove-data", "detail": b},
    ]
    path = tmp_path / "transactions.jsonl"
    path.write_text("".join(json.dumps(e) + "\n" for e in entries))
    assert files_installed_by_hammunition(TransactionLog(path=path)) == {a}


def test_uninstall_removes_every_tile_with_the_directory(tmp_path: Path) -> None:
    from hammunition.distro import Target
    from hammunition.state.uninstall import RemovalPaths, plan_removal

    paths = RemovalPaths(
        prefix=tmp_path / "prefix",
        venv_root=tmp_path / "venvs",
        bin_dir=tmp_path / "bin",
        applications_dir=tmp_path / "applications",
    )
    backend = _backend(tmp_path, DemResolution(regions=(OCEANIA,), fetch=(PINNED_A, UNPINNED_B)))
    backend = DemTilesBackend(
        fetcher=backend.fetcher, prefix=paths.prefix, resolution=backend.resolution
    )
    _run(backend)
    directory = _data(paths.prefix)
    assert sorted(p.name for p in directory.iterdir()) == [
        f"{A}{TIF}",
        f"{B}{TIF}",
        "atlantis-oceania.tiles",
    ]
    plan = plan_removal(
        ["dem-copernicus"],
        catalog={"dem-copernicus": manifest()},
        profiles={},
        target=Target(distro="debian", version="13", arch="x86_64"),
        attributed=frozenset(),
        states={},
        paths=paths,
    )
    assert [(a.kind, a.path, a.basis) for a in plan.artifacts["dem-copernicus"]] == [
        ("tree", directory, "namespaced")
    ]
