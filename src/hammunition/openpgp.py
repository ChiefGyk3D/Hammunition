# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The one OpenPGP question this engine asks: whose key is in this file?

A third-party apt repository is added only against a fingerprint the
manifest pins (D-040), and the fingerprint has to be computed from the bytes
that will be installed as the keyring -- not read from a ``gpg`` invocation
over some other copy, and not taken on trust from the URL. Computing it is
small: a v4 fingerprint is the SHA-1 of the public-key packet framed as
``0x99 || two-byte length || body`` (RFC 4880 §12.2), a v6 fingerprint the
SHA-256 of ``0x9B || four-byte length || body`` (RFC 9580 §5.5.4). Everything
else here is reading the packet framing to find those bytes, in both the
binary form VSCodium publishes and the ASCII-armored form Microsoft does.

Nothing is verified beyond identity. No signature is checked, no expiry is
read, no web of trust is consulted; apt does its own verification against
the keyring once it is installed. This module answers "is the key in this
file the key the manifest says", and refuses -- by name -- any file it
cannot answer that for: an unsupported key version, a partial-body packet,
an armor block whose CRC does not match, or a keyring holding more than one
primary key, because apt would trust every key in the file and the
disclosure named only one.
"""

from __future__ import annotations

import base64
import hashlib
from collections.abc import Iterator

__all__ = ["KeyFileError", "binary_form", "normalize_fingerprint", "primary_fingerprints"]

_ARMOR_BEGIN = b"-----BEGIN PGP PUBLIC KEY BLOCK-----"
_ARMOR_END = b"-----END PGP PUBLIC KEY BLOCK-----"
_TAG_PUBLIC_KEY = 6


class KeyFileError(ValueError):
    """The file is not a key this engine can identify. Always names why."""


def normalize_fingerprint(text: str) -> str:
    """Forty hex digits, upper case, with the spaces people paste removed."""
    return "".join(text.split()).upper()


def _dearmor(data: bytes) -> bytes:
    """The binary packets inside an ASCII-armored block, CRC checked.

    Armor headers (``Version:``, ``Comment:``) end at the first blank line;
    the base64 body runs to the ``=XXXX`` CRC-24 line. The CRC is verified
    because a truncated or line-wrapped paste decodes to *something*, and
    something is not the key.
    """
    lines = data.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == _ARMOR_BEGIN)
    except StopIteration:
        raise KeyFileError("no PGP PUBLIC KEY BLOCK armor header found") from None
    body: list[bytes] = []
    crc_line: bytes | None = None
    in_headers = True
    for line in lines[start + 1 :]:
        stripped = line.strip()
        if in_headers:
            if stripped == b"":
                in_headers = False
            elif b":" not in stripped:
                # No blank line after the headers: the first base64 line.
                in_headers = False
                body.append(stripped)
            continue
        if stripped == _ARMOR_END:
            break
        if stripped.startswith(b"="):
            crc_line = stripped[1:]
            continue
        if stripped:
            body.append(stripped)
    else:
        raise KeyFileError("armor block is not terminated by an END line")
    try:
        packets = base64.b64decode(b"".join(body), validate=True)
    except ValueError as exc:
        raise KeyFileError(f"armor body is not valid base64: {exc}") from exc
    if crc_line is not None:
        try:
            expected = int.from_bytes(base64.b64decode(crc_line, validate=True), "big")
        except ValueError as exc:
            raise KeyFileError(f"armor CRC line is not valid base64: {exc}") from exc
        if _crc24(packets) != expected:
            raise KeyFileError("armor CRC-24 does not match the decoded body")
    return packets


def _crc24(data: bytes) -> int:
    crc = 0xB704CE
    for byte in data:
        crc ^= byte << 16
        for _ in range(8):
            crc <<= 1
            if crc & 0x1000000:
                crc ^= 0x1864CFB
    return crc & 0xFFFFFF


def _packets(data: bytes) -> Iterator[tuple[int, bytes]]:
    """(tag, body) for every packet, old and new framing (RFC 4880 §4.2)."""
    i = 0
    while i < len(data):
        head = data[i]
        if not head & 0x80:
            raise KeyFileError(f"byte {i} is not a packet header; not an OpenPGP file")
        i += 1
        if head & 0x40:
            tag = head & 0x3F
            first = data[i]
            i += 1
            if first < 192:
                length = first
            elif first < 224:
                length = ((first - 192) << 8) + data[i] + 192
                i += 1
            elif first == 255:
                length = int.from_bytes(data[i : i + 4], "big")
                i += 4
            else:
                raise KeyFileError("partial-body packet lengths are not used by keys; refused")
        else:
            tag = (head >> 2) & 0x0F
            length_type = head & 0x03
            if length_type == 3:
                raise KeyFileError("indeterminate-length packet; refused")
            width = (1, 2, 4)[length_type]
            length = int.from_bytes(data[i : i + width], "big")
            i += width
        body = data[i : i + length]
        if len(body) != length:
            raise KeyFileError(f"packet at byte {i} is truncated ({len(body)} of {length} bytes)")
        i += length
        yield tag, body


def _fingerprint(body: bytes) -> str:
    version = body[0] if body else 0
    if version == 4:
        framed = b"\x99" + len(body).to_bytes(2, "big") + body
        return hashlib.sha1(framed).hexdigest().upper()  # the format's own digest
    if version == 6:
        framed = b"\x9b" + len(body).to_bytes(4, "big") + body
        return hashlib.sha256(framed).hexdigest().upper()
    raise KeyFileError(
        f"public key packet is version {version}; only v4 (RFC 4880) and v6 "
        f"(RFC 9580) fingerprints are computed here"
    )


def binary_form(data: bytes) -> bytes:
    """*data* as OpenPGP packets: dearmored if it was armored, else as is.

    What the fingerprint is computed over, and therefore what is installed as
    the keyring -- the same bytes, in the binary form every distribution's
    own ``Signed-By`` instructions use, whichever form the publisher served.
    """
    if data.lstrip().startswith(_ARMOR_BEGIN):
        return _dearmor(data)
    return data


def primary_fingerprints(data: bytes) -> tuple[str, ...]:
    """The fingerprint of every *primary* public key in *data*, in file order.

    Subkeys (tag 14) are not listed: apt trusts a repository through the
    primary key's certification chain, and the manifest pins the primary. A
    file with no primary key is an error rather than an empty tuple, because
    every caller would otherwise have to remember to check.
    """
    data = binary_form(data)
    found = tuple(_fingerprint(body) for tag, body in _packets(data) if tag == _TAG_PUBLIC_KEY)
    if not found:
        raise KeyFileError("no public key packet in the file")
    return found
