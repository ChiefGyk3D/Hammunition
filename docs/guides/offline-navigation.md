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
Reading gpsd at 127.0.0.1 port 2947. Any number of NMEA programs may connect at once.
Options: --gpsd HOST[:PORT] for a gpsd on another machine, --port N if 10110 is taken.
Ctrl-C stops it. Navit reads gpsd directly and needs none of this.
```

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

## 13. CoMaps: search and routing like a phone app

CoMaps is the desktop build of the CoMaps phone app, a community fork of
Organic Maps. It draws vector maps on the machine, searches addresses,
places and postcodes from an index inside each map file, and routes by
car, bike, on foot and by public transport, all offline. It reads its own
map format, not Geofabrik's, so it has its own map unit (**D-069**).

**What it cannot do on the laptop yet: show where you are.** CoMaps on
Linux asks for its position from GeoClue2 only, the desktop's location
service, by name. It has no gpsd client and no NMEA reader, so neither
gpsd nor the GPS tether reaches it. Use it to find a place and plan a
route; use Navit (section 4) or QMapShack with the tether (section 11) to
see yourself move. The route to a position is in "Giving CoMaps a
position" below, and none of it is done by Hammunition.

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
install. All 50 US states and DC are covered.

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

`hammunition maps comaps --configure-only` does the first two and does
not start it. CoMaps also installs its own menu entry, **CoMaps**, under
its own categories. That one starts it without the preparation above: the
first start shows the licence dialog, and it does not see Hammunition's
maps.

### Keep the maps current

The maps are the version the app's own index names, and CoMaps' server
keeps a version for months, not forever. `hammunition update comaps-maps`
says whether every map your regions need is installed at that version;
`hammunition update comaps-maps --upstream` asks the server and says
**pin expiring** from 90 days after the version's date and **pin expired**
once it is gone. A new version comes with a new CoMaps release in the
catalog; until then the maps you have keep working offline.

### Giving CoMaps a position (not done, not measured)

The route, for anyone who wants to try it by hand:

1. Feed the GPS to GeoClue. GeoClue's **network-NMEA** source reads NMEA
   from a network service advertised on the local network; Parrot's
   `/etc/geoclue/geoclue.conf` has it enabled. Something would have to
   advertise the tether's NMEA there.
2. Allow CoMaps. GeoClue asks a desktop agent before it gives an app a
   position, and Parrot's configuration names no KDE agent. An
   `[app.comaps.comaps]` section with `allowed=true` in `geoclue.conf` is
   the usual way.

Both are changes to the whole machine, neither has been measured here, and
Hammunition makes neither. Until they are, CoMaps has no "you are here" on
the laptop.

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

Your QMapShack settings keep the directories the launcher added; QMapShack
lists nothing there once they are gone.

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

Measured on the field laptop on 2026-09-29, and recorded in bench session
12: the whole install on two regions, with its build times; QMapShack
listing the maps, the contour map and the elevation from the directories
the launcher writes; hillshade; and the GPS tether giving QMapShack a
position from a real receiver.

For CoMaps (**D-069**), see section 13: US address search, the build
through the engine and CoMaps reading the linked maps are all owed.

Offline reference (Kiwix, a local tile server) is the next piece of this
work and not in this profile.
