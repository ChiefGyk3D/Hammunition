<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Activity hubs

One page per thing a person sets out to do, so the answer to "what do I
install, with what hardware, and what do I do first?" sits in one place. Each
hub says what the activity is, which programs and which hardware the catalog
carries for it, how to install them, a first useful task, what needs a
network and what does not, and what was measured and what was not. The
detail stays in the guides and package pages each hub links to; a hub does
not copy it.

The lists of programs and hardware on every hub are generated from the
catalog (`scripts/gen_activity_hubs.py`), so they cannot drift from it. The
prose around them is written by hand.

| Hub | For |
|---|---|
| [GPS, position and time](gps-time.md) | A receiver, gpsd, your position on a map, and the clock when the network is gone |
| [APRS](aprs.md) | Position reports, messages and weather over VHF, with Direwolf and a map client |
| [Meshtastic](meshtastic.md) | A ready-made LoRa text mesh, from the desktop |
| [Reticulum](reticulum.md) | Encrypted networking over LoRa, packet, cable or a local network |
| [MeshCore](meshcore.md) | A stub: not yet carried, and what the route to it is |

Every program also has its own page in the [package
reference](../packages/index.md), and [Applications by
activity](../applications.md) lists the whole catalog the way the desktop menu
is laid out.
