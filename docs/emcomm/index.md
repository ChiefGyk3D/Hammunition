<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# EMCOMM and field operation

Hammunition is being developed into a field kit for emergency communications
alongside its other jobs. This section is the one place that says how to
**prepare before** a deployment and what to do **when the internet is gone**.
It collects what the other guides already describe, in the order you will need
it, and links to the guide that owns each procedure. It invents no command; a
step that has not been run on real hardware says so.

## Three kinds of "offline"

"Offline" does not mean "needs nothing". Keep three things apart, because
each fails separately and a field plan has to cover each one:

| | What it is | Examples here | What loses it |
|---|---|---|---|
| **Internet** | Your connection to the rest of the world | `apt`, map and book downloads, Winlink's telnet gateway, Hill's fetched panels | Storm, outage, remote site |
| **Local network** | Machines you control, linked without the internet | A [Bunker](../suite/bunker.md) on a NAS, an SSH forward, a phone reading the hotspot's web server | A switch, a router, power |
| **Radio link** | Your own RF path | Packet to a Winlink gateway, FT8, APRS, mesh | Antenna, band conditions, battery, a radio, a sound interface |

A tool that "works offline" still needs its **hardware** (a GPS with a fix, a
radio, a sound interface) and its **local services** (gpsd, the GPS tether,
`hammunition reference serve` on 127.0.0.1). Each [application
page](../packages/index.md) has an "Offline use" section that says which of
the three it needs; where it says *not yet documented*, assume nothing.

## The pages

1. [Preparation checklist](preparation-checklist.md): what to do and verify
   before you leave, in order.
2. [Offline data and its limits](offline-data.md): maps, terrain, reference
   books, forms, repeater and infrastructure layers: coverage, source, date,
   how to update, and what each does **not** tell you.
3. [Communications workflows](communications.md): rig control, packet,
   Winlink, APRS, digital modes, mesh: what each needs and what has been
   exercised.
4. [Backup and recovery](backup-and-recovery.md): what is worth saving, where
   it lives, how to put it back.
5. [Troubleshooting with no internet](no-internet.md): by symptom.
6. [Quick reference](quick-reference.md): the essential commands on one page.

Also: [Offline navigation](../guides/offline-navigation.md) and [Offline
reference](../guides/offline-reference.md) are the full guides;
[Operating at a conference](../guides/conference-operating.md) is a worked
example of a deployment; the [offline documentation
bundle](../offline/index.md) is this documentation without the internet.

## What is implemented, what is not

| Capability | State |
|---|---|
| Offline maps in Navit and QMapShack, GPS position, address search | Implemented. Not yet run end to end on the field laptop; the guide's *What has not been measured yet* lists the gaps |
| Browser map with your position, GraphHopper routes | Implemented, not yet measured on the bench |
| Repeater layers from your own exports and open lists | Implemented |
| Infrastructure layers (medical, responders, supply, shelter candidates, transport, power, telecom, water) | Implemented from OpenStreetMap; drawing in QMapShack and Navit not yet measured |
| Offline Wikipedia, dictionaries, FEMA ICS forms | Implemented |
| Packet, Winlink (Pat), ARDOP, Mercury, FreeDATA | Packaged and installable. Pat carrying a message peer to peer with Mercury was measured without a radio; **nothing has been exercised over the air from the field laptop** |
| LAN mirror (Bunker) | Experimental: the Bunker has never run on a NAS |
| Mesh (Meshtastic, Reticulum) | Packaged; no LoRa link has been run |
| Live shelter or facility status | **Not provided and not possible offline**: see [limits](offline-data.md#what-a-mapped-place-does-not-tell-you) |

The authoritative record of what has run on real hardware is the
[bench record](../reference/bench-verification-5430.md).
