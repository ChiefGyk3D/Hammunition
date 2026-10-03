<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Your first profile

A profile is a named bundle of software that belongs together. Install the
bundle, not two dozen packages by hand. Profiles are flat tags — they overlap
(gpsd is in both `station` and `navigation`) but never nest, so you compose
them freely.

Every command here runs the engine as `hammunition`, which `./bootstrap.sh`
put on your PATH. If the shell says `command not found`, run the checkout's
`.venv/bin/hammunition` by its full path instead;
[installing the engine](install.md) says why and how to fix it.

## Start with `station`

`station` is the floor every setup stands on: rig control, time, and position.
Nothing mode-specific, nothing that assumes what you operate.

```sh
hammunition install station --dry-run   # read it first
hammunition install station             # then do it
```

It installs hamlib (the library every rig-control program speaks through),
flrig, `rig-service` (one shared `rigctld` for your radio, once you have said
which radio it is, below), CHIRP for programming handhelds, the gpsd stack for
a GPS receiver, a couple of clocks, the project's own dashboard, and the tray
switches for your desktop. `hammunition show station` lists every member and
why it is there. A member your machine cannot take (the Plasma applet on an
Xfce desktop, say) is deferred by name and the rest installs.

## Tell the engine who you are

Some software writes configuration templated with your callsign, grid square
and packet node alias — a Winlink node transmits, and its identity is yours,
so **nothing is invented**. Set your values once:

```sh
hammunition station set --callsign N0TST --grid-square FN31pr
```

Use your own callsign and grid; `N0TST` and `FN31pr` are placeholders.
Saved to `~/.config/hammunition/station.yml`, mode 0600. An interactive install
that needs a value you have not set will offer to prompt for it; a value left
blank simply defers the one file that needed it and installs everything else
(a profile does not refuse because one file wants a callsign).

## Tell it which radio you have

If you control a radio from the computer (CAT), say which one once, and the
`rig-service` that came with `station` runs one shared `rigctld` for every
program. `rig-service` waits for this, so until you do it is reported as
deferred, and that is not a failure:

```sh
hammunition station set --rig yaesu-ft-991a --rig-device /dev/serial/by-id/usb-... --rig-baud 38400
hammunition install rig-service
```

[Rig control](../guides/rig-control.md) finds the port, the model number and
the baud rate, and covers a radio with no CAT and the flrig route.

## Then the hardware step

```sh
hammunition hardware apply --dry-run
hammunition hardware apply
```

This writes the udev rules for the devices the catalog knows, adds you to the
groups they need (log out and back in afterward), and writes the lists the
tray switches read ([the tray's Controls
panel](../guides/tray-controls.md)). It prints every file first.

## Then a mode profile

Pick what you operate. The big one:

```sh
hammunition install digital-modes --dry-run
```

The fldigi/NBEMS family, WSJT-X and its forks for FT8, MSHV, JS8Call,
FreeDV, and the decoders. Several build from source — the plan shows
you which, and the build dependencies come from apt before any compiler runs.
This is a real install with real compile time; read the plan, then let it run.

Other profiles worth knowing (`hammunition list profiles` shows them all):

- **`packet`** — the EMCOMM core: Direwolf, the AX.25 stack, Pat for Winlink,
  BPQ, ARDOP, Xastir. Offers you a mail client if you do not already run one.
- **`sdr`** — SDR++, GQRX, CubicSDR, GNU Radio, the SoapySDR device modules.
- **`listening`** — aeronautical and maritime decoders (ACARS, HFDL, VDL2,
  AIS), remote-SDR clients. No transmit, no hardware needed to start.
- **`workstation`** — the general tools a station machine wants, and a
  serial-terminal picker (PuTTY and friends) for rig consoles.
- **`rf-security`** / **`rf-research`** — SIGINT and RF-security tooling,
  **behind an explicit consent gate**. `hammunition show rf-research` prints
  the full disclosure before you ever install; you affirm it deliberately, and
  `--yes` cannot affirm it for you.

## What a profile tells you

`hammunition show <profile>` prints, without installing anything: what it
installs and why those things belong together, its disk footprint, what it
deliberately leaves out, and what you still have to configure by hand
afterward. Read it before a profile you do not know.

## Then a guide

The [guides](../guides/index.md) take each kind of operating from here to
working: [rig control](../guides/rig-control.md), [radio
audio](../guides/audio-routing.md) and [the clock](../guides/time-and-gps.md)
first, then [FT8](../guides/digital-modes.md),
[Winlink](../guides/packet-winlink.md), [APRS](../guides/aprs.md), [SDR
listening](../guides/sdr.md) or [satellites](../guides/satellite.md).
