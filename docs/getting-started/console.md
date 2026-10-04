# The console

`hammunition console` is a full-screen terminal program for the same commands this documentation describes. It shows what is
installed, what is wrong and what to do next, and runs the engine's own commands for you, so you can walk from a fresh install
to a working station without remembering the verbs. It is part of the engine: the same release, the same version, started
with one subcommand. (Until v0.21.0 it was a separate project, `hammunition-console`; that repository is archived and this
replaces it, see [D-059](../reference/json-interface.md)'s amendment in the decision record.)

It has no install logic and no package names of its own; it asks the engine, and everything it does is a command you could
type, which it shows you first. It is the alternative to typing them, not a replacement for the
[command reference](../reference/cli.md). Its keys and screens are in the [console reference](../console/index.md).

The console is not yet measured on hardware: it has not been run on the field laptop, and this page says so until the bench
records it. Whether it works over SSH or on a Raspberry Pi has not been measured either.

## Start it

Install the engine first ([install the engine](install.md)); then:

```sh
hammunition console
```

That is all: there is no second program to install. Its one dependency is [urwid](https://urwid.org/). On the Debian family
`sudo apt install python3-urwid` provides it; `./bootstrap.sh` installs it into the engine's virtualenv; and in any other
virtualenv `pip install 'hammunition[console]'` does. Without it, `hammunition console` prints one line naming the command to
run and exits 2, and the rest of `hammunition` never needs urwid.

It needs a terminal of at least 80x24 and refuses to start without one, with `TERM=dumb`, or as root. `hammunition console
--help` lists its keys and exit codes, and `hammunition console --version` prints the engine's version, because there is no
second one. There is a generated entry in the desktop menu too (`hammunition menus apply` writes it, running the engine by its
absolute path).

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

Nothing, beyond what the engine's own commands write when you press `R` on a plan. The one file of its own is its
configuration, `~/.config/hammunition-console/config.toml`, created when it first runs: the last screen, the colour theme and
whether you dismissed the checklist. Never a station value. A crash writes `crash.log` beside it with the exception's type and
frames, never a message. Inspect with `ls -l ~/.config/hammunition-console/`; remove with `rm -r ~/.config/hammunition-console`.

The menu entry is the one other file: `~/.local/share/applications/hammunition-engine-console.desktop`, written by
`hammunition menus apply` and rewritten by it each time; delete the file to remove it.

If you installed the standalone `hammunition-console` unit before v0.21.0, it still runs until you remove it:
`hammunition uninstall hammunition-console`. The catalog keeps the unit, retired, for exactly that.

## What it never does


It never answers a consent prompt for you and never passes the engine's assume-yes flag ([D-021](../reference/cli.md)); it
removes any scripted-consent variable you exported from the environment of everything it starts. It never fetches anything
from the network itself (the engine does, and asks upstream only when you press `u` on Update). It never runs a `doctor` fix. Every read is `hammunition <verb> --json` ([D-059](../reference/json-interface.md)).

## What was measured, and what was not

Measured: the console's test suite, which is part of the engine's own, runs against documents recorded from the engine,
against a fake engine that asks for `yes` on a real pseudo-terminal, and drives the whole program in one.

Not measured: a real install through the console's terminal pane on a real target, which is a bench item; the engine's
per-profile installed state and its update report for retired units, which the console treats as present and shows as
"unknown" when absent; Hardware and maps screens, which the console does not have yet.
