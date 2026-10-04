<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# EMCOMM preparation and field use

This page is the plan: what to do before a deployment, what you will have with
no internet, and what has and has not been measured. It links the guides that
own each procedure and does not repeat them. Examples use the placeholders
`N0CALL` and `FN31pr`.

Hammunition is a software station, **not** a certified emergency system. It is
for an operator who holds a licence and is part of a served-agency plan.

## Three kinds of "offline"

Keep these apart; most field surprises come from mixing them.

| | What it is | Examples here | Lost when |
|---|---|---|---|
| **Internet** | The wider network | Downloading maps, books, the Winlink gateway list; PSK Reporter; Pat telnet | The uplink is gone |
| **Local network** | This machine, or a LAN you run | `hammunition reference serve` on 127.0.0.1:8480; the GPS tether on 127.0.0.1; a [Bunker](../suite.md) on a NAS | The machine or the router is off |
| **Radio** | A link you make with a radio | Winlink by packet or HF, APRS, Meshtastic, Reticulum | No radio, interface, gateway or path |

"Works offline" on a page means: works with no internet **once installed and
prepared**. It does not mean without its radio, GPS or local service. The
position comes from a GPS receiver, not the internet, but only if it is
attached, not parked, and has a fix.

## Status words

| Word | Means |
|---|---|
| **Implemented** | The code and manifest exist and tests pass. Not a claim that it ran on hardware |
| **Measured** | A [bench](../reference/bench-verification-5430.md) or VM campaign page records it running |
| **Built, not yet measured** | Written, never run where it matters |
| **Planned** | Not written |
| **Unverified** | Fetched from a source that publishes no checksum |

## 1. Before the deployment

### Online, weeks ahead

Commands, in order, are in [Before a deployment](../getting-started/before-deployment.md).
In short:

- [ ] `hammunition doctor`, then set your station values (`station set`).
- [ ] Install the profiles you will use, plan first (`--dry-run`), then `hardware apply`.
- [ ] Choose map regions covering the whole route, then `install navigation`.
- [ ] Choose reference books; `install kiwix-library ics-forms`.
- [ ] Build the infrastructure and repeater layers (after the regions).
- [ ] Register Pat over the internet and fetch the gateway list.
- [ ] Download these documents ([section 7](../getting-started/before-deployment.md#7-this-documentation)) and keep a copy on a second device and on paper.
- [ ] If you run a Bunker, point the laptop at it and keep a verified copy: [LAN mirror](lan-mirror.md).

### A few days ahead

- [ ] `hammunition update` (works offline): anything behind the catalog's pins?
- [ ] Update, then re-run the layer imports if the regions changed.
- [ ] Charge everything; test cables and the sound interface.
- [ ] Write down the preparation date on the paper plan, the gateway list, frequencies and your agency's contacts.

### The rehearsal, with networking off

Do this once at home. It proves what you have, not what a site will have.

```sh
nmcli networking off              # NetworkManager machines; other systems differ
hammunition doctor
hammunition status
hammunition reference serve       # open http://127.0.0.1:8480/ ; Ctrl-C to stop
hammunition maps navit            # or open QMapShack: maps and the position
nmcli networking on
```

Check: the books, forms and map open; the GPS has a fix in `cgps`; the clock
holds ([GPS time](gps-time.md)); a rig answers; a test Winlink message works
by whatever path you will use. **Not measured:** this whole sequence as one
rehearsal. The pieces are in the guides linked below.

### On arrival

- [ ] `hammunition hardware list` shows what is attached; `hammunition hardware wake NAME` for a parked device ([Tray controls](tray-controls.md)).
- [ ] The GPS has a fix; the clock is right (FT8 stops decoding at about a second off).
- [ ] Rig control up ([Rig control](rig-control.md)); audio levels set ([Radio audio](audio-routing.md)).

## 2. The data, and its limits

Every layer states a source and, in its name, a date. Using it needs no internet;
refreshing it does.

| Dataset | Source | Coverage | Update | Guide |
|---|---|---|---|---|
| Street maps (`osm-regions`, `osm-navit`) | OpenStreetMap through Geofabrik | Only the regions you chose | `hammunition update`, then reinstall | [Offline navigation](offline-navigation.md) |
| Trail and terrain maps, routing, browser map | Built here from the same extracts; Copernicus elevation | Your regions | Reinstall | same |
| US topo sheets | USGS, Forest Service | Within `topo_radius_km` of your grid square | Reinstall | same |
| Medical, responders, supply, shelter candidates, transport, power, telecom, water | OpenStreetMap, from the installed extracts | Your regions | `maps infra import --from-osm` | same |
| Airports, power plants | FAA NASR, EIA, WRI | US, US and world | Reinstall after the pin moves | same |
| Towers, Weather Radio | FCC, NOAA, fetched on request | Your regions | Run again; **unverified** | same |
| Repeaters | Your own export, Open Repeater, hearham, ETCC, Brandmeister, OSM | Varies | Import again | same |
| Books, dictionaries, ICS forms | Kiwix, FEMA | What you chose | `update --upstream` online | [Offline reference](offline-reference.md) |

Dates, counts and licences are printed in each plan and are not repeated here.
`hammunition update` shows installed versus the catalog's pins and never fetches.

> **A mapped shelter, hospital, repeater, substation or transmitter does not
> establish that it exists, is open, has power, has capacity or is the one your
> agency uses.** The shelter layer says *candidate, not a designated shelter*.
> OpenStreetMap is volunteer-mapped and as old as the extract. Repeater
> positions are approximate and machines go off the air. Confirm by radio,
> telephone or the emergency manager.

## 3. Communications

| Workflow | Needs, radio | Needs, internet or LAN | Guide | Exercised |
|---|---|---|---|---|
| Rig control | CAT radio or PTT interface | None | [Rig control](rig-control.md) | Built, not yet measured on a bench |
| Radio audio | Sound interface | None | [Radio audio](audio-routing.md) | Guide only |
| Winlink by packet (Direwolf, Pat) | Radio, interface, a gateway in range | Internet only to register and fetch the gateway list | [Packet and Winlink](packet-winlink.md) | Installed in VMs; **no over-the-air message from the field laptop** |
| Winlink over telnet | None | Internet | same | Pat's documented first test |
| Winlink HF (ardopcf, Mercury) | HF radio | as above | same | Two Mercury instances passed a message with no radio (2026-09-30); not over the air |
| Packet BBS, LinBPQ | Radio, TNC or Direwolf | None | same | Packaged only |
| APRS | VHF radio | Internet only for an igate | [APRS](aprs.md) | Guide |
| FT8, JS8 | Radio, interface, correct clock | Spots need internet | [Digital modes](digital-modes.md) | Guide |
| Mesh: Meshtastic, Reticulum | LoRa nodes or RNode | None | [Mesh and Reticulum](mesh-and-reticulum.md) | Two containers exchanged an LXMF message; **no LoRa link run** |
| Time from GPS | A receiver with a fix | None | [GPS time](gps-time.md) | Built; bench owed |

Notes: Pat's first connection must be over the internet. The packet core does
not need the kernel's AX.25 ([kernel AX.25](../reference/kernel-ax25.md)).
Nothing transmits by itself; transmitting is your decision under your licence.
FEMA's 39 ICS PDFs are installed by `ics-forms` and listed on the
`hammunition reference serve` page; the ICS 309 log is not among them, so keep a
paper one.

## 4. Position and navigation

[Offline navigation](offline-navigation.md) owns this. The path is: a GPS
receiver, gpsd, then the [GPS Tether](../suite.md#hammunition-gps-tether), then
QMapShack, Navit, CoMaps or the browser map at `hammunition reference serve`.
No fix means no position, whatever the maps hold. Parking the GPS from the tray
([Tray controls](tray-controls.md)) switches it off. **Not measured:** the tether
as a service after a reboot, and QMapShack drawing the infrastructure layers.

## 5. Saving and recovering your configuration

Hammunition has **no backup or restore command**, and this procedure has not
been run end to end. Software and downloaded data come back by reinstalling;
what you back up is yours.

| Save | Where | Sensitive |
|---|---|---|
| Station values | `~/.config/hammunition/station.yml` (0600) | Yes: callsign and location |
| Repeater and infrastructure layers | `~/.local/share/hammunition/overlays/` | Yes; personal-use terms, keep to your machines |
| Pat's configuration and mailbox | `~/.config/pat/` | Yes: the password |
| Configuration the engine wrote | `/etc/direwolf.conf`, `/etc/bpq32.cfg`, `/etc/hammunition-hill/config.toml` | Contains your callsign |
| Mesh identities | `~/.reticulum`, `~/.nomadnetwork`, `~/.lxmd`, `~/.rnsh` (an identity cannot be recreated) | Yes; archive command in [Mesh and Reticulum](mesh-and-reticulum.md) |
| Your logs | wherever your logging program keeps them | Yes |

Not worth saving: `~/.cache/hammunition/` and `/usr/local/share/hammunition/`.

To recover on a fresh machine: install the engine ([Installation](../getting-started/installation.md)),
restore the files above into the same paths, `chmod 600` the station file,
`hammunition station show`, re-run the installs (plan first), then
`hammunition hardware apply`, and re-fetch the data (from a Bunker if you
have one). An existing configuration file is copied to a `.hammunition-backup`
before an install rewrites it. Encrypt an archive that leaves your hands.

## 6. Troubleshooting without the internet

| Symptom | Likely cause | What to try |
|---|---|---|
| `install` says it could not check for newer data | No network | Expected: regions already installed are kept as they are. A region never installed cannot be fetched; the plan refuses and names it |
| A pinned book or map will not download | The publisher moved or expired it | Needs the internet, or a mirror that has it; not fixable in the field |
| No position | GPS parked, no fix, gpsd stopped, or tether not running | `hammunition hardware state`, `cgps`, `systemctl --user status hammunition-gps-tether.service` |
| FT8 decodes nothing | Clock off | [GPS time](gps-time.md) |
| A page will not open | Local server not running | Start `hammunition reference serve`; it listens on 127.0.0.1 only |
| Something changed and you do not know what | | `hammunition logs --last`; `hammunition transactions --last 10` |
| Hardware not found | Permissions or a parked device | `hammunition hardware list`, `hammunition hardware apply` |

More: [Troubleshooting](../troubleshooting/index.md).

## 7. Quick reference

```sh
hammunition doctor                    hammunition status
hammunition update                    hammunition hardware list
hammunition hardware state            hammunition hardware wake NAME
hammunition reference serve           hammunition maps navit
hammunition maps gps-tether           pat-winlink http
hammunition logs --last               hammunition transactions --last 10
```

## 8. What is not measured

Stated here so no one reads it as a promise.

- The full rehearsal sequence above, as one run, and a restore from a backup.
- Rig control on a bench (D-073: proposed).
- Packet or Winlink over the air from the field laptop; HF Winlink over the air.
- Any LoRa mesh link; only two containers over a LAN.
- The GPS tether as a service across a reboot; GPS time on the bench (D-058).
- The Tray on the Qt desktops; the Bunker on a NAS; the Console through a real install.
- QMapShack and Navit drawing the infrastructure layers, and real `fetch-fcc-asr` and `fetch-nwr`.
- The accuracy and currency of any mapped place.
