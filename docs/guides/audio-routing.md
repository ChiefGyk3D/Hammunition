<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Radio audio

Every digital mode is sound. FT8, PSK31, RTTY, JS8, packet and SSTV all
reach the computer as audio from the radio's receiver and leave it as
audio into the radio's transmitter. When a digital-modes station does not
work, the cause is more often the audio path than the program, and the
audio path is the one part of the station nothing in the catalog sets up
for you. This page is that part.

It covers what sits between the radio and the program on a 2026 Linux
desktop, how to tell which sound device is the radio, how to see and
change where each program's audio goes, sample rates, levels (and the ALC
trap), and a symptom-first list for when it goes wrong. It is the second
of the four station guides: [Rig control (CAT)](rig-control.md) comes
before it, [Time and position](time-and-gps.md) and [Your callsign in each
program](station-settings.md) after, and [FT8 and the digital
modes](digital-modes.md) puts all four together into a first FT8 QSO.

This page closes gap A3 of `docs/reference/catalog-gaps-2026-09.md`.

**What was measured, and on what.** Everything marked *measured* below was
read on the field laptop (Dell Latitude 5430 Rugged, Parrot 7.3, KDE
Plasma, `docs/reference/bench-verification-5430.md`) on 2026-09-29 with
read-only commands, and **with no radio or USB sound interface attached**.
So the layers, the library each program loads, the PipeWire clock, the
ALSA device names and the command output shapes are measured; everything
about a real rig's USB codec, its levels and its sample rates is not, and
says so where it appears. `pactl` and `pw-loopback`'s options were also
read on Ubuntu 24.04 on 2026-09-30. Which audio packages Debian 13, Kali
and the Ubuntu family install by default has not been checked.

---

## What you need first

- The `station` and `digital-modes` profiles installed, or at least the
  program you mean to run (`hammunition install digital-modes --dry-run`
  shows the plan first).
- **An audio path to the radio**, both directions. One of:
  - a radio with a **built-in USB sound card** — the FT-991A, IC-7300 and
    most current HF rigs: one USB cable carries audio and CAT;
  - a **Digirig**-class interface: a small USB box with a sound chip and a
    USB-serial chip, cabled to the radio's data or mic port;
  - a **SignaLink USB**-class interface: a sound chip and a VOX circuit
    that keys the radio when audio arrives, with no serial port at all;
  - a plain USB sound dongle and a home-made cable.
- The command-line tools used on this page. All of them come from packages
  the field laptop already had installed (measured): `wpctl` from
  `wireplumber`, `pw-cli`, `pw-link`, `pw-top` and `pw-loopback` from
  `pipewire-bin`, `pactl` from `pulseaudio-utils`, `arecord` and `aplay`
  from `alsa-utils`.

---

## 1. The layers: PipeWire and the three doors into it

On Parrot, Debian 13 and Ubuntu 24.04 and later the sound server is
**PipeWire**, with **WirePlumber** deciding what connects to what. Ham
programs were written for older sound systems and do not talk to PipeWire
directly. They come in through one of three compatibility doors, each a
package:

| Door | Package | What uses it |
|---|---|---|
| PulseAudio | `pipewire-pulse` | Anything linked against `libpulse`: WSJT-X and JS8Call through Qt Multimedia, fldigi's PulseAudio option, `pavucontrol` |
| ALSA | `pipewire-alsa` | Anything opening ALSA's `default` device: Direwolf, `arecord`, fldigi's PortAudio option in most setups |
| JACK | `pipewire-jack` | JACK clients; no carried digital-modes program needs it |

Check yours:

```
pactl info | grep 'Server Name'
dpkg -l pipewire pipewire-pulse pipewire-alsa wireplumber pulseaudio
```

**Measured on the field laptop:** `pactl info` reports
`Server Name: PulseAudio (on PipeWire 1.4.9)`; `pipewire`,
`pipewire-pulse`, `pipewire-alsa` and `pipewire-jack` are all 1.4.9 from
Parrot's backports, `wireplumber` is 0.5.12, and the `pulseaudio` daemon
package is **not** installed (only `pulseaudio-utils`, for `pactl`). That is
the healthy shape: one sound server, three doors into it.

> **Do not install the `pulseaudio` package on a PipeWire desktop.** It
> conflicts with `pipewire-alsa`, so apt removes the ALSA door to make room,
> and every ALSA program loses its sound. That is not hypothetical: the
> Debian `morse` package pulled `pulseaudio` in as a Recommends and the
> `morse` profile refused on the field laptop over exactly this (issue #61,
> fixed by declaring the conflict; see the bench page). If a forum answer
> tells you to "reinstall PulseAudio", it was written for a different
> system.

### Which door each program opens

Read from the libraries each installed binary loads (`ldd`, field laptop,
2026-09-29). `ldd` lists every library pulled in, not only the ones the
program calls itself, so "loads" is the accurate word:

| Program | Audio libraries it loads | What that means in practice |
|---|---|---|
| **WSJT-X** 3.0.2 (source build) | `libQt5Multimedia`, `libpulse` | Qt 5 Multimedia's PulseAudio backend: the device list in its Audio settings is PipeWire's, seen through `pipewire-pulse` |
| **JS8Call** 3.0.3 (source build) | `libQt6Multimedia`, `libpulse` | The same, through Qt 6 |
| **fldigi** 4.2.13 (source build) | `libportaudio`, `libpulse`, `libpulse-simple`, `libasound`, `libjack` | Its Configure → Soundcard → Devices page offers a choice; the binary carries both `PortAudio` and `PulseAudio` as option strings. Either works through PipeWire; PulseAudio is the simpler one to point at a named device |
| **Direwolf** 1.7 (apt) | `libasound` only | Pure ALSA. It reaches PipeWire through `pipewire-alsa`, or bypasses it with a `plughw:` device name (section 6) |

What was not measured: how Qt 6 Multimedia chooses its backend on each
target. An upstream report (JS8Call-improved issue 120, on Arch) says Qt 6
builds of JS8Call and WSJT-X do not list PipeWire *virtual* devices as
inputs on some systems. Real sound cards are not affected by that report;
virtual cables are (section 7).

---

## 2. Which device is the radio?

A laptop has its own sound card, HDMI outputs, possibly a webcam
microphone, and then the radio. The programs list all of them, often by
names that do not say "radio". Find it by difference: look before you plug
it in, and again after.

```sh
cat /proc/asound/cards
arecord -l
aplay -l
pactl list short sources    # things that record: your mic, the radio's receive audio
pactl list short sinks      # things that play: your speakers, the radio's transmit input
```

**Measured on the field laptop, nothing plugged in**, `cat /proc/asound/cards`
shows one card (its second line, the bus address, trimmed):

```
 0 [PCH            ]: HDA-Intel - HDA Intel PCH
```

and `arecord -l` one capture device, `card 0: PCH [HDA Intel PCH], device 0:
ALC3254 Analog`. Plug the radio's USB cable in, run the three commands
again, and the new card is the radio; in the `pactl` lists its entries
have `usb` and the chip's name in them. If nothing new appears, the
computer does not see the interface: check the cable and the radio's USB
setting, then `hammunition hardware list`. The word in square brackets
(`PCH` here) is the card's **ID**, and it is what to write down: card
*numbers* are handed out in the order devices appear and can change after
a reboot or a replug, the ID does not.

What a rig's card looks like was **not measured** — no radio has been
attached to the bench for this page. What is widely reported, and should be
checked against your own `/proc/asound/cards` rather than trusted:

- **FT-991A, IC-7300 and similar**: a TI/Burr-Brown USB audio codec,
  usually shown as `USB Audio CODEC` with an ID like `CODEC`. Two radios of
  the same kind get `CODEC` and `CODEC_1`, which is how you tell two rigs
  apart.
- **Digirig**: a C-Media CM108-class chip, usually `USB PnP Sound Device`
  or `USB Audio Device`, with ID `Device`. Cheap USB dongles use the same
  chip family, so a Digirig and a headset dongle can look alike; unplug one
  to be sure.
- **SignaLink USB**: a TI/Burr-Brown codec again, `USB Audio CODEC`.

Note the collision: an FT-991A and a SignaLink can both call themselves
`USB Audio CODEC`. The ID and the before/after difference are what identify
yours, not the name. (The same trap exists on the serial side, where one
USB-serial chip identifier names several different radios and cables;
`docs/reference/usb-ambiguity.md` measures it, and D-028 is why Hammunition
never makes a `/dev` name from a chip identifier.)

The ALSA name to give a program that wants one comes from the long listing:

```
arecord -L | grep -A1 '^plughw:'
```

Measured shape on the laptop: `plughw:CARD=PCH,DEV=0`. A rig with ID
`CODEC` becomes `plughw:CARD=CODEC,DEV=0`. Use the `CARD=` form, never
`plughw:1,0`: the number is the part that moves.

PipeWire's names for the same card are longer. `wpctl status` shows the
friendly description, and `pw-cli ls Node` the node name; on the laptop
(measured) the built-in card is `Built-in Audio Analog Stereo`, node names
`alsa_output.pci-0000_00_1f.3.analog-stereo` and
`alsa_input.pci-0000_00_1f.3.analog-stereo`. A USB rig's node is named
`alsa_input.usb-…` after the USB vendor and product strings, which is
usually the most readable name the programs show you.

---

## 3. See where the audio goes, and patch it

### Read the graph

```
wpctl status          # devices, sinks (outputs), sources (inputs), streams; * marks the default
pw-cli ls Node        # every node with its node.name and media.class
pw-link -l            # every connection currently made
pw-top                # live: which nodes are running, at what rate and buffer size
```

All four are read-only and safe to run while a program is transmitting.
`wpctl status` is the first thing to run: when WSJT-X is receiving, it
appears under *Streams* with a link to the source it is actually recording
from, which answers "is it listening to the radio or to the laptop's
microphone?" in one line.

### A patchbay, if you want to see it drawn

[qpwgraph](../packages/qpwgraph.md) draws every PipeWire device and every
connection as boxes and wires, so "which input is WSJT-X actually
listening to?" is answered by looking. It is in the
[`digital-modes`](../profiles/digital-modes.md) profile; on its own:

```sh
hammunition install qpwgraph
```

`pavucontrol` is the older PulseAudio mixer and still works against
`pipewire-pulse`: its *Recording* and *Playback* tabs show each running
program and a drop-down for its device. Neither was installed on the
field laptop, so neither was measured here.

### Never make the radio the default device

The single most useful rule on this page. If the radio's USB codec becomes
the **default output**, every notification sound, browser tab and system
beep goes into the transmitter — and with VOX or a SignaLink, keys it.
WirePlumber may make a newly plugged USB device the default. After plugging
the radio in, check the `*` in `wpctl status` and move it back to the
laptop's own speakers:

```
wpctl status                      # find the ID number of the built-in sink
wpctl set-default <id>
```

Then choose the radio **by name inside each ham program**, never through
the desktop default. Turning off system notification sounds in the
desktop's settings is worth doing on a station laptop anyway.

### Set a level from the command line

```
wpctl get-volume <id>
wpctl set-volume <id> 1.0         # 1.0 is unity; above it clips digitally
wpctl set-mute <id> 0
```

These change the software gain PipeWire applies. Section 5 says which way
to turn them.

### Choose the radio in each program

| Program | Where (per its documentation) | Input (receive) | Output (transmit) |
|---|---|---|---|
| [WSJT-X](../packages/wsjtx.md), [JTDX](../packages/jtdx.md), [JS8Call](../packages/js8call.md) | File → Settings → Audio | The radio's source | The radio's sink |
| [fldigi](../packages/fldigi.md) and the fl family | Configure → Sound Card → Devices | PulseAudio or PortAudio: the radio's capture | the radio's playback |
| [FreeDV](../packages/freedv.md) | Tools → Audio Config | Receive tab: from radio, to speakers | Transmit tab: from mic, to radio |
| [QSSTV](../packages/qsstv.md) | Options → Configuration → Sound | the radio's input | the radio's output |
| [Direwolf](../packages/direwolf.md) | `ADEVICE` in `direwolf.conf` | §6, and [Packet and Winlink](packet-winlink.md) | same line |
| [ardopcf](../packages/ardopcf.md) | the two device names on its command line | `plughw:` names, see [Packet and Winlink](packet-winlink.md) | same |

No dialog in this table was opened on the bench; the paths move a little
between versions, the field names less.

---

## 4. Sample rates

**Measured on the field laptop:** PipeWire's graph runs at one clock rate,
`clock.rate 48000`, with `clock.allowed-rates [ 48000 ]` (read with
`pw-metadata -n settings 0`). A program that opens a device at another rate
is resampled by PipeWire to and from 48 kHz; that is PipeWire's documented
behaviour, and it was not exercised with a rig for this page.

What this means for each program:

- **WSJT-X and JS8Call** open the device at 48 kHz and do their own
  downsampling (their documentation). Nothing to set.
- **fldigi** has its own sample-rate settings under Configure → Soundcard
  and a **frequency correction in parts per million**. Resampled audio is
  fine for PSK31 and RTTY; for **SSTV and fax, a sound card whose clock is
  a little off slants every picture**, and that is calibrated once per
  sound card (the `digital-modes` profile's own notes say the same). The
  calibration is to the rig's codec, not to PipeWire.
- **Direwolf** sets its rate with `ARATE` in `direwolf.conf`. Through the
  ALSA `default` device PipeWire resamples; through `plughw:` the ALSA plug
  layer converts to whatever the card supports.

Allowing more rates (so a 44.1 kHz program is not resampled) is a
`clock.allowed-rates` line in a file under
`~/.config/pipewire/pipewire.conf.d/`. It is not needed for any mode on
this page and has not been tried here; leave it alone unless a program's
own documentation asks for it.

---

## 5. Levels, and the ALC trap

### Receive

Tune to an empty frequency on the band you will use, with the radio's AGC
on and its noise blanker off. Set receive level so the program sees band
noise comfortably above nothing and well below clipping. Too low and weak
signals vanish into the computer's own noise; too high and a strong
station clips and smears across the waterfall, taking weak ones with it.

- **WSJT-X**: the level bar at the bottom left. WSJT-X's own guidance is
  around 30 dB on a quiet band with no signals.
- **fldigi**: the waterfall's background should be a speckled noise floor,
  not black and not solid colour.
- **Direwolf**: it prints an `audio level` with every packet it hears,
  like `audio level = 50(25/24)`; its user guide aims for about 50.

Adjust in this order: the radio's own USB/data *output* level menu first,
then the capture volume with `wpctl set-volume` on the radio's source,
then the program's own slider if it has one. Receive level is forgiving;
get it roughly right and move on.

### Transmit: the ALC trap

This is the one that makes a station that hears everyone and is heard by
nobody (Direwolf's manifest says so, and the `digital-modes` profile
repeats it).

An SSB transmitter's **ALC** (automatic level control) is there to stop
voice peaks overdriving the final amplifier. Digital modes are a steady
tone, and **any ALC action on a digital signal means you are overdriving
the transmitter's audio stage**. The signal still shows full power on the
meter, but it is distorted: it spreads into neighbouring FT8 slots or PSK
channels, it decodes badly or not at all at the far end, and the people
beside you on the waterfall can see it.

The rule:

1. Set the radio's **power** with the radio's power control, never by
   turning audio up.
2. Put the radio's meter on **ALC**.
3. Press **Tune** in WSJT-X (or fldigi's **Tune**) into a dummy load or a
   clear frequency.
4. Bring the audio up — the program's own Pwr slider, then
   `wpctl set-volume` on the radio's sink — until the power reaches what
   you set and the **ALC shows little or no movement**. If the ALC moves,
   back the audio off. Never raise PipeWire's volume above 1.0 to get more
   drive; that clips before the audio leaves the computer.

Direwolf, ardopcf and fldigi each have their own transmit level; the same
rule applies to all of them.

On radios with a USB codec there is usually also a *data input level*
menu item for the USB audio into the transmitter, and a *data input
select* (rear/USB versus mic). Menu names and numbers differ by radio and
firmware; the radio's manual has them. None of this was measured on the
maintainer's FT-991A for this page.

---

## 6. Direwolf: the ALSA program

Direwolf reads its device from `ADEVICE` in `direwolf.conf`. The shipped
example (measured, `/usr/share/doc/direwolf/conf/direwolf.conf.gz` on the
laptop) says to use `plughw` with a card from `arecord -l`, and gives
`ADEVICE plughw:1,0` as the example. Use the `CARD=` form instead:

```
ADEVICE plughw:CARD=CODEC,DEV=0
```

There are two ways in, and they behave differently:

- **`ADEVICE plughw:CARD=…`** goes straight to the hardware, around
  PipeWire. PipeWire opens every sound card it manages, so if WirePlumber
  has the radio's card open when Direwolf starts, the open can fail with
  *Device or resource busy*. WirePlumber suspends an idle device after a
  few seconds, which is why this works on some starts and not others. That
  behaviour is PipeWire's documented one and was **not reproduced** here.
  The way out that keeps `plughw:` is to make PipeWire let go of that one
  card: in `pavucontrol`'s **Configuration** tab set the radio's card
  profile to **Off** (the desktop keeps its own sound). Also unmeasured.
- **`ADEVICE default`** (or no `ADEVICE` line, which means the default)
  goes through `pipewire-alsa`: the laptop's
  `/etc/alsa/conf.d/99-pipewire-default.conf` points ALSA's `default` at
  PipeWire (measured present). PipeWire then shares the card. Pick the
  radio for Direwolf's stream in `pavucontrol` or `qpwgraph`, or route it
  with WirePlumber rules. `aplay -L` on the laptop also lists a `pipewire`
  ALSA device; there is **no `pulse` ALSA device** there, because
  `libasound2-plugins` is not installed (measured), so a guide that says
  `ADEVICE pulse` needs that package first.

For **PTT**, a Digirig-class or CM108 interface can key the radio from the
sound chip's own GPIO: the example file carries `#PTT CM108` for exactly
this. Other options — a serial line's RTS, a Pi GPIO pin, hamlib CAT — are
in the example file and in Direwolf's Radio Interface Guide, which the file
links to. Direwolf's config is still the operator's to write; station
config filling in `MYCALL` is gap report A1, not built yet. A whole
working `direwolf.conf` for Winlink, with the AGW and KISS ports Pat uses,
is in [Packet and Winlink](packet-winlink.md#1-direwolf-the-modem).

---

## 7. Virtual cables: SDR audio into a decoder

To decode what an SDR receiver hears — SDR++ or gqrx audio into WSJT-X or
fldigi — the SDR program's output has to become a decoder's input. On
PipeWire that is a **loopback** or a **null sink**:

```sh
pw-loopback \
  --capture-props='media.class=Audio/Sink node.name=sdr-out node.description="SDR out"' \
  --playback-props='media.class=Audio/Source node.name=sdr-in node.description="SDR in"'
```

makes a pair while it runs (Ctrl-C stops it): send the SDR program's
audio to **SDR out** and pick **SDR in** as the decoder's input. (Both options are in `pw-loopback --help` on the
laptop, measured; the pair was not created.) Or, through the PulseAudio
door, a null sink whose *monitor* is the decoder's input:

```
pactl load-module module-null-sink sink_name=sdr-to-decoder
```

The null sink lasts until PipeWire restarts. **Neither has been tried on
the field laptop for this page**, and the upstream report above
([JS8Call-improved issue 120](https://github.com/JS8Call-improved/JS8Call-improved/issues/120))
says Qt 6 builds may not list such a device as an input, failing with
*Requested input audio format is not supported on device*; the
workaround that report names is the kernel's ALSA loopback (`snd-aloop`),
which needs a module loaded as root and has also not been measured here.
The catalog carries no loopback configuration yet: gap report A3 plans one,
once that Qt 6 behaviour has been measured on the field laptop.

---

## 8. When it goes wrong

Symptom first. Each points to the section that explains it.

- <a name="no-waterfall"></a>**The waterfall is flat or black: the program
  hears nothing.** Run `wpctl status` while the program is running and read
  its line under *Streams*: it is recording from the wrong source (the
  laptop's microphone is the usual one), or the source is muted. Pick the
  radio by name in the program's audio settings (§2, §3). Confirm the radio
  itself is sending audio: its USB/data output level menu at zero is a
  flat waterfall.
- <a name="radio-missing"></a>**The radio's sound card is not in the
  program's list.** Check `cat /proc/asound/cards`: if the card is not
  there, the kernel does not see it (cable, USB port, or the radio's USB
  audio switched off in its menu). If it is there but the program does not
  list it, check the program is on the door you think (§1) and that
  `pulseaudio` has not replaced `pipewire-pulse`.
- <a name="notifications-on-air"></a>**Desktop sounds go out over the air,
  or the radio keys by itself.** The radio became the default output (§3).
  Move the default back, and turn off notification sounds.
- <a name="clipping"></a>**The waterfall is solid colour and decodes
  nothing.** The input is clipping. Lower the radio's USB audio output
  level first (§5).
- <a name="no-power"></a>**Tune keys the radio but the meter shows no
  power.** Wrong output device in the program, or the radio is taking
  transmit audio from its microphone jack: a menu item on Yaesu and Icom
  radios chooses the USB or rear input as the data-mode audio source (§5).
- <a name="after-update"></a>**Everything worked until the desktop was
  updated.** The default device moved to the radio, or a program lost its
  saved device name. Check the default (§3), then each program's audio
  settings.
- <a name="alc"></a>**Full power on the meter, nobody decodes me, PSKReporter
  shows nothing.** Overdrive. Watch ALC while tuning and back the audio off
  until ALC barely moves (§5).
- <a name="busy"></a>**Direwolf or ardopcf: `Device or resource busy`.** It
  is opening the card with `plughw:` while PipeWire holds it (§6). Use the
  `default` route, or set the radio's card profile to Off in `pavucontrol`.
- <a name="sstv-slant"></a>**SSTV pictures slant, fax images skew.** Sound
  card clock error; calibrate fldigi's or QSSTV's ppm correction once for
  that sound card (§4).
- <a name="two-programs"></a>**It worked until I opened a second program.**
  Two ham programs on one radio fight over its audio and its CAT port. Run
  one per session (the `digital-modes` profile says the same of the FT8
  family).
- <a name="pulseaudio-removed"></a>**All sound stopped after installing
  something.** Check `dpkg -l pipewire-alsa pipewire-pulse pulseaudio`: a
  package that pulled in `pulseaudio` removed `pipewire-alsa` (§1). Put the
  PipeWire packages back with apt and remove `pulseaudio`.
- <a name="decodes-nothing"></a>**Audio looks fine, the waterfall shows
  signals, WSJT-X decodes nothing.** Not audio: the clock. See
  [Time and position](time-and-gps.md).

---

## What has not been measured yet

Plainly, so nobody reads this page as a bench report:

- **No radio or USB sound interface was attached** for this page. The rig
  card names in §2, all level guidance in §5 and every FT-991A detail are
  from manufacturers' and upstreams' documentation and common operating
  practice, not from this bench.
- **Only the field laptop** (Parrot 7.3, PipeWire 1.4.9) was read. Which
  audio packages Debian 13, Kali and the Ubuntu targets install by default
  is not recorded, and neither is whether the six VM campaigns ran PipeWire
  at all (the bench page notes the same gap).
- **The *busy device* behaviour, PipeWire resampling with a real codec,
  the loopback commands in §7 and the Qt 6 virtual-device report** are
  documented behaviours, not reproduced here.
- **`qpwgraph` and `pavucontrol`** were not installed on the laptop and
  were not run.
- No GUI was opened to write this page: the dialog paths named are from the
  programs' documentation and the option strings in their binaries.

A measurement of any of these belongs in
`docs/reference/bench-verification-5430.md`, and then here.
