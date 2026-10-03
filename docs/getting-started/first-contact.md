<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# First contact

The standard this project holds itself to: a licensed ham with moderate Linux
experience gets from a fresh install to a working digital-modes station without
asking anyone a question or reading a forum thread. This page is that last
stretch — from installed software to a decode on the waterfall.

It is the short version. Two guides carry the long one:
[FT8 and the digital modes](../guides/digital-modes.md) walks rig control, the clock,
your callsign in each program, the first FT8 QSO, PSK31, RTTY and JS8Call;
[Radio audio](../guides/audio-routing.md) covers the sound path between
radio and program on PipeWire, levels and the ALC trap, and its own list of
audio symptoms.

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

1. **Check the clock.** `timedatectl` should say *System clock synchronized:
   yes*. FT8 decodes nothing, with no error, when the clock is a second
   out; [Time and position](../guides/time-and-gps.md) covers a station with
   no network.
2. **Set your callsign and grid** if you have not: `hammunition station set
   --callsign … --grid-square …`. WSJT-X asks for them on first run too;
   [Your callsign in each program](../guides/station-settings.md) lists
   where every program wants them.
3. **Rig control.** Say which radio you have
   (`hammunition station set --rig …`, then `hammunition install rig-service`)
   and WSJT-X talks to it as *Hamlib NET rigctl* at `127.0.0.1:4532`; or start
   flrig, select your radio and choose *FLRig* in WSJT-X. Either way exactly
   one program holds the serial port and everything else asks it, so there is
   no second CAT cable fight. [Rig control](../guides/rig-control.md) walks
   both.
4. **Audio routing.** In your sound settings, confirm the interface appears as
   both an input and an output device. In WSJT-X's Settings → Audio, select it
   for both. The waterfall should come alive with the band's noise. Finding
   which device is the radio, and keeping it from becoming the desktop's
   default output, is in
   [Radio audio](../guides/audio-routing.md#2-which-device-is-the-radio).
5. **PTT.** WSJT-X → Settings → Radio: set PTT to CAT (through the rig
   service or flrig) or a serial line. Test with the **Tune** button — the radio should key and show
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
  interface shows input level in your OS sound settings first; the
  [audio symptoms list](../guides/audio-routing.md#8-when-it-goes-wrong)
  goes further.
- **Signals on the waterfall, no decodes** → the clock. FT8 needs it within
  about a second; see
  [the time section](../guides/digital-modes.md#3-time-the-clock-must-be-right).
- **Decodes but Tune does not key the radio** → PTT. Wrong CAT setting or
  serial line; first read the frequency back through the program that owns the
  port (`rigctl -m 2 -r 127.0.0.1:4532 f`, or flrig's own panel), then see
  [Rig control](../guides/rig-control.md#when-it-does-not-work).
- **`dialout` permission errors on the serial device** → you were added to the
  group at install, but group membership needs a fresh login. Log out and back
  in.
- **On Wayland, a ham GUI misbehaves** (blank window, no decorations — WSJT-X
  on a Pi is the classic) → switch the session to X11. This is accumulated
  operational knowledge, not a bug in the software.

- **Decodes appear, but only a few, and the time column looks wrong** → the
  clock. `timedatectl`.

Each step above has a full guide: [rig control](../guides/rig-control.md),
[radio audio](../guides/audio-routing.md), and [FT8 and the digital
modes](../guides/digital-modes.md), which goes on to JS8Call and fldigi.
Deeper symptom-first help lives in the [troubleshooting
section](../troubleshooting/index.md); each program's [package
page](../packages/index.md) carries its own known problems and where to get
real support for it.

Back: [Your first profile](first-profile.md). Next: [the
guides](../guides/index.md), one task each.
