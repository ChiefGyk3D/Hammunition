<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Offline navigation: maps on the laptop before you need them

A phone's navigation leans on the phone network for its maps and often for
its routing. At a remote site, on a served agency's deployment, or after a
storm has taken the towers down, that is exactly what is missing. The
`navigation` profile puts OpenStreetMap maps for the regions you choose on
the laptop, converted for Navit, with Navit following your GPS receiver
through gpsd and speaking the turns. Once it is installed, using it needs no
network at all.

Daily use and EMCOMM are the same setup. The maps have to be on the disk
before anything goes wrong, so the way to be ready for the bad day is to use
it on ordinary days and refresh it as routine. The decision record behind
all of this is **D-057** in `docs/DECISIONS.md`.

The examples below use Vermont and New Hampshire. Use your own regions.

---

## What you need first

- **A GPS receiver that gpsd can see.** Almost any USB GNSS receiver works;
  `docs/hardware/gps-receiver-class.md` covers setting one up (the short
  version: be in the `dialout` group, plug it in, and run `cgps`). If you
  park the receiver with `hammunition hardware park` to save power, wake it
  again before you navigate.
- **Disk space.** See [Disk planning](#disk-planning) below. A US state's
  download ranges from 20.3 MB (District of Columbia) to 1.29 GB
  (California) — Texas, a mid-large state, is 681 MB; a large country is
  gigabytes to tens of gigabytes while it converts.
- **A network connection at install time**, and only then.
- **Audio output**, for spoken directions.

The profile is marked post-1.0: it is built and its pieces are tested, but it
has not yet been run end to end on real hardware. [What has not been
measured yet](#what-has-not-been-measured-yet) lists exactly what that means.

---

## 1. Choose your regions

Regions are Geofabrik's own download paths: `north-america/us/vermont`,
`europe/germany/bayern`. Any region Geofabrik offers is accepted, from a
whole continent down to a state or province.

To find the path for a place, list Geofabrik's regions and filter them:

```
hammunition maps regions vermont
hammunition maps regions germany
```

This fetches Geofabrik's region index when you run it, and only then. Then
save the regions you want:

```
hammunition station set --map-regions north-america/us/vermont,north-america/us/new-hampshire
```

`--map-regions` replaces the whole list each time, so to add a region, give
the full list again with the new one in it; to drop one, give the list
without it. The next install removes the dropped region's files and says so
in the plan before it does. An empty `--map-regions` is refused; to remove
every region, uninstall `osm-navit` and `osm-regions` (see
[Removing it](#removing-it)), and the station file keeps the list until you
set a new one.

The regions are stored in your station config
(`~/.config/hammunition/station.yml`, readable only by you) beside your
callsign. A list of regions says where you live or travel, so
`hammunition station show` prints how many are set and never their names.
Keep that in mind before pasting the station file anywhere.

Pick regions for where you would actually need to drive: home, the next
state over if you cross into it, the route to your served agency, the
places you deploy to. Adjacent regions each get their own map.

---

## 2. Choose how fresh the maps are

```
hammunition station set --map-freshness yearly     # the default
hammunition station set --map-freshness monthly
hammunition station set --map-freshness latest
```

| Mode | What it fetches | How it is usually checked |
|---|---|---|
| `yearly` | Geofabrik's extract from 1 January this year | sha256 Hammunition measured, for the 50 US states and DC |
| `monthly` | The extract from the 1st of this month | sha256 when this month is in the pin list, otherwise Geofabrik's MD5 |
| `latest` | Geofabrik's newest extract, usually from yesterday | Geofabrik's MD5 only |

**Yearly is the right choice for most people.** Roads change slowly, a map
from 1 January is a good map for the whole year, and it is the mode that is
checked most strongly. Choose `monthly` or `latest` if you map actively, or
an area has changed a lot and you want the change now, and accept the weaker
check that usually comes with it. [What the verification wording
means](#what-the-verification-wording-means) explains the difference.

With no freshness set, `yearly` is used.

---

## 3. Look at the plan, then install

Always look before you install:

```
hammunition install navigation --dry-run
```

Among everything else the plan prints, the map regions get their own
section. For Vermont and New Hampshire in yearly mode it reads:

```
Map regions, from station config (D-057):
  will be downloaded and installed:
    north-america/us/vermont        260101    44.4 MB  sha256, pinned by Hammunition
    north-america/us/new-hampshire  260101    68.1 MB  sha256, pinned by Hammunition
  will be converted for Navit (map sizes an estimate, measured on three regions, scratch on one):
    north-america/us/vermont        260101  about 40.0 MB
    north-america/us/new-hampshire  260101  about 61.3 MB
      licence: ODbL-1.0, stated at https://www.openstreetmap.org/copyright
      download total: 0.11 GB; about 0.21 GB of disk with Navit's maps (estimate, measured on three regions, scratch on one)
      installs under <prefix>/share/hammunition/data/
```

Each region's line is the dated file it will fetch (`260101` is 1 January
2026), its size, and how it will be checked. A region already installed at
that date says `already installed, current` and is not downloaded again. The
commands section shows each download and each conversion, including where
the conversion runs and how much scratch space it needs.

That "0.20 GB of disk with Navit's maps" line is narrower than the 2.8×
figure in [Disk planning](#disk-planning) below: it is only the download
and the converted map for the regions this run is about to fetch, and it
does not count the verified copy that stays in the download cache (the
Disk planning figures do, until you clear it).

Then install for real:

```
hammunition install navigation
```

Run it as yourself. The engine asks for `sudo` for the steps that need it,
apt and writing the maps under `/usr/local`, and prints each of them first.
The conversion runs as you, never as root, in
`~/.cache/hammunition/build/osm-navit/`, and the finished map is checked
again as it is copied into place. How long a conversion takes has been
measured on one region only: a 6.1 GB country took 75 minutes on a laptop
i7. A single state is a small fraction of that size.

**If you have not set any regions**, the plan says the two map units are
deferred and names the command to run; Navit and gpsd install anyway, and
running the install again after `station set --map-regions` adds the maps.

**If one region fails** (a download that does not verify, or a conversion
that fails), the other regions still install and convert, and Navit is
configured with the maps that exist. The run then ends with an error naming
each region that did not make it. Run the install again to retry them: the
regions that succeeded are skipped.

### What the licence means for you

OpenStreetMap data is under the Open Database License. You may use it for
anything, including navigation, EMCOMM and commercial work. If you publish
a map made from it, credit "© OpenStreetMap contributors" and say the data
is available under the ODbL; if you share a database made from it, offer it
under the ODbL too. Hammunition states that obligation and does not judge
your use.

---

## 4. Start it: the launcher

The install gives you `navit-offline`, on your `PATH` and as a menu entry,
*Navit (offline navigation)*, under *Operate the Station → Navigation &
Maps* once you have run `hammunition menus apply`.

```
navit-offline
```

It opens Navit with a configuration Hammunition writes: Debian's own
`/etc/navit/navit.xml` with every installed region added, the first start
centred on the first of your regions, the view following your GPS receiver,
and spoken directions through `espeak-ng`. That configuration lives at
`/usr/local/share/hammunition/data/osm-navit/navit.xml` and is rewritten on
every install, so do not edit it by hand. Plain `navit` still runs Debian's
configuration, untouched, and your `~/.navit` directory (bookmarks, the last
destination) is never touched either.

Navit's interface is built for a touch screen. There is no menu bar: click
or tap the map to open the menu, which is a grid of large tiles, and set a
destination from there. The Navit wiki (https://wiki.navit-project.org/)
documents the menus.

---

## 5. "Where am I?"

Situational awareness is a mode of its own, and it needs nothing extra:

- **Navit with no destination set** is a moving map. It follows the GPS and
  shows your position and speed. Start `navit-offline` and do not route
  anywhere.
- **`cgps`**, in a terminal, is the text view: latitude, longitude,
  altitude, speed, time and the satellites in use. It is the fastest way to
  read a position aloud over the radio.
- **`xgps`** is the same in a window, with a sky plot of the satellites.

Both come from `gpsd-clients`, which the profile installs. If `cgps` shows
no fix, the problem is the receiver or gpsd, not the maps: the receiver
needs a view of the sky, and a fix from cold takes a minute or two.

A Maidenhead grid-square readout is not part of this profile; the station
dashboards carry that.

---

## 6. Keep the maps fresh

Refresh as routine, on an ordinary day with a network, not when you need
the map. `hammunition update` is the reminder:

```
hammunition update
```

It reports, for `osm-regions`, how many regions are installed and how many
have a newer date pinned for them — never the regions themselves, by the
same rule that keeps a region list out of `station show`: it is the same
class of fact as a grid square (D-057), and the install plan is the only
place names appear. A report reads, for example:

```
osm-regions  behind the pin  2 regions installed; 1 behind the pin (newer map data pinned: 260901)
```

It checks from the files on the laptop and the catalog; it downloads
nothing. When it says a region is behind the pin:

```
hammunition install osm-regions osm-navit
```

fetches the newer file for each region that has one, converts it again, and
leaves the regions that are already current alone. Older cached copies of a
region are deleted once its new one is installed, and the plan names them.

In yearly mode that is once a year, after 1 January. Hammunition measures
its pins for the new year after Geofabrik publishes the new file, and
`update` says a newer map is pinned once the catalog you have carries them.
If you install in the new year before then, the plan will say the new file
is checked by MD5 only: you can take it then, or wait for the pins and the
stronger check. The map is the same file either way.

In `monthly` mode, refresh after the 1st of each month. In `latest` mode,
refresh whenever you like; every run fetches Geofabrik's newest file.

---

## 7. With no network

Everything the maps need at the moment of use is already on the laptop:
Navit, the converted maps, the configuration, gpsd and the voice. Nothing
asks the network when you navigate.

If you run `hammunition install navigation` with no network, regions that
are already installed are kept exactly as they are, and the plan says it
could not check for a newer map for each one. A region you added but never
installed cannot be fetched, and the plan refuses, naming it, without
changing anything. Connect and run it again when you can.

Before a deployment, check it works offline on purpose: turn networking off
(`nmcli networking off`), start `navit-offline`, confirm the map, your
position and a route, then turn networking back on (`nmcli networking on`).
That is the test worth doing at home.

---

## Disk planning

For each region, the plan estimates and checks, before anything downloads:

| What | How much | Where | How long it stays |
|---|---|---|---|
| The download, verified | the region's size | `~/.cache/hammunition/artifacts/` | Until you delete it; a cache, safe to clear |
| The installed region file | the region's size | `/usr/local/share/hammunition/data/osm-regions/` | Until uninstall or the region is dropped |
| Navit's converted map | about 0.9× the region | `/usr/local/share/hammunition/data/osm-navit/` | Until uninstall or the region is dropped |
| Conversion scratch | about 2× the region, plus the converted map staged | `~/.cache/hammunition/build/osm-navit/` | Only while it converts |

If a conversion fails, maptool's scratch stays in
`~/.cache/hammunition/build/osm-navit/`, so the failure can be looked at.
Its `country_*_broken_.tmp` and `country_*_poly_.tmp` files are cleared the
next time a region's map installs; anything else it left is not. All of it
is safe to delete by hand whenever no install is running.

So while a region converts, allow about 5.8 times its download
size if the cache and `/usr/local` are on the same disk; afterwards it takes
about 2.9 times (1.9 if you clear the download cache). A single US state
ranges from 20.3 MB (District of Columbia) to 1.29 GB (California); Vermont
is 44.4 MB. If there is not enough space, the plan refuses before anything
is fetched and prints the estimate and what is free on each disk that is
short — a disk with enough room is not named.

The 0.9× map factor comes from **three regions** converted on the field
laptop: a 6.1 GB country that became a 4.7 GB map (about 0.77×) in 75
minutes on an i7-1185G7 with a peak of about 2.4 GB of memory, and two
US-state-sized regions on 2026-09-28 that converted at 0.874× and 0.856×.
It was 0.8× from the first region alone, which was low for the other two,
so it now errs above them. The 2× scratch factor is from the country-sized
region only. The plan calls both an estimate for that reason.
A very large region may need more memory than a small machine has.

---

## What the verification wording means

Every region's plan line ends with one of two phrases, and you are told
which every time, whether or not you pass `--yes`:

- **"sha256, pinned by Hammunition"** — Hammunition downloaded this exact
  file, took its sha256, and recorded it in
  `catalog/data/geofabrik-pins.yaml`. Your download must match that hash.
  A file that was damaged or deliberately altered after it was pinned will
  not match. Today that covers each of the 50 US states and DC, for 1
  January 2026 and 1 September 2026, measured 2026-09-28.
- **"MD5 from Geofabrik only; not pinned"** — no pin exists for this region
  and date, so the download is checked against the MD5 Geofabrik publishes
  beside the file. That reliably catches a damaged or incomplete download.
  It does **not** protect against someone who can change the file on
  Geofabrik's server, because they can change the MD5 beside it too. This
  is the weaker check; it is allowed because the alternative was to offer
  maps for the US only, and it is always disclosed. Every region outside the
  pin list gets it, as does every region in `latest` mode, and a pinned
  region on a date the pin list does not yet cover.

Either way, a file that does not match is not installed and is not
converted, and the run ends with an error naming it.

Anyone can ask for a region to be pinned: it is one line in
`scripts/gen_geofabrik_pins.py` and a regeneration, which is how the pin
list stays exactly what that script says.

---

## Troubleshooting

### Navit opens on a blank map

A plain grey or black screen with no roads, even with a GPS fix, means
Navit is looking at a place where you have no map.

**Configurations written by Hammunition 0.10.0 and earlier** kept Navit's
stock starting point, which is Munich, and did not tell Navit to follow the
GPS: the view stayed in Germany whatever the receiver said. Run the install
again and the configuration is rewritten to start on the first of your
regions and to follow the receiver:

```
hammunition install navigation
```

**Navit remembers where you last looked.** The starting point in the
configuration is only used the first time: after that, Navit restores its
last view from `~/.navit/center.txt`. If that file was written while the
view sat on Munich, Navit goes back there on every start, new configuration
or not. Remove it, and the next start opens on your maps:

```
rm -f ~/.navit/center.txt
```

It holds nothing but that last position; your bookmarks and destinations
are in other files in `~/.navit/` and are not affected.

**If it is still blank**, check that you have a fix (`cgps` in a terminal)
and that the fix is inside one of your regions: a map of one state shows
nothing while you are in another.

---

## Removing it

```
hammunition uninstall osm-navit osm-regions
```

removes the converted maps, Navit's generated configuration and the region
files, and leaves Navit installed; `--dry-run` shows what it will remove
first. Your station config keeps its regions until you
change them; the download cache in `~/.cache/hammunition/artifacts/` is
yours to clear.

---

## What has not been measured yet

These are built, and are not claimed until they have run on the field
laptop and been recorded in `docs/reference/bench-verification-5430.md`:

- The whole install through Hammunition on real hardware. The conversion
  time and scratch figures above come from one region converted by hand;
  the map-size factor also rests on two US-state-sized regions converted on
  the field laptop on 2026-09-28.
- **Routing from one region into the next.** Each region is converted into
  its own map. Whether Navit routes across the border between two of them,
  a trip from Vermont into New Hampshire, has not been tested. Until it has,
  plan such a trip as two legs.
- The whole path with networking off: start, position from gpsd, a route,
  voice.
- Spoken directions for a street whose name contains an apostrophe, which
  Navit's own way of calling the speech program may break.
- `UrllibProbe.text` has run live against Geofabrik's region index
  (2026-09-28: `index-v1-nogeom.json`, 555 regions parsed by `region_ids`).
  `UrllibProbe.head` — the reachability check a fetch, and now a plan-time
  region check, both depend on — remains unmeasured against the live
  server; the tests stand in for it.

Hiking and topographic maps (QMapShack, contours) and offline reference
(Kiwix, a local tile server) are later pieces of this work and not in this
profile.
