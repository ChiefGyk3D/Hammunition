<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Repeater overlays: implementation plan (D-064)

**Spec:** `docs/superpowers/specs/2026-09-29-repeaters-design.md`.
**Branch:** `repeaters`, worktree `../Hammunition-repeaters`, own `.venv`.
Every task is test first: the test is written, run and seen to fail for the
reason it names, then the code, then the test passes. Fixtures are synthetic
(`N0CALL`, `N0TST`, Springfield IL). No network: the hearham fetch is tested
against a loopback server. No GUI is launched: `execvp` is stubbed.

## Task 1 — parsers and the row (`src/hammunition/repeaters.py`)

- `Repeater` (frozen dataclass): callsign, output_hz, offset_hz, tone, mode,
  lat, lon, place, notes, use, status, updated, source, label_name.
- `read_input(path) -> ParsedInput` detecting GPX, RepeaterBook CSV, hearham
  JSON and hand CSV from the content; `RepeaterInputError` naming CHIRP CSV,
  CHIRP `.img` (suffix or magic), a RepeaterBook CSV without Lat/Long, KML/KMZ,
  a DOCTYPE/ENTITY, and anything else.
- Skipped rows counted by reason with the first line numbers.
- Tests: `tests/test_repeaters.py` — one per format, one per refusal, one per
  skip reason.

## Task 2 — dedup and the layer name

- `merge(rows) -> (kept, merged_count)` on callsign + Hz + 0.01° position;
  newer `updated` wins, else first.
- `layer_name(date)`, `hearham_layer_name(date)`, `export_date(paths, override)`.
- Tests: co-sited merge, 120 km kept, newer wins, oldest mtime chosen,
  `--exported` wins, bad date refused.

## Task 3 — writers

- `gpx_text(layer, rows, attribution)`, `navit_text(rows)`,
  `write_poi(path, layer, rows, comment, date)`.
- The float32 tile-line nudge in the POI index.
- Tests: GPX parsed back (name, desc, sym, metadata), Navit lines exact,
  every POI found by QMapShack's verbatim query in exactly one tile, a point
  on a tile line included (and shown lost without the nudge).

## Task 4 — Navit's mapset (`navit_config.add_maps`)

- Insert `<map type="textfile" enabled="yes" data=.../>` before the enabled
  mapset's `</mapset>`; idempotent; refuses when not exactly one enabled
  mapset.
- Tests in `tests/test_navit_config.py`.

## Task 5 — the store and registration

- `overlay_dir()`, `write_layer(...)` (atomic, 0600 files, 0700 directory),
  `remove_layer()`, root refused.
- QMapShack `poiPaths` added and removed through `ensure_paths`; `maps
  qmapshack` keeps it in step with the `.poi`'s presence.
- Per-user Navit config written from the generated one.

## Task 6 — documents and the CLI

- `src/hammunition/interface/repeaters.py`: `RepeatersDocument` (`repeaters`)
  and `RepeatersRemovedDocument` (`repeaters-removed`).
- `cmd_maps_repeaters_import`, `cmd_maps_repeaters_remove` (JSON capable),
  `cmd_maps_repeaters_fetch_hearham`, `cmd_maps_navit`; `command_name`
  reads a third level so an error document names `maps repeaters import`.
- Tests: through `cli.main`, text and `--json`, schema-validated, text values
  in the document, no callsign or coordinate in either; refusals end in one
  error document.

## Task 7 — hearham fetch

- `fetch_hearham(url, timeout, limit) -> (bytes, sha256, fetched_at)`,
  HTTPS-only redirects, size bound; disclosure printed first.
- Tests against `http.server` on 127.0.0.1 in a thread; an oversize body
  refused; a non-JSON body refused.

## Task 8 — the Navit launcher

- `catalog/packages/navit.yaml`: `exec: hammunition maps navit`; the
  package reference regenerated.
- Tests: `maps navit` with and without a layer, under root, with the
  generated config absent; `execvp` stubbed.

## Task 9 — documentation

- `## D-064` appended at the end of `docs/DECISIONS.md`; CLAUDE.md table row;
  CHANGELOG under Unreleased; `docs/reference/cli.md` sections;
  `docs/guides/offline-navigation.md` "Repeaters on the map";
  `scripts/gen_json_reference.py` rerun; generated package docs rerun.

## Task 10 — verification and review

- `make check` to a log, exit status tested.
- One whole-branch review (opus); findings ruled on and fixed.
