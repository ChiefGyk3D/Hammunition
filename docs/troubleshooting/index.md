<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Troubleshooting

Organised by **symptom**, because that is how trouble presents — you do not
know which component is at fault yet, that is the whole problem. Find what you
are seeing; the fix names the component.

Every entry under *Installing* and *Running* was observed on a real machine
(the VM verification campaigns or field use), not imagined. The *Audio*
entries point into the audio-routing guide, which says for each one whether
it was measured on the bench or is documented behaviour not yet reproduced
here. Where a fix is distribution-specific it says so.

## Installing

- **[The dry run seems to hang, or an install sits silent](install-failures.md#slow-plan)** —
  the plan is checking publishers over the network; on a terminal it says
  what it is waiting on, and `HAMMUNITION_PROGRESS=1` makes it say so when
  stderr is not one.
- **[An install stops at a sudo password prompt for hours](../guides/offline-navigation.md#the-install-waits-at-a-sudo-password-prompt)** —
  the ticket expired during a long conversion; the engine now keeps it alive.
- **[A source build fails to fetch — HTTP 404](install-failures.md#dead-url)** —
  a pinned upstream URL moved. Report it; run the URL sweep.
- **[apt refuses with "held broken packages" on Parrot](install-failures.md#parrot-backports)** —
  the backports-vs-base development-library skew. Install the -dev packages
  from backports.
- **[`python3 -m venv` fails with ensurepip](install-failures.md#venv)** — a
  Debian netinst without `python3-venv`.
- **[A vendor .deb is refused for a file collision](install-failures.md#deb-conflict)** —
  `wsjtx-improved` versus the distribution's `wsjtx-data`, by design.
- **[A package is "refused by name" for a backend/repo](install-failures.md#refused)** —
  not a failure; the engine will not shim an unsupported combination.

## Running

- **[A GUI comes up blank or without decorations](running.md#wayland)** —
  Wayland; switch the session to X11. The classic is WSJT-X on a Pi.
- **[Permission denied on a serial device](running.md#dialout)** — you were
  added to `dialout` at install, but group membership needs a fresh login.
- **[A venv-installed program is "not found"](running.md#local-bin)** —
  `~/.local/bin` reaches PATH on next login; open a new shell.
- **["Address family not supported by protocol" from a packet program](running.md#ax25)** —
  Linux 7.1 removed kernel AX.25; the userspace path still works.
- **[A CH340 serial device vanishes the moment it is plugged in](running.md#brltty)** —
  `brltty` claimed it as a braille display. Ubuntu 24.04 and Mint, behind one
  kind of hub; measured per target.
- **[The FT8 waterfall is silent](../getting-started/first-contact.md#when-the-waterfall-is-silent)** —
  audio routing, covered in first contact.
- **[FT8 decodes nothing on a busy band](running.md#clock)** —
  the clock is more than a second out. `timedatectl`; with no network, a GPS
  keeps it, by a route that depends on the time daemon.
- **[GPS dead after the laptop slept](running.md#gps-after-suspend)** —
  the receiver is not re-enumerated on resume and gpsd keeps a quiet tty.
  `hammunition hardware apply` installs the resume step; park and wake by hand
  if it is still dead.
- **[A tray switch does nothing, or a group says "update hammunition-tray"](../guides/tray-controls.md#when-it-does-not-work)** —
  no polkit agent in the session, or an older helper than the panel.
- **[No position in QMapShack or the browser map](../guides/offline-navigation.md#11-your-position-in-qmapshack-the-gps-tether)** —
  the GPS tether is not running (it starts at your next login after install),
  or gpsd has no fix.
- **[The browser map has no Route control](../guides/offline-navigation.md#the-map-has-no-route-control-or-says-the-router-stopped)** —
  GraphHopper's graph is not installed, or the router stopped.
- **[A program cannot reach the radio, or the radio behaves erratically](../guides/rig-control.md#when-it-does-not-work)** —
  two programs have the serial port open. One owns it; the rest ask it.
- **[Everyone is heard, nobody hears you](../guides/audio-routing.md#transmit-the-alc-trap)** —
  transmit audio level. No ALC action.
- **[`rtl_test` says the dongle is busy](../guides/sdr.md#if-rtl_test-says-the-device-is-busy)** —
  the kernel's TV driver claimed it first.
- **[Direwolf or ardopcf: device busy](../guides/packet-winlink.md#1-direwolf-the-modem)** —
  PipeWire has the sound card; set its profile to Off.

## Audio and digital modes

Symptom first; each links to the entry in
[Radio audio](../guides/audio-routing.md#8-when-it-goes-wrong) or the
[digital-modes guide](../guides/digital-modes.md).

- **[The waterfall is flat or black](../guides/audio-routing.md#no-waterfall)** —
  the program is recording from the wrong source. `wpctl status` shows which.
- **[The waterfall is solid colour and decodes nothing](../guides/audio-routing.md#clipping)** —
  the input is clipping; lower the radio's USB output level.
- **[Tune keys the radio but shows no power](../guides/audio-routing.md#no-power)** —
  wrong output device, or the radio's data-mode audio source is the mic jack.
- **[The radio's sound card is not in the program's list](../guides/audio-routing.md#radio-missing)** —
  `cat /proc/asound/cards` says whether the kernel sees it at all.
- **[Desktop sounds go out over the air, or the radio keys by itself](../guides/audio-routing.md#notifications-on-air)** —
  the radio became the default output.
- **[SSTV pictures slant](../guides/audio-routing.md#sstv-slant)** — sound
  card clock error; calibrate once per card.
- **[It worked until I opened a second program](../guides/audio-routing.md#two-programs)** —
  one ham program per radio per session.
- **[All sound stopped after installing something](../guides/audio-routing.md#pulseaudio-removed)** —
  a package pulled in `pulseaudio`, which removes `pipewire-alsa`. The
  planned removal was measured on the bench, where Hammunition refused it
  (issue #61).
- **[WSJT-X's Test CAT fails](../guides/digital-modes.md#test-with-rigctl-before-you-blame-a-program)** —
  test the radio with `rigctl` first; then look for a second program holding
  the serial port.

## When nothing here fits

Each program's own known problems and real support channel are on its page
under [`docs/packages/`](../packages/index.md) — the `known_problems` and
`upstream_support` fields, straight from the manifest. That is where a problem
specific to one program, rather than to installing or launching it, belongs.
