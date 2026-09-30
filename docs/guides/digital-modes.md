<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Digital modes: from installed to first contact

The standard this project holds itself to: a licensed ham with moderate
Linux experience gets from a fresh Parrot install to a working
digital-modes station without asking anyone. The `digital-modes` profile
installs the programs; this page is everything after that, in the order
that works: **rig control first, then audio, then the clock, then your
callsign in each program, then the first FT8 contact**, and after that
PSK31 and RTTY in fldigi, and JS8Call.

[First contact](../getting-started/first-contact.md) is the short version
of this page. [Audio routing](audio-routing.md) is the long version of step
2, and has its own troubleshooting list.

This page closes gap A9.1 of `docs/reference/catalog-gaps-2026-09.md`, and
carries the "enter your callsign and grid once per program" instructions
that gap A1 assigned to a page rather than a config block: WSJT-X, fldigi
and JS8Call rewrite their own settings files on exit, so Hammunition does
not template them (Q-022 item 1).

**What was measured, and on what.** Read-only, on the field laptop (Dell
Latitude 5430 Rugged, Parrot 7.3, `docs/reference/bench-verification-5430.md`),
2026-09-29: which of these programs are installed and at what path, the
hamlib model numbers (`rigctl -l`, hamlib 4.7.2), the libraries each
program loads, the config file names that appear inside the binaries, and
how the laptop keeps time. **No radio was connected and no program's window
was opened** for this page. The dialog paths (File → Settings and so on)
are from each program's own documentation and are marked where they
appear; so are the config file locations that could not be read from the
binary. Nothing here says a QSO was made from the bench.

The callsign and grid in the examples are placeholders: `N0CALL`, `FN31pr`.

---

## 0. Install

```
hammunition install station digital-modes --dry-run
hammunition install station digital-modes
hammunition station set --callsign N0CALL --grid-square FN31pr
```

Read the dry run first: five of the `digital-modes` programs are source
builds (fldigi, WSJT-X, MSHV, glfer, xwefax), so it is a long install, and
the plan says what each step does. Log out and back in afterwards so the
`dialout` group membership the plan added takes effect
([why](../troubleshooting/running.md#dialout)).

The station values are stored in `~/.config/hammunition/station.yml`,
readable only by you. Today they fill in LinBPQ's configuration and nothing
in this profile; the programs below each ask for them once (§4).

---

## 1. Rig control: one program owns the CAT port

A radio has one CAT (computer control) port, and a station has several
programs that want it: WSJT-X, fldigi, a logger. If two of them open the
serial port directly, the radio behaves erratically and nothing reports an
error (the `flrig` and `libhamlib-utils` manifests both say so). The fix is
to let **one** program own the port and point the rest at it. The catalog
gives you two:

| Owner | Carried as | What the other programs select |
|---|---|---|
| **`rigctld`**, hamlib's daemon | `libhamlib-utils` (in `station`) | *Hamlib NET rigctl*, `localhost:4532` (hamlib model 2) |
| **flrig**, a front panel with an XML-RPC server | `flrig` (in `station` and `digital-modes`) | *FLRig* (hamlib model 4), or fldigi's own flrig interface |

Pick flrig if you want a window with the radio's controls; pick `rigctld`
if you want nothing on screen. Both work with every program on this page.
Hammunition does not start either for you yet — running one `rigctld` as a
service from station config is gap report A2, not built.

### Find the radio's serial port

Use the stable name, never `/dev/ttyUSB0` (the number is whatever order
devices were found in):

```
ls -l /dev/serial/by-id/
```

A radio with a built-in USB interface often shows **two** serial ports. On
Yaesu radios with a CP2105 chip (the FT-991A among them), Yaesu's
documentation names the *Enhanced* port (the `-if00-` one) for CAT and the
*Standard* port (`-if01-`) for PTT and keying lines. That split was not
measured on the maintainer's FT-991A for this page; check it against your
radio's manual. A Digirig shows one port; a SignaLink shows none, because it
keys by VOX. `docs/reference/device-naming.md` is the measured account of
what `/dev/serial/by-id/` does and does not name.

### Test with `rigctl` before you blame a program

Find your radio's model number (measured on the laptop: the FT-991 family
is `1035`, the IC-7300 is `3073`, the FT-891 is `1036`):

```
rigctl -l | grep -i 'ft-991'
```

Then set the radio's **CAT RATE** menu and use the same number here:

```
rigctl -m 1035 -r /dev/serial/by-id/usb-…-if00-port0 -s 38400 f
```

It prints the dial frequency in hertz. If it does, the cable, the port, the
baud rate and the model are right, and anything that fails later is a
program setting. If it does not: wrong model (the closest-looking one is
often wrong), wrong baud, or for Icom radios a wrong CI-V address (see the
`libhamlib-utils` page under `docs/packages/`).

### Run the owner

**`rigctld`**, in a terminal you leave open:

```
rigctld -m 1035 -r /dev/serial/by-id/usb-…-if00-port0 -s 38400
```

and from another terminal, through it:

```
rigctl -m 2 f
```

**flrig**: start it, choose the radio and serial port in its configuration
(Config → Setup → Transceiver, per flrig's documentation), and confirm the
frequency display follows the radio's dial.

### PTT: how the program keys the radio

| Method | When | Select in the program |
|---|---|---|
| **CAT** | Radio with CAT PTT through the owner above | PTT method *CAT* |
| **RTS or DTR** on a serial line | A Digirig's serial port, or the radio's second port | PTT method *RTS* / *DTR*, and that port |
| **VOX** | SignaLink, or no serial line | PTT method *VOX*; the interface keys when audio starts |
| **CM108 GPIO** | Digirig-class sound chips, Direwolf only | `PTT CM108` in `direwolf.conf` |

---

## 2. Audio: radio in, radio out

The whole of this is [Audio routing](audio-routing.md). The minimum, before
the first decode:

1. Find the radio's sound card by difference: `cat /proc/asound/cards`
   before and after plugging the radio in
   ([§2 there](audio-routing.md#2-which-device-is-the-radio)).
2. Make sure the radio is **not** the desktop's default output
   (`wpctl status`; the `*` should be on the laptop's own speakers).
   Otherwise system sounds go out over the air.
3. In each program, choose the radio's card **by name** for both input and
   output.
4. On transmit, watch the radio's **ALC** meter: set power with the power
   control, and bring audio up only until ALC barely moves
   ([the ALC trap](audio-routing.md#transmit-the-alc-trap)).

---

## 3. Time: the clock must be right

FT8, FT4, JS8 and WSPR transmit and decode in fixed time slots. A clock more
than about a second off decodes nothing while everything else appears to
work (the `wsjtx` manifest and the `digital-modes` profile both require
"within about a second"). There is no GPS-time guide yet; gap report A4
plans a `chrony` unit fed by `gpsd`, and until it exists the clock comes
from the network.

Check it before operating:

```
timedatectl
```

`System clock synchronized: yes` and `NTP service: active` are the two
lines that matter. For the actual offset, ask whichever time daemon the
machine runs:

```
ntpq -p            # ntpsec or ntp: the 'offset' column, in milliseconds
chronyc tracking   # chrony: the 'System time' line, in seconds
```

**Measured on the field laptop:** Parrot 7.3 there runs **ntpsec**
(`ntpsec` active, `systemd-timesyncd` inactive, `chronyc` not installed),
and `timedatectl` reports the clock synchronised. Which daemon the other
targets run by default is not recorded.

Offline, the clock drifts: a laptop's real-time clock can pass a second in
days. Sync before you leave the network. In WSJT-X the **DT** column shows
each decode's time offset; if every station reads DT of a second or more
the same way, it is your clock, not theirs.

---

## 4. Enter your callsign and grid once per program

Each of these programs keeps its own settings file and rewrites it when it
exits, so type the values in the program's own dialog, and never edit the
file while the program is running. The dialog paths are from each
program's documentation (not opened on the bench):

| Program | Where | Fields |
|---|---|---|
| **WSJT-X** | File → Settings → General | *My Call*, *My Grid* |
| **JS8Call** | File → Settings → General → Station | *Callsign*, *Maidenhead grid* |
| **fldigi** | First-run wizard, or Configure → Config dialog → Operator | *Callsign*, *Name*, *QTH*, *Locator* |

Use the same callsign and grid you gave `hammunition station set`.

---

## 5. WSJT-X: the first FT8 contact

WSJT-X is the catalog's recommended default of the FT8 family (the
`wsjtx` manifest records the ruling). Start it from the menu or with
`wsjtx`. On first run it asks for your callsign and grid (§4).

**File → Settings → Radio** (per WSJT-X's documentation):

- *Rig*: **Hamlib NET rigctl** with *Network Server* `localhost:4532` if
  `rigctld` owns the port, or **FLRig** if flrig does.
- *PTT Method*: **CAT**, or *RTS*/*DTR* on the serial port that keys, or
  *VOX* for a SignaLink.
- *Mode*: **Data/Pkt** if your radio has a data mode that takes USB audio,
  otherwise *USB*.
- *Split Operation*: **Fake It** or **Rig**. Either keeps your transmit
  audio in the range the radio passes cleanly.
- Press **Test CAT** (it turns green) and **Test PTT** (the radio keys; into
  a dummy load, or a clear frequency).

**File → Settings → Audio**: *Input* and *Output* both the radio's card,
by the name you found in §2.

Then:

1. Choose **20 m** from the band list: the dial goes to **14.074 MHz** USB.
   The other FT8 frequencies are in the same list.
2. Set the receive level to about **30 dB** on the level bar with no
   signals (the WSJT-X guidance; [levels](audio-routing.md#receive)).
3. Watch one 15-second cycle. Decodes appear in the left pane: time, dB,
   DT, frequency and the message. **That is your receive chain working end
   to end** — hearing decodes before you transmit is the check that saves
   an hour.
4. Press **Tune** and set transmit audio against ALC
   ([the ALC trap](audio-routing.md#transmit-the-alc-trap)). Press Tune
   again to stop.
5. **Double-click a CQ** in the left pane. WSJT-X sets up the reply, enables
   transmit, and runs the exchange: your call and grid, the signal reports,
   `RR73`, `73`. When it finishes it offers a **Log QSO** dialog; accept it.

If the waterfall shows signals and nothing decodes, it is the clock (§3).
If the waterfall is flat, it is audio
([symptoms](audio-routing.md#8-when-it-goes-wrong)).

Only one of the FT8 family at a time: `wsjtx`, `jtdx` and `mshv` all want
the same sound card and the same radio.

---

## 6. fldigi: PSK31 and RTTY

fldigi is the keyboard-modes program: PSK31, RTTY, Olivia, MT63 and the
NBEMS messaging stack. The fldigi binary on the laptop offers both
*PortAudio* and *PulseAudio* as sound options (measured, from the strings
in the binary).

**Configure → Config dialog** (per fldigi's documentation):

- *Soundcard → Devices*: choose **PulseAudio** and leave the server string
  empty; pick the radio's card in the per-stream selection, or choose it
  for fldigi's stream in `pavucontrol`/`qpwgraph`. *PortAudio* also works
  and lists the devices by name.
- *Rig Control*: the **flrig** tab if flrig owns the port, or **Hamlib**
  with rig *Hamlib NET rigctl* and device `localhost:4532` if `rigctld`
  does. PTT on the same page.
- *Operator*: your callsign, name, QTH and locator (§4). fldigi's macros
  use them as `<MYCALL>` and the like.

**PSK31** on 20 m lives around **14.070 MHz** USB. Pick *PSK → BPSK-31* from
the Op Mode menu, click a trace on the waterfall to tune it, and text
scrolls in the receive pane. Transmit: type in the lower pane and press
*T/R*, or use the CQ macro. PSK31 is narrow; overdrive (ALC again) shows up
on the waterfall as extra traces either side of yours.

**RTTY** is traditionally sent as 45.45 baud, 170 Hz shift; fldigi's default
RTTY settings match that. On 20 m it sits above the PSK31 activity, roughly
**14.080 to 14.090 MHz**, busiest during contests. Click between the two
tones on the waterfall.

Both frequencies are the conventional activity areas, not a band plan;
your country's band plan governs.

---

## 7. JS8Call: keyboard messaging on the FT8 modem

JS8Call uses FT8's modulation for real text conversations and
store-and-forward messages. It shares WSJT-X's heritage, so its settings
look similar (per its documentation):

- **File → Settings → Radio**: the same *Rig*, *PTT* and *Mode* choices as
  WSJT-X (§5).
- **File → Settings → Audio**: the radio's card for input and output.
- **File → Settings → General → Station**: callsign and grid (§4).

The 20 m JS8 dial frequency is **14.078 MHz** USB. JS8Call needs the clock
right exactly as FT8 does (§3), and it should not run at the same time as
WSJT-X on the same radio.

On Ubuntu 24.04 (and Mint 22.3 and Pop!_OS 24.04 on the same base) the
catalog installs the distribution's older JS8Call 2.2.0, because JS8Call 3
needs Qt 6.5; the settings described here may be laid out differently in
that version (the `js8call` manifest records why).

---

## 8. What each program writes, and where

So you can back it up, move it to another machine, or know what to delete
when a program's settings go wrong. Hammunition writes none of these files
(Q-022 item 1). *Measured* means the file name is in the program's own
binary or shipped example on the field laptop; the rest are from the
programs' documentation, and none of these files existed on the laptop,
because none of the programs has been run there.

| Program | Settings | Logs and data | Source |
|---|---|---|---|
| **WSJT-X** | `~/.config/WSJT-X.ini` | `~/.local/share/WSJT-X/`: `wsjtx_log.adi` (your QSOs, ADIF), `ALL.TXT` (every decode) | Documentation |
| **JS8Call** | `~/.config/JS8Call.ini` | `~/.local/share/JS8Call/`: `js8call_log.adi`, `ALL.TXT`, `DIRECTED.TXT` | Documentation |
| **fldigi** | `~/.fldigi/fldigi_def.xml` | `~/.fldigi/`: `logs/` (logbook), `macros/` | `.fldigi/` and `fldigi_def.xml` measured in the binary; subfolders documentation |
| **flrig** | `~/.flrig/`, one prefs file per radio | Debug and trace files in the same folder | Folder measured (it exists on the laptop, holding only debug and trace files); prefs file documentation |
| **Direwolf** | `direwolf.conf` in the directory you start it from, then your home directory; or the file given with `-c` | Optional log directory set in the file | Measured, from the shipped example's own text |
| **`rigctld`** | None: everything is on its command line | None | — |

For WSJT-X, JS8Call and fldigi, change settings through the program, and
if you must edit the file, quit the program first: it writes its whole
settings file back when it exits. For packet and Winlink, `pat` keeps
`~/.config/pat/config.json` (written by `pat configure`, per its manifest
and documentation), and Direwolf's file is the one above; a packet guide is
gap report A9.2.

---

## When something is wrong

- **Flat waterfall, program hears nothing** → audio:
  [audio routing, symptoms](audio-routing.md#8-when-it-goes-wrong).
- **Signals on the waterfall, no decodes** → the clock (§3).
- **Test CAT fails** → run `rigctl` directly (§1). If `rigctl` works and the
  program does not, the program is set to the wrong rig, or a second program
  holds the serial port.
- **Permission denied on the serial port** → the `dialout` group needs a
  fresh login ([troubleshooting](../troubleshooting/running.md#dialout)).
- **Full power, nobody hears you** → the ALC trap
  ([audio routing](audio-routing.md#transmit-the-alc-trap)).
- **A window comes up blank or without decorations** → Wayland
  ([troubleshooting](../troubleshooting/running.md#wayland)).

## What has not been measured yet

- **No QSO, decode or CAT session has been run from the field laptop** for
  this page. The first-contact walk-through is the programs' documented
  path, not a bench report. When the FT-991A is on the bench, the result
  belongs in `docs/reference/bench-verification-5430.md` first.
- **Every dialog path** (File → Settings and the rest) is from the
  programs' documentation; no GUI was opened.
- **The FT-991A's two-port split** (Enhanced for CAT, Standard for keying)
  is Yaesu's documentation, not measured.
- **Settings and log locations** marked *documentation* in §8.
- **Which time daemon** the targets other than Parrot 7.3 run by default.
