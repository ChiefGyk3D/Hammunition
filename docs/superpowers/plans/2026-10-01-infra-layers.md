<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Infrastructure and EMCOMM layers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** D-075: one map layer per infrastructure source (eight OSM layers, FAA NASR, EIA-860M, WRI, FCC ASR, NOAA Weather Radio) for QMapShack, Navit and the browser map, with three generated pins and an `infra` tile layer.

**Architecture:** A pure layer module (`infra.py`: layer table, points, writers, store) beside the repeater layers, a parser module for the federal and worldwide files (`infra_sources.py`), documents in `interface/infra.py`, CLI verbs under `maps infra`, three data-unit manifests with generators sharing `scripts/data_pin.py`, and the converter and map page extended.

**Tech Stack:** Python 3.11 stdlib (zipfile, csv, xml.etree iterparse, sqlite3), osmium-tool, tilemaker 3.0 Lua, MapLibre GL JS.

**Spec:** `docs/superpowers/specs/2026-10-01-infra-layers-design.md`

## Global Constraints

- Licence lines verbatim: `© OpenStreetMap contributors, ODbL 1.0`; `FAA NASR <cycle>, public domain`; `Source: U.S. Energy Information Administration (<Mon YYYY>), public domain`; `WRI Global Power Plant Database v1.3.0 (2021), CC BY 4.0`; `FCC Antenna Structure Registration, US Government work, public domain`; `NOAA/NWS, public domain, not an official NWS product`.
- Shelter candidates: "candidate, not a designated shelter" in the layer name and every description.
- FCC: only `RA.dat` and `CO.dat` read; `EN.dat` never opened; RA's signature fields never kept.
- NWR: `status` dropped before anything is written.
- Files under `$XDG_DATA_HOME/hammunition/overlays/infra/`, directory 0700, files 0600, refused as root.
- Documents carry no name, position, region, box or extract digest.
- Tests: synthetic fixtures only, no network, no GUI; osmium-dependent tests skip when osmium is absent.
- Machine: `nice -n 19 ionice -c 3`; network only for the three pins and the two HEADs.

## Review Focus

- An extract with no header box among several: named by number, left out, the rest filtered (Task 3 test).
- A layer that empties on re-import: its old files removed and reported, not left stale (Task 4 test).
- An `r_tower.zip` whose `EN.dat` carries a canary: the canary appears in no file and no output (Task 6 test).
- A workbook whose `Operating` sheet has a preamble and a blank coordinate: the header found by its column names, the row skipped and counted (Task 5 test).
- QMapShack/Navit registration with both repeater and infra layers present, and one kind removed: the other kind stays registered (Task 8 test).

---

### Task 1: Generalise the POI writer

**Files:** Modify `src/hammunition/repeaters.py` (`write_poi`); Test `tests/test_repeaters.py`.

**Interfaces:** Produces `write_poi_points(path: Path, layer: str, comment: str, day: date, points: Sequence[PoiPoint], *, category: str, nudge: bool = True) -> None` and `PoiPoint(lat: float, lon: float, name: str, description: str, tag: str)`; `write_poi` keeps its signature and bytes.

- [ ] Step 1: test that `write_poi` output for the fixture rows is byte-identical to `write_poi_points` given the equivalent points and `POI_CATEGORY`, and that a custom category lands in `poi_categories`.
- [ ] Step 2: run, expect ImportError.
- [ ] Step 3: move the body into `write_poi_points`; `write_poi` builds `PoiPoint(r.lat, r.lon, r.label_text(), r.description(), "communication:amateur_radio:repeater=yes")`.
- [ ] Step 4: run `tests/test_repeaters.py tests/test_repeater_layers.py`, expect pass. Commit.

### Task 2: The layer module

**Files:** Create `src/hammunition/infra.py`; Test `tests/test_infra.py`.

**Interfaces:** Produces
- `OSM_LAYERS: dict[str, OsmLayer]` keyed `medical, responders, supply, shelter-candidates, transport, power, telecom, water`; `OsmLayer(title, kinds: tuple[Kind, ...], symbol, navit_icon)`; `Kind(label, match: Callable[[dict[str,str]], bool], keys: tuple[str, ...])` where `keys` are osmium tags-filter expressions.
- `LAYERS: dict[str, LayerSpec]` for every layer id (`osm-<key>`, `faa-airports`, `eia-plants`, `wri-plants`, `fcc-towers`, `nwr`) with `stem`, `symbol`, `navit_type`, `navit_icon`.
- `Point(name: str, kind: str, lat: float, lon: float, details: tuple[str, ...] = ())` with `description(source: str) -> str`.
- `InfraLayer(layer_id, name, licence, day, points)`.
- `gpx_text(layer: InfraLayer) -> str`, `navit_text(layer) -> str`, `geojson_text(layer) -> str`.
- `overlay_dir() -> Path`, `layer_files(layer_id) -> tuple[str, str, str, str]` (`.gpx, .poi, .navit.txt, .geojson`), `write_layer(where, layer) -> tuple[Path, ...]`, `remove_layer(where, layer_id | None) -> tuple[Path, ...]`, `present_layers(where) -> tuple[str, ...]`.
- `read_osm_xml(text, *, wanted: Sequence[str]) -> OsmRead` (points per OSM layer key, read count, skips), `osmium_argv(pbf, out, wanted) -> list[str]`.
- `shelter` text: `SHELTER_NOTE = "candidate, not a designated shelter"`.

- [ ] Step 1: tests: each kind's tag set classifies the fixture OSM objects (a hospital node, a clinic way, a fire station relation, an `amenity=shelter` that lands nowhere, a mast with `tower:type=communication` and one without, a water tower, an aerodrome way, a substation); a way placed at its nodes' mean, a relation at its member ways' nodes; skips numbered in reading order; every shelter description and the layer name carry `SHELTER_NOTE`; GPX `<sym>` per layer; Navit lines carry the layer's `poi_custom` type and icon; GeoJSON validates as a FeatureCollection; `write_layer` modes 0600/0700 and root refusal mirrors repeaters; every symbol is in the 132-name list carried in the test from `CWptIconManager.cpp`.
- [ ] Step 2: run, expect ImportError.
- [ ] Step 3: implement, reusing `repeaters._position`, `_own_dir`, `_write_staged`-shaped staging and `write_poi_points`.
- [ ] Step 4: run, expect pass. Commit.

### Task 3: Region boxes and the OSM import

**Files:** Modify `src/hammunition/infra.py` (`region_boxes`, `in_boxes`, `filter_extract`); Test `tests/test_infra.py`.

**Interfaces:** `region_boxes(prefix: Path) -> tuple[list[Box], list[str]]` (boxes as `(west, south, east, north)`, notes naming skipped extracts by number); `in_boxes(lat, lon, boxes, pad=0.0) -> bool`; `filter_extract(pbf, scratch, wanted, *, run=None, label) -> OsmRead`.

- [ ] Step 1: tests: a synthetic pbf header (`test_osm_pbf.pbf`) gives its box; an extract with no box is noted as `region extract 2 of 2 has no bounding box` and skipped; none installed → empty list; `filter_extract` with a stubbed runner reads the fixture; osmium's stderr has the extract's name replaced by the label; a real-osmium test over `osmium cat` of the fixture (skipped without osmium).
- [ ] Step 2-4: fail, implement, pass. Commit.

### Task 4: The documents and `maps infra import --from-osm` / `remove`

**Files:** Create `src/hammunition/interface/infra.py`; Modify `src/hammunition/cli/main.py`; Test `tests/test_infra_cli.py`.

**Interfaces:** `InfraLayerView(layer_id, name, licence, read, written, skipped: tuple[SkipView,...], files: tuple[str,...], removed: tuple[str,...])`, `InfraDocument(KIND="infra"; route, inputs: tuple[InputView,...], layers, directory, registered: tuple[RegistrationView,...], notes: tuple[str,...])`, `InfraRemovedDocument(KIND="infra-removed"; directory, layers, removed, unregistered)`, `render_infra`, `render_infra_removed`. CLI: `cmd_maps_infra_import`, `cmd_maps_infra_remove`; parser `maps infra import (--from-osm [--layers L,...] | --from-nasr | --from-eia | --from-wri)`, `maps infra remove [--layer ID]`.

- [ ] Step 1: tests: `--from-osm` writes eight layers from stubbed osmium; `--layers medical,water` writes two and leaves others; an unknown layer name refused by name; an emptied layer's old files removed and listed; JSON validates and carries no fixture name, coordinate or region slug; root refused; `remove --layer osm-medical` and `remove` idempotent.
- [ ] Step 2-4: fail, implement, pass. Commit.

### Task 5: Federal parsers and the three data imports

**Files:** Create `src/hammunition/infra_sources.py`; Modify CLI; Test `tests/test_infra_sources.py`, fixtures built in-test.

**Interfaces:** `read_nasr(path, boxes) -> SourceRead`, `read_eia(path, boxes) -> SourceRead`, `read_wri(path, boxes) -> SourceRead`, `parse_fcc_asr(raw: bytes, url, boxes) -> SourceRead`, `parse_nwr(raw: bytes, url, boxes) -> SourceRead`; `SourceRead(points, read, skipped, day: date, licence: str, name: str)`; constants `NASR_FILE, EIA_FILE, WRI_FILE` (paths under the data root), `FCC_ASR_URL`, `NWR_URL`.

- [ ] Step 1: tests per parser: NASR cycle from `EFF_DATE`, licence line exact, box filter; EIA header found under a preamble, plants grouped by plant id with summed MW, month from the title row, licence exact, a blank latitude skipped; WRI `USA` rows dropped with the EIA note, licence exact; a zip member over the cap refused.
- [ ] Step 2-4: fail, implement, pass; the CLI routes `--from-nasr/--from-eia/--from-wri` refuse a missing installed file naming the install command. Commit.

### Task 6: The two fetches

**Files:** Modify `infra_sources.py`, CLI; Test `tests/test_infra_sources.py`, `tests/test_infra_cli.py`.

- [ ] Step 1: tests: FCC zip with an `EN.dat` canary and RA signature names: neither appears anywhere written or printed; status filter (C/G, no dismantle date, T coordinates); date from `counts`; NWR `status` value appears nowhere, SAME codes kept, pad 1.0°; both against a loopback server; disclosure printed before the request; no `--json`.
- [ ] Step 2-4: fail, implement via `repeaters.fetch_list`, pass. Commit.

### Task 7: Data units and generators

**Files:** Create `catalog/packages/{faa-nasr-airports,eia-860m,wri-power-plants}.yaml`, `scripts/data_pin.py`, `scripts/gen_nasr_pin.py`, `scripts/gen_eia860m_pin.py`, `scripts/gen_wri_pin.py`; Modify `.github/workflows/ci.yml`; Test `tests/test_gen_infra_pins.py`, `tests/test_artifacts.py`.

- [ ] Step 1: tests: AIRAC cycle arithmetic (2026-10-01 current on 2026-10-01, 2026-09-03 on 2026-09-30); regenerate writes url/sha256/size/version/licence lines once each; `--check --offline` well-formed, falsified three ways; EIA move to `archive/` rewrites the URL and keeps the pin; WRI MD5 mismatch refuses; `artifacts` lists the three units.
- [ ] Step 2-4: fail, implement, pass; generate the three pins from the network once, check each twice. Commit.

### Task 8: Registration shared with repeaters

**Files:** Modify `src/hammunition/cli/main.py` (`_navit_overlay_maps`, `cmd_maps_navit`, `cmd_maps_qmapshack`); Test `tests/test_infra_cli.py`.

- [ ] Step 1: tests: with repeater and infra layers both present, the user navit.xml lists both kinds' textfiles; removing all infra layers keeps the repeater maps and poiPaths entry; `maps qmapshack --configure-only` adds both directories.
- [ ] Step 2-4. Commit.

### Task 9: The tile layer

**Files:** Modify `src/hammunition/backends/pmtiles.py`; Create `src/hammunition/map_style/__init__.py` (Lua and config generation, style layers, ramp), `src/hammunition/map_style/LICENSE.openinframap`; Modify `pyproject.toml` package-data; Test `tests/test_pmtiles.py`, `tests/test_map_style.py`.

- [ ] Step 1: tests: argv names `config-infra.json` and `process-infra.lua` in the work directory; both written as the operator before tilemaker; the config is the kit's plus `infra`; a kit config that is not JSON fails the region by name; `CONVERTER == "tilemaker-pmtiles 2"`; the Lua `dofile`s the kit's process file by absolute path; the ramp equals OIM's `voltage_scale`; the notice file carries OIM's copyright line.
- [ ] Step 2-4; run the real tilemaker from the spike's extracted package on Delaware once (nice, ionice, `--threads 2`) and record size and layer list. Commit.

### Task 10: The browser map overlays

**Files:** Modify `src/hammunition/map_page.py`, `src/hammunition/reference.py`, CLI `cmd_reference_serve`; Test `tests/test_map_overlays.py` (new), `tests/test_map_render.py`.

- [ ] Step 1: tests: `find_overlays(dir)` serves each `infra-*.geojson` by exact name at `/map/overlays/<file>`, lists them at `/map/overlays.json` with id, name, licence; a symlink or other file is not served; the page names the overlays URL, the infra style and the OIM credit; the licence file is served.
- [ ] Step 2-4. Commit.

### Task 10b: Docs

**Files:** `docs/DECISIONS.md` (D-075), `CLAUDE.md`, `CHANGELOG.md`, `docs/reference/cli.md`, `docs/reference/json-interface.md` (regenerated), package pages (regenerated), `docs/guides/offline-navigation.md` (new section), `docs/guides/lan-mirror.md`, capability matrix delta.

- [ ] Write, regenerate, `make check`, commit.

### Task 11: Merge main, final checks, review

- [ ] `git merge origin/main`, keep both sides, regenerate generated pages; `make check` (log, `$?`); `nice -n 19 unshare -r .venv/bin/python -m pytest tests -q -p no:cacheprovider`; one opus whole-branch reviewer; act on findings; report.
