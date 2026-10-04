<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Hammunition Hill

## At a glance

| | |
|---|---|
| **Repository** | <https://github.com/ChiefGyk3D/hammunition-hill> |
| **Purpose** | A ham-radio dashboard served from your own machine to your own browser: clocks, band plan, space-weather dials, propagation, a globe with greyline and paths, DX spots coloured by your log, satellites, weather, callsign lookup, a CW trainer, pocket references and shack calculators |
| **Status** | Pinned by the catalog at v1.0.0 as a `.deb`. Upstream's README describes its newer releases and keeps a feature-by-feature status table; read that for the current state. US-first: band plans, exam pools and weather severity are US |
| **Platforms** | Targets whose archive has Python 3.11 or later. Ubuntu 22.04 and Pop!_OS 22.04 are refused at plan time |
| **Independent?** | Yes. It does not need the engine to run; the engine installs it |
| **Report problems** | [Issues on hammunition-hill](https://github.com/ChiefGyk3D/hammunition-hill/issues). Run `hamhill check --fetch` first: it exercises every configured source |

## What it is for

The screen above the radio: is the band open, who is spotted, what is the weather, what does this callsign belong to. It is an alternative to HamClock-style dashboards, with your own log and station in the picture and no outbound dependency the page can be broken by. In the field its pocket references and shack tools are available without internet.

## Dependencies

- **Software:** a browser on this machine. Optionally an ADIF log, and API keys for the sources that want one.
- **Network:** an internet connection for the fetched tiers (space weather, spots, NWS). Nothing for the offline tier.
- **Hardware:** none. Position comes from the browser's geolocation; gpsd is not consulted yet.
- **Services:** `hammunition-hill.service`, a system service run as the `hamhill` user, **started at install**, listening on `127.0.0.1:8073`.

## Install and first run

```sh
hammunition install hammunition-hill --dry-run
hammunition install hammunition-hill
systemctl status hammunition-hill
```

Then open <http://127.0.0.1:8073/>. Set your callsign in `/etc/hammunition-hill/config.toml`; the file documents each option.

## Basic usage

Open the page and pick a dashboard (Home, Map, Space Weather, Operating, Activity, Field and Weather, Toolbox, as upstream describes them). Expected: clocks and band plan are filled in at once; the fetched panels fill as the collector reads its sources. A blank panel usually means an upstream source changed: `hamhill check --fetch` names which.

## Offline behaviour

A collector fetches sources on a schedule and the page reads stored snapshots. The page itself never talks to the internet, so the parts that need none keep working with the WAN unplugged. The fetched tiers go stale without a connection. What a fetched panel shows after days offline has not been measured here.

## Troubleshooting

- **Never expose it to the internet.** It has no authentication by design and the unit is hardened on the assumption that it is loopback-only.
- Inspect: `systemctl status hammunition-hill`. Stop: `systemctl disable --now hammunition-hill`. Removing the unit leaves `/etc/hammunition-hill/config.toml`.
- Install refused: the target's Python is older than 3.11.

## Where the details live

Panels, configuration options, security model and architecture belong to the Hill repository (its `docs/` directory: `INSTALL.md`, `CONFIGURATION.md`, `SECURITY.md`, `STATUS.md`). The version, service and what the install changes are on the generated [package page](../packages/hammunition-hill.md).
