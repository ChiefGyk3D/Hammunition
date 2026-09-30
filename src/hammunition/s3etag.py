# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""An S3 object's ETag as a checksum of its bytes.  D-068.

A single-part upload's ETag is the MD5 of the object. A multipart upload's
is ``<hex>-<parts>``: the MD5 of the concatenated binary MD5s of its parts.
The part size is not published, but it is fixed per upload, so it is found
by trying each whole-MiB size from S3's 5 MiB minimum that splits the object
into exactly that many parts. Measured by the spike on 2026-09-29: a US Topo
PDF matched at 8 MiB parts and a 3DEP tile at 5 MiB. Every candidate
reproducing nothing is a mismatch, never an unverified pass.

It is the publisher's checksum, not one Hammunition measured, and MD5 at
that: it catches a damaged or truncated download, not a deliberately
altered object, and the plan says so wherever it is used.
"""

from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path

__all__ = ["MIB", "EtagError", "etag_matches", "parse_etag", "part_sizes"]

MIB = 1024 * 1024
#: S3's smallest part but the last: a multipart ETag's part size is at least this.
MIN_PART = 5 * MIB
#: The largest part size tried. S3's own ceiling is 5 GiB; the objects this
#: checks are tens to hundreds of MB, uploaded at a few MiB a part.
MAX_PART = 512 * MIB
ETAG = re.compile(r"([0-9a-f]{32})(?:-(\d{1,5}))?")
_CHUNK = 1024 * 1024


class EtagError(ValueError):
    """Not an S3 ETag this can check."""


def parse_etag(etag: str) -> tuple[str, int | None]:
    """(hex, parts) of an S3 ETag; *parts* is None for a single-part upload.
    Quotes are stripped; anything else is refused."""
    match = ETAG.fullmatch(etag.strip().strip('"'))
    if match is None:
        raise EtagError(f"{etag!r} is not an S3 ETag (an MD5, or an MD5 and a part count)")
    parts = match.group(2)
    if parts is not None and int(parts) < 1:
        raise EtagError(f"{etag!r} claims {parts} parts")
    return match.group(1), None if parts is None else int(parts)


def part_sizes(size: int, parts: int) -> list[int]:
    """Part sizes that split *size* bytes into exactly *parts* parts: every
    whole MiB from S3's 5 MiB minimum, the common 8 MiB and 5 MiB first. One
    part is the whole object."""
    if parts == 1:
        return [size]
    found = [
        mib * MIB
        for mib in range(MIN_PART // MIB, MAX_PART // MIB + 1)
        if math.ceil(size / (mib * MIB)) == parts
    ]
    preferred = [p for p in (8 * MIB, 5 * MIB, 16 * MIB) if p in found]
    return preferred + [p for p in found if p not in preferred]


def _md5_of(path: Path) -> str:
    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _multipart(path: Path, part: int) -> tuple[str, int]:
    """(MD5 of the parts' MD5s, part count) of *path* cut at *part* bytes."""
    outer = hashlib.md5(usedforsecurity=False)
    count = 0
    with path.open("rb") as handle:
        while True:
            inner = hashlib.md5(usedforsecurity=False)
            left = part
            while left:
                chunk = handle.read(min(_CHUNK, left))
                if not chunk:
                    break
                inner.update(chunk)
                left -= len(chunk)
            if left == part:
                break
            outer.update(inner.digest())
            count += 1
            if left:
                break
    return outer.hexdigest(), count


def etag_matches(path: Path, etag: str) -> bool:
    """Whether *path*'s bytes reproduce the S3 *etag*.

    Single-part: the MD5 of the file. Multipart: the MD5 of the parts'
    MD5s at some part size in :func:`part_sizes`; the part size is not
    published, so each candidate is tried until one reproduces it."""
    digest, parts = parse_etag(etag)
    if parts is None:
        return _md5_of(path) == digest
    size = path.stat().st_size
    for part in part_sizes(size, parts):
        got, count = _multipart(path, part)
        if count == parts and got == digest:
            return True
    return False
