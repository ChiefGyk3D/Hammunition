<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# APRS

The Automatic Packet Reporting System: short position reports, weather and
text messages sent on one shared VHF frequency and repeated by digipeaters
across a region. On a map it shows who is on the air around you, with no
internet involved. APRS-IS carries the same packets over the internet for
sites like aprs.fi.

```text
 radio --audio--> Direwolf (soundcard modem) --AGWPE :8000--> Xastir / YAAC
                        |
                        +--> APRS-IS (internet, optional): receive-only or gating
```

## Programs the catalog carries

<!-- BEGIN generated: programs -->

- [a2d](../packages/a2d.md): Bridges APRS messages to DAPNET pagers (in [`packet`](../profiles/packet.md))
- [aprsdigi](../packages/aprsdigi.md): APRS digipeater — repeats packets so they reach further than one hop (in [`packet`](../profiles/packet.md))
- [aprx](../packages/aprx.md): APRS digipeater and internet gateway, small enough for a Pi (in [`packet`](../profiles/packet.md))
- [direwolf](../packages/direwolf.md): Software TNC — turns a sound card into an APRS and packet modem (in [`packet`](../profiles/packet.md))
- [qtbpqaprs](../packages/qtbpqaprs.md): G8BPQ's Qt APRS client, the messaging-focused one (by name only)
- [xastir](../packages/xastir.md): APRS client with real maps — see and be seen on the packet network (in [`packet`](../profiles/packet.md))
- [yaac](../packages/yaac.md): Yet Another APRS Client — the deep, portable Java one (by name only)

<!-- END generated: programs -->

[Direwolf](../packages/direwolf.md) is the modem and the clients talk to it;
the same Direwolf serves [Packet and Winlink](../guides/packet-winlink.md).

## Hardware

APRS needs no catalogued device of its own. It needs a VHF transceiver with an
audio path to the computer (rig, sound interface and cable), or a hardware
TNC. [Rig control](../guides/rig-control.md) and [Radio
audio](../guides/audio-routing.md) set those up. APRS-IS needs only a network.

## Install

```sh
hammunition install station packet --dry-run
hammunition install station packet
```

`packet` carries Direwolf, Xastir, the digipeaters and the rest of the packet
stack; YAAC and QtBPQAPRS are by name only (`hammunition install yaac`).
`aprsdigi` needs the kernel's AX.25 stack, which some kernels lack; the plan
defers it by name where it is absent (D-041), and the userspace programs above
do not need it.

## First useful task: receive

Set up Direwolf as in [Packet and Winlink, step
1](../guides/packet-winlink.md#1-direwolf-the-modem), tune the radio to the
APRS frequency for your region (144.390 MHz in North America, 144.800 MHz in
most of Europe), and watch packets decode. Then start Xastir, add a *Networked
AGWPE* interface at `localhost` port `8000`, and the stations appear on the
map. Receiving needs no licence; transmitting does. [APRS](../guides/aprs.md)
has each dialog.

## Beaconing, digipeating and gating are decisions

Each puts traffic on a shared channel under your callsign, so none is on by
default. Receive-only gating to APRS-IS helps coverage and is harmless;
beaconing, digipeating and transmit gating are covered in [the
guide](../guides/aprs.md#beaconing-digipeating-and-gating-are-decisions).

## What stations heard becomes a map layer

Direwolf's log can feed the repeater map. Start it with `-l ~/direwolf-logs`,
then:

```sh
hammunition maps repeaters import --from-direwolf-log ~/direwolf-logs/*.log
```

This writes a *heard off the air* layer from the APRS repeater objects local
digipeaters send. It fetches nothing, uses no login, stays apart from the
directory layers (it is evidence, not a listing), and still shows an object
that was later withdrawn, because the log does not say. See [offline
navigation](../guides/offline-navigation.md).

## Offline, LAN and radio

| Part | With no internet? |
|---|---|
| Receiving and decoding on RF, Xastir and YAAC showing what Direwolf hears | Yes: it is all radio and local. |
| Transmitting beacons and messages over RF | Yes (licence required). |
| APRS-IS, an igate, aprs.fi | No: it is the internet side. |
| A map under the client | Online tile maps need the network; install offline maps ahead of time. |

## Where the detail lives

[APRS](../guides/aprs.md), [Packet and Winlink](../guides/packet-winlink.md),
[Station settings](../guides/station-settings.md) (where each program wants
your callsign), the [package pages](../packages/index.md) above.

## What was measured, and what was not

Measured: Direwolf's example lines were read from its 1.7 release and
`callpass` was run from Xastir 2.2.0 on Ubuntu 24.04 (2026-09-30); Xastir's
*AX.25 TNC* interface type fails on Linux 7.1 with no kernel stack, while
*Networked AGWPE* and *Serial KISS TNC* need none (recorded in its manifest).

Not measured:

- **APRS on air from the field laptop.** It is not in the [bench
  record](../reference/bench-verification-5430.md).
- **The client dialogs.** They follow each program's own documentation.
- **`--from-direwolf-log` on the field laptop's own Direwolf log.** The
  importer's column header was read from Direwolf 1.8.1's log format
  ([CLI reference](../reference/cli.md)); no import of a log from this
  station is in the bench record.
- **`aprx`, `aprsdigi` and `qtbpqaprs` as a running station**: none is in the
  bench record.
