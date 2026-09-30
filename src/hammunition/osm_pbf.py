# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The bounding box in an OpenStreetMap PBF's header.  D-057.

Navit opened on a blank screen on the field laptop: the generated config kept
the stock ``center=``, which is Munich, and no map existed there. The fix
centres Navit on the regions it has, and the one cheap source of *where* a
region is lies in the first blob of its ``.osm.pbf``.

Only that blob is read. The layout (the OSM wiki's *PBF Format* page):

* a 4-byte big-endian length, then a ``BlobHeader`` of that length whose
  ``type`` (field 1) must be ``OSMHeader`` and whose ``datasize`` (field 3)
  is the length of what follows;
* a ``Blob`` holding the block as ``raw`` (field 1) or ``zlib_data``
  (field 3); ``lzma_data`` and later compressions are refused by name;
* inside, ``HeaderBlock`` field 1 is an optional ``HeaderBBox`` whose
  fields 1-4 are left, right, top, bottom as zigzag ``sint64`` nanodegrees.

Standard library only, with a size cap on everything read and on what zlib
may inflate: a region is gigabytes, the header is a few hundred bytes, and a
parser of downloaded data reads no more than it needs.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path
from typing import BinaryIO

__all__ = ["HEADER_CAP", "OsmPbfError", "bbox_center", "header_bbox"]

#: The most this reads of either the BlobHeader or the header Blob, packed or
#: inflated. The format caps a BlobHeader at 64 KiB; a real OSMHeader block is
#: a few hundred bytes, so 1 MiB is generous and still bounded.
HEADER_CAP = 1024 * 1024

_NANO = 1e-9


class OsmPbfError(Exception):
    """The file is not a readable OSM PBF: truncated, malformed, or oversized."""


BBox = tuple[float, float, float, float]


def _varint(buf: bytes, pos: int) -> tuple[int, int]:
    result = 0
    for shift in range(0, 70, 7):
        if pos >= len(buf):
            raise OsmPbfError("a varint runs past the end of its message")
        byte = buf[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, pos
    raise OsmPbfError("a varint is longer than ten bytes")


def _fields(buf: bytes) -> dict[int, int | bytes]:
    """The last value of each field in *buf*: varints as int, length-delimited
    as bytes. Fixed-width fields are skipped; groups are refused."""
    out: dict[int, int | bytes] = {}
    pos = 0
    while pos < len(buf):
        key, pos = _varint(buf, pos)
        number, wire = key >> 3, key & 7
        if wire == 0:
            out[number], pos = _varint(buf, pos)
        elif wire == 2:
            length, pos = _varint(buf, pos)
            if pos + length > len(buf):
                raise OsmPbfError(f"field {number} runs past the end of its message")
            out[number] = buf[pos : pos + length]
            pos += length
        elif wire == 1:
            pos += 8
        elif wire == 5:
            pos += 4
        else:
            raise OsmPbfError(f"field {number} has unsupported wire type {wire}")
        if pos > len(buf):
            raise OsmPbfError(f"field {number} runs past the end of its message")
    return out


def _bytes(fields: dict[int, int | bytes], number: int) -> bytes | None:
    value = fields.get(number)
    if value is None:
        return None
    if not isinstance(value, bytes):
        raise OsmPbfError(f"field {number} is not length-delimited")
    return value


def _int(fields: dict[int, int | bytes], number: int) -> int | None:
    value = fields.get(number)
    if value is None:
        return None
    if not isinstance(value, int):
        raise OsmPbfError(f"field {number} is not a varint")
    return value


def _unzigzag(value: int) -> int:
    return (value >> 1) ^ -(value & 1)


def _read_exactly(handle: BinaryIO, size: int, what: str) -> bytes:
    data = handle.read(size)
    if len(data) != size:
        raise OsmPbfError(f"truncated: {what} wants {size} bytes, the file has {len(data)}")
    return data


def _header_block(path: Path) -> bytes:
    with path.open("rb") as handle:
        (length,) = struct.unpack(">I", _read_exactly(handle, 4, "the BlobHeader length"))
        if length > HEADER_CAP:
            raise OsmPbfError(f"the BlobHeader is too large ({length} bytes, cap {HEADER_CAP})")
        blob_header = _fields(_read_exactly(handle, length, "the BlobHeader"))
        kind = _bytes(blob_header, 1)
        if kind != b"OSMHeader":
            shown = kind.decode("ascii", "replace") if kind is not None else "none"
            raise OsmPbfError(f"the first blob is {shown!r}, not 'OSMHeader'")
        size = _int(blob_header, 3)
        if size is None:
            raise OsmPbfError("the BlobHeader has no datasize")
        if size > HEADER_CAP:
            raise OsmPbfError(f"the header blob is too large ({size} bytes, cap {HEADER_CAP})")
        blob = _fields(_read_exactly(handle, size, "the header blob"))
    raw = _bytes(blob, 1)
    if raw is not None:
        return raw
    packed = _bytes(blob, 3)
    if packed is None:
        raise OsmPbfError("the header blob is neither raw nor zlib (another compression?)")
    inflater = zlib.decompressobj()
    try:
        block = inflater.decompress(packed, HEADER_CAP)
    except zlib.error as exc:
        raise OsmPbfError(f"the header blob's zlib data is corrupt: {exc}") from exc
    if inflater.unconsumed_tail:
        raise OsmPbfError(f"the header blob inflates too large (past the {HEADER_CAP}-byte cap)")
    if not inflater.eof:
        raise OsmPbfError("the header blob's zlib data is truncated")
    return block


def header_bbox(path: Path) -> BBox | None:
    """(left, right, top, bottom) in degrees from *path*'s header, or None.

    None when the header carries no bbox, which the format allows. Raises
    :class:`OsmPbfError` naming *path* on a malformed or truncated file, and
    lets an ``OSError`` opening it through unchanged. A bbox outside
    -180..180 and -90..90 is malformed."""
    try:
        block = _fields(_header_block(path))
        box = _bytes(block, 1)
        if box is None:
            return None
        sides = _fields(box)
        values = [_int(sides, n) for n in (1, 2, 3, 4)]
    except OsmPbfError as exc:
        raise OsmPbfError(f"{path}: {exc}") from exc
    if any(v is None for v in values):
        raise OsmPbfError(f"{path}: the header bbox is missing a side")
    left, right, top, bottom = (_unzigzag(v) * _NANO for v in values if v is not None)
    # A corrupt writer or a bad pin, not an attacker (the file is hash-checked),
    # but a centre of billions of degrees is a blank map again.
    if not all(-180.0 <= x <= 180.0 for x in (left, right)) or not all(
        -90.0 <= y <= 90.0 for y in (top, bottom)
    ):
        raise OsmPbfError(
            f"{path}: the header bbox is out of range "
            f"(left {left}, right {right}, top {top}, bottom {bottom})"
        )
    return left, right, top, bottom


def bbox_center(bbox: BBox) -> tuple[float, float]:
    """The (lon, lat) midpoint of *bbox*, the way round a box that wraps.

    ``left > right`` means the box crosses the antimeridian; its middle is
    found going east from *left*, and folded back into -180..180."""
    left, right, top, bottom = bbox
    if right < left:
        right += 360.0
    lon = (left + right) / 2
    if lon > 180.0:
        lon -= 360.0
    return lon, (top + bottom) / 2
