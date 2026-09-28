# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for :mod:`hammunition.navit_config`.  D-057, task 5."""

from __future__ import annotations

from pathlib import Path

import pytest

from hammunition.navit_config import STOCK, NavitConfigError, rewrite

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
