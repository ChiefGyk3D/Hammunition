<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Hammunition, the engine and catalog

## At a glance

| | |
|---|---|
| **Repository** | <https://github.com/ChiefGyk3D/Hammunition> |
| **Purpose** | Turns an existing Debian-family install into an amateur radio, SDR and RF workstation, and documents what it installed |
| **Status** | Pre-1.0. Version 0.20.0 in this tree. Every install method is implemented and VM-verified; hardware steps are partly measured (see the [bench record](../reference/bench-verification-5430.md)) |
| **Platforms** | Parrot OS first; Debian 13, Ubuntu 24.04 and 26.04, Kali and Linux Mint 22.3 tested in containers; a Debian 13 arm64 target for Raspberry Pi OS. Pop!_OS 24.04 passed the VM campaign but is not declared. [Desktop notes](../desktops.md) |
| **Independent?** | Yes. It is the hub; everything else in the [suite](index.md) is installed by it or reads from it |
| **Owns** | The catalog (software, profiles, hardware), the CLI, the pins and the verification of every download |
| **Report problems** | [Issues on the repository](https://github.com/ChiefGyk3D/Hammunition/issues); for a failed install, attach the run log (`hammunition logs --last`) with your callsign and grid removed |

## What it is for

- Installing a coherent set of ham, SDR and RF software with one command, with the whole plan shown first.
- Keeping station values (callsign, grid square, map regions, rig) in one place and filling them into each program's configuration.
- Hardware setup: udev rules, group membership, parking and waking devices, GPS time.
- Offline data for the field: maps, terrain, reference books, forms, repeater and infrastructure layers.

It is not a distribution and does not replace your OS. It uses your distribution's packages wherever they exist.

## Dependencies

- A Debian-family system with `sudo`, Python 3.11 or later and `python3-venv`, and a network connection at install time (or a [LAN mirror](../guides/lan-mirror.md) for data downloads).
- [Disk space](../getting-started/disk-space.md): about 5 GB for one or two profiles, about 55 GB for the whole catalog.
- No radio is needed to install; each application's page says what it needs to run.

## Install and first run

```sh
git clone https://github.com/ChiefGyk3D/Hammunition.git
cd Hammunition
./bootstrap.sh
hammunition doctor
hammunition install station --dry-run
```

`bootstrap.sh` makes the engine's virtualenv and links `hammunition` into `~/.local/bin`; `doctor` is a read-only health check. The last line changes nothing: it prints every package, file and system change the install would make. Read it, then run it without `--dry-run`. The full walk-through with expected output is [Installation](../getting-started/installation.md).

## Basic usage

```sh
hammunition station set --callsign N0CALL --grid-square FN31pr   # your own values
hammunition install station
hammunition list profiles
hammunition status
```

Use your own callsign and grid square; `N0CALL` and `FN31pr` are placeholders. A missing station value never blocks an install: it defers the one file that needs it and the plan says which command would write it.

Expected result: `status` lists what is installed and what was deferred. Every command and flag is in the [command reference](../reference/cli.md).

## Offline behaviour

Installing needs the network (or a mirror, or a package cache you prepared). Using what was installed generally does not. Which applications work with no internet is on each [application page](../packages/index.md) under "Offline use"; [the field guides](../emcomm/index.md) cover the workflows. Downloading *software and data* is the engine's job; downloading *this documentation* is [a separate step](../offline/index.md).

## Troubleshooting

[Troubleshooting](../troubleshooting/index.md) is organised by symptom. First checks: `hammunition doctor`, `hammunition logs --last`, `hammunition transactions --last 5`.

## Where the details live

This repository is the owner of everything in [the ownership table](index.md#which-repository-owns-which-details). The reference section's generated pages (package pages, profile pages, schema, JSON interface, capability matrix) are built from the manifests and tested to be current; do not edit them by hand.
