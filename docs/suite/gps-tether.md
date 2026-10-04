<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Hammunition GPS Tether

## At a glance

| | |
|---|---|
| **Repository** | <https://github.com/ChiefGyk3D/hammunition-gps-tether> |
| **Purpose** | Reads your position from gpsd and serves it on this machine only: NMEA on `127.0.0.1:10110` (QMapShack's *GPS TCP/IP* source and many map programs), a server-sent-event stream at `http://127.0.0.1:10111/position` (the offline browser map), and, where `hammunition hardware apply` set GeoClue up, a unix socket GeoClue reads (how CoMaps gets a position) |
| **Status** | v0.1.1 pinned by the catalog, source archive checked by sha256, pure Python. The service started from the unit on a real machine, and its start at login after a reboot, are not yet measured |
| **Platforms** | Targets with Python 3.11 or later (not Ubuntu 22.04 or Pop!_OS 22.04) |
| **Independent?** | It needs gpsd and a receiver with a fix; the engine installs it and its systemd **user** service |
| **Report problems** | [Issues on hammunition-gps-tether](https://github.com/ChiefGyk3D/hammunition-gps-tether/issues); gpsd's own tools (`cgps`, `gpsmon`) for a receiver with no fix |

## What it is for

QMapShack and the browser map have no gpsd client of their own. The tether is the one small local bridge, started once as a login service, that every map reads.

## Dependencies

- **Hardware:** a GPS/GNSS receiver gpsd can see, with a fix. Indoors, or parked with `hammunition hardware park`, there is none.
- **Software:** gpsd (the `station` profile's, socket-activated: the first client wakes it).
- **Network:** none. Loopback only, but loopback is not per-user: any local account can read your position from it.
- **Service:** `hammunition-gps-tether.service`, a user service enabled at install and started at your next login.

## Install and first run

```sh
hammunition install gps-tether
systemctl --user start hammunition-gps-tether.service
```

## Basic usage

```sh
nc 127.0.0.1 10110
```

Expected: with a fix, `$GPRMC` and `$GPGGA` sentences; with no fix, nothing, and the tether reports that gpsd sent no position with a fix. In QMapShack, Realtime dock, right-click, *Add source*, *GPS TCP/IP*, host `127.0.0.1`, port `10110`. The offline map at `http://127.0.0.1:8480/map/` (`hammunition reference serve`) draws your position from port 10111. Step by step: [Offline navigation, section 11](../guides/offline-navigation.md#11-your-position-in-qmapshack-the-gps-tether), which owns the details.

## Offline behaviour

Fully local. The only radio link is the GNSS signal. Check `cgps` shows a fix **before** you leave.

## Troubleshooting

- *"cannot listen"*: another tether holds port 10110 (a foreground `hammunition maps gps-tether`, or QMapShack's menu entry). One tether per machine.
- *"cannot reach gpsd"*: `systemctl status gpsd`.
- *No fix*: `xgps` or `cgps`; `sudo systemctl restart gpsd.socket gpsd` has helped once on the field laptop.
- Service does not start until login, or ever on a machine you never log in to: user manager only; `loginctl enable-linger` is not set by this unit.

## Where the details live

The program's behaviour is the tether repository's; the unit, ports and what its install writes are on the generated [package page](../packages/gps-tether.md); the engine-side verb is `hammunition maps gps-tether` in the [command reference](../reference/cli.md).
