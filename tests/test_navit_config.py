# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for :mod:`hammunition.navit_config`.  D-057, task 5."""

from __future__ import annotations

from pathlib import Path

import pytest

from hammunition.navit_config import STOCK, NavitConfigError, follow_problem, rewrite

FIXTURE = (Path(__file__).parent / "fixtures" / "navit.xml").read_text()
MAPS = [Path("/usr/local/share/hammunition/data/osm-navit/north-america-us-vermont.bin")]


def test_speech_goes_to_espeak_ng() -> None:
    out = rewrite(FIXTURE, MAPS)
    assert '<speech type="cmdline" data="espeak-ng' in out
    assert "Fix the speech tag" not in out


def test_one_mapset_is_ours_and_enabled_with_each_map() -> None:
    out = rewrite(FIXTURE, MAPS)
    assert f'<map type="binfile" enabled="yes" data="{MAPS[0]}"/>' in out
    assert out.count('<mapset enabled="yes">') == 1


def test_every_other_mapset_is_disabled() -> None:
    out = rewrite(FIXTURE, MAPS)
    assert "$NAVIT_SHAREDIR/maps/*.xml" not in out.split('<mapset enabled="yes">')[1]


def test_no_maps_is_refused() -> None:
    with pytest.raises(NavitConfigError):
        rewrite(FIXTURE, [])


def test_a_stock_file_without_the_anchors_is_refused_by_name() -> None:
    with pytest.raises(NavitConfigError, match="speech"):
        rewrite("<config><navit></navit></config>", MAPS)


def test_two_enabled_mapsets_is_refused_by_name() -> None:
    # A hypothetical stock file that violates Navit's own "only one mapset
    # enabled at a time" convention. Silently keeping the second one enabled
    # alongside ours would produce a config Navit mis-loads; refuse instead.
    stock = (
        "<config><navit>"
        '<speech type="cmdline" data="echo %s" cps="15"/>'
        '<mapset enabled="yes"><map type="binfile" enabled="yes" data="/a.bin"/></mapset>'
        '<mapset enabled="yes"><map type="binfile" enabled="yes" data="/b.bin"/></mapset>'
        "</navit></config>"
    )
    with pytest.raises(NavitConfigError) as exc_info:
        rewrite(stock, MAPS)
    message = str(exc_info.value)
    assert str(STOCK) in message
    assert "2" in message


def test_the_output_is_well_formed_xml() -> None:
    from xml.etree import ElementTree

    ElementTree.fromstring(rewrite(FIXTURE, MAPS).replace("xi:include", "include"))


# ---------------------------------------------------------------------------
# Where Navit opens, and whether it follows the GPS  (bench, 2026-09-28)
# ---------------------------------------------------------------------------

#: A synthetic centre, nowhere in particular.
CENTER = (-72.5, 44.0)


def _navit_open_tag(text: str) -> str:
    start = text.index("<navit ")
    return text[start : text.index(">", start) + 1]


def _gpsd_vehicle(text: str) -> str:
    start = text.index('<vehicle name="Local GPS" profilename="car" enabled="yes"')
    return text[start : text.index(">", start) + 1]


def test_the_center_replaces_the_stock_one_in_lon_lat_order_to_four_places() -> None:
    tag = _navit_open_tag(rewrite(FIXTURE, MAPS, center=CENTER))
    assert 'center="-72.5000 44.0000"' in tag
    assert "11.5666 48.1333" not in tag
    # Only the attribute changes: the rest of the element is the stock one.
    assert 'zoom="256"' in tag and 'default_layout="Car"' in tag


def test_without_a_center_the_stock_one_stays() -> None:
    assert 'center="11.5666 48.1333"' in _navit_open_tag(rewrite(FIXTURE, MAPS))


def test_the_comment_that_explains_center_is_kept() -> None:
    out = rewrite(FIXTURE, MAPS, center=CENTER)
    assert "center= defines which map location Navit will show after first start." in out


def test_a_stock_file_without_a_navit_center_is_refused_by_name() -> None:
    stock = FIXTURE.replace('<navit center="11.5666 48.1333" ', "<navit ")
    with pytest.raises(NavitConfigError, match="center"):
        rewrite(stock, MAPS, center=CENTER)


def test_the_gpsd_vehicle_follows_the_position() -> None:
    out = rewrite(FIXTURE, MAPS)
    assert 'follow="1"' in _gpsd_vehicle(out)
    assert out.count('follow="1"') == FIXTURE.count('follow="1"') + 1


def test_the_commented_out_vehicles_are_left_as_they_are() -> None:
    out = rewrite(FIXTURE, MAPS)
    assert '<!-- <vehicle name="Meins" enabled="yes" source="gpsd://localhost"' in out
    assert "<!-- For SDL, you should add follow" in out
    assert '<vehicle name="Demo" profilename="car" enabled="no" source="demo://"/>' in out


def test_a_vehicle_that_already_follows_is_not_touched() -> None:
    stock = FIXTURE.replace('active="1" source="gpsd://', 'active="1" follow="0" source="gpsd://')
    out = rewrite(stock, MAPS)
    assert 'follow="0"' in _gpsd_vehicle(out)
    assert 'follow="1"' not in _gpsd_vehicle(out)


def _no_gpsd() -> str:
    return FIXTURE.replace(
        'enabled="yes" active="1" source="gpsd://', 'enabled="no" active="1" source="gpsd://'
    )


def _two_gpsd() -> str:
    return FIXTURE.replace(
        '<vehicle name="Demo" profilename="car" enabled="no" source="demo://"/>',
        '<vehicle name="Second" enabled="yes" source="gpsd://otherhost"/>',
    )


def test_one_gpsd_vehicle_has_no_follow_problem() -> None:
    assert follow_problem(FIXTURE) is None


@pytest.mark.parametrize(("stock", "count"), [(_no_gpsd(), "0"), (_two_gpsd(), "2")])
def test_not_exactly_one_gpsd_vehicle_still_writes_the_config_without_follow(
    stock: str, count: str
) -> None:
    """Soft, like the centre (fix round 1, I2): an operator's serial receiver or
    second gpsd vehicle costs them follow, never the whole configuration."""
    problem = follow_problem(stock)
    assert problem is not None
    assert "gpsd" in problem and count in problem
    out = rewrite(stock, MAPS, center=CENTER)
    assert out.count('follow="1"') == stock.count('follow="1"')
    assert f'data="{MAPS[0]}"' in out
    assert 'center="-72.5000 44.0000"' in out


def test_feeding_the_output_back_in_changes_nothing() -> None:
    """Fix round 1, M6: rewriting a rewritten file is a no-op, centre or not."""
    once = rewrite(FIXTURE, MAPS, center=CENTER)
    assert rewrite(once, MAPS, center=CENTER) == once
    plain = rewrite(FIXTURE, MAPS)
    assert rewrite(plain, MAPS) == plain


def test_the_centred_following_output_is_still_well_formed_xml() -> None:
    from xml.etree import ElementTree

    root = ElementTree.fromstring(
        rewrite(FIXTURE, MAPS, center=CENTER).replace("xi:include", "include")
    )
    navit = root.find("navit")
    assert navit is not None
    assert navit.get("center") == "-72.5000 44.0000"
    gps = [v for v in navit.iter("vehicle") if (v.get("source") or "").startswith("gpsd://")]
    assert [v.get("follow") for v in gps] == ["1"]
