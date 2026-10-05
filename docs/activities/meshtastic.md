<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Meshtastic

Meshtastic is a ready-made text and position mesh on LoRa: inexpensive boards
run its firmware, a phone or computer is the client, and no infrastructure is
needed. The node is the radio. It is a different network from Reticulum's, and
the two do not exchange messages, though they use the same kinds of board.

## Programs the catalog carries

<!-- BEGIN generated: programs -->

- [gtk-meshtastic-client](../packages/gtk-meshtastic-client.md): Desktop GUI for Meshtastic nodes (in [`mesh`](../profiles/mesh.md))
- [python3-meshtastic](../packages/python3-meshtastic.md): Meshtastic command-line client and Python API (in [`mesh`](../profiles/mesh.md))

<!-- END generated: programs -->

Both come from the distribution's archive. `meshtasticd`, the Linux node
daemon for a machine with a LoRa HAT, is **not carried yet**: no archive has it,
it comes from a third-party repository, and it is the next unit of Track C
(issue #105). The web client and the flashers are likewise to come.

## Hardware the catalog identifies

<!-- BEGIN generated: hardware -->

- [meshtastic](../hardware/meshtastic.md): Meshtastic LoRa nodes — T-Deck, T-Echo, RAK and WisMesh boards (status supported; not maintainer-verified)

<!-- END generated: hardware -->

The maintainer's own Meshtastic nodes (T-Deck, T-Echo, RAK) were lost to
flooding, so nobody on this project has run this hardware. The catalog's USB
identifiers come from upstream's board metadata (107 boards), and most are
shared by many products: an identifier names the module a board is built on,
not the board. The [device page](../hardware/meshtastic.md) lists them; an
owner can help close that gap ([contributing hardware](../contributing/hardware.md)).

## Install

```sh
hammunition install mesh --dry-run
hammunition install mesh
```

The `mesh` profile also carries Reticulum (see [that hub](reticulum.md)); read
the plan, which defers by name any Meshtastic package your archive lacks
(`python3-meshtastic` is absent on Ubuntu 24.04 and Pop!_OS 24.04, measured
2026-10-03). Add yourself to `dialout`, log out and back in, and attach the
node. A node appears as `/dev/ttyACM0` or `/dev/ttyUSB0`. The profile is
post-1.0 and says so.

## First useful task: read your node

```sh
meshtastic --info
meshtastic --nodes
```

`--info` reads the node's configuration, `--nodes` lists the nodes it has
heard. A node transmits only after its region is set; the form is
`meshtastic --set lora.region US` with your own region's code. The client's
`--help` also lists `--sendtext` to send a message and `--set-ham`, Meshtastic's
own switch for the amateur-radio question. Regional frequency rules and
licensing are yours to establish; the catalog does not rule on them. A GTK
desktop client, `gtk-meshtastic-client`, does the same with windows.

## Offline, LAN and radio

| Part | With no internet? |
|---|---|
| Talking to your own node over USB, and the mesh over LoRa | Yes. |
| Installing the clients and flashing firmware | No: fetch them ahead of time. |

## Where the detail lives

[Mesh and Reticulum, section 11](../guides/mesh-and-reticulum.md#11-meshtastic-beside-it),
the [device page](../hardware/meshtastic.md), [LoRa inventory](../reference/lora-inventory.md),
upstream's documentation at <https://meshtastic.org/>.

## What was measured, and what was not

Measured: that both clients exist in Debian 13 (the device entry records this),
the options quoted above were read from the CLI's `--help` (version 2.7.11;
Debian 13 and Parrot carry 2.6.0, which may differ), and the board and
identifier survey over 107 upstream boards.

Not measured:

- **Any Meshtastic node.** None has been run for this catalog, and no LoRa
  link has been run through the `mesh` profile.
- **The commands above.** Their field names and region codes are Meshtastic's;
  the guide did not run them.
- **Firmware flashing** with `esptool` or the UF2 bootloader.
- **`gtk-meshtastic-client`** against a node.
