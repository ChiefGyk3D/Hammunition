<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Your first profile

A profile is a named bundle of software that belongs together. Install the
bundle, not two dozen packages by hand. Profiles are flat tags — they overlap
(fldigi is in both `digital-modes` and `nbems`) but never nest, so you compose
them freely.

## Start with `station`

`station` is the floor every setup stands on: rig control, time, and position.
Nothing mode-specific, nothing that assumes what you operate.

```sh
hammunition install station --dry-run   # read it first
hammunition install station             # then do it
```

It installs hamlib (the library every rig-control program speaks through),
flrig, CHIRP for programming handhelds, the gpsd stack for a GPS receiver, and
a couple of clocks. Ten packages, all from apt on every target, one command.

## Tell the engine who you are

Some software writes configuration templated with your callsign, grid square
and packet node alias — a Winlink node transmits, and its identity is yours,
so **nothing is invented**. Set your values once:

```sh
hammunition station set --callsign M0ABC --grid-square IO91wm
```

Saved to `~/.config/hammunition/station.yml`, mode 0600. An interactive install
that needs a value you have not set will offer to prompt for it; a value left
blank simply defers the one file that needed it and installs everything else
(a nineteen-package profile does not refuse because one file wants a callsign).

## Then a mode profile

Pick what you operate. The big one:

```sh
hammunition install digital-modes --dry-run
```

Twenty-one units: the fldigi/NBEMS family, WSJT-X and its forks for FT8, MSHV,
JS8Call, FreeDV, and the decoders. Several build from source — the plan shows
you which, and the build dependencies come from apt before any compiler runs.
This is a real install with real compile time; read the plan, then let it run.

Other profiles worth knowing (`hammunition list profiles` shows all fifteen):

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
