<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# MeshCore

MeshCore is another LoRa mesh messaging system for the same family of boards
as Meshtastic and RNode. **The catalog does not carry it yet.** This page
exists so that a person looking for it finds the reason and the route, not a
gap.

## Programs the catalog carries

<!-- BEGIN generated: programs -->

The catalog carries no MeshCore unit and no MeshCore device entry.

<!-- END generated: programs -->

## Hardware the catalog carries

<!-- BEGIN generated: hardware -->

The catalog carries no MeshCore unit and no MeshCore device entry.

<!-- END generated: hardware -->

## Why not yet

MeshCore was asked for by the maintainer on 2026-09-13 as part of Track C
(mesh and Reticulum), and it is in scope. Track C ships in parts, each measured
before it is claimed (issue #105): the Reticulum core and the two Meshtastic
clients landed first ([Reticulum hub](reticulum.md), [Meshtastic
hub](meshtastic.md)). What is recorded about MeshCore so far, from the
[mesh inventory](../reference/mesh-inventory.md):

- Its tooling, `meshcore-cli` and `python-meshcore`, is MIT throughout, and a
  scratch virtualenv of `meshcore-cli` is about 19 MB.
- Both sit in Debian sid only: not in trixie, not in Ubuntu 24.04 or 26.04.
- The pins resolve against PyPI on both architectures.

## The route

The Track C plan (see [SCOPE](https://github.com/Renegade-Penguin/Hammunition/blob/main/docs/SCOPE.md))
names MeshCore's companion clients and the web flasher's firmware pins as
units, with the board definitions the LoRa sweep already reads. The shape
that fits the catalog is the Reticulum one: hash-pinned per-user virtualenvs
and a documented device entry. A MeshCore board is likely to present its base module's USB
identifier like the other LoRa boards
([LoRa inventory](../reference/lora-inventory.md)); that is not measured, and
the device entry needs a capture from a board someone owns.
This page is replaced by a full hub when the first unit lands.

## What you can do today

Install the tools yourself from upstream, outside Hammunition, and bring your
own board. Hammunition's [serial permission
entry](../troubleshooting/running.md#dialout) (`dialout`) applies to any
serial LoRa board. MeshCore's own documentation is the authority for its use.

## What was measured, and what was not

The licence, the Debian archive status and the venv size above are from the
mesh inventory (2026-10-03). Not measured: any MeshCore node, client or
flasher, and whether a catalog unit installs cleanly. Nothing here has been
run.
