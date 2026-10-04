<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Guides

One task each, from the start to something working. The [getting started
pages](../getting-started/index.md) install the engine and a first profile;
these pick up from there.

## Set up the station once

Everything else leans on these. Do them in this order the first time.

1. **[Rig control (CAT)](rig-control.md)** — one program owns the radio's
   serial port and every other program asks it. The single biggest cause of
   "it was working yesterday" is two programs fighting over that port.
2. **[Radio audio](audio-routing.md)** — the radio's audio into the computer
   and back, at the right level. Every digital mode needs it.
3. **[Time and position](time-and-gps.md)** — FT8 and its relatives need the
   clock within a second. With a network that is automatic; without one, a
   GPS keeps it. On a machine running ntpsec (Parrot's security edition),
   [GPS time on ntpsec](gps-time.md) is the route, with four modes you can
   switch.
4. **[Your callsign in each program](station-settings.md)** — what
   Hammunition writes for you from `hammunition station set`, and the settings
   dialog to visit in each program it does not write.

Then, when you want to switch things off and on:

- **[The tray's Controls panel](tray-controls.md)** — park the GPS or a modem
  you are not using, start and stop the services behind your position and
  your clock, and switch the machine's radios, from the tray or from
  `hammunition services`, and which of those asks for a password.

## Modes

- **[FT8 and the digital modes](digital-modes.md)** — WSJT-X, JS8Call and
  fldigi, to a first decode and a first contact.
- **[Packet and Winlink](packet-winlink.md)** — Direwolf as the modem, Pat for
  radio email, ARDOP on HF.
- **[APRS](aprs.md)** — Direwolf as the TNC, Xastir or YAAC on the map, and
  the decisions about digipeating and gating that affect other people.
- **[Mesh and Reticulum](mesh-and-reticulum.md)** — encrypted messaging with no
  infrastructure: two laptops on one network, then a LoRa RNode, a packet
  modem or the internet, with NomadNet, `rnsh` and the Meshtastic clients beside
  it.

## Receiving

- **[SDR first steps](sdr.md)** — an inexpensive dongle to broadcast FM, aircraft and
  433 MHz sensors in an evening.
- **[Satellites](satellite.md)** — passes, Doppler, and pictures from weather
  satellites.
- **[Propagation](propagation.md)** — when a band is open, and why.

## In the field

- **[Offline navigation](offline-navigation.md)** — maps, routing and terrain
  with no network at all.
- **[Offline reference](offline-reference.md)** — Wikipedia, WikiMed, a
  dictionary and the ICS forms on the laptop, on one local page.
- **[A LAN mirror for map and reference data](lan-mirror.md)** — keep a
  verified copy of the big downloads on a machine on your own network and take
  them from it.
- **[Operating at a conference](conference-operating.md)** — a portable
  station in a hotel full of other people's RF.
- **[Rayhunter](rayhunter.md)** — watching for cell-site simulators with EFF's
  tool.

## How these guides are written

- **Commands are copied from the tool, not remembered.** Where a guide quotes
  a default, a port or a file name, it was read from the installed program on
  the date the guide gives.
- **What was not measured says so.** A step that has not been run on real
  radio hardware by this project is marked *unmeasured*; it follows the
  program's own documentation, which each guide links.
- **Placeholders, never a real station.** Examples use the callsign `N0TST`
  or `N0CALL` and the grid square `FN31pr`. Put your own in their place.
- **Each program's own manual wins.** These pages get you to a working
  station; the program's documentation, linked from its [package
  page](../packages/index.md), is where its depth lives.
