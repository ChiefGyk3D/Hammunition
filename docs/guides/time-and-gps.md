<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Time and position

Two things a station needs from its surroundings: the right time and where
it is. With a network both are automatic. This page is about the day the
network is not there, which is the day an EMCOMM station exists for.

## Why the clock matters

FT8, FT4, JS8 and WSPR transmit in fixed time slots, and a decoder only
looks for a signal where its clock says the slot is. **A clock more than
about a second off decodes nothing**, with no error, on a band full of
signals. A laptop's own clock drifts that far in days without correction.

Check it now:

```sh
timedatectl
```

`System clock synchronized: yes` means something is keeping it right. With
a network, that something is the distribution's time service, and there is
nothing else to do.

## With no network: a GPS keeps the clock

The [`station`](../profiles/station.md) profile installs
[gpsd](../packages/gpsd.md), which reads a GPS receiver and shares it with
every program. Handing its time to the system clock is the job of the
machine's **time daemon**, and which one you have decides the route. Only
one can be installed at a time: chrony, ntpsec and systemd-timesyncd each
declare themselves the machine's `time-daemon` and conflict with the other
two, so installing one removes the other
(measured: [Time daemons](../reference/time-daemons.md)).

```sh
dpkg -l chrony ntpsec systemd-timesyncd 2>/dev/null | grep '^ii'
```

| You have | Usually on | The route |
|---|---|---|
| **ntpsec** | Parrot (its security edition pulls it in), the field laptop | GPS time through ntpsec, **D-058**. Its guide, docs/guides/gps-time.md, arrives with pull request #124 and is not on this branch yet. Do not install chrony here: it would remove ntpsec, and Hammunition refuses to. |
| **systemd-timesyncd** | Debian 13, Ubuntu 24.04, Linux Mint 22.3; Kali, whose `kali-linux-core` pulls it in (a Kali whose `kali-linux-default` came first may have ntpsec) | It cannot read a GPS. Replace it with chrony, below. |
| **chrony** | Ubuntu 26.04 | Already the right daemon. Install the unit below; it adds the GPS and changes nothing else. |

### 1. Plug in the GPS and confirm gpsd sees it

```sh
cgps
```

Wait for a fix: the screen shows latitude, longitude and a time. A receiver
indoors can take minutes. `gpsmon` shows the raw sentences if nothing
appears. The [GPS receiver page](../hardware/gps-receiver-class.md) covers
which receivers work and how they appear.

### 2. Install the chrony unit

On a machine with systemd-timesyncd, remove it yourself first. Hammunition
never removes a package you did not ask it to (**D-022**); if you skip this
step, the install refuses and prints the same command.

```sh
sudo apt-get remove systemd-timesyncd     # only where it is installed
hammunition install chrony --dry-run      # read what it will do
hammunition install chrony
sudo reboot
```

The [`chrony` unit](../packages/chrony.md) installs chrony and writes two
files:

- `/etc/chrony/conf.d/hammunition-gps.conf`, one line:
  `refclock SHM 0 refid GPS poll 2 delay 0.2`, the time gpsd publishes for
  the first receiver it opens. Every target's `chrony.conf` reads that
  directory.
- `/etc/systemd/system/gpsd.service.d/hammunition-gps.conf`, which starts
  gpsd with `-n`. **Without it gpsd reads the receiver only while a program
  is connected**, and chrony gets no time at all (measured: no samples
  without `-n`, one a second with it).

**Reboot rather than restart gpsd**: restarting a running gpsd in place,
tried in a container, left two gpsd processes and no time. After a reboot
gpsd starts with `-n` from the beginning.

chrony keeps using the network's time servers whenever there is a network,
so nothing is lost. The GPS line tells chrony its time is good to about a
tenth of a second (`delay 0.2`), which is what NMEA over USB gives and
plenty for FT8.

### 3. Optional: calibrate the offset

NMEA sentences arrive a little after the second they describe, by an amount
that depends on the receiver. With the network up, after a few minutes:

```sh
chronyc -n sourcestats
```

The `GPS` line's *Offset* column is how far the GPS sits from the
network-disciplined clock. To take it out, add `offset` with that value in
seconds to the line in `/etc/chrony/conf.d/hammunition-gps.conf` (for
example `refclock SHM 0 refid GPS poll 2 delay 0.2 offset 0.12`) and
`sudo systemctl restart chrony`. How large it is on any real receiver has
not been measured yet.

A receiver with a **PPS** output wired to the computer is accurate to
microseconds instead; chrony's own [configuration
examples](https://chrony-project.org/examples.html) and gpsd's [time
service HOWTO](https://gpsd.gitlab.io/gpsd/gpsd-time-service-howto.html)
cover it. Most USB pucks do not provide PPS, and FT8 does not need it.

### 4. Check it with the network off

Disconnect from the network, wait a minute, then:

```sh
chronyc -n sources
```

The line starting `#*` is the source in use. With the network off it should
be `GPS`.

### Undoing it

Uninstalling the unit leaves the two files, so remove them by hand:

```sh
sudo rm /etc/chrony/conf.d/hammunition-gps.conf \
        /etc/systemd/system/gpsd.service.d/hammunition-gps.conf
sudo systemctl daemon-reload
sudo apt install systemd-timesyncd        # if you want it back; removes chrony
sudo reboot
```

## Position

Your position is yours to share or not.

- **Your grid square** is what the digital modes send. Set it once with
  `hammunition station set --grid-square FN31pr` (your own, not this
  placeholder); [Your callsign in each program](station-settings.md) lists
  where each program wants it.
- **Moving position** comes from gpsd. [Pat](../packages/pat.md) can post a
  position report from it (`pat-winlink position`), APRS clients read it
  directly, and [Offline navigation](offline-navigation.md) shows it on a
  map.
- **gpsd is local only.** It listens on `localhost:2947`; nothing on the
  network can read your position from it unless you change that.

## What was measured

Which time daemon each target offers and pulls in, that the three conflict,
and the chrony and gpsd behaviour above were measured in containers of all
seven targets on 2026-09-29 and 2026-09-30; the tables and commands are in
[Time daemons](../reference/time-daemons.md), with what was not measured.
The gpsd-to-chrony path was run with a script standing in for the receiver.
It has not yet been run with a receiver on the field laptop, which runs
ntpsec and so takes the D-058 route; the GNSS module planned for it is the
bench for that.
