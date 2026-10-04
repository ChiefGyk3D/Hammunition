<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Hammunition Console

## At a glance

| | |
|---|---|
| **Repository** | <https://github.com/ChiefGyk3D/hammunition-console> |
| **Purpose** | A full-screen terminal program showing what is installed, what is wrong and what to do next; runs the engine's own commands in a terminal pane |
| **Status** | v0.1.0 pinned; first release. Tested against recorded engine documents and a fake engine on a pseudo-terminal; **not yet run through a real install**. Hardware and maps screens are not in this release |
| **Platforms** | Any target with Python 3.11 or later (not Ubuntu 22.04 or Pop!_OS 22.04). A terminal of at least 80x24; refuses `TERM=dumb` and root. Works over SSH and on a Pi |
| **Independent?** | No. It needs the engine (0.19.0 or later) on PATH and installs nothing itself |
| **Report problems** | [Issues on hammunition-console](https://github.com/ChiefGyk3D/hammunition-console/issues); `hammunition doctor` for anything the engine reports |

## What it is for

Picking from a list instead of remembering verbs, or walking a fresh machine to a working station for the first time. It is a front end for the [command reference](../reference/cli.md) and does exactly what those commands do. Sudo and every consent prompt are the engine's, answered by you in the terminal pane, never by the console.

## Dependencies

The engine; Python 3.11+; a real terminal. The network is whatever the commands you run need.

## Install and first run

```sh
hammunition install hammunition-console
hammunition-console
```

It is in no profile. The first-run checklist (set the station, apply the hardware rules, pick a profile, install) is walked through in [The console](../getting-started/console.md), which owns this page's details.

## Basic usage

On Home, press `s` to skip a checklist step, `D` to dismiss it. In Install, choose `station`: the engine's plan is shown first, grouped as the engine groups it, and nothing changes until you press `R` and type any `yes` yourself.

## Offline behaviour

Looking around needs no network. Installs need what the engine needs.

## Troubleshooting

A crash writes `crash.log` beside `~/.config/hammunition-console/config.toml` with the exception type and frames, never a message. A copy placed by the console repository's own `install.sh` conflicts with this unit's launcher; run that repository's `uninstall.sh` once.

## Where the details live

[The console](../getting-started/console.md) (this repository) for the walk-through; the console's repository for screens and keys.
