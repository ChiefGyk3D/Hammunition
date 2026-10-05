<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# User services generalised; the GPS tether as an installed user service (D-073 amended)

**Design:** work package 4 of the device-and-service-control design (2026-10-02).
**Branch:** `tether-service`, worktree `../Hammunition-tether-svc`, own `.venv`.
Every task is test first. No service is started or enabled on the development
machine; nothing is run as root; `nice -n 19` throughout.

## Task 1 - `plan_user_services` without rig assumptions

- `UserService` gains `restart` (`on-failure`, `always`, `no`; default
  `on-failure`) and `restart_sec` (default 5): a rig unit renders byte for
  byte as before.
- A service with no `when_station`, no `unless_station`, no `{station.*}` and
  no `binds_to_device` is **plain**: it needs neither the station nor the
  hardware catalog, is always planned, and never defers. A manifest may mix
  plain and rig entries; each group is decided on its own.
- The unit file's header names the catalog unit that wrote it
  (`# Written by Hammunition (catalog unit `gps-tether`, D-073).`). Removal
  recognises any such header; the rig's is unchanged.
- Several units per plan; the plan view names each service's own unit and
  says only what is true of it (the "can key the transmitter" warning stays
  the rig's), and a service with no device says it starts at next login.
- Tests: `tests/test_user_services_plan.py`, `_schema.py`, `_execute.py`,
  `test_json_plan.py` (the JSON fixtures stay unchanged).

## Task 2 - the `gps-tether` catalog unit

- `catalog/packages/gps-tether.yaml`, profile `navigation`: a `git` build at
  the tag of `Renegade-Penguin/hammunition-gps-tether`, a `user_services` block for
  `hammunition-gps-tether.service` listening on 127.0.0.1:10110 and :10111.
- Until the tag exists the unit carries an explicit unpinned marker that a
  test recognises as "not installable".

## Task 3 - the call-through, the launcher, the docs

- `hammunition maps gps-tether` runs the installed program when it is present
  and says where from; otherwise the engine's own module, with a deprecation
  note. The `qmapshack` launcher calls the installed program.
- Guide, CLI reference, CHANGELOG, D-073 amendment, D-071 note, regenerated
  pages and counts.

## Ledger

| Task | Tests written | Seen failing | Code | Green |
|---|---|---|---|---|
| 1 schema fields | | | | |
| 1 plain services | | | | |
| 1 header and removal | | | | |
| 1 plan view | | | | |
| 2 catalog unit | | | | |
| 3 call-through | | | | |
| 3 launcher | | | | |
| 3 docs and counts | | | | |
