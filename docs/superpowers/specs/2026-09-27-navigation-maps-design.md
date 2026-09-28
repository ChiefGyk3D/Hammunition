# Navigation, piece 1: offline map data and driving

**Status:** section 1 approved in conversation 2026-09-27, the rest written for
review in this document; awaiting the maintainer's read.
**Decision record:** D-057, written with the implementation. It amends D-049
(freshness modes; derived data) and D-055 (one new fine tag).
**Origin:** the maintainer, 2026-09-27: turn the laptop into a GPS navigator
"for pure emergency situations, phone and everything is down", and "for daily
use as well as EMCOMM; this can be for fun and shit hit the fan". Driving and
hiking both, with plain situational awareness as a first-class mode.

## 1. The three pieces, and this one

| Piece | What | Spec |
|---|---|---|
| **1** | Region selection, freshness modes, the yearly pin list, a derived-data step, Navit for driving and "where am I" | this document |
| 2 | Hiking: QMapShack, `mkgmap` + `mkgmap-splitter`, elevation data for contours, GPSPrune | its own, after this lands |
| 3 | The rest of D-049's queue: Kiwix with a Wikipedia ZIM, ETC's tileset with `mbtileserver` | its own |

Every tool in pieces 1 and 2 is in Parrot 7.3's archive, measured 2026-09-27:
`navit` 0.5.6, `maptool` 0.5.6, `espeak-ng` 1.52.0, `osmium-tool` 1.18.0,
`qmapshack` 1.17.1, `mkgmap` svn4923, `mkgmap-splitter` svn654, `gpsprune` 25.2,
`viking` 1.10, `marble` 25.04, `kiwix` 2.4.1. Nothing is built from source.

## 2. Daily use and EMCOMM are one path

Maps must be on the machine before anything goes wrong, so the daily path is the
emergency preparation:

- Everything installs ahead of time and works with no network.
- `hammunition update` reports each region's map date and whether a newer pin
  exists, so refreshing is routine rather than remembered in a crisis.
- The Navit launcher starts wired up: following the GPS through gpsd, voice on,
  every installed region loaded.

## 3. What the operator sets (approved)

```
hammunition station set --map-regions north-america/us/vermont,north-america/us/new-hampshire
hammunition station set --map-freshness yearly        # yearly (default) | monthly | latest
```

- **Regions** are Geofabrik's own paths, and any region Geofabrik offers is
  accepted. `hammunition maps regions [FILTER]` lists them, from
  Geofabrik's published index, fetched on request only.
- **Freshness** is one setting for every region.
- **Unset:** the map data unit is deferred by name and Navit still installs
  (D-035, D-049 rule 3). The plan names the command to run.
- Stored in station config beside the other station values, mode 0600; region
  names are not personal data, but they sit with values that are.

## 4. How a region file is fetched and verified

Measured on Geofabrik 2026-09-27 (Vermont's page): a dated file every
1 January from 2020 to 2026 (2014-2019 are also linked), the 1st of the last three
months (`260701`, `260801`, `260901`), and the last seven days; `-latest`
redirects (302) to today's dated file; every file has a published `.md5`.

| Freshness | File fetched | Verified by |
|---|---|---|
| `yearly` (default) | `<region>-YY0101.osm.pbf`, this year's 1 January | **sha256 from our pin list** when the region is pinned; otherwise Geofabrik's MD5 |
| `monthly` | `<region>-YYMM01.osm.pbf`, this month's 1st | sha256 from the monthly pin list when pinned; otherwise Geofabrik's MD5 |
| `latest` | the dated file `-latest` redirects to, resolved at plan time | Geofabrik's MD5 only |

The plan prints, per region: the dated file, its size, and one of **"sha256,
pinned by Hammunition"** or **"MD5 from Geofabrik only; not pinned"**. MD5 is
disclosed as the weaker check every time, never silently. `--yes` does not
change what is disclosed.

**The pin list** is a new generated file, `geofabrik-pins.yaml` under `catalog/data`, written by
a new generator, `gen_geofabrik_pins.py` in `scripts`: for each pinned region and each of the
current yearly and monthly snapshots, the URL, size, sha256 and the date it was
measured. Pinned regions at first: the 50 US states and DC. Adding a region is
one line in the generator's region list and a regeneration. It is run on the
maintainer's machine (about 10 GB per pass, all downloaded and hashed, none
kept); CI's weekly pin review checks every pinned URL still answers, and a
monthly pin that has aged out (Geofabrik keeps about three) fails that job with
the command to regenerate. A generated YAML file in `catalog/` is data, the
same standing as `ambiguous-ids.yaml`.

## 5. Derived data: converting a region for an application

D-049's `data` method fetches and installs files; Navit cannot read `.osm.pbf`.
New: a **derived artefact**, produced by running a converter from an installed
package over a fetched artefact, recorded in the transaction log like any
other artefact, and removed by `uninstall`.

- **The catalog names a converter by enum, never by command line.** The manifest
  says `converter: navit-maptool`; the engine owns what that means
  (`maptool --protobuf -i <input> <output>`), exactly as `build_system: cmake`
  is an enum the source backend implements. The catalog stays pure data.
- The converter's package is a `depends` of the data unit, so it is installed
  first.
- The plan prints each conversion with its input, output and an estimate of
  output size (measured ratio, §9).
- Output: `<prefix>/share/hammunition/data/osm-navit/<region-slug>.bin`, with a
  Navit map snippet `<region-slug>.xml` beside it (§6). The downloaded `.pbf`
  is kept in `…/data/osm-regions/` so piece 2's converters reuse it without a
  second download.
- Idempotent: a region already converted from the same dated input is skipped;
  a changed input reconverts it; a region dropped from station config is
  removed on the next install, disclosed in the plan.

## 6. Navit, wired up

Navit's stock `/etc/navit/navit.xml` already has a vehicle on `gpsd://localhost`
and includes `$NAVIT_SHAREDIR/maps/*.xml` into a mapset. Hammunition does not
edit it and does not touch `~/.navit`.

- The engine generates `~/.config/hammunition/navit/navit.xml` from the
  installed `/etc/navit/navit.xml` at install time, with two changes applied by
  a tested transformation: the `<speech>` element becomes `espeak-ng`, and a
  mapset includes `<prefix>/share/hammunition/data/osm-navit/*.xml`. Built
  from the installed file, so it follows Debian's version.
- The launcher runs `navit ~/.config/hammunition/navit/navit.xml`. The menu
  entry sits under the new category (§7). Running plain `navit` is untouched.
- **Situational mode** is the same Navit screen with no destination set: the
  map follows the GPS, with position and speed shown. `cgps` stays the text
  view. A grid-square readout is piece 2's or Hill's, not this one's.
- **Unmeasured, so measured before it is claimed:** whether Navit routes across
  two separately converted regions (a trip from one state into the next). If it
  does not, routing gets one merged map (`osmium merge` then `maptool`), the
  display keeps per-region files, and the docs say which.

## 7. Catalog

- **Category:** a new fine tag `navigation-maps` ("Navigation & Maps": offline
  maps, turn-by-turn, tracks), in the group that holds `gps-gnss`. D-055 fixed
  the vocabulary deliberately, so D-057 records the addition.
- **Units:**
  - `navit`: apt `navit`, `navit-gui-internal`, `navit-graphics-gtk-drawing-area`,
    `espeak-ng`; launcher as §6. (`navit-gui-gtk` left out: the internal GUI is
    the one that works with a touch screen and on a small panel.)
  - `osm-regions`: data, the Geofabrik region files per §3–4.
  - `osm-navit`: derived data, `converter: navit-maptool`, depends `maptool` and
    `osm-regions`.
  - `gpsd`, `gpsd-clients` already exist and are reused.
- **Profile:** a new `navigation` profile: `gpsd`, `gpsd-clients`, `navit`,
  `osm-regions`, `osm-navit`. Pieces 2 and 3 add to it.

## 8. Failure behaviour

| Case | Result |
|---|---|
| No regions set | Data units deferred by name; Navit installs; the plan names the command |
| A region name Geofabrik does not have | Refused at plan time, naming it and the `maps regions` command |
| A pinned yearly/monthly file 404s | Refused for that region, naming the file; the pin list needs regenerating |
| sha256 or MD5 mismatch | That region is not installed; nothing converted; others continue (D-039's shape) |
| `maptool` fails or writes nothing | That region's conversion is reported unverified; its `.pbf` stays; Navit still gets the regions that did convert |
| Disk space below the plan's estimate | Refused at plan time, with the estimate and what is free |
| No network at install time | Fetches fail by name; already-installed regions are untouched |

## 9. Measurements before claims

On the field laptop, recorded on the bench page:

- Conversion time and output size for a small, a medium and a large state
  (Vermont about 46 MB of `.pbf`; California about 1.3 GB), which sets the
  plan's size estimate.
- Navit routing across two adjacent regions (§6).
- The whole path with the network unplugged: launch, position from gpsd, a
  route, voice.
- `update` reporting a region's date against a newer pin.

## 10. Out of scope here

Hiking and contours (piece 2); Kiwix and tile servers (piece 3); online tiles
of any kind; editing maps (JOSM); Marble and Viking, which piece 2 weighs
against QMapShack; regions pinned beyond US states and DC until someone asks.
