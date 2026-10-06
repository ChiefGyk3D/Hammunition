<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# GPS, position and time

A GPS (GNSS) receiver gives a station two things: where it is, and what time
it is. With a network both come for free. This hub is for the day the network
is not there, and for the plumbing between the receiver and the programs that
want its answers.

```text
 receiver --USB--> gpsd --> cgps, xgps, gpspipe ...        (position, on screen)
                     |
                     +--> the GPS tether (127.0.0.1 only)
                     |        +--> QMapShack, CoMaps (through GeoClue), the browser map
                     |
                     +--> time daemon: ntpsec (D-058) or chrony (D-072)  --> the clock
```

## Programs the catalog carries

<!-- BEGIN generated: programs -->

- [chrony](../packages/chrony.md): The clock follows your GPS receiver when the network is gone — chrony reading gpsd (by name only)
- [comaps](../packages/comaps.md): Offline vector maps with search and car, bike and foot routing, from CoMaps' own map files (in [`navigation`](../profiles/navigation.md))
- [gnss-sdr](../packages/gnss-sdr.md): A complete GPS and GNSS receiver built entirely in software (in [`sdr`](../profiles/sdr.md))
- [gps-tether](../packages/gps-tether.md): Your GPS position on 127.0.0.1 for QMapShack, the browser map and GeoClue, as a user service (in [`navigation`](../profiles/navigation.md))
- [gpsbabel](../packages/gpsbabel.md): Converts between GPS file formats and talks to the receiver (in [`station`](../profiles/station.md))
- [gpsd](../packages/gpsd.md): GPS service daemon — one process owns the receiver, everything else asks it (in [`navigation`](../profiles/navigation.md), [`station`](../profiles/station.md))
- [gpsd-clients](../packages/gpsd-clients.md): Clients that consume what gpsd serves — xgps, gpspipe, gpxlogger, gpsdecode (in [`navigation`](../profiles/navigation.md), [`station`](../profiles/station.md))
- [gpsd-tools](../packages/gpsd-tools.md): cgps and gpsmon — the two programs you actually reach for when a receiver misbehaves (in [`station`](../profiles/station.md))
- [navit](../packages/navit.md): Offline turn-by-turn navigation that follows the GPS, with spoken directions (in [`navigation`](../profiles/navigation.md))
- [osm-pmtiles](../packages/osm-pmtiles.md): Vector-tile maps of your OpenStreetMap regions, for the offline browser map (in [`navigation`](../profiles/navigation.md))
- [pygpsclient](../packages/pygpsclient.md): See what your GNSS receiver sees, and configure a u-blox receiver without u-center (by name only)
- [qmapshack](../packages/qmapshack.md): Offline topographic maps, trails, GPX tracks, elevation profiles and routing on foot (in [`navigation`](../profiles/navigation.md))

<!-- END generated: programs -->

## Hardware the catalog carries

<!-- BEGIN generated: hardware -->

- [gps-receiver](../hardware/gps-receiver-class.md) (class): USB GNSS receivers — position for APRS and grid squares, and time for FT8

<!-- END generated: hardware -->

The class page says how a receiver appears (nearly all present as a USB
serial port) and which group you need. A catalogued receiver is not the same
thing as a tested one: the device pages keep the two apart.

## Install

The `station` profile installs gpsd, its clients and tools, and gpsbabel; the
`navigation` profile adds the maps and the GPS tether. Read the plan first.

```sh
hammunition install station --dry-run
hammunition install station
```

Join `dialout` (the plan says whether it is needed) and log out and back in.

## First useful task: see a fix

Plug the receiver in, then:

```sh
cgps
```

Wait for a fix: latitude, longitude and a time appear, and indoors that can
take minutes. `gpsmon` shows the raw sentences if nothing does. Then check
what the machine thinks of its clock and its position:

```sh
timedatectl
hammunition doctor
```

## Position on a map

The tether turns gpsd's position into NMEA on `127.0.0.1:10110` and a browser
stream on `127.0.0.1:10111`, both on this machine only, as a login service.
QMapShack and CoMaps read the first (CoMaps through GeoClue); the offline
browser map reads the second. [Offline navigation](../guides/offline-navigation.md)
walks through the maps, section 11 the tether. Your position is yours to
share: gpsd itself listens on `localhost` only.

## The clock without a network

FT8 and its relatives stop decoding once the clock is off by about a second,
and a laptop drifts that far in days. Which route depends on the time daemon
the machine already has, and only one can be installed at a time:

| You have | Route |
|---|---|
| ntpsec (Parrot) | [GPS time on ntpsec](../guides/gps-time.md): four modes, `hammunition time`, disclosed grants (D-058) |
| systemd-timesyncd or chrony | [Time and position](../guides/time-and-gps.md): the `chrony` unit (D-072) |

A battery-backed hardware clock (RTC) carries the time across a power-off
and nothing in software replaces it; `hammunition doctor` warns when there is
none.

## Parking and waking the receiver

A receiver you are not using draws power. `hammunition hardware park
gps-receiver` and `hammunition hardware wake gps-receiver` (or the tray's
Controls panel) switch it off and on. Parking also turns GPS time off, so the
clock follows the network or holds over until you wake it. See [device power
control](../hardware/power-control.md) and [the tray's
Controls panel](../guides/tray-controls.md). If the fix does not return after
the laptop sleeps, [troubleshooting](../troubleshooting/running.md#gps-after-suspend)
has the manual steps.

## Offline, LAN and radio

| Needs | Works with no internet? |
|---|---|
| The fix, `cgps`, the tether, a position on a map already installed | Yes. A GPS receives satellites, not the internet. |
| GPS time | Yes: that is the point. It needs a fix first. |
| Installing the programs, and downloading map data ahead of time | No: do these before you leave. See [offline navigation](../guides/offline-navigation.md). |

## Where the detail lives

[Time and position](../guides/time-and-gps.md), [GPS time on
ntpsec](../guides/gps-time.md), [Offline navigation](../guides/offline-navigation.md),
[the GPS receiver class](../hardware/gps-receiver-class.md), [device power
control](../hardware/power-control.md), [Time daemons](../reference/time-daemons.md).

## What was measured, and what was not

Measured, on the field laptop with a u-blox 9 receiver
([bench record](../reference/bench-verification-5430.md)): parking and waking
the receiver, with gpsd dropping and re-adopting it within a second and a 3D
fix back by 74 s after the wake (session 10); QMapShack taking a position from
the tether (session 12); the tether running as a login service, including
across a reboot, and a fix from a cold boot (session 13); the NMEA
path's offset on that receiver, read as -27.3 to -23.2 ms against the
network-disciplined clock, with the GPS never the system peer while the
network was up, by design (session 14, 2026-10-04).

Not measured:

- **GPS time taking over with the network off.** It is built and tested in
  containers and fakes; the run is owed (session 14, part B, issue #310).
- **Recovery after a real suspend and resume** (issues #177, #301): the resume
  step is installed and fires, but the full run across several suspends is
  owed. A reboot clearing the symptom says nothing about a suspend.
- **PPS pulses** on that receiver (`ppstest` was not installed; issue #319).
- **The chrony route with a real receiver**: it ran in containers of all seven
  targets with a script standing in for the receiver.
- **Navit, CoMaps and the browser map fed by a real receiver.**
