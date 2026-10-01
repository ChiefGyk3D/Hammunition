# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The browser map's infrastructure layer: the tilemaker profile that adds it
and the style that draws it.  D-075.

**The tiles.** tilemaker 3.0 runs the kit's OpenMapTiles profile
(``vector-map-kit``, D-071) unchanged, through a wrapper Lua that
``dofile``-s it and then adds one ``infra`` layer at zoom 10 to 14: power
lines, cables, substations, plants and generators; telecom masts and
exchanges; pipelines; water works, wastewater plants, pumping stations,
water towers and wells; hydrants, sirens, ambulance stations, defibrillators
and assembly points. The spike measured the wrapper on Delaware: 20,113,393
bytes to 20,659,287 (+2.7 %), the ``infra`` layer listed in the metadata.
The config is the kit's plus that one layer. Both files are text the
converter writes into its working directory as the operator
(:mod:`hammunition.backends.pmtiles`); the kit's own files are never changed.

**The style.** Layers written here for that source layer, drawn over OSM
Bright: power lines and power points coloured by Open Infrastructure Map's
voltage ramp, everything else in colours of our own. OIM's style itself
cannot be used: it is TypeScript reading fields its PostGIS views compute
(the spike). The ramp is OIM's ``voltage_scale``, used under its
BSD-3-Clause licence, whose notice is :data:`NOTICE`, shipped beside this
module and served beside the map.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

__all__ = [
    "CREDIT",
    "INFRA_LAYER",
    "NOTICE",
    "VOLTAGE_SCALE",
    "infra_config",
    "infra_lua",
    "style_layers",
    "voltage_color",
]

INFRA_LAYER = "infra"
#: Zoom 10 to 14, as the spike measured it.
INFRA_ZOOM = {"minzoom": 10, "maxzoom": 14}
#: Open Infrastructure Map's BSD-3-Clause notice, verbatim, with what was taken.
NOTICE = Path(__file__).resolve().parent / "LICENSE.openinframap"
#: Shown in the map's credit whenever the page draws the infra layer.
CREDIT = "infrastructure style after Open Infrastructure Map, BSD-3-Clause"

#: ``voltage_scale`` in Open Infrastructure Map's web/src/style/style_oim_power.ts
#: at commit 5f20a29a (2026-09-24): kV from which each colour applies.
VOLTAGE_SCALE: tuple[tuple[int | None, str], ...] = (
    (None, "#7A7A85"),
    (10, "#6E97B8"),
    (25, "#55B555"),
    (52, "#B59F10"),
    (132, "#B55D00"),
    (220, "#C73030"),
    (310, "#B54EB2"),
    (550, "#00C1CF"),
)


def infra_config(kit_config: str) -> str:
    """The kit's ``config-openmaptiles.json`` with the ``infra`` layer added,
    or ValueError when it is not that profile's JSON."""
    try:
        config: Any = json.loads(kit_config)
    except json.JSONDecodeError:
        config = None
    layers = config.get("layers") if isinstance(config, dict) else None
    if not isinstance(layers, dict) or not layers or INFRA_LAYER in layers:
        raise ValueError(
            "config-openmaptiles.json is not the profile's JSON (an object whose "
            "`layers` names the OpenMapTiles layers, and no `infra` among them)"
        )
    layers[INFRA_LAYER] = dict(INFRA_ZOOM)
    return json.dumps(config, indent=1) + "\n"


_LUA = """\
-- Hammunition (D-075): the OpenMapTiles profile plus one "infra" layer,
-- after Open Infrastructure Map's tag selection (BSD-3-Clause; see
-- LICENSE.openinframap beside the engine's map_style module). Written by the
-- tilemaker-pmtiles converter; the kit's own profile runs unchanged first.
dofile([==[__PROCESS__]==])

local omt_node = node_function
local omt_way = way_function

for _, k in ipairs({ "power", "man_made", "emergency", "tower:type", "telecom", "pipeline" }) do
\ttable.insert(node_keys, k)
end

local function infra_class()
\tlocal p = Find("power")
\tif p == "substation" or p == "plant" or p == "generator" then return "power", p end
\tif p == "line" or p == "minor_line" or p == "cable" then return "power", p end
\tlocal m = Find("man_made")
\tif m == "mast" or m == "communications_tower" or (m == "tower" and Find("tower:type") == "communication") then
\t\treturn "telecoms", "mast"
\tend
\tlocal t = Find("telecom")
\tif t == "exchange" or t == "central_office" or Find("building") == "data_center" then
\t\treturn "telecoms", "exchange"
\tend
\tif m == "pipeline" then return "pipeline", Find("substance") end
\tif m == "water_works" or m == "wastewater_plant" or m == "pumping_station" or m == "water_tower" or m == "water_well" then
\t\treturn "water", m
\tend
\tlocal e = Find("emergency")
\tif e == "fire_hydrant" or e == "siren" or e == "ambulance_station" or e == "defibrillator" or e == "assembly_point" then
\t\treturn "emergency", e
\tend
\treturn nil
end

local function attrs(c, s)
\tAttribute("class", c)
\tAttribute("subclass", s or "")
\tlocal kv = tonumber(Find("voltage"):match("^%s*([%d%.]+)") or "")
\tif kv then AttributeNumeric("voltage_kv", kv / 1000) end
\tfor _, k in ipairs({ "operator", "name", "plant:source", "generator:source" }) do
\t\tlocal v = Find(k)
\t\tif v ~= "" then Attribute(k, v) end
\tend
end

function node_function()
\tomt_node()
\tlocal c, s = infra_class()
\tif c then
\t\tLayer("infra", false)
\t\tattrs(c, s)
\tend
end

function way_function()
\tomt_way()
\tlocal c, s = infra_class()
\tif c then
\t\tif s == "line" or s == "minor_line" or s == "cable" or c == "pipeline" then
\t\t\tLayer("infra", false)
\t\telse
\t\t\tLayerAsCentroid("infra")
\t\tend
\t\tattrs(c, s)
\tend
end
"""


def infra_lua(process: Path) -> str:
    """The wrapper profile, running the kit's *process* Lua by its absolute
    path. A path that would end Lua's long bracket is refused."""
    text = str(process)
    if "]==]" in text or "\n" in text:
        raise ValueError(f"{text!r} cannot be quoted in a Lua long string")
    return _LUA.replace("__PROCESS__", text)


def voltage_color() -> list[Any]:
    """OIM's step function over ``voltage_kv``, as a MapLibre expression:
    each threshold 0.01 kV below the scale's, as OIM writes it."""
    expression: list[Any] = ["step", ["to-number", ["coalesce", ["get", "voltage_kv"], 0]]]
    for threshold, colour in VOLTAGE_SCALE:
        if threshold is not None:
            expression.append(round(threshold - 0.01, 2))
        expression.append(colour)
    return expression


def _layer(
    ident: str, kind: str, minzoom: int, where: list[Any], paint: dict[str, Any]
) -> dict[str, Any]:
    return {
        "id": f"infra-{ident}",
        "type": kind,
        "source": "openmaptiles",
        "source-layer": INFRA_LAYER,
        "minzoom": minzoom,
        "filter": where,
        "paint": paint,
    }


def _class(name: str) -> list[Any]:
    return ["==", ["get", "class"], name]


_LINES = ["in", ["get", "subclass"], ["literal", ["line", "minor_line", "cable"]]]


def style_layers() -> list[dict[str, Any]]:
    """The infra source layer's style layers, drawn above OSM Bright's."""
    width = ["interpolate", ["linear"], ["zoom"], 10, 0.8, 14, 2.5]
    return [
        _layer(
            "pipelines",
            "line",
            10,
            _class("pipeline"),
            {"line-color": "#8B6F47", "line-width": width, "line-dasharray": [3, 2]},
        ),
        _layer(
            "power-lines",
            "line",
            10,
            ["all", _class("power"), _LINES],
            {"line-color": voltage_color(), "line-width": width},
        ),
        _layer(
            "power-points",
            "circle",
            11,
            ["all", _class("power"), ["!", _LINES]],
            {
                "circle-color": voltage_color(),
                "circle-radius": ["interpolate", ["linear"], ["zoom"], 11, 2.5, 14, 6],
                "circle-stroke-color": "#333333",
                "circle-stroke-width": 1,
            },
        ),
        _layer(
            "telecoms",
            "circle",
            11,
            _class("telecoms"),
            {
                "circle-color": "#6E4C9E",
                "circle-radius": ["interpolate", ["linear"], ["zoom"], 11, 2.5, 14, 5],
                "circle-stroke-color": "#ffffff",
                "circle-stroke-width": 1,
            },
        ),
        _layer(
            "water",
            "circle",
            12,
            _class("water"),
            {
                "circle-color": "#3B7BBF",
                "circle-radius": ["interpolate", ["linear"], ["zoom"], 12, 2.5, 14, 5],
                "circle-stroke-color": "#ffffff",
                "circle-stroke-width": 1,
            },
        ),
        _layer(
            "emergency",
            "circle",
            13,
            _class("emergency"),
            {
                "circle-color": "#D62728",
                "circle-radius": ["interpolate", ["linear"], ["zoom"], 13, 1.5, 14, 3],
            },
        ),
    ]
