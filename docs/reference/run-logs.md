# Run logs

Every run that changes something, or runs long, leaves one plain-text file
behind (**D-077**). It exists for the case a terminal cannot cover: an install
that ran for hours and closed its window, a dry run that sat silent while it
asked a publisher a thousand questions, an issue that needs "what did it
actually do". Read it with `hammunition logs`; it is not the record
`hammunition uninstall` stands on, which is the
[transaction log](transaction-log.md).

## Which commands

Logged: `install`, `uninstall`, `update`, `menus apply`, `hardware apply`,
`hardware unapply`, `hardware park`, `hardware wake`, every `maps ...`,
`reference serve`, `services ...` and `time mode`, with or without `--dry-run`.

Not logged: the readouts (`status`, `list`, `show`, `doctor`, `hardware list`,
`hardware state`, `artifacts`, `logs`, `station show`, `reference books`,
`time`) and `station set`, whose argv *is* the station values.

## Where, and who can read it

`$XDG_STATE_HOME/hammunition/logs/`, `~/.local/state/hammunition/logs/` by
default: the same state directory as the transaction log, and resolved the same
way. A run under `sudo` logs under the **invoking operator's** state directory,
never root's, and hands the directory and the file to them. The directory is
mode 0700 and each file 0600: a log can hold command output and paths.

The file is named `<UTC timestamp>-<command>-<pid>.log`, for example
`20261002T181500Z-install-12345.log`.

## Format

One event per line: `<UTC timestamp, milliseconds> <tag> <text>`. Written and
flushed a line at a time, so a run that was killed leaves a log you can read up
to the moment it died.

| Tag | What it is |
|---|---|
| `meta` | The run's own facts: engine version, command, argv, pid and euid. The value of `--callsign`, `--grid-square`, `--node-alias`, `--map-regions`, `--rig-device`, `--rig-owner` and `--mirror` is replaced by `<redacted>`. A crash adds `crashed:` and the traceback. |
| `out`, `err` | Everything the engine printed on stdout and stderr, the plan included. The terminal still sees exactly the same bytes. A progress counter redrawn in place leaves its first and last lines, not a line per redraw. |
| `cmd` | A command the engine started, as run. |
| `cmd-out`, `cmd-err` | That command's stdout and stderr, line by line as they arrive, so `tail -f` follows an hour-long build. |
| `cmd-end` | `exit=<code> elapsed=<seconds>` for that command. |
| `result` | The last line: `exit=<code> <ok\|failed\|refused\|not confirmed> elapsed=<seconds>`, the same codes as [the CLI](cli.md#exit-codes). |

A real run, from a fixture (a failing command, a station flag in argv; the interpreter path in the `cmd` line shortened):

```
2026-10-02T18:48:05.836Z meta    hammunition 0.19.0
2026-10-02T18:48:05.836Z meta    command: install
2026-10-02T18:48:05.836Z meta    argv: hammunition install fixture-apt --callsign <redacted>
2026-10-02T18:48:05.836Z meta    pid=974784 euid=1000
2026-10-02T18:48:05.836Z out       $ apt-get install --yes -- fixture-apt
2026-10-02T18:48:05.836Z cmd     $ apt-get install --yes -- fixture-apt
2026-10-02T18:48:05.851Z cmd-err E: Unable to locate package fixture-apt
2026-10-02T18:48:05.851Z cmd-out Reading package lists...
2026-10-02T18:48:05.854Z cmd-end exit=100 elapsed=0.0s  apt-get
2026-10-02T18:48:05.854Z err     error: apt-get install failed (exit 100)
2026-10-02T18:48:05.854Z result  exit=1 failed elapsed=0.0s
```

Only the commands the engine runs through its command runner are streamed as
`cmd-out`; steps the engine performs itself (a download, an unpack) appear as
the `out` lines it prints for them.

## Rotation

At the start of each logged run the oldest logs are removed until the new one
fits under **30 files** and **200 MB** in total. A run in progress is never
removed: each run holds a lock on its own file for as long as it lives, which
the kernel releases however the process ends, so a killed run is not mistaken
for a live one and a live one is not deleted. Files in the directory whose
names are not run logs are not counted and not touched.

Both limits are constants (`MAX_FILES`, `MAX_BYTES` in
`src/hammunition/runlog.py`), not station settings: station values are what
only the operator can supply, and a retention policy is not one.

## Reading them

```
hammunition logs            # when, which command, size, how it ended
hammunition logs --last     # the newest, in full
tail -f "$(hammunition logs --path)"
hammunition logs --json     # for a front end; see json-interface.md
```

How a run ended: `ok`, `failed`, `refused`, `not confirmed` (the exit code's
words); `running` while a live process holds the file; `incomplete` when there
is no `result` line and nothing holds the file, which is a run that was killed.
`hammunition doctor` reports how many logs there are, their size, and how the
newest ended. A run that ends on a terminal prints `Log: <path>` as its last
line, on stderr; under `--json` it does not (the document is unchanged, and
stderr is diagnostics for it), and the run is still logged.

## If the log cannot be written

The run says so once on stderr (`note: no run log for this command ...`) and
carries on unlogged. A log must not fail the run it describes.

## What was not measured

A run under real `sudo` handing the directory and file to the operator uses the
same helpers as the transaction log and is tested with an injected `euid`, not
on a machine.

To undo all of it, delete the directory: nothing reads the logs back but
`hammunition logs` and `doctor`.
