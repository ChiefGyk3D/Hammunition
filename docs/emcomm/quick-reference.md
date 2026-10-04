<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Quick reference

Essential tasks on one page, printable. Every command is described in the
[command reference](../reference/cli.md). Use your own callsign and grid
square for `N0CALL` and `FN31pr`.

## Engine

| Task | Command |
|---|---|
| Health check (read-only) | `hammunition doctor` |
| What is installed | `hammunition status` |
| Profiles and packages | `hammunition list profiles`, `hammunition list packages` |
| Plan an install (changes nothing) | `hammunition install NAME --dry-run` |
| Install | `hammunition install NAME` |
| Remove | `hammunition uninstall NAME` |
| Behind the catalog's pins? | `hammunition update` |
| Last run's output | `hammunition logs --last` |
| History | `hammunition transactions --last 10` |

## Station

| Task | Command |
|---|---|
| Set callsign and grid | `hammunition station set --callsign N0CALL --grid-square FN31pr` |
| Show values | `hammunition station show` |
| Choose map regions (replaces the list) | `hammunition station set --map-regions A,B` |
| Choose reference books | `hammunition station set --reference-books ID,ID` |
| Use a LAN mirror | `hammunition station set --mirror http://HOST:8080/` |

## Hardware

| Task | Command |
|---|---|
| Apply udev rules and groups | `hammunition hardware apply --dry-run`, then `hammunition hardware apply` |
| Device state | `hammunition hardware state` |
| Park, wake | `hammunition hardware park NAME`, `hammunition hardware wake NAME` |
| Services | `hammunition services` |
| Clock mode | `hammunition time` |

## Field data

| Task | Command |
|---|---|
| Find a region name | `hammunition maps regions NAME` |
| Infrastructure layers | `hammunition maps infra import --from-osm` |
| Repeater layer from your export | `hammunition maps repeaters import FILE` |
| Remove a layer | `hammunition maps infra remove`, `hammunition maps repeaters remove` |
| Offline maps | `navit-offline`, `qmapshack-offline` |
| GPS to map programs | `systemctl --user start hammunition-gps-tether.service`; NMEA on 127.0.0.1:10110 |
| Reference, books, forms, browser map | `hammunition reference serve`, then <http://127.0.0.1:8480/> |
| Dictionary | `dict WORD` |

## Radio

| Task | Command |
|---|---|
| Direwolf | `direwolf -c /etc/direwolf.conf` |
| Pat setup, web UI | `pat-winlink configure`, `pat-winlink http` then <http://localhost:8080> |
| Gateway list | `pat-winlink rmslist --mode packet --sort-distance` |
| Connect over packet | `pat-winlink connect ax25+agwpe:///N0CALL-10` |

## Offline test

```sh
nmcli networking off
navit-offline
nmcli networking on
```

## Remember

- A mapped shelter, hospital or repeater is **not** a statement that it is open.
- Internet, a local network and a radio link are different things.
- The first Winlink connection needs the internet.
- Check `cgps` for a fix before relying on position.
