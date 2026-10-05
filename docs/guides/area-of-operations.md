<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Load every area ahead, activate where you are

You may be sent to Ohio one day, Michigan the next, then flown down to Florida.
There will be no good network where you land, and there is far more data than
you want drawn at once. So the work is split in two (**D-082**):

- **At home, load everything ahead.** Every state and region on the roster that
  you might be sent to: its maps, its repeaters, its infrastructure.
- **On arrival, activate where you are.** One command makes that area the
  active one. The next day, another. **Nothing is deleted and nothing is
  downloaded again.**

This page is the walk through both. The procedures behind each step live in
[Offline navigation](offline-navigation.md) (sections 13, 18 and 19) and the plan
around it is [EMCOMM preparation and field use](emcomm-field.md). Examples use
the placeholders `N0CALL` and `FN31pr`, and Ohio, Michigan and Florida.

## Before you start

You need the engine installed and your station set
([Before a deployment](../getting-started/before-deployment.md)). Everything in
the first half needs the internet, so do it somewhere you have it.

An **area** is a US state code (`OH`) or a map region (`north-america/us/ohio`,
or its last word, `ohio`). A state and the region that is the same ground switch
together. Elsewhere in the world a RepeaterBook `state_id` such as `CA01` is the
state code.

## Part 1. At home: load every area

### 1. Map regions

Find the region paths, then name every region on the roster in one list. The
list replaces any earlier one, so give all of them:

```sh
hammunition maps regions ohio
hammunition maps regions michigan
hammunition maps regions florida
hammunition station set --map-regions north-america/us/ohio,north-america/us/michigan,north-america/us/florida
hammunition install navigation --dry-run
hammunition install navigation
```

The dry run prints every download with its size before anything happens. Each
region is a download and a build; a large state takes real time and real disk.
How much disk the whole roster needs depends on the regions, the terrain and
routing you keep and the topo sheets in range: read the sizes the plan prints,
and add them up for your roster before you start. Fewer and smaller regions are
the way to fit a small disk.

### 2. Repeaters, one layer per state

RepeaterBook's own export is for personal use, so Hammunition asks its API with
a token of yours and writes one layer per state. Install the client unit, then
give the token to the engine in either of two ways.

```sh
hammunition install repeaterbook-client --dry-run
hammunition install repeaterbook-client
```

- **The Secrets screen** in the [console](../getting-started/console.md#keys-for-downloads-that-need-one):
  it shows whether a source would answer, never the value.
- **The environment**: `export REPEATERBOOK=rbuapp_...` in the shell you fetch
  from, or Doppler, named once with
  `hammunition station set --doppler-project PROJECT --doppler-config CONFIG`.

Check where the engine would find it, without printing it:

```sh
hammunition secrets status
```

Then fetch each state:

```sh
hammunition maps repeaters fetch-repeaterbook --state OH
hammunition maps repeaters fetch-repeaterbook --state MI
hammunition maps repeaters fetch-repeaterbook --state FL
```

A state's fetch replaces only that state's layer. RepeaterBook answers at most
about 3,500 rows at once; when a state is that large the fetch says so, and
the route is the county form, merged into the state's layer:

```sh
hammunition maps repeaters fetch-repeaterbook --state FL --county Miami-Dade --county Broward
```

RepeaterBook data is personal-use: fetched for yourself, never put on a Bunker
or served to others. The open layers (`maps repeaters import --from-osm`,
`--from-open-repeater`) may be.

### 3. Infrastructure, one set per region

After the maps are installed, because it is filtered from them:

```sh
hammunition maps infra import --from-osm
```

It writes the medical, responders, supply, shelter-candidate, transport, power,
telecom and water layers once for **each** region you installed. The US federal
lists (`--from-nasr`, `--from-eia`) are clipped to each region the same way. Add
`--merged` only if you want one layer across every region, which belongs to no
area and is always drawn. See [Infrastructure and EMCOMM points](offline-navigation.md#18-infrastructure-and-emcomm-points).

### 4. Confirm what is loaded

```sh
hammunition maps areas
```

lists every state and region with files on this machine: its layers, their
sizes and dates, and whether each is active. Each area you meant to load should
be there with its map, its repeater layer and its infrastructure. A missing one
is a step above that did not finish. `hammunition maps areas --json` prints the
same as one document for programs.

Then try the switch once, at home, where a surprise costs nothing:

```sh
hammunition maps activate OH --dry-run
```

## Part 2. On arrival: activate where you are

```sh
hammunition maps activate OH
```

The next day:

```sh
hammunition maps activate MI
```

Two at once, everything again, or nothing:

```sh
hammunition maps activate OH MI
hammunition maps activate --all
hammunition maps activate --none
```

`--all` is also the state of a machine that has never used the switch. Layers
that belong to no area (your own imports, the open and ACMA sources, merged
infrastructure) stay registered whatever you pick; `maps areas` lists them as
*Always active*.

### What you see afterwards

| Where | What changes |
|---|---|
| QMapShack | Only the active areas' POI collections are listed. Close QMapShack before you switch, or run `hammunition maps qmapshack` to put the list back |
| Navit | `hammunition maps navit` opens with only the active regions' maps and layers |
| The browser map | Restart `hammunition reference serve`; it lists and serves only the active regions and layers |
| Hammunition Hill | The repeaters panel shows the active areas, with area chips to add or drop one for that browser session only; the map follows the chips. The chips never change the engine's setting |
| The console | Press `R` on a plan to run `maps activate`; the console has no area selector of its own yet (#322, #323). The Secrets screen is where the RepeaterBook token goes |

Hill needs an engine that has areas; an older one keeps every layer and shows no
chips.

## What was measured, and what was not

Stated so no one reads it as a promise.

- **Built and tested against synthetic layers:** the station value, the files
  each program is given, the infrastructure split per region, the `areas` and
  `--json` documents, the Hill chips against fixture data.
- **Not measured on hardware: QMapShack listing a POI collection through a
  link in the `poiPaths` directory.** `maps activate` points QMapShack at a
  directory of symbolic links to the active areas' `.poi` files
  (`overlays/active-poi`). If QMapShack will not follow them, the route
  recorded in **D-082** is to copy the active files there instead. The first
  bench run settles it.
- **Not measured:** Navit and the browser drawing the switched result, Hill
  against a real station's layers, and a switch on the field laptop.
- **Not run against the live API:** the RepeaterBook fetch, per state or per
  county. It was built from RepeaterBook's documentation and the client's source.
- **Not measured:** the disk a whole roster takes; it is stated by the plan, not
  predicted here.
- **Not a statement of fact:** a mapped repeater, shelter, hospital or substation
  does not establish that it exists, is open or has power. Confirm by radio or
  telephone.
