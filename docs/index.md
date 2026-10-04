<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Hacker's Ham Shack

**Hammunition** turns a Debian-family computer you already have into an
amateur radio, software-defined radio and RF workstation. Parrot OS is the
primary target; Debian 13, Ubuntu, Kali and Raspberry Pi OS are supported
too. It is not a distribution and does not replace your system: it adds to
it, using your distribution's own packages wherever they exist.

These pages are the manual. The standard they are written to: a licensed
ham with moderate Linux experience gets from a fresh install to a working
digital-modes station **without asking anyone a question or reading a forum
thread**. A step that needs knowledge these pages do not give is a bug in
them, and worth [an issue](https://github.com/ChiefGyk3D/Hammunition/issues).

## Start here, in this order

New to Hammunition? Read these four, in order. Each is written so you can
finish it without asking anyone a question.

1. **[Installation](getting-started/installation.md).** A numbered walkthrough
   from a fresh machine: the engine, the health check, your callsign and grid,
   the dry run and how to read it, the real install, and how to undo it. Every
   command is written out with the output it prints.
2. **[Profiles](profiles/index.md).** All nineteen bundles of software, what
   each installs and leaves out, and a "which profile do I want" table by goal.
3. **[Guides](guides/index.md).** One task each, start to finish: rig control,
   radio audio, FT8, Winlink, APRS, SDR, satellites, offline maps.
4. **[Troubleshooting](troubleshooting/index.md).** By symptom, when something
   does not do what a page said it would.

## Where everything is

| Area | What is there |
|---|---|
| **Setup** | [Installation](getting-started/installation.md), [profiles](profiles/index.md), [first profile](getting-started/first-profile.md) |
| **Applications** | [Every application](packages/index.md), by category and by profile, each with how to install, launch and use it offline |
| **The suite** | [Hammunition, Tray, Hill, Bunker, Console and GPS Tether](suite/index.md): what each is, its repository, status and how they fit together |
| **EMCOMM** | [Field guides](emcomm/index.md): preparation checklist, offline data, communications, backup, no-internet troubleshooting, quick reference |
| **Offline** | [This documentation as a folder you can carry](offline/index.md), and the difference between downloading documents, software and data |
| **Troubleshooting** | [By symptom](troubleshooting/index.md), and [without the internet](emcomm/no-internet.md) |
| **Contributing** | [Writing and publishing the docs](contributing/documentation.md) and the templates |

## Five minutes to a plan

The short form of step 1, for someone who has done this before:

```sh
git clone https://github.com/ChiefGyk3D/Hammunition.git
cd Hammunition
./bootstrap.sh
hammunition install station --dry-run
```

The last line changes nothing. It prints every package, every file and
every system change the install *would* make. Read it, then run it again
without `--dry-run`. [Installation](getting-started/installation.md) walks the
whole path, and [How much disk you need](getting-started/disk-space.md) says
what to have free first: about 5 GB for one or two profiles, about 55 GB for
the whole catalog.

## What do you want to do?

Find your situation, then follow the link. Each guide says what to install,
what to run and what you should see.

| I want to… | Start here | Profile |
|---|---|---|
| Make FT8, JS8 or PSK contacts | [FT8 and the digital modes](guides/digital-modes.md) | [`digital-modes`](profiles/digital-modes.md) |
| Let every program control my radio | [Rig control (CAT)](guides/rig-control.md) | [`station`](profiles/station.md) |
| Get audio between radio and computer right | [Radio audio](guides/audio-routing.md) | — |
| Send email by radio when the internet is down | [Packet and Winlink](guides/packet-winlink.md) | [`packet`](profiles/packet.md) |
| Report my position, see who is around | [APRS](guides/aprs.md) | [`packet`](profiles/packet.md) |
| Listen with a cheap SDR dongle | [SDR first steps](guides/sdr.md) | [`sdr`](profiles/sdr.md), [`listening`](profiles/listening.md) |
| Track and hear satellites | [Satellites](guides/satellite.md) | [`satellite`](profiles/satellite.md) |
| Know when a band is open | [Propagation](guides/propagation.md) | [`propagation`](profiles/propagation.md) |
| Navigate with no network at all | [Offline navigation](guides/offline-navigation.md) | [`navigation`](profiles/navigation.md) |
| Keep the clock right with no network | [Time and position](guides/time-and-gps.md) | [`station`](profiles/station.md) |
| Switch the GPS, a modem or a service off to save power | [The tray's Controls panel](guides/tray-controls.md) | [`station`](profiles/station.md) |
| See repeaters, airfields and hospitals on an offline map | [Offline navigation](guides/offline-navigation.md) | [`navigation`](profiles/navigation.md) |
| Read Wikipedia and the ICS forms with no network | [Offline reference](guides/offline-reference.md) | [`reference`](profiles/reference.md) |
| Study wireless security | [RF security](rf-security/index.md) | [`rf-security`](profiles/rf-security.md) |
| Use an SDR dongle I already own | [SDR first steps](guides/sdr.md), then the device's page, for example [RTL-SDR](hardware/rtl-sdr.md) | [`sdr`](profiles/sdr.md) |
| Find my radio or adapter and see what Linux needs for it | [Hardware](hardware/index.md) | — |
| Know how big a disk to buy | [How much disk you need](getting-started/disk-space.md) | — |
| Run this on Ubuntu, Kali, Mint, a Pi or a desktop other than Plasma | [What works on which desktop](desktops.md), then [Getting started](getting-started/index.md) | — |
| Understand what an install will do to my machine | [Your first profile](getting-started/first-profile.md): read the plan, then run it | — |
| Fix something that broke | [Troubleshooting](troubleshooting/index.md), by symptom | — |
| Add a program or a device's identifiers to the catalog | [Contributing](contributing/manifests.md) | — |

Every guide says which parts were measured on real hardware and which were
not. Where it has not been measured, it says *unmeasured* rather than
guessing.

## How it treats your machine

- **It shows you first.** `--dry-run` prints the complete plan: packages,
  builds, files, groups, udev rules, repositories. It is not an
  approximation.
- **It installs other people's software, verified.** Distribution packages
  through apt. Anything else is pinned to a version and checked against a
  checksum before it runs; nothing unverified is installed, and nothing is
  ever piped into a shell.
- **It records what it did.** `hammunition status` shows every transaction,
  and `hammunition uninstall` reverses them.
- **It never guesses your callsign.** Files that need your callsign or grid
  are written from values you set once, and skipped, by name, until you do.
- **Transmit-capable security tooling needs your consent,** typed, and
  `--yes` cannot give it for you.

## The software is theirs

Hammunition writes none of the radio software it installs. [The projects we
install](projects.md) links every one of them to its home, and
[Credits](credits.md) names the projects whose years of curation this
catalog stands on. When a program misbehaves, its page in the [package
reference](packages/index.md) says where to get real help with it.

## Where things are

- **[Installation](getting-started/installation.md)** — the whole path from a
  fresh machine, with every command and what it prints.
- **[Profiles](profiles/index.md)** — the bundles, what each installs and
  what it leaves for you to set up, and which one you want.
- **[Guides](guides/index.md)** — one task each, start to finish.
- **[Troubleshooting](troubleshooting/index.md)** — by symptom.
- **[Getting started](getting-started/index.md)** — the short pages: size
  your disk, the first profile, the first decode.
- **[Packages](packages/index.md)** — every program, what it does, what it
  needs, its known problems.
- **[Hardware](hardware/index.md)** — radios, SDRs, GPS and the rest: what
  Linux needs to talk to each.
- **[What works on which desktop](desktops.md)** — the tray and the menus on
  Plasma, Xfce, LXQt, GNOME and the rest.
- **[Reference](reference/cli.md)** — the command line and the measurements
  everything here rests on.
- **[Contributing](contributing/manifests.md)** — add a program, send a
  device's identifiers.
