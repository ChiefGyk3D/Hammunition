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
and elevation with contour lines (**D-061**), and for US regions it lays the
official USGS topographic sheets over them (**D-068**). Once it is
installed, using it needs no network at all.

Daily use and EMCOMM are the same setup. The maps have to be on the disk
before anything goes wrong, so the way to be ready for the bad day is to use
it on ordinary days and refresh it as routine. The decision records behind
all of this are **D-057**, **D-061**, **D-068** for the official topo
sheets and, for repeaters, **D-064** in `docs/DECISIONS.md`; section 14
makes the same maps for the team's phones (**D-067**).

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
  your regions, about 39 MB each: tens to hundreds of them a region, so
  up to 17.5 GB for a US state (Alaska; see
  [Disk planning](#disk-planning));
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
starts it. The map and elevation directories go under `[Canvas]`, where
QMapShack reads them. An earlier launcher put them under `[General]`, where
QMapShack ignores them; run once, the launcher takes its own directories out
of `[General]` and says so. It also selects the routing database in the
Routing dock when nothing is selected there (see *Route on foot* below), and
says that too. If it says it cannot read your settings file, nothing was changed
and QMapShack was not started. Add the directories by hand in QMapShack's
setup, or move the file (`~/.config/QLandkarte/QMapShack.conf`) aside and
start it again. From the menu you will not see that message; see
[QMapShack does not start from the menu](#qmapshack-does-not-start-from-the-menu).

In QMapShack:

- **Maps.** Your regions' Garmin maps and the contour map (`contours.vrt`,
  listed as `contours`) are listed in the map dock. Activate a region's map, then the contour map
  over it. Close in, residential areas are drawn hatched: that is mkgmap's
  default style, not a fault (see [What QMapShack does not do
  (yet)](#what-qmapshack-does-not-do-yet)).
- **Terrain.** The elevation (`dem.vrt`) is listed in the DEM dock as `dem`; activate
  it and turn on hillshade or slope there.
- **Route on foot.** In the *Routing* dock choose *Routino (offline)*, the
  database `hammunition` in the *Database* list, and the profile `foot`.
  Place a start and an end on the map; the route follows trails. When
  Routino was run on one region for this work, walks of 10 to 17 km came
  back in 5 to 39 ms.

  If the *Database* list is blank, open it: `hammunition` is there, just
  not selected, and nothing routes until it is. QMapShack remembers which
  entry was selected when it last closed, and a QMapShack closed before
  the maps existed remembers "none". The launcher now selects the first
  database when none is, so this should only happen if you started
  `qmapshack` directly. Pick `hammunition` once and it stays picked.

  The folder button to the right of the *Database* list opens *Setup
  Routino database…*, where the directories QMapShack searches are listed;
  no menu item opens it. The launcher has already put ours there.

  The *Database* **dock**, the one that says *Needs setup…*, is something
  else: QMapShack's own store for your tracks, routes and waypoints. It has
  nothing to do with routing, and routing does not need it set up.
- **Tracks.** Record, load and edit GPX tracks and waypoints; any track
  shows an elevation profile from the elevation data.

On the field laptop, on 2026-09-29, the maps, the contour map and the
elevation were listed, and hillshade drew. A route on foot has not yet been
recorded; [What has not been measured yet](#what-has-not-been-measured-yet)
says what else has not.

Routino's foot profile does not read trail difficulty (`sac_scale`): an
alpine path counts the same as a pavement. Look at the contours and judge
the route yourself, or route the same walk with BRouter, below.

### Route with BRouter: trail difficulty and climbs

QMapShack has a second offline router, BRouter, and the `navigation`
profile installs it (**D-063**):

- **`brouter`**: BRouter 1.7.10 itself, from upstream's release zip checked
  against its published sha256, under `/usr/local/share/hammunition/brouter/`,
  with Java from your distribution;
- **`brouter-segments`**: BRouter's routing files, built on your machine
  from the same regions and the same elevation tiles as everything above,
  under `/usr/local/share/hammunition/data/brouter-segments/`;
- **`brouter-mapcreator-profiles`**: two small filter files BRouter's map
  builder needs, from BRouter's own source.

What it adds over Routino: its `hiking-mountain` profile reads how hard a
trail is (`sac_scale`), so a scramble is not treated as a footpath; every
profile weighs climbs from the elevation, so a bike route avoids a hill
Routino would ride straight over; and a route comes back with an elevation
profile and turn hints. It has 26 profiles: `trekking` and its variants,
`hiking-mountain`, `mtb`, `gravel`, `fastbike`, `safety`, `shortest`, three
car profiles, `moped` and a few more. Routino stays the default, and
neither searches for an address (section 10).

**Why the routing files are built here, and never downloaded.** BRouter's
own site, brouter.de, publishes ready-made routing files for the whole
world. They are rebuilt every week and published with no checksum of any
kind, so nothing can say a file is what its builder made, and Hammunition
never fetches them. BRouter's own map builder is inside the same checked
jar, so the install runs it over your regions instead, with the terrain
tiles folded in as elevation. For Delaware, a public example, that was
3.3 MB of routing files from a 22.1 MB download; brouter.de's file for the
same area is 115 MB, because it covers a whole 5-by-5-degree square.

The build runs as you, never as root, in
`~/.cache/hammunition/build/brouter-segments/`, like the Routino database:
the regions are merged into one input when there are two or more, the
elevation is built one 5-degree square at a time, then BRouter's map
builder runs its three steps. It is one set for all your regions, so a
route may cross from one region into the next, and a region that fails
fails the set; the set you already had is kept (unless a failing disk
stops the new set halfway into place, when the set is removed rather than
left mixed, and the next run rebuilds it). It is rebuilt when a
region, a snapshot, the elevation tiles or BRouter itself changes. Each
Java step may use up to 4 GB of memory; the elevation step took 1.33 GB
for Delaware's square. A region with no elevation tile is routed flat.

Using it in QMapShack:

1. Start QMapShack from the `qmapshack-offline` launcher. When BRouter and
   its routing files are installed, the launcher points QMapShack's local
   BRouter at them, on 127.0.0.1 only, and says so. If you had already set
   up a BRouter of your own in QMapShack, it leaves yours alone and says
   that instead.
2. In the *Routing* dock, choose *BRouter* in the router list (QMapShack
   1.17.1 labels it *BRouter (online)*; the launcher has set it to run
   locally) and a profile such as `hiking-mountain` or `trekking`.
3. Place a start and an end. QMapShack starts BRouter in the background the
   first time, which takes a few seconds, and stops it when QMapShack
   closes. Nothing runs while you are not routing with it.

Do not use QMapShack's own *BRouter setup* wizard for this: it downloads
BRouter and its routing files from brouter.de.

BRouter is meant to listen on 127.0.0.1 only: the launcher sets that host
and turns on QMapShack's "bind to hostname only", because without it
BRouter accepts connections from the whole network. QMapShack passes the
host to BRouter only when it has read BRouter's version, which it does by
running the jar and waiting up to 3 seconds; if that times out (a slow
start on a busy machine), QMapShack can start BRouter without the host, on
every interface. To check while a route is being calculated:

```
ss -ltnp | grep 17777
```

`127.0.0.1:17777` (or `[::ffff:127.0.0.1]:17777`) is loopback only;
`*:17777` or `0.0.0.0:17777` is not, and then close QMapShack, reopen it and
choose BRouter again. The development host started the jar and printed its
version in 0.09 s, so this is not expected; it has not been seen on the
field laptop either way.

A route drawn by QMapShack through this BRouter has not been measured yet;
see [What has not been measured yet](#what-has-not-been-measured-yet).

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

QMapShack does not talk to gpsd. Its Realtime source *GPS TCP/IP* reads NMEA, the sentence
format GPS receivers speak, from a network port. The tether makes that NMEA
from gpsd's position and serves it on this machine only. Run the *GPS
position for QMapShack* launcher, or in a terminal:

```
hammunition maps gps-tether
```

It prints what to enter:

```
Serving gpsd's position as NMEA on 127.0.0.1 port 10110, to this machine only.
In QMapShack: Realtime, Add source, GPS TCP/IP; host 127.0.0.1, port 10110.
The offline browser map (`hammunition reference serve`) reads it from http://127.0.0.1:10111/position.
Reading gpsd at 127.0.0.1 port 2947. Any number of NMEA programs may connect at once.
Options: --gpsd HOST[:PORT] for a gpsd on another machine, --port N if 10110 is taken, --position-port N for the map's.
Ctrl-C stops it. Navit reads gpsd directly and needs none of this.
```

The same tether also feeds the browser map (section 16) on 127.0.0.1
port 10111.

In QMapShack open the *Realtime* dock, right-click its list, *Add source*, choose *GPS TCP/IP* (measured on 1.17.1: that is the label, not "GPS Tether"), and enter host `127.0.0.1`
and port `10110`.

Once set up, QMapShack connects again by itself whenever a tether is
running: start the tether after QMapShack and the position appears without
touching QMapShack. Any number of programs can connect at once, and each
gets every sentence, so a test from a terminal (`nc 127.0.0.1 10110`) works
while QMapShack is open.

How it works, so you know what you are running:

- It asks gpsd for its position the way `xgps` and Navit do, as JSON, and
  writes two NMEA sentences for every position with a fix: `$GPRMC` (time,
  position, speed, heading) and `$GPGGA` (position, fix quality, satellites,
  altitude). A value gpsd did not give is left empty, never made up; the
  one exception is the time, which falls back to this machine's clock (in
  UTC) if gpsd sent none. With
  no fix, it sends nothing.
- It listens on 127.0.0.1, port 10110 (or the port `--port` names), and
  nowhere else: nothing else on the network can connect to it. Any number
  of programs on this machine can, and each gets every sentence. It keeps
  one connection to gpsd open while any of them is connected, and closes it
  when the last one goes. A program that stops reading is disconnected on
  its own, and the others carry on.
- It runs while that terminal stays open. Ctrl-C stops it. Nothing is
  installed as a service, and it does not run as root.
- The terminal shows a line when a program connects or goes, with how many
  are connected. If gpsd has sent no position with a fix within 10 seconds,
  it says that too.

If it says gpsd has sent no position with a fix, the tether has nothing to
pass on. Check with `xgps`, and see ["Where am I?"](#6-where-am-i). If it
says it cannot listen on port 10110, another tether is already running;
stop that one first, or use another port (section 12). If it says it cannot reach gpsd, gpsd is not running:
`systemctl status gpsd` says why. If gpsd is running and `xgps` shows no
position either, restarting it can help:
`sudo systemctl restart gpsd.socket gpsd`. On the field laptop gpsd once
stopped reporting altogether, and after that restart it gave a 3D fix
within a second.

The first version of the tether passed on gpsd's raw NMEA through `socat`.
On the field laptop it sent nothing, at a time when gpsd itself was
reporting no position at all, so why is not known. This version needs
neither program and says plainly when gpsd has no fix. If you installed the
first version,
`socat` is no longer part of this profile; it is kept in the catalog as
retired, so `hammunition uninstall socat` still removes it. Do that only
if nothing else of yours uses it.

---

## 12. Other setups

Section 11 assumes a GPS receiver plugged into the laptop that runs
QMapShack. Yours may not be. The tether takes two options for that, and
the rest is gpsd's own setup. Every command below runs as you, not root,
unless it starts with `sudo`.

```
hammunition maps gps-tether --gpsd HOST[:PORT] --port N
```

- `--gpsd HOST[:PORT]` is the gpsd to read: a host name or an address,
  port 2947 if you leave it out. An IPv6 address goes in brackets:
  `--gpsd [2001:db8::7]:2947`.
- `--port N` is the port to serve on, 1024 to 65535, if 10110 is taken.
  Below 1024 is refused, because only root can use those ports and the
  tether never runs as root.

Neither option changes where the tether listens: 127.0.0.1 only, always.
Anyone who could connect to it would get your position without a
password, so there is no option to open it to the network. To use it
from another machine, see *A second machine* below.

### gpsd on another machine: a Pi, a shack computer

The receiver is on a Raspberry Pi on the mast, or on the shack computer,
and gpsd runs there. The simplest route, which changes nothing on that
machine, is an SSH tunnel to its gpsd. In one terminal:

```
ssh -N -L 12947:127.0.0.1:2947 pi@shack-pi
```

and in another:

```
hammunition maps gps-tether --gpsd 127.0.0.1:12947
```

The tunnel uses local port 12947, not 2947, because this laptop's own
gpsd may already hold 2947. The position crosses the network encrypted,
and the Pi's gpsd keeps listening only to itself.

The other route is to make gpsd on that machine listen on the network,
then point the tether straight at it:

```
hammunition maps gps-tether --gpsd shack-pi
```

gpsd listens only on its own loopback unless told otherwise. On Debian
and Parrot it is started by `gpsd.socket`, and that unit file's own
comment says how: start gpsd with `-G` and add `ListenStream=[::]:2947`
and `ListenStream=0.0.0.0:2947` (measured: the comment is in
`/lib/systemd/system/gpsd.socket` from gpsd 3.25 on Parrot 7). Put the
lines in an override with `sudo systemctl edit gpsd.socket` rather than
editing the file, which an upgrade replaces, and add `-G` to
`GPSD_OPTIONS` in that machine's `/etc/default/gpsd`. This has not been run
here. Anyone on that network can then read your position from gpsd; do it
only on a network you trust, and prefer the tunnel.

If the tether says it cannot reach gpsd, check from the laptop with
`xgps shack-pi:2947` (or `xgps 127.0.0.1:12947` through the tunnel). If
`xgps` cannot reach it either, the problem is gpsd or the network, not the
tether.

### A phone as the GPS source

A phone has a good receiver. Apps that share it over the network come in
two kinds, and the tether reads only one of them directly. **None has been
tested here**: what follows is what each kind of app should need, not
something measured.

- **An app that speaks gpsd's own protocol on a port.** The tether reads
  it like any gpsd: `hammunition maps gps-tether --gpsd PHONE:PORT`. It
  needs the app to answer `?WATCH` with gpsd's `TPV` reports, which is
  what "gpsd protocol" means; an app that only says "gpsd compatible" may
  mean something else.
- **An app that serves NMEA over TCP.** The tether does not read NMEA. Give
  it to this laptop's gpsd, and the tether reads that as usual:

  ```
  sudo gpsdctl add tcp://PHONE:PORT
  hammunition maps gps-tether
  ```

  To keep it across reboots, put it in `/etc/default/gpsd` instead:
  `DEVICES="tcp://PHONE:PORT"`, then `sudo systemctl restart gpsd`.
  gpsd's manual page names `tcp://` and `udp://` sources; an app that sends
  NMEA to the laptop over UDP is `udp://0.0.0.0:PORT`. QMapShack can also
  read such an app directly, with the phone's address and port in its GPS
  Tether dialog and no tether at all.

The phone and the laptop must be on the same network, which for a field
setup usually means the phone's hotspot. Whether the phone keeps sending
with its screen off depends on the app and the phone's battery settings.

### A Bluetooth or USB serial NMEA receiver

A receiver that is not USB-native (a Bluetooth puck, or a module on a
USB-serial cable) is still one gpsd can read. gpsd must be told the port,
because only a few receivers are recognised by themselves.

For a Bluetooth receiver, pair it, then bind it to a serial port; `rfcomm`
comes with bluez on Parrot, and the address is your receiver's:

```
sudo rfcomm bind 0 00:11:22:33:44:55
sudo gpsdctl add /dev/rfcomm0
```

For a USB serial receiver, use its stable name under `/dev/serial/by-id/`
rather than `/dev/ttyUSB0`, which can change when something else is
plugged in:

```
ls /dev/serial/by-id/
sudo gpsdctl add /dev/serial/by-id/usb-...-port0
```

`gpsdctl add` hands the port to the gpsd that is already running, and
lasts until gpsd restarts. To make it permanent, name the port in
`/etc/default/gpsd`, one line:

```
DEVICES="/dev/serial/by-id/usb-...-port0"
```

then `sudo systemctl restart gpsd`. `gpsd -n /dev/ttyUSB0` in a terminal
also works for a quick test, but only with the system's gpsd stopped
first (`sudo systemctl stop gpsd.socket gpsd`), because both want port
2947. In every case the tether needs nothing new: `hammunition maps
gps-tether`.

### A rig with built-in GPS

Some radios have a GPS receiver and send its NMEA out of a serial or USB
port: the same port rig control uses, or a second one. Which radios do,
and on which port, is in the radio's manual; none has been tested here.
Give that port to gpsd exactly as for a serial receiver above.

**A serial port has one owner.** If the radio sends GPS on the same port
rig control uses (Hamlib's `rigctld`, flrig, WSJT-X's CAT), gpsd and rig
control cannot both have it. gpsd reads from the port and sends probes
down it while it identifies the device, and rig control on the same port
then sees garbage or nothing. Pick one of these:

- **The radio has a second port** (many USB-connected radios present two
  serial ports, one for CAT and one for data or GPS). Give gpsd the GPS
  one and rig control the other. `ls -l /dev/serial/by-id/` shows both;
  the names usually end `-if00` and `-if02` or similar.
- **The radio sends GPS on a separate jack** (a data or accessory
  connector). Use a second cable for it.
- **One port does both.** Choose: rig control, and a separate USB GPS
  receiver for position (the cheapest fix); or GPS, and no CAT while you
  navigate.

gpsd does not grab a rig's port on its own on Parrot: its udev rules
(`/usr/lib/udev/rules.d/60-gpsd.rules`, gpsd 3.25) leave the common
USB-serial bridge chips commented out, among them `10c4:ea60`, `0403:6001`
and `067b:2303`, because those chips are in rig cables as often as GPS
receivers (measured on the development host, 2026-09-29). A port is
gpsd's only when you name it.

### Another port

If 10110 is taken (another tether, or another program that serves NMEA
there):

```
hammunition maps gps-tether --port 10111
```

and enter port 10111 in QMapShack's GPS Tether dialog. The terminal
prints the port to enter.

### Two NMEA programs at once

Start the tether once, and point every program at it: QMapShack, a second
QMapShack window, a logger, an APRS client that reads NMEA over TCP. Each
gets every sentence. The terminal counts them as they come and go, for
example `A client connected; 2 connected`. A program that stops reading
(one frozen, or paused in a debugger) is disconnected once 64 KiB is
waiting for it, and the others are not held up.

### A second machine: `ssh -L`

To use the laptop's position on another computer, tunnel to the tether
from that computer:

```
ssh -N -L 10110:127.0.0.1:10110 you@laptop
```

and point the program there at `127.0.0.1` port 10110, as if the
receiver were local. Use another local port on the left (`-L
10111:127.0.0.1:10110`) if that machine has its own 10110 in use. This is
the only supported way: the tether never listens beyond loopback, because
anyone who could connect would get your position without a password, and
SSH gives the second machine an encrypted, authenticated path instead.

### A parked receiver

A receiver parked with `hammunition hardware park` (**D-056**) is gone
from gpsd: gpsd sees it unplugged. A tether left running stays up, keeps
its programs connected, and sends nothing; if nothing has come since it
connected to gpsd, it says gpsd has sent no position with a fix. Wake the
receiver with `hammunition hardware wake gps-receiver`. On the field
laptop gpsd took the device back within a second of a wake, and a 3D fix
was back within 74 s (`docs/hardware/gps-receiver-class.md`). Whether a
running tether then carries on by itself, without being restarted, has
not been measured; restart it if nothing comes once `xgps` shows a fix.

Parking is per machine. Parking this laptop's receiver does nothing to a
gpsd on a Pi or a phone you read with `--gpsd`, and parking the Pi's
receiver is done on the Pi.

### Navit and xgps need none of this

Navit and `xgps` read gpsd themselves. Both reach a gpsd on another
machine without the tether: `xgps shack-pi:2947`, or through the tunnel,
`xgps 127.0.0.1:12947`. Navit reads this machine's gpsd by default,
through the `source="gpsd://..."` of the vehicle in its own `navit.xml`;
another machine's gpsd is a different host there, which has not been
tried here. The tether is for QMapShack and other programs that want NMEA.

### Check the feed from a terminal

With the tether running:

```
nc 127.0.0.1 10110
```

prints the sentences as they arrive, two per position (`$GPRMC` and
`$GPGGA`), while QMapShack stays connected. Nothing printed means gpsd has
no fix; the tether's terminal says so after 10 seconds. The lines carry
your position, so do not paste them anywhere public. Ctrl-C stops `nc`,
not the tether.

### What is measured, and what is not

Measured on 2026-09-29, on the development host against its own gpsd with
a receiver streaming fixes: the tether on a spare port read gpsd through
`--gpsd`, both as `127.0.0.1` and as `[::1]:2947`, and served two raw
clients at once. In one run both received the same 32 sentences, byte
for byte and in the same order, every checksum valid; when one left, the
other kept receiving; Ctrl-C ended it with exit 0. The tests
(`tests/test_gps_tether.py`, `tests/test_maps_tools.py`) cover both
options and their refusals, the whole command against a fake gpsd reached
through `--gpsd`, an IPv6 gpsd, two clients receiving identical bytes,
one leaving while the other keeps its gpsd watch, a stalled client
dropped while the other keeps receiving, and stopping with every socket
closed. Also measured: the commented-out bridge chips in gpsd's udev
rules, and the comment in `gpsd.socket`, both read from gpsd 3.25 on
Parrot 7.

Not measured here: a gpsd on another machine over a real network, with
or without an SSH tunnel; any phone app; a Bluetooth receiver; a rig's
built-in GPS; `gpsdctl add` and `tcp://` or `udp://` sources; `-G` and a
`gpsd.socket` override; a program reached over `ssh -L`; and whether a
running tether picks the position back up after a wake. The commands for
those come from each program's own documentation and are what should
work, not what has been seen to.

---

## 13. Repeaters on the map

Your own repeater list, converted on this machine into a layer QMapShack and
Navit both show (**D-064**). Hammunition fetches nothing from RepeaterBook
and ships no repeater data: you export it with your own account, and the
conversion happens here, offline. Five more sources each make a layer of
their own beside it (**D-074**): Open Repeater's open list, the repeaters
tagged in your OpenStreetMap regions, the UK's ETCC list, Brandmeister's
DMR repeaters, and the repeater objects your own station heard on APRS.
Every layer says where it came from, its date and its licence in its name
and description, so a wrong entry can be traced and a source dropped.

### Get an export

- **RepeaterBook, as GPX (the one to use).** Logged in on repeaterbook.com,
  run a search (by location, proximity, keyword and so on), then choose
  *Export → GPX*. RepeaterBook does not export multi-county or multi-state
  searches as GPX; run one search per area and import the files together.
- **RepeaterBook, as CSV.** Only when its header has `Lat` and `Long`
  columns. One without them is refused: there is nothing to place.
- **Your own list.** A CSV with exactly this header, positions in decimal
  degrees:

  ```
  callsign,output_mhz,offset_mhz,tone,mode,lat,lon,name,notes
  N0CALL,146.940,-0.600,100.0,FM,39.8017,-89.6436,Springfield,club machine
  ```

- **hearham.com's open list**, fetched for you on request; see below.

CHIRP files do not work, and are refused by name: a CHIRP CSV or `.img`
holds channels, not places. CHIRP's own RepeaterBook query drops the
coordinates and keeps only "near <city>" (measured), and a position guessed
from a town name would be an invented one. KML is not read yet; export GPX
from the same search.

### Convert it

```
hammunition maps repeaters import ~/Downloads/repeaters.gpx
```

Several files at once are merged into one layer; the same repeater in two
exports becomes one, and the same callsign and frequency on two different
hills stays two. It prints RepeaterBook's attribution and terms first, then
what it read, skipped and merged, and the files it wrote. The layer's name
carries the export's date, taken from the file; give it yourself with
`--exported 2026-09-01` if the file has been copied since.

The files are yours, in `~/.local/share/hammunition/overlays/repeaters/`,
readable only by you. RepeaterBook's export terms are personal,
non-commercial use, and the data may not be redistributed in any form, so
keep the files to your own machines. Positions are approximate: a map
overlay to find a machine to talk through, not directions to a repeater
site.

A new import replaces this layer and leaves the other sources' layers as
they are. To refresh it, export again and import again.

### See it

- **QMapShack.** The layer is a POI collection: open the *POI Collections*
  dock and tick *Amateur radio repeaters*. The import added its directory to
  QMapShack's settings; if QMapShack was open during the import, close it
  and start it from `qmapshack-offline`, which adds the directory back. The
  GPX is there too, for *File → Load* or to copy to a phone or a Garmin
  unit.
- **Navit.** Start `navit-offline`. Repeaters draw as towers labelled with
  callsign and frequency, and list under *POIs → Other* with their
  distance. They are **not** in Navit's address search: the file format
  Navit reads them from has no search. The launcher now runs
  `hammunition maps navit`; a launcher from an earlier install is updated
  by `hammunition menus apply`.

### hearham.com's open list

```
hammunition maps repeaters fetch-hearham
```

fetches the whole world's list from hearham.com (about 9.5 MB) when you run
it, and at no other time, and converts it the same way. hearham publishes no
checksum and no dated copy, so Hammunition records the digest of what
arrived and names the layer *unverified*. hearham states no licence for its
data, and says it should not be relied upon "for medical emergencies, or any
other life-and-death operations". To combine it with your RepeaterBook
export, save hearham's JSON yourself and give both files to one
`maps repeaters import`.

### More sources, one layer each

What was measured on 2026-10-01 is blunt: open bulk repeater data for the
US barely exists. Across Delaware, Vermont and the Shenandoah valley these
sources together added about one repeater to hearham's list. They earn
their place elsewhere: outside the US, in the UK, on DMR, and in what your
own radio hears.

**Open Repeater (CC0).** The only bulk directory found under an open
licence. Its rows today are in Sweden, Malaysia and India, with one in
Canada.

```
hammunition install open-repeater
hammunition maps repeaters import --from-open-repeater
```

The first installs Open Repeater's whole list (about 241 kB), checked
against the digest the catalog pinned; a LAN mirror (`docs/guides/lan-mirror.md`)
can serve it. The second makes the layer *Repeaters (Open Repeater
YYYY-MM-DD, CC0)*, dated by the newest entry's verification. A copy you
downloaded yourself works too: `--from-open-repeater ~/Downloads/file.json`.
Open Repeater's download address carries no date, so the catalog's pin goes
stale whenever the site changes; the install then refuses the file by its
digest until the pin is regenerated (the weekly check says when).

**Australia: the regulator's register (ACMA).** The Australian
Communications and Media Authority publishes its whole Register of
Radiocommunications Licences as one file, rebuilt every day, under a
licence that allows a derived map layer with attribution. On 2026-10-01 it
held 1,784 amateur repeater transmitters with a site position.

```
hammunition station set --map-regions australia-oceania/australia/tasmania
hammunition install osm-regions
hammunition install acma-register
hammunition maps repeaters import --from-acma
```

`install acma-register` downloads the whole register, about 67.5 MB, and
**the plan says it is unverified**: the ACMA publishes no checksum (the
`ETag` its server sends is a storage version stamp, not a digest of the
file) and the file changes every day, so Hammunition cannot pin it. What is
checked is that the zip is whole (every member's CRC-32) and holds the
tables the import reads. That catches a damaged download, not a
deliberately altered one; for that reason the unit is in no profile and is
installed only when you name it. A LAN mirror can serve it, checked the
same way.

The import keeps the transmitters on granted *Amateur Repeater* licences
whose site lies inside the bounding box of a map region you have installed,
so install an Australian region first (the four lines above use Tasmania).
Outside Australia, or with no Australian region, it says the layer would be
empty and writes nothing. The layer is *Repeaters (ACMA, YYYY-MM-DD)*, dated
by the register itself, and every file carries the attribution the licence
requires: "Based on Australian Communications and Media Authority
information". Each repeater shows its output, the input paired from the
same licence's receiver, the emission in plain words with its designator
(`FM (16K0F3E)`), the site's name and how precisely the ACMA records it, and
the licence number. The register has no CTCSS tones. A bounding box is a
rectangle, so a region's box can take in sites just over a state border.

The installed file is the whole register, including licensees' names and
addresses. The import never opens that table and the layer carries none of
it; the licence forbids passing on a private person's details, so keep the
installed file to yourself. A copy you downloaded works the same:
`--from-acma ~/Downloads/spectra_rrl.zip`. Reading it takes about
20 seconds.

**Your OpenStreetMap regions.** No download at all: the repeaters tagged in
the region extracts you already installed for the maps.

```
hammunition maps repeaters import --from-osm
```

It needs `osmium` (the `osmium-tool` package, which `osm-navit` brings).
Mappers have tagged under a thousand repeaters worldwide, few in the US, so
expect a short list or none; the layer is *Repeaters (OpenStreetMap, ODbL,
YYYY-MM-DD)*, dated by your oldest extract. Mappers write the frequency in
several ways (`146.685`, `146685`, `145350000` and, for 146.61 MHz,
`1466100000` were all found); the import tries each unit and takes the one
that lands in a repeater band. The data is under the ODbL: if you share
the layer, its share-alike terms apply to it.

**The UK's ETCC list (RSGB).**

```
hammunition maps repeaters fetch-etcc
```

fetches ukrepeater.net's whole list (about 62 kB) when you run it. It
states no licence, so the layer is marked *unverified* with the digest of
what arrived. Its positions are Maidenhead locators, and a four-character
locator puts a repeater at the centre of its square, which can be tens of
kilometres from the hill it is on: each repeater's description says which
locator it came from.

**Brandmeister's DMR repeaters.**

```
hammunition maps repeaters fetch-brandmeister
```

fetches Brandmeister's device list (about 9.5 MB). **Most of that list is
hotspots: somebody's house.** Only repeaters are kept, a 6-digit id whose
transmit and receive frequencies differ; every hotspot is dropped before
anything is written, and only how many is printed. No terms are published,
so this layer is *unverified* too. hearham already carries most of
Brandmeister's repeaters; this mainly adds colour codes.

**What your station heard.** Direwolf decodes the APRS repeater objects
local digipeaters send (one or two per area, the machines a traveller is
pointed to). Start Direwolf with `-l ~/direwolf-logs` (or `-L file`) to keep
its log, then:

```
hammunition maps repeaters import --from-direwolf-log ~/direwolf-logs/*.log
```

makes *Repeaters heard off the air (APRS objects, YYYY-MM-DD)*, dated by
the last hearing. Nothing is fetched and no login is used. Direwolf's log
does not say whether an object was withdrawn, so one that was is still
shown. This layer stays apart from the directories: it is evidence of what
you heard, not a listing.

### All sources in one file

With two directory layers or more, every import, fetch and remove rebuilds
`repeaters-all.gpx` in the same folder: each repeater once, for a phone or
QMapShack's *File → Load*. Two entries from different sources are the same
repeater when their output frequency matches and they are within about
2 km, or carry the same callsign within about 25 km. Where they disagree,
the better source wins: your own export or list, then the regulator (the
ACMA), the ETCC, Open Repeater, hearham, Brandmeister, OpenStreetMap; a
detail the winner lacks
(an offset, a tone) is filled from the next. Each entry says every source
that listed it, and the import prints how many were joined. The APRS layer
is never in it. QMapShack and Navit show every layer anyway, so in them the
same repeater can appear once per source.

### Remove it

```
hammunition maps repeaters remove
hammunition maps repeaters remove --layer osm
```

The first deletes every layer and the all-sources file and takes the
directory out of QMapShack's settings; Navit goes back to the generated
configuration at its next start. The second deletes one layer
(`export`, `acma`, `open-repeater`, `osm`, `etcc`, `brandmeister` or
`aprs-heard`)
and rebuilds the rest.

### Not carried

- Anything fetched from RepeaterBook. Its API needs approval, and its
  data-use terms forbid bulk extraction and offline bundling without written
  permission. The ARRL's directory is RepeaterBook's data under the same
  terms.
- Xastir, whose point layers live in a root-owned map directory, and YAAC,
  whose importer makes APRS objects it can transmit (a D-021 matter, not a
  map).
- The FCC's licence database: US repeaters are not licensed individually,
  and its records carry a mailing address, not a site.
- RadioReference (private viewing only without a licence), RFinder (a paid
  app with no bulk data), RadioID (its terms exclude mapping, and its list
  has no positions), the WIA's CSV (all rights reserved, no positions),
  repeatermap.de (a token on request only), and the D-STAR, YSF and NXDN
  lists (personal-use pages, or internet reflectors without positions).
- An APRS-IS capture, and the US coordinators' and Brandmeister's lists
  under an explicit licence: those wait on the maintainer's decision
  (D-074).

---

## 14. Maps for your phone

The laptop can make the team's phone maps from the same regions, so every
phone navigates on the same verified data with the phone network down
(**D-067**). Two units build them, one file per region each:

| Unit | File | What a phone app does with it |
|---|---|---|
| `mapsforge-map` | `<region>.map`, a Mapsforge vector map | draws it offline, with the app's own style |
| `mapsforge-poi` | `<region>.poi`, a Mapsforge points-of-interest file | searches it for places by name or kind |
| `osm-garmin` (section 9) | `<region>.img`, the Garmin map | a Garmin handheld reads it from its card; so does OruxMaps |

They are their own profile, `phone-maps`, not part of `navigation`: every
unit in a profile is built for every region, and a map for phones takes
time. On Delaware (a 22 MB download) the map took 3 minutes 38 seconds and
about 1 GB of memory, and the POI file 23 seconds; at that rate a region
sixty times the size would take hours. Install it when you have phones to fill:

```
hammunition install phone-maps --dry-run
hammunition install phone-maps
```

The plan says, for each region, what it builds and what it costs, with every
figure marked "measured on one region". It also fetches one file that no
archive packages: Mapsforge's POI writer, 18.8 MB from Maven Central,
checked against a sha256 Hammunition measured. The plan says so, and says
that the signature Central publishes beside it is recorded and not checked.
Everything else comes from your distribution: `osmosis`,
`libmapsforge-java` and a Java runtime.

### Put the files in one folder

```
hammunition maps phone
```

copies every phone file installed into `~/.local/share/hammunition/phone/`,
with a `SHA256SUMS` beside them, and prints how to carry them to a phone. It
copies nothing that is already current, removes a file it put there whose
region you dropped, and touches nothing else in the folder. **It sends nothing
anywhere**: the ways across are commands for you.

### Get them onto the phones

Install a map app that reads Mapsforge files on each phone **while it still
has internet**. By their own documentation, Cruiser, Locus Map, OruxMaps and
c:geo read Mapsforge maps and POI files. None of them has been tried with
these files yet.

**The laptop's hotspot and a browser.** Nothing to install, and every phone
at once:

```
nmcli device wifi hotspot ssid hammunition-maps password 'choose-8-or-more'
ip -4 addr show
python3 -m http.server 8000 --bind 127.0.0.1 --directory ~/.local/share/hammunition/phone
```

Open `http://127.0.0.1:8000/` on the laptop to check the list, stop it with
Ctrl-C, then serve it on the hotspot's own address, which `ip -4 addr show`
lists on the Wi-Fi interface (NetworkManager uses 10.42.0.1 unless told
otherwise):

```
python3 -m http.server 8000 --bind 10.42.0.1 --directory ~/.local/share/hammunition/phone
```

Join each phone to the hotspot and open `http://10.42.0.1:8000/` in its
browser. The files are expected to land in Downloads for the app to open
from there; that has not been tried on a phone yet.
**Always give `--bind`.** Without it, `http.server` answers on every network
the laptop is on, a hotel's or an office's included; bound to the hotspot's
address, only the phones on the hotspot can reach it. It is plain HTTP on a
local link, which is why `SHA256SUMS` is in the list too, for anyone who can
check a hash on the phone.

**A USB cable.** On KDE Plasma, plug the phone in, choose "File transfer" on
the phone, and Dolphin shows it; copy the files into its Download folder.
Plasma's `kio-extras` does this and is already installed. On another
desktop, `gvfs-backends`, `jmtpfs` or `mtp-tools` does the same. One phone at
a time.

**`adb`, if you already use it.** `sudo apt install adb` also installs
`android-udev-rules`, which adds udev rules to the machine. The phone needs
Developer options with USB debugging turned on, which most people's phones
do not have; turn it off again afterwards.

```
adb push ~/.local/share/hammunition/phone /sdcard/Download/
```

**KDE Connect, if the phones already have it.** `sudo apt install
kdeconnect`; each phone needs the KDE Connect app, installed while it had
internet, and pairing. It works over the laptop's hotspot.

### Formats not made here, and why

- **OsmAnd's `.obf`** would be the best single file (map, routing, address
  search and POI in one), and the laptop can make it offline, but the only
  generator is a nightly build replaced every day with no checksum,
  signature or version. Nothing can be checked, so it is not carried. The
  route is building OsmAnd's tools from a fixed source commit.
- **Organic Maps and CoMaps `.mwm`** must be made by a generator from the
  same release as the app, and a region on the coast needs the whole
  planet's coastline. The route is the publishers' own `.mwm` files, checked
  by the hashes they publish; that is separate work.
- **PocketMaps** needs a routing engine from 2019, and the app has had no
  change since October 2024.
- **Transportr** asks online services for every journey and keeps nothing on
  the phone; there is nothing to make for it.

### What has not been tried

No file made here has been opened on a phone, in any app. The converters
have not yet run through Hammunition on the field laptop; their figures come
from one region converted by hand. The bench owes both, and the hotspot's
address on the field laptop. Until then, check each new phone app with one
small region first.

---

## 15. Official topo: US Topo, FSTopo and 3DEP

For a region in the United States, the `navigation` profile also installs
the **USGS US Topo** map sheets its outline touches (`usgs-ustopo`) and
makes them one QMapShack map (`ustopo-qmapshack`). A US Topo sheet is the
printed 7.5-minute topographic map, public domain: trails by the name on the
signpost (the Park Service's and the Forest Service's own names),
campgrounds, visitor centres, shelters, roads, water, woodland and 40 ft
contours, drawn by USGS. OpenStreetMap already has nearly every trail's
line; the sheet adds the official names and the look search teams and
rangers hand out on paper.

Nothing is set for it beyond your map regions. The plan's *US Topo* part,
under Terrain, lists each region's sheet count and size, every sheet to be
downloaded with how it is checked, and what is built:

```
hammunition install navigation --dry-run
```

**How much.** A sheet is about 8 MB (2 to 20 MB). Measured from USGS's
index on 2026-09-29: Delaware's 38 sheets are about 220 MB, Vermont's 194
about 1.6 GB, Virginia's 729 about 6 GB. A region's outline touches the
sheets just across its borders too, so expect a little more than the
state's own. Each sheet is kept twice once built (the download, and the
copy made for QMapShack), so allow about twice those figures.

**Outside the United States** a region gets no sheets. The plan says
`note: no US Topo quad covers <region>` and everything else installs.
OpenStreetMap stays the trail map there. (The UK's Ordnance Survey
publishes a checksum for each of its open files, the pattern a future UK
source would follow; nothing outside the US is carried yet.)

**How each sheet is checked.** Hammunition carries an index of every
current sheet, `catalog/data/ustopo-quads.txt`, built from USGS's own list
and its storage bucket, with each sheet's size and the checksum the bucket
keeps for it (its ETag). Before the download the bucket is asked again, and
must still report the same; the download must then reproduce it. The plan
says **"MD5 from the publisher's object metadata; not pinned by
Hammunition"** for every sheet: see [What the verification wording
means](#what-the-verification-wording-means).

**In QMapShack.** `qmapshack-offline` adds
`/usr/local/share/hammunition/data/ustopo-qmapshack` to QMapShack's map
directories. In the *Maps* dock, `ustopo` is one map covering every sheet;
tick it to show it, and drag it above or below the Garmin maps. Each sheet
was reprojected and cropped to its own quadrangle when it was built, so the
white margin and legend around a printed sheet are gone and neighbouring
sheets are meant to meet edge to edge (the crop was measured on one sheet;
the seam between two has not been looked at). The legend is not in the map: USGS's own
[US Topo symbol sheet](https://www.usgs.gov/programs/national-geospatial-program/us-topo-maps-america)
explains the symbols.

**Not measured yet: QMapShack drawing it.** In the one run so far,
QMapShack opened the map file and listed it, and the map area stayed blank,
for a reason not yet found. It has not been run on the field laptop. If it
stays blank for you, see
[US Topo is listed but draws nothing](#us-topo-is-listed-but-draws-nothing).

**Newer editions.** USGS revises a sheet every few years. When the carried
index lists a newer edition than the one installed, `hammunition update`
counts it (never naming the sheet), and
`hammunition install usgs-ustopo ustopo-qmapshack` fetches the new edition,
removes the old one once the new one is installed (if it does not arrive,
the old one stays, in the map too) and rebuilds the map. A sheet USGS adds
where it had none is picked up only when a region is added or changed,
since a region's sheets are remembered after its first install.

**Not carried, and why:**

- **Park Service, Forest Service and state trail lines as a second layer.**
  OpenStreetMap already has 97.5 % of Shenandoah National Park's official
  trail mileage within 25 m, and 96 % of a sample of the George Washington
  and Jefferson National Forest's. A second layer draws every trail twice,
  and the US Topo sheet already shows the official names.
- **1 m lidar elevation**: one Shenandoah project alone is 26.9 GB.
- **The PDF editions (GeoPDF)**: six times the size, and they would have
  to be turned into images anyway.
- **Historical topographic maps**: of historical interest; Vermont alone is
  9.4 GB.
- **Park PDF trail maps**: not georeferenced, so a program cannot place them.
- **BLM and Fish and Wildlife Service layers**: only answerable as online
  queries, with no fixed file to check.
- **Protected-area boundaries (PAD-US)**: later, if at all; its publisher
  gives no checksum.
- **Park points of interest and boundaries as GPX**: a later piece, once
  there is a checksum to check them by.

### Forest Service FSTopo sheets: trail numbers

The Forest Service's own 7.5-minute sheets, **FSTopo** (`usfs-fstopo`),
carry Forest Service trails by their **trail numbers**, forest roads by
number, 40 ft contours and the forest's boundaries, as the ranger district
prints them. Public domain. **They are not part of the `navigation`
profile**, because the Forest Service publishes no checksum for them (see
below); you install them by name, after reading the plan:

```
hammunition install usfs-fstopo ustopo-qmapshack --dry-run
hammunition install usfs-fstopo ustopo-qmapshack
```

Nothing is set for it beyond your map regions; a region with no National
Forest land (Delaware, for one) gets `note: no FSTopo quad covers <region>`
and nothing else happens. The plan's *FSTopo* part lists each region's sheet
count and download size before anything downloads.

**How much.** About 21 MB a sheet (one George Washington National Forest
sheet, measured), and about 1.2 times that again once converted for
QMapShack. The Forest Service's index lists 87 sheets primarily in Vermont
and 247 in Virginia; about 142 touch the George Washington and Jefferson
National Forest, roughly 3 GB.

**How each sheet is checked: usually, it is not.** The Forest Service
publishes no checksum for its sheets. Hammunition carries a pin, a sha256
the maintainer measured, for the sheets in
`catalog/data/fstopo-pins.yaml`, and those are checked against it; today
that list is empty. Every other sheet is fetched **unverified**: only its
size, as the Forest Service's server announced it when you planned, and its
being a TIFF image are checked. The plan says so on each sheet's line —
"unverified: the Forest Service publishes no checksum and Hammunition has
pinned none; only the size is checked" — and counts them in a warning. A
damaged or cut-off download is caught; a sheet altered on the Forest
Service's server is not. That is why the sheets are installed only when you
name them, never by the profile: Hammunition's rule is that a download
without a checksum is not installed by default. When every sheet your
regions need has been pinned, the plan says "every FSTopo quad your regions
need is pinned by Hammunition", and the unit may then join the profile by a
recorded decision (**D-068**). Without FSTopo, `ustopo-qmapshack` builds the
US Topo map alone.

**In QMapShack.** Each sheet's colours are expanded to full colour, tiled,
and given overviews (they come as one long strip each, with no zoomed-out
copies, and a mosaic of sheets with different colour tables would show them
all in the first one's colours), and `FSTopo.vrt` is built over them in the
same directory as `ustopo.vrt`. The *Maps* dock lists it as a second map,
`FSTopo`; tick it and order it against `ustopo` and the Garmin maps as you
like. **Not measured yet: QMapShack drawing it**, any more than US Topo.

**A new vintage.** When the carried index lists a sheet at a newer vintage,
`hammunition update` counts it and
`hammunition install usfs-fstopo ustopo-qmapshack` fetches it and removes
the older one once the new one is on disk.

### USGS 3DEP: bare-earth elevation, if you want it

QMapShack's hillshade, slope and contours come from Copernicus GLO-30 by
default. Copernicus is a *surface* model: under trees it measures the top of
the canopy. Over a forested window in Shenandoah National Park it read
11.8 m above USGS's bare-earth 3DEP on average (measured 2026-09-29), so its
contours ride the treetops. **3DEP** is the ground, at about 10 m rather than
30 m. It is also about ten times the size: a 3DEP tile is about 480 MB where
Copernicus's is about 46 MB for the same square degree (Shenandoah one tile,
Delaware two, about 0.9 GB, Vermont twelve, about 4.4 GB). That size is why
Copernicus stays the default. To choose 3DEP:

```
hammunition station set --dem-source 3dep
hammunition install navigation --dry-run
```

The plan's *USGS 3DEP* part then lists each region's tiles and what each
region downloads, before you confirm; each tile is checked against the
checksum USGS's storage keeps for it ("MD5 from the publisher's object
metadata; not pinned by Hammunition"). `dem-qmapshack` redraws the
contours from 3DEP at its full detail (one tile measured: 17 s and a 212 MB
temporary file to trace, 8.4 MB of contours). Copernicus stays installed:
BRouter's routing elevation reads it. 3DEP covers the United States only; a
region elsewhere gets a warning that QMapShack has no elevation for it while
3DEP is chosen.

To go back: `hammunition station set --dem-source copernicus`, then install
again. The 3DEP tiles are removed and the contours redrawn from Copernicus.
QMapShack drawing hillshade from 3DEP has not been measured yet.

---

## 16. A map in the browser

The same regions, drawn in any web browser on this machine with no program
to learn and no network (**D-071**). `hammunition install navigation` builds
it: `osm-pmtiles` turns each region into vector tiles with the archive's
`tilemaker`, and `vector-map-kit` installs the fixed files the page needs.
To build only this, `hammunition install osm-pmtiles`.

Open it with the reference page's server, and your position with the
tether, each in its own terminal:

```
hammunition reference serve
hammunition maps gps-tether
```

Then open <http://127.0.0.1:8480/map/>. Choose a region at the top left;
the map frames it. Zoom to 14 shows streets, buildings, water, parks and
place names. With the tether running, a red marker shows where you are and
*Centre on me* moves the map there; without it the bar says to start it.
The corner of the map reads "© OpenMapTiles © OpenStreetMap contributors":
the OpenMapTiles schema's CC-BY licence and OpenStreetMap's ODbL ask for
that credit on the map, so it is never hidden.

What it is made of, so you know what runs:

- **The tiles** are built once per region, as you, in
  `~/.cache/hammunition/build/osm-pmtiles/`, by tilemaker with tilemaker's
  own OpenMapTiles profile at v3.0.0. tilemaker's `--store` keeps its memory
  near 0.5 GB instead of 2.8 GB on a region the size of Delaware (measured
  by the spike). They land in
  `/usr/local/share/hammunition/data/osm-pmtiles/<region>.pmtiles`, about
  0.91 times the download.
- **The ocean** is Natural Earth's 1:10m polygon, clipped to each region
  first with GDAL's `ogr2ogr`. The accurate ocean OpenStreetMap's tools use
  (osmdata.openstreetmap.de's water polygons) is rebuilt every day with no
  checksum: its simplified set changed size overnight between 2026-09-29
  and 09-30, so no pin would last a day, and it is not carried. At street
  zoom a coast may sit a little off OpenStreetMap's shoreline.
- **The page** is served by `reference serve`'s own loopback server with
  MapLibre GL JS 6.11.2, pmtiles.js 4.5.0 and the OSM Bright style, each
  pinned by sha256 in `vector-map-kit`. Nothing is loaded from anywhere
  else: the style as tilemaker ships it loads its sprite from GitHub and its
  fonts from a local server of its own, and the page points both at this
  machine. A headless browser with every non-loopback host blocked drew it
  in the test suite with every request on 127.0.0.1.
- **The position** comes from the tether's `GET /position` event stream on
  127.0.0.1 port 10111 (`--position-port` on both commands if that port is
  taken). A browser cannot read the NMEA port, and its own location service
  on Linux is GeoClue's network guess, not your GPS. The tether refuses a
  request that does not name 127.0.0.1 or localhost, and never hands the
  stream to a page from another site.

**Where tilemaker 3.0 is missing.** Ubuntu 24.04, and the releases built on
it, carry tilemaker 2.4, which cannot write PMTiles. The plan says so and
leaves `osm-pmtiles` out of `navigation` there, naming the version it found;
everything else installs.

**What else reads these maps.** Measured by the spike (2026-09-29):

| Program | Reads | Here |
|---|---|---|
| This page | PMTiles vector tiles | yes |
| AIS-catcher 0.70 | its own `.mbtiles` or a z/x/y folder, raster certain, vector not verified | no: tilemaker writes one file per run, and PMTiles is the one made |
| QMapShack, Xastir, SDRangel | raster PNG tiles from a URL | no (below) |
| YAAC | the `.osm.pbf` region itself (*File › OpenStreetMap › Import Raw OSM Map File*) | yes, from `/usr/local/share/hammunition/data/osm-regions/` |
| pat, the Winlink standard forms | no maps at all | not needed |

Raster tiles for QMapShack, Xastir or SDRangel need a whole stack:
PostgreSQL with PostGIS, `osm2pgsql`, `renderd` with `mod_tile` and the
openstreetmap-carto style, all in the archive. The spike imported Delaware
into it (53 s, a 155 MB database) and did not measure the drawing, and the
style wants the same unpinnable daily ocean again. A database service and a
web server to draw PNGs on a field laptop is the heaviest route there is,
so it is documented, not built.

**Tile servers not carried**, each for its reason: martin, go-pmtiles
(`pmtiles serve`) and mbtileserver are GitHub binaries with no checksum
from their publishers, and the page needs nothing they add (go-pmtiles also
listens on every address by default); tileserver-gl needs npm install
scripts that fetch native binaries, which D-037 refuses; planetiler is not
in any archive, needs Java 21 and about 1.45 GB of side downloads before
the first tile, and is slower than tilemaker on a region.

### Routes on the browser map: GraphHopper

The browser map can also plan a route, by car, bike, on foot or hiking,
with turn-by-turn directions and no network, through GraphHopper
(**D-076**). It is not part of `navigation`; install it by name:

```
hammunition install graphhopper-graph
```

That brings two units:

- **`graphhopper`**: GraphHopper 11.1, one Java file
  (`graphhopper-web-11.1.jar`, 47 MB) from Maven Central, checked against
  the sha256 Central publishes beside it, under
  `/usr/local/share/hammunition/graphhopper/`, with Java from your
  distribution (17 or newer; Debian 13 has 21). Central also publishes a
  PGP signature; Hammunition records it and does not check it, and the
  plan says so.
- **`graphhopper-graph`**: GraphHopper's route graph, built on your machine
  from the same regions as everything above, one graph over all of them so
  a route crosses from one region into the next, under
  `/usr/local/share/hammunition/data/graphhopper-graph/`. With no regions
  set, the install refuses and says how to set them.

Then start the reference page as before (`hammunition reference serve`).
When the graph is installed and Java is there, the terminal says `routes:
GraphHopper starting`, and the map's bar gains a second line: *Route for*
(car, bike, foot or hike), *Route* and *Clear*. Press *Route*, then click
where to go: with the tether running the route starts where you are;
without it, click the start first, then the end. The route is drawn in
blue with a green pin at the start, and the bar shows its length and time;
open that line for the directions. Choosing another profile routes the
same two points again. GraphHopper takes a few seconds to start; a route
asked before then says it is still starting. You can also open a route
directly, for example
`http://127.0.0.1:8480/map/#route=44.2601,-72.5754;44.2700,-72.5600;hike`
(two points near Montpelier, Vermont, as latitude,longitude, then the
profile).

What the profiles do: **car** and **bike** follow roads and cycle routes;
**foot** keeps off mountain paths (it refuses `sac_scale` mountain hiking
and harder); **hike** takes trails by their difficulty, mountain paths
included. Routes are flat: GraphHopper's own elevation sources are online
downloads, and none of them reads the Copernicus tiles Hammunition
installs.

**How it runs, so you know what is listening.** `reference serve` starts
GraphHopper's own server as a child on 127.0.0.1, at a port the system
picks each time, and stops it when you press Ctrl-C (or when
`reference serve` is killed). The map never calls GraphHopper itself: it
asks `/map/route` on the reference page's own server, which refuses any
request that does not name 127.0.0.1 or localhost, rebuilds the request
from two points and a profile, and passes GraphHopper's answer back.
GraphHopper's own server answers every web page with
`Access-Control-Allow-Origin: *` and checks no Host name (measured on
11.1), so while it runs a page from elsewhere in your browser that found
its port could ask it for routes over your regions. Stop `reference serve`
when you are not using the map. GraphHopper's own web page at `/maps/` on
that port is not used: its base maps all come from the internet. Its log
is `~/.cache/hammunition/reference/graphhopper/graphhopper.log`; if
GraphHopper stops, the books and the map keep serving and the Route control
says the router stopped.

**Which router for what.** Each one is here for a program that uses it:

| Router | Used by | What it is for |
|---|---|---|
| Navit's own | Navit (sections 4 and 5) | Driving with spoken directions and address search |
| Routino | QMapShack (section 9) | Routes on foot or by bike over the trails map; ignores trail difficulty and hills |
| BRouter | QMapShack (section 9) | Hiking by trail difficulty, and bike routes that weigh climbs from the elevation |
| CoMaps' own | CoMaps (section 17) | Phone-style car, bike and foot routing with address search |
| GraphHopper | The browser map (this section) | Car, bike, foot and hiking routes in any browser on this machine, from your position |

GraphHopper is installed by name only, because of its size: the graph is
about 3.7 times all your downloads together (Delaware's 22.1 MB made 78 MB,
measured by the routing spike), the largest of any map unit, and building
it took 1.2 GB of memory on Delaware, with nothing larger measured. The
`navigation` profile already carries three offline routers.

---

## 17. CoMaps: search and routing like a phone app

CoMaps is the desktop build of the CoMaps phone app, a community fork of
Organic Maps. It draws vector maps on the machine, searches addresses,
places and postcodes from an index inside each map file, and routes by
car, bike, on foot and by public transport, all offline. It reads its own
map format, not Geofabrik's, so it has its own map unit (**D-069**).

**Where you are comes from GeoClue.** CoMaps on Linux asks for its
position from GeoClue2 only, the desktop's location service, by name. It
has no gpsd client and no NMEA reader. So Hammunition hands GeoClue the GPS
tether's NMEA on a socket (one `hardware apply`, then the tether running);
"Giving CoMaps a position" below is the whole of it, with what it changes,
what it costs and what has not been measured yet on a real desktop.

### Install it

Both units are in the `navigation` profile, and use the regions you chose
in section 1:

```
hammunition install comaps comaps-maps --dry-run
hammunition install comaps comaps-maps
```

`comaps` is built from source: no archive carries it and upstream
publishes no Linux binary. The plan names the tag (`v2026.08.31-14`) and
the commit it must resolve to (`72632e4`, the commit Flathub, nixpkgs and
the AUR all build), fetches the source and its submodules, builds a small
Python for the build with a pinned protobuf, runs CoMaps' own
`configure.sh` and then CMake. Expect tens of minutes; by hand, on an
8-core laptop at two jobs, configure took about 3 minutes and the compile
about 8. The build needs about 2 GB of memory per parallel job, which the
engine already sizes to your machine.

`comaps-maps` downloads CoMaps' own maps for your regions. The plan prints
each map with its size, its licence and how it is checked:

```
Fetch CoMaps map US_Vermont (60.9 MB, ODbL-1.0) — SHA-1 and size from CoMaps' own map index at the pinned commit (the publisher's check)
```

That is the check CoMaps publishes and nothing stronger: the SHA-1 and
exact size from its index (`countries.txt`) at the commit the app is built
from. The size is compared exactly because CoMaps' mirrors answer a
missing file with a normal-looking page. The sha256 of each file as
installed goes into the transaction log. A US state is one to a dozen
files and tens to a few hundred megabytes; Vermont is 61 MB, all of the
US 15.7 GB.

A region CoMaps names differently from Geofabrik (Geofabrik's
`europe/germany/bayern` is CoMaps' "Free State of Bavaria") has no CoMaps
map. The plan says so by name and fetches nothing for it; the rest
install. All 50 US states and DC are covered, and 165 of the 197
country-level Geofabrik regions; China, Russia, Ireland and Northern
Ireland, and Israel and Palestine are among those that are not. If none of
your regions has a CoMaps map, the plan says that too, and nothing is
fetched. A LAN mirror (`station set --mirror`, see the LAN mirror guide) is
asked first for each map, checked the same way.

### Start it

From the menu: **CoMaps with your offline maps**, under Navigation & Maps.
It runs `hammunition maps comaps`, which, as you:

- records in `~/.config/CoMaps/settings.ini` that CoMaps' licence and
  copyright notice is accepted, only if the file has no answer yet, so
  the first start does not stop at that dialog. The notice itself is
  `/usr/local/share/comaps/data/copyright.html`;
- links each installed map into `~/.local/share/CoMaps/<version>/`, where
  CoMaps looks. A map you downloaded inside CoMaps is left alone;
- starts CoMaps with those two directories named.

Started from the menu, it opens no terminal, so you will not see it say
that it recorded the licence answer; `hammunition maps comaps
--configure-only` in a terminal does the first two, says what it did, and
does not start CoMaps. CoMaps also installs its own menu entry, **CoMaps**, under
its own categories. That one starts it without the preparation above: the
first start shows the licence dialog, and it does not see Hammunition's
maps.

### Keep the maps current

The maps are the version the app's own index names, and CoMaps' server
keeps a version for months, not forever. `hammunition update comaps-maps`
says whether every map your regions need is installed at that version;
`hammunition update comaps-maps --upstream` asks the server and says
**pin expiring** from 90 days after the version's date and **pin expired**
once it is gone (a busy server is reported as unanswered, not expired). A new version comes with a new CoMaps release in the
catalog; until then the maps you have keep working offline.

### Giving CoMaps a position

The chain is gpsd → the GPS tether (section 11) → a unix socket → GeoClue's
**network-NMEA** source → Qt's `geoclue2` plugin → CoMaps. No CoMaps patch
and no Avahi. `comaps` depends on `geoclue-2.0` and
`libqt6positioning6-plugins`, so installing it brings both.

**Once:** set GeoClue up with the hardware step, after reading its plan:

```
hammunition hardware apply --dry-run
hammunition hardware apply
```

Where GeoClue is installed, the plan prints two files and writes them as
root (**D-069**):

- `/etc/geoclue/conf.d/90-hammunition-gps.conf`, a drop-in read after
  Debian's own `geoclue.conf`, which is not edited:

  ```
  [network-nmea]
  enable=true
  nmea-socket=/run/hammunition-gps/nmea.sock
  ```

- `/etc/tmpfiles.d/hammunition-gps.conf`, one line,
  `d /run/hammunition-gps 2750 <you> geoclue -`. `/run` is emptied at every
  boot; this line has systemd make the directory again each time, and the
  apply runs `systemd-tmpfiles --create` on it so it exists now. Mode 2750
  with the setgid bit means the socket the tether makes inside takes
  GeoClue's group: GeoClue can read it, and no other account can.

It then runs `systemctl try-restart geoclue`, which restarts GeoClue only
if it is running. No `[app.comaps.comaps]` entry is written: GeoClue treats
any app that is not a Flatpak as a system app and allows it without one
(measured in the spike, below). `hammunition hardware apply --no-geoclue`
skips all of this.

**Every time:** start **GPS position for QMapShack, this machine only**
from the menu (it runs `hammunition maps gps-tether`), then CoMaps. Once
the drop-in is there the tether serves
`/run/hammunition-gps/nmea.sock` beside TCP 10110 with no option, and says
so when it starts. `--no-nmea-socket` leaves the socket off for one run.

**What to know before agreeing.** The plan says these four things, word
for word:

- GeoClue reads its configuration only when it starts; it exits after 60 s
  with no client, and `systemctl try-restart geoclue` applies a change at
  once.
- While the tether runs, GeoClue hands the GPS fix to any native
  (non-Flatpak) app of a user with a GeoClue agent, and Debian's demo agent
  does not prompt.
- Stock GeoClue also asks beacondb (nearby Wi-Fi networks, or GeoIP when
  Wi-Fi is off) whenever CoMaps asks for a position, so with the tether
  stopped the map shows that coarse network location; only GeoClue's
  `[static-source]` would stop the GeoIP lookups, and Hammunition does not
  change it.
- Qt caches the last fix under `~/.local/share/qtposition-geoclue2`.

The third is the one to remember in the field: a dot with the tether
stopped is a guess from the network (or the last cached fix), not the
receiver. With the network down there is nothing to guess from.

**The agent.** GeoClue gives a position only to a user with a GeoClue
agent running in their session. `geoclue-2.0` starts Debian's demo agent at
login on every desktop but GNOME (whose shell is its own agent), from
`/etc/xdg/autostart/geoclue-demo-agent.desktop`, so install CoMaps, then
log out and back in once. Without an agent, GeoClue holds CoMaps' request
and Qt gives up after about 25 s: no dot, no error on screen.
`hammunition doctor` says whether the agent is running (it reads
`busctl --user list`, which starts nothing).

**Inspect it:**

```
cat /etc/geoclue/conf.d/90-hammunition-gps.conf /etc/tmpfiles.d/hammunition-gps.conf
ls -ld /run/hammunition-gps
journalctl -u geoclue | grep -i nmea
```

The directory reads `drwxr-s---` with you as owner and `geoclue` as group.
GeoClue's journal shows only failures here: `Failed to connect to NMEA
service: No such file or directory` (the tether is not running) or `…
Connection refused` (a tether that crashed left its socket), repeated every
5 s while something asks for a position. GeoClue reconnects by itself when
you start the tether, with no restart. Its success line, `NMEA service
connected.`, is a debug message the stock service does not log. The sign
that it worked is in the tether's own terminal: `A client on the socket
connected`. `hammunition doctor` reports the files, the directory and the
agent.

One thing `doctor` does not read: another drop-in in
`/etc/geoclue/conf.d/` sorting after `90-` (a `99-something.conf`) that sets
`nmea-socket` itself wins over ours. `ls /etc/geoclue/conf.d/` shows whether
there is one.

**Reverse it:** `hammunition hardware unapply`, which deletes both files
(each only if it starts with Hammunition's header), removes the socket,
runs `rmdir /run/hammunition-gps` and `systemctl try-restart geoclue`. Stop
the tether first. By hand it is the same four steps, with `sudo`. The Qt
cache in your home is yours: `rm -r ~/.local/share/qtposition-geoclue2`
forgets the last fix.

**How it was measured, and what is still owed.** The spike of 2026-10-01
ran Debian's own GeoClue 2.7.2, its demo agent and Qt 6.8.2's `geoclue2`
plugin, asking exactly as CoMaps does, in a private namespace with no
network, with a fake NMEA feed of a fixed position (Montpelier, Vermont) on
the socket: the position reached the client, a stopped feed gave none,
and a restarted feed was picked up with no GeoClue restart, both over
Debian's untouched `geoclue.conf` plus the drop-in. Not yet run on the
field laptop, and owed by the bench:

- the demo agent present in the Plasma session (`busctl --user list`);
- the real GeoClue, sandboxed as user `geoclue` by its systemd unit,
  connecting to the socket in `/run`: the tether's `A client on the socket
  connected` while CoMaps asks, and no `Failed to connect to NMEA service`
  in the journal (read from the kernel's rules, which exempt sockets from
  read-only mounts; not seen);
- CoMaps' dot following the tether, and what it shows with the tether
  stopped;
- `/run/hammunition-gps` made again after a reboot;
- the demo agent autostarting on the Xfce and LXQt VMs.

**What stays a gap.** A Flatpak CoMaps would also need an
`[app.comaps.comaps]` entry or a desktop that prompts; Hammunition builds
the native one and writes no entry. Reading NMEA without GeoClue would
need a CoMaps patch, which the engine refuses and nobody carries.

### Not measured yet

- **US address search.** The desktop app has no way to script a search,
  so the quality of US address results is for a person at the screen to
  judge; the bench owes it.
- **The build through Hammunition.** CoMaps was built by hand on
  2026-09-29 with the same steps; the engine's build, including the
  shallow submodule fetch, has not run.
- **CoMaps reading the linked maps.** Its source reads a linked file like
  any other; a running CoMaps has not been seen to.

---

## What QMapShack does not do (yet)

- **No offline address search**: use Navit (section 10).
- **Routino does not route on trail difficulty** (section 9); BRouter's
  `hiking-mountain` profile does.
- **No hiking map style.** Trails are drawn by mkgmap's default style; no
  hiking style is packaged in the archive. One visible result: residential
  land use is drawn as hatching when you zoom in close. It is cosmetic.
- **Contours are unlabelled lines**, legible rather than pretty. Labelled
  contours need a tool the archive does not carry.
- **The Garmin maps have no address index**, and QMapShack would not read
  one anyway.
- **No terrain where Copernicus publishes none.** Its public 30 m release
  leaves out some land as well as the open sea (Armenia and Azerbaijan, for
  example). A region inside it gets its maps and no terrain, and the plan
  warns by name. The 90 m Copernicus release is the candidate route; it has
  not been measured here.

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
| Elevation tiles | about 39 MB a tile; tens to hundreds a region | `/usr/local/share/hammunition/data/dem-copernicus/` | Until uninstall, or no region needs the tile |
| Contours | about 5.5 MB a tile, with up to 98 MB of scratch at a time | `/usr/local/share/hammunition/data/dem-qmapshack/` | As long as the tiles |
| BRouter itself | about 8.5 MB, once | `/usr/local/share/hammunition/brouter/` | Until uninstall |
| BRouter's routing files, all regions | about 0.2× all the regions together (Delaware: 3.3 MB from 22.1 MB) | `/usr/local/share/hammunition/data/brouter-segments/` | Rebuilt when the regions or tiles change |
| Their build scratch | up to 3× all the regions together (an allowance, not measured), plus the merged regions when there are two or more, and about 650 MB of elevation scratch for one 5-degree square at a time | `~/.cache/hammunition/build/brouter-segments/` | Only while they build |
| US Topo sheets (US regions) | about 8 MB a sheet | `/usr/local/share/hammunition/data/usgs-ustopo/` | Until uninstall, or no region needs the sheet |
| The sheets made for QMapShack | about 1× each sheet, measured on one | `/usr/local/share/hammunition/data/ustopo-qmapshack/` | As long as the sheets |
| Their build scratch | about 1× one sheet at a time | `~/.cache/hammunition/build/ustopo-qmapshack/` | Only while it builds |
| FSTopo sheets (National Forest land, installed by name only) | about 21 MB a sheet | `/usr/local/share/hammunition/data/usfs-fstopo/` | Until uninstall, or no region needs the sheet |
| FSTopo sheets made for QMapShack | about 1.2× each sheet, measured on one | `/usr/local/share/hammunition/data/ustopo-qmapshack/fstopo/` | As long as the sheets |
| 3DEP tiles (only with `--dem-source 3dep`) | about 480 MB a tile, ten times Copernicus | `/usr/local/share/hammunition/data/dem-3dep/` | Until uninstall, the source set back to `copernicus`, or no region needs the tile |
| 3DEP contour scratch | about 212 MB, one tile at a time | `~/.cache/hammunition/build/dem-qmapshack/` | Only while it builds |

Terrain is the part that grows fastest with a region's area. Measured on
2026-09-28 over Geofabrik's US state outlines: a region's terrain is tens
to hundreds of tiles; a contiguous US state can exceed 90 tiles (about
3.6 GB); Alaska is 449 tiles (about 17.5 GB); the 50 states and DC together
are 1,447 tiles. Regions that reach across the 180° meridian, such as
Alaska, Fiji, New Zealand and Russia's far east, select their tiles like any
other. Your own figure is in the plan: the Terrain block prints each
region's tile count and download size, and a dry run
(`hammunition install navigation --dry-run`) shows it before anything is
fetched.

A tile's download is deleted from the cache as soon as it is installed: a
tile never changes, so there is no reason to keep two copies. The plan
counts all of this with the Navit figures above, and refuses before
anything is fetched if a disk is short.

GraphHopper, only when you install it by name (section 16), adds:

| What | How much | Where | How long it stays |
|---|---|---|---|
| GraphHopper itself | 47 MB, once | `/usr/local/share/hammunition/graphhopper/` | Until uninstall |
| The route graph, all regions | about 3.7× all the regions together (Delaware: 78 MB from 22.1 MB, one measurement) | `/usr/local/share/hammunition/data/graphhopper-graph/` | Rebuilt when the regions or GraphHopper change |
| Its build scratch | the graph once more, plus the merged regions when there are two or more | `~/.cache/hammunition/build/graphhopper-graph/` | Only while it builds |

Building it took about 1.2 GB of memory on Delaware; Java's heap is capped
at 4 GB, and a region much larger than Delaware has not been tried.

---

## Taking the downloads from your own network

If a machine on your LAN keeps a copy of the regions and tiles
([Hammunition Bunker](https://github.com/ChiefGyk3D/hammunition-bunker)),
`hammunition station set --mirror http://bunker.lan:8080/` makes every map
and terrain download ask it first, checked against the same digests as the
publisher's, and fall back to the publisher on any failure (**D-070**).
[lan-mirror.md](lan-mirror.md) is the walk-through.

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

US Topo sheets (section 15) always get the second wording. The index
carries the checksum the storage service reported when it was built, the
bucket is asked again before each download, and the download must
reproduce it. For a sheet uploaded in parts that checksum is the MD5 of each
part's MD5; Hammunition works out the part size by trying each whole
megabyte-size part, and a download matching none is refused by name. USGS
3DEP tiles (section 15) are checked the same way and get the same wording.

FSTopo sheets (section 15) get one of two others, because the Forest
Service publishes no checksum at all:

- **"sha256, pinned by Hammunition (the Forest Service publishes no
  checksum)"**: the sheet has a row in `catalog/data/fstopo-pins.yaml`,
  measured by the maintainer. A sheet the Forest Service has since re-issued
  is refused by name until it is measured again.
- **"unverified: the Forest Service publishes no checksum and Hammunition
  has pinned none; only the size is checked"**: nothing checks the content.
  The size the server announced and a TIFF header catch a cut-off download
  or a web page in its place; nothing catches a sheet altered at the source.
  Like hearham's repeater list (section 13), it is data Hammunition cannot
  verify, and the plan counts these sheets in a warning every time.

The ACMA's repeater register (section 13) gets a third: **"unverified: the
ACMA publishes no checksum ... the zip's own CRC-32s and the tables the
repeater import reads are checked"**. The file changes daily, so nothing can
be pinned; the zip's own checksums catch a damaged or cut-off download and a
web page in its place, never a file altered at the source.

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

From this version the menu entry works: `qmapshack-offline` and `gps-tether`
run Hammunition by its full path, because the desktop starts a menu entry
without `~/.local/bin` on its `PATH` (Plasma runs each one as a systemd user
service). A launcher written by an earlier version says plain `hammunition`
and fails from the menu with `hammunition: not found`, status 127, in the
session journal (`journalctl --user -e`). One command rewrites it:

```
hammunition menus apply
```

`hammunition doctor` names every launcher still in that state, under
**launchers**.

If a launcher written by this version says `not found`, the Hammunition
it names has moved: the checkout was moved or its `.venv` rebuilt somewhere
else. Run `./bootstrap.sh` from the checkout you use, which links
`~/.local/bin/hammunition` to it again, then `hammunition menus apply`,
which rewrites the launchers with that path. `hammunition doctor` names the
launcher and the path it can no longer find.

For anything else, run the launcher in a terminal to see why:

```
qmapshack-offline
```

If it says it cannot read `~/.config/QLandkarte/QMapShack.conf`, nothing was
changed and QMapShack was not started: the file holds something the
launcher does not edit on a guess. Add the directories in QMapShack's own
setup instead, or move the file aside (`mv ~/.config/QLandkarte/QMapShack.conf
~/.config/QLandkarte/QMapShack.conf.old`) and run the launcher again.

If QMapShack starts and at once stops with "The specified translations XML
file did not exist", Routino's data file is missing. `hammunition doctor`
names it, and this puts it back:

```
sudo apt-get install --reinstall routino-common
```

### The map has no Route control, or says the router stopped

The Route control appears only when `reference serve` started GraphHopper;
the terminal says why when it did not. The usual reasons: the graph is not
installed (`hammunition install graphhopper-graph`); it was built by
another GraphHopper than the one installed, after an upgrade
(`hammunition install graphhopper-graph` rebuilds it); or `java` is not on
the PATH (`hammunition install graphhopper`). If the control says the
router stopped, read the last lines of
`~/.cache/hammunition/reference/graphhopper/graphhopper.log`; a graph too
large for Java's 4 GB heap would end there with Java's out-of-memory error
(not yet seen: nothing larger than Delaware has been built). "Still
starting" goes away after a few seconds. A route that comes back "Point 0 is
out of bounds" asked for a point outside your regions.

### US Topo is listed but draws nothing

Not yet explained (section 15). The same goes for `FSTopo`, whose map is
`FSTopo.vrt` in the same directory (in NAD83 degrees rather than Web
Mercator). Things worth trying, and reporting back with what happened:

- Tick `ustopo` in the *Maps* dock, then zoom to a place inside one of your
  US regions: the map draws only over the sheets you have.
- Check the map file names sheets that exist:
  `gdalinfo /usr/local/share/hammunition/data/ustopo-qmapshack/ustopo.vrt`
  prints its size and corners in Web Mercator; if it reports an error
  opening a sheet, `hammunition install ustopo-qmapshack` rebuilds the map
  from the sheets that are there.
- Move `ustopo` above the Garmin maps in the dock; a map below an opaque
  one is hidden.

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

### The install waits at a sudo password prompt

Converting maps takes a long time, and it runs as you, not as root. sudo
remembers your password for 15 minutes by default, so in Hammunition 0.14.3
and earlier the step after a long conversion, which needs root to put the map in
place, asked for the password again. If you had walked away, the install
waited there: one run on the field laptop waited 7.8 hours after 30 minutes
of work (issue #137).

**The engine now handles this itself** (D-062). When a plan has both root
steps and steps that run as you, it prints a *sudo* section, asks for your
password once, just after you confirm and before the first step, and keeps
sudo's ticket valid for the rest of the run with `sudo -n -v` every 4
minutes. It stops when the run ends; your password is only ever typed into
sudo itself. You can walk away once the first step has started.

If you still see a second prompt, the section in the plan says why it can
happen: the install ran with `--no-sudo-keepalive`, or a refresh failed and
printed a warning saying so (your sudoers sets `timestamp_timeout` below 4
minutes, or something ran `sudo -k`). In either case this still works, in
the same terminal as the install:

```
sudo -v && (while sudo -n -v; do sleep 240; done &) && hammunition install navigation --no-sudo-keepalive
```

Run it in the install's own terminal, not another window. sudo keeps a
separate ticket per terminal by default (`timestamp_type=tty`, as on the
field laptop), so a loop in another window refreshes a ticket the install
never uses. The engine's own refresh runs from the install's process, so it
has no such problem. Unlike the engine's refresh, the loop keeps running
after the install ends. `sudo -k` in the same terminal ends it: the ticket
is gone, the loop's next `sudo -n -v` fails, and the loop exits.

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
hammunition uninstall brouter-segments dem-qmapshack dem-copernicus osm-routino osm-garmin
```

BRouter itself and its two filter files go with:

```
hammunition uninstall brouter brouter-mapcreator-profiles
```

and the US Topo sheets and their QMapShack map:

```
hammunition uninstall ustopo-qmapshack usgs-ustopo
```

Your QMapShack settings keep the directories the launcher added; QMapShack
lists nothing there once they are gone.

Your repeater layer is not part of any unit; `hammunition maps repeaters
remove` removes it (section 13).

The phone files go the same way, with the POI writer, and leave osmosis
installed; the copies in `~/.local/share/hammunition/phone/` are yours to
delete:

```
hammunition uninstall mapsforge-poi mapsforge-map
```

The browser map's tiles and its kit go with:

```
hammunition uninstall osm-pmtiles vector-map-kit
```

and GraphHopper and its route graph with:

```
hammunition uninstall graphhopper-graph graphhopper
```

`~/.cache/hammunition/reference/graphhopper/` (the server's configuration,
its links to the graph and its log) is yours to delete.

CoMaps' maps go with `hammunition uninstall comaps-maps`. CoMaps itself is
refused by `uninstall`, as every build is whose own install rule wrote into
`/usr/local`: that rule leaves no list of files to reverse, and what it
wrote is in the transaction log. The links in `~/.local/share/CoMaps/` are
removed by `hammunition maps comaps` once their maps are gone.

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

- A route on foot, within one region or across the boundary between two.
  QMapShack 1.17.1 lists and loads the `hammunition` database (field
  laptop, 2026-09-29); a route has not yet been recorded.
- Slope shading. Hillshade draws; slope was not tried.
- QMapShack 1.21.1 from backports. Everything above ran on 1.17.1.

For BRouter (**D-063**), every command the build runs was run on the
development host on 2026-09-29, against the pinned jar, on two synthetic
regions and a synthetic elevation tile, and BRouter, started the way
QMapShack starts it, routed across both with that elevation. Not yet
measured, and owed by the bench:

- **A route in QMapShack through BRouter.** No desktop runs on the
  development host. QMapShack's own check of the install (it runs the jar
  and reads its version) has not been seen to pass.
- **BRouter on loopback only while QMapShack routes**: `ss -ltnp | grep
  17777` during a route should show `127.0.0.1` and nothing wider.
- The build on a real region through `hammunition install`, with its time,
  memory and scratch; the scratch figure in the plan is an allowance.
- Java on the targets other than Parrot.

For the US Topo sheets (**D-068**), one Delaware sheet was downloaded,
checked against its two-part checksum, reprojected and cropped on the
development host on 2026-09-29 (2.5 s, 9.2 MB in, 8.9 MB out with
overviews). Not yet run:

- **QMapShack drawing the US Topo map.** One run on the development host
  opened the map file and left the map area blank, reason unknown. This
  belongs in a virtual machine, not on a desktop in use: QMapShack's
  single-instance socket is shared whatever `HOME` is set to.
- The whole install of the sheets through Hammunition, on any machine.

For FSTopo and 3DEP (**D-068**, amended 2026-10-01), one George Washington
National Forest FSTopo sheet and one Shenandoah 3DEP tile were downloaded
through Hammunition's own code on the development host on 2026-10-01 and
run through the converters' commands: the sheet expanded and given
overviews in 10.6 s (21.2 MB in, 24.5 MB out), the tile's contours traced
and drawn in about 21 s (488 MB in, 8.4 MB out). Not yet run:

- **QMapShack drawing `FSTopo.vrt`, or hillshade from 3DEP.** The same
  caveat as US Topo: in a virtual machine, never on a desktop in use.
- Whether every sheet in the Forest Service's index has a GeoTIFF at its
  gateway. A sheet with none refuses the plan by name.
- The whole install of either through Hammunition, on any machine.

For the browser map (**D-071**), the page was drawn by headless Chromium in
the test suite from the pinned kit and a synthetic tile, with every
non-loopback host blocked and every request on 127.0.0.1; and the spike drew
a real Delaware map the same way. Not yet measured, and owed by the bench:

- **tilemaker through the engine.** tilemaker is not installed on the
  development host, so the converter ran only against a stand-in. The first
  real run, with Natural Earth's clipped ocean in place of the water
  polygons the spike used, is the bench's, with its time, memory and the
  `--store` scratch (the plan allows three times the download).
- The page in a desktop browser, with the tether feeding a real receiver's
  position.
- tilemaker 3.1 (Ubuntu 26.04) and 3.2 (Debian forky) with the 3.0 profile.

For routes on the browser map (**D-076**), every command the build and the
server run was run on the development host on 2026-10-01, against the
pinned jar and the archive's Java, on two synthetic regions near
Montpelier: the graph built through the engine's own converter (4.6 s),
GraphHopper started from the read-only graph the way `reference serve`
starts it, listening on 127.0.0.1 only, and car, bike, foot and hiking
routes asked through the reference server, one crossing from one region
into the other; the hike took a mountain path the foot route went round.
The Route control was drawn by headless Chromium against a stand-in for
GraphHopper, every request on 127.0.0.1. Not yet measured, and owed by the
bench:

- **A real region through `hammunition install graphhopper-graph`**, with
  its time, memory and scratch; the figures above are the spike's, on
  Delaware, and nothing larger has been built.
- **The Route control in a desktop browser** on the field laptop, starting
  from a real receiver's position.
- Java on the targets other than Parrot.

Measured on the field laptop on 2026-09-29, and recorded in bench session
12: the whole install on two regions, with its build times; QMapShack
listing the maps, the contour map and the elevation from the directories
the launcher writes; hillshade; and the GPS tether giving QMapShack a
position from a real receiver.

For repeaters on the map (**D-064**), nothing has been drawn on a desktop
yet: QMapShack showing the GPX and the POI collection (and reading the
collection from `poiPaths` under `[Canvas]`), Navit's labels and tower icons,
and the *POIs → Other* listing all rest on reading QMapShack's and Navit's
source, not on a screen. The columns of a real RepeaterBook CSV export, and
what a real GPX export puts in `<name>` and `<desc>`, have not been seen:
they need one export by a logged-in operator.

For the phone files (**D-067**, section 14): none has been loaded on a
phone, the converters have not run through Hammunition on real hardware,
and their figures come from one region.

For CoMaps (**D-069**), see section 17: US address search, the build
through the engine and CoMaps reading the linked maps are all owed.

The offline reference (Kiwix books, dictionaries, ICS forms) is its own
profile, `reference` (D-066). The browser map (section 16) is in this one.
