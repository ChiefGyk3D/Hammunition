# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Terrain tiles resolved before the plan prints.  D-061.

Synthetic regions with synthetic outlines near 0/0 only.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hammunition.backends.dem import RegionTiles, render_record
from hammunition.copernicus import CopernicusError, TilePin, tile_url
from hammunition.geofabrik import GeofabrikError
from hammunition.terrain_plan import poly_url, resolve_terrain

A = "Copernicus_DSM_COG_10_N00_00_E000_00_DEM"
B = "Copernicus_DSM_COG_10_N00_00_E001_00_DEM"
C = "Copernicus_DSM_COG_10_N01_00_E000_00_DEM"
LIST = frozenset({A, B, C})
MD5 = "0123456789abcdef0123456789abcdef"
#: Covers squares (0,0), (0,1), (1,0) and (1,1); (1,1) is not in LIST: sea.
OUTLINE = "oceania\n1\n 0.5 0.5\n 1.5 0.5\n 1.5 1.5\n 0.5 1.5\nEND\nEND\n"


class RegionProbe:
    def __init__(self, texts: dict[str, str]) -> None:
        self.texts = texts
        self.asked: list[str] = []

    def head(self, url: str) -> tuple[int, int, str | None]:  # pragma: no cover
        raise AssertionError("terrain never HEADs Geofabrik")

    def text(self, url: str) -> str:
        self.asked.append(url)
        if url not in self.texts:
            raise GeofabrikError(f"{url} could not be fetched: offline")
        return self.texts[url]


class TileProbe:
    def __init__(self, heads: dict[str, tuple[int, int, str | None]]) -> None:
        self.heads = heads
        self.asked: list[str] = []

    def head(self, url: str) -> tuple[int, int, str | None]:
        self.asked.append(url)
        if url not in self.heads:
            raise CopernicusError(f"{url} could not be reached: offline")
        return self.heads[url]


def _ok(*names: str) -> dict[str, tuple[int, int, str | None]]:
    return {tile_url(n): (200, 39_000_000, f'"{MD5}"') for n in names}


def test_a_new_region_is_resolved_from_its_outline_and_each_tile_by_head(
    tmp_path: Path,
) -> None:
    regions = RegionProbe({poly_url("atlantis/oceania"): OUTLINE})
    tiles = TileProbe(_ok(A, B, C))
    got = resolve_terrain(
        [("atlantis/oceania", "atlantis-oceania")],
        installed=tmp_path,
        tile_list=LIST,
        pins={},
        region_probe=regions,
        tile_probe=tiles,
    )
    assert got.regions == (RegionTiles("atlantis/oceania", "atlantis-oceania", (A, B, C), 1),)
    assert [t.name for t in got.fetch] == [A, B, C]
    assert all(t.md5 == MD5 for t in got.fetch)
    assert regions.asked == ["https://download.geofabrik.de/atlantis/oceania.poly"]


def test_a_recorded_region_with_every_tile_installed_needs_no_network(tmp_path: Path) -> None:
    entry = RegionTiles("atlantis/oceania", "atlantis-oceania", (A, B), 2)
    (tmp_path / "atlantis-oceania.tiles").write_text(render_record(entry))
    for name in (A, B):
        (tmp_path / f"{name}.tif").write_bytes(b"t")
    regions, tiles = RegionProbe({}), TileProbe({})
    got = resolve_terrain(
        [("atlantis/oceania", "atlantis-oceania")],
        installed=tmp_path,
        tile_list=LIST,
        pins={},
        region_probe=regions,
        tile_probe=tiles,
    )
    assert got.regions == (entry,)
    assert got.fetch == () and got.current == (A, B)
    assert regions.asked == [] and tiles.asked == []


def test_a_pinned_tile_uses_its_pin_and_is_still_checked_reachable(tmp_path: Path) -> None:
    (tmp_path / "atlantis-oceania.tiles").write_text(
        render_record(RegionTiles("atlantis/oceania", "atlantis-oceania", (A,), 0))
    )
    tiles = TileProbe(_ok(A))
    got = resolve_terrain(
        [("atlantis/oceania", "atlantis-oceania")],
        installed=tmp_path,
        tile_list=LIST,
        pins={A: TilePin(A, 39_000_000, "a" * 64, MD5)},
        region_probe=RegionProbe({}),
        tile_probe=tiles,
    )
    assert got.fetch[0].sha256 == "a" * 64
    assert tiles.asked == [tile_url(A)]


def test_offline_every_unresolvable_region_and_tile_is_named_together(tmp_path: Path) -> None:
    (tmp_path / "atlantis-oceania.tiles").write_text(
        render_record(RegionTiles("atlantis/oceania", "atlantis-oceania", (A, B), 0))
    )
    (tmp_path / f"{A}.tif").write_bytes(b"t")
    with pytest.raises(CopernicusError) as raised:
        resolve_terrain(
            [("atlantis/oceania", "atlantis-oceania"), ("atlantis/lemuria", "atlantis-lemuria")],
            installed=tmp_path,
            tile_list=LIST,
            pins={},
            region_probe=RegionProbe({}),
            tile_probe=TileProbe({}),
        )
    message = str(raised.value)
    assert "2 terrain item(s)" in message
    assert "atlantis/lemuria: its outline could not be read" in message
    assert B in message and f"{A}:" not in message, "an installed tile is never asked about"


def test_a_malformed_outline_refuses_rather_than_selecting_nothing(tmp_path: Path) -> None:
    with pytest.raises(CopernicusError, match="atlantis/oceania"):
        resolve_terrain(
            [("atlantis/oceania", "atlantis-oceania")],
            installed=tmp_path,
            tile_list=LIST,
            pins={},
            region_probe=RegionProbe({poly_url("atlantis/oceania"): "<html>busy</html>"}),
            tile_probe=TileProbe({}),
        )


def test_a_multipart_etag_never_reaches_the_plan_as_verifiable(tmp_path: Path) -> None:
    (tmp_path / "atlantis-oceania.tiles").write_text(
        render_record(RegionTiles("atlantis/oceania", "atlantis-oceania", (A,), 0))
    )
    tiles = TileProbe({tile_url(A): (200, 39_000_000, f'"{MD5}-5"')})
    with pytest.raises(CopernicusError) as raised:
        resolve_terrain(
            [("atlantis/oceania", "atlantis-oceania")],
            installed=tmp_path,
            tile_list=LIST,
            pins={},
            region_probe=RegionProbe({}),
            tile_probe=tiles,
        )
    assert A in str(raised.value) and "single-part MD5" in str(raised.value)


def test_an_all_sea_record_reads_back_and_fetches_nothing(tmp_path: Path) -> None:
    entry = RegionTiles("atlantis/oceania", "atlantis-oceania", (), 4)
    (tmp_path / "atlantis-oceania.tiles").write_text(render_record(entry))
    regions, tiles = RegionProbe({}), TileProbe({})
    got = resolve_terrain(
        [("atlantis/oceania", "atlantis-oceania")],
        installed=tmp_path,
        tile_list=LIST,
        pins={},
        region_probe=regions,
        tile_probe=tiles,
    )
    assert got.regions == (entry,) and got.fetch == () and got.current == ()
    assert regions.asked == [] and tiles.asked == []


def test_current_is_the_tiles_on_disk_not_the_record(tmp_path: Path) -> None:
    """The record is written even when a tile failed; only the ``.tif`` says
    a tile is installed."""
    (tmp_path / "atlantis-oceania.tiles").write_text(
        render_record(RegionTiles("atlantis/oceania", "atlantis-oceania", (A, B), 0))
    )
    (tmp_path / f"{A}.tif").write_bytes(b"t")
    tiles = TileProbe(_ok(B))
    got = resolve_terrain(
        [("atlantis/oceania", "atlantis-oceania")],
        installed=tmp_path,
        tile_list=LIST,
        pins={},
        region_probe=RegionProbe({}),
        tile_probe=tiles,
    )
    assert got.current == (A,) and [t.name for t in got.fetch] == [B]
    assert tiles.asked == [tile_url(B)]


def test_a_region_named_twice_fetches_its_outline_once(tmp_path: Path) -> None:
    regions = RegionProbe({poly_url("atlantis/oceania"): OUTLINE})
    got = resolve_terrain(
        [("atlantis/oceania", "atlantis-oceania"), ("atlantis/oceania", "atlantis-oceania")],
        installed=tmp_path,
        tile_list=LIST,
        pins={},
        region_probe=regions,
        tile_probe=TileProbe(_ok(A, B, C)),
    )
    assert len(got.regions) == 1
    assert regions.asked == [poly_url("atlantis/oceania")]


def test_the_outline_is_asked_of_geofabrik_only() -> None:
    assert poly_url("europe/andorra") == "https://download.geofabrik.de/europe/andorra.poly"
