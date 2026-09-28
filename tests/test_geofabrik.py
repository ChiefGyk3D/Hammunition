# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Which Geofabrik file a region and freshness mode mean, and how it is verified."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest

from hammunition.geofabrik import (
    GeofabrikError,
    Pin,
    RegionFile,
    load_pins,
    resolve,
    snapshot_for,
)

VT = "north-america/us/vermont"
MD5 = "f96442116ca488f5e2f8647166d20bb0"
SHA = "a" * 64


class FakeProbe:
    def __init__(
        self, heads: dict[str, tuple[int, int, str | None]], texts: dict[str, str]
    ) -> None:
        self.heads, self.texts = heads, texts
        self.seen: list[str] = []

    def head(self, url: str) -> tuple[int, int, str | None]:
        self.seen.append(url)
        return self.heads.get(url, (404, 0, None))

    def text(self, url: str) -> str:
        if url not in self.texts:
            raise GeofabrikError(f"{url}: 404")
        return self.texts[url]


def _url(snapshot: str) -> str:
    return f"https://download.geofabrik.de/{VT}-{snapshot}.osm.pbf"


def test_snapshot_names() -> None:
    assert snapshot_for("yearly", date(2026, 9, 27)) == "260101"
    assert snapshot_for("monthly", date(2026, 9, 27)) == "260901"


def test_yearly_pinned_region_uses_the_pin_and_asks_nothing() -> None:
    pins = {(VT, "260101"): Pin(VT, "260101", 45_000_000, SHA)}
    probe = FakeProbe({}, {})
    got = resolve(VT, "yearly", today=date(2026, 9, 27), pins=pins, probe=probe)
    assert got == RegionFile(VT, "260101", _url("260101"), 45_000_000, SHA, None)
    assert got.verified_by == "sha256, pinned by Hammunition"
    assert probe.seen == []


def test_unpinned_region_uses_geofabriks_md5_and_says_so() -> None:
    probe = FakeProbe(
        {_url("260101"): (200, 44_000_000, None)},
        {_url("260101") + ".md5": f"{MD5}  vermont-260101.osm.pbf\n"},
    )
    got = resolve(VT, "yearly", today=date(2026, 9, 27), pins={}, probe=probe)
    assert got.sha256 is None and got.md5 == MD5 and got.size == 44_000_000
    assert got.verified_by == "MD5 from Geofabrik only; not pinned"


def test_latest_resolves_the_redirect_to_a_dated_file() -> None:
    latest = f"https://download.geofabrik.de/{VT}-latest.osm.pbf"
    probe = FakeProbe(
        {latest: (302, 0, _url("260926")), _url("260926"): (200, 45_951_595, None)},
        {_url("260926") + ".md5": f"{MD5}  vermont-260926.osm.pbf\n"},
    )
    got = resolve(VT, "latest", today=date(2026, 9, 27), pins={}, probe=probe)
    assert got.snapshot == "260926" and got.url == _url("260926") and got.md5 == MD5


def test_a_snapshot_not_yet_published_falls_back_to_the_previous_one() -> None:
    probe = FakeProbe(
        {_url("261001"): (404, 0, None), _url("260901"): (200, 44_000_000, None)},
        {_url("260901") + ".md5": f"{MD5}  vermont-260901.osm.pbf\n"},
    )
    got = resolve(VT, "monthly", today=date(2026, 10, 1), pins={}, probe=probe)
    assert got.snapshot == "260901"


def test_an_unknown_region_is_refused_naming_the_file() -> None:
    probe = FakeProbe({}, {})
    with pytest.raises(GeofabrikError, match=re.escape("north-america/us/atlantis-260101.osm.pbf")):
        resolve(
            "north-america/us/atlantis", "yearly", today=date(2026, 9, 27), pins={}, probe=probe
        )


def test_an_md5_file_that_is_not_an_md5_is_refused() -> None:
    probe = FakeProbe(
        {_url("260101"): (200, 1, None)},
        {_url("260101") + ".md5": "<html>not found</html>"},
    )
    with pytest.raises(GeofabrikError, match="md5"):
        resolve(VT, "yearly", today=date(2026, 9, 27), pins={}, probe=probe)


def test_load_pins(tmp_path: Path) -> None:
    f = tmp_path / "pins.yaml"
    f.write_text(
        f"pins:\n  - region: {VT}\n    snapshot: '260101'\n    size: 45000000\n    sha256: {SHA}\n"
    )
    assert load_pins(f) == {(VT, "260101"): Pin(VT, "260101", 45_000_000, SHA)}


def test_slug() -> None:
    assert RegionFile(VT, "260101", _url("260101"), 1, SHA, None).slug == "north-america-us-vermont"
