# The console

`hammunition-console` is a full-screen terminal program for the same commands this documentation describes. It shows what is
installed, what is wrong and what to do next, and runs the engine's own commands for you, so you can walk from a fresh install
to a working station without remembering the verbs. It works over SSH and on a Pi. It is its own project, with its own
releases, at <https://github.com/ChiefGyk3D/hammunition-console>.

It is a client of the engine. It has no install logic and no package names of its own; it asks the engine, and everything it
does is a command you could type, which it shows you first. It is the alternative to typing them, not a replacement for the
[command reference](../reference/cli.md).

The console is not yet measured on hardware: it has not been run on the field laptop, and this page says so until the bench records it.

## Install it

Install the engine first ([install the engine](install.md)); the console never does that. Then:

```sh
hammunition install hammunition-console
```

That is by name: it is in no profile. The plan lists exactly what is placed (below). Then run `hammunition-console` from a
terminal, or pick it from the desktop menu.

It needs a terminal of at least 80x24 and refuses to start without one, with `TERM=dumb`, or as root.

## Your first run: four steps

Home shows a checklist the first time. Each step is optional, skippable (`s`) and resumable, and the state is read from the
engine each time, so the list is always true. `D` dismisses it for good.

1. **Set your station.** Opens Station and runs the engine's own `hammunition station set`. The console never holds the
   value: the engine's station file does, and the Station screen hides it until you press `v`. Nothing is invented; a missing
   value only defers the one file that needed it ([D-035](../reference/cli.md)).
2. **Apply the hardware rules.** Shows the command, `hammunition hardware apply`, and runs it in a terminal pane. That command
   prints its own plan and asks for its own typed confirmation and your sudo password; the console cannot show the plan first
   because the engine has no JSON form of it yet, and says so. The checklist shows this step as unknown, never done, because
   no engine document reports whether the rules are applied.
3. **Pick a profile.** Opens Install with `station`, the floor everything stands on, selected, and shows why its units belong
   together and what you still set up by hand.
4. **Install.** The engine's plan comes first, grouped as the engine groups it: units in order, third-party repositories with
   their pinned key fingerprints, offline data with size and licence, group memberships, files written, what will not
   happen, and every consent gate. Nothing has changed while you read it. Press `R` and the real command runs in a terminal
   pane; you type any `yes` yourself.

## What it writes on your machine

- The program's tree under `/usr/local/share/hammunition/hammunition-console`, handed to your account by the engine's
  `chown` step, with a launcher in `~/.local/bin/hammunition-console` and a terminal menu entry. Nothing runs as root but
  the copy.
- Its own configuration, `~/.config/hammunition-console/config.toml`, created when it first runs: the last screen, the
  colour theme and whether you dismissed the checklist. Nothing else, and never a station value. A crash writes `crash.log`
  beside it with the exception's type and frames, never a message.

Inspect with `ls -l ~/.local/bin/hammunition-console /usr/local/share/hammunition/hammunition-console`. Remove with
`hammunition uninstall hammunition-console`; the configuration directory is left, and `rm -r
~/.config/hammunition-console` removes it.

## What it never does

It never answers a consent prompt for you and never passes the engine's assume-yes flag ([D-021](../reference/cli.md)); it
removes any scripted-consent variable you exported from the environment of everything it starts. It never fetches anything
from the network. It never runs a `doctor` fix. Every read is `hammunition <verb> --json` ([D-059](../reference/json-interface.md)).

## What was measured, and what was not

Measured: the console's test suite runs against documents recorded from the engine, against a fake engine that asks for `yes`
on a real pseudo-terminal, and drives the whole program in one, on Python 3.11 and 3.13 with urwid 2.6.10, 2.6.16 and 3.0.4
and the Debian 13 and Ubuntu 24.04 archives' own `python3-urwid`.

Not measured: a real install through the console's terminal pane on a real target, which is a bench item; the engine's
per-profile installed state and its update report for retired units, which the console treats as present and shows as
"unknown" when absent; Hardware and maps screens, which are not in the first release.
