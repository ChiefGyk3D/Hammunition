# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The offline browser map that ``hammunition reference serve`` serves.  D-071.

What is served, found on disk when the server starts, each file by its exact
installed name and nothing else:

* the region maps, ``<data>/osm-pmtiles/<slug>.pmtiles``, at
  ``/map/tiles/<slug>.pmtiles``, read by pmtiles.js with HTTP byte ranges;
* the fixed kit, ``<data>/vector-map-kit/``: MapLibre GL JS, pmtiles.js, the
  OSM Bright style, its sprite and fonts, at ``/map/kit/<path>``;
* the page at ``/map/`` and the list of regions at ``/map/regions.json``.

The page loads nothing from anywhere else. The style as tilemaker ships it
names a sprite on openmaptiles.github.io and a font and tile server on
``localhost:8080``; the page points all three at this server before MapLibre
reads it. The attribution control is not collapsed and reads
:data:`CREDIT`, which the OpenMapTiles schema's CC-BY licence requires
visibly on the map. "You are here" comes from the GPS tether's
``/position`` event stream on 127.0.0.1 (:mod:`hammunition.gps_tether`).
"""

from __future__ import annotations

import html
import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

KIT_UNIT = "vector-map-kit"
TILES_UNIT = "osm-pmtiles"
MAP = "/map/"
KIT = "/map/kit/"
TILES = "/map/tiles/"
REGIONS = "/map/regions.json"
#: The credit OpenMapTiles' CC-BY licence and OpenStreetMap's ODbL require on
#: the map (OSM Bright's LICENSE.md). A test asserts the page carries it.
CREDIT = "© OpenMapTiles © OpenStreetMap contributors"
CREDIT_HTML = (
    '<a href="https://openmaptiles.org/">© OpenMapTiles</a> '
    '<a href="https://www.openstreetmap.org/copyright">© OpenStreetMap contributors</a>'
)
#: The kit's subtrees and files the page reads; nothing else of it is served.
SERVED: tuple[str, ...] = ("maplibre", "pmtiles/dist", "tilemaker/server/static")
SPRITES: tuple[str, ...] = ("sprite.png", "sprite.json", "sprite@2x.png", "sprite@2x.json")
#: What the page cannot start without.
REQUIRED: tuple[str, ...] = (
    "maplibre/maplibre-gl.mjs",
    "maplibre/maplibre-gl-shared.mjs",
    "maplibre/maplibre-gl-worker.mjs",
    "maplibre/maplibre-gl.css",
    "pmtiles/dist/pmtiles.js",
    "tilemaker/server/static/style.json",
    *SPRITES,
)
STYLE = "tilemaker/server/static/style.json"
FONTS = "tilemaker/server/static/fonts"


@dataclass(frozen=True)
class MapShelf:
    """What the map has to serve: kit files and region maps by URL path,
    percent-decoded (the server decodes a request's path before it looks it
    up, and looks it up only: nothing is joined to a directory)."""

    files: dict[str, Path]
    regions: tuple[str, ...]
    missing: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return not self.missing


def _plain_files(root: Path) -> list[Path]:
    if not root.is_dir() or root.is_symlink():
        return []
    return sorted(p for p in root.rglob("*") if p.is_file() and not p.is_symlink())


def find_map(data: Path) -> MapShelf:
    """The kit's page files and the installed region maps under *data*."""
    kit = data / KIT_UNIT
    files: dict[str, Path] = {}
    for sub in SERVED:
        for path in _plain_files(kit / sub):
            files[KIT + path.relative_to(kit).as_posix()] = path
    for name in SPRITES:
        path = kit / name
        if path.is_file() and not path.is_symlink():
            files[KIT + name] = path
    missing = tuple(r for r in REQUIRED if KIT + r not in files)
    tiles = sorted(
        p for p in (data / TILES_UNIT).glob("*.pmtiles") if p.is_file() and not p.is_symlink()
    )
    for path in tiles:
        files[TILES + path.name] = path
    return MapShelf(
        files=files,
        regions=tuple(p.name.removesuffix(".pmtiles") for p in tiles),
        missing=missing,
    )


def regions_json(shelf: MapShelf) -> bytes:
    """``[{"name": slug, "url": "/map/tiles/<slug>.pmtiles"}, ...]``."""
    rows = [{"name": r, "url": TILES + quote(f"{r}.pmtiles")} for r in shelf.regions]
    return (json.dumps(rows) + "\n").encode("utf-8")


_SCRIPT = """
import * as maplibregl from '__KIT__maplibre/maplibre-gl.mjs';
const credit = __CREDIT__;
const positionUrl = 'http://127.0.0.1:__POSITION__/position';
const status = document.getElementById('status');
const where = document.getElementById('where');
const chooser = document.getElementById('region');
window.__errors = [];
const protocol = new pmtiles.Protocol();
maplibregl.addProtocol('pmtiles', protocol.tile);
const regions = await (await fetch('__REGIONS__')).json();
if (!regions.length) {
  status.textContent = 'No vector-tile maps are installed: set map regions, then `hammunition install osm-pmtiles`.';
  document.body.dataset.state = 'empty';
} else {
  for (const r of regions) {
    const o = document.createElement('option');
    o.value = r.url; o.textContent = r.name; chooser.appendChild(o);
  }
  const tiles = (url) => 'pmtiles://' + location.origin + url;
  const style = await (await fetch('__KIT____STYLE__')).json();
  style.sprite = location.origin + '__KIT__sprite';
  style.glyphs = location.origin + '__KIT____FONTS__/{fontstack}/{range}.pbf';
  style.sources = {openmaptiles: {type: 'vector', url: tiles(regions[0].url), attribution: credit}};
  const map = new maplibregl.Map({container: 'map', style, attributionControl: {compact: false}});
  window.__map = map;
  map.addControl(new maplibregl.NavigationControl());
  map.on('error', (e) => {
    const m = String((e.error && e.error.message) || e);
    window.__errors.push(m);
    status.textContent = 'Map error: ' + m;
  });
  map.on('load', () => { document.body.dataset.loaded = '1'; });
  const frame = async (url) => {
    const h = await new pmtiles.PMTiles(location.origin + url).getHeader();
    map.fitBounds([[h.minLon, h.minLat], [h.maxLon, h.maxLat]], {animate: false});
  };
  map.once('load', () => frame(regions[0].url));
  chooser.addEventListener('change', () => {
    map.getSource('openmaptiles').setUrl(tiles(chooser.value));
    frame(chooser.value);
  });
  map.on('idle', () => {
    document.body.dataset.state = 'idle';
    document.body.dataset.errors = String(window.__errors.length);
  });
  let marker = null;
  let here = null;
  document.getElementById('centre').addEventListener('click', () => {
    if (here) map.easeTo({center: here, zoom: Math.max(map.getZoom(), 14)});
  });
  const events = new EventSource(positionUrl);
  events.onmessage = (e) => {
    const p = JSON.parse(e.data);
    here = [p.lon, p.lat];
    if (!marker) marker = new maplibregl.Marker({color: '#c00'}).setLngLat(here).addTo(map);
    else marker.setLngLat(here);
    where.textContent = 'You are here: ' + p.lat.toFixed(5) + ', ' + p.lon.toFixed(5) +
      (p.mode === 3 ? ' (3D fix)' : ' (2D fix)');
  };
  events.onerror = () => {
    where.textContent = 'No position: run `hammunition maps gps-tether`, which serves it on 127.0.0.1:__POSITION__.';
  };
}
"""


def map_page(*, position_port: int) -> str:
    """The page. Everything it names is on this server, except the position,
    which is the tether's, also on 127.0.0.1."""
    script = (
        _SCRIPT.replace("__KIT__", KIT)
        .replace("__STYLE__", STYLE)
        .replace("__FONTS__", quote(FONTS))
        .replace("__REGIONS__", REGIONS)
        .replace("__POSITION__", str(position_port))
        .replace("__CREDIT__", json.dumps(CREDIT_HTML))
    )
    return (
        "\n".join(
            [
                "<!doctype html>",
                '<html lang="en"><head><meta charset="utf-8">',
                '<meta name="viewport" content="width=device-width, initial-scale=1">',
                "<title>Offline map</title>",
                f'<link rel="stylesheet" href="{KIT}maplibre/maplibre-gl.css">',
                "<style>html,body{margin:0;height:100%;font:14px system-ui,sans-serif}"
                "#map{position:absolute;inset:0}"
                "#bar{position:absolute;top:8px;left:8px;z-index:2;background:#fff;padding:6px;"
                "border-radius:4px;max-width:calc(100% - 64px)}#bar>*{margin:2px}</style>",
                "</head><body>",
                '<div id="map"></div>',
                '<div id="bar"><label>Region <select id="region"></select></label> '
                '<button id="centre" type="button">Centre on me</button> '
                '<span id="where">Waiting for a position…</span> <span id="status"></span>',
                f"<noscript>{html.escape(CREDIT)}. The map needs JavaScript.</noscript></div>",
                "<script>window.addEventListener('error',(e)=>{document.body.dataset.error="
                "String(e.message);document.getElementById('status').textContent='Error: '+e.message;});"
                "window.addEventListener('unhandledrejection',(e)=>{const m=String((e.reason&&"
                "e.reason.message)||e.reason);document.body.dataset.error=m;"
                "document.getElementById('status').textContent='Error: '+m;});</script>",
                f'<script src="{KIT}pmtiles/dist/pmtiles.js"></script>',
                f'<script type="module">{script}</script>',
                "</body></html>",
            ]
        )
        + "\n"
    )


def landing_section(shelf: MapShelf) -> str:
    """The landing page's lines about the map."""
    if shelf.regions and shelf.ready:
        return (
            f'<h2>Map</h2><p><a href="{MAP}">Open the offline map</a> '
            f"({len(shelf.regions)} region(s)). Your position shows when "
            f"<code>hammunition maps gps-tether</code> is running.</p>"
        )
    if shelf.missing:
        return (
            "<h2>Map</h2><p>Not installed: <code>hammunition install osm-pmtiles</code> "
            "(with map regions set) builds the maps and installs the page's files.</p>"
        )
    return (
        "<h2>Map</h2><p>No vector-tile maps are installed: set map regions "
        "(<code>hammunition station set --map-regions …</code>), then "
        "<code>hammunition install osm-pmtiles</code>.</p>"
    )
