<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Repeater data sources beyond RepeaterBook: implementation plan (D-074)

**Spec:** `docs/superpowers/specs/2026-10-01-repeater-sources-design.md`.
**Branch:** `repeater-sources`, worktree `../Hammunition-repsrc`, own `.venv`.
Every task is test first: the test is written, run and seen to fail for the
reason it names, then the code, then the test passes. Fixtures are synthetic
(`N0CALL`, `N0TST`, Springfield IL). The network is used once to pin Open
Repeater (and twice to verify the pin) and once to HEAD the ETCC and
Brandmeister URLs for the docs; never in a test. No GUI is started. Every
command runs under `nice -n 19 ionice -c 3`.

## Task 1 — the new parsers (`src/hammunition/repeater_sources.py`)

- Source constants beside D-064's in `repeaters.py` (`SOURCE_NAMES`), and a
  `Repeater.also` field naming other sources that listed the same machine.
- `parse_open_repeater(raw, path, mtime) -> ParsedInput`; offset units;
  `open_repeater_date`.
- `parse_etcc(raw, url)`, `parse_brandmeister(raw, url)` with the hotspot
  filter, both from bytes in memory.
- `parse_direwolf_log(paths)`: `dti` `;`, band check, newest hearing wins.
- D-064's `read_input` refuses the three new file shapes, naming the flag.
- Tests: `tests/test_repeater_sources.py`, one per field rule and skip; the
  Direwolf fixture is Direwolf's own output on synthetic packets.

## Task 2 — OpenStreetMap

- `osm_frequency(text)`, `osm_offset(shift, out_hz, freq_in)`,
  `read_osm_xml(text)` (nodes, ways at the mean of their nodes, relations
  counted), `filter_extract(pbf, scratch, run)` running osmium as given.
- `installed_extracts(prefix)` and the oldest snapshot as the date.
- Tests: the four measured spellings, units given, unsigned shift, each
  "not a repeater" reason, a way's centre; a real `osmium cat` + `tags-filter`
  run over a synthetic extract, skipped without osmium.

## Task 3 — layers, sidecars and the merged file (`repeaters.py`)

- `LAYERS` (id → stem), `layer_files(id)`, `write_layer(where, layer, id)`
  writing the `.rows.json` beside the three files; `remove_layer(where,
  id=None)`; `present_layers(where)`.
- `cross_merge(rows_by_layer) -> (rows, merges)` with the precedence order;
  `rebuild_all(where) -> AllSources | None`.
- Tests: two layers coexist, one removed leaves the other, call match,
  distance match, 0.03° apart kept, field fill, `also`, APRS excluded, a
  layer with no sidecar named.

## Task 4 — the CLI and documents

- `import` flags, exclusivity, `--exported` only with files; `fetch-etcc`,
  `fetch-brandmeister` on D-064's fetch path; `remove --layer`.
- Registrations: QMapShack while any `.poi`; Navit with every layer's
  textfile; `maps navit` and `maps qmapshack` follow.
- `RepeatersDocument.layer_id`, `.all_sources`; `RepeatersRemovedDocument.layers`.
- Tests in `tests/test_repeater_sources_cli.py`: each route end to end,
  loopback fetches, documents validated, no private value in any output.

## Task 5 — the data unit and its pin

- `catalog/packages/open-repeater.yaml`; `scripts/gen_open-repeater-pin.py`
  (regenerate, `--check`, `--check --offline`), the weekly CI step, the
  generated-docs test; `artifacts` lists it.
- Tests: `tests/test_gen_open_repeater_pin.py` against a faked fetch, the
  offline check falsified by a broken manifest, nothing written by a check.
- Run the generator once for real, `--check` twice.

## Task 6 — documentation

D-074 in `docs/DECISIONS.md`; CLAUDE.md's row and counts; README count;
CHANGELOG under Unreleased; `docs/reference/cli.md`; the offline-navigation
guide's "Repeaters on the map" section; `docs/guides/lan-mirror.md`'s note
that the Open Repeater artifact is mirrorable; regenerate
`json-interface.md`, the package pages and every catalog-derived page.

## Task 7 — verification and review

`make check` to a log with `$?` tested; the unshared pytest run; one final
whole-branch review on opus; fixes; the report.
