# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The browser map's infrastructure layer: the tilemaker profile it adds and
the style that draws it.  D-075.

The Lua and the config are text the converter writes; tilemaker itself is
not installed on the development host or in CI, so its run on a real
extract is recorded in D-075, not repeated here.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hammunition import map_style

KIT_CONFIG = json.dumps({"layers": {"place": {"minzoom": 0, "maxzoom": 14}}, "settings": {}})


def test_the_config_is_the_kits_plus_the_infra_layer() -> None:
    config = json.loads(map_style.infra_config(KIT_CONFIG))
    assert config["layers"] == {
        "place": {"minzoom": 0, "maxzoom": 14},
        "infra": {"minzoom": 10, "maxzoom": 14},
    }


@pytest.mark.parametrize("text", ["stand-in", "[]", '{"layers": []}', '{"layers": {"infra": {}}}'])
def test_a_config_that_is_not_the_profiles_is_refused(text: str) -> None:
    with pytest.raises(ValueError, match="not the profile's JSON"):
        map_style.infra_config(text)


def test_the_lua_runs_the_kits_profile_unchanged_then_adds_the_layer() -> None:
    lua = map_style.infra_lua(Path("/usr/local/share/hammunition/data/vector-map-kit/p.lua"))
    assert lua.splitlines()[0].startswith("-- Hammunition (D-075)")
    assert "dofile([==[/usr/local/share/hammunition/data/vector-map-kit/p.lua]==])" in lua
    assert 'Layer("infra", false)' in lua and 'LayerAsCentroid("infra")' in lua
    assert 'AttributeNumeric("voltage_kv"' in lua
    for kind in ('"substation"', '"plant"', '"line"', '"mast"', '"fire_hydrant"', '"pipeline"'):
        assert kind in lua


def test_a_path_that_would_close_the_lua_string_is_refused() -> None:
    with pytest.raises(ValueError, match="cannot be quoted"):
        map_style.infra_lua(Path("/kit/]==]os.execute('x')--.lua"))


def test_the_voltage_ramp_is_open_infrastructure_maps() -> None:
    """``voltage_scale`` in web/src/style/style_oim_power.ts at 5f20a29a."""
    assert map_style.VOLTAGE_SCALE == (
        (None, "#7A7A85"),
        (10, "#6E97B8"),
        (25, "#55B555"),
        (52, "#B59F10"),
        (132, "#B55D00"),
        (220, "#C73030"),
        (310, "#B54EB2"),
        (550, "#00C1CF"),
    )
    step = map_style.voltage_color()
    assert step[:3] == ["step", ["to-number", ["coalesce", ["get", "voltage_kv"], 0]], "#7A7A85"]
    assert step[3:5] == [9.99, "#6E97B8"] and step[-2:] == [549.99, "#00C1CF"]


def test_every_style_layer_draws_the_infra_source_layer() -> None:
    layers = map_style.style_layers()
    assert layers and len({layer["id"] for layer in layers}) == len(layers)
    for layer in layers:
        assert layer["source"] == "openmaptiles"
        assert layer["source-layer"] == "infra"
        assert layer["id"].startswith("infra-")
        assert layer["minzoom"] >= 10
    lines = next(layer for layer in layers if layer["id"] == "infra-power-lines")
    assert lines["paint"]["line-color"] == map_style.voltage_color()
    json.dumps(layers)  # the page embeds them as JSON


def test_the_notice_is_open_infrastructure_maps_bsd_3_clause() -> None:
    text = map_style.NOTICE.read_text()
    assert "Copyright Open Infrastructure Map contributors" in text
    assert "Redistribution and use in source and binary forms" in text
    assert "voltage colour ramp" in text
    assert map_style.CREDIT == "infrastructure style after Open Infrastructure Map, BSD-3-Clause"
