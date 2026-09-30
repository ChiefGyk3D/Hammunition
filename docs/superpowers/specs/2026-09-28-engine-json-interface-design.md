# The engine's machine-readable interface, and `hammunition` on the PATH

**Status:** approach chosen by the maintainer 2026-09-28 (option A: front ends
are separate projects driving the engine through a stable interface); this
document is piece 1 of 4, awaiting the maintainer's read.
**Decision record:** D-059, written with the implementation.
**Origin:** the maintainer, 2026-09-28: "we will need to make it easier with
like an ncurses or whatever menu … the whole point of the project is to make it
easier. And the installer should be able to track the ones already installed
when we open it again to add more", then: the first version covers everything,
"but the parts like the tray should be modularized to that project and can be
installed as part of hammunition. We want things separated out where they make
sense to be separate in case someone just wants that piece."

## 1. The four pieces

| Piece | What | Where |
|---|---|---|
| **1** | The engine's JSON interface; `hammunition` on the PATH | Hammunition (this document) |
| 2 | The console's install flow: what is installed, tick more, pick map regions, the station form, the plan, install and remove | a new project, `hammunition-console` |
| 3 | Console screens for hardware, park and wake, GPS time, `doctor`, `update` | `hammunition-console` |
| 4 | `hammunition-console` carried in the catalog, offered by `bootstrap.sh` | Hammunition |

The tray (`hammunition-tray`) is already the model: its own repository and
release, installable alone or through the catalog, and a client of the engine,
never part of it. The console follows it. The engine stays the only place that
plans, installs, and does privileged work.

## 2. `hammunition` on the PATH

Measured: `bootstrap.sh` installs the engine into the checkout's `.venv` and
only suggests `source .venv/bin/activate`. On the field laptop `hammunition`
was not on the PATH, and a short command in the docs failed with "command not
found".

- `bootstrap.sh` creates `~/.local/bin/hammunition` as a symlink to the
  checkout's `.venv/bin/hammunition`, disclosed, idempotent, refusing to
  replace a file it did not create.
- If `~/.local/bin` is not on the PATH (`doctor` already checks this), it says
  so and prints the one line to add.
- `doctor` gains a check: `hammunition` resolves on the PATH, and to this
  checkout.
- Every example in the docs is written as `hammunition …`, and the getting-
  started page says the bootstrap puts it there.

## 3. The JSON interface

A global `--json` flag. With it, a command prints one JSON document on stdout
and nothing else there; diagnostics go to stderr; the exit code is unchanged.
Every document carries:

```json
{"schema": "hammunition/1", "kind": "<kind>", "engine": "<version>", ...}
```

`schema` versions the whole interface: a field is added freely within a major
version; removing or changing a field's meaning bumps it. Front ends refuse a
major version they do not know, by name.

**Commands in piece 1**, each with its `kind`:

| Command | `kind` | Carries |
|---|---|---|
| `status --json` | `status` | target, installed units and profiles from the transaction log (name, version or pin, method, when), deferrals, what the catalog offers |
| `list --json` | `catalog` | every profile (members, stage, documentation fields) and package (summary, categories, methods, whether it resolves on this target) |
| `show NAME --json` | `unit` / `profile` | the full manifest view `show` prints today |
| `install … --dry-run --json` | `plan` | the whole plan: packages and their state, deferrals and refusals with reasons and remedies, map regions and their verification, disk estimates, commands, system modifications; exactly what the text plan prints |
| `uninstall … --dry-run --json` | `plan` | the same shape for a removal |
| `station show --json` | `station` | the values, including map regions — for a local front end; the docs say it is not for pasting |
| `hardware state --json` | `hardware` | the parkable devices (already JSON in the helper; exposed through the CLI) |
| `maps regions [FILTER] --json` | `regions` | the region list |
| `update --json` | `update` | the rows `update` prints |
| `doctor --json` | `doctor` | each check: name, status, detail, fix |

**Running an install from a front end.** A real install is never driven
through JSON. The front end suspends itself and runs the ordinary command in
the same terminal (`hammunition install … `), so sudo, consent gates (typed
fingerprints, the helper's yes), and every disclosure are exactly the CLI's;
then it resumes and re-reads `status --json`. Nothing about consent is
reimplemented or weakened by a front end (D-021).

## 4. Where it comes from

The text output and the JSON come from the same objects. Today the plan is
rendered straight to text in `src/hammunition/cli/main.py`; piece 1 introduces a plain data
model for each command's result (dataclasses) that both the text renderer and
the JSON encoder read, so the two cannot drift. A test asserts, for each
command, that every value the text shows is present in the JSON.

## 5. Tests

- A golden JSON document per command (fixture catalog, fake target), so a
  change to the interface is a deliberate diff.
- Every document validates against the published schema
  (a new generated page, `json-interface.md` under `docs/reference`, documents each `kind`, generated from
  the dataclasses, never hand-written).
- `--json` never writes anything but the one document to stdout, including on
  a refusal (exit code kept, reason in the document).
- The bootstrap symlink: created, idempotent, refuses to replace a foreign
  file; `doctor`'s PATH check.

## 6. Privacy

`station show --json` includes the operator's regions and callsign, because a
local front end needs them; `plan` carries exactly what the text plan prints
(the regions, never rendered config contents). The reference says plainly that these
documents are for local programs, not for pasting into an issue, and `doctor
--json` and `update --json` keep the count-only rule the text output follows.

## 7. Out of scope here

The console itself (pieces 2-3), its packaging (piece 4), a network API of any
kind (the interface is local stdout only), and changing any command's text
output.
