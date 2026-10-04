<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Troubleshooting with no internet

By symptom. Each line says what to check with the tools already on the
machine. The wider set is [Troubleshooting](../troubleshooting/index.md).
Remember the three kinds of connectivity ([EMCOMM overview](index.md#three-kinds-of-offline)):
say which one is missing before you chase anything.

## The machine and the engine

| Symptom | Check |
|---|---|
| Not sure the system is healthy | `hammunition doctor` (read-only) |
| What did the last run do? | `hammunition logs --last`, `hammunition transactions --last 5` |
| An install fails or hangs | Is it waiting for a sudo password? See the run log; with no network `hammunition install` keeps installed regions and refuses an unfetched one by name. Ask for the plan: `--dry-run` |
| Everything needs a package that is not here | You cannot fetch it. Use only what is installed, or a [LAN mirror](../guides/lan-mirror.md) for data. Software comes from apt: a prepared package cache or a repository you mirror is outside this tool |
| `hammunition: command not found` | Log out and in, or run `.venv/bin/hammunition` from the checkout |
| The mirror is down | A dead mirror costs one ten-second wait; the publisher is then asked and fails offline. `--no-mirror` skips it |

## Maps, position and reference

| Symptom | Check |
|---|---|
| No position | `cgps` or `xgps`. No fix: be outdoors, wake a parked receiver (`hammunition hardware wake NAME`), `systemctl status gpsd`. `sudo systemctl restart gpsd.socket gpsd` has helped |
| QMapShack or the browser map shows no dot | Is the tether running: `systemctl --user status hammunition-gps-tether.service`, `nc 127.0.0.1 10110`. Only one tether per machine |
| Navit opens on a blank map | See *Navit opens on a blank map* in [Offline navigation](../guides/offline-navigation.md#troubleshooting) |
| `/map/` says no region installed | `osm-pmtiles` has built nothing for your regions; needs an install while online |
| Address search finds almost nothing | OpenStreetMap's coverage of addresses there; see the guide |
| Reference page does not open | `hammunition reference serve`, then <http://127.0.0.1:8480/>. It listens on 127.0.0.1 only; use an SSH forward from another machine |
| A book or form is missing | It was never installed; you cannot fetch it now |
| A layer is missing a point you know exists | The data is as old as the extract and as complete as its source; see [limits](offline-data.md#what-a-mapped-place-does-not-tell-you) |

## Radio and time

| Symptom | Check |
|---|---|
| FT8 stops decoding | The clock drifted about a second. `hammunition time`; [GPS time](../guides/gps-time.md) |
| Hears everyone, heard by nobody | Transmit audio level too high ([Radio audio](../guides/audio-routing.md)) |
| Radio will not key | [Rig control](../guides/rig-control.md); `hammunition doctor` checks the rig service without keying |
| Pat cannot connect to a gateway | Gateway in range? Direwolf running with `ADEVICE` set? Pat's engine set to `agwpe`? [Packet and Winlink](../guides/packet-winlink.md) |
| Pat's first connection | It must be made over the internet: it cannot be done in the field |
| A device does not appear | `hammunition hardware state`; was it parked? Is the udev step applied? |
| Wi-Fi or Bluetooth is gone | Check the [tray](../suite/tray.md) Radios group and `hammunition hardware state`: a switch may have turned it off |

## Dashboards

Hill's fetched panels go blank or stale offline by design; its clocks, band
plan and references keep working. `hamhill check --fetch` is for when you do
have internet.

## When it is not in these pages

The [offline documentation bundle](../offline/index.md) has local search.
Package pages carry *Known problems* and where to get help with the software
itself, which needs the internet.
