# Design: the Hammunition console

Status: draft for the maintainer, 2026-10-03. Nothing is built. This is a spec
for a new repository in the Hammunition suite, a terminal UI that installs and
manages a station. It rests on the spike
`console-spike.md` (2026-10-02, engine 0.19.0, read-only) and on
`docs/reference/json-interface.md`. Where the spike measured something this
spec says "measured". Where it did not, this spec says "unmeasured".

The working name in this document is "the console". The real name is an open
decision (see Open decisions).

## 1. Purpose and who it is for

A licensed operator with moderate Linux experience installs Hammunition and
wants to get from a fresh machine to a working station without remembering
CLI verbs. The console is one full-screen program that shows what is
installed, what is wrong, and what the next step is, and that runs the
engine's own commands for them.

The model is PiNodeXMR's setup menu: a short top level, a confirmation that
says what will happen, a way out that changes nothing. The spike measured what
that menu gets wrong, and the console fixes each point:

- It has no status line. The console puts one on every screen.
- Its state lives in 30 loose shell files. The console holds none; the
  engine's station config and logs are the state.
- It has no dry run and pipes remote scripts to bash. The console runs a plan
  first and never fetches or pipes anything.
- It navigates by recursion. The console keeps a real back stack.

Who it is for: an operator on a laptop or a Pi over SSH who would rather pick
from a list than read `docs/reference/cli.md`. It is also the "easy to walk
through" first-run path (section 6).

## 2. What it is not

- Not a second engine. It has no install logic, no package names, no catalog
  parsing, no distro detection. It asks the engine.
- Not a web UI. It is a terminal program and works over SSH.
- Not a replacement for the CLI. Every action it takes is a CLI command the
  operator could type, and the console shows that command before running it.
- Not a consent shortcut. It never answers a consent gate (D-021). The
  operator types `yes` into the real prompt.
- Not a holder of station values. The callsign and grid square live in the
  engine's station config and nowhere else.
- Not a GUI launcher. It can start a program that has its own window by running
  the engine's verb, but it embeds none.

## 3. Architecture

### 3.1 Process model

Three channels, each with one job. The console never touches the machine by
any other route.

1. **Reads.** The console runs `hammunition <verb> --json` in a worker thread
   and parses the one document on stdout (D-059). It never parses text. It
   refuses a document whose `schema` major it does not know, by name, and
   shows the document's `engine` field in the header.
2. **Writes that need a tty or a consent gate.** The console runs the real
   `hammunition` command in an embedded pty pane (`urwid.Terminal`, if urwid
   is chosen). The child owns the tty. The operator types into it. The console
   sees only the exit code and then re-reads.
3. **Switches.** Park, wake, service start and stop, time mode, radios, linger
   go through `/usr/local/libexec/hammunition-devctl`, reads directly and
   writes through `/usr/bin/pkexec`, exactly as hammunition-tray does (D-056).
   polkit supplies the consent. The console never imports the engine or the
   helper's package.

The console writes one thing itself: its own small config under
`~/.config/hammunition-console/` (the directory carries the final name). The
config holds the last screen, the colour theme, and a "walkthrough dismissed"
flag. It holds no station value.

### 3.2 Diagram

```
                +--------------------------------------------+
                |  console (python3 + urwid, no engine import) |
                |  header: engine version, target, doctor     |
                |  counts, "station: set / not set"           |
                +---+----------------+-----------------+------+
                    |                |                 |
           worker threads      pty pane (child)    switches
           (no tty needed)     (tty handed over)   (no engine)
                    |                |                 |
          hammunition <verb>   hammunition install   /usr/bin/pkexec
          --json  (stdout =    hammunition uninstall   /usr/local/libexec/
          one document)        hammunition hardware      hammunition-devctl
                    |           apply|unapply            park|wake|time mode|
                    |           hammunition station set   services|linger
                    |           hammunition maps ...          |
                    v                |                       v
              status, list, doctor,  v                  polkit action
              update, logs, plan,   sudo, consent        (one prompt)
              station show, ...     gates, typed `yes`
                    |                |                       |
                    +--------+-------+-----------------------+
                             v
                  the engine and its files (station config,
                  run logs, transaction log). The console reads
                  them only through the engine.
```

### 3.3 Rules that fall out of this

- Every command line the console runs is built from a fixed argv list. A name
  typed by the operator is one argv element, never part of a shell string.
  The console never uses `shell=True`.
- Reads are never run in the UI thread. `doctor` (measured 3.2 s) and
  `update` (measured about 1.6 s per profile) are the slow ones.
- A read that fails shows the `error` document's `message` and exit code. It is
  never retried silently.
- The console sets no scripted-consent variable and passes no `--yes` (section
  9 holds a test for both). It also removes any such variable from the
  child's environment, so one the operator exported in the parent shell does
  not reach a gate through the console.
- The status header never prints a station value. "Station: set" or "not set"
  is all it says. Screens that must show a value (Station) show it only from
  a fresh `station show --json`, hold it only in the widget, and never write
  it to the console's config or log.

## 4. Screens

Keys on every screen: digits select, `b` goes back (a real stack), `?` is
help, `q` quits, `r` refreshes. The header is one line: engine version, target
description, doctor counts, station set or not.

### 4.1 Home

- Shows: the doctor summary (fails, warns, healthy), whether the station is
  set, the most recent run and its result, and a count of units behind their
  pin. Enter on the doctor line lists the checks with their `fix` text.
- Reads: `status --json`, `doctor --json`, `station show --json` (only to learn
  whether it is set), `logs --json`, and `update --json` for installed
  profiles, lazily.
- Runs: nothing.
- Refuses: nothing. If the engine is older than the floor (section 7) it shows
  that and nothing else.
- The `fix` field is text, not an argv (measured, spike item b). The console
  shows it and never runs it.

### 4.2 Install

- Shows: the profile list with name, stage, summary, disk hint and a gate
  marker "G" where `consent_gated` is true. A second list browses single units
  by name. Enter on either opens the plan pane (section 5).
- Reads: `list --json` (profiles and packages), `show <profile> --json` for the
  profile's documentation fields, `install NAMES --dry-run --json` for the
  plan.
- Runs: `hammunition install NAMES` in the pty pane, after the plan is shown
  and the operator chooses Run. Uninstall is the same with `uninstall NAMES
  --dry-run --json` first, then `hammunition uninstall NAMES` in the pane.
- Refuses: it does not offer a profile whose plan came back `outcome:
  "refused"`; it shows the blockers and their remedies instead. A name the
  operator types is passed through and the engine decides.
- Known gap: per-profile installed state is not in `list --json` (spike item
  e, f). Until engine work E1 lands the console may derive it from `update
  <profile> --json` rows, measured at 1.6 s for 13 rows. That is a stopgap and
  is labelled as one in the code.

### 4.3 Station

- Shows: the station values, with the callsign and grid hidden until the
  operator presses a key to reveal them, plus alias, map regions count,
  freshness, books, mirror, DEM source and the rig fields. Placeholders in all
  docs and tests are N0CALL and FN31pr.
- Reads: `station show --json`, `maps regions --json` for the region picker,
  `reference books --json` for the book picker.
- Runs: the real `hammunition station set` with the flag for the field being
  changed, in the pty pane. The value goes to the engine as one argv element
  and nowhere else.
- Refuses: it keeps no copy. It does not write the value to its own config, a
  log, a crash report or the environment. It does not validate a callsign
  itself; the engine's refusal is shown verbatim.
- `station set` has no JSON form today (measured, spike item d). The console
  runs it in the pane, reads the exit code, and then reads `station show
  --json` to confirm. Engine work E3 would add an echo document.

### 4.4 Hardware

- Shows: parkable devices and their state, services and linger, GPS time
  state, radios. Offers udev and group apply and unapply.
- Reads: the helper's unprivileged verbs `state`, `services state`, `time
  state`, `radio state` (the tray polls these every 5 s; measured in the tray
  README), and `hardware state --json` from the engine for the device list.
- Runs: park, wake, forget, `services start|stop|enable|disable`, `time mode`
  and `linger` through `/usr/bin/pkexec` and the helper. `hammunition hardware
  apply` and `unapply` run in the pty pane because they ask their own typed
  confirmations (D-056).
- Refuses: if `/usr/local/libexec/hammunition-devctl` is missing or its
  `--version` is not "contract 1" the screen says so in one line naming
  `hammunition install hammunition-tray` and shows no switches. A helper
  that answers exit 2 with argparse's "invalid choice" gets the tray's own
  wording, "update hammunition-tray", not an error.
- `hardware list` and `hardware apply --dry-run` have no JSON form (measured,
  spike item o, p). The first release shows the helper's device state and runs
  apply in the pane, which prints its own plan. Whether this screen ships in
  the first release is an open decision.

### 4.5 Maps and data

- Shows: map regions chosen, data artifacts with sizes and licences, Kiwix
  books chosen and installed, the LAN mirror.
- Reads: `maps regions --json`, `artifacts --json`, `reference books --json`,
  `station show --json`.
- Runs: `maps repeaters import` and `maps infra import` (they have JSON
  results and take a path the operator types), `maps phone` (JSON), and
  `station set --mirror URL` or `--clear-mirror` in the pane. Programs that
  open a window or a server (`maps qmapshack`, `maps navit`, `maps comaps`,
  `reference serve`) run in the pane. Per the maintainer's rule they are not
  launched during development.
- Refuses: an import path is passed as one argv element; a missing file is the
  engine's refusal, shown verbatim. It never fetches a map itself.
- `maps regions` fetches an index (measured 1.5 s), so it runs on entry in a
  worker and shows a spinner.

### 4.6 Logs

- Shows: the run list newest first, with command, started, result (`ok`,
  `failed`, `refused`, `not confirmed`, `running`, `incomplete`) and exit code.
  Enter opens the log file; a `running` entry is followed live.
- Reads: `logs --json`, then the file at `RunEntry.path` read directly, since
  the path is the engine's published location (json-interface.md, `logs`).
- Runs: nothing.
- Refuses: it only opens a path that `logs --json` returned and that is inside
  the returned `directory`. It does not search or filter in the first release.
- Transaction history has no document (measured, spike item n). Engine work E6.

### 4.7 Update

- Shows: installed versus the catalog, per unit, with the lists' age as the
  engine reports it; an opt-in "ask upstream" toggle that adds `--upstream`.
- Reads: `update [NAMES] --json`.
- Runs: the engine's own upgrade or rebuild commands from the document, in the
  pane. The console shows the command first and runs the argv it was given, not
  a string it assembles.
- Refuses: with no names the engine currently refuses and exits 2 when the log
  names retired units (measured here: 9 of 195). The console shows that error
  as it is and offers per-profile updates instead. Engine work E2 removes the
  refusal and is the blocking fix.

### 4.8 Help

- Shows: offline text for each screen, the keys, and the profile documentation
  fields (`what_it_installs`, `why_together`, `deliberately_excludes`,
  `manual_configuration`, `disk_footprint_hint`) from `show <profile> --json`.
- Reads: `show --json`. The console also bundles a short help file of its own.
- Runs: nothing.
- Refuses: nothing. It does not render the engine's docs site; it points to
  the page by name.

## 5. The install flow in detail

The plan comes first, always. No path reaches the real command without it.

1. **Select.** The operator picks a profile or units. The console builds
   `["hammunition", "install", *names, "--dry-run", "--json"]`.
2. **Plan.** It runs that in a worker and parses a `plan` document. If
   `outcome` is `refused`, it shows each `BlockerLine` (subject, reason,
   remedy) and stops. The exit code is 2 in that case.
3. **Display, grouped as the plan groups it (D-016).** One section per field of
   `InstallPlanView`, hidden when empty:
   - Units, in install order, each with `method`, `state` and `requested_by`.
   - apt releases and no-recommends notes.
   - Third-party repositories (`repos`), each with its pinned key fingerprint.
   - Offline data (`data`) with `total_human`, licence and `verified_by`, and
     map regions (`maps`) with `download_total_human` and `disk_total_human`.
     These are the size and licence disclosures. They are shown before the
     operator can choose Run.
   - Group memberships, configuration files written (with the station values
     they fill by name, never the values), user services.
   - Deferrals: what will not happen and why.
   - Consent gates: each `GateLine` with its `risk_lines`. The console labels
     this section "You will be asked to type yes for each of these."
   - sudo note (`SudoLine.text`) and the step list (`StepView.display`).
4. **The `plan` document is for local programs.** It names the operator's
   account, home paths and the map regions. The console does not copy it into
   its config, its logs or a crash report.
5. **Choose.** Run, or Back. Back changes nothing and says so.
6. **Run.** The console opens the pty pane and runs the same argv without
   `--dry-run` and without `--json`. The child has a real tty, so sudo's
   password prompt, the group choice, and the typed `yes` all reach the engine
   untouched. The console does not read the pane's input for the word `yes`,
   does not echo it, and does not inject keystrokes.
7. **Progress.** The pane shows the engine's own output. In addition the
   console may tail the run's log file for a step view. Matching log lines to
   `plan.commands[i]` is inference today (measured, spike item j), so the first
   release shows no "step N of M" counter. Engine work E7 adds a stable step
   id.
8. **Result.** When the child exits, the console reads `logs --json` and shows
   the newest `install` run's `result` and `exit_code`, then re-reads
   `status --json`. The exit code table is the engine's (`docs/reference/
   cli.md`); the console reports the engine's word, not its own.
9. **Interrupt.** Ctrl-C goes to the child, as in any terminal. The console
   does not kill it. If the console itself receives SIGHUP it closes the pty,
   which is the same as the terminal closing, and the engine's run log records
   `incomplete`.

## 6. First-run walkthrough

On first start, or when Home sees something undone, the console offers a
four-step checklist. Each step is optional, resumable, and skippable. The
state is read from the engine each time, not stored, so the checklist is always
true. The only thing the console stores is "dismissed".

1. **Station set.** Done when `station show --json` reports the callsign and
   grid present. Not done: the Station screen opens and runs the real
   `hammunition station set`. The step never reveals a value on the checklist.
2. **Hardware apply.** Done when the engine's hardware state shows the udev
   rules and groups applied (an unmeasured field today; E4 would make this
   readable. Until then the step is shown as "unknown" and never as done). Runs
   `hammunition hardware apply` in the pane.
3. **Pick a profile.** Opens Install with the starter profile `station`
   highlighted and the profile's `why_together` and `manual_configuration`
   shown, so the operator knows what they still set by hand.
4. **Install.** The flow in section 5.

A step the operator skips stays on the checklist, marked skipped, and Home
keeps showing the checklist until they dismiss it. A step that fails leaves
the checklist where it was and shows the engine's reason.

## 7. Error handling

- **Engine missing.** `hammunition` not found on `PATH`: one screen naming the
  command and the engine's install page, and quit. The console never offers to
  install the engine.
- **Engine too old.** The version floor is read from the `engine` field of the
  first document, not by parsing `hammunition --version` (under `--json`,
  `--version` prints to stderr and emits no document). Below the floor: one
  screen naming both versions and the command to update, and nothing else. The
  floor is a constant in one file with a test. Its value is set when the
  engine work in section 11 ships; it is not guessed here.
- **Unknown schema major.** Refused by name, with the schema string shown.
- **Exit codes.** Read a document's own `outcome` first, then the exit code.
  Exit 2 with kind `error` shows `message`. A refused plan is a `plan`, not an
  `error`. A command with no JSON form returns an `error` document and exit 2
  and ran nothing (json-interface.md); the console treats that as a bug in its
  own screen table, not as a user error, and a test asserts no screen runs a
  non-JSON verb under `--json`.
- **Helper missing or too old.** As in 4.4.
- **No tty.** The console needs one. If stdin or stdout is not a tty it prints
  one line and exits 2 before drawing anything. It also refuses to run when
  `TERM` is `dumb`. The install path needs a real tty regardless (measured:
  the engine reads the typed gate with `input()` only when
  `sys.stdin.isatty()`, spike section 2.1).
- **A pane child that dies.** Shown with its exit code. The console does not
  retry.
- **Terminal too small.** Under 80x24 it shows a one-line request to resize.
- **Crash.** An uncaught exception restores the terminal, prints a traceback to
  the console's own log file, and exits 1. The log holds no station value and
  no `plan` content.

## 8. Packaging and install

The console follows the shape of hammunition-tray: its own repository, a tag
archive, an installer, a catalog unit in the engine that pins it.

### 8.1 Repository layout

```
<name>/
  README.md
  LICENSE                      GPL-3.0-or-later
  install.sh                   per-user or prefix install; no pip, no venv
  uninstall.sh
  bin/<name>                   a /bin/sh wrapper that execs python3 -m <package>
  src/<package>/               the console
    app.py  client.py  screens/  pane.py  helper.py  config.py
  tests/                       fixtures/ (recorded JSON), fake_hammunition/
  docs/                        contract notes: which documents are read
  man/<name>.1
  .github/workflows/ci.yml
```

### 8.2 Release and pin

- A tagged release; the engine pins the tag's source archive by sha256 (the
  D-024 reasoning, as for the tray). `method: binary` in the catalog unit, with
  `depends: [python3-urwid]` if urwid is chosen.
- No `venv`, no `pip`, no `pipx` (D-014). The interpreter is the system
  `python3`, 3.11 or later, which every target has. The console imports no
  engine code.
- The catalog unit is data only. It names the archive, the sha256, the wrapper
  path under the shared prefix and a menu entry via the engine's menu
  generator (D-050, D-054). The unit carries the documentation fields every
  manifest requires. It sits in no profile at first; the operator installs it
  by name: `hammunition install <name>`.
- The wrapper is the only file placed on `PATH`. Nothing runs as root.
- Uninstall removes the tree and the wrapper. The console's own config under
  `~/.config/hammunition-console/` is left and named in the unit's notes.

### 8.3 Dependency floor

urwid 2.6.10 on Ubuntu 24.04, 2.6.16 on Debian 13 and Parrot, 3.0.4 on Ubuntu
26.04 and Kali (measured, spike section 3). The code must run on that whole
range. API drift between 2.6 and 3.x is unmeasured. The CI matrix in section
9 tests both ends.

## 9. Testing

Tests live in the console's repository and run in its CI. Checks are in the
test suite, not in a CI-only script.

- **Unit tests with recorded fixtures.** Real documents from each `--json`
  command the console reads, recorded once from a real engine run with the
  station values replaced by N0CALL and FN31pr, and with paths and hostnames
  scrubbed. Each screen's widget builds from its fixture. A fixture with an
  unknown `schema` major must be refused. A fixture is regenerated by a script,
  and a test fails when the engine's published JSON Schema (from
  `docs/reference/json-interface.md`) and a fixture disagree.
- **A pty test against a fake `hammunition`.** A script on `PATH` named
  `hammunition` answers `--json` reads from fixtures and, for `install`
  without `--dry-run`, behaves like the real one: it calls `input()` only when
  `sys.stdin.isatty()`, prompts "Type 'yes' to continue", and exits 0 on
  `yes`, 1 otherwise. The test drives the console in a pty, types `yes` in the
  pane, and asserts the fake received it and exited 0. A second case closes
  stdin and asserts the fake refuses, so the test proves the tty is real.
- **The consent test.** A test asserts that for every code path the console
  builds an argv or environment for, the argv never contains `--yes` or `-y`,
  and the environment never contains a variable named in any fixture's
  `GateLine.env_var` or any variable ending in `_CONSENT`. A second test sets
  one such variable in the parent environment and asserts the child does not
  see it. Both tests must be falsified before they are trusted: break the code
  to pass `--yes` and confirm the test goes red with a message naming the file.
- **No station values.** A test runs every screen against a fixture whose
  callsign is a sentinel string and asserts the sentinel appears in no file the
  console wrote, no log line, and not on screen until revealed.
- **No non-JSON verbs under `--json`.** A test walks the screen table and fails
  if one lists a verb that is not in the engine's "Commands" list.
- **Helper tests.** A fake helper keyed by argv, as the tray's tests do. Any
  argv nobody faked fails the test. No test starts `pkexec`, `systemctl` or
  `nmcli`.
- **Socket and network.** Every test blocks sockets. The console fetches
  nothing.
- **Headless widget tests.** Urwid has no built-in harness comparable to
  Textual's Pilot (the spike: unmeasured how painful this is). The first
  release drives widgets directly with `urwid.raw_display` replaced by a
  screen stub, and renders each screen to a string for a golden comparison.
- **CI.** The repository's CI runs the tests on Python 3.11 and 3.13, with
  `mypy --strict`, against urwid 2.6.x and 3.x. Actions are pinned by resolved
  commit (`git ls-remote --tags`), not from memory. In the engine repository,
  the catalog unit gets the engine's usual checks, and the pin is verified per
  PR by `check_pin_reviews.py --verify-refs --only <manifest>`.
- **Measured later, not claimed now.** A real `hammunition install` through
  the pane on a real target is unmeasured. It is a bench item, recorded in the
  bench report only after it runs.

## 10. Documentation

A feature is not done until it is documented.

- **README** in the console's repository: what it is, requirements, install,
  the three channels, what it never does, the keys, and a Status section that
  says what has and has not run on real hardware.
- **A docs page in the engine's site**, `docs/getting-started/console.md`, in
  `mkdocs.yml` nav in the same commit, built `--strict`. It walks the first run
  with the four steps and says what each writes. It links to the console's
  repository.
- **The generated package reference** picks up the catalog unit's required
  documentation fields. `docs/projects.md` and `docs/credits.md` gain the entry.
- **Man-style help.** `<name> --help` prints usage, the keys and the exit
  codes; a `man/<name>.1` page ships with the archive.
- **System modifications.** The unit's page states: files placed, the wrapper
  on `PATH`, the menu entry, nothing else, how to inspect them and how to
  remove them.
- **Changelog.** The engine's PR adds a fragment under `changelog.d/`, never an
  edit to `CHANGELOG.md`. The decision, if recorded, goes in `docs/DECISIONS.md`.

## 11. Engine prerequisites

Numbers are the spike's. Hours are the spike's estimates, not measurements.
Each adds a command or a document; none is a flag the engine has today.

| id | adds | blocking for first release? |
|---|---|---|
| E1 | per-profile install state in `list --json`, or a profiles state document (installed n of m); optionally byte sizes from apt `Installed-Size` in `PackageLine` (6 to 8 h) | Yes (minimum, with E2) |
| E2 | `update --json` with no names reports retired units as rows and continues, instead of refusing with exit 2 (3 to 4 h) | Yes (minimum) |
| E3 | `station set --json`: an echo document of the saved values and per-flag refusals (3 h) | No. The console runs `station set` in the pane and re-reads `station show --json`. Wanted for the Station screen's polish |
| E4 | `hardware list --json`, and `hardware apply` and `unapply` with `--dry-run --json` in the plan's shape (6 to 8 h) | No. Needed only if the Hardware screen ships with a native plan view |
| E5 | JSON results for `time mode`, `services` verbs, `hardware park|wake` (4 to 6 h) | No. The console calls the helper as the tray does |
| E6 | a transaction history document, `transactions --json`, reading rotated JSONL in order (4 to 5 h) | No. Logs screen shows runs only |
| E7 | a stable `step` id in the run log and in `StepView`, so the console can show "N of M" without inference (4 to 6 h) | No. First release shows the engine's own output |
| E8 | `doctor` fixes as argv lists, not only prose (2 to 3 h) | No. Fix text is shown, never run |
| E9 | an apt version floor on a unit's `depends` (5 to 7 h) | No for urwid. Yes if Textual is chosen, so Ubuntu 24.04 defers it by name |
| E10 | which command prints the `unit` kind (documented at json-interface.md, "unit"; the spike did not confirm the verb) (1 to 2 h) | No. Needed to browse a single unit's detail natively |

The spike says E1 and E2 are the minimum for a useful Home and Install, and E3
for Station. This spec agrees.

Reconciliations the engine owner should confirm:

- Version floor: the spec reads the `engine` field of a document. It does not
  parse `hammunition --version`.
- E10: the spike measured `show` as taking a profile. The console's unit
  browser uses `list --json` entries and shows `show` only for profiles until
  E10 names the verb.

## 12. Open decisions

These were the maintainer's. Each had a recommendation, and the maintainer
ruled on all four on 2026-10-03:

| decision | ruling |
|---|---|
| 12.1 name | `hammunition-console` |
| 12.2 toolkit | urwid |
| 12.3 first release | Home, Install, Station, Logs, Update, Help; Hardware and Maps deferred to the tray and the CLI |
| 12.4 `hammunition console` subcommand | yes, after the first console release |

The sections below are kept as the record of what was weighed.

### 12.1 The name

Free under ChiefGyk3D, measured by the spike with `gh repo view`:
`hammunition-console`, `hammunition-cockpit`, `hammunition-helm`; also free:
`hammunition-panel`, `hammunition-menu`, `hammunition-deck`, `hammunition-tui`.
PyPI and Debian name collisions are unmeasured because the unit is not
published there.

Recommendation: `hammunition-console`. It is the maintainer's own word and
D-059's word for a front end. `hammunition-cockpit` is more evocative but says
less to a newcomer reading a menu. The suite already has the tray as the
device front end, so a name that reads as "the text front end" avoids a
second metaphor.

### 12.2 The toolkit

| | urwid | Textual |
|---|---|---|
| Versions in archives (measured) | 2.6.10 to 3.0.4 across all targets, on every one | 0.1.13 on Ubuntu 24.04, 2.1.2 on Debian 13, Parrot and Ubuntu 26.04, 8.2.3 on Kali |
| Ubuntu 24.04 (Pop!_OS, Mint noble-based, unmeasured) | Present, usable | 0.1.13 is a different, unusable generation. A bare `depends: [python3-textual]` would install it and fail at import |
| Embedded pty pane | `urwid.Terminal` exists (measured by class presence and source, not by running a real install) | None in 2.1.2. `App.suspend()` hands the whole screen to the child, which is correct for consent but is a full-screen hand-off, not a pane |
| Engine work | none | E9, an apt version floor, 5 to 7 h, so 24.04 defers by name |
| Test harness | none built in; golden-string rendering (unmeasured how painful) | Pilot, headless, cheap to make falsifiable |
| Look | plain, tables hand-built from Columns and ListBox | tables, trees, tabs, markdown view |
| Spike estimate of console hours | about 146 | about 100, plus E9 and two CI legs |
| API drift | 2.6 to 3.x to 4.x unmeasured | 2.1.2 to 8.x unmeasured |

Recommendation: urwid. It is the only rich toolkit on every target, one apt
dependency, and the pane keeps the consent gate inside the console. The cost
is about 46 more hours than Textual and no cheap headless harness. Textual's
cost is E9, a three-generation version spread, and a pane that is really a
screen hand-off. Choose Textual only if the look matters more than reach and
the maintainer accepts that Ubuntu 24.04 is deferred.

### 12.3 Hardware screen in the first release, or left to the tray

The tray already does park, wake, services, time mode and radios through the
same helper, on Plasma and in the Qt tray, and it is not on a headless box.
The console would add the same switches in a terminal, plus `hardware apply`.

Recommendation: ship the first release with Home, Install, Station, Logs,
Update and Help, and defer Hardware and Maps. Hardware needs E4 for a native
plan and its helper path has only been run against fakes (tray README).
`hardware apply` can be run from the CLI in the walkthrough meanwhile, with the
console printing the command and offering to run it in the pane. This keeps the
first release inside E1 and E2 only.

### 12.4 A `hammunition console` subcommand

Option: the engine ships `hammunition console`, which finds and execs the
installed console and otherwise says `hammunition install <name>`. This is a
convenience for discovery.

Recommendation: yes, later, and small. It is engine work (a verb, a `--json`
refusal, a cli.md entry, a test) and it must not import the console. It does
not block the first release. A catalog unit and a menu entry are enough to
start.

## 13. Out of scope for the first release

- Hardware and Maps and data screens (if 12.3 is accepted).
- A native "step N of M" progress bar (E7).
- Transaction history (E6).
- Log search and filter.
- Editing the engine's configuration files, or any file other than the
  console's own config.
- Running any `doctor` fix (E8).
- Launching GUI programs (QMapShack, Navit, CoMaps) during development.
- Installing the engine or the helper.
- A scripted or unattended mode of any kind. The consent gates forbid it and
  the CLI already serves scripts.
- Mouse-first design. Mouse support is allowed; the keyboard is the interface.
- Themes beyond one light and one dark.
- Translations.
- Anything on Raspberry Pi OS, Pop!_OS or Mint that has not been run. Their
  package versions are inferred from their bases, not probed.
