# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The install plan's publisher HEAD cache."""

from __future__ import annotations

import json
import stat
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from pathlib import Path

import pytest

from hammunition.copernicus import CachingTileProbe, HEAD_CACHE_TTL

URL = "https://copernicus-dem-30m.s3.amazonaws.com/test-tile"
OK = (200, 39_000_000, '"0123456789abcdef0123456789abcdef"')


class FakeProbe:
    def __init__(self, result: tuple[int, int, str | None] | Exception = OK) -> None:
        self.result = result
        self.asked: list[str] = []

    def head(self, url: str) -> tuple[int, int, str | None]:
        self.asked.append(url)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def test_a_second_head_within_the_ttl_uses_the_cache(tmp_path: Path) -> None:
    now = [100]
    inner = FakeProbe()
    probe = CachingTileProbe(inner, tmp_path, now=lambda: now[0])

    assert probe.head(URL) == OK
    assert probe.head(URL) == OK
    assert inner.asked == [URL]


def test_an_expired_head_is_asked_again(tmp_path: Path) -> None:
    now = [100]
    inner = FakeProbe()
    probe = CachingTileProbe(inner, tmp_path, now=lambda: now[0])
    probe.head(URL)
    now[0] += HEAD_CACHE_TTL

    assert probe.head(URL) == OK
    assert inner.asked == [URL, URL]


@pytest.mark.parametrize("result", [(404, 0, None), RuntimeError("offline")])
def test_non_200_answers_and_exceptions_are_not_cached(
    tmp_path: Path, result: tuple[int, int, str | None] | Exception
) -> None:
    inner = FakeProbe(result)
    probe = CachingTileProbe(inner, tmp_path, now=lambda: 100)

    for _ in range(2):
        context = pytest.raises(RuntimeError) if isinstance(result, RuntimeError) else nullcontext()
        with context:
            probe.head(URL)
    assert inner.asked == [URL, URL]


def test_a_corrupt_file_is_ignored_and_rewritten(tmp_path: Path) -> None:
    cache = tmp_path / "tile-heads.json"
    cache.write_text("{")
    probe = CachingTileProbe(FakeProbe(), tmp_path, now=lambda: 100)

    assert probe.head(URL) == OK
    probe.flush()

    record = json.loads(cache.read_text())[URL]
    assert record == {"status": 200, "size": OK[1], "etag": OK[2], "at": 100}


def test_flushed_entries_survive_a_new_probe(tmp_path: Path) -> None:
    first_inner = FakeProbe()
    first = CachingTileProbe(first_inner, tmp_path, now=lambda: 100)
    first.head(URL)
    first.flush()
    second_inner = FakeProbe()
    second = CachingTileProbe(second_inner, tmp_path, now=lambda: 101)

    assert second.head(URL) == OK
    assert second_inner.asked == []


def test_many_threads_can_ask_and_flush_a_valid_private_cache(tmp_path: Path) -> None:
    probe = CachingTileProbe(FakeProbe(), tmp_path, now=lambda: 100)

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert list(pool.map(probe.head, [URL] * 8)) == [OK] * 8
    probe.flush()

    cache = tmp_path / "tile-heads.json"
    assert json.loads(cache.read_text())[URL]["status"] == 200
    assert stat.S_IMODE(cache.stat().st_mode) == 0o600


def test_the_cache_drops_the_oldest_entries_over_its_limit(tmp_path: Path) -> None:
    now = [0]
    probe = CachingTileProbe(FakeProbe(), tmp_path, now=lambda: now[0])
    for index in range(20_001):
        now[0] = index
        probe.head(f"{URL}/{index}")

    probe.flush()
    entries = json.loads((tmp_path / "tile-heads.json").read_text())
    assert len(entries) == 20_000
    assert f"{URL}/0" not in entries
