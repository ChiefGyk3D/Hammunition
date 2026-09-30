<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Satellites

Amateur satellites are repeaters in orbit, weather satellites send pictures,
and small science satellites send telemetry anyone may decode. All of them
pass overhead for a few minutes at a time, so the work is knowing when, and
pointing and tuning while they move.

```sh
hammunition install station satellite
```

The [`satellite`](../profiles/satellite.md) profile carries
[gpredict](../packages/gpredict.md) for passes and control,
[SatDump](../packages/satdump.md) for weather images,
[gr-satellites](../packages/gr-satellites.md) for telemetry, and hamlib.

## 1. Tell gpredict where you are

Every prediction is relative to your position, so it has to be right.
**Edit → Preferences → General → Ground Stations → Add new.** Give it a
name and either your latitude and longitude or your Maidenhead locator, and
your altitude. Make it the default.

## 2. Update the orbital elements, every time

gpredict computes passes from orbital elements (TLEs) it downloaded, and
they go stale in days. It does not warn you. **Edit → Update TLE → From
network** before any session you care about. A pass that does not happen
when predicted is almost always stale elements.

For a trip with no network, update just before you leave: elements a few
days old are still good to a minute or so for most amateur satellites.

## 3. See the passes

The default module shows a map and a list of satellites with their next
pass. To follow one: from the module's menu (the small arrow at the top
right of the module), **Upcoming passes** lists the next ones with times,
maximum elevation and duration. Passes above about 20° elevation are the
ones worth trying with a handheld antenna.

Which satellites are active changes often. Check [AMSAT's
status page](https://www.amsat.org/status/) for what is working this week;
AMSAT's site also lists each satellite's uplink and downlink.

## 4. Doppler: let gpredict tune the radio

A satellite moving at orbital speed shifts its frequency by up to about
±3 kHz on 2 m and ±10 kHz on 70 cm across a pass. gpredict corrects for it
through hamlib.

1. Set up [rig control](rig-control.md) with `rigctld` on `127.0.0.1:4532`.
2. **Edit → Preferences → Interfaces → Radios → Add New:** host
   `localhost`, port `4532`, and the radio type: *RX only* for listening,
   *Duplex* for a radio with two VFOs that transmits and receives at once.
3. From the module's menu, **Radio Control**. Choose the satellite and its
   transponder, then **Engage** and **Track**. gpredict retunes the radio
   through the pass.

A rotator works the same way: `rotctld` from hamlib on port 4533, added
under **Interfaces → Rotators**, then **Antenna Control** from the module's
menu. `rotctl -l` lists rotator models as `rigctl -l` lists radios.

## 5. Weather pictures with SatDump

The American NOAA satellites that sent the classic APT pictures went out of
service on 2025-11-09 ([not carried](../reference/not-carried.md)). The
Russian **Meteor-M** satellites still send LRPT pictures on 137 MHz, and
SatDump decodes them from an RTL-SDR.

1. Find a Meteor pass in gpredict. If the satellite is not in your module,
   add it through the module's **Configure** dialog. Check the current frequency on
   the satellite's own status pages: they have moved between 137.1 and
   137.9 MHz over the years.
2. In SatDump, **Recorder**: choose the SDR and the frequency, and the
   Meteor LRPT pipeline, and start before the satellite rises.
3. SatDump decodes as it receives and writes the images when the pass ends.

A V-dipole or QFH antenna made for 137 MHz makes the difference between
noise and a picture. On a slow laptop, record the pass and process the
recording afterwards with SatDump's offline mode, which its manifest notes
is the reliable path on modest hardware.

The geostationary weather satellites (GOES, GK-2A) need a dish and a
different setup; SatDump decodes them too, and its own documentation walks
through it.

## 6. Telemetry with gr-satellites

[gr-satellites](../packages/gr-satellites.md) decodes the telemetry of
hundreds of small satellites from a recording or a live receiver. Its
documentation lists them and the command for each. Uploading decoded frames
to [SatNOGS](https://db.satnogs.org/) helps the teams who built them.

## What was measured

The profile's members and SatDump's known problems were read from the
catalog. The gpredict steps follow gpredict's own documentation, and the
Doppler figures are the textbook values for low-orbit satellites. A pass
worked or decoded from the field laptop is not yet in the [bench
record](../reference/bench-verification-5430.md).
