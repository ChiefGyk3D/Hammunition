<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Installing the engine

Hammunition is a Python engine plus a separate catalog of YAML manifests. The
supported install today is a git clone: the engine runs from the checkout, and
it finds the catalog by walking up from its own location, so nothing needs
configuring.

## The one-command way

```sh
git clone https://github.com/ChiefGyk3D/Hammunition
cd Hammunition
./bootstrap.sh
```

`bootstrap.sh` creates the virtualenv, installs the engine into it, installs
`python3-venv` if a netinst left it out (the only thing it does as root, and it
tells you first), and finishes by running `hammunition doctor` so you see
exactly what is ready. It is idempotent — safe to re-run after a `git pull`.

## Or by hand

```sh
git clone https://github.com/ChiefGyk3D/Hammunition
cd Hammunition
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/hammunition doctor
```

`hammunition doctor` is the read-only health check: target detected, catalog
loaded, `python3-venv` present, `~/.local/bin` on PATH, a compiler for source
builds, your callsign, device groups, attached hardware. It changes nothing,
names the one command that fixes each gap, and is the thing to paste when
asking for help. `hammunition status` is the narrower "does it see my
machine":

`hammunition status` is the "does it see my machine" check. It prints what
`/etc/os-release` says you are running, whether that is a Debian family the
engine will install on, how many of the catalog's manifests resolve on this
target, and where your transaction log will live:

```
Target: Parrot Security 7.3 (echo) (ID=parrot, version=7.3, arch=x86_64)
Debian family: yes
Catalog: /home/op/Hammunition/catalog
  242 packages, 240 of which resolve on this target
  15 profiles
Transaction log: /home/op/.local/state/hammunition/transactions.jsonl
  no transactions recorded
```

## One prerequisite the minimal images miss

The engine builds some software from source in a per-user virtualenv, so it
needs Python's venv support. Parrot and Kali ship it; a **Debian netinst**
does not, and `python3 -m venv` fails there with an ensurepip error. If you
installed from netinst:

```sh
sudo apt install python3-venv
```

A `.deb` with a vendored virtualenv is planned, so eventually this prerequisite
disappears; until then, it is the one manual step a bare Debian needs.

## What the commands mean

| Command | What it does | Needs root |
|---|---|---|
| `hammunition status` | What this machine is, and what has been done to it | no |
| `hammunition list [packages\|profiles]` | Everything in the catalog, with each package's method **on this machine** | no |
| `hammunition show PROFILE` | A profile's docs, package list, and any consent disclosure | no |
| `hammunition install NAME... --dry-run` | The complete plan, changing nothing | no |
| `hammunition install NAME...` | The real thing — prompts before running | yes (for apt) |
| `hammunition uninstall NAME...` | Removes what Hammunition itself installed | yes (for apt) |

Read `hammunition install <profile> --dry-run` before every real install. It
prints every command, every group you will join, every config file that will
be written, and every consent gate you will meet — the same text the real run
shows, so nothing about the real run is a surprise.
