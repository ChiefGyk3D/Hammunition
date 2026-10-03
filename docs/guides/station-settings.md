<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Your callsign in each program

Almost every program on the station asks for the same two things on first
run: your callsign and your grid square. This page says which ones
Hammunition fills in for you and where to type them in the rest, so you do
it once per program and never wonder where a setting went.

## Tell Hammunition once

```sh
hammunition station set --callsign N0TST --grid-square FN31pr
hammunition station show
```

Use your own callsign and grid, not these placeholders. They are kept in
`~/.config/hammunition/station.yml`, readable only by you. `station show`
prints them back; it is fine on your screen, but do not paste its output
into a forum or an issue: a callsign leads to a name and an address.

**Nothing is ever invented.** If a program needs a value you have not set,
the install still happens, and the plan names the one file it could not
write and the command that would let it. See [the station
command](../reference/cli.md#hammunition-station-set).

## What Hammunition writes for you

| Program | File | Values |
|---|---|---|
| [LinBPQ](../packages/linbpq.md) | `/etc/bpq32.cfg` | node callsign, node alias, locator |

That is the whole list today. Direwolf, the AX.25 port file, gpredict's
ground station and several plain-text configs are planned next ([gap
analysis, A1](../reference/catalog-gaps-2026-09.md)). Programs that rewrite
their own settings file every time they close, like WSJT-X and fldigi, will
stay on the list below: their first-run dialog is the safer place for the
value than a file written underneath them.

## Where to type it in the rest

| Program | Where | Fields |
|---|---|---|
| [WSJT-X](../packages/wsjtx.md), [JTDX](../packages/jtdx.md) | File → Settings → General | My Call, My Grid |
| [JS8Call](../packages/js8call.md) | File → Settings → General → Station | Callsign, Grid |
| [MSHV](../packages/mshv.md) | Options → Macros | My Call, My Grid |
| [fldigi](../packages/fldigi.md), and flmsg, flamp, fllog which share it | Configure → Operator | Callsign, Name, QTH, Locator |
| [FreeDV](../packages/freedv.md) | Tools → Options → Reporting | Callsign, Grid square, to appear on FreeDV Reporter |
| [QSSTV](../packages/qsstv.md) | Options → Configuration → Operator | Callsign, Locator |
| [Direwolf](../packages/direwolf.md) | `MYCALL` in `direwolf.conf` | see [Packet and Winlink](packet-winlink.md) |
| [Pat](../packages/pat.md) | `pat-winlink configure` | `mycall`, `locator` |
| [Xastir](../packages/xastir.md) | File → Configure → Station | Callsign, position, symbol |
| [YAAC](../packages/yaac.md) | its first-run wizard | Callsign, position |
| [gpredict](../packages/gpredict.md) | Edit → Preferences → General → Ground Stations | Name, latitude and longitude, or a Maidenhead locator |
| [CQRLOG](../packages/cqrlog.md) | Preferences → Station | Callsign, Locator |
| [QLog](../packages/qlog.md) | Settings → Station | Callsign, Locator (a station profile) |
| [tlf](../packages/tlf.md) | `logcfg.dat` in the contest directory | `CALL=`, `MYLOCATOR=` (hand-edited) |
| [HamClock](../packages/hamclock-next.md), [OpenHamClock](../packages/openhamclock.md) | first-run setup | Callsign, location |
| [Hammunition Hill](../packages/hammunition-hill.md) | `/etc/hammunition-hill/config.toml`, then `sudo systemctl restart hammunition-hill` | Callsign, and an ADIF log to show |

The dialog names come from each program's documentation and move a little
between versions; the field names do not.

## Things that are secrets, not settings

Some programs also want something that is a credential. Hammunition never
stores or writes any of these, and they never belong in a shared screenshot.

- **Winlink password** (Pat's `secure_login_password`): issued by Winlink when
  you first connect. Pat stores it in its own config file.
- **APRS-IS passcode** (Xastir, YAAC, Direwolf's iGate): a number derived from
  your callsign. Xastir ships a tool that prints it: `callpass N0TST`. It is
  a gate against accidental uploads, not strong security, but keep it to
  yourself.
- **Logbook of the World certificate** ([TQSL](../packages/trustedqsl.md)):
  ARRL issues it after verifying your licence, and it signs every contact
  you upload. TQSL's File → Backup writes a `.tbk` file; keep that somewhere
  safe and private.
- **QRZ.com or HamQTH logins** for callsign lookups in the loggers.

## The radio is a station value too

Alongside the callsign, `station set` takes the radio on the station — which
rig, on which port, at what speed — so one shared `rigctld` carries it to every
program instead of each one opening the serial port itself:

```sh
hammunition station set --rig yaesu-ft-991a \
    --rig-device /dev/serial/by-id/usb-...-if00-port0 --rig-baud 38400
hammunition install rig-service
```

The full walk-through, the program-by-program settings, radios with no CAT, the
flrig alternative and the unattended-station option are in
[Rig control](rig-control.md) (**D-073**).

## What was measured

The `station` commands and the file they write were run against this
checkout's engine on 2026-09-30. `callpass` was run from Xastir 2.2.0 on
Ubuntu 24.04 the same day. The dialog paths are the programs' own; this
project has not yet walked every row against every version it installs.
