<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# How much disk you need

Short answer: one or two software profiles fit in about 5 GB of free space
on top of your operating system. The whole catalog needs about 55 GB. Offline
maps, official topo sheets and Wikipedia are what take a disk from there to
hundreds of gigabytes, and you choose each of them.

This page gives every figure with its source. A figure is one of four kinds,
and each row says which:

- **Measured**: someone read it off a real machine or a real publisher
  response, and the page it comes from is named.
- **Pinned**: the catalog records the publisher's size, so the plan can print
  it before it downloads anything.
- **Quoted**: the maintainer reported it, and it is not recorded in this
  repository's measurement pages. Treat it as a good estimate.
- **Unmeasured**: nobody has measured it. The row says so rather than guess.

The engine does not make you trust this page. `hammunition install PROFILE
--dry-run` prints the size of every data artifact (a map region, a terrain
tile, a Wikipedia book) in the plan, before it asks for consent (**D-049**).
Read that number for your own selection; this page is for choosing a disk
before you have one.

## The three tiers

| Tier | For | Free space on top of your OS | Suggested SSD |
|---|---|---|---|
| **Minimum** | One or two software profiles, for example `station` and `digital-modes` | About 5 GB, including the build cache and some headroom | Your distribution's own minimum, plus 5 GB. We have not measured a bare Parrot, Debian or Kali install, so check your distribution's page. |
| **Recommended** | The whole catalog and a few map regions | About 55 GB, plus the regions you pick (see below) | 256 GB |
| **Large** | Official topo sheets for several states, full English Wikipedia, many regions, terrain for large states | About 220 to 300 GB | 512 GB, and 1 TB if you add more |

The suggested sizes are our advice, not a measured limit. They are the
measured use plus headroom for a kernel update, a second set of build
trees and the scratch space a map conversion needs while it runs.

## Where the numbers come from

### The operating system

| Figure | Value | Kind and source |
|---|---|---|
| A full Parrot Security install with the whole catalog, dpkg Installed-Size for the whole OS | 32.9 GB | Quoted. One run on the field laptop (a Dell Latitude 5430 Rugged, Parrot Security 7.4). |
| A bare install of each supported distribution | | Unmeasured here. |

That 32.9 GB covers everything apt installed, the distribution's own
software as well as ours, so it is not a per-profile figure. It does not
count `/usr/local`, where source builds and data land.

### Software, per profile

The footprints are on each profile's page, which is generated from the
manifests plus prose (`hammunition show PROFILE` prints the same line).
These are the 1.0 profiles.

| Profile | Installed software | Kind and source |
|---|---|---|
| [`station`](../profiles/station.md) | about 125 MB | Estimate in the profile page |
| [`morse`](../profiles/morse.md) | under 100 MB | Estimate in the profile page |
| [`antenna`](../profiles/antenna.md) | about 150 MB, plus terrain if your map regions are set | Estimate in the profile page |
| [`electronics`](../profiles/electronics.md) | about 250 MB, plus about 780 MB of Qt development packages for the LibreVNA build | The 780 MB is measured on a bare Debian 13 image, 2026-10-01 |
| [`rf-security`](../profiles/rf-security.md) | about 300 MB | Estimate in the profile page; Kismet's share measured by apt on 2026-09-30 |
| [`satellite`](../profiles/satellite.md) | about 400 MB, about double on a machine without GNU Radio | Estimate in the profile page |
| [`listening`](../profiles/listening.md) | about 400 MB | Estimate in the profile page |
| [`propagation`](../profiles/propagation.md) | about 450 MB | The Node tree is measured at about 140 MB; the rest is estimated |
| [`packet`](../profiles/packet.md) | about 500 MB plus 220 MB for FreeDATA's venv | The venv is measured on Parrot; the rest is an estimate |
| [`logging`](../profiles/logging.md) | about 700 MB | Estimate in the profile page |
| [`digital-modes`](../profiles/digital-modes.md) | about 1.2 GB | Measured: 1.28 GB on Kali rolling, 2026-09-02, `df` before and after |
| [`sdr`](../profiles/sdr.md) | about 1.5 GB, about 300 MB without GNU Radio | Estimate in the profile page |
| **All twelve 1.0 profiles** | **about 6.3 GB, an upper bound** | The sum of the rows above. They overlap (GNU Radio is shared by `sdr`, `satellite` and others), so the real union is smaller. |

Three source builds add their development packages on top of those
figures, measured on bare Debian 13 images and not added to the profile
totals: DroidStar about 1.1 GB, `pihpsdr` about 1.0 GB, LibreVNA about
780 MB. They share Qt, so they do not add up to 2.9 GB, but what they add
together has not been measured.

The post-1.0 profiles are small except for their data:
[`workstation`](../profiles/workstation.md) about 200 MB,
[`editors`](../profiles/editors.md) about 400 MB each, `rfid` under 50 MB,
and [`navigation`](../profiles/navigation.md),
[`reference`](../profiles/reference.md) and
[`phone-maps`](../profiles/phone-maps.md), whose software is small and whose
data is below. Several of those footprints say "not yet measured" for the
apt part; this page says the same.

### The whole catalog, as one machine measured it

The field laptop has the whole catalog installed. On 2026-10-03 it held:

| Where | Size | Kind and source |
|---|---|---|
| The operating system and everything apt installed | 32.9 GB | Quoted, as above |
| Installed trees and offline data, `/usr/local/share/hammunition` | 14 GB, including the offline-map data for several regions | Measured on the field laptop |
| Per-user data, `~/.local/share/hammunition` | 1.3 GB | Measured on the field laptop |
| Build cache, `~/.cache/hammunition/build` | 6.1 GB | Measured on the field laptop |
| apt's package archive, `/var/cache/apt/archives` | 1.1 GB | Measured on the field laptop |
| **Total** | **about 55 GB** | The sum of the five rows |

This is where the recommended tier's 55 GB comes from. It is one machine,
with one set of map regions, so use it as a scale and not as a promise.

### Two things you can get back

- **The build cache.** Source and git builds compile under
  `~/.cache/hammunition/build`. Once a unit is built and installed, the tree
  is only there to save time on a rebuild. On the field laptop it was
  6.1 GB; `digital-modes` alone leaves about 0.9 GB. Delete it when you need
  the space, and the next build starts again from the pinned source. Do not
  delete it while an install is running.
- **apt's archive.** `sudo apt clean` clears the 1.1 GB the field laptop
  holds.

### Offline data

Data units are fetched and checked against a size and digest recorded in
the catalog, so the plan prints their sizes. Each is chosen with
`hammunition station set`; nothing below downloads until you choose it.
The guides carry the detail and the figures' own sources.

| Layer | Size | Kind and source |
|---|---|---|
| Map regions (OpenStreetMap extracts) | One US state from about 20 MB (District of Columbia) to 1.3 GB (California); a country-sized region is several GB (6.1 GB measured) | Measured, [Offline navigation](../guides/offline-navigation.md) |
| What a region becomes on disk | Navit map about 0.9 times the download; Garmin map about 0.85 times; vector-tile map about 0.91 times; routing files about 0.2 times; phone map about 0.78 times plus a POI file about 0.21 times | Measured on one to three regions each, [the `navigation` profile](../profiles/navigation.md) |
| Scratch while a region converts | About two to six times the download, released afterward | Measured on some conversions, allowed for in others (the guide says which) |
| Country borders, the browser map kit | 13.3 MB and about 45 MB installed | Measured |
| Terrain (Copernicus elevation) | About 39 MB a tile and tens to hundreds of tiles a region: over 90 tiles, about 3.6 GB, for the largest contiguous US states; 449 tiles, about 17.5 GB, for Alaska | Pinned tile list, measured, [Offline navigation](../guides/offline-navigation.md) |
| US Topo sheets | About 8 MB a sheet, twice over once warped for QMapShack: Delaware about 220 MB, Vermont about 1.6 GB, Virginia about 6 GB | Measured from USGS's index on 2026-09-29 |
| US Topo for a handful of states | About 55 GB | Quoted from the bench; not recorded in the guides |
| Forest Service FSTopo sheets (by name only) | About 21 MB a sheet | Measured |
| 3DEP elevation (only with `--dem-source 3dep`) | About 480 MB a tile, ten times Copernicus | Measured |
| CoMaps (the application, built from source) | About 11 GB of build tree, 123 MB installed with its World maps; a US state is tens to a few hundred MB, all of the US 15.7 GB | Measured by hand; the engine's shallow fetch is smaller and not measured |
| The whole navigation plan for several regions | 111 GB | Quoted from the bench |
| Kiwix books, small | Simple English Wiktionary 26.5 MB, Amateur Radio Stack Exchange 75.9 MB, WikiMed introductions 163 MB | Pinned from Kiwix's metadata, 2026-09-29, [Offline reference](../guides/offline-reference.md) |
| Kiwix books, medium | WikEM 347 MB, Wikivoyage 272 MB, Appropedia 582 MB, WikiMed 862 MB, Simple English Wikipedia 1.09 GB, WikiMed with pictures 2.22 GB, iFixit 3.57 GB, Army Publishing Directorate 8.23 GB | Pinned, same page |
| Kiwix books, large | English Wikipedia introductions only 14.4 GB, no pictures 52.7 GB, with pictures 127 GB | Pinned, same page |
| Dictionaries, readers, ICS forms | About 32 MB, 11.4 MB for kiwix-tools, 8 MB for the forms | Measured |

Two things about those numbers. A Kiwix book is counted twice while it
installs, so keep room for the file and a copy. And a map region's cost is
the region you choose: a one-state station and a whole-country station are
different machines. Your plan prints the sizes of yours.

## Choosing a tier

**Minimum.** `station` and one mode profile. `digital-modes` is the big one
at about 1.2 GB with 0.9 GB of build cache; `station` with `sdr` is about
1.6 GB. Allow 5 GB so the cache and a kernel update do not surprise you.

**Recommended.** All the 1.0 profiles, `navigation` for a few regions, and a
few small Kiwix books. The field laptop's 55 GB is the scale. A 256 GB SSD
leaves room for more regions, a second set of builds and the scratch a
conversion needs.

**Large.** Official topo sheets for several states (about 55 GB quoted), the
whole navigation plan (111 GB quoted), full English Wikipedia (52.7 to
127 GB), terrain for large states. Added to the recommended tier those come
to about 220 to 300 GB, which is why we suggest 512 GB. If you keep a
[LAN mirror](../guides/lan-mirror.md), the big files live on that machine
and the laptop only needs the working set.

## What was not measured

- A bare install of any supported distribution, and so the true size of the
  base operating system apart from our software.
- The apt part of the `navigation`, `phone-maps` and `reference` profiles,
  and the web-engine part of kiwix and goldendict-ng.
- The development packages three source builds add, taken together.
- The 32.9 GB, 55 GB and 111 GB figures were quoted by the maintainer and are
  not in the bench pages. When they are, this page should point at the
  record.

Back: [installing the engine](install.md). Next: [your first
profile](first-profile.md), which has you read the plan before you install
anything.
