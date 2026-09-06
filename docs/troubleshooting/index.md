<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Troubleshooting

Organised by **symptom**, because that is how trouble presents — you do not
know which component is at fault yet, that is the whole problem. Find what you
are seeing; the fix names the component.

Every entry here was observed on a real machine (the VM verification campaigns
or field use), not imagined. Where a fix is distribution-specific it says so.

## Installing

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
- **[The FT8 waterfall is silent](../getting-started/first-contact.md#when-the-waterfall-is-silent)** —
  audio routing, covered in first contact.

## When nothing here fits

Each program's own known problems and real support channel are on its page
under [`docs/packages/`](../packages/index.md) — the `known_problems` and
`upstream_support` fields, straight from the manifest. That is where a problem
specific to one program, rather than to installing or launching it, belongs.
