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

## 5. Say which radio is on the station, and the service is there

Tell Hammunition the radio, the port and the speed once:

```sh
hammunition station set --rig yaesu-ft-991a \
    --rig-device /dev/serial/by-id/usb-Silicon_Labs_CP2105_...-if00-port0 \
    --rig-baud 38400
```

`--rig` takes a radio the catalog knows ([`hammunition hardware list`](../reference/cli.md)),
or `hamlib:<model>` for one it does not (`--rig hamlib:3073`, with `--rig-baud`
then required). The value is checked against the catalog and against your
machine's hamlib as you set it; a speed outside the backend's range, or a
value that is not a rig, is refused there and then.

Then install the service (it ships in the [`station`](../profiles/station.md)
profile):

```sh
hammunition install rig-service
```

The plan prints the unit file it writes, the command line it runs with the
serial elided, and the plain warning that **any program on this machine can
key the transmitter through `127.0.0.1:4532`, which has no password**. It
writes `~/.config/systemd/user/hammunition-rigctld.service`, binds it to the
radio's USB port so it stops when the radio is switched off, and enables it so
it starts at your login. `-T 127.0.0.1` is fixed: the service never listens
beyond loopback.

Check it:

```sh
systemctl --user status hammunition-rigctld
rigctl -m 2 -r 127.0.0.1:4532 f     # model 2 is NET rigctl: "ask the rigctld here"
hammunition doctor                  # reports the service, the port and the device
```

Changing a rig value (`station set --rig-baud …`) reaches the service only
through `hammunition install rig-service` again, which rewrites the file and
restarts it. `hammunition uninstall rig-service` disables it and removes the
file. To choose flrig's panel instead, see [the flrig route](#the-flrig-route).

!!! info "A station with nobody logged in"
    By default the service runs while you are logged in and stops with your
    last session. For a remote or headless station, `hammunition station set
    --unattended` turns on linger (through the power-control helper) so your
    user services keep running after you log out — the transmitter then keyable
    through 4532 with nobody at the machine. `--no-unattended` reverses it. The
    plain `loginctl enable-linger` does the same by hand.

## 6. Point every program at it

Every program below reaches the service as *Hamlib NET rigctl*, hamlib model
2, at `127.0.0.1:4532`. The only question is where each keeps the setting.

| Program | Where | What to set |
|---|---|---|
| [WSJT-X](../packages/wsjtx.md), [JTDX](../packages/jtdx.md), [JS8Call](../packages/js8call.md) | File → Settings → Radio | Rig: *Hamlib NET rigctl*. Network Server: `127.0.0.1:4532`. PTT method: *CAT* |
| [fldigi](../packages/fldigi.md) (and flmsg, flamp) | Configure → Rig Control → Hamlib | Use Hamlib; Rig: *Hamlib NET rigctl*; Device: `127.0.0.1:4532` |
| MSHV | Options → Rig control | *Hamlib NET rigctl*, `127.0.0.1:4532` |
| [gpredict](../packages/gpredict.md) | written for you | Hammunition writes `~/.config/Gpredict/hwconf/hammunition.rig` pointing at `127.0.0.1:4532`; pick it under Edit → Preferences → Interfaces → Radios. Doppler needs CAT, so a PTT-only rig cannot tune |
| tlf | `logcfg.dat` | `RIGMODEL=2`, `RIGPORT=localhost:4532` (whether `RIGPORT` takes host:port for model 2 is not yet measured here) |
| [Direwolf](../packages/direwolf.md) | `direwolf.conf` | `PTT RIG 2 localhost:4532` — a rig *number*, not a name. The packet radio is often not the station's CAT rig |
| [Pat](../packages/pat.md) | `pat configure` or its web settings | A `hamlib_rigs` entry with `"address": "localhost:4532", "network": "tcp"`, then `rig` per transport |
| [FreeDATA](../packages/freedata.md) | Settings → Radio | control *rigctld* (never *rigctld_bundle*, which starts a second one on 4532); IP `127.0.0.1`, port `4532` (the shipped defaults) |
| Mercury | command line | key through Pat's `rig`, or `-R 2 -A 127.0.0.1:4532` (not yet measured here) |
| [CQRLOG](../packages/cqrlog.md) | Preferences → TRX control | Rig model 2 (*NET rigctl*), host `127.0.0.1`, port `4532`, and **untick *Run rigctld*** or it starts a second one on 4532 |
| [QLog](../packages/qlog.md), KLog, xlog, QSSTV, FreeDV | each program's own rig dialog | *Hamlib NET rigctl*, `127.0.0.1:4532` |
| SuperSDR, OpenHamClock's rig bridge | command line or their settings | a `rigctld` client: `127.0.0.1:4532` |

[Xastir](../packages/xastir.md) and [YAAC](../packages/yaac.md) speak no CAT at
all; they key through Direwolf. `ardopcf` is keyed by Pat's `rig`, a serial
line, or VOX.

The dialog names are from each program's own documentation. They move a little
between versions; the field names do not.

## A radio with no CAT (PTT only)

A radio hamlib cannot drive — a BTECH or Baofeng handheld or mobile, keyed
through a Digirig or SignaLink — is still carried by the same service, so every
program is configured for it exactly as above. Name the radio, the interface's
serial port, and which control line keys it:

```sh
hammunition station set --rig btech-uv-50pro \
    --rig-device /dev/serial/by-id/usb-...-if00-port0 \
    --rig-ptt-line rts        # or dtr, whichever your interface keys it on
```

The service runs `rigctld` with hamlib's dummy model and that line; a program's
PTT method *CAT* through 4532 asserts the line. **There is no frequency
control** — the programs read the dummy's frequency, so set the band by hand on
the radio. If the radio keys itself on audio instead, `--rig-ptt-line vox`: no
service runs, and each program's PTT method is set to *VOX*.

!!! warning "Opening the port can key the radio"
    Linux raises RTS and DTR when a serial port is opened, before hamlib sets
    them, so a radio keyed on either line may key briefly when the service
    starts. Until this is measured on your interface, start the service with the
    radio switched off or on a dummy load.

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
were read from hamlib 4.7.2 (Parrot's backport) on 2026-10-01; which programs
link hamlib was read with `ldd`, and each program's configuration keys from the
strings in its binary. A browser's HTTP POST to `127.0.0.1:4532` was measured
against hamlib's dummy model and **did not** key it, which is why the service
binds 4532 directly with no filter in front of it (D-073 §11).

This project has not yet driven the service or any row of the program table
against a real radio: the FT-991A and the UV-50PRO on the field laptop are the
bench for that ([bench record](../reference/bench-verification-5430.md)), and
until it has run the radio pages say `untested`. The design and its rulings are
[D-073](../DECISIONS.md).
