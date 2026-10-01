<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# SDR first steps

A software-defined radio receiver turns the computer into a radio that can
tune from shortwave to microwave and see a whole slice of spectrum at once.
The cheapest way in is an **RTL-SDR** dongle, and nothing on this page needs
a licence: it is all receiving.

This page gets a dongle from the bag to three things in one evening:
broadcast FM, aircraft, and the 433 MHz sensors around your house.

## Install

```sh
hammunition install sdr listening --dry-run
hammunition install sdr listening
```

[`sdr`](../profiles/sdr.md) carries the receivers (Gqrx, SDR++, CubicSDR,
SDRangel), GNU Radio and the device drivers.
[`listening`](../profiles/listening.md) carries the decoders: aircraft,
ships, pagers, sensors, weather. Some units are not in every distribution's
archive; the plan names any it defers and why, and installs the rest.

## 1. Plug it in and check it

```sh
hammunition hardware list
```

This lists what is plugged in and whether the catalog recognises it, and
whether its permissions are set up. Then ask the device itself:

```sh
rtl_test
```

It should find the dongle, name its tuner chip, and start reading samples.
A few seconds without `lost at least` messages is a healthy device; stop it
with Ctrl-C. Other devices have their own test tool, named on their
[hardware page](../hardware/index.md).

### If `rtl_test` says the device is busy

A message like `usb_claim_interface error -6` means the Linux kernel's
digital-TV driver took the dongle first. It was built for watching TV, and
it holds the device so nothing else can.

```sh
echo 'blacklist dvb_usb_rtl28xxu' | sudo tee /etc/modprobe.d/blacklist-rtl-sdr.conf
sudo modprobe -r dvb_usb_rtl28xxu
```

Unplug the dongle and plug it back in. Undo: delete that file.

Whether your distribution already ships this file varies. Ubuntu 24.04's
`rtl-sdr` 2.0.1 packages ship udev rules and no blacklist (read from the
package archives, 2026-09-30), so there the command above may be needed.

### If it says permission denied

The device's udev rule grants access to the `plugdev` group, and group
membership starts at your next login. Log out and back in.
`hammunition hardware apply --dry-run` shows the rules and groups the
catalog would set up for every device it knows.

## 2. Broadcast FM with Gqrx

[Gqrx](../packages/gqrx-sdr.md) is the catalog's general-purpose default
receiver ([why](../reference/overlaps.md)).

1. Start Gqrx. The first-run dialog lists detected devices: choose the
   RTL-SDR. Leave the sample rate at its default.
2. Press the **power** button (top left) to start.
3. Set the frequency to a local FM station, say 99.5 MHz, and the mode
   (right-hand panel) to **WFM (stereo)**.
4. Raise the **Gain** in the Input Controls tab until the station is clear;
   too much gain makes ghosts of strong stations all over the band.

You are hearing the station, and the waterfall above shows every station
around it at once.

The other receivers do the same job differently.
[SDR++](../packages/sdrpp.md) is fast and modern,
[SDRangel](../packages/sdrangel.md) does almost everything including
transmit on capable hardware, [CubicSDR](../packages/cubicsdr.md) is simple.
Try them; they coexist.

## 3. Aircraft

Aircraft broadcast their position, altitude and callsign on 1090 MHz
(ADS-B). [readsb](../packages/readsb.md) decodes it, and serves a map and
data feeds for other programs. It is not in every distribution's archive
(Ubuntu 24.04 has none; checked 2026-09-30), and the install plan says
where it is deferred. Its own documentation gives the command lines.

Close Gqrx first: one program at a time can hold the dongle.

For aircraft datalink text rather than positions,
[acarsdec](../packages/acarsdec.md) (VHF ACARS),
[dumpvdl2](../packages/dumpvdl2.md) and [dumphfdl](../packages/dumphfdl.md)
(HF) are in `listening`.

## 4. Sensors on 433 MHz

Weather stations, tyre-pressure sensors, doorbells and utility meters
transmit short bursts on 433.92 MHz (868 MHz in Europe for many).
[rtl_433](../packages/rtl-433.md) knows hundreds of them:

```sh
rtl_433
```

With no options it listens on 433.92 MHz and prints each decoded device as
it hears it: model, ID, and whatever it reports. Give it a few minutes in a
built-up area. `rtl_433 -f 868M` listens on 868 MHz.

## 5. Ships

On the coast, ships broadcast AIS on 162 MHz. [AIS-catcher](../packages/ais-catcher.md)
and [rtl-ais](../packages/rtl-ais.md) decode it; their pages say how to feed
a map.

## What you may decode is your law to know

Receiving is unlicensed nearly everywhere. What you may *decode, record or
repeat* is not the same everywhere: pager traffic, aircraft datalink and
some utility transmissions are protected in some countries. Hammunition
tells you what a tool can do and never judges what your law allows. That is
yours to know before you listen.

## When it does not work

- **Nothing found by `rtl_test`** → cable, USB port, then `hammunition
  hardware list`.
- **Busy** → the kernel driver, above.
- **Everything is noise** → the antenna. The telescopic antenna in the box is
  a compromise; for 1090 MHz a quarter-wave (about 6.9 cm) vertical helps
  enormously.
- **The frequency is slightly off** → cheap dongles' crystals drift. Newer
  ones with a TCXO barely do. `rtl_test -p` measures the error in ppm, and
  Gqrx's input settings take it as a *Freq. correction*.

## What was measured

The `rtl-sdr` package contents, `rtl_test`'s options and `rtl_433`'s default frequency were read
from Ubuntu 24.04's packages on 2026-09-30, and readsb's absence from its
archive the same day. The receiver steps follow each program's own
documentation. The field laptop's SDR bench is recorded in the [bench
record](../reference/bench-verification-5430.md); this page's steps were not
run end to end there.
