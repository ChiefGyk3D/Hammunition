<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Backup and recovery

Hammunition has **no backup or restore command**. This page lists what is
worth saving, where each thing lives, and how to put it back using only
commands the engine and your system already have. Nothing here is automatic.

The principle: **software and downloaded data are rebuilt by reinstalling;
your values and your own files are what you back up.** A reinstall is
idempotent and the plan shows what it will do.

## What to save, in order of value

| What | Where | Why | Sensitive? |
|---|---|---|---|
| Station values | `~/.config/hammunition/station.yml` (mode 0600) | Callsign, grid square, map regions, mirror, rig, reference books. Everything else is derived from it | **Yes.** A callsign resolves to a name and address; regions and a grid say where you are |
| Your repeater and infrastructure layers | `~/.local/share/hammunition/overlays/` (files 0600) | Built from your own exports; RepeaterBook's terms are personal use and no redistribution | Yes, and keep them to your own machines |
| Pat's configuration and mailbox | `~/.config/pat/config.json` and Pat's data directory | Your Winlink password and messages | **Yes** (the password) |
| Program configs the engine wrote | `/etc/direwolf.conf` (first backup kept as `/etc/direwolf.conf.hammunition-backup`), `/etc/bpq32.cfg`, `/etc/hammunition-hill/config.toml` | Audio device and PTT choices the engine cannot know | Contains your callsign |
| QMapShack's settings | `$XDG_CONFIG_HOME/QLandkarte/QMapShack.conf` (by default under `~/.config`) | Projects, sources, the registered overlay directories | Maybe |
| Your logs and ADIF files | Wherever your logging program keeps them; Hill reads an ADIF you point it at | Contact records | Yes |
| Reticulum and mesh identities | `~/.reticulum`, `~/.nomadnetwork`, `~/.lxmd`, `~/.rnsh` (uninstall leaves them) | An identity cannot be recreated | **Yes** |
| The record of what ran | `~/.local/state/hammunition/` (transaction log, run logs) | Lets you see what was installed and when | Contains command output; check before sharing |

Not worth saving: `~/.cache/hammunition/` (downloads and build scratch, safe to
clear), `/usr/local/share/hammunition/` (installed software and data; it comes
back by reinstalling), and the catalog (it is in the git checkout).

Copying the download cache to another machine is **not** a documented way to
avoid downloads. For that, use a [LAN mirror](../guides/lan-mirror.md).

## Saving

Keep the archive on media you control and encrypt it if it leaves your hands.

```sh
mkdir -p ~/hammunition-backup && chmod 700 ~/hammunition-backup
cd ~ && tar -czf ~/hammunition-backup/config-$(date +%F).tar.gz \
  .config/hammunition .local/share/hammunition/overlays .config/pat
sudo cp -a /etc/direwolf.conf /etc/bpq32.cfg /etc/hammunition-hill ~/hammunition-backup/ 2>/dev/null
hammunition station show        # the values, with names of regions withheld
```

Adjust the list to what you use. `tar` will complain about a path that does
not exist; remove it from the command. The `mesh-identities` archive command
in [Mesh and Reticulum](../guides/mesh-and-reticulum.md) is the one to use for
those identities.

## Recovering onto a fresh or rebuilt machine

1. Install the engine from the git checkout ([installation](../getting-started/installation.md)); `hammunition doctor`.
2. Restore the saved configuration into the same paths:

    ```sh
    cd ~ && tar -xzf /path/to/config-YYYY-MM-DD.tar.gz
    chmod 600 ~/.config/hammunition/station.yml
    hammunition station show
    ```

3. Reinstall the profiles you used, plan first: `hammunition install station --dry-run`, then the rest. Station values are already set, so configuration files are written, and any existing file is copied to a `.hammunition-backup` first.
4. Re-apply hardware rules: `hammunition hardware apply`.
5. Re-fetch data. With a Bunker, point at it first (`hammunition station set --mirror URL`); otherwise it downloads from the publishers. Rebuild layers: `hammunition maps infra import --from-osm`; your repeater layer is restored with the overlay directory.
6. Put back any hand-edited config you saved (a later install rewrites a file from station config; the first backup is kept).
7. Run the [rehearsal](preparation-checklist.md#c-the-rehearsal-with-networking-off).

## Moving between machines

The same steps move a station. Station values are per user. Reinstalling is
the supported way to copy software: do not copy `/usr/local/share/hammunition`
between machines.

## Not verified

This procedure has not been run end to end as a restore. The individual
pieces (station file location and mode, overlay directory, backup of existing
config files on install) are as documented in the [command
reference](../reference/cli.md) and the package pages.
