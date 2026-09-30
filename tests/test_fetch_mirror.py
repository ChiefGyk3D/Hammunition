# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The verified fetch tries a LAN mirror first.  D-070.

Written to the failures, as ``tests/test_fetch.py`` is: a mirror that is
missing the file, sends the wrong bytes, sends too many, or does not answer
at all. Each must end with the publisher's verified copy, or a refusal that
names both attempts, and never with the mirror's bytes in the cache.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from typing import IO

import pytest

from hammunition.backends import BackendError
from hammunition.fetch import (
    Fetcher,
    MirrorPath,
    TransportUnreachable,
    VerificationError,
    mirror_url,
)
from hammunition.manifest.schema import RemoteArtifact

PAYLOAD = b"public map data\n"
DIGEST = hashlib.sha256(PAYLOAD).hexdigest()
MD5 = hashlib.md5(PAYLOAD, usedforsecurity=False).hexdigest()
PUBLISHER = "https://download.example.invalid/north-america/us/vermont-260101.osm.pbf"
MIRROR = "http://bunker.lan:8080/"
PATH = MirrorPath("osm-regions", "north-america/us/vermont")
AT_MIRROR = "http://bunker.lan:8080/osm-regions/north-america/us/vermont"
ARTIFACT = RemoteArtifact(url=PUBLISHER, sha256=DIGEST)


class Routes:
    """Serves bytes per URL, or raises what a URL is set to raise."""

    def __init__(self, routes: dict[str, bytes | Exception]) -> None:
        self.routes = routes
        self.requested: list[str] = []

    @contextmanager
    def open(self, url: str) -> Iterator[IO[bytes]]:
        self.requested.append(url)
        answer = self.routes.get(url, BackendError(f"{url} returned HTTP 404 (Not Found)"))
        if isinstance(answer, Exception):
            raise answer
        yield BytesIO(answer)


def _fetcher(tmp_path: Path, routes: Routes, mirror: str | None = MIRROR) -> Fetcher:
    return Fetcher(tmp_path / "cache", transport=routes, mirror=mirror)


def _cache(tmp_path: Path) -> list[str]:
    return sorted(p.name for p in (tmp_path / "cache").iterdir())


def test_the_mirror_path_is_unit_then_name_under_the_base() -> None:
    assert mirror_url(MIRROR, PATH) == AT_MIRROR
    assert mirror_url("http://bunker.lan:8080", PATH) == AT_MIRROR
    assert (
        mirror_url("http://nas.lan/bunker/", MirrorPath("country-files", "bigcty 2026.zip"))
        == "http://nas.lan/bunker/country-files/bigcty%202026.zip"
    )


@pytest.mark.parametrize(
    ("unit", "name"),
    [
        ("osm-regions", "../etc/passwd"),
        ("osm-regions", "a//b"),
        ("", "x"),
        ("a/b", "x"),
        ("osm-regions", ""),
        ("osm-regions", "a/./b"),
    ],
)
def test_a_mirror_path_that_could_escape_its_unit_is_refused(unit: str, name: str) -> None:
    with pytest.raises(BackendError, match="mirror"):
        MirrorPath(unit, name)


def test_a_mirror_hit_never_asks_the_publisher(tmp_path: Path) -> None:
    routes = Routes({AT_MIRROR: PAYLOAD, PUBLISHER: PAYLOAD})
    result = _fetcher(tmp_path, routes).fetch(ARTIFACT, mirror=PATH)
    assert routes.requested == [AT_MIRROR]
    assert (result.source, result.url, result.mirror_failure) == ("mirror", AT_MIRROR, None)
    assert result.path.read_bytes() == PAYLOAD


@pytest.mark.parametrize(
    ("answer", "why"),
    [
        (BackendError(f"{AT_MIRROR} returned HTTP 404 (Not Found)"), "404"),
        (b"tampered bytes\n", "does not match"),
        (b"x" * 4096, "limit"),
    ],
)
def test_any_mirror_failure_falls_back_to_the_publisher_and_the_same_digest(
    tmp_path: Path, answer: bytes | Exception, why: str
) -> None:
    routes = Routes({AT_MIRROR: answer, PUBLISHER: PAYLOAD})
    fetcher = _fetcher(tmp_path, routes)
    result = fetcher.fetch(ARTIFACT, mirror=PATH, max_bytes=1024)
    assert routes.requested == [AT_MIRROR, PUBLISHER]
    assert (result.source, result.url, result.sha256) == ("publisher", PUBLISHER, DIGEST)
    assert result.mirror_failure is not None and why in result.mirror_failure
    assert _cache(tmp_path) == [result.path.name]  # the mirror's bytes are gone


def test_a_mirror_that_does_not_answer_is_not_asked_again_this_run(tmp_path: Path) -> None:
    other = RemoteArtifact(url=PUBLISHER + ".2", sha256=DIGEST)
    routes = Routes(
        {
            AT_MIRROR: TransportUnreachable("connection refused"),
            PUBLISHER: PAYLOAD,
            PUBLISHER + ".2": PAYLOAD,
        }
    )
    fetcher = _fetcher(tmp_path, routes)
    fetcher.fetch(ARTIFACT, mirror=PATH)
    second = fetcher.fetch(other, mirror=MirrorPath("osm-regions", "x"))
    assert routes.requested == [AT_MIRROR, PUBLISHER, PUBLISHER + ".2"]
    assert second.source == "publisher"
    assert second.mirror_failure is not None and "did not answer" in second.mirror_failure


def test_a_404_does_not_stop_the_mirror_being_asked_for_the_next_file(tmp_path: Path) -> None:
    routes = Routes({PUBLISHER: PAYLOAD, "http://bunker.lan:8080/osm-regions/x": PAYLOAD})
    fetcher = _fetcher(tmp_path, routes)
    fetcher.fetch(ARTIFACT, mirror=PATH)
    other = RemoteArtifact(url=PUBLISHER + ".2", sha256=DIGEST)
    assert fetcher.fetch(other, mirror=MirrorPath("osm-regions", "x")).source == "mirror"


def test_when_both_fail_the_refusal_names_both(tmp_path: Path) -> None:
    routes = Routes({AT_MIRROR: b"wrong\n", PUBLISHER: b"also wrong\n"})
    with pytest.raises(VerificationError) as exc:
        _fetcher(tmp_path, routes).fetch(ARTIFACT, mirror=PATH)
    assert PUBLISHER in str(exc.value) and AT_MIRROR in str(exc.value)
    assert _cache(tmp_path) == []


def test_without_a_mirror_or_a_path_only_the_publisher_is_asked(tmp_path: Path) -> None:
    routes = Routes({PUBLISHER: PAYLOAD})
    assert _fetcher(tmp_path, routes, mirror=None).fetch(ARTIFACT, mirror=PATH).source == (
        "publisher"
    )
    routes2 = Routes({PUBLISHER: PAYLOAD})
    assert _fetcher(tmp_path / "b", routes2).fetch(ARTIFACT).source == "publisher"
    assert routes.requested == [PUBLISHER] and routes2.requested == [PUBLISHER]


def test_a_verified_cached_copy_asks_nobody(tmp_path: Path) -> None:
    routes = Routes({AT_MIRROR: PAYLOAD})
    fetcher = _fetcher(tmp_path, routes)
    fetcher.fetch(ARTIFACT, mirror=PATH)
    again = fetcher.fetch(ARTIFACT, mirror=PATH)
    assert (again.source, again.from_cache, again.url) == ("cache", True, None)
    assert routes.requested == [AT_MIRROR]


def test_sources_for_lists_the_order_the_fetch_will_try(tmp_path: Path) -> None:
    fetcher = _fetcher(tmp_path, Routes({}))
    assert fetcher.sources_for(PUBLISHER, PATH) == (("mirror", AT_MIRROR), ("publisher", PUBLISHER))
    assert fetcher.sources_for(PUBLISHER, None) == (("publisher", PUBLISHER),)
    plain = _fetcher(tmp_path, Routes({}), mirror=None)
    assert plain.sources_for(PUBLISHER, PATH) == (("publisher", PUBLISHER),)


# -- the MD5 path (unpinned regions and tiles) -------------------------------


def test_md5_mirror_hit(tmp_path: Path) -> None:
    routes = Routes({AT_MIRROR: PAYLOAD})
    result = _fetcher(tmp_path, routes).fetch_md5(
        PUBLISHER, MD5, expected_size=len(PAYLOAD), mirror=PATH
    )
    assert (result.source, routes.requested) == ("mirror", [AT_MIRROR])


@pytest.mark.parametrize(
    ("answer", "why"),
    [(PAYLOAD + b"more", "size"), (b"X" * len(PAYLOAD), "md5")],
)
def test_md5_mirror_with_the_wrong_size_or_hash_falls_back(
    tmp_path: Path, answer: bytes, why: str
) -> None:
    routes = Routes({AT_MIRROR: answer, PUBLISHER: PAYLOAD})
    result = _fetcher(tmp_path, routes).fetch_md5(
        PUBLISHER, MD5, expected_size=len(PAYLOAD), mirror=PATH
    )
    assert (result.source, routes.requested) == ("publisher", [AT_MIRROR, PUBLISHER])
    assert result.mirror_failure is not None and why in result.mirror_failure
    assert _cache(tmp_path) == [result.path.name]


def test_md5_when_both_fail_nothing_is_left(tmp_path: Path) -> None:
    routes = Routes({AT_MIRROR: b"X" * len(PAYLOAD), PUBLISHER: b"Y" * len(PAYLOAD)})
    with pytest.raises(VerificationError, match="mirror"):
        _fetcher(tmp_path, routes).fetch_md5(
            PUBLISHER, MD5, expected_size=len(PAYLOAD), mirror=PATH
        )
    assert _cache(tmp_path) == []
