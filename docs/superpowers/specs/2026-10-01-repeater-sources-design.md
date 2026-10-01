<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Repeater data sources beyond RepeaterBook (D-074)

**Date:** 2026-10-01. **Status:** approved by the maintainer as scoped
below; three items are his to decide and are not built (§9). **Builds on:**
D-064 (the repeater overlays this adds layers to), D-049 (a data unit),
D-066 (a generated pin), D-070 (the mirror and `artifacts`), D-033 (an
unlicensed source judged on what we do with it), D-035 (a station value is
the operator's), D-021 (disclose, never adjudicate), D-031 (the input's
date, not the run's), D-059 (one JSON document per command).

**Measured by** the spike of 2026-10-01 (the scratchpad file
`repeater-sources-spike.md`, not committed): every URL, licence quote,
byte-stability result, count and the precedence rule below were measured on
three public example areas (Delaware, Vermont, Shenandoah). Its headline is
that open bulk data for the US barely exists: about one repeater gained over
hearham across the three areas. The value of this work is outside the US
and in what the station hears itself.

## 1. What it adds

Five sources, each its own layer, beside D-064's:

| Source | How it arrives | Layer name | Licence line |
|---|---|---|---|
| Open Repeater (CC0) | `open-repeater`, a D-049 data unit pinned by sha256 | `Repeaters (Open Repeater YYYY-MM-DD, CC0)` | Open Repeater, CC0 1.0 (openrepeater.org) |
| OpenStreetMap | a filter over the region extracts already installed, zero downloads | `Repeaters (OpenStreetMap, ODbL, YYYY-MM-DD)` | © OpenStreetMap contributors, ODbL 1.0 |
| UK RSGB ETCC | `maps repeaters fetch-etcc`, on request | `Repeaters (RSGB ETCC YYYY-MM-DD, unverified)` | no licence stated; D-033; sha256 observed |
| Brandmeister | `maps repeaters fetch-brandmeister`, on request | `DMR repeaters (Brandmeister YYYY-MM-DD, unverified)` | no terms published; D-033; hotspots dropped |
| Direwolf's APRS log | `--from-direwolf-log FILE...` | `Repeaters heard off the air (APRS objects, YYYY-MM-DD)` | received by this station |

And one convenience file: `repeaters-all.gpx`, the directory layers merged
across sources (§5).

## 2. The layers on disk

Every layer is three files in D-064's directory,
`$XDG_DATA_HOME/hammunition/overlays/repeaters/` (0700, files 0600, each
renamed into place), under its own stem:

| Layer id | Stem | Written by |
|---|---|---|
| `export` | `repeaters` | `import FILE...`, `fetch-hearham` (D-064, unchanged) |
| `open-repeater` | `repeaters-open-repeater` | `import --from-open-repeater [FILE]` |
| `osm` | `repeaters-osm` | `import --from-osm` |
| `etcc` | `repeaters-etcc` | `fetch-etcc` |
| `brandmeister` | `repeaters-brandmeister` | `fetch-brandmeister` |
| `aprs-heard` | `repeaters-aprs-heard` | `import --from-direwolf-log FILE...` |

Each stem has `.gpx`, `.poi` and `.navit.txt`, plus `.rows.json`: the
layer's rows as data, which is what the all-sources merge reads (a GPX's
`<desc>` is prose and cannot be read back without guessing). One command
writes one layer and replaces only that layer.

**Registration.** QMapShack's `[Canvas] poiPaths` already names the
directory (D-064); it stays there while any layer's `.poi` exists, and each
`.poi` shows as its own collection. Navit's operator copy of the generated
configuration gets one `textfile` map per layer present, rebuilt from the
generated file on every write, remove and `maps navit`; with none, the copy
is deleted.

**`maps repeaters remove [--layer ID]`** removes every layer (and the
merged file) by default, as it did; `--layer` removes one and rebuilds the
merged file and the registrations from what is left.

## 3. Each source

### 3.1 Open Repeater, a data unit

`catalog/packages/open-repeater.yaml`, `method: data`, one artifact:
`https://www.openrepeater.org/api/downloads?format=json&country=All+countries&band=All+bands&mode=All+modes&status=All`
installed as `open-repeater.json` under
`<prefix>/share/hammunition/data/open-repeater/`, licence `CC0 1.0`,
`licence_url` the downloads page. The sha256, size and `version` (the day
measured) are written by `scripts/gen_open-repeater-pin.py` into the
manifest itself, three lines it finds exactly once, re-parsed after the
write to confirm the effect. **The URL is not dated**: the file changes
whenever the site's data does, so the pin dies on Open Repeater's calendar.
`--check` fetches it (241 kB) and compares; the weekly pin review runs that
and goes red naming the generator. `--check --offline` checks the
manifest's shape and runs in the test suite. A stale pin refuses the
install by its digest; a LAN mirror (D-070) holding the pinned bytes still
serves it, and the Bunker mirrors it like any pinned data because it is a
`data` artifact in the `artifacts` document. Not in any profile: its rows
today are Sweden, Malaysia, India and one in Canada (§8 of the spike).

`maps repeaters import --from-open-repeater [FILE]` reads the installed file,
or a copy the operator downloaded. Fields: `callsign`, `frequency` (MHz,
the output), `offset` (MHz when its magnitude is under 50, else kHz: both
occur, -0.6 177 times and -600 85 times), `ctcss`/`dcs`, `mode`, `city`,
`status`, `last_verified`, `lat`/`lng` (113 of 461 have none and are
skipped by name). The layer is dated by the newest `last_verified` (the
data's own date), else the file's modification date.

### 3.2 OpenStreetMap, a filter over the extracts

**Ruling: an explicit `import --from-osm`, not a converter run with the
maps.** The conversions run as root inside `install`; this layer is the
operator's file in their home, D-057 keeps parsing of downloaded data out
of root, and the spike measured the yield in the US at one object in two
states. A converter would write an empty layer on most machines.

It reads every `<slug>.osm.pbf` under
`<prefix>/share/hammunition/data/osm-regions/` (the extracts the station
already has, verified by the map units; no station file is read and
nothing is downloaded) and runs, as the operator,
`osmium tags-filter <pbf> nwr/communication:amateur_radio*
nwr/communication:ham_radio* -f osm -o <scratch> --overwrite`. Nodes are
placed where they are; a way at the mean of its nodes (osmium includes the
referenced nodes); a relation is skipped and counted. An object is a
repeater when `communication:amateur_radio:repeater` is `yes` or a
callsign, or `communication:amateur_radio` is `repeater`, or it carries a
`…:repeater:frequency_out`; `communication:ham_radio:*` is read as the same
scheme. `=yes` alone (a mast with amateur antennas), `beacon` and `no` are
counted as "not a repeater". Callsign from `…:callsign`, else a callsign
written as the `…:repeater` value.

**Frequency units.** The spike found `145350000`, `146.685`, `146685` and
`1466100000` (146.61 MHz written ×10) in use. A value with a unit (`MHz`,
`kHz`, `Hz`) is taken in it; a bare number is tried as MHz, kHz, Hz and Hz
×10, in that order, and the first scaling that lands in a repeater band
(D-064's table) is taken. No two scalings of one number land in bands, so
the order never decides between two answers. A value that lands in none is
skipped, counted. `…:repeater:shift` is an offset with its sign; a bare
magnitude under 50 is MHz, else kHz, else Hz; unsigned, it is kept in the
notes and no offset is claimed. `frequency_in` gives the offset when no
shift does. `…:ctcss` is the tone, `…:modulation` the mode, `name` the
place.

The layer is dated by the oldest extract's snapshot (`YYMMDD` in its
sidecar; the file's date when it has none). **The JSON document names the
directory, not the extracts**: a region says where the operator is
(D-057), and this document is meant to be pasteable (D-064). `osmium`
missing is named with the package (`osmium-tool`) and the unit that brings
it (`osm-navit`).

### 3.3 UK ETCC, on request

`maps repeaters fetch-etcc` prints what it will fetch, fetches
`https://ukrepeater.net/csvcreate_all.php` once through D-064's fetch path
(bounded, redirects to HTTPS only), and parses the bytes in memory. Header
(measured): `CALL,BAND,CHAN,txMHz,rxMHz,CTCSS,QTHR,WHERE,lat,lon,ANALOG,DMR,DSTAR,FUSION`.
`txMHz` is the repeater's output (UK 2 m outputs sit 600 kHz above their
inputs in the measured file), `rxMHz - txMHz` the offset, the four flags
the modes, `CHAN` and `QTHR` in the notes. **Positions are at locator
precision**: a four-character locator puts a repeater at its square's
centre, tens of kilometres from the site; the description says which
locator and its length. No licence or terms are stated; carried under
D-033, never redistributed, the observed sha256 recorded.

### 3.4 Brandmeister, on request, hotspots dropped

`maps repeaters fetch-brandmeister` fetches
`https://api.brandmeister.network/v2/device` (no key; about 9.5 MB) the
same way, prints first that most entries are hotspots, and parses in
memory. **Kept only: a 6-digit id whose `tx` and `rx` differ.** Seven- and
nine-digit ids are personal ids and a `tx == rx` device a simplex hotspot:
somebody's house. They are dropped before anything is written, counted
under their reason, and never reach the disk or the document beyond the
count. `tx` is the output, `rx - tx` the offset, `colorcode` and
`lastKnownMaster` in the notes, `last_seen` the update date; `status` is
not interpreted (its codes are undocumented). No terms published; D-033.

### 3.5 Direwolf's log, heard off the air

`import --from-direwolf-log FILE...` reads Direwolf's `-l` daily logs or
its `-L` file. **The header was measured** by decoding synthetic objects
(`gen_packets` into `direwolf -l`, Direwolf 1.8.1, 2026-10-01):
`chan,utime,isotime,source,heard,level,error,dti,name,symbol,latitude,longitude,speed,course,altitude,frequency,offset,tone,system,status,telemetry,comment`.
Direwolf has already decoded the APRS frequency convention: `frequency` in
MHz, `offset` in signed kHz (`-600`, `+5000`), `tone` in Hz (`100.0`).
Kept: rows with `dti` `;` (an object) whose frequency is in a repeater
band. An object named like a callsign (`N0TST-R`, ircDDB's `N0TST  B`)
keeps it; one named by its frequency (`146.940NE`) is labelled with its
name. The sender is in the notes. Heard many times, one object is one row:
the newest hearing wins (D-064's merge, with the hearing time as the
update date). The layer is dated by the newest hearing. **It is never
merged into the directory layers**: it is evidence of what this station
heard, not a directory entry. A killed object cannot be told from a live
one in the CSV (no column carries it); the docs say so.

## 4. Inputs D-064's import now refuses by name

`import FILE...` reads exactly D-064's four formats. An Open Repeater JSON,
an ETCC CSV or a Direwolf log given there is refused, naming the flag or
command that makes it its own layer, so a source never lands under another
source's name. The `--from-*` flags are exclusive with each other and with
files; `--exported` dates an export only.

## 5. Precedence across sources

- **One layer per source**, named with its source, date and licence, so a
  wrong row can be traced and a source dropped.
- **Within a source, D-064's key**: callsign + output Hz + 0.01°.
- **The merged file, `repeaters-all.gpx`**, is rebuilt after every import,
  fetch and remove whenever two directory layers or more exist, and deleted
  otherwise. Rows are taken best source first: the operator's export or
  hand list; the regulator or coordinator (ETCC); CC0 (Open Repeater);
  hearham; Brandmeister; OSM. A row joins a kept one when its output Hz is
  equal **and** either its callsign is equal or it lies within 0.02° in
  latitude and longitude (about 2 km). The kept row keeps its position and
  fields and takes a field it lacks (offset, tone, mode, place) from the
  joining row; its description names every source that listed it. Every
  merge is counted and printed, and in the document. **The APRS layer is
  never an input.** GPX only: QMapShack and Navit already draw every
  layer, and a merged POI would draw each repeater twice beside them. A
  `.rows.json` that cannot be read is skipped by name, and a layer written
  before this change (no `.rows.json`) is named as "re-import to include".

## 6. Commands and documents

- `maps repeaters import [FILE...] [--exported D] [--from-open-repeater
  [FILE] | --from-osm | --from-direwolf-log FILE...] [--json]`
- `maps repeaters fetch-etcc`, `maps repeaters fetch-brandmeister`: no JSON
  form, like `fetch-hearham` (the disclosure is printed before the
  request).
- `maps repeaters remove [--layer ID] [--json]`.
- The `repeaters` document gains `layer_id` and `all_sources` (null, or the
  merged file's path, layers read, rows written, merges, layers skipped);
  `repeaters-removed` gains `layers`. Within schema 1: fields added, none
  removed. Neither carries a callsign, a position, a region or a region's
  digest.

## 7. Not carried, each for its reason

RepeaterBook bulk (written permission needed for bulk extraction,
mirroring, offline bundling); RadioReference (private viewing only without
a licence); RFinder (paid app, no bulk data); the ARRL directory (powered
by RepeaterBook, same terms); FCC ULS (no repeater positions); RadioID
(mapping excluded in its terms, no coordinates); the WIA CSV (all rights
reserved, no coordinates); repeatermap.de (token on request); D-STAR, YSF
and NXDN lists (personal-use HTML or internet reflectors without
coordinates). **ACMA's register is a route named, not built**: a 67.5 MB
daily file whose licence permits derivatives with attribution, 493
repeaters with positions; a later data unit, with a generated extract and
a hosting decision.

## 8. Tests

Synthetic only: `N0CALL`, `N0TST`, Springfield IL and public example
coordinates. Every parser, every skip reason and refusal; the frequency
heuristics for all four measured spellings; the hotspot filter (6, 7 and 9
digits, tx = rx); the Direwolf log captured from Direwolf itself on
synthetic packets; osmium over a tiny synthetic extract built at test time
by `osmium cat` (skipped where osmium is absent), and the XML reader on its
own everywhere; the cross-source merge (call match, distance match, 0.03°
kept apart, precedence, field fill, counts, APRS excluded); the layers'
coexistence, remove by id, registrations of several layers; the generator
against a faked fetch, its offline check falsified; `artifacts` listing
the unit with the name a mirror is asked for; both fetches against a
loopback server; both documents validated, with no callsign, position or
region in either.

## 9. Not built: the maintainer decides

- Whether the Bunker may hold unverified snapshots of hearham-class data
  (hearham, ETCC, Brandmeister).
- Writing to the RSGB, the US coordinators and Brandmeister for an
  explicit open licence: the only route to real US gain.
- Any APRS-IS capture: `N0CALL` and `NOCALL` were refused by aprsc, and
  whether a non-callsign login is acceptable is his call.

## 10. Owed to the bench

QMapShack listing each layer's `.poi` as its own collection and loading
`repeaters-all.gpx`; Navit drawing two textfile maps from one mapset; a real
`fetch-etcc` and `fetch-brandmeister` (the parsers are written from the
measured headers and the spike's saved files' shapes); `--from-osm` on the
laptop's own extracts; a day of Direwolf's real log through
`--from-direwolf-log`; `install open-repeater` from the publisher and from
a Bunker.
