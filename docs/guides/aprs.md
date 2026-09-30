<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# APRS

The Automatic Packet Reporting System: short position reports, weather
readings and text messages, broadcast on one shared VHF frequency and
repeated by digipeaters across a region. On a map it shows who is on the
air around you, right now, with no internet involved.

| Part | Program |
|---|---|
| The modem | [Direwolf](../packages/direwolf.md), the same one Winlink uses |
| A map client | [Xastir](../packages/xastir.md) (apt) or [YAAC](../packages/yaac.md) (Java) |
| Sending messages to pagers | [a2d](../packages/a2d.md) |
| A digipeater or iGate | Direwolf itself, or [aprx](../packages/aprx.md) |

## Install and the modem

```sh
hammunition install station packet
```

Set up Direwolf as in [Packet and Winlink, step
1](packet-winlink.md#1-direwolf-the-modem): the same `~/direwolf.conf`
works for APRS. Tune the radio to the APRS frequency for your region:

| Region | Frequency |
|---|---|
| North America | 144.390 MHz |
| Europe and most of ITU Region 1 | 144.800 MHz |

Other countries use others; your national society's band plan says which.
With Direwolf running you will see packets decoded within a few minutes in
most populated areas, each with its audio level. Receiving needs no
licence; transmitting does.

## A map: Xastir

Start Xastir. On first run it asks for your station:

1. **File → Configure → Station:** callsign, your position, a symbol. Your
   position is what you choose to broadcast. You can round it, or use a
   point that is not your house.
2. **Interface → Interface Control → Add → Networked AGWPE:** host
   `localhost`, port `8000`. That is Direwolf. Tick *Activate on Startup*,
   then **Start**.
3. **Map → Map Chooser:** pick a map. Online tile maps need the network;
   for offline maps see [Offline navigation](offline-navigation.md).

Stations appear as Direwolf decodes them. Click one for its details and
path.

!!! note "Use the AGWPE interface"
    Xastir's *AX.25 TNC* interface type opens a kernel AX.25 socket and
    fails on Linux 7.1 with *Address family not supported by protocol*.
    *Networked AGWPE* and *Serial KISS TNC* need no kernel stack and keep
    working. See [Xastir's page](../packages/xastir.md).

## A map: YAAC

[YAAC](../packages/yaac.md) is the portable Java client, deeper on
messaging and filtering. Its first-run wizard asks for callsign and
position; then **File → Configure → Ports → Add**, type **AGWPE**, host
`localhost`, port `8000`.

## The internet side: APRS-IS

APRS-IS carries the same packets over the internet, and sites like
[aprs.fi](https://aprs.fi/) draw them. A client can connect to it to show
distant stations. In Xastir: **Interface → Interface Control → Add →
Internet Server**, server `noam.aprs2.net` (or `euro.aprs2.net`, and so on),
port `14580`, your callsign, and your **passcode**:

```sh
callpass N0TST
```

`callpass` ships with Xastir and prints the passcode for a callsign. Without
it, a client can read APRS-IS but not send to it. Keep yours to yourself.

## Beaconing, digipeating and gating are decisions

Three things put traffic on a shared channel under your callsign. Each one
affects everyone else on the frequency, so none is on by default, in
Direwolf's shipped example or here.

- **Beaconing your position.** A `PBEACON` line in `direwolf.conf`, or the
  client's *transmit position* setting. Every 10 to 30 minutes is plenty for
  a fixed station; a moving one can use SmartBeaconing in the client.
- **Digipeating.** Direwolf can repeat other stations' packets with a
  `DIGIPEAT` line. A badly placed or badly configured digipeater floods the
  channel. Coordinate with your local APRS group before turning it on.
- **iGating.** Direwolf can pass what it hears to APRS-IS with `IGSERVER`
  and `IGLOGIN`, and, with `IGTXVIA`, pass messages the other way. Receive-only
  gating is harmless and helps coverage; transmit gating needs care.

Direwolf's shipped example documents each of these lines in place, and its
user guide explains them fully.

## When it does not work

- **Direwolf decodes nothing** → wrong frequency, or the audio level is far
  off 50. Listen: APRS bursts are unmistakable.
- **Xastir shows nothing Direwolf decodes** → the interface is not started,
  or it is the *AX.25 TNC* type. Interface Control shows its state.
- **Your beacons never appear on aprs.fi** → no iGate hears you. Transmit
  audio level first, then whether a digipeater is in range.

## What was measured

Direwolf's example lines were read from its 1.7 release and `callpass` was
run from Xastir 2.2.0 on Ubuntu 24.04, 2026-09-30. Xastir's kernel-socket
failure on Linux 7.1 is recorded in its manifest. The client dialogs follow
their own documentation; APRS on air from the field laptop is not yet in
the [bench record](../reference/bench-verification-5430.md).
