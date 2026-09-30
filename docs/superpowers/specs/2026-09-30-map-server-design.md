# The local map server and tile page — design (D-071)

**Date:** 2026-09-30. **Status:** approved by the maintainer from the tile
spike's report (2026-09-29, measured on Delaware); written for the record.
**Decision:** D-071 in `docs/DECISIONS.md`. **Depends on:** D-057 (regions,
derived data by converter enum), D-061 (converters as the operator through
one `Staging`, their own ledger), D-066 (`reference serve`, 127.0.0.1 only),
D-067 (a pinned file the archive lacks), D-049 (data is pinned, sized and
licensed in the plan), D-039 (a target gap defers by name), D-037 (a floor
checked against the archive's candidate, never assumed), D-070 (a data
artifact may come from the LAN mirror, verified the same).

## What it is

A browser map of the station's own regions, drawn on the machine with no
network: vector tiles made from each region by the archive's `tilemaker`,
served with byte ranges by the page `hammunition reference serve` already
runs on 127.0.0.1, drawn by a pinned MapLibre GL JS with the OSM Bright
style, and a "you are here" from the GPS tether.

## Units

| Unit | Method | What |
|---|---|---|
| `vector-map-kit` | `data` | tilemaker's OpenMapTiles profile and the OSM Bright style and three Noto fonts (members of Debian's `tilemaker_3.0.0.orig.tar.gz`), Natural Earth's ocean, urban areas, glaciers and ice shelves (shapefiles at the v5.1.2 commit), OSM Bright's sprite (gh-pages commit), MapLibre GL JS 6.11.2 (`dist.zip`) and pmtiles.js 4.5.0 (npm) |
| `osm-pmtiles` | `derived`, converter `tilemaker-pmtiles`, `source: osm-regions`, `kit: vector-map-kit` | one `<slug>.pmtiles` per region |

Both join the `navigation` profile. `tilemaker` is a distribution
dependency of `osm-pmtiles`, as `osmosis` is of `mapsforge-map`; `gdal-bin`
(already carried) clips the ocean.

## Measured changes to the approved design

1. **The simplified water polygons cannot be pinned.** Measured
   2026-09-30: `simplified-water-polygons-split-3857.zip` was 23,732,315
   bytes on 2026-09-29 and 23,730,235 bytes the next morning
   (`Last-Modified` 03:43 GMT that day). It is rebuilt daily like the full
   set; a pin would fail within a day. The ocean is Natural Earth's 1:10m
   `ne_10m_ocean`, public domain, pinned at the same commit as
   `country-boundaries`, clipped per region with `ogr2ogr -clipsrc` (0.1 s
   on Delaware's box, measured) because it is one world-sized polygon.
   Coasts at z12 and above are Natural Earth's line, not OSM's: a
   documented gap whose route is the unpinnable daily set.
2. **The pinned config names four shapefiles**, not one: the ocean, and
   Natural Earth urban areas, glaciers and Antarctic ice shelves. All four
   are carried so the pinned config runs unmodified.
3. **Glyphs are 768 files.** They come as members of one archive, Debian's
   pool copy of tilemaker 3.0.0's tarball, which carries the style, the
   profile and the fonts, byte-identical to the spike's upstream copies. A
   `data` archive gains `members` (extract only these) and `into` (a
   subdirectory), because two archives extracted into one directory
   replace each other.

## The converter

Per region, as the operator in `<builds>/osm-pmtiles/<slug>.work/` under
its lock: clear; make `coastline/` and `landcover/<layer>/`; read the
region's box from its `.osm.pbf` header (`osm_pbf.header_bbox`, the capped
reader Navit's centre uses) and clip the ocean to it plus 0.1°, or copy the
world polygon whole when the header has none (slower, said in the outcome);
link the three land-cover layers; run
`tilemaker --input <pbf> --output <slug>.pmtiles --config <kit>/tilemaker/resources/config-openmaptiles.json --process <kit>/tilemaker/resources/process-openmaptiles.lua --store store`;
check the output starts with `PMTiles`; publish into
`<data>/osm-pmtiles/<slug>.pmtiles` re-verified with a `.source` sidecar
(`<snapshot>` and `converter: tilemaker-pmtiles 1`). A failure is recorded
in a tiles ledger whose step fails the run by name, last.

**Floor.** tilemaker 3.0 is the first to write PMTiles. The plan reads the
archive's candidate (or the installed version) for `tilemaker` from the
probe it already makes: below 3.0, `osm-pmtiles` is deferred from a profile
and refused when typed, naming the version; with no lists it is a note.
Ubuntu 24.04 (2.4.0) is the case. The floor is the engine's, like the
argv, not the manifest's.

## The server

`reference serve` gains, on the same 127.0.0.1 port: `/map/` (the page),
`/map/regions.json`, `/map/tiles/<slug>.pmtiles` and `/map/kit/<path>`,
each by exact installed name only. Every file answers `Range` with 206 and
`Content-Range`, a bad range with 416, `HEAD` with its size and
`Accept-Ranges: bytes`. A request whose `Host` is not
`127.0.0.1:<port>` or `localhost:<port>` is refused (403): the tiles say
where the operator's regions are, and a DNS-rebinding page must not read
them.

## The page

One generated HTML file: MapLibre as an ES module, pmtiles.js, the style
fetched and pointed at the local sprite, glyphs and region; a region
selector from `/map/regions.json`; the attribution control, not compact,
reading **"© OpenMapTiles © OpenStreetMap contributors"** with links; a
"you are here" marker from the tether.

## The position

`hammunition maps gps-tether` gains an HTTP listener on 127.0.0.1 port
10111 (`--position-port`) answering `GET /position` as Server-Sent Events:
one `data: {"lat","lon","mode","time"}` event per TPV with a fix. **SSE,
not a JSON poll**, because the tether watches gpsd only while a client is
connected: an event stream is a connected client and rides the existing
fan-out, while a poll would need a gpsd connection per request or a
lingering watch with a timer. The response carries
`Access-Control-Allow-Origin` only for a loopback origin, and a request
with another `Host` is refused, so no web page can read the position.

## Tests

Synthetic only: a `.osm.pbf` header built in the test, a fake `tilemaker`
and `ogr2ogr` on PATH, a PMTiles file with one hand-encoded vector tile.
The page under headless Chromium runs when `chromium` is on PATH and the
pinned kit archives are in `HAMMUNITION_MAP_KIT_DIR` (each checked against
the manifest's sha256), with every non-loopback host unresolvable and the
net log read back: every request must be to 127.0.0.1. Otherwise it is
skipped by name.

## Not carried

planetiler (Java 21+, 1.45 GB of side inputs, not in any archive); martin,
go-pmtiles, mbtileserver (GitHub binaries with no publisher checksum;
nothing they add the page needs); tileserver-gl (native install scripts,
D-037); `.mbtiles` (tilemaker writes one output per run); the raster stack
(PostGIS, osm2pgsql, renderd, carto: documented with the measured import,
not built).
