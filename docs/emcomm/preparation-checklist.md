<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Pre-deployment preparation checklist

Do the first half **with an internet connection, weeks ahead**, the second
half in the **days before**, and rehearse once with the network switched off.
Tick as you go. Every command is described in the page it links to; use your
own callsign and grid square where examples show `N0CALL` and `FN31pr`.

## A. With internet, as early as you can

- [ ] **The machine is healthy.** `hammunition doctor` (read-only). Fix every *warn* it prints.
- [ ] **Station values set.** `hammunition station set --callsign N0CALL --grid-square FN31pr`, then `hammunition station show`. See [station settings](../guides/station-settings.md). A missing value defers one file; it does not stop an install, but a deferred file is a program that is not configured when you need it.
- [ ] **Disk is enough.** Check [how much disk you need](../getting-started/disk-space.md); the plan prints each size and refuses before fetching if a disk is short.
- [ ] **Core software installed.** Plan first, then install: `hammunition install station --dry-run`, then without `--dry-run`. Add the profiles your mission uses, for example `navigation`, `reference`, `packet`, `digital-modes` ([profiles](../profiles/index.md)).
- [ ] **Hardware rules applied.** `hammunition hardware apply --dry-run`, read it, then `hammunition hardware apply` ([power control](../hardware/power-control.md)). Log out and in if it added you to a group.
- [ ] **Map regions chosen for every place you may go**, including the route: `hammunition maps regions NAME`, then `hammunition station set --map-regions A,B`. The list *replaces* the previous one. Then `hammunition install navigation` ([Offline navigation](../guides/offline-navigation.md)).
- [ ] **Reference books and forms.** `hammunition reference books`, `hammunition station set --reference-books ID,ID`, `hammunition install kiwix-library ics-forms` ([Offline reference](../guides/offline-reference.md)).
- [ ] **Infrastructure and repeater layers built.** `hammunition maps infra import --from-osm`; your own repeater export through `hammunition maps repeaters import FILE` ([data and limits](offline-data.md)). Note each layer's date.
- [ ] **Winlink registered over the internet** (the first connection must be): `pat-winlink http`, telnet alias ([Packet and Winlink](../guides/packet-winlink.md)). Download the gateway list: `pat-winlink rmslist --mode packet --sort-distance`, and write down the gateways you can reach.
- [ ] **A copy of these docs on the machine and a spare.** [Offline documentation](../offline/index.md).
- [ ] **Configuration saved.** [Backup and recovery](backup-and-recovery.md).
- [ ] **Optional: a Bunker** holding the data, if several machines are being prepared ([LAN mirror](../guides/lan-mirror.md)). Experimental.

## B. In the days before

- [ ] **Refresh.** `hammunition update` (offline, reports what is behind the pin); `hammunition install osm-regions osm-navit` fetches newer maps if regions are behind.
- [ ] **GPS has a fix outdoors.** `cgps` or `xgps` shows one. If you park the receiver, wake it: `hammunition hardware wake NAME`.
- [ ] **Time is right with no network.** `hammunition time`; on ntpsec targets see [GPS time](../guides/gps-time.md). FT8 stops decoding once the clock is off by about a second.
- [ ] **Rig control works.** [Rig control](../guides/rig-control.md); `hammunition doctor` checks the rig service read-only and never keys the transmitter.
- [ ] **Audio levels set** for each digital mode ([Radio audio](../guides/audio-routing.md)). Transmit audio level is the usual cause of a station that hears everyone and is heard by nobody.
- [ ] **Packages and a spare**: batteries, cables, a printed copy of [the quick reference](quick-reference.md) and your ICS forms.

## C. The rehearsal, with networking off

This is the test worth doing. Offline is a property you have to demonstrate.

1. Switch networking off: `nmcli networking off`.
2. Start `navit-offline`. Confirm the map, your position and a route.
3. Run `hammunition reference serve` and open <http://127.0.0.1:8480/>: a book, a form, and `/map/` if installed.
4. Open the offline documentation from disk.
5. Start Direwolf and Pat locally; confirm audio and the radio keys on a dummy load or a test frequency.
6. Switch networking back on: `nmcli networking on`.

Write down what failed and fix it while you still have internet.

## D. On site

- [ ] Position and clock verified before first transmit.
- [ ] Record what you set and when (a paper log is the backup of last resort).
- [ ] Remember a mapped hospital, shelter or repeater is **not** a statement that it is open or working: confirm by radio or phone.

## What this checklist does not prove

Items needing real hardware are marked in [Communications workflows](communications.md). In particular, an over-the-air Winlink message from the field laptop and a Bunker on a real NAS have not been exercised.
