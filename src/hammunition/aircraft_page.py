# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""tar1090, the ADS-B aircraft map, as a page on ``reference serve``.  D-071 (amended 2026-10-02).

tar1090's own installer is a root script piped from ``wget`` that clones
``master`` and configures lighttpd on port 80 on every address, so none of it
is run. Its page is static files; what is installed is the pinned archive's
``html/`` directory (the ``tar1090`` data unit), and what serves it is the
loopback server the offline map already runs, at ``/aircraft/``:

* each file of that tree, by exact installed name;
* ``/aircraft/data/<name>.json``, read from readsb's output directory
  (Debian's service writes ``/run/readsb``), one plain JSON name at a time,
  read-only, never cached; ``receiver.json`` is the one file rewritten, to
  the five keys the page needs (see :func:`receiver_document`);
* ``index.html`` and ``config.js`` are ours (the tree's are not served).

**The page may not call out.** Three layers, because tar1090 reaches for the
internet in many places (online tile, weather and airspace layers, aircraft
photographs, a route service, FAA and weather overlays):

1. ``config.js`` switches off the features that fetch (photographs, routes,
   overlays), each a documented setting of tar1090's own;
2. ``hammunition-layers.js`` replaces ``createBaseLayers`` so the only base
   layer is the local PMTiles map (when ``osm-pmtiles`` is installed) or a
   blank background (when it is not, with the reason drawn on the page), and
   none of tar1090's remote layers exist;
3. every response carries a Content-Security-Policy that names no host, so a
   request to anywhere else is refused by the browser itself.

What the policy cannot stop is the operator clicking one of tar1090's
outbound links (FlightAware, planespotters) in an aircraft's detail panel:
that is a navigation they chose, not the page calling out.

The aircraft database (``wiedehopf/tar1090-db``) is not carried: upstream
replaces its only commit regularly, so it cannot be pinned. Type, operator
and registration come from readsb when readsb knows them.
"""

from __future__ import annotations

import html
import json
import math
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import IO, TYPE_CHECKING

if TYPE_CHECKING:
    from .map_page import MapShelf

UNIT = "tar1090"
#: The archive is extracted into ``<data>/tar1090/src``; the page is its ``html/``.
SRC = "src"
HTML = "html"
AIRCRAFT = "/aircraft/"
DATA = AIRCRAFT + "data/"
LAYERS_FILE = "hammunition-layers.js"
#: Where Debian's readsb service writes its JSON (measured in a debian:13
#: container, 2026-10-01); ``/var/run`` is the same directory by a link.
JSON_DIRS: tuple[Path, ...] = (Path("/run/readsb"), Path("/var/run/readsb"))
#: The one place the page is rewritten: after tar1090's own settings and before
#: its layers are built. A page without it is not the pinned one.
ANCHOR = '<script src="layers.js"></script>'
PMTILES_SCRIPT = '<script src="/map/kit/pmtiles/dist/pmtiles.js"></script>'
#: Not served from the tree: ours replace them, or the database is not carried.
REPLACED = frozenset({"index.html", "config.js", LAYERS_FILE})
#: ``<name>.json`` and nothing else: no directory, no dot file, no compression.
JSON_NAME_CHARS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-")
RECEIVER = "receiver.json"
#: readsb's own receiver.json is read up to this size and no more.
RECEIVER_LIMIT = 1 << 20
#: The one aircraft file the page is told to read (see :func:`receiver_document`).
AIRCRAFT_JSON = "aircraft.json"
#: What the page may do: read from this server and nothing else. No source
#: names a host, so the browser refuses a request to any other.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; "
    "font-src 'self' data:; "
    "connect-src 'self'; "
    "worker-src 'self' blob:; "
    "frame-src 'none'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'none'; "
    "frame-ancestors 'none'"
)

NO_KIT = (
    "No basemap: vector-map-kit is not installed, so the map's drawing files are missing "
    "(hammunition install vector-map-kit osm-pmtiles). The aircraft are drawn on a plain "
    "background; this page never loads a map from the internet."
)
NO_REGIONS = (
    "No basemap: no region map is built yet (set map regions with "
    "hammunition station set --map-regions, then hammunition install osm-pmtiles). "
    "The aircraft are drawn on a plain background; this page never loads a map from the internet."
)
NO_MAP = (
    "No basemap: osm-pmtiles is not installed (hammunition install osm-pmtiles). The aircraft "
    "are drawn on a plain background; this page never loads a map from the internet."
)

#: tar1090's own settings, each a variable of its defaults.js. They are
#: assigned in config.js, which tar1090 loads after its defaults.
_CONFIG = """\
// Written by hammunition (reference serve). tar1090's own config.js is not served.
// Nothing this page does may leave 127.0.0.1: these are the settings that fetch.
"use strict";
planespottersAPI = false;
planespottingAPI = false;
planespottersLinks = false;
jetphotoLinks = false;
showPictures = false;
useRouteAPI = false;
routeApiUrl = "";
tfrs = false;
offlineMapDetail = 0;
"""

#: Replaces tar1090's ``createBaseLayers``. __CONFIG__ is JSON.
_LAYERS = """\
// Written by hammunition (reference serve). Replaces tar1090's createBaseLayers:
// the base layer is the local PMTiles map or nothing, and no remote layer exists.
"use strict";
(function () {
    const config = __CONFIG__;
    const LAND = '#ece9e1';

    function notice(text) {
        const show = function () {
            const bar = document.createElement('div');
            bar.id = 'hammunition-notice';
            bar.textContent = text;
            bar.style.cssText = 'position:fixed;left:50%;bottom:2.2em;transform:translateX(-50%);' +
                'z-index:10;background:#fff8dc;color:#222;border:1px solid #c9b458;' +
                'padding:.3em .7em;font:13px sans-serif;max-width:70%;border-radius:4px;';
            document.body.appendChild(bar);
            const canvas = document.getElementById('map_canvas');
            if (canvas) { canvas.style.backgroundColor = LAND; }
        };
        if (document.body) { show(); } else { document.addEventListener('DOMContentLoaded', show); }
    }

    function none() {
        return new ol.layer.Vector({
            source: new ol.source.Vector(),
            name: 'hammunition_none',
            title: 'No basemap',
            type: 'base',
        });
    }

    const Style = ol.style.Style, Fill = ol.style.Fill, Stroke = ol.style.Stroke, Text = ol.style.Text;
    const GREEN = {wood: 1, forest: 1, grass: 1, park: 1, meadow: 1, farmland: 0, scrub: 1,
                   nature_reserve: 1, protected_area: 1, garden: 1, cemetery: 1, golf_course: 1};
    const ROADS = {motorway: [3, '#e8a14a'], trunk: [2.6, '#efb96a'], primary: [2.4, '#f4cf8f'],
                   secondary: [2, '#f7e2b0'], tertiary: [1.6, '#ffffff'], minor: [1.2, '#ffffff'],
                   service: [0.8, '#ffffff'], rail: [1, '#999999']};
    const styles = {
        water: new Style({fill: new Fill({color: '#a6c8e6'})}),
        waterway: new Style({stroke: new Stroke({color: '#a6c8e6', width: 1.2})}),
        green: new Style({fill: new Fill({color: '#d4e3c4'})}),
        boundary: new Style({stroke: new Stroke({color: '#8b88a0', width: 1.1, lineDash: [6, 4]})}),
    };

    function styleFor(feature) {
        const layer = feature.get('layer');
        const type = feature.getGeometry().getType();
        const cls = feature.get('class');
        const polygon = type === 'Polygon' || type === 'MultiPolygon';
        const line = type === 'LineString' || type === 'MultiLineString';
        if (layer === 'water' && polygon) { return styles.water; }
        if (layer === 'waterway' && line) { return styles.waterway; }
        if ((layer === 'landcover' || layer === 'landuse' || layer === 'park') && polygon) {
            return GREEN[cls] ? styles.green : null;
        }
        if (layer === 'boundary' && line) {
            const level = feature.get('admin_level');
            return level === undefined || level <= 4 ? styles.boundary : null;
        }
        if (layer === 'transportation' && line) {
            const road = ROADS[cls];
            return road ? new Style({stroke: new Stroke({color: road[1], width: road[0]})}) : null;
        }
        if (layer === 'place' && type === 'Point' && feature.get('name')) {
            const rank = {country: 14, state: 13, city: 13, town: 11, village: 10}[cls];
            if (!rank) { return null; }
            return new Style({text: new Text({
                text: String(feature.get('name')),
                font: rank + 'px sans-serif',
                fill: new Fill({color: '#333'}),
                stroke: new Stroke({color: '#fff', width: 3}),
            })});
        }
        return null;
    }

    function inBox(h, z, x, y) {
        const n = Math.pow(2, z);
        const lon = (t) => t / n * 360 - 180;
        const lat = (t) => Math.atan(Math.sinh(Math.PI * (1 - 2 * t / n))) * 180 / Math.PI;
        const west = lon(x), east = lon(x + 1), north = lat(y), south = lat(y + 1);
        return !(east < h.minLon || west > h.maxLon || north < h.minLat || south > h.maxLat);
    }

    function basemap() {
        const format = new ol.format.MVT();
        const archives = config.regions.map(function (url) {
            const archive = new pmtiles.PMTiles(url);
            return {archive: archive, header: archive.getHeader()};
        });
        const source = new ol.source.VectorTile({
            format: format,
            url: 'pmtiles://{z}/{x}/{y}',
            maxZoom: 14,
            tileLoadFunction: function (tile, url) {
                tile.setLoader(function (extent, resolution, projection) {
                    const coord = tile.getTileCoord();
                    const z = coord[0], x = coord[1], y = coord[2];
                    Promise.all(archives.map(function (a) {
                        return a.header.then(function (h) {
                            if (!inBox(h, z, x, y)) { return []; }
                            return a.archive.getZxy(z, x, y).then(function (t) {
                                if (!t) { return []; }
                                return format.readFeatures(t.data, {
                                    extent: extent, featureProjection: projection});
                            });
                        }).catch(function () { return []; });  // one bad region is not every region
                    })).then(function (parts) {
                        tile.setFeatures([].concat.apply([], parts));
                    }).catch(function () { tile.setState(3); });
                });
            },
        });
        // What the page's tests read back (as the map page's data-state is read).
        let tiles = 0, features = 0;
        source.on('tileloadend', function (e) {
            tiles += 1;
            features += e.tile.getFeatures().length;
            document.body.dataset.basemapTiles = String(tiles);
            document.body.dataset.basemapFeatures = String(features);
        });
        source.on('tileloaderror', function () { document.body.dataset.basemapError = 'tile'; });
        return new ol.layer.VectorTile({
            source: source,
            style: styleFor,
            declutter: true,
            name: 'hammunition_pmtiles',
            title: 'Offline map (OpenStreetMap)',
            type: 'base',
            attributions: 'Map data © OpenStreetMap contributors, © OpenMapTiles',
        });
    }

    createBaseLayers = function () {
        // tar1090 chooses its base layer by name, from what the operator picked
        // last time (browser storage) or a ?baseMap= address: here there is one.
        MapType_tar1090 = config.reason === null ? 'hammunition_pmtiles' : 'hammunition_none';
        let layer;
        if (config.reason === null && typeof pmtiles !== 'undefined') {
            layer = basemap();
            const canvas = document.getElementById('map_canvas');
            if (canvas) { canvas.style.backgroundColor = LAND; }
        } else {
            layer = none();
            notice(config.reason === null ? 'No basemap: the map library did not load.' : config.reason);
        }
        return new ol.layer.Group({
            layers: new ol.Collection([
                new ol.layer.Group({
                    name: 'world', title: 'Offline', fold: 'open',
                    layers: new ol.Collection([layer]),
                }),
            ]),
        });
    };
})();
"""


@dataclass(frozen=True)
class AircraftShelf:
    """What the aircraft page serves: the tree's files by URL path, the three
    generated files, and the directory ``data/`` reads from."""

    files: dict[str, Path]
    index: bytes
    config: bytes
    layers: bytes
    json_dir: Path
    basemap: bool
    reason: str | None


def default_json_dir(
    candidates: tuple[Path, ...] = JSON_DIRS,
) -> Path:
    """The first of readsb's usual directories that exists; the first when
    none does (readsb may not be running yet)."""
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return candidates[0]


def _plain_files(root: Path) -> list[Path]:
    if not root.is_dir() or root.is_symlink():
        return []
    return sorted(p for p in root.rglob("*") if p.is_file() and not p.is_symlink())


def find_aircraft(
    data: Path, map_shelf: MapShelf | None, *, json_dir: Path | None = None
) -> AircraftShelf | None:
    """The page from ``<data>/tar1090``, or None when it is not installed.

    Raises :class:`ValueError`, naming the file, when it is installed and is
    not the pinned page: serving it unrewritten would let it ask the
    internet for tiles."""
    src = data / UNIT / SRC
    tree = src / HTML
    if not tree.is_dir() or tree.is_symlink():
        return None
    index = tree / "index.html"
    if not index.is_file() or index.is_symlink():
        raise ValueError(f"{tree} has no index.html: `hammunition install {UNIT}` again")
    try:
        text = index.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"{index} cannot be read ({exc.strerror or exc})") from exc
    if ANCHOR not in text:
        raise ValueError(
            f"{index} does not load layers.js where the pinned page does, so it is not the "
            f"page this server rewrites; `hammunition install {UNIT}` again"
        )
    regions: list[str] = []
    if map_shelf is None:
        reason: str | None = NO_MAP
    elif not map_shelf.ready:
        reason = NO_KIT
    elif not map_shelf.regions:
        reason = NO_REGIONS
    else:
        reason = None
        from .map_page import regions_json

        regions = [r["url"] for r in json.loads(regions_json(map_shelf))]
    basemap = reason is None
    rewritten = text.replace(
        ANCHOR,
        (f"{PMTILES_SCRIPT}\n" if basemap else "")
        + f'{ANCHOR}\n<script src="{LAYERS_FILE}"></script>',
        1,
    )
    files = {
        AIRCRAFT + path.relative_to(tree).as_posix(): path
        for path in _plain_files(tree)
        if path.relative_to(tree).as_posix() not in REPLACED
        and path.relative_to(tree).parts[0] not in ("data", "db2")
    }
    # The regions are file names: JSON, so a quote in one is a string
    # character in the script. It is a .js file, never inline in a page.
    layers = _LAYERS.replace(
        "__CONFIG__", json.dumps({"regions": regions, "reason": reason}, ensure_ascii=True)
    )
    return AircraftShelf(
        files=files,
        index=rewritten.encode("utf-8"),
        config=_CONFIG.encode("utf-8"),
        layers=layers.encode("utf-8"),
        json_dir=json_dir if json_dir is not None else default_json_dir(),
        basemap=basemap,
        reason=reason,
    )


def data_name(rest: str) -> str | None:
    """*rest* (already percent-decoded) if it is ``<name>.json`` of letters,
    digits, ``_`` and ``-``; else None."""
    stem, dot, suffix = rest.rpartition(".")
    if dot != "." or suffix != "json" or not stem or not set(stem) <= JSON_NAME_CHARS:
        return None
    return rest


def data_file(shelf: AircraftShelf, name: str) -> Path | None:
    """readsb's file *name* if it is a regular file, not a link."""
    if data_name(name) is None:
        return None
    path = shelf.json_dir / name
    try:
        mode = path.lstat().st_mode
    except OSError:
        return None
    return path if stat.S_ISREG(mode) else None


def open_regular(path: Path) -> IO[bytes] | None:
    """*path* opened for reading if it is a regular file and not a link, else
    None. Opened without following a link and without blocking, and checked
    on the descriptor, so a file swapped for a link or a FIFO between a
    listing and this call is refused (review, 2026-10-02)."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    except OSError:
        return None
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            os.close(fd)
            return None
        return os.fdopen(fd, "rb")
    except OSError:
        return None


def _number(value: object, low: float, high: float) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) and low <= value <= high else None


def receiver_document(shelf: AircraftShelf) -> bytes | None:
    """The ``receiver.json`` the page is served: five keys, and no more.

    tar1090 reads this file first and chooses how to read everything else from
    it. Debian's readsb 3.14.1630 writes ``aircraft.binCraft.zst`` beside
    ``aircraft.json`` (measured 2026-10-02), and tar1090 asks for the binary
    form when this file says ``binCraft`` or ``zstd``, for globe-index files
    when it names a ``globeIndexGrid``, for a re-api when ``reapi``, and for
    history chunks when ``history`` is more than one. None of those is served
    here, so none of those keys is passed on: the page reads ``aircraft.json``
    every second, which readsb always writes, and takes the receiver's
    version, refresh interval and position from what readsb says.

    Built from readsb's file when there is one that parses, else from
    nothing: a directory that holds only ``aircraft.json`` (dump978-fa's
    ``--json-port`` output, a hand-run decoder) gets a page too. None when
    there is no ``aircraft.json`` at all (readsb is not running yet): 404, and
    tar1090 asks again.
    """
    if data_file(shelf, AIRCRAFT_JSON) is None:
        return None
    source: dict[str, object] = {}
    path = data_file(shelf, RECEIVER)
    handle = open_regular(path) if path is not None else None
    if handle is not None:
        with handle:
            raw = handle.read(RECEIVER_LIMIT + 1)
        if len(raw) <= RECEIVER_LIMIT:
            try:
                loaded = json.loads(raw)
            except ValueError:
                loaded = None
            if isinstance(loaded, dict):
                source = loaded
    version = source.get("version")
    refresh = _number(source.get("refresh"), 100, 60000)
    document: dict[str, object] = {
        "version": version if isinstance(version, str) and len(version) <= 64 else "unknown",
        "refresh": refresh if refresh is not None else 1000,
        "history": 0,
    }
    if source.get("readsb") is True:
        document["readsb"] = True
    lat, lon = _number(source.get("lat"), -90, 90), _number(source.get("lon"), -180, 180)
    if lat is not None and lon is not None:
        document["lat"], document["lon"] = lat, lon
    return (json.dumps(document) + "\n").encode("utf-8")


def landing_section(shelf: AircraftShelf | None) -> str:
    """The landing page's lines about the aircraft map."""
    e = html.escape
    if shelf is None:
        return (
            "<h2>Aircraft</h2><p>Not installed: <code>hammunition install tar1090</code> "
            "(it needs <code>readsb</code>, which decodes the aircraft).</p>"
        )
    parts = [
        f'<h2>Aircraft</h2><p><a href="{AIRCRAFT}">Open the aircraft map</a> (tar1090), '
        f"reading <code>{e(str(shelf.json_dir))}</code> from <code>readsb</code>."
    ]
    if not shelf.json_dir.is_dir():
        parts.append(
            " That directory is not there yet: readsb is not running, or writes elsewhere "
            "(<code>hammunition reference serve --readsb-json DIR</code>)."
        )
    parts.append("</p>")
    if shelf.reason is not None:
        parts.append(f"<p><small>{e(shelf.reason)}</small></p>")
    return "".join(parts)
