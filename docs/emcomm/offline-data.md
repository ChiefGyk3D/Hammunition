<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Offline data and its limits

Hammunition can put maps, terrain, reference books, forms and point layers on
the laptop before you need them. This page says, for each one, **where it
comes from, what it covers, how old it is, how to update it, and what it
cannot tell you.** The procedures are in [Offline
navigation](../guides/offline-navigation.md) and [Offline
reference](../guides/offline-reference.md); this page is the summary a field
plan needs.

Downloading data is not downloading software and not downloading these
documents: data arrives through `hammunition install` of a *data unit*, with
its size and licence printed in the plan before anything is fetched
([offline documentation](../offline/index.md) covers the docs).

## The datasets

| Dataset | Unit or command | Source | Coverage | Date | Update |
|---|---|---|---|---|---|
| Street maps | `osm-regions`, `osm-navit` | OpenStreetMap, as Geofabrik extracts | Only the regions you chose with `station set --map-regions` | The extract's date: 1 January of this year by default (`--map-freshness monthly` or `latest` for newer) | `hammunition update`, then `hammunition install osm-regions osm-navit` |
| Trail and terrain maps, routing | `qmapshack`, `osm-garmin`, `brouter`, `brouter-segments`, `dem-copernicus` | Built on this machine from the same extracts; elevation from Copernicus GLO-30 (optionally USGS 3DEP) | The regions you chose | Date of the extract; elevation is a fixed model | Reinstall after updating regions |
| US official topo | `usgs-ustopo`, `usfs-fstopo`, `dem-3dep` | USGS US Topo, Forest Service FSTopo, USGS 3DEP | Sheets within `topo_radius_km` (100 when unset) of your grid square | As published when fetched | Reinstall; the plan prints the count and size |
| Browser map | `osm-pmtiles`, `vector-map-kit` | Built from your regions | Your regions | Same as the extract | Reinstall |
| Phone maps | `maps phone` | Copies the files built above | Your regions | Same | Run again |
| Medical, responders, supply, shelter candidates, transport, power, telecom, water layers | `hammunition maps infra import --from-osm` | OpenStreetMap, from the installed extracts | Inside your regions | The extract's date | `maps infra import --from-osm` again after updating regions |
| Airports and heliports (US) | `faa-nasr-airports`, `maps infra import --from-nasr` | FAA NASR | US | Renewed every 28 days upstream; pinned in the catalog | Reinstall after the catalog's pin moves |
| Power plants | `eia-860m`, `wri-power-plants` | EIA (US), WRI (outside the US) | US / worldwide | EIA monthly; WRI frozen in 2021 | Reinstall |
| Towers, Weather Radio | `maps infra fetch-fcc-asr`, `fetch-nwr` | FCC ASR, NOAA | Your regions | When you run it; **unverified** (no checksum published) | Run again |
| Repeaters | `maps repeaters import FILE`, `open-repeater` unit, `fetch-hearham`, `fetch-etcc`, `fetch-brandmeister` | Your own RepeaterBook export, Open Repeater (CC0), hearham, ETCC, Brandmeister, OSM, your APRS log | Depends on the source | Each layer's name carries its date and source | Export and import again; fetch commands on request |
| Encyclopaedia, Q&A, dictionaries | `kiwix-library`, `dictionaries` | Kiwix books you choose | The books you choose | Pinned dated files; Kiwix keeps only the two newest, so a pin can expire | `hammunition update --upstream` online |
| ICS forms | `ics-forms` | FEMA's 39 PDFs | US | Sha256 measured 2026-09-29 | Reinstall after a re-pin |

Sizes are in the plans and in [disk space](../getting-started/disk-space.md).
Licences: OpenStreetMap data is ODbL; each plan prints its data's licence and
the browser map draws its credits.

## What a mapped place does not tell you

> **A mapped shelter, hospital, fire station, airfield, substation or
> repeater does not establish that it exists today, is open, has power, has
> capacity or is the one your agency is using.** Confirm by radio, telephone
> or your emergency manager's announcement.

- **Shelters.** The layer is named *shelter candidates, not a designated
  shelter*: schools, community centres, town halls and places of worship, where
  shelters are often opened. Which one is open is announced, not mapped.
  OpenStreetMap's picnic and bus-stop shelters are deliberately left out. FEMA's
  live list of open shelters is not carried (it is useless offline outside an
  event).
- **Medical.** Hospitals, clinics, doctors and pharmacies as mappers tagged
  them. A hospital marked as having an emergency department says so in its
  description, but diversion, closure and capacity are live facts a map cannot
  hold.
- **Repeaters.** Positions are approximate, a way to find a machine to try, not
  directions to a site. Machines go off the air. hearham states no licence and
  warns against relying on its list for life-and-death operations. The
  ETCC, Brandmeister and hearham layers are fetched **unverified**.
- **Power and telecom.** Voltage and operator appear where mapped. A substation
  on the map may be dark.
- **Weather Radio.** The list drops the live on-air status; confirm a
  transmitter is on the air before relying on it. It is not an official NWS
  product.
- **Everything from OpenStreetMap** is volunteer-mapped and as old as the
  extract. Coverage and accuracy vary by region.
- **Accuracy of derived layers.** The counts quoted in the navigation guide
  were measured on two example states on 2026-10-01; your region will differ.
- **Not carried at all:** HIFLD Open (retired), OpenGridWorks, 911 boundaries,
  OpenFEMA areas, USGS National Structures. See the navigation guide's *Not
  carried, and why*.

## Knowing how old your data is

- `hammunition update` (offline) reports, per data unit, what is installed
  against the catalog's pin, and never prints your region names.
- Each repeater and infrastructure layer's **name and description carry its
  source, date and licence**.
- `hammunition transactions --last 10` lists when each install ran and
  `hammunition logs --last` the full output; the transaction log records where
  each download came from (`mirror`, `publisher` or `cache`).
- Write the date you prepared the machine on the paper copy of your plan.

## Updating, and what needs the internet

Updating always needs the internet or a [LAN mirror](../guides/lan-mirror.md);
using the data afterwards does not. If you run `hammunition install` with no
network, regions already installed are kept exactly as they are and the plan
says it could not check for newer ones; a region you added but never installed
cannot be fetched and the plan refuses, naming it, without changing anything.

## Not measured

QMapShack and Navit drawing the infrastructure layers, a real `fetch-fcc-asr`
and `fetch-nwr`, and the imports over a station's own regions are owed to the
bench. See *What has not been measured yet* in the navigation guide.
