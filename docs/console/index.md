<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# The console: reference

`hammunition console` is the full-screen terminal front end of the engine. This page is its reference: how it works, what it
never does, its keys and its screens. The walkthrough from a fresh install is [The console](../getting-started/console.md).

It is part of the engine: the same release and the same version, started with `hammunition console`. It has no install logic,
no package names and no catalog parser of its own; it asks the engine, through the engine's `--json` documents
([D-059](../reference/json-interface.md)), and runs the engine's own commands. Whether it works well over SSH or on a
Raspberry Pi has not been measured.

## What it is

Eight screens: Home, Install, Station, Secrets, Repeaters, Logs, Update and Help. Every action is a command you could type yourself, and the console
shows it before it runs. Hardware setup is one first-run step on Home (`hammunition hardware apply`, in a pane, with the
engine's own prompts); everything else about hardware, and maps, is left to the CLI and to
[hammunition-tray](https://github.com/ChiefGyk3D/hammunition-tray) for now.

## Requirements

- Hammunition itself. The console is a subcommand, so there is nothing else to install except its one dependency,
  [urwid](https://urwid.org/) 2.6 or later: `sudo apt install python3-urwid` on the Debian family (Debian 13 and Parrot carry
  2.6.16, Ubuntu 24.04 2.6.10, Ubuntu 26.04 and Kali 3.0.4), or `pip install 'hammunition[console]'` inside a virtualenv, which
  does not see the archive's module. `./bootstrap.sh` installs it into the engine's virtualenv for you.
- Python 3.11 or later.
- A terminal of at least 80x24. It refuses to start without a terminal, with `TERM=dumb`, or as root, and without urwid it
  prints one line naming the install command and exits 2.

`hammunition console --help` lists the keys and the exit codes; `hammunition console --version` prints the engine's version,
because there is no second one.

## How it works

Three channels, each with one job.

1. **Reads** run `hammunition <verb> --json` in a worker thread and parse the one document it prints. The console reads only
   the verbs listed in [what it reads](contract.md), refuses a document whose `schema` it does not know, and
   shows the engine's version from the first document's `engine` field. It never compares it with anything: the console and
   the engine are one release.
2. **Writes** run the real `hammunition` command inside a terminal pane. The child owns the tty: sudo's password prompt, the
   group choice and any consent prompt reach the engine untouched, typed by you. The console sees only the exit code, then
   reads again.
3. **Its own config**, `~/.config/hammunition-console/config.toml`: the last screen, the colour theme, whether you dismissed
   the first-run checklist. Nothing else. (A crash writes `crash.log` beside it with the exception type and its frames, never a
   message.)

The plan always comes first: choosing a profile shows the engine's own dry run (`--dry-run`), grouped as the engine groups it,
and nothing runs until you press `R` on it.

The engine it runs is the one that started it: the console launches `python -m hammunition` with the interpreter it is itself
running under, never whatever `hammunition` happens to resolve to on `PATH`, so a checkout's virtualenv, the
bootstrap-linked `~/.local/bin/hammunition` and a packaged install each drive their own engine.

## What it never does

- It never answers a consent prompt for you: you type yes into the engine's own prompt, in the pane.
- It never runs anything but the engine's own commands (and the apt upgrade the engine's update report offers).
- It never writes a secret anywhere: one you enter lives in its memory for the engine commands it starts and is cleared when you quit.
- It never stores your callsign, grid square or any station value; the engine's station file is the only copy.
- It never fetches anything from the network itself; the engine does, and it asks GitHub, git hosts and PyPI only when you press u on Update.

Also: it never passes the engine's assume-yes flag, never sets a scripted-consent environment variable and removes any you
exported from the environment of everything it starts, never runs a `doctor` fix (it shows the engine's fix text and leaves the
command to you), and never runs as root. The header says only "station: set" or "not set", and the Station screen hides
values until you ask.

## Keys

| Keys | Meaning |
|---|---|
| `1-7` | open the screen with that number (Home) |
| `Enter` | open the selected row |
| `b / Esc` | go back; changes nothing (in a text prompt only Esc: b is typed) |
| `?` | help |
| `q` | quit |
| `r` | refresh this screen |
| `R` | run the planned command in a terminal pane (plan and confirm screens) |
| `Tab` | switch between profiles and single units (Install) |
| `U` | plan an uninstall of the selected profile (Install) |
| `i` | the selected profile's documentation (Install) |
| `v` | reveal or hide station values (Station) |
| `c` | clear the selected value, where the engine can (Station) |
| `g` | where to get the selected secret (Secrets) |
| `d` | name a Doppler project and config for the selected secret (Secrets) |
| `e` | enter the selected secret for this session only, hidden (Secrets) |
| `x` | forget the session value of the selected secret (Secrets) |
| `f` | run the command the selected secret unlocks (Secrets) |
| `f` | fetch RepeaterBook by state (Repeaters) |
| `i` | import your own repeater export (Repeaters) |
| `a` | choose the active areas (Repeaters) |
| `x` | remove the selected layer (Repeaters) |
| `l` | look repeaters up near a place, by band and mode (Repeaters) |
| `u` | also ask upstream whether the catalog's pins are current (Update) |
| `A` | run the apt upgrade the report offers (Update) |
| `B` | plan the rebuilds the report offers (Update) |
| `s` | skip the selected first-run step (Home) |
| `D` | dismiss the first-run checklist (Home) |

## Screens

- **Home**: the engine's health check, whether the station is set, the last run, units behind their pin, and a first-run
  checklist (set the station, apply the hardware rules, pick a profile, install it).
- **Install**: profiles, and with `Tab` single units; the plan; the run.
- **Station**: the saved values, changed by running the engine's own `station set`.
- **Secrets**: the keys the engine can use for downloads that need one (RepeaterBook's token first), where each would come
  from (the environment, Doppler or nowhere) and never its value. `g` says where to get one, `d` names a Doppler project and
  config through `station set`, `e` keeps a value for this console session only, and `f` runs the command it unlocks.
- **Repeaters**: the repeater layers on this machine grouped by area (`maps repeaters list --json`), the areas and which are
  active (`maps areas --json`), and each source's credit exactly as the engine words it. `f` fetches RepeaterBook by state
  (and optionally one county), `i` imports your own export from a file, `a` chooses the active areas with the current set
  filled in (`all` and `none` stand alone), `x` removes the selected layer after showing the command, and `l` looks repeaters
  up by place, distance, band and mode into a table of callsign, output, offset, tone, mode, distance and bearing. `f` first
  asks the engine whether `REPEATERBOOK` can be supplied and opens **Secrets** with the reason when it cannot; when the
  `repeaterbook-client` unit is not installed it offers the install (the engine's plan, then a pane) and runs the fetch after
  it succeeds. Choosing areas deletes nothing. The station's own position is used for distances and never printed.
- **Logs**: each run the engine recorded, newest first; a run in progress is followed live.
- **Update**: installed against the catalog; `u` also asks upstream.
- **Help**: keys, what the console never does, and what each profile is for.

## Status

Built and tested; not yet run on the field laptop, the target it was built for. What has run: the test suite (unit tests against
fixtures recorded from the engine, a fake `hammunition` that asks for `yes` on a real pseudo-terminal, and the console driven
end to end in one), inside the engine's own suite, with urwid 4.x on Python 3.13. The recorded fixtures date from the console's
first release; the earlier CI matrix named urwid 2.6.10, 2.6.16 and 3.0.4 and the Debian 13 and Ubuntu 24.04 archives' own
`python3-urwid`, and those legs are not yet part of the engine's CI.

What has not been run: the bench run on the field laptop; a real `hammunition install` through the pane on a real target;
urwid's `urwid.Terminal` against a real engine install on any machine; Raspberry Pi OS, Pop!_OS and Mint, which are inferred
from their bases. A claim about hardware belongs here only after it has run there.

## Development

The package is `src/hammunition/console/` and its tests are `tests/console/`, run by the engine's own `pytest`. The fixtures
are documents the engine printed, kept in `tests/console/fixtures/`; they are recorded by
`tests/console/capture_fixtures.py`, which **refuses to run** unless the HOME the engine would see is a temporary directory
it created itself, outside every real account's home, with the owner variables removed (a capture once overwrote a real
station file through a HOME override). Run it only in a container or a throwaway VM, never on a machine whose station is set.
Review every new fixture by eye before committing: the identifier scan is a net, not a guarantee.
