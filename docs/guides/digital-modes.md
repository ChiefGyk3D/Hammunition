<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# FT8 and the digital modes

From an installed station to a decode, then to a contact. FT8 first,
because it is the mode with the most activity and the fastest feedback:
with the radio on a working antenna, a correctly wired station decodes
dozens of stations in its first fifteen seconds.

[First contact](../getting-started/first-contact.md) is the short version of
this page. This one explains each step and covers JS8Call and fldigi too.

## Before you start

Four things have to be right before any digital mode works. Each has its
own guide; do them first.

1. **Rig control** — one program owns the radio's port. [Rig control
   (CAT)](rig-control.md).
2. **Audio** — the radio's sound card chosen by name, levels set. [Radio
   audio](audio-routing.md).
3. **The clock** — within a second. `timedatectl` says *synchronized*, or
   see [Time and position](time-and-gps.md).
4. **Your callsign and grid** in each program. [Your callsign in each
   program](station-settings.md).

## Install

```sh
hammunition install station digital-modes --dry-run
hammunition install station digital-modes
```

The [`digital-modes`](../profiles/digital-modes.md) profile carries the
WSJT-X family (WSJT-X, JTDX, MSHV), JS8Call, the fldigi family, QSSTV for
SSTV, FreeDV for digital voice on HF, and a handful of decoders. WSJT-X is
built from source at a pinned release, so the install takes a while; the
plan says which units are builds before anything runs.

## FT8 with WSJT-X

### Settings, once

Open WSJT-X, then **File → Settings**.

- **General:** My Call and My Grid. Your own.
- **Radio:** Rig *Hamlib NET rigctl*, Network Server `127.0.0.1:4532` (or
  *FLRig FLRig* on `127.0.0.1:12345` if flrig owns the radio). PTT Method
  *CAT*. Mode *Data/Pkt* if your radio has a data mode, otherwise *USB*.
  Split Operation *Fake It* or *Rig*: either keeps your transmit audio in the
  radio's clean passband. Press **Test CAT**: it turns green when WSJT-X can
  reach the radio.
- **Audio:** the radio's sound card for both Input and Output, by name.

### The first decode

1. Choose **20 m** from the band list at the lower right. WSJT-X sets the
   radio to 14.074 MHz USB through CAT.
2. The waterfall fills with band noise. Set the receive level so the meter
   at the lower left reads about **30 dB**.
3. Wait for the next 15-second cycle to end. Decodes appear in the *Band
   Activity* pane: the time, the signal report, the offset in Hz, and the
   message, like `CQ N0CALL FN31`.

If nothing decodes after two or three cycles on a band that should be
open: check the clock first, the input device second.

Common FT8 dial frequencies, all USB, as WSJT-X ships them:

| Band | 80 m | 40 m | 30 m | 20 m | 17 m | 15 m | 10 m | 6 m |
|---|---|---|---|---|---|---|---|---|
| MHz | 3.573 | 7.074 | 10.136 | 14.074 | 18.100 | 21.074 | 28.074 | 50.313 |

### The first contact

A licence is needed to transmit. Receiving needs none.

1. Set the transmit level first: **Tune**, then lower the *Pwr* slider
   until the radio's ALC meter stops moving. [Radio
   audio](audio-routing.md#5-set-the-transmit-level) explains why.
2. Double-click a line that starts `CQ`. WSJT-X fills in the station, picks
   the right message and enables transmit.
3. It runs the exchange for you: your grid, then reports both ways, then
   `RR73` and `73`. Watch the *Rx Frequency* pane on the right.
4. When the log dialog appears, OK saves the contact to `wsjtx_log.adi`,
   which every logger can import.

## JS8Call: conversation instead of exchanges

[JS8Call](../packages/js8call.md) uses FT8's modulation for free text:
messages, relays through other stations, and a heartbeat that shows who
can hear whom. Its settings mirror WSJT-X's (Settings → Radio, Settings →
Audio, Settings → General → Station). The common frequencies are 7.078 and
14.078 MHz USB. Run it or WSJT-X, not both: they share the radio and the
sound card.

## fldigi: PSK31, RTTY and the keyboard modes

[fldigi](../packages/fldigi.md) is the program for the modes you type
into: PSK31, RTTY, Olivia, MT63, and the NBEMS family that moves forms and
files over the air.

1. **Configure → Operator:** callsign, name, locator.
2. **Configure → Sound Card → Devices:** the radio's capture and playback.
3. **Configure → Rig Control:** *Hamlib* with `127.0.0.1:4532`, or the
   *flrig* tab.
4. Choose **Op Mode → PSK → BPSK31**, tune to 14.070 MHz USB, and click on a
   trace in the waterfall. Decoded text scrolls in the receive pane.

Transmit is typing into the lower pane and pressing **T/R**. The same ALC
rule applies: no ALC action.

## Other modes on the profile

| Mode | Program | Guide |
|---|---|---|
| SSTV (pictures) | [QSSTV](../packages/qsstv.md) | its own manual; audio as above |
| FreeDV (digital voice on HF) | [FreeDV](../packages/freedv.md) | it has two audio paths, radio and headset; see its Tools → Audio Config |
| Weather fax | [xwefax](../packages/xwefax.md), or fldigi's WEFAX mode | receive only |
| NBEMS messages | [flmsg](../packages/flmsg.md), [flamp](../packages/flamp.md) | run through fldigi |

## When it does not work

- **Decodes nothing, waterfall busy** → the clock. `timedatectl`.
- **Decodes, but nobody answers** → transmit audio level or the wrong
  output device. Check your own signal on a public receiver: a
  [PSK Reporter](https://pskreporter.info/pskmap.html) map shows who heard you.
- **Test CAT stays red** → [Rig control](rig-control.md).
- **The window is blank or has no title bar** → Wayland; see
  [Troubleshooting](../troubleshooting/running.md#wayland).
- **Two FT8 programs open** → they fight over the sound card and the radio.
  One at a time.

## What was measured

The profile's members were read from the catalog. The WSJT-X settings,
frequencies and QSO sequence follow WSJT-X's own user guide; this project's
[digital-modes VM campaign](../reference/vm-campaign-digital-modes.md)
covers the install, and a contact on air from the field laptop has not yet
been recorded in the [bench record](../reference/bench-verification-5430.md).
