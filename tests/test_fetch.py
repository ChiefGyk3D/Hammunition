# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The verified fetcher.

The property worth asserting is not that a good download succeeds. It is that a
**bad one leaves nothing usable behind** — CLAUDE.md requires checksum
verification and a refusal to install without it, and the way that requirement
fails in practice is not "we forgot to check" but "we checked, refused, and left
the file where the next run would find it".

So the tests below are written to the failure: a corrupted transfer, a tampered
cache, an oversized body, a dead host. Each asserts the refusal *and* the state
of the cache directory afterwards.
"""

from __future__ import annotations

import hashlib
import socket
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from typing import IO

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from hammunition.backends import BackendError  # noqa: E402
from hammunition.fetch import (  # noqa: E402
    Fetcher,
    FetchResult,
    UrllibTransport,
    VerificationError,
    signature_gap,
)
from hammunition.manifest.schema import RemoteArtifact  # noqa: E402

PAYLOAD = b"the artifact bytes\n"
DIGEST = hashlib.sha256(PAYLOAD).hexdigest()
URL = "https://example.invalid/glfer-0.4.2.tar.gz"


class FakeTransport:
    """Serves fixed bytes. Records every URL it was asked for."""

    def __init__(self, body: bytes = PAYLOAD) -> None:
        self.body = body
        self.requested: list[str] = []

    @contextmanager
    def open(self, url: str) -> Iterator[IO[bytes]]:
        self.requested.append(url)
        yield BytesIO(self.body)


def _artifact(sha256: str = DIGEST, url: str = URL, **kwargs: object) -> RemoteArtifact:
    return RemoteArtifact(url=url, sha256=sha256, **kwargs)  # type: ignore[arg-type]


def _cache_files(cache: Path) -> list[str]:
    return sorted(p.name for p in cache.iterdir()) if cache.exists() else []


# ---------------------------------------------------------------------------
# The happy path, only enough of it to make the failures meaningful
# ---------------------------------------------------------------------------


def test_a_matching_download_is_verified_and_cached(tmp_path: Path) -> None:
    fetcher = Fetcher(tmp_path, transport=FakeTransport())
    result = fetcher.fetch(_artifact())

    assert isinstance(result, FetchResult)
    assert result.sha256 == DIGEST
    assert result.size == len(PAYLOAD)
    assert not result.from_cache
    assert result.path.read_bytes() == PAYLOAD
    assert result.path.name.startswith(DIGEST), "the cache path must encode the digest"


def test_a_second_fetch_reuses_the_cache_without_downloading(tmp_path: Path) -> None:
    transport = FakeTransport()
    fetcher = Fetcher(tmp_path, transport=transport)
    fetcher.fetch(_artifact())
    again = fetcher.fetch(_artifact())

    assert again.from_cache
    assert len(transport.requested) == 1, "a cached artifact was downloaded again"


def test_path_for_predicts_the_destination_without_touching_disk(tmp_path: Path) -> None:
    """The plan discloses where a download will land before it lands."""
    fetcher = Fetcher(tmp_path, transport=FakeTransport())
    predicted = fetcher.path_for(_artifact())
    assert not tmp_path.exists() or _cache_files(tmp_path) == []
    assert fetcher.fetch(_artifact()).path == predicted


# ---------------------------------------------------------------------------
# The refusals. These are the reason the module exists.
# ---------------------------------------------------------------------------


def test_a_mismatched_digest_is_refused(tmp_path: Path) -> None:
    wrong = hashlib.sha256(b"something else entirely").hexdigest()
    fetcher = Fetcher(tmp_path, transport=FakeTransport())

    with pytest.raises(VerificationError) as caught:
        fetcher.fetch(_artifact(sha256=wrong))

    message = str(caught.value)
    assert wrong in message and DIGEST in message, "the error must show both digests"


def test_a_mismatched_download_leaves_nothing_behind(tmp_path: Path) -> None:
    """The failure mode that matters. Refusing and then leaving the bad file in
    the cache would let the *next* run pick it up as if it had been verified."""
    wrong = hashlib.sha256(b"something else entirely").hexdigest()
    fetcher = Fetcher(tmp_path, transport=FakeTransport())

    with pytest.raises(VerificationError):
        fetcher.fetch(_artifact(sha256=wrong))

    assert _cache_files(tmp_path) == [], (
        f"a rejected download was left in the cache: {_cache_files(tmp_path)}"
    )


def test_a_tampered_cache_entry_is_not_trusted(tmp_path: Path) -> None:
    """A file that was verified once is re-verified, not trusted for having
    been. Content-addressing means a mismatch here is corruption or tampering,
    never a stale version — so it is replaced, and never served."""
    transport = FakeTransport()
    fetcher = Fetcher(tmp_path, transport=transport)
    cached = fetcher.fetch(_artifact()).path

    cached.write_bytes(b"replaced after verification")
    result = fetcher.fetch(_artifact())

    assert result.path.read_bytes() == PAYLOAD, "tampered cache content was served"
    assert not result.from_cache
    assert len(transport.requested) == 2, "the tampered entry was not re-downloaded"


def test_an_oversized_body_is_abandoned(tmp_path: Path) -> None:
    big = b"x" * 4096
    fetcher = Fetcher(
        tmp_path,
        transport=FakeTransport(big),
        max_bytes=1024,
    )

    with pytest.raises(BackendError, match="byte limit"):
        fetcher.fetch(_artifact(sha256=hashlib.sha256(big).hexdigest()))

    assert _cache_files(tmp_path) == [], "an abandoned oversized download was left behind"


def test_a_transport_failure_leaves_nothing_behind(tmp_path: Path) -> None:
    class Failing:
        @contextmanager
        def open(self, url: str) -> Iterator[IO[bytes]]:
            raise BackendError("host is unreachable")
            # Unreachable by design: this fake fails at open(), before any
            # stream exists. The yield is what makes it a generator.
            yield BytesIO(b"")  # type: ignore[unreachable]

    fetcher = Fetcher(tmp_path, transport=Failing())
    with pytest.raises(BackendError, match="unreachable"):
        fetcher.fetch(_artifact())
    assert _cache_files(tmp_path) == []


def test_a_partial_transfer_leaves_nothing_behind(tmp_path: Path) -> None:
    """A stream that dies mid-body must not leave a `.part` file that a later
    run could mistake for anything."""

    class Truncating:
        @contextmanager
        def open(self, url: str) -> Iterator[IO[bytes]]:
            class Stream:
                def read(self, _n: int = -1) -> bytes:
                    raise OSError("connection reset")

            yield Stream()  # type: ignore[misc]

    fetcher = Fetcher(tmp_path, transport=Truncating())
    with pytest.raises(OSError, match="connection reset"):
        fetcher.fetch(_artifact())
    assert _cache_files(tmp_path) == []


# ---------------------------------------------------------------------------
# Cache naming
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "https://example.invalid/../../etc/passwd",
        "https://example.invalid/..%2f..%2fetc%2fpasswd",
        "https://example.invalid/",
        "https://example.invalid/name?query=1#frag",
        "https://example.invalid/" + "a" * 500,
    ],
)
def test_the_cache_name_stays_inside_the_cache(tmp_path: Path, url: str) -> None:
    """The digest identifies the file; the readable half is derived from the URL
    and must never be able to escape the directory or grow unboundedly.

    The property is where the path *resolves*, not whether the name contains a
    scary substring: `..` between two ordinary characters, with no separator
    anywhere, traverses nothing. Asserting on the substring instead flagged
    `..%2f..%2fetc%2fpasswd` — which lands harmlessly inside the cache — while
    proving nothing about traversal.
    """
    fetcher = Fetcher(tmp_path, transport=FakeTransport())
    path = fetcher.path_for(_artifact(url=url))

    assert path.resolve().parent == tmp_path.resolve(), "the cache name escaped the cache"
    assert path.name not in {".", ".."}
    assert not path.name.startswith("."), "a cache entry must not be a dotfile"
    assert "/" not in path.name and "\0" not in path.name
    assert len(path.name) <= 64 + len(DIGEST) + 1


def test_two_urls_with_the_same_bytes_share_one_entry(tmp_path: Path) -> None:
    fetcher = Fetcher(tmp_path, transport=FakeTransport())
    first = fetcher.fetch(_artifact(url="https://a.invalid/pkg.tar.gz"))
    second = fetcher.fetch(_artifact(url="https://b.invalid/pkg.tar.gz"))
    assert first.path == second.path
    assert second.from_cache


# ---------------------------------------------------------------------------
# The gap we do not paper over
# ---------------------------------------------------------------------------


def test_an_unsigned_artifact_reports_no_gap() -> None:
    assert signature_gap(_artifact()) is None


def test_a_signed_artifact_reports_that_we_do_not_check_it() -> None:
    """CLAUDE.md requires honest gaps. A manifest carrying a signature URL the
    engine ignores reads as covered when it is not, so it says so."""
    artifact = _artifact(signature_url="https://example.invalid/pkg.tar.gz.asc")
    gap = signature_gap(artifact)
    assert gap is not None
    assert "does not verify" in gap


# ---------------------------------------------------------------------------
# The transport itself
# ---------------------------------------------------------------------------


def test_the_real_transport_has_no_handler_for_file_urls(tmp_path: Path) -> None:
    """A redirect to `file://` must not be followed into the local filesystem.
    The schema refuses a non-http(s) `url`; it cannot see the redirect chain,
    so the opener is built without those handlers at all."""
    secret = tmp_path / "secret"
    secret.write_text("not yours")

    transport = UrllibTransport()
    with pytest.raises(BackendError), transport.open(secret.as_uri()) as _stream:
        pass  # pragma: no cover


def test_the_suite_blocks_the_network() -> None:
    """The seam is only a seam if nothing can go around it. Asserted here so
    the guard itself is tested rather than assumed (CLAUDE.md: a check nobody
    falsified is a check nobody should trust)."""
    with pytest.raises(Exception, match="blocked a connection"):
        socket.create_connection(("example.com", 80), timeout=1)
