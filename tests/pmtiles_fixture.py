# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""A tiny PMTiles v3 file with one hand-encoded vector tile, for the tests.  D-071.

One z0 tile in the OpenMapTiles schema's shape: a ``water`` polygon (class
``ocean``) over the whole tile and a ``place`` point (class ``city``, named
``Testville``), enough for OSM Bright to draw a fill, a pattern from the
sprite and a label from the glyphs. Synthetic: no map data of anywhere.
Written from the PMTiles v3 specification and the Mapbox Vector Tile 2.1
specification; uncompressed, one entry in the root directory.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

EXTENT = 4096


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


def _key(number: int, wire: int) -> bytes:
    return varint((number << 3) | wire)


def _bytes(number: int, value: bytes) -> bytes:
    return _key(number, 2) + varint(len(value)) + value


def _uint(number: int, value: int) -> bytes:
    return _key(number, 0) + varint(value)


def _packed(number: int, values: list[int]) -> bytes:
    return _bytes(number, b"".join(varint(v) for v in values))


def _zigzag(n: int) -> int:
    return (n << 1) ^ (n >> 31)


def _command(cid: int, count: int) -> int:
    return (cid & 7) | (count << 3)


def _layer(name: str, geometry_type: int, geometry: list[int], tags: dict[str, str]) -> bytes:
    keys = list(tags)
    values = [tags[k] for k in keys]
    feature = (
        _uint(1, 1)
        + _packed(2, [n for i in range(len(keys)) for n in (i, i)])
        + _uint(3, geometry_type)
        + _packed(4, geometry)
    )
    return (
        _uint(15, 2)
        + _bytes(1, name.encode())
        + _bytes(2, feature)
        + b"".join(_bytes(3, k.encode()) for k in keys)
        + b"".join(_bytes(4, _bytes(1, v.encode())) for v in values)
        + _uint(5, EXTENT)
    )


def vector_tile() -> bytes:
    """The one tile: ocean everywhere, one city in the middle."""
    square = [
        _command(1, 1), _zigzag(0), _zigzag(0),
        _command(2, 3), _zigzag(EXTENT), _zigzag(0), _zigzag(0), _zigzag(EXTENT),
        _zigzag(-EXTENT), _zigzag(0),
        _command(7, 1),
    ]  # fmt: skip
    point = [_command(1, 1), _zigzag(EXTENT // 2), _zigzag(EXTENT // 2)]
    water = _layer("water", 3, square, {"class": "ocean"})
    place = _layer(
        "place", 1, point, {"class": "city", "name": "Testville", "name:latin": "Testville"}
    )
    return _bytes(3, water) + _bytes(3, place)


def write_pmtiles(path: Path) -> Path:
    tile = vector_tile()
    # One directory entry: tile id 0 (z0), run length 1, its length, offset 0
    # (stored as offset + 1, the spec's way of saying "not contiguous").
    directory = varint(1) + varint(0) + varint(1) + varint(len(tile)) + varint(1)
    metadata = json.dumps(
        {"vector_layers": [{"id": "water", "fields": {}}, {"id": "place", "fields": {}}]}
    ).encode()
    header_size = 127
    root_offset = header_size
    metadata_offset = root_offset + len(directory)
    data_offset = metadata_offset + len(metadata)
    header = b"PMTiles" + bytes([3])
    header += struct.pack(
        "<11Q",
        root_offset,
        len(directory),
        metadata_offset,
        len(metadata),
        0,
        0,
        data_offset,
        len(tile),
        1,
        1,
        1,
    )
    e7 = 10_000_000
    header += struct.pack("<BBBBBB", 1, 1, 1, 1, 0, 0)  # clustered, no compression, MVT, z0-0
    header += struct.pack("<iiii", -10 * e7, -10 * e7, 10 * e7, 10 * e7)
    header += struct.pack("<Bii", 0, 0, 0)
    assert len(header) == header_size
    path.write_bytes(header + directory + metadata + tile)
    return path
