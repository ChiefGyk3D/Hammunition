<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Packet and Winlink

Email by radio, for the day the internet is not there. This guide builds
the chain in the order that lets you test each link before adding the next:
the modem, then the mail client over the internet, then the mail client
over the air.

| Link | Program | What it does |
|---|---|---|
| Modem, VHF/UHF | [Direwolf](../packages/direwolf.md) | Turns the sound card into a 1200-baud packet TNC |
| Modem, HF | [ardopcf](../packages/ardopcf.md) | ARDOP, the open HF Winlink modem |
| Modem, HF | [Mercury](../packages/mercury.md) | An open HF modem Pat drives through its VARA transport |
| Mail client | [Pat](../packages/pat.md) | Winlink email, with a web interface |
| Gateways | Winlink RMS stations | Other hams' stations that move your mail to and from the internet |

## Install

```sh
hammunition install station packet --dry-run
hammunition install station packet
```

The [`packet`](../profiles/packet.md) profile carries Direwolf, Pat, ARDOP,
Mercury, FreeDATA, the AX.25 tools, LinBPQ, the packet terminals and the APRS clients. If you
have no mail client, an interactive install offers one; it never installs
one silently.

!!! note "No kernel AX.25? That is fine."
    Linux 7.1 removed the kernel's AX.25 stack, and several distributions
    already ship without it. This guide never needs it: Pat talks to
    Direwolf directly over Direwolf's AGW port. The kernel stack is only for
    the older tools that need an `ax0` interface; see [Kernel
    AX.25](../reference/kernel-ax25.md).

## 1. Direwolf: the modem

Set up [rig control](rig-control.md) and [radio audio](audio-routing.md)
first. Then find the radio's sound card by its ALSA name:

```sh
sudo apt install alsa-utils   # if arecord is missing
arecord -l
```

A line like `card 1: CODEC [USB Audio CODEC], device 0` gives the card's
name, `CODEC`. Use the name, not the number: `plughw:CARD=CODEC,DEV=0`
keeps working when the card numbers change.

Create `~/direwolf.conf`. Direwolf reads that file when started from your
home directory, and searches your home directory if it is not in the
current one:

```text
# The radio's sound card, by name. Both directions.
ADEVICE plughw:CARD=CODEC,DEV=0
ACHANNELS 1
CHANNEL 0
# Your callsign, in place of the example's N0CALL placeholder.
MYCALL N0CALL
MODEM 1200
# Key the radio through rigctld (model 2 = NET rigctl), see the rig-control guide.
PTT RIG 2 localhost:4532
# The ports Pat and the other clients connect to.
AGWPORT 8000
KISSPORT 8001
```

The `PTT` line depends on your interface. The shipped example lists the
others: `PTT /dev/ttyUSB0 RTS` for an interface that keys on RTS (a Digirig
does), `PTT CM108` for a USB sound card with a PTT pin. Use the
`/dev/serial/by-id/` path, not `ttyUSB0`.

Start it:

```sh
direwolf
```

It prints the audio device it opened and ends with the AGW and KISS ports
it is listening on. Leave it running. Tune the radio to your local packet
frequency (a Winlink gateway's, found in step 4), and every packet heard is
printed with an **audio level**, like `audio level = 50(25/24)`. Aim for
roughly 50; adjust the radio's USB audio output level to get there.

!!! warning "Device busy?"
    Direwolf and ardopcf open the sound card directly through ALSA. If
    PipeWire already has it open, they fail with *device busy*. In
    `pavucontrol`, **Configuration** tab, set the radio's card profile to
    **Off**: PipeWire lets go of it, and the desktop keeps its own sound.
    Unmeasured on the field laptop.

!!! info "As a service"
    The Direwolf package also installs a system service, `direwolf.service`,
    which runs Direwolf as its own `direwolf` user from
    `/etc/direwolf.conf` and only starts if that file exists (read from
    Ubuntu 24.04's package, 2026-09-30). Use it for an unattended node.
    For a station you sit at, running it in your session as above is
    simpler.

## 2. Pat: configure

Debian and Ubuntu install Pat's command as **`pat-winlink`**, not `pat`.

```sh
pat-winlink configure
```

That opens the configuration in your editor. Set these, leaving everything
else as it is:

```json
"mycall": "N0CALL",
"locator": "FN31pr",
"ax25": {
  "engine": "agwpe"
},
"agwpe": {
  "addr": "localhost:8000",
  "radio_port": 0
},
```

`engine` is the change that matters: Pat 0.15.1's default is `"linux"`, the
kernel stack. `agwpe` points it at Direwolf's port 8000 instead (defaults
read from Pat 0.15.1, 2026-09-30). Keep the rest of the `ax25` block as it
was when you edit it.

## 3. Pat: send a message over the internet first

This proves Pat, your account and your mailbox before any radio is
involved.

```sh
pat-winlink http
```

Open <http://localhost:8080>. Compose a message to yourself, then use
**Action → Connect** with the *telnet* alias, which reaches Winlink's
servers over the internet. Your first connection registers your callsign
with Winlink; follow the instructions in the message Winlink sends back,
which include setting a password. Put that password in Pat's
`secure_login_password`, and keep it private: it is the only thing between
your callsign and anyone else sending mail as you.

The web interface only listens on `localhost`. Leave it that way.

## 4. Find a gateway

```sh
pat-winlink rmslist --mode packet --sort-distance
```

Pat downloads Winlink's list of gateways and prints them nearest first, with
callsign, frequency and distance. Pat needs your locator for the distances.
Pick one you can reach; a packet gateway on VHF needs line of sight or a
digipeater.

## 5. Send it over the air

Tune the radio to the gateway's frequency, with Direwolf running. Then, in
the web interface's Connect dialog, choose transport **ax25**, enter the
gateway's callsign (with its SSID, like `N0CALL-10`), and connect. From the
command line, the same thing:

```sh
pat-winlink connect ax25+agwpe:///N0CALL-10
```

Direwolf's window shows the packets going both ways. Pat's shows the
session, and mail in the outbox leaves.

## HF: ARDOP

Winlink on HF runs through [ardopcf](../packages/ardopcf.md). It is a modem
like Direwolf, but for HF, and it includes its own web interface.

```sh
ardopcf -G 8514 8515 plughw:CARD=CODEC,DEV=0 plughw:CARD=CODEC,DEV=0
```

`8515` is the port Pat expects (its default `ardop.addr`), the two device
names are capture and playback, and `-G 8514` serves ardopcf's own web
interface at <http://localhost:8514>, where you can watch levels and
traffic. For PTT, either let Pat key the radio through hamlib (set
`"ptt_ctrl": true` and a `rig` in Pat's `ardop` section, pointing at a
`hamlib_rigs` entry for `localhost:4532`), or give ardopcf `-p` with the
radio's serial port for RTS keying. Not both: ardopcf's own usage notes warn
against two programs keying through the same port.

```sh
pat-winlink rmslist --mode ardop --band 40m --sort-distance
pat-winlink connect 'ardop:///N0CALL?freq=7101.5'
```

`freq` is the dial frequency in kHz, set through rig control before the
call. The gateway list gives each station's.

!!! note "ardopcf and CM108 keying"
    The catalog builds ardopcf with one compiler warning relaxed, because
    GCC 14 turned it into an error. That warning is a real bug in its CM108
    PTT path. Test CM108 keying before relying on it; RTS and CAT keying are
    unaffected. [ardopcf's page](../packages/ardopcf.md) has the detail.

## Choosing an HF modem

Three free HF modems come with the profile, and the one to use is decided
by the station at the other end, because none of them understands the
others on the air:

- **[ardopcf](../packages/ardopcf.md)** for a gateway or station that runs
  ARDOP. Pat's `ardop://` transport, above.
- **[Mercury](../packages/mercury.md)** for a station that runs Mercury.
  Mercury speaks VARA HF's TCP interface to your software, so Pat reaches
  it through its `varahf://` transport with no change. It does not speak
  VARA's waveform, so a gateway that runs only VARA is out of reach.
- **[FreeDATA](../packages/freedata.md)** for messages and files straight
  to another FreeDATA station, in a browser. It is its own system, not
  Winlink, and Pat does not use it.

VARA itself, the proprietary modem many Winlink gateways also run, is not
installed by Hammunition in 1.0; see [not carried](../reference/not-carried.md).
Its Wine prefix is post-1.0 and optional now that Mercury covers the free
end of Pat's VARA transport.

All three transmit on HF when a client keys them. A licence and the band
plan apply, and nothing here keys the rig without your rig-control setup.

## HF: Mercury

```sh
mercury -i plughw:CARD=CODEC,DEV=0 -o plughw:CARD=CODEC,DEV=0 -P serial -A /dev/ttyUSB0
```

Mercury listens for Pat on port 8300, which is Pat's default `varahf.addr`
(`localhost:8300`), so Pat's `varahf` section can stay as it is. `-i` and
`-o` are capture and playback, and `mercury -z` lists the sound devices.
`-P serial -A` keys the radio on the serial port's RTS line, DigiRig style;
`-R <model> -A <device>` keys through hamlib instead, and with no `-P`
Mercury leaves keying to Pat (`"ptt_ctrl": true` and a `rig` in Pat's
`varahf` section, as for ARDOP above). Kali's packaged Mercury is 1.9.13, which has no `-P`: use hamlib
or Pat's keying there.

```sh
pat-winlink connect 'varahf:///N0CALL'
pat-winlink connect 'varahf:///N0CALL?p2p=true'
```

The second form is a peer-to-peer session with another operator rather
than a gateway. Pat logs "got a vara command I wasn't expecting" for
Mercury's `SN` and `BITRATE` status lines; that is harmless. Mercury's
channel-busy detector is off by default, so listen before you connect.

## Station to station: FreeDATA

```sh
freedata
```

That starts FreeDATA's server and opens <http://127.0.0.1:5000/gui> in
your browser. Before anything else, open Settings and replace the example
callsign AA1AAA and grid JN48ea with yours, then choose the sound devices
and the keying (rigctld, flrig, serial PTT or VOX). Stop the server when
you are done: it has no login, and [its page](../packages/freedata.md)
says why that matters in a browser you also use for the web.

## Keyboard packet and BBSes

For a live connection to a packet BBS or node rather than mail, the
terminals in the profile connect to the same Direwolf port:
[Paracon](../packages/paracon.md) and [QtTermTCP](../packages/qttermtcp.md)
to the AGW port 8000, anything speaking KISS to 8001.
[LinBPQ](../packages/linbpq.md) is a whole node: a BBS, a chat server and a
Winlink gateway of your own, and a larger project than this guide.

## What was measured

Pat's command name, its subcommands, its default configuration and its
transport list were read from Pat 0.15.1 (Ubuntu 24.04) on 2026-09-30.
Direwolf's example configuration was read from its 1.7 release, its
service file and its hamlib linking from Ubuntu 24.04's package. ardopcf's
options are from its own usage notes at the release the catalog builds.
The [packet VM campaign](../reference/vm-campaign-packet-debian13.md)
covers the install on Debian 13; a message sent over the air from the field
laptop is not yet in the [bench record](../reference/bench-verification-5430.md).

Mercury's options are from its 1.9.15 `-h` and README. On 2026-09-30,
Debian's Pat 0.16.0 carried a message peer to peer (`varahf:///…?p2p=true`)
between two Mercury 1.9.15 instances on the field laptop, their audio
crossed through named pipes at real time and PTT set to none: no radio and
no sound card were involved, and the session took about two minutes for one
line of text. Mercury over the air, and FreeDATA's server, window and audio
path, have not been exercised here.
