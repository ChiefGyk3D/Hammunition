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
through gpsd and speaking the turns. For trails and terrain it also builds
maps for QMapShack from the same regions, a routing database for walking,
and elevation with contour lines (**D-061**). Once it is installed, using it
needs no network at all.

Daily use and EMCOMM are the same setup. The maps have to be on the disk
before anything goes wrong, so the way to be ready for the bad day is to use
it on ordinary days and refresh it as routine. The decision records behind
all of this are **D-057** and **D-061** in `docs/DECISIONS.md`.

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
- **Memory, for the trail maps**: mkgmap, which builds them, is given 6 GB,
  and the plan says so. On a machine with much less, a Garmin map may fail
  to build; the run names the region, and its Navit map installs anyway.
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
    north-america/us/vermont        260101  about 40.0 MB  border: US
    north-america/us/new-hampshire  260101  about 61.3 MB  border: US
      each region is first merged with its country's closed border (osmium merge, in the
      staging directory, removed afterwards), so maptool files its towns under the
      country and address search finds them; maptool runs with -U, so a town the border
      misses is indexed under the country Unknown, not dropped
      country borders: Natural Earth 1:10m admin-0 countries, 13.3 MB, Public domain
      (Natural Earth's terms of use), sha256, pinned by Hammunition
      licence: ODbL-1.0, stated at https://www.openstreetmap.org/copyright
      download total: 0.11 GB; about 0.21 GB of disk with Navit's maps (estimate, measured on three regions, scratch on one)
      installs under <prefix>/share/hammunition/data/
```

Each region's line is the dated file it will fetch (`260101` is 1 January
2026), its size, and how it will be checked. A region already installed at
that date says `already installed, current` and is not downloaded again. The
commands section shows each download and each conversion, including where
the conversion runs and how much scratch space it needs.

Each line to convert also says whose country border is merged into it
first (`border: US`), which is what makes address search work (see
[Find an address](#5-find-an-address)). The border file itself, Natural
Earth's world country outlines, is the `country-boundaries` unit: it is
listed once under *Offline data that will be downloaded and installed*,
13.3 MB, public domain, checked against a sha256 Hammunition measured. A
region whose country is not known (a whole continent, or a group such as
`us-northeast`) says `border: none known` and converts without one. A map
built by an older Hammunition says `(converter changed)` and is converted
again even though its download has not changed.

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

## 5. Find an address

Navit searches by town, then street, then house number, all offline. With
the internal interface on this install:

1. **Tap or click anywhere on the map.** The main menu opens.
2. Choose **Actions**, then **Town**.
3. The country is already chosen, from your language setting (`LANG`
   ending in `_US` picks the United States). To search another country,
   press the **flag button** at the left of the text field and pick it.
4. **Type the town's name.** Results appear from the first letter, and
   narrow as you type. Pick the town.
5. For a street, use the **street icon** to the right of the text field
   instead of picking the town, and type the street's name.
6. For a house number, pick the street, or use the **house-number icon**,
   and type the number. Numbers are there wherever OpenStreetMap has them,
   which in rural areas is not everywhere.
7. From a result, choose **Set as destination** to route there, or **Set
   as position** to look at it.

**A town you know is there, and the search does not find it**, may be
filed under the pseudo-country *Unknown*. The country borders merged into
the maps are about 1 km coarse, and a few places close to a national
border fall on the wrong side of the line. They are
still indexed, just not under their country. Press the flag button, type
`*`, and pick **\* Unknown, add is_in tags to those cities**; then search
for the town as above. Places there have no state or county beside their
name.

Why it works: Navit's map converter, `maptool`, files every town under a
country by testing it against that country's border, and a state extract
from Geofabrik carries only the pieces of the US border that lie inside
the state. Without a closed border maptool dropped almost every town from
the search index: on one US-state-sized region the index held about a
dozen items for a map that draws a few thousand places. Hammunition now
merges a closed border into each region before converting it, and the
same region's index held over four thousand, a few hundred times as many,
all under the USA and almost all with their state and county; house numbers are indexed wherever OpenStreetMap has them. Maps converted
by Hammunition before this fix are converted again on the next
`hammunition install navigation`; see [Troubleshooting](#troubleshooting).

---

## 6. "Where am I?"

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

## 7. Keep the maps fresh

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

## 8. With no network

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

## 9. Trails and terrain: QMapShack

The same install builds a second set of maps from the same regions, for
walking rather than driving:

- **Garmin maps** (`osm-garmin`) that show paths, footways, tracks and
  bridleways as well as roads, with land use and water;
- **one routing database** (`osm-routino`) over every region, so a route on
  foot can cross from one region into the next;
- **elevation** (`dem-copernicus`): the Copernicus 30 m elevation tiles for
  your regions, about 39 MB each, tens of them for a US state;
- **hillshade, slope and contour lines** (`dem-qmapshack`) drawn from that
  elevation, with a contour line every 20 m.

The plan shows all of it before anything happens, in a *Terrain* block under
*Map regions*. It says how many tiles each region needs, how many of its
squares have no published tile (nothing to download: open sea, or land
Copernicus does not release, which the tile list cannot tell apart) and
what its tiles cost to download. If none of a region's squares has a
published tile, the plan says so as a warning, "no terrain available for
*region* from Copernicus GLO-30", and the region gets no terrain. The rest
of the install carries on: you asked for that region's maps, and they still
install. Then it lists each tile to fetch with its size and how it is
checked, and what will be built with its estimated size. Tile names encode
a latitude and a longitude, so they appear in the plan on your own terminal
and nowhere else.

The first time a region's terrain is planned, the plan asks Geofabrik for
the region's outline to choose its tiles, and says so. The answer is kept
once the terrain is installed, so later plans need no network for it. Until
then every plan asks again, a dry run included, so a dry run with no
network before the first install cannot choose tiles and stops, changing
nothing.

The Garmin maps and the routing database are built as you, never as root,
in `~/.cache/hammunition/build/osm-garmin/` and `.../osm-routino/`, and the
contours in `.../dem-qmapshack/`. mkgmap, the Garmin map builder, is given
6 GB of memory; the plan says so. A region whose Garmin map fails to build
still gets its Navit map, and the run ends naming what failed. The routing
database is one file set for all your regions, so a region that fails to
read fails the database, and the database you already had is kept.

Start QMapShack from its launcher, *QMapShack with your offline maps*, under
*Operate the Station → Navigation & Maps* once you have run
`hammunition menus apply`, or in a terminal:

```
qmapshack-offline
```

The launcher adds the map, elevation and routing directories to QMapShack's
own settings the first time, keeping anything you set there yourself, then
starts it. If it says it cannot read your settings file, nothing was changed
and QMapShack was not started. Add the directories by hand in QMapShack's
setup, or move the file (`~/.config/QLandkarte/QMapShack.conf`) aside and
start it again. From the menu you will not see that message; see
[QMapShack does not start from the menu](#qmapshack-does-not-start-from-the-menu).

In QMapShack:

- **Maps.** Your regions' Garmin maps and the contour map (`contours.vrt`)
  are listed in the map dock. Activate a region's map, then the contour map
  over it.
- **Terrain.** The elevation (`dem.vrt`) is listed in the DEM dock; activate
  it and turn on hillshade or slope there.
- **Route on foot.** In the routing dock choose *Routino (offline)*, the
  database `hammunition`, and the profile `foot`. Place a start and an end
  on the map; the route follows trails. When Routino was run on one region
  for this work, walks of 10 to 17 km came back in 5 to 39 ms.
- **Tracks.** Record, load and edit GPX tracks and waypoints; any track
  shows an elevation profile from the elevation data.

Those four steps are what QMapShack is expected to show with the launcher's
settings; they have not yet been walked through on the field laptop. [What
has not been measured yet](#what-has-not-been-measured-yet) says which.

Routino's foot profile does not read trail difficulty (`sac_scale`): an
alpine path counts the same as a pavement. Look at the contours and judge
the route yourself.

---

## 10. Find an address in Navit, walk it in QMapShack

QMapShack cannot search for an address offline: its search asks online
services, and Routino routes between points, not addresses. Navit can.

1. In `navit-offline`, search for the town and street (and house number,
   where OpenStreetMap has one) as [Find an address](#5-find-an-address)
   describes, and look at the result on the map. Note where it is: the
   nearest trail junction, road end or landmark.
2. In QMapShack, place the route's end there and plan the walk.

A named trailhead is found in Navit only if OpenStreetMap tags it as a
place. Otherwise find the nearest road end in Navit and walk from there in
QMapShack.

---

## 11. Your position in QMapShack: the GPS tether

QMapShack does not talk to gpsd. Run the *GPS position for QMapShack* launcher,
or in a terminal:

```
hammunition maps gps-tether
```

It serves gpsd's position on this machine only, 127.0.0.1 port 10110, and
prints what to enter. In QMapShack open *Realtime*, add *GPS Tether*, and
enter host `127.0.0.1` and port `10110`. It runs while that terminal stays
open; Ctrl-C stops it. Nothing is installed as a service, nothing else on
the network can connect to it, and one program at a time can. Navit reads
gpsd directly and needs none of this.

If `cgps` shows no fix, the tether has nothing to pass on; see
["Where am I?"](#6-where-am-i).

---

## What QMapShack does not do (yet)

- **No offline address search**: use Navit (section 10).
- **Trail difficulty is not routed on** (section 9).
- **No hiking map style.** Trails are drawn by mkgmap's default style; no
  hiking style is packaged in the archive.
- **Contours are unlabelled lines**, legible rather than pretty. Labelled
  contours need a tool the archive does not carry.
- **The Garmin maps have no address index**, and QMapShack would not read
  one anyway.
- **Regions that cross the 180° meridian** (Alaska's Aleutians, Fiji) are
  refused by name for terrain, until how Geofabrik draws such an outline
  has been measured.
- **No terrain where Copernicus publishes none.** Its public 30 m release
  leaves out some land as well as the open sea (Armenia and Azerbaijan, for
  example). A region inside it gets its maps and no terrain, and the plan
  warns by name. The 90 m Copernicus release is the candidate route; it has
  not been measured here.
- **Hillshade drawing** has not yet been confirmed on the field laptop.

---

## Disk planning

For each region, the plan estimates and checks, before anything downloads:

| What | How much | Where | How long it stays |
|---|---|---|---|
| The download, verified | the region's size | `~/.cache/hammunition/artifacts/` | Until you delete it; a cache, safe to clear |
| The installed region file | the region's size | `/usr/local/share/hammunition/data/osm-regions/` | Until uninstall or the region is dropped |
| Navit's converted map | about 0.9× the region | `/usr/local/share/hammunition/data/osm-navit/` | Until uninstall or the region is dropped |
| Conversion scratch | about 2× the region, plus the converted map staged | `~/.cache/hammunition/build/osm-navit/` | Only while it converts |
| The region merged with its country's border | about 1× the region | `~/.cache/hammunition/build/osm-navit/` | Only while it converts; removed afterwards whether it worked or not |
| Natural Earth's country borders | 13.3 MB, once | `/usr/local/share/hammunition/data/country-boundaries/` | Until uninstall |

If a conversion fails, maptool's scratch stays in
`~/.cache/hammunition/build/osm-navit/`, so the failure can be looked at.
Its `country_*_broken_.tmp` and `country_*_poly_.tmp` files are cleared the
next time a region's map installs; anything else it left is not. All of it
is safe to delete by hand whenever no install is running.

So while a region converts, allow about 6.8 times its download
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

With the QMapShack units, each region also takes the following, measured on
one US-state-sized region:

| What | How much | Where | How long it stays |
|---|---|---|---|
| The Garmin map | about 0.85× the region | `/usr/local/share/hammunition/data/osm-garmin/` | Until uninstall or the region is dropped |
| Its build scratch | up to 3× the region, one region at a time | `~/.cache/hammunition/build/osm-garmin/` | Only while it builds |
| The routing database, all regions | about 0.67× all the regions together | `/usr/local/share/hammunition/data/osm-routino/` | Rebuilt when the regions change |
| Its build scratch | up to 6× all the regions together | `~/.cache/hammunition/build/osm-routino/` | Only while it builds |
| Elevation tiles | about 39 MB a tile; tens for a US state | `/usr/local/share/hammunition/data/dem-copernicus/` | Until uninstall, or no region needs the tile |
| Contours | about 5.5 MB a tile, with up to 98 MB of scratch at a time | `/usr/local/share/hammunition/data/dem-qmapshack/` | As long as the tiles |

A tile's download is deleted from the cache as soon as it is installed: a
tile never changes, so there is no reason to keep two copies. The plan
counts all of this with the Navit figures above, and refuses before
anything is fetched if a disk is short.

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

Elevation tiles use the same two levels, in their own words:

- **"sha256, pinned by Hammunition"**: the tile has a row in
  `catalog/data/copernicus-glo30-pins.yaml`, measured by Hammunition.
- **"MD5 from the publisher's object metadata; not pinned by Hammunition"**:
  the tile is checked against the MD5 the storage service keeps for the
  file. It catches a damaged download, not a deliberately altered one.

Today no tile is pinned, so every tile gets the second wording. The pin
list grows as Hammunition measures tiles, in a fixed order that covers the
50 US states and DC, and a tile pinned later is checked the stronger way
from then on. A tile whose stored checksum is not a plain MD5 is refused by
name rather than installed unchecked.

Anyone can ask for a region to be pinned: it is one line in
`scripts/gen_geofabrik_pins.py` and a regeneration, which is how the pin
list stays exactly what that script says.

---

## Troubleshooting

### QMapShack does not start from the menu

Run the launcher in a terminal to see why:

```
qmapshack-offline
```

If it says it cannot read `~/.config/QLandkarte/QMapShack.conf`, nothing was
changed and QMapShack was not started: the file holds something the
launcher does not edit on a guess. Add the directories in QMapShack's own
setup instead, or move the file aside (`mv ~/.config/QLandkarte/QMapShack.conf
~/.config/QLandkarte/QMapShack.conf.old`) and run the launcher again. If
the shell says `hammunition: not found`, run `./bootstrap.sh` from your
Hammunition checkout again, which puts it on your `PATH`
(`hammunition doctor` checks this too).

If QMapShack starts and at once stops with "The specified translations XML
file did not exist", Routino's data file is missing. `hammunition doctor`
names it, and this puts it back:

```
sudo apt-get install --reinstall routino-common
```

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

### Address search finds almost nothing

Maps converted by Hammunition 0.12.0 and earlier were built without a
closed country border, and their search index holds only a handful of
towns. Run the install again:

```
hammunition install navigation
```

The plan marks each such map `(converter changed)` and converts it again
from the region already on disk; nothing is downloaded but the 13.3 MB
border file. If one town is still missing, look under the *Unknown*
country, as [Find an address](#5-find-an-address) describes.

maptool's log for a conversion always warns `Broken country polygon` for
the region's own, partial copy of its country's border. That is expected
and harmless. A warning for the merged border itself fails the conversion,
and the run ends naming the region.

---

## Removing it

```
hammunition uninstall osm-navit osm-regions country-boundaries
```

removes the converted maps, Navit's generated configuration, the region
files and the country-border file, and leaves Navit installed; `--dry-run` shows what it will remove
first. Your station config keeps its regions until you
change them; the download cache in `~/.cache/hammunition/artifacts/` is
yours to clear.

The QMapShack maps, routing database and elevation go the same way, and
leave QMapShack installed:

```
hammunition uninstall dem-qmapshack dem-copernicus osm-routino osm-garmin
```

Your QMapShack settings keep the directories the launcher added; QMapShack
lists nothing there once they are gone.

---

## What has not been measured yet

These are built, and are not claimed until they have run on the field
laptop and been recorded in `docs/reference/bench-verification-5430.md`:

- The whole install through Hammunition on real hardware. The conversion
  time and scratch figures above come from one region converted by hand;
  the map-size factor also rests on two US-state-sized regions converted on
  the field laptop on 2026-09-28.
- **Address search on maps built by the engine.** The index figures
  above comes from a build made by hand, in the spike that chose this fix,
  with the same steps the converter now runs (a Natural Earth border merged
  with `osmium merge`, then `maptool -U`); a map converted through
  `hammunition install` has not yet been searched on the field laptop.
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

For the QMapShack units (**D-061**), the converters and their sizes were
measured on one region on the development host. None of the following has
yet been run on a desktop; bench session 12 in
`docs/reference/bench-verification-5430.md` is that check:

- QMapShack reading the directories the launcher writes into its settings,
  in 1.17.1 (or 1.21.1 from backports).
- QMapShack listing the `hammunition` routing database.
- QMapShack drawing hillshade and slope from the elevation.
- A route on foot across the boundary between two regions.
- The GPS tether with a real receiver.
- The whole install on the field laptop, with its build times.

Offline reference (Kiwix, a local tile server) is the next piece of this
work and not in this profile.
