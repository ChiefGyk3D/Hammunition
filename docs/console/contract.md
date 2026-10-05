<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# What the console reads, and how each screen degrades

The console reads only `hammunition <verb> --json` ([the JSON interface](../reference/json-interface.md)). Every read runs in
a worker thread. A document whose `schema` is not `hammunition/1` is refused by name. There is no version floor: the console is part of the engine, so
the `engine` field is shown and never compared. A read that fails shows the
engine's own message and is never retried silently.

Engine prerequisites: **E1** is per-profile `members`, `installed` and `installed_size_bytes` on each profile of
`hammunition list`; **E2** is `hammunition update` reporting retired units as rows with exit 0 (engine issue 239). Both are
treated as present; each screen that reads them shows "unknown" when they are not.

| Screen | Reads | Fields used | When a field or document is missing |
|---|---|---|---|
| Home | `hammunition status` | `target`, `engine` | the header says `?` |
| Home | `hammunition doctor` | `fails`, `warns`, `healthy`, `checks[].name/status/detail/fix` | the counts say `?`; `fix` is shown, never run |
| Home | `hammunition station show` | `callsign`, `grid_square` (only whether each is set) | "Station: unknown - (the engine's words)" on the screen; the header says `station ?` |
| Home | `hammunition logs` | `runs[0]` | "Last run: no runs yet" for an empty list, "Last run: unknown" when `runs` is not a list |
| Home | `hammunition update` | `counts.behind_pin`, rows in state `retired` | without E2 the engine refuses with exit 2: "unknown (the engine's words)" |
| Home | `hammunition list` | the starter profile's `members`, `installed` (E1) | the checklist's install steps show `[?]` |
| Install | `hammunition list` | profiles: `name`, `stage`, `summary`, `consent_gated`, `packages`, `documentation`, E1 fields; units: `name`, `status`, `summary`, `resolves_here` | without E1: "N units, state unknown" |
| Install | `hammunition install NAMES --dry-run`, `hammunition uninstall NAMES --dry-run` | the whole plan: every section of `InstallPlanView` and `RemovalPlanView`, `blockers` | a refused plan shows its blockers and offers no run |
| Station | `hammunition station show` | every station field | an unset field says "not set" |
| Station | `hammunition maps regions FILTER`, `hammunition reference books` | `regions`; `books[].id/title/licence` | the chooser shows the engine's error |
| Secrets | `hammunition secrets status` | `doppler.*`, `secrets[].name/purpose/available/source/detail/unit/command/get_url/get_how` (never a value: the engine has none to give) | the screen shows the engine's error |
| Logs | `hammunition logs` | `directory`, `runs[].path/started/command/result/exit_code/size` | "No runs yet." A path outside `directory` is never opened |
| Update | `hammunition update [NAMES] [--upstream]` | `counts`, `rows`, `lists_note`, `upgrade_command`, `rebuild_command`, `upstream` | without E2: the refusal is shown and a per-profile list is offered |
| Help | `hammunition list`, `hammunition show PROFILE` | `documentation.*`, `consent.disclosure`, `suggests_one_of` | the engine's error is shown |

Writes (never read as JSON): `hammunition install|uninstall NAMES`, `hammunition station set --FLAG=VALUE`, `hammunition maps repeaters fetch-repeaterbook --state STATE` (with a session secret in its environment, never its argv),
`hammunition hardware apply`, and the apt upgrade command the `update` report prints (run without apt's assume-yes, so apt
asks). All of them run in a terminal pane.

`hammunition services`, `hammunition artifacts`, `hammunition maps phone` and the other documents the engine publishes are not
read in this release.
