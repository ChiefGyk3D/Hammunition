# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The US Topo index, quad selection and ETag verification (D-068).

Synthetic quads near 0/0 and public example boxes only; no network."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from hammunition.copernicus import UNPINNED, bbox_ring
from hammunition.ustopo import (
    MIB,
    Quad,
    UstopoError,
    check_quad,
    etag_matches,
    load_index,
    parse_etag,
    parse_index,
    part_sizes,
)

MD5 = "0123456789abcdef0123456789abcdef"


def row(south: float, west: float, north: float, east: float, path: str, etag: str = MD5) -> str:
    return f"{south} {west} {north} {east} 1000 {etag} {path}"


INDEX = "\n".join(
    [
        "# a comment",
        "",
        row(0.0, 0.0, 0.125, 0.125, "ZZ/ZZ_Alpha_20240101"),
        row(0.0, 0.125, 0.125, 0.25, "ZZ/ZZ_Beta_20240101"),
        row(0.125, 0.0, 0.25, 0.125, "ZZ/ZZ_Gamma_20230505"),
        # Off the grid, the way an oversized sheet is: 0.3 to 0.5 east.
        row(0.0, 0.3, 0.125, 0.5, "ZZ/ZZ_Delta_(Oversized)_20220202"),
    ]
)


def test_a_row_is_a_quad_with_its_key_and_url() -> None:
    index = parse_index(INDEX)
    alpha = index.by_path()["ZZ/ZZ_Alpha_20240101"]
    assert (alpha.south, alpha.west, alpha.north, alpha.east) == (0.0, 0.0, 0.125, 0.125)
    assert alpha.name == "ZZ_Alpha_20240101"
    assert alpha.state == "ZZ"
    assert alpha.edition == "20240101"
    assert alpha.key == "StagedProducts/Maps/USTopo/GeoTIFF/ZZ/ZZ_Alpha_20240101_TM_geo.tif"
    assert alpha.url == f"https://prd-tnm.s3.amazonaws.com/{alpha.key}"
    assert alpha.verified_by == UNPINNED


def test_a_region_selects_the_quads_whose_box_it_touches() -> None:
    index = parse_index(INDEX)
    # 0.01..0.1 square: inside Alpha only.
    got = index.select([bbox_ring(0.01, 0.1, 0.1, 0.01)])
    assert [q.name for q in got] == ["ZZ_Alpha_20240101"]


def test_a_region_on_a_cell_boundary_touches_both_cells() -> None:
    index = parse_index(INDEX)
    got = index.select([bbox_ring(0.1, 0.2, 0.1, 0.01)])
    assert {q.name for q in got} == {"ZZ_Alpha_20240101", "ZZ_Beta_20240101"}


def test_an_off_grid_box_is_selected_by_the_cells_it_overlaps() -> None:
    index = parse_index(INDEX)
    got = index.select([bbox_ring(0.45, 0.48, 0.1, 0.05)])
    assert [q.name for q in got] == ["ZZ_Delta_(Oversized)_20220202"]


def test_a_region_away_from_every_quad_selects_none() -> None:
    assert parse_index(INDEX).select([bbox_ring(10.1, 10.2, 10.2, 10.1)]) == ()


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("", "names no quads"),
        ("# only a comment\n", "names no quads"),
        ("0 0 0.125 0.125 1000 x ZZ/ZZ_A_20240101", "not an S3 ETag"),
        (f"0 0 0.125 0.125 1000 {MD5} ZZ/../etc_20240101", "is not <ST>"),
        (f"0 0 0.125 0.125 1000 {MD5} ZZ/ZZ_A", "is not <ST>"),
        (f"0.2 0 0.1 0.125 1000 {MD5} ZZ/ZZ_A_20240101", "not a box"),
        (f"0 0 0.125 0.125 0 {MD5} ZZ/ZZ_A_20240101", "positive"),
        ("0 0 0.125", "not an index row"),
        (
            f"0 0 0.125 0.125 1 {MD5} ZZ/ZZ_A_20240101\n0 0 0.125 0.125 1 {MD5} ZZ/ZZ_A_20240101",
            "second time",
        ),
    ],
)
def test_a_malformed_index_is_refused_by_line(text: str, message: str) -> None:
    with pytest.raises(UstopoError, match=message):
        parse_index(text)


def test_an_unreadable_index_names_the_generator(tmp_path: Path) -> None:
    with pytest.raises(UstopoError, match=r"gen_ustopo_index\.py --fetch"):
        load_index(tmp_path / "missing.txt")


def test_the_carried_index_loads_and_holds_the_public_examples() -> None:
    root = Path(__file__).resolve().parent.parent
    index = load_index(root / "catalog" / "data" / "ustopo-quads.txt")
    assert len(index.quads) > 60_000
    # Delaware, a public example area: its 38 quads (spike, 2026-09-29) sit
    # within this box, and the index carries every one of them.
    delaware = [q for q in index.quads if q.state == "DE"]
    assert len(delaware) == 38


# ---------------------------------------------------------------------------
# ETags
# ---------------------------------------------------------------------------


def test_an_etag_is_parsed_with_its_part_count() -> None:
    assert parse_etag(f'"{MD5}"') == (MD5, None)
    assert parse_etag(f"{MD5}-7") == (MD5, 7)
    with pytest.raises(UstopoError):
        parse_etag(f"{MD5}-0")
    with pytest.raises(UstopoError):
        parse_etag("W/xyz")


def test_part_sizes_split_the_object_into_exactly_that_many_parts() -> None:
    size = 12 * MIB
    got = part_sizes(size, 2)
    assert got[0] == 8 * MIB
    assert all(-(-size // p) == 2 for p in got)
    assert 5 * MIB not in got  # 12 MiB at 5 MiB is three parts
    assert part_sizes(size, 1) == [size]
    assert part_sizes(size, 3)[0] == 5 * MIB


def multipart_etag(data: bytes, part: int) -> str:
    digests = b"".join(
        hashlib.md5(data[i : i + part], usedforsecurity=False).digest()
        for i in range(0, len(data), part)
    )
    count = -(-len(data) // part)
    return f"{hashlib.md5(digests, usedforsecurity=False).hexdigest()}-{count}"


@pytest.mark.parametrize(
    ("length", "part"),
    [
        (9 * MIB + 17, 8 * MIB),  # the common two-part upload
        (11 * MIB + 3, 5 * MIB),  # three parts at S3's minimum
        (16 * MIB, 8 * MIB),  # an exact multiple
        (13 * MIB, 7 * MIB),  # an uncommon whole-MiB part size, still found
    ],
)
def test_a_multipart_etag_is_reproduced(tmp_path: Path, length: int, part: int) -> None:
    data = bytes(range(256)) * (length // 256) + b"x" * (length % 256)
    path = tmp_path / "quad.tif"
    path.write_bytes(data)
    assert etag_matches(path, multipart_etag(data, part))


def test_a_single_part_etag_is_the_md5(tmp_path: Path) -> None:
    path = tmp_path / "quad.tif"
    path.write_bytes(b"quad")
    assert etag_matches(path, hashlib.md5(b"quad", usedforsecurity=False).hexdigest())


def test_a_one_part_multipart_etag_is_the_md5_of_the_md5(tmp_path: Path) -> None:
    path = tmp_path / "quad.tif"
    path.write_bytes(b"quad")
    inner = hashlib.md5(b"quad", usedforsecurity=False).digest()
    assert etag_matches(path, hashlib.md5(inner, usedforsecurity=False).hexdigest() + "-1")


def test_a_changed_byte_does_not_match(tmp_path: Path) -> None:
    data = b"a" * (9 * MIB)
    etag = multipart_etag(data, 8 * MIB)
    path = tmp_path / "quad.tif"
    path.write_bytes(data[:-1] + b"b")
    assert not etag_matches(path, etag)
    path.write_bytes(b"quad")
    assert not etag_matches(path, MD5)


# ---------------------------------------------------------------------------
# The plan-time check against the bucket
# ---------------------------------------------------------------------------


class FakeProbe:
    def __init__(self, answer: tuple[int, int, str | None]) -> None:
        self.answer = answer
        self.seen: list[str] = []

    def head(self, url: str) -> tuple[int, int, str | None]:
        self.seen.append(url)
        return self.answer


QUAD = Quad(0.0, 0.0, 0.125, 0.125, 1000, MD5, "ZZ/ZZ_Alpha_20240101")


def test_a_quad_the_bucket_serves_as_indexed_passes() -> None:
    probe = FakeProbe((200, 1000, f'"{MD5}"'))
    check_quad(QUAD, probe)
    assert probe.seen == [QUAD.url]


@pytest.mark.parametrize(
    ("answer", "message"),
    [
        ((404, 0, None), "HTTP 404"),
        ((200, 999, f'"{MD5}"'), "object changed"),
        ((200, 1000, '"ffffffffffffffffffffffffffffffff"'), "object changed"),
    ],
)
def test_a_quad_the_bucket_no_longer_serves_as_indexed_is_refused(
    answer: tuple[int, int, str | None], message: str
) -> None:
    with pytest.raises(UstopoError, match=message) as excinfo:
        check_quad(QUAD, FakeProbe(answer))
    assert "gen_ustopo_index.py --fetch" in str(excinfo.value)
