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

It also puts `hammunition` on your PATH: `~/.local/bin/hammunition` becomes a
link to this checkout's `.venv/bin/hammunition`, so every command in these docs
works as written. It prints the link before making it, and it never replaces a
`~/.local/bin/hammunition` it did not create: a pipx install, a wrapper of your
own, or a link to a different checkout is left alone and named, and for a
different checkout it prints the one `ln -sfn` command that switches it.
`hammunition doctor` tells you which `hammunition` your PATH finds.

## If the shell says `hammunition: command not found`

Every example in these docs is written `hammunition ...`. Until the link is
on your PATH, run the engine by the full path of the checkout's
`.venv/bin/hammunition` instead. For a checkout at `~/src/Hammunition`:

```sh
~/src/Hammunition/.venv/bin/hammunition doctor
```

From inside the checkout, `.venv/bin/hammunition doctor` is the same program.
There are three ways to get here:

- **You have not run `./bootstrap.sh` yet.** Nothing has made the link. Run it.
- **Bootstrap made `~/.local/bin` for the first time.** Parrot
  (`/etc/profile.d/ZZparrot.sh`) and Debian 13 (the `~/.profile` a new
  account is given) add `~/.local/bin` to PATH at login, and only when the
  directory already exists. Bootstrap says `~/.local/bin is not on your PATH` and prints an
  `export PATH=...` line for `~/.profile`. On those two systems, logging out
  and back in is enough. On a system whose login scripts never add it, add
  the line bootstrap printed.
- **Bootstrap left an existing `~/.local/bin/hammunition` alone.** It said
  so and named it, and the rest of bootstrap carried on. If it is
  bootstrap's own link to a different checkout, bootstrap printed the
  `ln -sfn` command that switches it to this one. Anything else, such as a
  pipx install or a wrapper, is yours: `hammunition doctor`, run by its full
  path, names it and how to inspect it, and never prints a command that
  would replace it.

**You do not need `sudo` in front of it.** Run it as yourself: it adds
`sudo` to the steps that need root, and prints each one first. If you do
type `sudo hammunition`, sudo replaces your PATH with its own
`secure_path`, which does not include `~/.local/bin`, so it says
`command not found` even though `hammunition` works without sudo. Give
sudo the full path in that case.

## Or by hand

```sh
git clone https://github.com/ChiefGyk3D/Hammunition
cd Hammunition
python3 -m venv .venv
.venv/bin/pip install -e .
scripts/path-link.sh "$PWD"
hammunition doctor
```

`scripts/path-link.sh` is the script bootstrap runs to make the link, and it
follows the same rules. If the last line says `command not found`, see the
section above.

`hammunition doctor` is the read-only health check: target detected, catalog
loaded, `python3-venv` present, `~/.local/bin` on PATH, a compiler for source
builds, your callsign, device groups, attached hardware. It changes nothing,
names the one command that fixes each gap, and is the thing to paste when
asking for help.

`hammunition status` is the narrower "does it see my machine" check. It prints what
`/etc/os-release` says you are running, whether that is a Debian family the
engine will install on, how many of the catalog's manifests resolve on this
target, and where your transaction log will live:

```
Target: Parrot Security 7.4 (echo) (ID=parrot, version=7.4, arch=x86_64)
Debian family: yes
Catalog: /home/op/Hammunition/catalog
  321 packages, 319 of which resolve on this target
  19 profiles
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
| `hammunition update [NAME...]` | Installed versus the catalog, as a report; nothing runs and nothing is fetched | no |
| `hammunition list [packages\|profiles]` | Everything in the catalog, with each package's method **on this machine** | no |
| `hammunition show PROFILE` | A profile's docs, package list, and any consent disclosure | no |
| `hammunition install NAME... --dry-run` | The complete plan, changing nothing | no |
| `hammunition install NAME...` | The real thing — prompts before running | yes (for apt) |
| `hammunition uninstall NAME...` | Removes what Hammunition itself installed | yes (for apt) |

Read `hammunition install <profile> --dry-run` before every real install. It
prints every command, every group you will join, every config file that will
be written, and every consent gate you will meet — the same text the real run
shows, so nothing about the real run is a surprise.

A unit that does one thing for each of hundreds of items (a US Topo sheet, a
terrain tile, a Kiwix book) would fill the plan with near-identical blocks, so
the plan prints such a run once: the step with `<placeholders>`, the first item
written out in full, every item's own values on a line, and the total. Nothing
is left out of it. `hammunition install <profile> --dry-run --full` prints every
step expanded, and `--dry-run --json` always carries every step.

The first command of any run that installs from apt is `apt-get update`.
Stale package lists are the commonest way a correct plan fails — apt asks
the mirror for a file the pool has replaced — so the refresh is on by
default. Pass `--no-refresh` on a local mirror or a station with no uplink.

## Next

[How much disk you need](disk-space.md) says what a profile or the whole
catalog costs before you start. Back: [Getting started](index.md).
