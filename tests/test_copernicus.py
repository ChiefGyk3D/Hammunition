# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Which Copernicus GLO-30 tiles a region needs, and how each is verified.  D-061.

Every outline and tile here is synthetic: small boxes near 0/0 and on the
antimeridian, nowhere anyone lives in particular.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hammunition.copernicus import (
    PINNED,
    UNPINNED,
    CopernicusError,
    S3Probe,
    TileFile,
    TilePin,
    bbox_ring,
    load_pins,
    parse_poly,
    parse_tile_list,
    resolve_tile,
    select,
    square_of,
    squares_touching,
    tile_name,
    tile_url,
)

A = "Copernicus_DSM_COG_10_N00_00_E000_00_DEM"
B = "Copernicus_DSM_COG_10_S01_00_W001_00_DEM"
MD5 = "0123456789abcdef0123456789abcdef"
SHA = "a" * 64


class FakeProbe:
    def __init__(self, heads: dict[str, tuple[int, int, str | None]]) -> None:
        self.heads = heads
        self.seen: list[str] = []

    def head(self, url: str) -> tuple[int, int, str | None]:
        self.seen.append(url)
        return self.heads.get(url, (404, 0, None))


def test_a_tile_is_named_by_its_south_west_corner() -> None:
    assert tile_name((0, 0)) == A
    assert tile_name((-1, -1)) == B
    assert tile_name((45, -120)) == "Copernicus_DSM_COG_10_N45_00_W120_00_DEM"
    assert square_of(B) == (-1, -1)
    assert tile_url(A) == f"https://copernicus-dem-30m.s3.amazonaws.com/{A}/{A}.tif"


def test_a_name_that_is_not_a_tile_is_refused() -> None:
    with pytest.raises(CopernicusError, match="not a Copernicus"):
        square_of("../../etc/passwd")
    with pytest.raises(CopernicusError):
        tile_url("Copernicus_DSM_COG_10_N00_00_E000_00_DEM/../x")


def test_a_box_crossing_zero_selects_the_four_squares_around_it() -> None:
    got = squares_touching([bbox_ring(-0.5, 0.5, 0.5, -0.5)])
    assert got == {(-1, -1), (-1, 0), (0, -1), (0, 0)}


def test_a_box_crossing_the_antimeridian_selects_both_sides() -> None:
    got = squares_touching([bbox_ring(179.5, -179.5, 10.5, 10.2)])
    assert got == {(10, 179), (10, -180)}


def test_an_outline_past_180_is_folded_back() -> None:
    outer, _ = parse_poly("x\n1\n 179.5 10.2\n 180.5 10.2\n 180.5 10.5\nEND\nEND\n")
    assert squares_touching(outer) == {(10, 179), (10, -180)}


def test_a_diagonal_outline_skips_the_squares_it_does_not_touch() -> None:
    # A thin strip from (0,0) to (3,3): its bounding box is nine squares and
    # the strip touches the diagonal and its neighbours only.
    strip = ((0.1, 0.0), (3.0, 2.9), (2.9, 3.0), (0.0, 0.1))
    got = squares_touching([strip])
    assert (0, 2) not in got and (2, 0) not in got
    assert {(0, 0), (1, 1), (2, 2)} <= got


def test_an_interior_square_is_selected_though_no_edge_crosses_it() -> None:
    got = squares_touching([bbox_ring(-0.5, 2.5, 2.5, -0.5)])
    assert (1, 1) in got
    assert len(got) == 16


def test_a_square_wholly_inside_a_hole_is_not_selected() -> None:
    # The hole spans 0.9..2.1: square (1, 1) lies wholly inside it, and the
    # squares its edges pass through are still selected.
    hole = bbox_ring(0.9, 2.1, 2.1, 0.9)
    got = squares_touching([bbox_ring(-0.5, 3.5, 3.5, -0.5)], [hole])
    assert (1, 1) not in got
    assert {(0, 0), (2, 2), (0, 2), (2, 0)} <= got


def test_squares_missing_from_the_list_are_sea_not_an_error() -> None:
    tiles, sea = select({(0, 0), (-1, -1), (5, 5)}, frozenset({A, B}))
    assert tiles == tuple(sorted((A, B)))
    assert sea == 1


def test_a_poly_outline_is_read_with_its_holes() -> None:
    text = "outline\n1\n 0.0 0.0\n 1.0 0.0\n 1.0 1.0\nEND\n!2\n 0.2 0.2\n 0.4 0.2\n 0.4 0.4\nEND\nEND\n"
    outer, holes = parse_poly(text)
    assert len(outer) == 1 and len(holes) == 1
    assert outer[0][1] == (1.0, 0.0)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "x\n1\n 0 0\n 1 0\n 1 1\nEND\n",  # no final END
        "x\n1\n 0 0\n 1 0\nEND\nEND\n",  # two points
        "x\n1\n 0 zero\n 1 0\n 1 1\nEND\nEND\n",
        "x\n1\n 0 95\n 1 0\n 1 1\nEND\nEND\n",
        "x\n!1\n 0 0\n 1 0\n 1 1\nEND\nEND\n",  # only a hole
    ],
)
def test_a_malformed_outline_is_refused(text: str) -> None:
    with pytest.raises(CopernicusError):
        parse_poly(text)


def test_the_tile_list_skips_comments_and_refuses_a_stray_line() -> None:
    assert parse_tile_list(f"# header\n\n{A}\n{B}\n") == {A, B}
    with pytest.raises(CopernicusError, match="line 2"):
        parse_tile_list(f"{A}\nnot-a-tile\n")


def test_a_pinned_tile_resolves_from_its_pin_and_asks_nothing() -> None:
    probe = FakeProbe({})
    got = resolve_tile(A, pins={A: TilePin(A, 39_000_000, SHA, MD5)}, probe=probe)
    assert got == TileFile(A, tile_url(A), 39_000_000, SHA, None)
    assert got.verified_by == PINNED == "sha256, pinned by Hammunition"
    assert probe.seen == []


def test_an_unpinned_tile_is_verified_by_its_etag_md5() -> None:
    probe = FakeProbe({tile_url(A): (200, 39_000_000, f'"{MD5}"')})
    got = resolve_tile(A, pins={}, probe=probe)
    assert got == TileFile(A, tile_url(A), 39_000_000, None, MD5)
    assert got.verified_by == UNPINNED
    assert UNPINNED == "MD5 from the publisher's object metadata; not pinned by Hammunition"


@pytest.mark.parametrize(
    ("head", "message"),
    [
        ((404, 0, None), "HTTP 404"),
        ((200, 0, f'"{MD5}"'), "no size"),
        ((200, 39_000_000, f'"{MD5}-3"'), "not a single-part MD5"),
        ((200, 39_000_000, None), "not a single-part MD5"),
    ],
)
def test_an_unverifiable_tile_is_refused_by_name(
    head: tuple[int, int, str | None], message: str
) -> None:
    with pytest.raises(CopernicusError, match=message):
        resolve_tile(A, pins={}, probe=FakeProbe({tile_url(A): head}))


def test_the_probe_asks_only_the_bucket() -> None:
    with pytest.raises(CopernicusError, match="only https://copernicus-dem-30m"):
        S3Probe().head("https://example.invalid/x.tif")


def test_pins_load_by_tile_name(tmp_path: Path) -> None:
    path = tmp_path / "pins.yaml"
    path.write_text(
        f"pins:\n- tile: {A}\n  size: 39000000\n  sha256: {SHA}\n  md5: {MD5}\n"
        f"  measured: '2026-09-28'\n"
    )
    assert load_pins(path) == {A: TilePin(A, 39_000_000, SHA, MD5)}
    path.write_text("pins: []\n")
    assert load_pins(path) == {}
