<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Hammunition Bunker

## At a glance

| | |
|---|---|
| **Repository** | <https://github.com/ChiefGyk3D/hammunition-bunker> |
| **Purpose** | A container for a NAS or home server that keeps a verified copy of the engine's offline data (map regions, elevation tiles, reference books and the other data units) fresh on a schedule, and serves it read-only on your LAN |
| **Status** | **0.1.0, unreleased. Tested against a fake engine and a publisher on loopback; the image has never been built and no NAS has run it.** Its README says the same. Treat it as experimental |
| **Platforms** | Documented for Synology Container Manager and for rootless Podman on a Debian host; both from their documentation, not from a run |
| **Independent?** | No. It asks `hammunition artifacts --json` what to keep and verifies with the engine's own fetcher. It is not installed by the engine |
| **Report problems** | [Issues on hammunition-bunker](https://github.com/ChiefGyk3D/hammunition-bunker/issues) |

## What it is for

Rebuilding a laptop, adding a region, or preparing several laptops for a deployment should not mean downloading a state's terrain or a 127 GB encyclopaedia again from the internet. With a Bunker on the LAN, the laptop's `hammunition install` takes its data from the next room, and checks every byte exactly as it would have from the publisher. It is also a way to hold your deployment data **before** the network goes away.

It is not a public mirror (it serves without authentication, over plain HTTP: LAN only, never published to the internet), not a second source of truth (the pins live in the engine's catalog), not an apt mirror, and not a push service.

## Dependencies

- **Hardware:** a NAS or any always-on machine with a container runtime and disk for the data (see [disk planning](../getting-started/disk-space.md)).
- **Software:** the engine release the Bunker pins (v0.19.0 at its 0.1.0), inside its image.
- **Network:** internet for the Bunker to fill itself from publishers; the LAN for laptops to read it.

## Install and first run

The Bunker's own README and its guide are the owners of these steps; in outline, on Synology: make a volume folder and a config folder, copy `config.example.toml` to `bunker.toml` and set your regions, import `compose.yaml` as a project with its `ports` line set to the NAS's LAN address. On Debian with rootless Podman, `packaging/bunker.container` is a quadlet unit whose header is the commands. These have not been run on a NAS.

Then on the laptop:

```sh
hammunition station set --mirror http://<nas-address>:8080/
hammunition station show
```

## Basic usage

With the mirror set, run any data install, for example `hammunition install osm-regions`. The plan names both sources in order, mirror then publisher. Expected: the download comes from the mirror, and the transaction log records `source: mirror`. If the mirror is off, lacks the file, sends the wrong size or the wrong bytes, the file is discarded and the publisher is asked; a dead mirror costs one ten-second wait per run. Details: [A LAN mirror for offline data](../guides/lan-mirror.md), which owns the engine side.

`--no-mirror` ignores the mirror for one run; `hammunition station set --clear-mirror` removes it.

## Offline behaviour

The Bunker is how a *local network* substitutes for the internet: laptops on the LAN can install data with no internet once the Bunker holds it. The Bunker itself needs the internet to fill and refresh. Some artifacts are held **unverified** (no publisher digest exists: the ACMA register and the on-request repeater lists); the status page lists them.

## Troubleshooting

See the Bunker's own guide (docs/guide.md in that repository) for folder permissions, the status page and checking a file by hand. `bunker doctor` reports held unverified artifacts and the engine version it was written against. On the laptop, `hammunition logs --last` shows where each download came from.

## Where the details live

Schedules, the check-kind table, the config file and the container are the Bunker repository's. What the engine asks of it (`artifacts`) is in the [command reference](../reference/cli.md) and the [JSON interface](../reference/json-interface.md).

## Not verified

Everything about a real deployment: image build, a NAS run, Synology and Podman steps, scheduled refresh over weeks.
