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
    _previous,
    load_pins,
    newest_snapshots,
    region_ids,
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


def test_previous_yearly_crosses_the_century() -> None:
    assert _previous("yearly", "000101") == "990101"


def test_previous_monthly_crosses_the_century() -> None:
    assert _previous("monthly", "000101") == "991201"


def test_previous_monthly_ordinary_month() -> None:
    assert _previous("monthly", "270101") == "261201"


def test_a_dead_rtc_falls_back_across_the_century() -> None:
    probe = FakeProbe(
        {_url("000101"): (404, 0, None), _url("990101"): (200, 44_000_000, None)},
        {_url("990101") + ".md5": f"{MD5}  vermont-990101.osm.pbf\n"},
    )
    got = resolve(VT, "yearly", today=date(2000, 1, 5), pins={}, probe=probe)
    assert got.snapshot == "990101"


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


def test_a_head_with_no_content_length_is_refused_naming_the_file() -> None:
    """Fix round 1, item 9: size 0 would otherwise surface only at the 1 MiB cap."""
    probe = FakeProbe({_url("260101"): (200, 0, None)}, {_url("260101") + ".md5": f"{MD5}  x\n"})
    with pytest.raises(GeofabrikError, match=re.escape(f"{VT}-260101.osm.pbf")):
        resolve(VT, "yearly", today=date(2026, 9, 27), pins={}, probe=probe)


# --- region_ids --------------------------------------------------------------


def test_region_ids_from_the_index() -> None:
    index = (
        '{"features": [{"properties": {"urls": {"pbf": '
        '"https://download.geofabrik.de/north-america/us/vermont-latest.osm.pbf"}}}, '
        '{"properties": {"urls": {"pbf": '
        '"https://download.geofabrik.de/europe-latest.osm.pbf"}}}]}'
    )
    assert region_ids(index) == ["europe", "north-america/us/vermont"]


def test_region_ids_deduplicates_and_sorts() -> None:
    index = (
        '{"features": ['
        '{"properties": {"urls": {"pbf": '
        '"https://download.geofabrik.de/north-america/us/vermont-latest.osm.pbf"}}},'
        '{"properties": {"urls": {"pbf": '
        '"https://download.geofabrik.de/north-america/us/vermont-latest.osm.pbf"}}},'
        '{"properties": {"urls": {"pbf": '
        '"https://download.geofabrik.de/africa-latest.osm.pbf"}}}'
        "]}"
    )
    assert region_ids(index) == ["africa", "north-america/us/vermont"]


def test_region_ids_ignores_a_feature_with_no_pbf_url() -> None:
    index = '{"features": [{"properties": {"urls": {}}}]}'
    assert region_ids(index) == []


def test_region_ids_refuses_invalid_json() -> None:
    with pytest.raises(GeofabrikError, match="not valid JSON"):
        region_ids("not json")


# --- newest_snapshots ---------------------------------------------------------


def test_newest_snapshots_keys_by_slug_and_keeps_the_greatest() -> None:
    pins = {
        (VT, "260101"): Pin(VT, "260101", 1, SHA),
        (VT, "260901"): Pin(VT, "260901", 1, SHA),
    }
    assert newest_snapshots(pins) == {"north-america-us-vermont": "260901"}
