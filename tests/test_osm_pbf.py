# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for :mod:`hammunition.osm_pbf`: the bounding box in a PBF's header.  D-057.

Navit opened on Munich, where no map exists, because the generated config
kept the stock ``center=``. The engine centres it on the first region's
bbox, read from the ``OSMHeader`` blob -- and only that blob: a region is
gigabytes, and the header is the first few hundred bytes.

Every PBF here is built by the encoder below, from a synthetic bbox. No
real extract is read and none is committed.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

import pytest

from hammunition.osm_pbf import HEADER_CAP, OsmPbfError, bbox_center, header_bbox

# ---------------------------------------------------------------------------
# A minimal protobuf encoder: just what an OSMHeader blob needs
# ---------------------------------------------------------------------------


def varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def zigzag(value: int) -> int:
    return (value << 1) ^ (value >> 63)


def field_varint(number: int, value: int) -> bytes:
    return varint(number << 3) + varint(value)


def field_bytes(number: int, value: bytes) -> bytes:
    return varint((number << 3) | 2) + varint(len(value)) + value


def header_block(bbox: tuple[float, float, float, float] | None) -> bytes:
    """A HeaderBlock: an optional HeaderBBox (left, right, top, bottom) and a
    required feature, the way osmium writes one."""
    body = b""
    if bbox is not None:
        box = b"".join(
            field_varint(n, zigzag(round(degrees * 1e9))) for n, degrees in enumerate(bbox, 1)
        )
        body += field_bytes(1, box)
    body += field_bytes(4, b"OsmSchema-V0.6")
    body += field_bytes(16, b"test-writer")
    return body


def pbf(
    bbox: tuple[float, float, float, float] | None = (-73.5, -71.4, 45.1, 42.7),
    *,
    compress: bool = True,
    blob_type: bytes = b"OSMHeader",
    trailing: bytes = b"",
) -> bytes:
    """A PBF whose first blob is an OSMHeader, zlib or raw, then *trailing*."""
    block = header_block(bbox)
    if compress:
        blob = field_bytes(3, zlib.compress(block)) + field_varint(2, len(block))
    else:
        blob = field_bytes(1, block)
    blob_header = field_bytes(1, blob_type) + field_varint(3, len(blob))
    return struct.pack(">I", len(blob_header)) + blob_header + blob + trailing


def write(tmp_path: Path, data: bytes) -> Path:
    path = tmp_path / "region.osm.pbf"
    path.write_bytes(data)
    return path


# ---------------------------------------------------------------------------
# Reading the bbox
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("compress", [True, False], ids=["zlib", "raw"])
def test_the_header_bbox_is_read_in_degrees(tmp_path: Path, compress: bool) -> None:
    got = header_bbox(write(tmp_path, pbf(compress=compress)))
    assert got == pytest.approx((-73.5, -71.4, 45.1, 42.7))


def test_a_header_without_a_bbox_is_none(tmp_path: Path) -> None:
    assert header_bbox(write(tmp_path, pbf(None))) is None


def test_only_the_first_blob_is_read(tmp_path: Path) -> None:
    """Whatever follows the header -- gigabytes, in a real extract -- is never read."""
    path = write(tmp_path, pbf(trailing=b"\xff" * 4096))
    assert header_bbox(path) == pytest.approx((-73.5, -71.4, 45.1, 42.7))


def test_a_first_blob_that_is_not_the_header_is_refused_by_name(tmp_path: Path) -> None:
    with pytest.raises(OsmPbfError, match="OSMData"):
        header_bbox(write(tmp_path, pbf(blob_type=b"OSMData")))


@pytest.mark.parametrize("cut", [0, 2, 4, 9, -3])
def test_a_truncated_file_is_refused_naming_it(tmp_path: Path, cut: int) -> None:
    data = pbf()
    path = write(tmp_path, data[:cut])
    with pytest.raises(OsmPbfError, match=str(path)):
        header_bbox(path)


def test_an_oversized_header_length_is_refused_without_reading_it(tmp_path: Path) -> None:
    path = write(tmp_path, struct.pack(">I", HEADER_CAP + 1) + b"\x00" * 16)
    with pytest.raises(OsmPbfError, match="too large"):
        header_bbox(path)


def test_a_blob_that_decompresses_past_the_cap_is_refused(tmp_path: Path) -> None:
    """A zip bomb in a header stops at the cap, not at the end of memory."""
    bomb = zlib.compress(b"\x00" * (HEADER_CAP * 4))
    blob = field_bytes(3, bomb) + field_varint(2, HEADER_CAP * 4)
    blob_header = field_bytes(1, b"OSMHeader") + field_varint(3, len(blob))
    path = write(tmp_path, struct.pack(">I", len(blob_header)) + blob_header + blob)
    with pytest.raises(OsmPbfError, match="too large"):
        header_bbox(path)


def test_an_unsupported_compression_is_refused_by_name(tmp_path: Path) -> None:
    blob = field_bytes(4, b"lzma bytes")  # lzma_data
    blob_header = field_bytes(1, b"OSMHeader") + field_varint(3, len(blob))
    path = write(tmp_path, struct.pack(">I", len(blob_header)) + blob_header + blob)
    with pytest.raises(OsmPbfError, match="neither raw nor zlib"):
        header_bbox(path)


def test_corrupt_zlib_is_refused(tmp_path: Path) -> None:
    blob = field_bytes(3, b"not zlib at all")
    blob_header = field_bytes(1, b"OSMHeader") + field_varint(3, len(blob))
    path = write(tmp_path, struct.pack(">I", len(blob_header)) + blob_header + blob)
    with pytest.raises(OsmPbfError, match="zlib"):
        header_bbox(path)


def test_a_missing_file_is_an_oserror_not_a_bbox(tmp_path: Path) -> None:
    with pytest.raises(OSError):
        header_bbox(tmp_path / "absent.osm.pbf")


# ---------------------------------------------------------------------------
# The centre Navit is given
# ---------------------------------------------------------------------------


def test_the_centre_is_the_midpoint_as_lon_lat() -> None:
    assert bbox_center((-73.5, -71.5, 45.0, 43.0)) == pytest.approx((-72.5, 44.0))


def test_a_bbox_across_the_antimeridian_is_centred_on_it_not_across_the_globe() -> None:
    """left > right: the box wraps. The naive midpoint would land on the far side."""
    lon, lat = bbox_center((170.0, -170.0, 60.0, 50.0))
    assert abs(lon) == pytest.approx(180.0)
    assert lat == pytest.approx(55.0)
    lon, _ = bbox_center((160.0, -170.0, 60.0, 50.0))
    assert lon == pytest.approx(175.0)
