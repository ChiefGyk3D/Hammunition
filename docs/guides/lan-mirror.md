<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# A LAN mirror for offline data

Map regions, elevation tiles and the other offline data units are public
data, and a laptop rebuilt or given a new region downloads them again from
their publishers: Geofabrik, the Copernicus bucket, Natural Earth,
country-files.com. A US state's terrain alone can be several gigabytes. If
a machine on your own network already holds a verified copy, the laptop can
take it from there instead, in seconds rather than hours, and with the
same checks it would have made against the publisher (**D-070**).

The server side is a separate project,
[Hammunition Bunker](https://github.com/ChiefGyk3D/hammunition-bunker): a
container for a NAS that asks the engine which artifacts to keep, keeps
them fresh on a schedule, and serves them on the LAN. This page is the
engine side: what to set, what the plan will say, and what is and is not
trusted.

## Point the engine at the mirror

```
hammunition station set --mirror http://bunker.lan:8080/
hammunition station show
```

From then on, `hammunition install` asks the mirror first for every data
download — each `data` unit's files, each map region, each terrain tile,
each of CoMaps' maps (`comaps-maps/<version>/<id>.mwm`, D-069) —
at `<mirror>/<unit>/<name>`, for example
`http://bunker.lan:8080/osm-regions/north-america/us/vermont`. Anything else
the install fetches (a source tarball, a prebuilt binary) still comes from
its publisher.

To stop using it for one run, `hammunition install --no-mirror ...`. To
remove it, `hammunition station set --clear-mirror`.

**A mirror does not make an install work offline.** The plan is still
made against the publishers: a region's dated file and its MD5 are asked of
Geofabrik, an unpinned tile's size and checksum of the Copernicus bucket,
and every region and tile to be downloaded is checked for being reachable
there before anything runs. With the internet down, the plan refuses by
name, mirror or not, and what is already installed stays installed. The mirror saves the download,
not the question.

## A mirror URL is a LAN address

**A mirror is a machine on your own network, never reachable from the
internet.** The Bunker serves without authentication and over plain HTTP,
and that is fine only because nothing it sends is trusted: every byte is
checked against a digest the engine already holds. Do not forward its port,
do not publish it, and do not point the engine at somebody else's.
The engine cannot check this for you: a hostname does not say whether it is
private.

A mirror URL may not carry a user name or password: the station file holds
no credentials. `http` and `https` both work.

## What the plan says

With a mirror set, the plan opens its data sections with

```
Data mirror (D-070):
  Each data download below (offline data, map regions, terrain tiles) is asked of the
  LAN mirror http://bunker.lan:8080/ first, ...
```

and every data download step names both places in order:

```
Fetch map region north-america/us/vermont (260101, ...) — sha256, pinned by Hammunition — the LAN mirror first, then the publisher; the sha256 is checked either way
  $ [fetch] http://bunker.lan:8080/osm-regions/north-america/us/vermont, then https://download.geofabrik.de/north-america/us/vermont-260101.osm.pbf (...)
```

`--dry-run` prints the same, and `install --dry-run --json` carries it as
`install.mirror` and each step's `sources`.

## What is trusted, and what happens when the mirror is wrong

Nothing from the mirror is trusted. A download from it is checked against
the same digest the publisher's would be: the sha256 Hammunition pins, or
the publisher's own MD5 for an unpinned region or tile, read from the
publisher while the plan is made. If the mirror is switched off, does not
have the file, sends too much, sends the wrong size or sends the wrong
bytes, the download is discarded and the publisher is asked instead. A
mirror that does not answer at all is not asked again in that run, so a
switched-off NAS costs one ten-second wait, not one per tile.

## Afterwards

The transaction log records where each download actually came from:
`source` (`mirror`, `publisher` or `cache`), `fetched_from`, and
`mirror_failure` when the mirror was passed over
(`docs/reference/transaction-log.md`).

## What the Bunker asks the engine

`hammunition artifacts --json` lists every artifact the engine would fetch
for a selection given on the command line, with no station and nothing
installed read; it is how the Bunker learns what to keep.
`docs/reference/cli.md` describes the command and
`docs/reference/json-interface.md` its `artifacts` document.
