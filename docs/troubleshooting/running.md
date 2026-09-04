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

## <a name="ax25"></a>"Address family not supported by protocol" from a packet program

```
kissattach: Address family not supported by protocol
OSError: [Errno 97] Address family not supported by protocol
modprobe: FATAL: Module ax25 not found in directory /lib/modules/7.1.5-…
```

Your kernel has no AX.25 stack. **Linux 7.1 removed it** — `net/ax25`,
NET/ROM, Rose and every `drivers/net/hamradio` driver, in one merge on
2026-04-24 — so on a 7.1 or newer kernel there is no `ax25` module to load and
nothing for `kissattach` to attach a TNC to. Check with:

```
uname -r
ls /lib/modules/$(uname -r)/kernel/net/ax25/
```

A directory with `ax25.ko` (or `.ko.xz`, `.ko.zst`) in it means the kernel
carries the stack and the module is merely not loaded yet — `sudo modprobe
ax25`, or run `kissattach` as root, which autoloads it. No such directory
means the kernel does not have it, and no package fixes that.

What still works: the **userspace** packet path. Direwolf's KISS and AGW ports
serve pat (`ax25+agwpe://`), LinBPQ, YAAC and Xastir's AGWPE interface with no
kernel AX.25 at all. What does not: `axports`, `kissattach`, `ax25d`,
`listen`, `mheard`, NET/ROM — everything in `ax25-tools` and `ax25-apps`, and
the programs that sit on them (`linpac`, `uronode`, `fbb`, `aprsdigi`).

Hammunition reads the running kernel at plan time and will refuse or defer
those units by name on such a kernel, so the usual way to meet this is
`hammunition install packet` on Kali (7.1.5) or a Pop!_OS machine on its
current kernel — and the plan says which members it withheld and why. The
measurements, and which units are affected, are in
[`docs/reference/kernel-ax25.md`](../reference/kernel-ax25.md). If you need a
kernel port, boot a kernel that still carries the stack: Debian 13's 6.12,
Parrot 7.3's 7.0, Ubuntu 26.04's 7.0. Hammunition does not build kernel
modules.
