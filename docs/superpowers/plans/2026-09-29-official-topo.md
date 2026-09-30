# Navigation piece 3a: official topographic maps — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `hammunition install navigation` (or `hammunition install ustopo-qmapshack`) also downloads, for the station's US regions, the USGS US Topo 7.5-minute GeoTIFF quads their outlines touch, each checked against the publisher's S3 ETag, warps each to EPSG:3857 with its collar cropped, and builds one `ustopo.vrt` that `hammunition maps qmapshack` registers under `[Canvas] mapPath`.

**Architecture:** One new install method, `topo-quads` (`provider: usgs-ustopo`), resolved at plan time like D-061's `dem-tiles`: the region's outline selects quads from a carried, generated index (`catalog/data/ustopo-quads.txt`, from `scripts/gen_ustopo_index.py`); one new `derived` converter, `ustopo-mosaic`, implemented beside `gdal-dem` on the shared `Staging` class. Both report into D-061's `TerrainLedger`, and the plan's Terrain block gains a US Topo part in text and JSON from one object. FSTopo and 3DEP are the next plan (spec section 8).

**Tech Stack:** Python 3.11+ (`mypy --strict`, pytest, ruff), Pydantic, `gdal-bin` 3.10.3, USGS `prd-tnm` S3 bucket.

**Spec:** `docs/superpowers/specs/2026-09-29-official-topo-design.md`.

## Global Constraints

- The plan wording per quad, exactly: `MD5 from the publisher's object metadata; not pinned by Hammunition`.
- Quad URL: `https://prd-tnm.s3.amazonaws.com/StagedProducts/Maps/USTopo/GeoTIFF/<ST>/<stem>_<date>_TM_geo.tif`.
- Install locations under `<prefix>/share/hammunition/data/`: `usgs-ustopo/<stem>_<date>.tif` + `<slug>.quads`; `ustopo-qmapshack/quads/<stem>_<date>.tif` (+ `.source`), `ustopo-qmapshack/ustopo.vrt`, `ustopo-qmapshack/quads.source`. Staging `~/.cache/hammunition/build/ustopo-qmapshack/ustopo.work/`.
- Privacy: fixtures and docs use public example areas (Vermont, Delaware, Shenandoah) or synthetic regions (`atlantis/*`); nothing of the maintainer's.
- No test reaches the network; GDAL-dependent tests make a tiny synthetic GeoTIFF and skip where `gdalwarp` is absent.
- The machine is the maintainer's field laptop in use: every command under `nice -n 19 ionice -c 3`; no GUI; no sudo; no real install.
- Gates per task: `make check` to a log, `$?` tested; at the end also `unshare -r .venv/bin/python -m pytest tests -q -p no:cacheprovider`.

## Tasks

### Task 1: generalise the outline-to-cells function and the S3 probe
- [ ] Test: `squares_touching(..., per_degree=8)` on a synthetic outline selects the eighth-degree cells it touches; folding at the antimeridian works in cell units; one-degree behaviour unchanged.
- [ ] Test: `S3Probe(bucket=...)` refuses a URL outside its bucket.
- [ ] Implement in `src/hammunition/copernicus.py`.

### Task 2: `src/hammunition/ustopo.py`
- [ ] Tests (`tests/test_ustopo.py`): parse an index line; refuse malformed lines, unsorted rows, an empty index; `select_quads` returns the quads whose bbox overlaps a touched cell (an off-grid bbox included, a neighbour sharing only an edge excluded); `etag_matches` for single-part, 2-part at 8 MiB, 3-part at 5 MiB, `-1`, and a wrong digest; `part_sizes` candidates; `resolve_quad` refuses a changed ETag, a changed size, a non-200 and names the regenerate command.
- [ ] Implement.

### Task 3: `Fetcher.fetch_etag`
- [ ] Tests: single-part delegates to MD5; multipart verified and kept; mismatch discarded with a `VerificationError` naming the ETag; the cached copy is re-verified.
- [ ] Implement in `src/hammunition/fetch.py`.

### Task 4: the index generator
- [ ] Tests (`tests/test_gen_ustopo_index.py`): rows built from a synthetic CSV and listing: current edition preferred, older GeoTIFF edition when the current is PDF-only (counted), a quad with no GeoTIFF dropped (counted); rendering is deterministic and sorted; `--check --offline` passes on the carried file and fails on a hand-edited one; `check_online` fails on a gone key or changed ETag and only counts a newer edition.
- [ ] Implement `scripts/gen_ustopo_index.py`; run `--fetch` once from the cached CSV and listing; wire into `tests/test_docs_generated.py` and the weekly CI job.

### Task 5: schema and catalog-wide plumbing
- [ ] Tests: `TopoQuadsInstall` validates; converter `ustopo-mosaic` needs a `topo-quads` source; `IMPLEMENTED_METHODS` has `topo-quads`; `_reads_map_regions` defers the units with no regions; the package reference and capability matrix render the method.
- [ ] Implement in `schema.py`, `backends/__init__.py`, `plan.py`, `state/uninstall.py`, `scripts/gen_package_reference.py`, `scripts/gen_capability_matrix.py`.

### Task 6: the `topo-quads` backend
- [ ] Tests (`tests/test_topo_backend.py`): steps fetch, install and delete the cached copy per quad; the record per region; removals of quads no region needs; a failed quad goes to the ledger and the others continue; a region with no quad records an empty set and says so.
- [ ] Implement `src/hammunition/backends/topo.py`.

### Task 7: the `ustopo-mosaic` converter
- [ ] Tests (`tests/test_topo_mosaic.py`): argv exactly as the spec; pending/current; publish + sidecar; VRT over installed warped quads only; failures to the ledger; a real run on a synthetic Transverse Mercator GeoTIFF with a collar produces an EPSG:3857 output cropped to the bbox (skipped without GDAL).
- [ ] Implement `src/hammunition/backends/topo_mosaic.py`.

### Task 8: plan-time resolution and wiring
- [ ] Tests (`tests/test_topo_plan.py`): record first, outline second; a HEAD per quad to fetch; offline refusals named together; a region outside the US gets no quad and a note; the memo probe asks each outline once; `TerrainRun` disclosure and disk needs include topo.
- [ ] Implement `src/hammunition/topo_plan.py`, extend `terrain_plan.py`, `execute.commands_for`, `cli/main.py`.

### Task 9: the plan view
- [ ] Tests: text golden for the US Topo part; JSON view; existing goldens byte-identical; `plan_state` says "already installed" when nothing is fetched or warped.
- [ ] Implement in `interface/plan.py`; regenerate `docs/reference/json-interface.md`.

### Task 10: QMapShack registration
- [ ] Test: `wanted()` includes `<data>/ustopo-qmapshack` under `[Canvas] mapPath`.
- [ ] Implement in `qmapshack_config.py`.

### Task 11: manifests, profile, generated docs
- [ ] `catalog/packages/usgs-ustopo.yaml`, `catalog/packages/ustopo-qmapshack.yaml`; add both to `catalog/profiles/navigation.yaml`; regenerate package and profile references; catalog tests updated.

### Task 12: one quad, live
- [ ] Download one small multipart Delaware quad to `.cache/`, check its ETag with `ustopo.etag_matches`, run the converter's argv, record size and time, delete.

### Task 13: documentation
- [ ] D-068 appended at the end of `docs/DECISIONS.md`; CLAUDE.md table row; CHANGELOG under Unreleased; `docs/reference/cli.md`; the navigation profile's page; an "Official topo sheets" section in `docs/guides/offline-navigation.md`.

### Task 14: final review
- [ ] One whole-branch reviewer (opus); fix what it finds; both gates green.
