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
    current_pinned_snapshots,
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


# --- current_pinned_snapshots (fix round 1, I1) -------------------------------
#
# `update` must compare an installed region against the snapshot the
# station's freshness mode would resolve *today*, restricted to what the
# pin list actually carries -- not the newest pin of any snapshot. Comparing
# against the newest pin of any snapshot reported a yearly install at
# 260101 behind 260901 (a pin from a different period) forever, since
# `install` never chases a monthly-shaped pin under yearly mode.


def test_current_pinned_snapshots_yearly_ignores_a_pin_from_another_period() -> None:
    pins = {
        (VT, "260101"): Pin(VT, "260101", 1, SHA),
        (VT, "260901"): Pin(VT, "260901", 1, SHA),
    }
    got = current_pinned_snapshots("yearly", date(2026, 9, 28), pins, [VT])
    assert got == {"north-america-us-vermont": "260101"}


def test_current_pinned_snapshots_yearly_follows_the_year_over() -> None:
    pins = {(VT, "270101"): Pin(VT, "270101", 1, SHA)}
    got = current_pinned_snapshots("yearly", date(2027, 1, 2), pins, [VT])
    assert got == {"north-america-us-vermont": "270101"}


def test_current_pinned_snapshots_monthly_falls_back_one_period_like_resolve() -> None:
    """No October pin yet: falls back to September, same as `resolve()`."""
    pins = {(VT, "260901"): Pin(VT, "260901", 1, SHA)}
    got = current_pinned_snapshots("monthly", date(2026, 10, 2), pins, [VT])
    assert got == {"north-america-us-vermont": "260901"}


def test_current_pinned_snapshots_latest_takes_the_newest_pin_overall() -> None:
    pins = {
        (VT, "260101"): Pin(VT, "260101", 1, SHA),
        (VT, "260901"): Pin(VT, "260901", 1, SHA),
    }
    got = current_pinned_snapshots("latest", date(2026, 9, 28), pins, [VT])
    assert got == {"north-america-us-vermont": "260901"}


def test_current_pinned_snapshots_a_region_with_no_matching_pin_is_absent() -> None:
    # Neither today's yearly candidate (260101) nor its one-period-back
    # fallback (250101) is pinned; a two-year-stale 240101 pin does not count.
    pins = {(VT, "240101"): Pin(VT, "240101", 1, SHA)}
    got = current_pinned_snapshots("yearly", date(2026, 9, 28), pins, [VT])
    assert got == {}


# --- region_ids: fail loudly on a malformed feature, not AttributeError -------
# (fix round 1, M6)


def test_region_ids_raises_geofabrik_error_on_null_properties() -> None:
    index = '{"features": [{"properties": null}]}'
    with pytest.raises(GeofabrikError, match="properties"):
        region_ids(index)


def test_region_ids_raises_geofabrik_error_on_missing_properties() -> None:
    index = '{"features": [{"type": "Feature"}]}'
    with pytest.raises(GeofabrikError, match="properties"):
        region_ids(index)


def test_region_ids_raises_geofabrik_error_on_null_urls() -> None:
    index = '{"features": [{"properties": {"id": "x", "urls": null}}]}'
    with pytest.raises(GeofabrikError, match="urls"):
        region_ids(index)


def test_region_ids_raises_geofabrik_error_on_missing_urls() -> None:
    index = '{"features": [{"properties": {"id": "x"}}]}'
    with pytest.raises(GeofabrikError, match="urls"):
        region_ids(index)


# A trimmed sample of the real index-v1-nogeom.json (fetched live 2026-09-28,
# https://download.geofabrik.de/index-v1-nogeom.json, two of its 555
# features): extra fields (`iso3166-2`, `parent`, `name`, `shp`,
# `pbf-internal`, `taginfo`, `updates`) alongside `urls.pbf`, and no
# `geometry` key -- the shape `maps regions` now fetches instead of the
# 3.79 MB `index-v1.json` (M6).
_NOGEOM_SAMPLE = """
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "properties": {
        "id": "act",
        "parent": "australia",
        "name": "Australian Capital Territory",
        "urls": {
          "pbf": "https://download.geofabrik.de/australia-oceania/australia/act-latest.osm.pbf",
          "shp": "https://download.geofabrik.de/australia-oceania/australia/act-latest-free.shp.zip",
          "pbf-internal": "https://osm-internal.download.geofabrik.de/australia-oceania/australia/act-latest-internal.osm.pbf",
          "history": "https://osm-internal.download.geofabrik.de/australia-oceania/australia/act-internal.osh.pbf",
          "taginfo": "https://taginfo.geofabrik.de/australia-oceania:australia:act",
          "updates": "https://download.geofabrik.de/australia-oceania/australia/act-updates"
        }
      }
    },
    {
      "type": "Feature",
      "properties": {
        "id": "us/vermont",
        "parent": "north-america",
        "iso3166-2": ["US-VT"],
        "name": "us/vermont",
        "urls": {
          "pbf": "https://download.geofabrik.de/north-america/us/vermont-latest.osm.pbf",
          "shp": "https://download.geofabrik.de/north-america/us/vermont-latest-free.shp.zip",
          "pbf-internal": "https://osm-internal.download.geofabrik.de/north-america/us/vermont-latest-internal.osm.pbf",
          "history": "https://osm-internal.download.geofabrik.de/north-america/us/vermont-internal.osh.pbf",
          "taginfo": "https://taginfo.geofabrik.de/north-america:us:vermont",
          "updates": "https://download.geofabrik.de/north-america/us/vermont-updates"
        }
      }
    }
  ]
}
"""


def test_region_ids_parses_the_real_nogeom_shape() -> None:
    assert region_ids(_NOGEOM_SAMPLE) == [
        "australia-oceania/australia/act",
        "north-america/us/vermont",
    ]
