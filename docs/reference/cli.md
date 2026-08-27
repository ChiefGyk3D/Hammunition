<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# CLI reference

The `hammunition` command. This is the M1 walking skeleton: **the apt backend
and nothing else**. Six further backends are measured, named and scheduled for
1.0 (`docs/DESIGN.md` §6), and a package needing one is **refused by name**
rather than skipped — see [What it refuses](#what-it-refuses).

## Installing the engine

A git clone is the supported install. The wheel carries the engine; the catalog
is a separate tree, and the CLI finds `catalog/` by walking up from its own
location, so running it from a checkout needs no configuration.

```
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/hammunition status
```

Override the catalog location with `--catalog DIR` or `HAMMUNITION_CATALOG`.
A directory with no `packages/` inside it is an error rather than an empty
catalog, because an empty catalog makes `list` print nothing and look like an
answer.

## Verbs

### `hammunition status`

What this machine is, what the catalog holds, and what has been done here.

```
Target: Debian GNU/Linux 13 (trixie) (ID=debian, version=13, arch=x86_64)
Debian family: yes
Catalog: /home/op/Hammunition/catalog
  58 packages, 56 of which resolve on this target
  4 profiles
Transaction log: /home/op/.local/state/hammunition/transactions.jsonl
  no transactions recorded
```

The target line reports what `/etc/os-release` said, not what we concluded from
it. A system that declares no `ID` is an error, never a guess — see
`docs/DESIGN.md` §8.

### `hammunition list [all|packages|profiles]`

Everything in the catalog, with each package's install method **on this
machine**. A package that does not resolve here says `unsupported here` rather
than being hidden; a package with a recorded `broken` or `retired` status is
flagged with it.

### `hammunition show PROFILE`

A profile's documentation, its package list, and — for a gated profile — the
full consent disclosure, printed without installing anything. This is how an
operator reads a disclosure before deciding, rather than while being asked.

### `hammunition install NAME... [--dry-run] [--yes] [--refresh] [--user NAME]`

Names may be packages or profiles, mixed freely.

| Flag | Effect |
|---|---|
| `--dry-run` | Resolve everything, print exactly what would run, change nothing |
| `--yes` | Skip the confirmation. **Does not satisfy a consent gate** (D-021) |
| `--refresh` | Run `apt-get update` as the transaction's first command |
| `--user NAME` | Who to add to groups. Defaults to `$SUDO_USER`, then `$USER` |

## How a run is ordered

Resolution is a distinct phase that finishes before anything is executed
(**D-016**). In order:

1. **Detect the target** from `/etc/os-release`. A non-Debian-family system is
   refused here; there is no shim that makes it appear to work.
2. **Expand** the requested names — profiles into their packages, and any
   `depends` that names another manifest.
3. **Order** by `after`, which is sequencing rather than dependency. A cycle is
   reported; it does not hang.
4. **Resolve** each manifest against `(distro, version, arch)`. No matching
   install block means this target is genuinely unsupported for that package.
5. **Check what this engine can actually do** — see below.
6. **Ask apt once**, about every distro package the whole transaction needs,
   the manifests' own packages and their `depends` together.
7. **Print the plan**, in full, for every run and not only for `--dry-run`.
8. **Present any consent gate**, then confirm, then execute.

If anything in steps 2–6 fails, **every** failure is printed together and
nothing is changed. Reporting only the first would have the same shape as the
defect this is built against: fix one, re-run, meet the next.

## What it refuses

Each of these is a named refusal with a remedy, never a silent skip. A
capability matrix that reports coverage the engine does not have is the shim
`CLAUDE.md` forbids.

| Situation | What you see |
|---|---|
| A `source`, `git`, `binary`, `venv` or `pipx` install block | the backend named, and that it is scheduled but not written |
| A manifest declaring third-party `apt_repos` | that adding a repository with a pinned key is a disclosed modification of its own |
| A manifest with `config_files` | that station-local configuration is the open design question it waits on (`docs/DESIGN.md` §15.3) |
| A `system_modifications` kind other than `group_membership` | the kind, by name |
| A package whose status is `broken` or `retired` | the recorded reason, verdict and date |
| A dependency apt has no candidate for | which name, and whether it came from `install` or `depends` |
| No apt package lists at all | that this is a stale-lists problem, with `--refresh` as the remedy |
| A group membership with no identifiable operator | that `--user` is needed |

The dependency check is the one that earns its keep. **D-016** names four AHRL
dependency lines suspected of failing silently for years — `fftw2` (FFTW
version 2), `libgtk2.0-dev` (EOL), `python3-tksnack`, and an OCaml binding
fldigi does not use. The only reason nobody knows is that nothing ever asked
apt. This asks.

## Privilege

`requires_root` is a property of each command, not of the run. Unprivileged
commands stay unprivileged, `sudo` is added in exactly one place, and
resolution never asks for it at all — so `--dry-run` works as a normal user.

Only two kinds of privileged command exist today: `apt-get`, and `gpasswd
--add` for a manifest's declared `group_membership`. Both are printed before
they run and recorded in the transaction log.

## Consent gates

A gated profile presents its disclosure before anything runs. `--yes` is
accepted by the call and deliberately never read: a gate a convenience flag
walks through is not a gate (**D-021**). In a script, set the profile's own
`HAMMUNITION_ACCEPT_*` variable to `1`. With no terminal and no variable, the
run stops — silence is not consent, and "nobody was asked" is recorded
differently from "somebody said no".

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success, or a dry run that resolved cleanly |
| 1 | A command failed while running, or the system is unsupported |
| 2 | The transaction could not be planned — every blocker is printed |
| 3 | A consent gate was declined, or could not be presented |

## What is recorded

Every run appends to the transaction log — format in
`docs/reference/transaction-log.md`. Each command is logged **before** it runs
and its outcome after, so a run killed mid-`apt-get` leaves a record that the
command was started. That is the state an operator needs to see, and a log
written only on success would hide it.

Hammunition does not roll back. It tells you what it did (**D-004**). On a
failure the run stops at that command, and the count that completed is printed
along with the log's location.

## What is not here yet

`uninstall` is not written. The log it will read is being written correctly
now, which is the part that cannot be added retroactively.
