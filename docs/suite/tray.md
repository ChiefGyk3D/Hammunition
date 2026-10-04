<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Hammunition Tray

## At a glance

| | |
|---|---|
| **Repository** | <https://github.com/ChiefGyk3D/hammunition-tray> |
| **Purpose** | A system-tray switch for each parkable device (GPS, cellular modem, Bluetooth, camera), a Services group (GPS daemon, clock, GPS tether, rig service), a Radios group (mobile broadband, Wi-Fi, Bluetooth) and a Time section for the GPS-time modes |
| **Status** | v0.5.0 pinned by the catalog. Two front ends from one repository: a KDE Plasma applet and a Qt tray. The Qt tray's manifest says it is not yet run on any of the desktops it lists |
| **Platforms** | `hammunition-tray`: KDE Plasma 6. `hammunition-tray-qt`: Xfce, LXQt, LXDE, MATE, Cinnamon with a system tray. GNOME and COSMIC: none yet, use the terminal commands |
| **Independent?** | No. It reads the lists `hammunition hardware apply` writes and calls the engine's helper through polkit |
| **Report problems** | [Issues on hammunition-tray](https://github.com/ChiefGyk3D/hammunition-tray/issues). For "the switch does nothing", run `hammunition hardware state` first: the tray shows what that reports |

## What it is for

A field station spends most of its day with something running that nobody is using: a GPS drawing power, a modem searching for a tower. The tray is one click and one password prompt for what `hammunition hardware park NAME`, `wake NAME` and `hammunition services` do from a terminal. It does exactly what those do and nothing else. The how-to, including which switch asks for a password, is [The tray's Controls panel](../guides/tray-controls.md), which owns those details.

## Dependencies

- **Software:** the engine; a polkit authentication agent running in your session; the helper and polkit action the tray unit installs. The engine's virtualenv must not be writable by any account but its owner: the install asks one `yes` that `--yes` cannot answer when it belongs to one account, and refuses when any account can write it.
- **Hardware:** a device only gets a switch when its catalog entry carries a `power_control` block and it is plugged in.
- **Network:** none at run time.

## Install and first run

```sh
hammunition hardware apply --dry-run     # read it
hammunition hardware apply
hammunition install hammunition-tray     # KDE Plasma
hammunition install hammunition-tray-qt  # Xfce, LXQt, LXDE, MATE, Cinnamon
```

Both are in the `station` profile; each defers itself by name on a desktop it does not serve. On Plasma, add *Hammunition Devices* to the panel or to the System Tray's shown items; nothing places it for you. Plasma keeps an old applet loaded after an upgrade until `systemctl --user restart plasma-plasmashell` or a new login.

## Basic usage

Plug in a catalogued GPS receiver. Its switch appears in the tray. Switch it off: the device detaches, the kernel drops it and its port can suspend. Switch it on again to bring it back. The tray icon goes grey while anything is parked. Terminal equivalents:

```sh
hammunition hardware state
hammunition hardware park NAME
hammunition hardware wake NAME
hammunition services
```

Unit pages with the generated install detail: [hammunition-tray](../packages/hammunition-tray.md), [hammunition-tray-qt](../packages/hammunition-tray-qt.md).

## Offline behaviour

Entirely local. Note the Radios group: switching Wi-Fi, mobile broadband or Bluetooth off is what disconnects them, so leave them on until you intend otherwise.

## Troubleshooting

- *No switches:* the lists are missing; run `hammunition hardware apply`.
- *"Device control is not installed":* the helper is missing; reinstall the tray unit.
- *Password prompt never appears:* no polkit agent in the session.
- *Old behaviour after upgrade on Plasma:* restart plasmashell as above.
- A per-user copy from the tray repository's own `install.sh` shadows the packaged one; run that repository's `uninstall.sh` once.

## Where the details live

The tray's code and its own changelog are in its repository. Which device may be parked and by what method is catalog data in this repository (`power_control`; [Park and wake devices](../hardware/power-control.md)). The lists the helper reads are [documented here](../reference/devctl-lists.md).

## Not verified

The Qt tray on Xfce, LXQt, LXDE, MATE and Cinnamon; left click on Wayland. See [desktops](../desktops.md).
