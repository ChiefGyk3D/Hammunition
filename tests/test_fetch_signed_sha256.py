# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Bunker bytes are also checked against the signed catalogue's sha256.  #381, Task 13.

A repository pin that is not a sha256 (an md5, a SHA-1, an ETag, a size, or
nothing) lets bytes through that the signed catalogue says are not the ones the
Bunker holds. For those routes the mirror's bytes (and a cached copy) must also
match the catalogue row's sha256, when the row has one. It is in addition to the
publisher check, never instead of it, and a sha256-pinned route is untouched.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path

import pytest

from hammunition.backends.base import BackendError
from hammunition.fetch import Fetcher, FetchResult, MirrorPath, mirror_url
from test_fetch_mirror import Routes

BODY = b"II*\x00pinned by a weak digest"
OTHER = b"II*\x00what the signed catalogue says it holds"
MD5 = hashlib.md5(BODY, usedforsecurity=False).hexdigest()
SHA1 = hashlib.sha1(BODY, usedforsecurity=False).hexdigest()
SHA256 = hashlib.sha256(BODY).hexdigest()
SIGNED = hashlib.sha256(OTHER).hexdigest()
PUBLISHER = "https://example.invalid/Test.tif"
BUNKER = "http://bunker.invalid"
PATH = MirrorPath("unit", "name/Test.tif")
AT_MIRROR = mirror_url(BUNKER, PATH)


def _md5(fetcher: Fetcher) -> FetchResult:
    return fetcher.fetch_md5(PUBLISHER, MD5, expected_size=len(BODY), mirror=PATH)


def _sha1(fetcher: Fetcher) -> FetchResult:
    return fetcher.fetch_sha1(PUBLISHER, SHA1, expected_size=len(BODY), mirror=PATH)


def _etag(fetcher: Fetcher) -> FetchResult:
    return fetcher.fetch_etag(PUBLISHER, MD5, expected_size=len(BODY), mirror=PATH)


def _sized(fetcher: Fetcher) -> FetchResult:
    return fetcher.fetch_sized(PUBLISHER, expected_size=len(BODY), mirror=PATH)


def _checked(fetcher: Fetcher) -> FetchResult:
    return fetcher.fetch_checked(PUBLISHER, max_bytes=1024, check=lambda path: None, mirror=PATH)


ROUTES = pytest.mark.parametrize(
    "fetch", [_md5, _sha1, _etag, _sized, _checked], ids=["md5", "sha1", "etag", "sized", "checked"]
)
Fetch = Callable[[Fetcher], FetchResult]


def _fetcher(
    tmp_path: Path,
    routes: Routes,
    signed: Callable[[MirrorPath], str | None] | None,
    *,
    offline: bool,
) -> Fetcher:
    return Fetcher(
        tmp_path / "cache",
        transport=routes,
        mirror=BUNKER,
        mirror_transport=routes,
        offline=offline,
        signed_sha256=signed,
    )


def _parts(tmp_path: Path) -> list[Path]:
    return list((tmp_path / "cache").glob("*.part.*"))


@ROUTES
def test_offline_mirror_bytes_failing_the_signed_sha256_are_refused_naming_both(
    tmp_path: Path, fetch: Fetch
) -> None:
    routes = Routes({AT_MIRROR: BODY})
    fetcher = _fetcher(tmp_path, routes, lambda path: SIGNED, offline=True)
    with pytest.raises(BackendError) as caught:
        fetch(fetcher)
    text = str(caught.value)
    assert SIGNED in text and SHA256 in text
    assert routes.requested == [AT_MIRROR]
    assert _parts(tmp_path) == []
    assert not [p for p in (tmp_path / "cache").iterdir()]


@ROUTES
def test_online_a_signed_mismatch_falls_back_to_the_publisher_naming_the_reason(
    tmp_path: Path, fetch: Fetch
) -> None:
    routes = Routes({AT_MIRROR: BODY, PUBLISHER: BODY})
    fetcher = _fetcher(tmp_path, routes, lambda path: SIGNED, offline=False)
    result = fetch(fetcher)
    assert result.source == "publisher"
    assert result.mirror_failure is not None
    assert SIGNED in result.mirror_failure and SHA256 in result.mirror_failure
    assert routes.requested == [AT_MIRROR, PUBLISHER]


@ROUTES
def test_online_the_publisher_is_still_checked_when_both_fail(tmp_path: Path, fetch: Fetch) -> None:
    # In addition to the publisher's own check, never instead of it.
    routes = Routes({AT_MIRROR: BODY, PUBLISHER: b"x" * len(BODY)})
    fetcher = _fetcher(tmp_path, routes, lambda path: SIGNED, offline=False)
    with pytest.raises(BackendError):
        if fetch is _checked:
            fetcher.fetch_checked(PUBLISHER, max_bytes=1024, check=_reject, mirror=PATH)
        else:
            fetch(fetcher)


def _reject(path: Path) -> None:
    raise BackendError("the structure check failed")


@ROUTES
def test_a_matching_signed_sha256_passes_and_is_asked_for_this_path(
    tmp_path: Path, fetch: Fetch
) -> None:
    asked: list[MirrorPath] = []

    def signed(path: MirrorPath) -> str | None:
        asked.append(path)
        return SHA256

    routes = Routes({AT_MIRROR: BODY})
    result = fetch(_fetcher(tmp_path, routes, signed, offline=True))
    assert result.source == "mirror" and result.sha256 == SHA256
    assert asked and set(asked) == {PATH}


@ROUTES
def test_no_signed_row_means_the_publisher_pin_alone_decides(tmp_path: Path, fetch: Fetch) -> None:
    routes = Routes({AT_MIRROR: BODY})
    result = fetch(_fetcher(tmp_path, routes, lambda path: None, offline=True))
    assert result.source == "mirror"


def test_a_sha256_pinned_route_does_not_consult_the_signed_row(tmp_path: Path) -> None:
    from hammunition.manifest.schema import RemoteArtifact

    def never(path: MirrorPath) -> str | None:
        pytest.fail("a sha256 pin was checked against the signed row as well")

    routes = Routes({AT_MIRROR: BODY})
    fetcher = _fetcher(tmp_path, routes, never, offline=True)
    result = fetcher.fetch(RemoteArtifact(url=PUBLISHER, sha256=SHA256), mirror=PATH)
    assert result.source == "mirror"


@pytest.mark.parametrize("fetch", [_md5, _sha1, _etag], ids=["md5", "sha1", "etag"])
def test_a_cached_copy_that_fails_the_signed_sha256_is_dropped_not_served(
    tmp_path: Path, fetch: Fetch
) -> None:
    routes = Routes({AT_MIRROR: BODY})
    fetcher = _fetcher(tmp_path, routes, lambda path: None, offline=True)
    first = fetch(fetcher)
    assert first.source == "mirror"
    # The signed catalogue now says something else: the cache hit must not be served.
    routes.requested.clear()
    fetcher = _fetcher(tmp_path, routes, lambda path: SIGNED, offline=True)
    with pytest.raises(BackendError):
        fetch(fetcher)
    assert routes.requested == [AT_MIRROR]
    assert not list((tmp_path / "cache").glob("*Test.tif"))


@pytest.mark.parametrize("fetch", [_md5, _sha1, _etag], ids=["md5", "sha1", "etag"])
def test_a_cached_copy_that_matches_the_signed_sha256_is_served(
    tmp_path: Path, fetch: Fetch
) -> None:
    routes = Routes({AT_MIRROR: BODY})
    fetch(_fetcher(tmp_path, routes, lambda path: SHA256, offline=True))
    routes.requested.clear()
    again = fetch(_fetcher(tmp_path, routes, lambda path: SHA256, offline=True))
    assert again.from_cache and routes.requested == []
