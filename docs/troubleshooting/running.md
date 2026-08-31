<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# When something is installed but misbehaves

## <a name="wayland"></a>A GUI comes up blank, or without window decorations

Ham GUI applications and Wayland do not always get along. The classic is
**WSJT-X on a Raspberry Pi**: it comes up with no border and no decorations
under Wayland. Other Qt applications may come up blank.

The reliable fix is to run an **X11** session instead of Wayland. On a
Raspberry Pi:

```
sudo raspi-config
  → 6 Advanced Options → A6 Wayland → W1 Openbox with X11 backend
  → reboot
```

On a desktop, choose an "on Xorg" session at the login screen. For a single
Qt application without switching the whole session, exporting
`QT_QPA_PLATFORM=xcb` before launching it often does the job.

This is accumulated operational knowledge — AHRL learned it over years and it
is captured here rather than rediscovered in the field. It is not a bug in the
software.

## <a name="dialout"></a>Permission denied on a serial device

```
could not open /dev/ttyUSB0: Permission denied
```

Serial devices (programming cables, CAT interfaces, GPS, TNCs) belong to the
`dialout` group. Profiles that touch serial hardware add you to it at install
— but **group membership only applies to a new login session.** Log out and
back in (or reboot), and the device opens.

Confirm you are in the group with `id -nG | tr ' ' '\n' | grep dialout`. If you
are, it is purely the stale-session problem; if you are not, the profile that
needed it was not installed.

## <a name="local-bin"></a>A venv-installed program is "not found"

Programs installed into a per-user virtualenv (not1mm, NanoVNASaver, and the
run-in-place Python units) get a small wrapper in `~/.local/bin`. Debian-family
shells add that directory to `PATH` **when it exists** — but a shell that was
already open before the first such install has the old PATH.

Open a new shell, or `source ~/.profile`. The wrapper is there; the shell just
has not looked since it appeared.

## <a name="config"></a>A program starts and immediately asks for a config file

```
CRITICAL: Config file station.cfg does not exist!
```

Some units (radiosonde-auto-rx is the example) install their whole tree but
need a station-local configuration you write once — location, upload
credentials, the things beyond the callsign/grid the engine already manages.
The program's page under [`docs/packages/`](../packages/index.md) says which
file and where; copy the shipped `*.example`, edit it, done. This is expected
first-run setup, not a broken install.
