<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Infrastructure and EMCOMM layers (D-075) — design

**Date:** 2026-10-01. **Status:** approved by the maintainer's delegate
(architectural path, no questions). **Input:** the infrastructure spike of
2026-10-01 (scratchpad, not committed), whose counts, URLs, licence lines
and byte-stability results were measured on Delaware and Vermont.
**Pattern:** D-074's repeater layers: one layer per source, `--from-osm`
over the installed extracts, opt-in unverified fetches with an observed
sha256, QMapShack `poiPaths` and Navit textfile registration, `remove
--layer`, a JSON document per command.

## Intent

An operator in an emergency wants, offline, on the maps they already have:
where the hospitals, fire stations, fuel, food and airfields are; where the
grid, the masts and the water works are; which NOAA Weather Radio
transmitter covers them and on what frequency. Everything is taken from
open data, converted on this machine, and drawn by the programs Hammunition
already installs: QMapShack, Navit and the browser map (D-071).

Success: one command per source writes a layer; each layer is three files
QMapShack, Navit and phones read plus one GeoJSON the browser map draws;
nothing personal reaches a document; every source's licence line is
printed and carried; the browser map's tiles draw power lines and plants
coloured by voltage, and the point layers are overlays that a new pin never
rebuilds the tiles for.

## Two rulings recorded (maintainer's delegate, 2026-10-01)

1. **Shelter candidates are labelled.** The layer name carries "candidate,
   not a designated shelter", and so does every waypoint's description.
2. **FCC ASR is fetched on request**, unverified, with its observed sha256
   (the ETCC's shape), not a data unit whose pin dies weekly.

## Sources and routes

| route | layer id | source | licence line (exact) |
|---|---|---|---|
| `import --from-osm` | `osm-medical`, `osm-responders`, `osm-supply`, `osm-shelter-candidates`, `osm-transport`, `osm-power`, `osm-telecom`, `osm-water` | the installed region extracts | `© OpenStreetMap contributors, ODbL 1.0` |
| `import --from-nasr` | `faa-airports` | `faa-nasr-airports` data unit | `FAA NASR <cycle>, public domain` |
| `import --from-eia` | `eia-plants` | `eia-860m` data unit | `Source: U.S. Energy Information Administration (<Mon YYYY>), public domain` |
| `import --from-wri` | `wri-plants` | `wri-power-plants` data unit | `WRI Global Power Plant Database v1.3.0 (2021), CC BY 4.0` |
| `fetch-fcc-asr` | `fcc-towers` | FCC `r_tower.zip`, on request | `FCC Antenna Structure Registration, US Government work, public domain` |
| `fetch-nwr` | `nwr` | NWS `ccl-data.js`, on request | `NOAA/NWS, public domain, not an official NWS product` |

### OpenStreetMap: the tag sets, exactly as the spike measured them

One `osmium tags-filter` per installed extract, as the operator, with every
selected layer's keys; Python then classifies each object. Counts are
objects (nodes, ways, relations); a node is placed where it is, a way at
the mean of its nodes, a relation at the mean of its member ways' nodes.

| layer | tags | DE / VT (spike) | QMapShack symbol | Navit icon |
|---|---|---|---|---|
| medical | `amenity=hospital`, `amenity=clinic\|doctors`, `amenity=pharmacy` | 187 / 199 | `Medical Facility` | `hospital.png` |
| responders | `amenity=fire_station`, `amenity=police`, `emergency=ambulance_station` | 160 / 367 | `Block, Red` | `firebrigade.png` |
| supply | `amenity=fuel`, `shop=supermarket`, `shop=hardware\|doityourself`, `amenity=charging_station`, `amenity=drinking_water\|water_point` | 573 / 885 | `Shopping Center` | `shopping.png` |
| shelter-candidates | `amenity=school`, `amenity=community_centre\|townhall`, `amenity=place_of_worship` | 671 / 1,801 | `City Hall` | `townhall.png` |
| transport | `aeroway=aerodrome`, `aeroway=helipad\|heliport`, `railway=station\|halt` | 72 / 123 | `Airport` | `airport.png` |
| power | `power=substation`, `power=plant` | 225 / 874 | `Danger` | `danger.png` |
| telecom | `man_made=mast\|tower\|communications_tower` or `tower:type=communication`, and one of `tower:type=communication`, `man_made=communications_tower`, a `communication:*` key | 314 / 174 | `Tall Tower` | `communication.png` |
| water | `man_made=water_works\|desalination_plant\|wastewater_plant\|pumping_station\|water_tower` | 163 / 105 | `Water` | `drinking_water.png` |

Every symbol name is one of QMapShack 1.17.1's built-in names
(`helpers/CWptIconManager.cpp`, the same source D-064 measured `Tall Tower`
from); an unknown name falls back to `Default`, which is why the spike's
`Radio Beacon` is not used. Every Navit icon is a file the `navit` package
ships in `/usr/share/navit/icons/` (0.5.6, measured), drawn and labelled
through the stock layout's `poi_custom*` rules, as D-064's repeaters are.

**Not carried as POIs**, each with the spike's reason: `amenity=shelter`
(picnic, bus and lean-to shelters, not mass-care shelters: 202 / 546);
sirens, defibrillators, assembly points, emergency water points and
`emergency=shelter` (0 to 24 a state); emergency phones (road call boxes);
`amenity=social_facility` (nursing homes and food banks mixed); power towers
and poles (15,586 / 32,671), generators (Vermont's 10,365 are rooftop
solar), hydrants (patchy), bridges and lines: those belong on the map, and
the browser map's `infra` tile layer draws lines and hydrants; bridges are
already drawn by OSM Bright. Exchanges and data centres (12 / 9), wells and
reservoirs are left out of the POI layers; exchanges and pipelines are in
the tile layer.

### Federal and worldwide sources

- **`faa-nasr-airports`**, a D-049 data unit: the NASR `APT_CSV.zip` at its
  dated 28-day URL, `https://nfdc.faa.gov/webContent/28DaySub/extra/<DD_Mon_YYYY>_APT_CSV.zip`
  (8,030,968 B for the 2026-10-01 cycle, byte-stable over two fetches). Its
  pin is written into the manifest by `scripts/gen_nasr_pin.py`: the cycle
  is computed from the AIRAC epoch (every 28 days from 2026-01-22), the
  URL, sha256, size, `version` (the cycle date) and the licence line
  (`FAA NASR <cycle>, public domain`, which is what the plan prints) are
  rewritten; `--check` goes red when a newer cycle is in effect or the
  pinned URL no longer answers with the pinned size, and the weekly pin
  review runs it. The import reads `APT_BASE.csv` from the zip: every site
  type (airport, heliport, seaplane base, ...), each with its identifier,
  name, city, type, status, use, elevation and ICAO id.
- **`eia-860m`**, a D-049 data unit: the monthly generator inventory
  workbook (13,955,142 B for August 2026). `scripts/gen_eia860m_pin.py`
  writes URL, sha256, size, `version` (YYYY-MM) and the licence line
  `Source: U.S. Energy Information Administration (Aug 2026), public
  domain`. **The move:** a month's file sits under `xls/` until the next
  month lands, then under `archive/xls/`; the generator, finding the pinned
  URL gone and the archive URL serving the same bytes, rewrites the URL to
  the archive and keeps the pin; `--check` names the move, and a newer
  month, as red. The import streams the `Operating` sheet (the workbook's
  sheet XML is 56 MB; it is read row by row), groups generators by plant
  id, and writes one point per plant: name, operator, technologies, summed
  nameplate MW, generator count.
- **`wri-power-plants`**, a D-049 data unit: WRI's Global Power Plant
  Database v1.3.0 (`global_power_plant_database_v_1_3.zip`, 4,178,889 B,
  CC BY 4.0, frozen since 2021-06-02). Pinned by our sha256 in the manifest
  and checked against the publisher's own MD5 (the S3 ETag, `8b4e4715…`) by
  `scripts/gen_wri_pin.py`, which records it in the manifest; `--check`
  HEADs the URL and compares the ETag and size. **Used outside the US
  only:** `--from-wri` drops every `USA` row and says EIA-860M covers the
  US (in the US WRI's rows are EIA's 2019 data).
- **FCC ASR**, on request: `fetch-fcc-asr` fetches `r_tower.zip` (37.8 MB,
  no checksum published), records its sha256, reads **only `RA.dat` and
  `CO.dat`** from the archive in memory (never `EN.dat`, which holds owner
  contact names, e-mail addresses and telephone numbers; and of `RA` only
  the registration number, status, dates, structure type and heights,
  never its signature-name fields), keeps registrations whose status is
  constructed or granted with no dismantle date and a structure
  coordinate. Measured: 266 / 189 for Delaware's and Vermont's own
  structures, exactly the spike's counts. Layer `FCC towers (unverified,
  <file date>)`, dated by the archive's own `counts` file.
- **NOAA Weather Radio**, on request: `fetch-nwr` fetches `ccl-data.js`
  (755 kB), keeps callsign, site, frequency, power, WFO and every county's
  name and SAME code, **drops `status`** (it is the live outage state, and
  regenerates the file on every outage). Layer `NOAA Weather Radio
  (unverified, fetched <date>)`.

### Filtering to the station's regions

The station's regions are the installed extracts (D-057), as `--from-osm`
reads them. Each extract's header box (`osm_pbf.header_bbox`, the capped
reader) is the filter; an extract with no box is named by its number and
left out. Nothing installed means the import refuses, naming
`hammunition install osm-regions`. NWR keeps a transmitter within 1.0° of a
box: measured, 0.5° missed one of Vermont's twelve covering transmitters
and 1.0° missed none (Delaware 12 kept for 5 covering, Vermont 21 for 12).
Nothing that names a region, its box or its digest reaches a document.

## Files, registration, documents

- `~/.local/share/hammunition/overlays/infra/`, mode 0700, the operator's,
  refused as root. Per layer: `infra-<id>.gpx`, `.poi`, `.navit.txt`,
  `.geojson`, 0600, each written to a temporary name and renamed.
- QMapShack: the directory in `[Canvas] poiPaths` while any `.poi` is
  there, by the editor D-064 uses; `maps qmapshack` keeps it as it keeps
  the repeaters'. Navit: the operator's `overlays/navit.xml` carries every
  repeater layer's and every infra layer's textfile; `navit-offline` opens
  it. One shared helper builds that list for both commands.
- `maps infra remove [--layer ID]`, idempotent.
- Documents `infra` and `infra-removed`, D-074's shape: `layers` (per
  layer: id, name, licence, read, written, skipped by reason, files),
  `inputs` (path or URL, format, sha256, empty for OSM), `directory`,
  `registered`. No name, position, region, box or digest of an extract.
  The fetches have no `--json` form, as D-074's fetches have none.

## The POI writer shared

`repeaters.write_poi` is generalised to points (name, description, tag),
category and comment; the repeater call keeps its bytes. One writer, one
float32 nudge.

## The browser map

- **Tiles:** an `infra` layer added to the OpenMapTiles profile by a
  wrapper Lua the converter writes into its working directory as the
  operator, `dofile`-ing the kit's unchanged `process-openmaptiles.lua`,
  with the kit's config plus `"infra": {"minzoom": 10, "maxzoom": 14}`
  beside it (the spike's measurement: Delaware 20,113,393 B to 20,659,287
  B, +2.7 %). Classes: power (line, minor_line, cable, substation, plant,
  generator), telecoms (masts, exchanges), pipeline, water, emergency
  (hydrants, sirens, ambulance stations, defibrillators, assembly points).
  Attributes: class, subclass, `voltage_kv` (the first value of `voltage`,
  in kV), operator, name, plant and generator source. `CONVERTER` becomes
  `tilemaker-pmtiles 2`, so every region is rebuilt once.
- **Style:** layers written by us, drawn over OSM Bright: lines and
  substations coloured by Open Infrastructure Map's voltage ramp
  (`voltage_scale` at its commit `5f20a29a`), under OIM's BSD-3-Clause
  notice, copied into `src/hammunition/map_style/LICENSE.openinframap`,
  served beside the page and named in the map's credit.
- **Overlays:** each infra layer's GeoJSON, found in the operator's
  overlay directory when `reference serve` starts, served by exact name at
  `/map/overlays/<file>`, listed at `/map/overlays.json` (id, name,
  licence); the page adds each as a circle layer with a toggle and its
  licence as the source's attribution. A new pin or a new fetch never
  rebuilds the tiles.

## Not carried (D-075 and the guide), each with the spike's reason

HIFLD Open (DHS retired it; HIFLD Secure needs an account and a data use
agreement; what remains are REST copies, the cell towers under the Esri
Master License Agreement); OpenGridWorks (a Vercel security checkpoint
answered 429, no terms readable, no bulk file; its sources are carried
directly); FEMA NSS Open Shelters (live only: five open nationwide on the
day); 911 PSAP boundaries (not public nationally); USGS National Structures
(82 MB for Delaware's 998 points, which OSM matches or beats); OpenFEMA
(county areas, not points; terms page unreadable from here).

## Error handling

Every input is parsed defensively: a malformed row is skipped and counted
by reason, numbered in reading order; a file that is not what it should be
is refused by name and nothing is written. The fetches go through D-064's
bounded HTTPS-only fetch. An xlsx or zip member is read with a size cap.
XML with a DOCTYPE is refused. A layer with no point is not written and its
old files are removed and reported; an import that writes nothing exits 1.

## Testing

Synthetic fixtures only (Delaware/Vermont-shaped, made-up names): a tiny
OSM XML (and an `.osm.pbf` built from it by `osmium cat` where osmium is
present), an `APT_BASE.csv` zip, a minimal xlsx built by the test, a WRI
CSV zip, an `r_tower.zip` whose `EN.dat` holds a canary that must never
appear, an NWR JS whose `status` must never appear. Fetches against a
loopback server. Documents validated, with no name, position or region
in them. The generators against faked fetches, their offline checks
falsified. The converter's argv, wrapper Lua and config against stand-in
kits. The map page's overlay list and routes. No GUI.

## Out of scope

Canada's TAFL, UK and EU sources (named routes in D-075, not built); FEMA
shelters during an event; deduplication across OSM and FCC; a profile for
the three units (the maintainer decides).
