<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Communications workflows

What Hammunition can set up for talking to people when the internet is not
there, what each workflow needs, and **what has actually been exercised**. The
step-by-step procedures are in the guides linked from each row; this page does
not repeat them.

| Workflow | Needs (radio link) | Needs (internet / LAN) | Start here | Exercised? |
|---|---|---|---|---|
| **Rig control** (one shared `rigctld`, or flrig) | A radio with CAT, or a PTT-only interface | None | [Rig control](../guides/rig-control.md) | Built; bench owed (D-073 status: proposed) |
| **Radio audio** | A sound interface to the radio | None | [Radio audio](../guides/audio-routing.md) | Guide only |
| **Winlink by packet** (Direwolf + Pat) | Radio, sound interface, a gateway in range | Internet only to register and to fetch the gateway list beforehand | [Packet and Winlink](../guides/packet-winlink.md) | Packaged and installed in VMs; **no over-the-air message from the field laptop** |
| **Winlink over telnet** | None | Internet | same | Pat's telnet path is the documented first test |
| **Winlink HF** (ardopcf, Mercury) | HF radio and interface | As above | same | Pat 0.16.0 carried a message peer to peer between two Mercury instances with no radio (2026-09-30); over the air not exercised |
| **FreeDATA** | HF radio | None | same | Not exercised |
| **Keyboard packet, BBS, LinBPQ node** | Radio, TNC or Direwolf | None | same; [LinBPQ](../packages/linbpq.md) | Packaged; callsign and alias come from station config |
| **APRS** | VHF radio, Direwolf or a TNC | Internet only for an igate | [APRS](../guides/aprs.md) | Guide |
| **FT8, JS8 and the digital modes** | HF/VHF radio, interface, correct clock | None (PSK Reporter and spots need internet) | [FT8 and the digital modes](../guides/digital-modes.md) | Guide |
| **Time with no network** | A GPS with a fix | None | [Time and position](../guides/time-and-gps.md), [GPS time](../guides/gps-time.md) | Built; bench owed (D-058) |
| **Mesh: Meshtastic, Reticulum** | LoRa nodes or an RNode | None | [Mesh and Reticulum](../guides/mesh-and-reticulum.md) | Two containers exchanged an LXMF message over AutoInterface; **no LoRa link run** |
| **Reading forms and references** | None | None once installed | [Offline reference](../guides/offline-reference.md) | Implemented |

## Practical notes

- **Winlink is two systems.** Telnet is internet; packet and HF are radio. Pat's
  first-ever connection, which registers your callsign and sets your password,
  has to be over the internet.
- **Gateways.** `pat-winlink rmslist --mode packet --sort-distance` downloads
  Winlink's list when you run it. Run it ahead and write the gateways down.
- **Kernel AX.25 is not required.** The packet core is userspace-primary
  (Direwolf and QtSoundModem over KISS or AGW); Linux 7.1 removed the kernel
  AX.25 stack ([kernel AX.25](../reference/kernel-ax25.md)).
- **Transmitting is your decision under your licence.** Nothing here transmits
  by itself; running an igate or digipeater puts traffic on a shared resource.
- **A tray switch is not a radio.** Parking a GPS or turning Wi-Fi off changes
  connectivity: check the [Tray](../suite/tray.md) state before assuming a link.

## ICS and message forms

FEMA's 39 ICS PDFs are installed by `ics-forms` and listed on the
`hammunition reference serve` page. Winlink users also have ICS-213 and its
siblings in Pat's forms. The ICS 309 communications log is not among the 39,
so keep a paper one.

## Not covered

Digital voice and trunking, satellite operating, and RF-security tooling are
in their own guides ([Satellites](../guides/satellite.md), [RF
security](../rf-security/index.md)); they are not part of this EMCOMM set.
