<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Getting started

Hammunition turns a fresh Debian-family install into a working amateur radio,
SDR and RF workstation. This section is the path from that fresh install to
your first decoded signal, written so a licensed ham with moderate Linux
experience never has to read a forum thread to finish.

The order that works:

1. **[Installation](installation.md)** — the full, numbered walkthrough, with
   every command and the output it prints, from a fresh machine to an installed
   and verified profile, with the differences for each supported system. Start
   here if you want nothing left out. The pages below are the shorter route.
2. [Install the engine](install.md) — the short form: five minutes, no root
   until you install something. `./bootstrap.sh` puts `hammunition` on your
   PATH, which is how every example here runs it; if your shell says `command
   not found`, that page says what to run instead.
3. [How much disk you need](disk-space.md) — one or two profiles fit in about
   5 GB, the whole catalog in about 55 GB, and offline maps and Wikipedia are
   what make a disk large. Every figure says where it came from.
4. [Your first profile](first-profile.md) — `station`, the floor every setup
   stands on, then a mode profile.
5. [First contact](first-contact.md) — a digital-modes station making its first
   decode. The full walk-through is
   [FT8 and the digital modes](../guides/digital-modes.md), with
   [Radio audio](../guides/audio-routing.md) beside it.
6. [The guides](../guides/index.md) — rig control, audio and the clock once,
   then FT8, Winlink, APRS, SDR listening, satellites, each start to finish.

Everything the engine does to your machine, it prints before it does it, and
records after. `--dry-run` shows the whole plan and changes nothing; a package
it cannot install is refused by name rather than skipped. You are never
surprised by this tool — that is the entire design.

## What you need

- A **Debian-family OS**: Parrot OS (primary), Debian 13, Ubuntu, Kali, or
  Raspberry Pi OS. The engine reads `/etc/os-release` and refuses anything
  that is not Debian-family rather than pretending to support it.
  [What works on which desktop](../desktops.md) says what is measured on
  KDE Plasma, Xfce, LXQt and the rest; the tray switches in particular
  depend on it.
- **Disk space.** About 5 GB free for one or two profiles, about 55 GB for the
  whole catalog; [the disk page](disk-space.md) has every figure and its
  source.
- A normal user account with `sudo`. The engine drops to your user wherever it
  can and asks for `sudo` only for apt and system changes.
- An internet connection. Source builds and pinned artifacts are fetched and
  verified against a checksum; nothing unverified is ever installed.
- For a **digital-modes station**: a radio, an audio interface between it and
  the computer (a sound-card interface or a Digirig-class device), and CAT
  control if you want frequency and mode followed automatically.

## What you do not need

- To be root to plan anything. `list`, `status`, `show` and `--dry-run` need
  no privileges at all.
- To trust the tool. Read the plan. It is complete and accurate, not
  approximate — if it were not, that would be a bug worth filing.
- To install everything. Profiles are opt-in bundles; nothing lands on your
  machine that you did not ask for, and RF-security tooling sits behind an
  explicit consent gate.

## If something goes wrong

[Troubleshooting](../troubleshooting/index.md) is organised by symptom. Start
with *Installing* if a plan or an install stopped, and *Running* if a program
installed but misbehaves. `hammunition doctor` is read-only and names the one
command that fixes each gap it finds.
