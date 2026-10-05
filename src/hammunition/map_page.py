# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The offline browser map that ``hammunition reference serve`` serves.  D-071.

What is served, found on disk when the server starts, each file by its exact
installed name and nothing else:

* the region maps, ``<data>/osm-pmtiles/<slug>.pmtiles``, at
  ``/map/tiles/<slug>.pmtiles``, read by pmtiles.js with HTTP byte ranges;
* the fixed kit, ``<data>/vector-map-kit/``: MapLibre GL JS, pmtiles.js, the
  OSM Bright style, its sprite and fonts, at ``/map/kit/<path>``;
* the page at ``/map/`` and the list of regions at ``/map/regions.json``;
* the operator's infrastructure layers (D-075), each ``infra-<id>.geojson``
  in their overlay directory, at ``/map/overlays/<file>``, listed at
  ``/map/overlays.json``, and the infrastructure style's licence at
  ``/map/infra-style-licence.txt``.

The page loads nothing from anywhere else. The style as tilemaker ships it
names a sprite on openmaptiles.github.io and a font and tile server on
``localhost:8080``; the page points all three at this server before MapLibre
reads it. The attribution control is not collapsed and reads
:data:`CREDIT`, which the OpenMapTiles schema's CC-BY licence requires
visibly on the map. "You are here" comes from the GPS tether's
``/position`` event stream on 127.0.0.1 (the hammunition-gps-tether project; :mod:`hammunition.tether_contract`
holds the port).

With a router (D-076) the bar gains a profile selector, *Route* and *Clear*:
the route is asked of this server at ``/map/route``, which asks GraphHopper,
and drawn from the GeoJSON line it answers with. It starts at the tether's
position when one has arrived. ``#route=LAT,LON;LAT,LON;PROFILE`` in the
address routes on load.
"""

from __future__ import annotations

import html
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from . import map_style

if TYPE_CHECKING:
    from .areas import Active

KIT_UNIT = "vector-map-kit"
TILES_UNIT = "osm-pmtiles"
MAP = "/map/"
KIT = "/map/kit/"
TILES = "/map/tiles/"
REGIONS = "/map/regions.json"
#: Where the page asks for a route; ``reference serve`` asks GraphHopper (D-076).
ROUTE = "/map/route"
OVERLAYS = "/map/overlays.json"
OVERLAY = "/map/overlays/"
STYLE_LICENCE = "/map/infra-style-licence.txt"
#: A GeoJSON larger than this is not offered: the largest layer measured
#: (Vermont's shelter candidates, 1,801 points) is well under 1 MB.
OVERLAY_LIMIT = 64 * 1024 * 1024
#: The credit OpenMapTiles' CC-BY licence and OpenStreetMap's ODbL require on
#: the map (OSM Bright's LICENSE.md). A test asserts the page carries it.
CREDIT = "© OpenMapTiles © OpenStreetMap contributors"
CREDIT_HTML = (
    '<a href="https://openmaptiles.org/">© OpenMapTiles</a> '
    '<a href="https://www.openstreetmap.org/copyright">© OpenStreetMap contributors</a> '
    f'<a href="/map/infra-style-licence.txt">{map_style.CREDIT}</a>'
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
class Overlay:
    """One infrastructure layer's GeoJSON, as the page lists it."""

    layer_id: str
    name: str
    licence: str
    url: str
    path: Path


@dataclass(frozen=True)
class MapShelf:
    """What the map has to serve: kit files and region maps by URL path,
    percent-decoded (the server decodes a request's path before it looks it
    up, and looks it up only: nothing is joined to a directory)."""

    files: dict[str, Path]
    regions: tuple[str, ...]
    missing: tuple[str, ...]
    overlays: tuple[Overlay, ...] = field(default=())

    @property
    def ready(self) -> bool:
        return not self.missing


def _plain_files(root: Path) -> list[Path]:
    if not root.is_dir() or root.is_symlink():
        return []
    return sorted(p for p in root.rglob("*") if p.is_file() and not p.is_symlink())


def find_overlays(
    where: Path | None, active: Active | None = None, universe: Sequence[str] = ()
) -> tuple[Overlay, ...]:
    """The infrastructure layers' GeoJSON in *where*, in layer order: each a
    regular file, not a link, under :data:`OVERLAY_LIMIT`, a FeatureCollection
    naming itself and its licence. Anything else is left out, and so is a
    layer of an area that is not active (D-082; *active* None is everything)."""
    from .infra import known_layers, layer_area, layer_files

    if where is None or not where.is_dir() or where.is_symlink():
        return ()
    found: list[Overlay] = []
    for layer_id in known_layers(where):
        if active is not None and not active.area(layer_area(layer_id), universe):
            continue
        path = where / layer_files(layer_id)[3]
        try:
            if path.is_symlink() or not path.is_file() or path.stat().st_size > OVERLAY_LIMIT:
                continue
            data: Any = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict) or data.get("type") != "FeatureCollection":
            continue
        name, licence = data.get("name"), data.get("licence")
        if not isinstance(name, str) or not isinstance(licence, str):
            continue
        found.append(Overlay(layer_id, name, licence, OVERLAY + quote(path.name), path))
    return tuple(found)


def overlays_json(shelf: MapShelf) -> bytes:
    rows = [
        {"id": o.layer_id, "name": o.name, "licence": o.licence, "url": o.url}
        for o in shelf.overlays
    ]
    return (json.dumps(rows, ensure_ascii=False) + "\n").encode("utf-8")


def find_map(
    data: Path,
    overlays: Path | None = None,
    active: Active | None = None,
    universe: Sequence[str] = (),
) -> MapShelf:
    """The kit's page files and the installed region maps under *data*, and
    the operator's infrastructure layers in *overlays* (D-075). With *active*
    (D-082), only the active regions' maps and layers are listed and served;
    *universe* is the station's map regions, which a bare region name is read
    against. None lists everything installed."""
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
    if active is not None:
        tiles = [p for p in tiles if active.region_slug(p.name.removesuffix(".pmtiles"), universe)]
    for path in tiles:
        files[TILES + path.name] = path
    layers = find_overlays(overlays, active, universe)
    for overlay in layers:
        files[OVERLAY + overlay.path.name] = overlay.path
    if map_style.NOTICE.is_file():
        files[STYLE_LICENCE] = map_style.NOTICE
    return MapShelf(
        files=files,
        regions=tuple(p.name.removesuffix(".pmtiles") for p in tiles),
        missing=missing,
        overlays=layers,
    )


def regions_json(shelf: MapShelf) -> bytes:
    """``[{"name": slug, "url": "/map/tiles/<slug>.pmtiles"}, ...]``."""
    rows = [{"name": r, "url": TILES + quote(f"{r}.pmtiles")} for r in shelf.regions]
    return (json.dumps(rows) + "\n").encode("utf-8")


_SCRIPT = """
import * as maplibregl from '__KIT__maplibre/maplibre-gl.mjs';
const credit = __CREDIT__;
const router = __ROUTER__;
const infraLayers = __INFRA_LAYERS__;
const esc = (s) => { const d = document.createElement('div'); d.textContent = String(s); return d.innerHTML; };
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
  style.layers = style.layers.concat(infraLayers);
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
  const asked = /^#route=([^;]+);([^;]+)(?:;([a-z]+))?$/.exec(location.hash);
  map.once('load', () => (router && asked ? null : frame(regions[0].url)));
  const overlays = await (await fetch('__OVERLAYS__')).json();
  const colours = ['#d62728', '#1f77b4', '#2ca02c', '#9467bd', '#ff7f0e', '#8c564b', '#e377c2', '#17becf', '#bcbd22', '#7f7f7f', '#393b79', '#637939', '#843c39'];
  const shown = document.getElementById('layers');
  const addOverlays = () => overlays.forEach((o, i) => {
    const id = 'overlay-' + o.id;
    map.addSource(id, {type: 'geojson', data: o.url, attribution: esc(o.licence)});
    map.addLayer({id, type: 'circle', source: id, paint: {
      'circle-color': colours[i % colours.length], 'circle-radius': 5,
      'circle-stroke-color': '#fff', 'circle-stroke-width': 1}});
    const label = document.createElement('label');
    const box = document.createElement('input');
    box.type = 'checkbox'; box.checked = true;
    box.addEventListener('change', () => map.setLayoutProperty(id, 'visibility', box.checked ? 'visible' : 'none'));
    label.appendChild(box); label.appendChild(document.createTextNode(' ' + o.name + ' '));
    shown.appendChild(label);
    map.on('click', id, (e) => {
      const f = e.features[0];
      new maplibregl.Popup().setLngLat(f.geometry.coordinates)
        .setText(f.properties.name + ': ' + f.properties.description).addTo(map);
    });
  });
  if (map.loaded()) addOverlays(); else map.once('load', addOverlays);
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
__ROUTES__}
"""


#: The route control, in the page only with a router (D-076).
_ROUTES = """
  if (router) {
    const profile = document.getElementById('profile');
    const info = document.getElementById('routeinfo');
    let picking = null;
    let points = null;
    const pins = [];
    const say = (text) => { info.textContent = text; };
    const pin = (at, color) => {
      pins.push(new maplibregl.Marker({color}).setLngLat(at).addTo(map));
    };
    const draw = (geometry) => {
      const data = {type: 'Feature', geometry, properties: {}};
      const source = map.getSource('route');
      if (source) { source.setData(data); return; }
      map.addSource('route', {type: 'geojson', data});
      map.addLayer({id: 'route-line', type: 'line', source: 'route',
        layout: {'line-join': 'round', 'line-cap': 'round'},
        paint: {'line-color': '#1a5fd0', 'line-width': 5, 'line-opacity': 0.85}});
    };
    const duration = (ms) => {
      const m = Math.round(ms / 60000);
      return m >= 60 ? Math.floor(m / 60) + ' h ' + (m % 60) + ' min' : m + ' min';
    };
    const ask = async () => {
      if (!points) return;
      const q = new URLSearchParams();
      for (const [lon, lat] of points) q.append('point', lat + ',' + lon);
      q.append('profile', profile.value);
      say('Routing…');
      document.body.dataset.route = 'asking';
      let answer;
      try {
        const r = await fetch('__ROUTE__?' + q.toString());
        answer = await r.json();
        if (!r.ok) {
          say('No route: ' + (answer.message || r.status));
          document.body.dataset.route = 'refused';
          return;
        }
      } catch (e) {
        say('No route: ' + (e.message || e));
        document.body.dataset.route = 'error';
        return;
      }
      const path = answer.paths && answer.paths[0];
      if (!path || !path.points || path.points.type !== 'LineString') {
        say('No route in the answer.');
        document.body.dataset.route = 'refused';
        return;
      }
      draw(path.points);
      for (const p of pins.splice(0)) p.remove();
      pin(points[0], '#2a2');
      pin(points[1], '#1a5fd0');
      const c = path.points.coordinates;
      const box = [[c[0][0], c[0][1]], [c[0][0], c[0][1]]];
      for (const [x, y] of c) {
        box[0][0] = Math.min(box[0][0], x); box[0][1] = Math.min(box[0][1], y);
        box[1][0] = Math.max(box[1][0], x); box[1][1] = Math.max(box[1][1], y);
      }
      const top = document.getElementById('bar').offsetHeight + 24;
      map.fitBounds(box, {padding: {top, bottom: 40, left: 40, right: 40}, animate: false, maxZoom: 16});
      info.textContent = '';
      const steps = document.createElement('details');
      const head = document.createElement('summary');
      head.textContent = (path.distance / 1000).toFixed(1) + ' km, ' + duration(path.time) +
        ' (' + profile.value + ')';
      steps.appendChild(head);
      const list = document.createElement('ol');
      for (const step of path.instructions || []) {
        const li = document.createElement('li');
        li.textContent = step.text;
        list.appendChild(li);
      }
      steps.appendChild(list);
      info.appendChild(steps);
      document.body.dataset.route = 'drawn';
    };
    const clear = () => {
      for (const p of pins.splice(0)) p.remove();
      points = null;
      picking = null;
      if (map.getLayer('route-line')) map.removeLayer('route-line');
      if (map.getSource('route')) map.removeSource('route');
      say('');
      delete document.body.dataset.route;
    };
    document.getElementById('route').addEventListener('click', () => {
      clear();
      picking = here ? [here] : [];
      say(here ? 'Click where to go; the route starts where you are.' : 'Click where to start.');
    });
    document.getElementById('clear').addEventListener('click', clear);
    profile.addEventListener('change', ask);
    map.on('click', (e) => {
      if (!picking) return;
      const at = [e.lngLat.lng, e.lngLat.lat];
      picking.push(at);
      pin(at, picking.length === 1 ? '#2a2' : '#1a5fd0');
      if (picking.length === 1) { say('Click where to go.'); return; }
      points = picking;
      picking = null;
      ask();
    });
    if (asked) {
      const lonlat = (text) => { const [lat, lon] = text.split(',').map(Number); return [lon, lat]; };
      points = [lonlat(asked[1]), lonlat(asked[2])];
      if (asked[3] && router.includes(asked[3])) profile.value = asked[3];
      map.once('load', ask);
    }
  }
"""


def map_page(*, position_port: int, router: Sequence[str] | None = None) -> str:
    """The page. Everything it names is on this server, except the position,
    which is the tether's, also on 127.0.0.1. With *router*, the profiles the
    route graph was built with, the route control (D-076)."""
    script = (
        _SCRIPT.replace("__KIT__", KIT)
        .replace("__ROUTER__", json.dumps(list(router)) if router else "null")
        .replace("__ROUTES__", _ROUTES.replace("__ROUTE__", ROUTE) if router else "")
        .replace("__STYLE__", STYLE)
        .replace("__FONTS__", quote(FONTS))
        .replace("__REGIONS__", REGIONS)
        .replace("__POSITION__", str(position_port))
        .replace("__CREDIT__", json.dumps(CREDIT_HTML))
        .replace("__INFRA_LAYERS__", json.dumps(map_style.style_layers()))
        .replace("__OVERLAYS__", OVERLAYS)
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
                + "#map{position:absolute;inset:0}"
                + "#bar{position:absolute;top:8px;left:8px;z-index:2;background:#fff;padding:6px;"
                + "border-radius:4px;max-width:calc(100% - 64px)}#bar>*{margin:2px}</style>",
                "</head><body>",
                '<div id="map"></div>',
                '<div id="bar"><label>Region <select id="region"></select></label> '
                + '<button id="centre" type="button">Centre on me</button> '
                + '<span id="where">Waiting for a position…</span> <span id="status"></span> '
                + '<span id="layers"></span>',
                *(
                    [
                        '<br><label>Route for <select id="profile">'
                        + "".join(f"<option>{html.escape(name)}</option>" for name in router)
                        + '</select></label> <button id="route" type="button">Route</button> '
                        '<button id="clear" type="button">Clear</button> <span id="routeinfo">'
                        "</span>"
                    ]
                    if router
                    else []
                ),
                f"<noscript>{html.escape(CREDIT)}. The map needs JavaScript.</noscript></div>",
                "<script>window.addEventListener('error',(e)=>{document.body.dataset.error="
                + "String(e.message);document.getElementById('status').textContent='Error: '+e.message;});"
                + "window.addEventListener('unhandledrejection',(e)=>{const m=String((e.reason&&"
                + "e.reason.message)||e.reason);document.body.dataset.error=m;"
                + "document.getElementById('status').textContent='Error: '+m;});</script>",
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
