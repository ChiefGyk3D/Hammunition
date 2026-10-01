<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Rig control (CAT)

CAT is the serial conversation between the computer and the radio: read the
frequency, set the mode, key the transmitter. Most modern radios speak it
over the same USB cable that carries their audio. Get it working once, in
one place, and every program on the station uses it.

**The rule that saves the most grief:** exactly one program opens the
radio's serial port. Everything else talks to that program over the
network, on this machine. Two programs opening the port directly works for
a while and then fails in ways that look like a broken radio.

You have two ways to be that one program. Both are in the
[`station`](../profiles/station.md) profile.

| | `rigctld` (from [hamlib](../packages/libhamlib-utils.md)) | [flrig](../packages/flrig.md) |
|---|---|---|
| What it is | A daemon with no window | A program with a front panel |
| Programs reach it at | `127.0.0.1:4532` as *Hamlib NET rigctl* | `127.0.0.1:12345` as *FLRig* |
| Good for | A station that runs unattended, satellites, scripts | Seeing and turning the knobs on screen |

Pick one. The `station` profile's own notes suggest flrig, because its
panel shows at a glance that the radio is answering. This page walks
`rigctld` first because every program on the station can speak to it, and
the flrig route is at the end. Either is right; running both against the
radio is not.

## 1. Find the radio's serial port

Plug the radio in and turn it on. Then:

```sh
ls -l /dev/serial/by-id/
```

Each line is a serial device with a name that does not change between
reboots. A radio with a built-in USB interface often shows **two** ports;
the radio's manual says which one is CAT. Use the `/dev/serial/by-id/...`
path everywhere, never `/dev/ttyUSB0`: the number changes with the order
things were plugged in.

If the directory does not exist, the radio is not being seen as a serial
device. `hammunition hardware list` shows what is plugged in and whether
the catalog recognises it.

!!! note "Permission denied?"
    Serial ports belong to the `dialout` group. The install added you to
    it, and group membership only takes effect at your next login. Log out
    and back in. See [Troubleshooting](../troubleshooting/running.md#dialout).

## 2. Find your radio's hamlib model number

```sh
rigctl -l | grep -i ft-991
```

The first column is the model number. A few, read from hamlib 4.5.5 on
2026-09-30:

| Radio | Model |
|---|---|
| Yaesu FT-991 / FT-991A | 1035 |
| Yaesu FT-891 | 1036 |
| Yaesu FT-710 | 1049 |
| Yaesu FT-817 / FT-818 | 1020 / 1041 |
| Icom IC-7300 | 3073 |
| Icom IC-705 | 3085 |
| Icom IC-9700 | 3081 |
| Kenwood TS-590SG | 2037 |
| QRP Labs QDX / QCX | 2052 |
| Hamlib Dummy (no radio, for testing) | 1 |

The numbers are stable across hamlib 4.x, but check your own list: a newer
hamlib knows more radios.

## 3. Match the baud rate to the radio's menu

The radio has a CAT baud rate in its menu, and hamlib has to use the same
one. Yaesu radios typically ship at 4800 or 38400; Icom radios over USB
usually accept 19200 or 115200. Set the radio to a fast rate it supports
and use that number below. Icom radios also have a CI-V address, which
hamlib's model already knows for the radio's default.

## 4. Test by hand

```sh
rigctl -m 1035 -r /dev/serial/by-id/usb-Silicon_Labs_CP2105...-if00-port0 -s 38400 f
```

Replace the model, the path and the speed with yours. It should print the
frequency the radio is on. `m` instead of `f` prints the mode. If it hangs
or prints an error, the port, the speed or the model is wrong; change one
thing at a time.

## 5. Run `rigctld` for everyone

```sh
rigctld -m 1035 -r /dev/serial/by-id/usb-...-if00-port0 -s 38400 -T 127.0.0.1
```

**Always pass `-T 127.0.0.1`.** Without it `rigctld` listens on every
network interface (its help says so: "default ANY"), which puts your
transmitter's controls on whatever network the laptop is on. On a machine
that also carries security tooling, that is not an acceptable default.

Leave it running and test it from another terminal:

```sh
rigctl -m 2 -r 127.0.0.1:4532 f
```

Model 2 is *NET rigctl*: "ask the rigctld on this address".

!!! info "Starting it with your session"
    Hammunition does not yet install a service for `rigctld`; making the rig
    part of the station configuration is planned
    ([gap analysis, A2](../reference/catalog-gaps-2026-09.md)). Until then,
    start it by hand or from your desktop's autostart.

## 6. Point every program at it

| Program | Where | What to set |
|---|---|---|
| [WSJT-X](../packages/wsjtx.md), [JTDX](../packages/jtdx.md), [JS8Call](../packages/js8call.md) | File → Settings → Radio | Rig: *Hamlib NET rigctl*. Network Server: `127.0.0.1:4532`. PTT method: *CAT* |
| [fldigi](../packages/fldigi.md) | Configure → Rig Control → Hamlib | Use Hamlib; Rig: *Hamlib NET rigctl*; Device: `127.0.0.1:4532` |
| [gpredict](../packages/gpredict.md) | Edit → Preferences → Interfaces → Radios | Host `127.0.0.1`, port `4532` |
| [CQRLOG](../packages/cqrlog.md) | Preferences → TRX control | Rig model 2 (*NET rigctl*), host `127.0.0.1`, port `4532`, and *do not* let it start its own `rigctld` |
| [Pat](../packages/pat.md) | `pat-winlink configure` | A `hamlib_rigs` entry with `"address": "localhost:4532", "network": "tcp"` |

The dialog names are from each program's own documentation. They move a
little between versions; the field names do not.

## The flrig route

[flrig](../packages/flrig.md) opens the port instead of `rigctld` and gives
you a front panel. In flrig, Config → Setup → Transceiver: choose the radio,
the `/dev/serial/by-id/` port and the baud rate, then *Init*. Then point the
other programs at flrig: WSJT-X's Rig is *FLRig FLRig* with Network Server
`127.0.0.1:12345`, and fldigi has its own *flrig* tab. Do not run `rigctld`
against the radio at the same time.

## The radio on another machine

When the radio sits beside a small computer in the shack and you operate
from somewhere else, run `rigctld` on the machine with the radio and
point the programs at that machine's address instead of `127.0.0.1`,
with `-T` set to an address only your own network can reach. Every
program above already speaks to it that way.

[ser2net](../packages/ser2net.md) is for the other case: software that
wants a raw serial port rather than hamlib, or a device hamlib does not
know. It serves a serial device on a TCP port, configured in
`/etc/ser2net.yaml`. It is not in the `station` profile, because
installing the package starts a root service whose shipped
configuration already listens on four loopback ports for the machine's
built-in serial ports; the package page says what that means and how to
turn it off. Never put either on a public address: there is no
encryption, and a CAT port is the transmitter's controls. Neither route
has been run against a real radio by this project.

## When it does not work

- **Nothing answers, no error** → baud rate or CI-V address mismatch. The
  radio's menu wins; make hamlib match it.
- **Works, then randomly stops** → a second program is opening the serial
  port. Close everything, start `rigctld` or flrig, then the rest.
- **Every transmission keys, but no audio goes out** → CAT is fine; this is
  audio. See [Radio audio](audio-routing.md).
- **The radio keys itself when a program starts** → the program is using RTS
  or DTR on the CAT port for PTT, and the interface wires those to PTT. Set
  PTT to CAT in that program, or disable RTS/DTR in its serial settings.

## What was measured

The hamlib model numbers, `rigctld`'s options and its listen-on-any default
were read from hamlib 4.5.5 (Ubuntu 24.04's package) on 2026-09-30. The
dialog paths are from each program's documentation. This project has not
yet driven every row of the program table against a real radio; the
FT-991A on the field laptop is the bench for that
([bench record](../reference/bench-verification-5430.md)).
