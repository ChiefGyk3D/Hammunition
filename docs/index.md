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

## Five minutes to a plan

```sh
git clone https://github.com/ChiefGyk3D/Hammunition.git
cd Hammunition
./bootstrap.sh
hammunition install station --dry-run
```

The last line changes nothing. It prints every package, every file and
every system change the install *would* make. Read it, then run it again
without `--dry-run`. [Getting started](getting-started/index.md) walks the
whole path.

## What do you want to do?

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
| Study wireless security | [RF security](rf-security/index.md) | [`rf-security`](profiles/rf-security.md) |

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

- **[Getting started](getting-started/index.md)** — install the engine, the
  first profile, the first decode.
- **[Guides](guides/index.md)** — one task each, start to finish.
- **[Profiles](profiles/index.md)** — the bundles, what each installs and
  what it leaves for you to set up.
- **[Packages](packages/index.md)** — every program, what it does, what it
  needs, its known problems.
- **[Hardware](hardware/index.md)** — radios, SDRs, GPS and the rest: what
  Linux needs to talk to each.
- **[Troubleshooting](troubleshooting/index.md)** — by symptom.
- **[Reference](reference/cli.md)** — the command line and the measurements
  everything here rests on.
- **[Contributing](contributing/manifests.md)** — add a program, send a
  device's identifiers.
