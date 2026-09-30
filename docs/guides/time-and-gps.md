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
every program. What it does not yet do is hand the time to the system clock.
That takes **chrony**, a time service that can take its time from gpsd.

!!! note "On Parrot, or any machine running ntpsec"
    ntpsec, not chrony, is the time daemon there, and Hammunition sets it up
    to follow the GPS itself: see [GPS time](gps-time.md) (**D-058**). The
    steps below are for a machine with systemd-timesyncd or chrony.

!!! info "Not a catalog unit yet"
    A `chrony` unit with this configuration is planned
    ([gap analysis, A4](../reference/catalog-gaps-2026-09.md)). Until it
    lands these steps are yours to run, and so is undoing them. Each step
    says how.

### 1. Plug in the GPS and confirm gpsd sees it

```sh
cgps
```

Wait for a fix: the screen shows latitude, longitude and a time. A receiver
indoors can take minutes. `gpsmon` shows the raw sentences if nothing
appears. The [GPS receiver page](../hardware/gps-receiver-class.md) covers
which receivers work and how they appear.

gpsd only reads the receiver while a program is connected to it. For the
clock, it has to read all the time. In `/etc/default/gpsd` set:

```sh
GPSD_OPTIONS="-n"
```

and restart it: `sudo systemctl restart gpsd`. Undo: set the line back to
`""` and restart.

### 2. Install chrony

```sh
sudo apt install chrony
```

**This removes `systemd-timesyncd`**, and apt says so before it asks. The
two cannot both run: both packages declare themselves the machine's
`time-daemon` and conflict with any other (measured from the package
metadata on Ubuntu 24.04). chrony keeps using the network's time servers
whenever there is a network, so nothing is lost. Undo: `sudo apt install
systemd-timesyncd`, which removes chrony in turn.

### 3. Tell chrony to listen to gpsd

Debian's and Ubuntu's `chrony.conf` read every file in `/etc/chrony/conf.d/`,
so the GPS goes in a file of its own:

```sh
sudo tee /etc/chrony/conf.d/gpsd.conf <<'EOF'
# Time from gpsd's shared memory, unit 0: the receiver's NMEA sentences.
# Good to roughly a tenth of a second over USB, which is plenty for FT8.
refclock SHM 0 refid GPS precision 1e-1 offset 0.0 delay 0.2 noselect
EOF
sudo systemctl restart chrony
```

`noselect` is deliberate for the first run: chrony watches the GPS without
trusting it yet. After a few minutes:

```sh
chronyc sourcestats
```

The `GPS` line's *Offset* column is how far the GPS's time sits from the
network-disciplined clock. Adjust the file's `offset` value, restarting
chrony each time, until that column sits near zero; then remove
`noselect` and restart once more. The GPS is now a source chrony will
use, and the only one when the network is gone. Undo: delete the file and
restart chrony.

A receiver with a **PPS** output wired to the computer is accurate to
microseconds instead; chrony's own [configuration
examples](https://chrony-project.org/examples.html) and gpsd's [time
service HOWTO](https://gpsd.gitlab.io/gpsd/gpsd-time-service-howto.html)
cover it. Most USB pucks do not provide PPS, and FT8 does not need it.

### 4. Check it with the network off

Disconnect from the network, wait a minute, then:

```sh
chronyc sources
```

The line starting `#*` is the source in use. With the network off it should
be `GPS`.

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

gpsd's `/etc/default/gpsd` fields, chrony's `confdir` line and the
chrony/timesyncd conflict were read from Ubuntu 24.04's packages on
2026-09-30. The chrony configuration follows chrony's and gpsd's own
documentation. It has not yet been run with a receiver on the field laptop;
the GNSS module planned for it is the bench for that.
