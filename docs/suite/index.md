<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# The Hammunition suite

Hammunition is one engine and a set of companion projects, each in its own
repository with its own releases. This page says what each one is, how they
fit together, and which of them you need. Each project has its own page here
that answers the same questions in the same order, so you do not have to
read source code or visit several repositories to get started.

## The projects at a glance

| Project | What it is | Repository | Status | Needs the engine? |
|---|---|---|---|---|
| [Hammunition](hammunition.md) | The engine and the catalog: installs, configures and documents the software | [Hammunition](https://github.com/ChiefGyk3D/Hammunition) | Pre-1.0 (v0.20.0 in this tree) | It *is* the engine |
| [Hammunition Tray](tray.md) | Switches for parking GPS, modem, Bluetooth and camera and for starting services, in the system tray | [hammunition-tray](https://github.com/ChiefGyk3D/hammunition-tray) | v0.5.0 pinned; the Qt tray has not yet been run on any desktop it lists | Yes: reads the lists `hammunition hardware apply` writes |
| [Hammunition Hill](hill.md) | A local ham-radio dashboard in your browser | [hammunition-hill](https://github.com/ChiefGyk3D/hammunition-hill) | v1.0.0 pinned (upstream's own README describes its current release) | No: runs alone; the engine just installs it |
| [Hammunition Bunker](bunker.md) | A LAN server that keeps verified copies of the engine's offline data | [hammunition-bunker](https://github.com/ChiefGyk3D/hammunition-bunker) | 0.1.0, unreleased: tested against a fake engine, never run on a NAS | Yes: asks the engine what to keep |
| [Hammunition Console](console.md) | A full-screen terminal front end for the engine | [hammunition-console](https://github.com/ChiefGyk3D/hammunition-console) | v0.1.0 pinned; not yet run through a real install | Yes: it only drives the engine |
| [Hammunition GPS Tether](gps-tether.md) | Your gpsd position as NMEA and as a browser stream, on this machine only | [hammunition-gps-tether](https://github.com/ChiefGyk3D/hammunition-gps-tether) | v0.1.1 pinned; not yet measured as a service on hardware | Needs gpsd; the engine installs and starts it |

"Pinned" means the version the catalog installs, written in
`catalog/packages/`; a project's own repository may be ahead of it. Each
project's page says where to read its newest state. **If a status here
disagrees with a project's own README, the README is the newer word and this
page is a bug: report it.**

Another project by the same maintainer is carried like any upstream:
[Skid-Finder](https://github.com/ChiefGyk3D/Skid-Finder), a passive BLE-spam
and Wi-Fi-attack detector, installed by the `skid-finder` unit
([its page](../packages/skid-finder.md)). It is not part of the suite's
runtime and nothing here depends on it.

## How they fit together

```text
   publishers (Geofabrik, Kiwix, FEMA ...)            your radios, GPS, SDRs
            |                                                |
            v                                                v
  +------------------+   artifacts --json   +-------------------------+
  | Hammunition      | <------------------- | Bunker (on a NAS, LAN)  |
  | Bunker           | -- LAN mirror -----> |                         |
  +------------------+     (read-only)      +-------------------------+
            |  <- optional: the engine asks the mirror first
            v
  +-------------------------------------------------------------+
  | Hammunition (the engine): catalog, plans, installs, station |
  +-------------------------------------------------------------+
     |            |                |                  |
     | installs   | --json         | hardware apply   | installs, starts
     v            v                v                  v
   Hill        Console         Tray (+ helper)     GPS Tether --> QMapShack,
 (browser)   (terminal)      park/wake, services     browser map, CoMaps
```

- **The engine is the hub.** Everything else is either installed *by* it, a
  *client* of it, or a *server* for its data. The catalog under `catalog/`
  is the single source of what gets installed and at which version.
- **Hill is independent.** It is a dashboard that happens to be installed
  through the engine (it is in the `station` profile) and does not need the
  engine to run. The plan is for it to show local sources (rig state, GPS
  fix) later; today its position comes from the browser.
- **The Tray and the Console are front ends.** Neither holds install logic.
  The Tray is a front end for `hammunition hardware park`, `wake` and
  `hammunition services`; the Console only runs the engine's commands.
- **The GPS Tether is a bridge.** It turns gpsd's position into the two
  shapes mapping programs ask for.
- **The Bunker is optional.** Without it every download comes from its
  publisher, with the same checks.

## Which do I need?

| I want to… | Install |
|---|---|
| A working radio workstation | The engine, then a [profile](../profiles/index.md); nothing else is required |
| A dashboard for band conditions, spots and references | Hill: it is in `station`, or `hammunition install hammunition-hill` |
| A switch to park the GPS or modem on battery | Tray (`hammunition-tray` on Plasma, `hammunition-tray-qt` on Xfce, LXQt, LXDE, MATE, Cinnamon) |
| To pick from a list instead of typing commands | Console (`hammunition install hammunition-console`) |
| My position in QMapShack or on the browser map | GPS Tether (in `navigation`, or `hammunition install gps-tether`) |
| Map and reference downloads from the next room, not the internet | Bunker, on a NAS, then `hammunition station set --mirror` |

## Which repository owns which details

So that two copies of a fact do not quietly drift apart, each kind of detail
has one home. A page here summarises, links to the owner, and says when it
was last checked against it.

| Detail | Owner | These pages |
|---|---|---|
| Commands, flags, exit codes, what the engine refuses | The engine's [command reference](../reference/cli.md) | Link; never restate a flag table |
| Which version of a companion project is installed, from where, how it is checked | `catalog/packages/*.yaml` in the engine repository | State the version the manifest pins, as of the build date |
| A companion project's internal architecture, configuration file options, its own changelog | That project's repository | Summarise in a paragraph; link |
| What a Hammunition install writes to your machine | The unit's [package page](../packages/index.md), generated from its manifest | Link |
| What each project does today and what is experimental | That project's README, and this page's status table | Say which; mark anything unverified |

If you change one of these in a repository, change this suite section in the
same pull request: [contributing documentation](../contributing/documentation.md).

## Status words used in these pages

| Word | Meaning |
|---|---|
| **Implemented** | Built, covered by tests, and described by the project's own docs |
| **Measured** | Run on real hardware or a real machine by the maintainer, recorded in the [bench record](../reference/bench-verification-5430.md) or a VM campaign page |
| **Experimental** | Built, not yet run on real hardware, or run once |
| **Planned** | Not written; stated by the maintainer's plans |
| **Unverified** | This documentation could not check it |

Almost everything in the suite is *implemented* and not yet *measured*. The
pages say so each time.

## Next

- [EMCOMM and field operation](../emcomm/index.md): using these pieces before
  and during a deployment.
- [Offline documentation](../offline/index.md): this documentation as a
  download.
- [Applications](../packages/index.md): every piece of software the engine
  can install, one page each.
