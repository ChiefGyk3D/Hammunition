<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Radio audio

Every digital mode is sound. The radio's receiver audio has to reach the
program, and the program's transmit audio has to reach the radio, at a level
that neither clips nor disappears into the noise. This page gets both right
on a 2026 Linux desktop, which means **PipeWire**: every supported target
uses it for desktop audio.

## 1. Find the radio's sound card

A radio with a built-in USB interface (FT-991A, IC-7300, IC-705 and most
current rigs), a Digirig, a SignaLink or any USB sound dongle appears as a
sound card called something like *USB Audio CODEC* or *C-Media USB Audio
Device*. With the radio plugged in and on:

```sh
pactl list short sinks      # things that play: your speakers, the radio's input
pactl list short sources    # things that record: your mic, the radio's output
```

The radio's entries have `usb` and the chip's name in them. If there are
none, the computer does not see the interface: check the cable, then
`hammunition hardware list`.

!!! tip "Names that stay put"
    PipeWire names follow the USB device, so they survive a reboot. ALSA
    card numbers (`hw:1,0`) do not: plugging in a webcam can make the radio
    card 2. Prefer the device *name* wherever a program offers one.

## 2. Keep the desktop's sounds off the radio

The desktop will happily make the radio's sound card the default output
the moment you plug it in, and then every notification chirp goes out over
the air. In your desktop's sound settings, set the **default** output and
input back to the laptop's own speakers and microphone. Programs that
should use the radio are told so by name, below.

## 3. Choose it in each program

| Program | Where | Input (receive) | Output (transmit) |
|---|---|---|---|
| [WSJT-X](../packages/wsjtx.md), [JTDX](../packages/jtdx.md), [JS8Call](../packages/js8call.md) | File → Settings → Audio | The radio's *source* | The radio's *sink* |
| [fldigi](../packages/fldigi.md) and the fl family | Configure → Sound Card → Devices | PortAudio or PulseAudio: the radio's capture | the radio's playback |
| [FreeDV](../packages/freedv.md) | Tools → Audio Config | Receive tab: from radio, to speakers | Transmit tab: from mic, to radio |
| [QSSTV](../packages/qsstv.md) | Options → Configuration → Sound | the radio's input | the radio's output |
| [Direwolf](../packages/direwolf.md) | `ADEVICE` in `direwolf.conf` | see [Packet and Winlink](packet-winlink.md) | same line |
| [ardopcf](../packages/ardopcf.md) | the two device names on its command line | `plughw:` names, see [Packet and Winlink](packet-winlink.md) | same |

## 4. Set the receive level

Tune to an empty frequency on the band you will use, with the radio's AGC
on and its noise blanker off.

- **WSJT-X / JS8Call:** the level bar at the bottom left should sit around
  **30 dB** on band noise. Adjust the radio's USB audio output level in its
  menu first, then the capture level in `pavucontrol` or your desktop's
  sound settings.
- **fldigi:** the waterfall should show the band noise as a faint texture,
  not black and not solid colour.

Too low and weak signals vanish into the computer's own noise. Too high and
a strong station clips and smears across the waterfall, taking weak ones with
it.

## 5. Set the transmit level

This is the setting that makes a station *heard by nobody* while it hears
everyone. Overdriving produces a signal that looks strong on your meter and
is splattered garbage on everyone else's waterfall.

1. Transmit into a dummy load, or into the antenna on a clear frequency.
2. In WSJT-X, press **Tune**. Watch the radio's **ALC** meter.
3. Lower the program's *Pwr* slider, or the radio's USB input level, until
   the ALC just stops moving. **No ALC action** is the target for every
   digital mode; set power with the radio's power control, not with audio.

Direwolf, ardopcf and fldigi each have their own transmit level; the same
rule applies to all of them.

## 6. A patchbay when something is not where you think

`qpwgraph` draws every PipeWire device and every connection as boxes and
wires, so "which input is WSJT-X actually listening to?" is answered by
looking. It is not in the catalog yet ([gap analysis,
A3](../reference/catalog-gaps-2026-09.md)); install it with apt:

```sh
sudo apt install qpwgraph
```

`pavucontrol` is the older, simpler tool: its *Recording* and *Playback*
tabs show and change which device each running program uses, and its
*Input Devices* tab shows a live level meter.

## 7. SDR audio into a decoder

To decode FT8, APRS or pagers from an SDR program instead of a radio, the
SDR program's audio output has to become a decoder's input. PipeWire can make
a virtual cable for that:

```sh
pw-loopback \
  --capture-props='media.class=Audio/Sink node.name=sdr-out node.description="SDR out"' \
  --playback-props='media.class=Audio/Source node.name=sdr-in node.description="SDR in"'
```

While that runs, set the SDR program's output to **SDR out** and the
decoder's input to **SDR in**. Stop it with Ctrl-C.

!!! warning "Known problem: virtual inputs missing in some Qt 6 programs"
    JS8Call-improved and Qt 6 builds of WSJT-X have been reported not to
    list PipeWire virtual devices as inputs, failing with *Requested input
    audio format is not supported on device*
    ([JS8Call-improved issue #120](https://github.com/JS8Call-improved/JS8Call-improved/issues/120),
    reported on Arch). The workaround reported there is the ALSA loopback
    module, `sudo modprobe snd-aloop`, which gives a pair of sound cards
    wired to each other. Unmeasured by this project.

## When it does not work

- **Waterfall flat, no noise at all** → wrong input device, or the radio's
  USB audio output level is at zero in its menu.
- **Waterfall solid colour, decodes nothing** → the input is clipping.
  Lower the radio's USB output level.
- **Tune keys the radio, meter shows no power** → wrong output device, or
  the radio is taking transmit audio from its microphone jack. On Yaesu and
  Icom radios a menu item chooses *USB* or *DATA* as the transmit audio
  source for data modes.
- **Everything worked until the desktop was updated** → the default device
  changed back to the radio, or a program lost its saved device name. Check
  step 2, then step 3.

## What was measured

`pactl` and `pw-loopback`'s options were read from PipeWire's tools on
Ubuntu 24.04 on 2026-09-30. The loopback recipe and the level targets
follow PipeWire's and WSJT-X's own documentation. None of this page has
yet been run end to end against a radio on the field laptop; when it is,
[the bench record](../reference/bench-verification-5430.md) will say so.
