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

1. [Install the engine](install.md) — five minutes, no root until you install
   something.
2. [Your first profile](first-profile.md) — `station`, the floor every setup
   stands on, then a mode profile.
3. [First contact](first-contact.md) — a digital-modes station making its first
   decode.

Everything the engine does to your machine, it prints before it does it, and
records after. `--dry-run` shows the whole plan and changes nothing; a package
it cannot install is refused by name rather than skipped. You are never
surprised by this tool — that is the entire design.

## What you need

- A **Debian-family OS**: Parrot OS (primary), Debian 13, Ubuntu, Kali, or
  Raspberry Pi OS. The engine reads `/etc/os-release` and refuses anything
  that is not Debian-family rather than pretending to support it.
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
