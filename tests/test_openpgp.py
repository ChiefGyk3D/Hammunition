# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Whose key is in this file?  D-040.

The fixture is a throwaway Ed25519 key generated for this suite on
2026-09-03 ("Hammunition test fixture (not a real key)"); its fingerprint was
read from ``gpg --with-colons --fingerprint`` at generation and is asserted
here against what the module computes from the same bytes. The armored and
binary forms are the same key, so they must agree. The failure tests
corrupt the fixture one way each and require the module to say why.
"""

from __future__ import annotations

import base64
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from hammunition.openpgp import (  # noqa: E402
    KeyFileError,
    normalize_fingerprint,
    primary_fingerprints,
)

FIXTURE_FINGERPRINT = "527CA4AEA2444BD240A9FDCD3852FF00E3430290"

FIXTURE_ASC = b"""\
-----BEGIN PGP PUBLIC KEY BLOCK-----

mDMEapln+xYJKwYBBAHaRw8BAQdA4N6zYGSyhuwXhY0YM34NWBTGRKz4MioULqcp
iBReAce0Q0hhbW11bml0aW9uIHRlc3QgZml4dHVyZSAobm90IGEgcmVhbCBrZXkp
IDxmaXh0dXJlQGV4YW1wbGUuaW52YWxpZD6IkAQTFggAOBYhBFJ8pK6iREvSQKn9
zThS/wDjQwKQBQJqmWf7AhsBBQsJCAcCBhUKCQgLAgQWAgMBAh4BAheAAAoJEDhS
/wDjQwKQTpEA/2i0i5xpraseWRD08nFv5u0OLoqRI5Mp5CzT4Qeq+bhdAP95b8jP
CeUtdVcEB5lR55oXbHzlC6oRoh7L6q/yGSlMCA==
=QAjn
-----END PGP PUBLIC KEY BLOCK-----
"""


def _binary() -> bytes:
    """The fixture's packets, dearmored by hand so the binary path is
    exercised without trusting the module's own dearmoring to produce it."""
    body = b"".join(line for line in FIXTURE_ASC.splitlines()[2:-2] if not line.startswith(b"="))
    return base64.b64decode(body)


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


def test_the_armored_fixture_reports_its_fingerprint() -> None:
    assert primary_fingerprints(FIXTURE_ASC) == (FIXTURE_FINGERPRINT,)


def test_the_binary_form_reports_the_same_fingerprint() -> None:
    assert primary_fingerprints(_binary()) == (FIXTURE_FINGERPRINT,)


def test_leading_whitespace_before_the_armor_is_tolerated() -> None:
    assert primary_fingerprints(b"\n\n" + FIXTURE_ASC) == (FIXTURE_FINGERPRINT,)


def test_normalize_strips_the_spaces_people_paste() -> None:
    spaced = "527C A4AE A244 4BD2 40A9  FDCD 3852 FF00 E343 0290"
    assert normalize_fingerprint(spaced.lower()) == FIXTURE_FINGERPRINT


# ---------------------------------------------------------------------------
# Refusals, each by name
# ---------------------------------------------------------------------------


def test_a_corrupted_armor_body_fails_the_crc() -> None:
    corrupted = FIXTURE_ASC.replace(b"mDMEapln", b"mDMEapla")
    with pytest.raises(KeyFileError, match="CRC-24"):
        primary_fingerprints(corrupted)


def test_a_truncated_armor_block_is_refused() -> None:
    cut = FIXTURE_ASC.split(b"=QAjn")[0]
    with pytest.raises(KeyFileError, match="not terminated"):
        primary_fingerprints(cut)


def test_a_truncated_binary_key_is_refused() -> None:
    with pytest.raises(KeyFileError, match="truncated"):
        primary_fingerprints(_binary()[:20])


def test_a_file_that_is_not_openpgp_is_refused() -> None:
    with pytest.raises(KeyFileError, match="not an OpenPGP file"):
        primary_fingerprints(b"<!doctype html><title>404</title>")


def test_a_file_with_no_public_key_packet_is_an_error_not_an_empty_tuple() -> None:
    # A lone user-id packet (tag 13, new format, 5 bytes of body).
    user_id = bytes([0xC0 | 13, 5]) + b"alice"
    with pytest.raises(KeyFileError, match="no public key packet"):
        primary_fingerprints(user_id)


def test_subkeys_are_not_listed_as_primaries() -> None:
    """A tag-14 subkey with the primary's body bytes must not add a second
    fingerprint: the manifest pins the primary, and apt trusts through it."""
    packets = list(_iter_packets(_binary()))
    primary_body = next(body for tag, body in packets if tag == 6)
    subkey = bytes([0xC0 | 14]) + _new_length(len(primary_body)) + primary_body
    assert primary_fingerprints(_binary() + subkey) == (FIXTURE_FINGERPRINT,)


def test_two_primaries_are_both_reported_so_the_caller_can_refuse() -> None:
    assert primary_fingerprints(_binary() + _binary()) == (FIXTURE_FINGERPRINT,) * 2


def test_an_unsupported_key_version_is_refused_by_number() -> None:
    body = bytes([3]) + b"\x00" * 10  # a v3 key, which nobody should be pinning
    packet = bytes([0xC0 | 6]) + _new_length(len(body)) + body
    with pytest.raises(KeyFileError, match="version 3"):
        primary_fingerprints(packet)


def test_a_partial_body_length_is_refused() -> None:
    packet = bytes([0xC0 | 6, 0xE0]) + b"\x04" * 32
    with pytest.raises(KeyFileError, match="partial-body"):
        primary_fingerprints(packet)


def test_a_v6_fingerprint_is_sha256_of_the_four_byte_framing() -> None:
    """RFC 9580 §5.5.4: the framing octet is 0x9B and the length is four
    bytes. Checked against the digest computed directly here rather than
    against a published v6 key, of which no repository this catalog carries
    has one yet."""
    import hashlib

    body = bytes([6]) + b"\x01" * 40
    packet = bytes([0xC0 | 6]) + _new_length(len(body)) + body
    expected = hashlib.sha256(b"\x9b" + len(body).to_bytes(4, "big") + body).hexdigest().upper()
    assert primary_fingerprints(packet) == (expected,)


# ---------------------------------------------------------------------------
# Small helpers: enough packet framing to build the corruptions above
# ---------------------------------------------------------------------------


def _new_length(n: int) -> bytes:
    if n < 192:
        return bytes([n])
    if n < 8384:
        n -= 192
        return bytes([(n >> 8) + 192, n & 0xFF])
    return bytes([255]) + n.to_bytes(4, "big")


def _iter_packets(data: bytes) -> list[tuple[int, bytes]]:
    from hammunition.openpgp import _packets

    return list(_packets(data))
