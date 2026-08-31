<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# First contact

The standard this project holds itself to: a licensed ham with moderate Linux
experience gets from a fresh install to a working digital-modes station without
asking anyone a question or reading a forum thread. This page is that last
stretch — from installed software to a decode on the waterfall.

## The chain you are building

A digital-modes station is four things wired together:

1. **The radio**, on a band with activity (20 m and FT8 is the reliable first
   test — 14.074 MHz).
2. **Audio** between radio and computer, both directions. A sound-card
   interface or a Digirig-class device. This is the part that most often needs
   attention: the computer must *hear* the radio and be able to *talk back*.
3. **PTT** — how the software keys the radio. CAT (through hamlib/flrig), a
   serial line, or VOX.
4. **The software** — WSJT-X for FT8, from the `digital-modes` profile.

## Wire it up

After `hammunition install station digital-modes`:

1. **Set your callsign and grid** if you have not: `hammunition station set
   --callsign … --grid-square …`. WSJT-X asks for them on first run too.
2. **Rig control.** Start flrig, select your radio, confirm it reads and sets
   frequency. WSJT-X then talks to the radio through flrig — no second CAT
   cable fight.
3. **Audio routing.** In your sound settings, confirm the interface appears as
   both an input and an output device. In WSJT-X's Settings → Audio, select it
   for both. The waterfall should come alive with the band's noise.
4. **PTT.** WSJT-X → Settings → Radio: set PTT to CAT (via flrig/hamlib) or a
   serial line. Test with the **Tune** button — the radio should key and show
   output into a dummy load or antenna.

## The first decode

Tune to 14.074 MHz USB, watch WSJT-X's waterfall for the FT8 signature (evenly
spaced tones in fifteen-second cycles), and let it run a cycle. Decodes appear
in the left pane: callsign, grid, signal report. That is first contact with the
mode — you are hearing the band.

Answering a CQ is one double-click, but hearing decodes first proves the whole
chain works receive-side before you transmit.

## When the waterfall is silent

Symptom-first, because that is how trouble actually presents:

- **Waterfall flat, no noise** → the computer is not hearing the radio. Wrong
  input device in WSJT-X, or audio cable in the wrong jack. Confirm the
  interface shows input level in your OS sound settings first.
- **Decodes but Tune does not key the radio** → PTT. Wrong CAT setting or
  serial line; test flrig can key the radio on its own.
- **`dialout` permission errors on the serial device** → you were added to the
  group at install, but group membership needs a fresh login. Log out and back
  in.
- **On Wayland, a ham GUI misbehaves** (blank window, no decorations — WSJT-X
  on a Pi is the classic) → switch the session to X11. This is accumulated
  operational knowledge, not a bug in the software.

Deeper symptom-first help lives in the troubleshooting section; the
per-package pages under `docs/packages/` carry each program's own known
problems and where to get real support for it.
