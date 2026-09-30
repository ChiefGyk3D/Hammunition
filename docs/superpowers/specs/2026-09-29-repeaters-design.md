<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Repeater overlays: the operator's own export, converted on this machine (D-064)

**Date:** 2026-09-29. **Status:** design approved by the maintainer from the
option-A spike (repeaters on QMapShack and Navit, measured 2026-09-29; the
spike's section 5 is this design). **Decision:** D-064.
**Depends on:** D-021, D-033, D-049, D-057, D-059, D-061.

Every row in every fixture is synthetic: `N0CALL`, `N0TST`, Springfield IL
(39.80 N, 89.64 W), the spike's own example city.

## 1. What it is

A command, not a catalog unit. The operator exports repeaters from a source
they have an account with (RepeaterBook's website export) or types their own
list, and `hammunition maps repeaters import FILE...` converts it into three
overlays on this machine, fully offline:

| Output | For | File |
|---|---|---|
| GPX 1.1 | QMapShack's File → Load, a phone, a Garmin unit | `repeaters.gpx` |
| Mapsforge POI (sqlite) | QMapShack's POI collections, persistent | `repeaters.poi` |
| Navit textfile | Navit's map, and its POIs → Other list | `repeaters.navit.txt` |

All three live in `~/.local/share/hammunition/overlays/repeaters/`
(`$XDG_DATA_HOME` honoured), mode 0600, directory 0700, owned by the
operator. Never under the root prefix, never in the catalog, never in the
transaction log. Run as root it refuses: the files are the operator's.

`hammunition maps repeaters fetch-hearham` is the one network route: it asks
hearham.com's unauthenticated API on request only, records the sha256 of what
it received, marks the layer unverified, and converts it exactly as an import.

`hammunition maps repeaters remove` deletes the files and unregisters them.

## 2. Inputs

Detected from the content, never from the name alone.

| Input | Recognised by | Fields read |
|---|---|---|
| RepeaterBook GPX | XML root `gpx` (1.0 or 1.1), any `<wpt>` with `lat` and `lon` | `name`, `desc`, `cmt`; callsign and output frequency found in `name`, then `desc` |
| RepeaterBook CSV | a header holding `Callsign`, `Frequency`, `Lat`, `Long` (case and surrounding spaces ignored) | optional `Input Freq`, `PL`, `TSQ`, `Nearest City`, `Landmark`, `Use`, `Operational Status`, `Last Update` |
| hearham JSON | a JSON array of objects with `callsign`, `frequency`, `latitude`, `longitude` | `offset` (Hz), `encode`, `decode` (`"0.00"`/`"0"`/empty = none), `mode` (stripped, upper-cased), `city`, `operational` (0 = off the air) |
| Hand CSV | the exact header `callsign,output_mhz,offset_mhz,tone,mode,lat,lon,name,notes` | all nine; WGS84 decimal degrees, UTF-8 (a BOM is accepted) |

**Refused by name, nothing written, exit 1:**

- a CHIRP CSV (header begins `Location,Name,Frequency,Duplex`): measured to
  drop Lat/Long and keep only "near <city>"; geocoding a town would invent
  a position;
- a CHIRP `.img` (the `.img` suffix, or CHIRP's metadata magic
  `\x00\xffchirp\xeeimg\x00\x01` from `chirp_common.py`): radio memories, no
  coordinates;
- a RepeaterBook CSV with `Callsign` and `Frequency` but no `Lat`/`Long`;
- KML or KMZ: deferred, the same data as the GPX;
- XML carrying a `<!DOCTYPE` or `<!ENTITY`: no GPX needs one;
- anything else: named as not a format this reads, with the four listed.

One refused input refuses the whole import: nothing is half-replaced.

A row without a usable position (missing, not a number, out of range, or
0,0), or without a callsign, is skipped and counted by reason, with the first
line or waypoint numbers named. An import in which no row survives writes
nothing and exits 1.

## 3. Deduplication

Key: callsign (trimmed, upper-cased) + output frequency in Hz + latitude and
longitude each rounded to 0.01°. Callsign plus frequency alone would have
collapsed 1,050 multi-site keys in hearham's 22,698 rows (spike §3). On a
merge the row with the newer `Last Update` wins when both carry one,
otherwise the first read; every merge is counted and printed. A GPX waypoint
with no frequency found keys on its own name instead of the callsign and 0 Hz.

## 4. The layer

- **Name:** `Repeaters (own export YYYY-MM-DD, personal use)`. The date is
  `--exported YYYY-MM-DD` when given, otherwise the input file's mtime (D-031
  practice: the input's date, not the day of the run); with several inputs,
  the oldest. A fetch names its layer
  `Repeaters (hearham YYYY-MM-DD, unverified)`, dated by the fetch.
- **GPX:** `<metadata><name>` the layer name, `<desc>` the attribution and
  (for a fetch) the observed sha256; each `<wpt>` has `<name>` `CALL FREQ`
  (`N0CALL 146.940`), `<desc>` offset, tone, mode, use, status, place and
  notes, then the source (`Data courtesy of RepeaterBook.com` for an export),
  `<sym>Tall Tower</sym>` (a QMapShack built-in: nothing is written into
  QMapShack's own directories) and `<type>repeater</type>`.
- **POI:** the Mapsforge schema QMapShack 1.17.1's `CPoiFilePOI` queries
  (`metadata`, `poi_categories`, `poi_data`, `poi_category_map`, the
  `poi_index` rtree); one category, `Amateur radio repeaters`; `bounds` as
  `minLat,minLon,maxLat,maxLon`; `comment` the layer name and attribution.
  The rtree stores float32 and QMapShack reads 0.1° tiles with
  `minLat >= tile` and `maxLat < tile + 0.1`: a point on a tile line falls in
  neither tile (spike). So a coordinate whose stored box would straddle a
  0.1° line, computed with SQLite's own rounding, is moved to the float32
  just inside the tile north or east of it (a few metres at most), and every
  point near a line, over the whole range of latitude and longitude, is
  asserted findable by QMapShack's own query in exactly one tile. (Amended
  after the review: a fixed 1e-5° band lost points past about 64°.)
- **Navit:** one line per repeater,
  `lon lat type=poi_custom0 label="CALL FREQ" icon_src="/usr/share/navit/icons/tower.png"`;
  `poi_custom0` has a label in the stock layout's "POI Labels" layer, where
  `poi_communication` has none (spike §2).

Every file is written whole to a temporary name in the directory and renamed
over the old one, so no file is half-written; an import interrupted between
two renames can leave new and old files together, which the next import
replaces and `remove` clears, temporaries included. Each
import replaces the layer: to combine an export with hearham's data, pass
both files to one import.

## 5. Registration

**QMapShack.** `[Canvas] poiPaths` gains the overlay directory, through
`qmapshack_config.ensure_paths`, the same editor and the same refusals as
`maps qmapshack` (a symbolic link, a non-regular file, a line it cannot read:
refused and left untouched; the rest of the layer is still written and the
reason named). `maps qmapshack` also adds it at every start while a
`repeaters.poi` exists, and takes it out while none does: a QMapShack that was
open during an import writes its configuration back on exit, and the launcher
puts the path back before the next start.

**Navit.** Navit's launcher opens a configuration under the root prefix that
the operator cannot write, and the operator's `~/.navit` is never touched
(navit manifest). So the launcher changes from
`navit /usr/local/share/hammunition/data/osm-navit/navit.xml` to
`hammunition maps navit`, the same shape as `maps qmapshack`: it reads the
generated configuration and, when the operator has a repeater layer, writes
`~/.local/share/hammunition/overlays/navit.xml` (0600) with a
`<map type="textfile" enabled="yes" data=".../repeaters.navit.txt"/>` added to
its one enabled mapset by `navit_config.add_maps`, then runs Navit on it.
With no layer it runs Navit on the generated file, as before, and removes a
stale per-user copy of ours. Under root it does the latter only. `import`
writes the per-user copy too when the generated configuration exists, so the
effect is inspectable at once.

**Remove** deletes the three files, the per-user Navit copy and the
directory when empty, and takes the path out of `poiPaths`. Absent files are
not an error: it is idempotent.

## 6. Licence text, printed at import

- RepeaterBook export (GPX, RepeaterBook CSV): "Data courtesy of
  RepeaterBook.com. Exported by you for your own personal, non-commercial use
  under RepeaterBook's export terms (repeaterbook.com/wiki/doku.php?id=exports):
  the data may not be redistributed in any form. Hammunition converts it on
  this machine only and never uploads, shares or bundles it; the overlay files
  are yours under the same terms. Positions are approximate: do not use them
  to visit a repeater site." followed by the terms page,
  `repeaterbook.com/about/legal`. Every GPX gets this text: RepeaterBook's
  GPX layout is unmeasured, so an export cannot be told from another GPX,
  and the attribution is the cautious default.
- hearham: "hearham.com states no licence for this data (its terms page is a
  service agreement; the Repeater-START app's GPL covers code, not data).
  Carried under D-033: used on your request, never redistributed. hearham:
  'Under no circumstances should this be relied upon for medical emergencies,
  or any other life-and-death operations.' Fetched <time>, sha256 <observed>,
  not verifiable." For an imported hearham file, "Read from <file>" replaces
  the fetch time.
- Hand CSV: "Your own data. Hammunition adds nothing to it and sends it
  nowhere."

## 7. The commands

```
hammunition maps repeaters import FILE... [--exported YYYY-MM-DD] [--json]
hammunition maps repeaters fetch-hearham
hammunition maps repeaters remove [--json]
hammunition maps navit
```

`import` prints the licence text for each source, then counts: read per
input, skipped by reason, merged, written; the layer name; each file
written; what was registered and where. `--json` prints a `repeaters`
document, `remove --json` a `repeaters-removed` document (D-059); text and
JSON render from the same object. Neither carries a repeater's position or
callsign: counts, paths and the layer name only. `fetch-hearham` and
`maps navit` have no `--json` form (a fetch prints its disclosure; `navit`
replaces itself with a GUI). Exit 0 on success; 1 on a refusal or failure.

`fetch-hearham` fetches `https://hearham.com/api/repeaters/v1` (about 9.5 MB,
22,698 rows on 2026-09-29), bounded at 64 MB, 60-second timeout, redirects to
HTTPS only, TLS verified; its disclosure is printed before the request. The
URL is a module constant a test points at a loopback server.

## 8. Not a D-049 data unit

A data unit is an artifact the engine fetches from its publisher and pins by
sha256. An export is neither fetched nor pinnable, and RepeaterBook forbids
us holding it. hearham's API is live with no ETag and no dated snapshot: a pin
would be stale the day it was taken, so the fetch records what it observed
and says it is unverified.

## 9. Not carried, documented

Any fetch from RepeaterBook (its API is gated; its data-use page forbids bulk
extraction and offline bundling without written permission). Navit address
search of repeaters (the textfile driver has no search method; they list
under POIs → Other). Xastir `.gnis` (its map tree is root-owned under
`/usr/share/xastir`). YAAC `.pos` (objects YAAC imports can be transmitted:
a D-021 matter, not a map). FCC ULS (no coordinates). KML (deferred).

## 10. Tests

Every parser against synthetic fixtures; every refusal by name; dedup (a
co-sited duplicate merged, the same call and frequency 120 km away kept,
newer `Last Update` wins); the three writers, the GPX parsed back, the POI
queried with QMapShack's verbatim SQL for every point including one on a
tile line (falsified: without the nudge that point is lost); Navit lines;
`add_maps` idempotent and refusing a mapset count other than one; the
QMapShack registration add and remove, byte-for-byte elsewhere; modes 0600
and 0700; root refused; the whole import through `cli.main` in text and
`--json` (validated against the schema, text values in the document, no
position or callsign in either); `remove` idempotent; `fetch-hearham`
against a loopback HTTP server only; `maps navit` with `execvp` stubbed.

## 11. Owed to the bench

QMapShack drawing the GPX and the `.poi` (and whether `poiPaths` under
`[Canvas]` is where it reads the list); Navit's `poi_custom0` label and icon
and the POIs → Other listing; a real RepeaterBook GPX and CSV export's
columns and `<desc>` layout, which need one logged-in export.
