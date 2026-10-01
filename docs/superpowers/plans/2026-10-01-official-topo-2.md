# Navigation piece 3a, second plan: FSTopo sheets and 3DEP elevation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `hammunition install navigation` also fetches, for the station's US regions, the Forest Service FSTopo 7.5-minute GeoTIFFs their outlines touch (sha256-checked where Hammunition pinned one, otherwise disclosed as unverified, by name) and makes them a second QMapShack map, `FSTopo.vrt`, beside `ustopo.vrt`; and, when the operator sets `hammunition station set --dem-source 3dep`, fetches USGS 3DEP 1/3-arc-second bare-earth tiles (checked against the publisher's S3 ETag) and draws QMapShack's elevation and contours from them instead of Copernicus.

**Architecture:** Two new provider members on existing install methods, never a new method: `topo-quads` gains `provider: usfs-fstopo`, `dem-tiles` gains `provider: usgs-3dep`. Each has a carried, generated list (`catalog/data/fstopo-quads.txt` from the GTAC index, `catalog/data/usgs-3dep-tiles.txt` from a bucket listing) so the plan picks a region's items offline from the outline it already fetches (one `MemoProbe`). The existing backends gain a provider dispatch (`TopoQuadsBackend.fstopo`, `DemTilesBackend.bare_earth`), so `execute.commands_for` keeps its signature. `ustopo-mosaic` gains an optional `fstopo` input; `gdal-dem` an optional `alternative` input, used when the station's `dem_source` is `3dep`. Both report into D-061's one `TerrainLedger`.

**Tech Stack:** Python 3.11+ (`mypy --strict`, pytest, ruff), Pydantic, `gdal-bin` 3.10.3, ArcGIS REST (GTAC index, generator only), the Forest Service raster gateway, USGS `prd-tnm` S3.

**Spec:** `docs/superpowers/specs/2026-09-29-official-topo-design.md` §8 (no new spec), D-068 "Next", and the spike measurements quoted in D-068.

## Measured facts that change §8 (recorded as a dated §8 note in the spec)

Measured 2026-10-01 on the development host with GDAL 3.10.3, offline, on the spike's own Reddish Knob FSTopo GeoTIFF and on synthetic rasters:

1. The FSTopo GeoTIFF is **stripped** (`Block=8951x1`) and has **no overviews**. A plain `gdalbuildvrt` over 74–200 such sheets reads whole 100-megapixel pages to draw a zoomed-out view.
2. `gdalbuildvrt` over two paletted GeoTIFFs whose colour tables differ exits 0, keeps only the first palette and warns "The end result might produce weird colors ... pre-process ... with gdal_translate -expand RGB". Whether FSTopo sheets share one palette is unmeasured (one sheet only).

So the FSTopo converter is not a plain `gdalbuildvrt`: per sheet, `gdal_translate -q -expand rgb -co TILED=YES -co COMPRESS=JPEG -co PHOTOMETRIC=YCBCR` then the same `gdaladdo 2 4 8 16` US Topo uses, then one `gdalbuildvrt` over the converted sheets. No warp: the sheet is already EPSG:4269 and collarless.

## Global Constraints

- FSTopo plan wording, per sheet: pinned `sha256, pinned by Hammunition (the Forest Service publishes no checksum)`; unpinned `unverified: the Forest Service publishes no checksum and Hammunition has pinned none; only the size is checked`.
- 3DEP plan wording, per tile: `MD5 from the publisher's object metadata; not pinned by Hammunition` (the Copernicus wording; ETag only — CRC64NVME is not used, Task 3 records why).
- FSTopo URL: `https://data.fs.usda.gov/geodata/rastergateway/downloadMap.php?mapID=<secoord>&mapType=tif&seriesType=FSTopo`; the plan follows its one 302 itself and fetches the `Location`, which must be `https://data.fs.usda.gov/geodata/rastergateway/…` and end `.tiff`.
- 3DEP URL: `https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/13/TIFF/current/<nYYwXXX>/USGS_13_<nYYwXXX>.tif`, named by the **north-west** corner.
- Install locations under `<prefix>/share/hammunition/data/`: `usfs-fstopo/<ST>_<Name>_<secoord>_<vintage>.tif` + `<slug>.quads`; `dem-3dep/USGS_13_<nYYwXXX>.tif` + `<slug>.tiles`; `ustopo-qmapshack/fstopo/<name>.tif` (+ `.source`), `ustopo-qmapshack/FSTopo.vrt`, `ustopo-qmapshack/fstopo.source`.
- Station key `dem_source`: `copernicus` (default when unset) or `3dep`; never a template variable.
- Copernicus stays installed in both modes: BRouter's elevation reads it, and it covers regions outside the US.
- Privacy: fixtures and docs use Delaware, Vermont, Shenandoah, George Washington National Forest, or synthetic `atlantis/*` / `ZZ` regions. Sheet and tile names are places: plan only.
- No test reaches the network; GDAL tests build synthetic rasters and skip without `gdal-bin`.
- Machine: every command under `nice -n 19 ionice -c 3`; no GUI; no sudo; no real install; never `pkill`/`killall` by name.
- Gates: `make check` to a log, `$?` tested; `nice -n 19 unshare -r .venv/bin/python -m pytest tests -q -p no:cacheprovider`.

## Review Focus

1. **Switching `--dem-source` back to `copernicus`** after 3DEP was installed: the 3DEP tiles and records must be removed, the contours redrawn from Copernicus and both VRTs rebuilt — never a VRT naming removed files. Test in Task 4 and Task 9.
2. **A region outside the US with `dem_source: 3dep`**: no 3DEP tile; the plan warns that QMapShack gets no elevation for it, Copernicus still installs, nothing fails. Test in Task 3.
3. **An FSTopo redirect to somewhere else** (another host, `http`, not `.tiff`, no redirect at all): refused at plan time by name, never followed. Test in Task 6.
4. **A pinned FSTopo sheet the Forest Service re-issued** (size changed): refused at plan time naming the pin and the regeneration command, never fetched against the old pin. Test in Task 6.
5. **A region with US Topo and no FSTopo** (Delaware: no National Forest): no `FSTopo.vrt` built, a note in the plan, `ustopo.vrt` unaffected. Test in Task 8.

---

### Task 1: schema, station key and CLI flag

**Files:** `src/hammunition/manifest/schema.py`, `src/hammunition/station.py`, `src/hammunition/cli/main.py` (`station set`), `src/hammunition/interface/station.py`; tests `tests/test_schema.py` (or the derived-input tests), `tests/test_station.py`.

**Produces:** `DemTilesInstall.provider: Literal["copernicus-glo30", "usgs-3dep"]`; `TopoQuadsInstall.provider: Literal["usgs-ustopo", "usfs-fstopo"]`; `DerivedDataInstall.alternative: str | None` (gdal-dem only, `dem-tiles`, optional) and `.fstopo: str | None` (ustopo-mosaic only, `topo-quads`, optional), both via `CONVERTER_INPUTS`; `Station.dem_source: str | None` with `DEM_SOURCES = ("copernicus", "3dep")` and property `Station.elevation -> str` (`"copernicus"` when unset); `DEM_PROVIDERS = {"copernicus": "copernicus-glo30", "3dep": "usgs-3dep"}`.

- [ ] Tests: the two providers validate; `alternative` on `mkgmap` is refused; `fstopo` on `gdal-dem` is refused; neither is required; `Station(dem_source="srtm")` raises naming both values; load/save round-trips `dem_source`; `dem_source` is not in `STATION_FIELDS`; `station set --dem-source 3dep` saves and prints it, and alone counts as something to set; `station show` and its JSON carry it.
- [ ] Implement; run the tests red then green; commit.

### Task 2: `src/hammunition/usgs3dep.py` and the tile list

**Files:** create `src/hammunition/usgs3dep.py`, `scripts/gen_3dep_tiles.py`, `catalog/data/usgs-3dep-tiles.txt`, `tests/test_usgs3dep.py`, `tests/test_gen_3dep_tiles.py`; modify `tests/test_docs_generated.py`, `.github/workflows/ci.yml` (weekly job).

**Produces:** `tile_name(square) -> str` (`USGS_13_n39w079` for square `(38, -79)`), `square_of(name) -> Square` (south-west corner, as Copernicus's), `dem_square(name) -> Square` (either provider), `tile_url(name)`, `TileRow(name, size, etag)`, `parse_tile_list(text) -> dict[str, TileRow]` (refuses an empty list), `load_tile_list(path)`, `check_tile(row, probe)` (200, same size and ETag, else `CopernicusError` naming `scripts/gen_3dep_tiles.py --fetch`), `PIXELS = 10812`.

- [ ] Tests: NW naming both ways incl. the southern and eastern hemispheres refused (3DEP names only `n`/`s`, `w`/`e` as published); `dem_square` on both providers; malformed and duplicate rows refused; `check_tile` refuses a changed ETag, a changed size, a 404. Generator: rows from a synthetic listing keep only `current/<t>/USGS_13_<t>.tif`; deterministic render; `--check --offline` passes on the carried file and fails on a hand edit; `check_online` names a gone tile or a changed ETag.
- [ ] Implement; run `scripts/gen_3dep_tiles.py --fetch` once (one bucket listing, no download); commit the list.

### Task 3: 3DEP resolution and the ETag-verified tile

**Files:** `src/hammunition/copernicus.py` (`TileFile.etag`), `src/hammunition/backends/dem.py`, `src/hammunition/terrain_plan.py`; tests `tests/test_dem_backend.py`, `tests/test_terrain_plan.py`.

**Produces:** `TileFile.etag: str | None = None` (`verified_by` returns `UNPINNED` for it); `DemTilesBackend.bare_earth: DemTilesBackend | None` and dispatch on `block.provider`; `resolve_station_3dep(plan, maps, catalog_root, *, prefix, source, region_probe, tile_probe) -> tuple[DemResolution, tuple[str, ...]]` — empty with a note when `source != "3dep"`; `no_bare_earth_line(region)`.

- [ ] Tests: an etag tile fetches through `Fetcher.fetch_etag` and installs re-verified by the sha256 measured on arrival; a region with squares and no 3DEP tile records `unpublished` and warns; `source="copernicus"` resolves nothing, asks no outline and no HEAD, and the backend's steps remove installed 3DEP tiles and records; a HEAD answering another ETag refuses naming the regenerate command.
- [ ] Measure pure-Python CRC-64/NVME speed on 64 MiB once and record the ruling (ETag only) in the module docstring.
- [ ] Implement; commit.

### Task 4: `gdal-dem` reads either provider

**Files:** `src/hammunition/backends/gdal_dem.py`, `src/hammunition/backends/terrain.py`; test `tests/test_gdal_dem.py`.

**Produces:** `GdalDemConverter.source_unit: str | None` (overrides `block.source`), `.provider: str`; `rasterize_argv(gpkg, out, name, pixels=PIXELS)`; `pixels_for(name)`; `contour_bytes(provider)`, `contour_scratch(provider)`; the record gains `elevation: usgs-3dep` before `converter:` for 3DEP only (a Copernicus record is byte-identical to today's, so no existing install rebuilds).

- [ ] Tests: argv for a 3DEP tile uses `-te -79 38 -78 39 -ts 10812 10812`; Copernicus argv unchanged; a 3DEP resolution reads tiles from `data/dem-3dep`; switching provider makes `current()` false and removes the other provider's contour rasters; real GDAL on a synthetic NW-named Float32 tile draws contours (skip without GDAL).
- [ ] Implement; commit.

### Task 5: `src/hammunition/fstopo.py` and the index

**Files:** create `src/hammunition/fstopo.py`, `scripts/gen_fstopo_index.py`, `catalog/data/fstopo-quads.txt`, `catalog/data/fstopo-pins.yaml` (`pins: []`), `tests/test_fstopo.py`, `tests/test_gen_fstopo_index.py`; modify `src/hammunition/ustopo.py` (the cell index made generic over any boxed item), `tests/test_docs_generated.py`, `.github/workflows/ci.yml`.

**Produces:** `FsQuad(south, west, north, east, secoord, state, cell, vintage)` with `.name` `<ST>_<Cell>_<secoord>_<vintage>`, `.map_url`; `FsIndex.select(outer, holes)`; `parse_index`, `load_index`; `FsPin(secoord, size, sha256)`, `load_pins(path)`; `GATEWAY`, `RASTER_PREFIX`.

- [ ] Tests: row parse/refuse; a cell name with spaces and an apostrophe; selection by eighth-degree cell; pins file validation (missing keys, duplicate, bad hex). Generator: features → rows (bbox from rings, sorted, deterministic); an all-water or nameless feature counted, not carried; `--check --offline`; `--pin SECOORD` with an injected fetch writes the pin and keeps the others.
- [ ] Implement; run `scripts/gen_fstopo_index.py --save-features` then `--fetch --features` once (19 pages, no sheet downloaded); commit.

### Task 6: the FSTopo backend and plan-time resolution

**Files:** create `src/hammunition/backends/fstopo.py`; modify `src/hammunition/fetch.py` (`fetch_sized`), `src/hammunition/backends/topo.py` (`TopoQuadsBackend.fstopo` dispatch), `src/hammunition/topo_plan.py` (`resolve_station_fstopo`), `src/hammunition/fstopo.py` (`GatewayProbe`); tests `tests/test_fstopo_backend.py`, `tests/test_fstopo_plan.py`, `tests/test_fetch.py`.

**Produces:** `GatewayProbe.locate(secoord) -> tuple[str, int]` (no-follow GET-less: one HEAD on the gateway expecting 302, one HEAD on the Location); `FsQuadFile(quad, url, size, sha256 | None)`; `FsTopoResolution(regions, fetch, current)`; `FsTopoBackend.steps`; `Fetcher.fetch_sized(url, expected_size)` (size-capped, size-checked, the first bytes a TIFF, sha256 returned).

- [ ] Tests: Review Focus 3 and 4; pinned → `fetch`; unpinned → `fetch_sized` and the plan's unverified wording; a non-TIFF body is refused; records, removals and edition replacement as US Topo; one failed sheet goes to the ledger, the others continue; a region with no FSTopo sheet records an empty set and gets a note.
- [ ] Implement; commit.

### Task 7: the FSTopo part of `ustopo-mosaic`

**Files:** `src/hammunition/backends/topo_mosaic.py`; test `tests/test_topo_mosaic.py`.

**Produces:** `translate_argv(source, out)`; `FSTOPO_CONVERTER = "ustopo-mosaic fstopo 1"`, `FSTOPO_VRT = "FSTopo.vrt"`, `FSTOPO_RECORD = "fstopo.source"`; `UstopoMosaicConverter.fstopo: FsTopoResolution | None`, `.fstopo_pending(manifest)`, `.fstopo_building(manifest, block) -> bool`.

- [ ] Tests: argv exactly; translate + overviews per pending sheet, publish + sidecar; `FSTopo.vrt` over installed converted sheets only; Review Focus 5; real GDAL on two synthetic paletted sheets with different palettes gives an RGB mosaic whose second half carries the second palette's colour (skip without GDAL).
- [ ] Implement; commit.

### Task 8: wiring, disclosure, plan view, update

**Files:** `src/hammunition/terrain_plan.py`, `src/hammunition/cli/main.py`, `src/hammunition/interface/plan.py`, `src/hammunition/update.py`, `src/hammunition/backends/terrain.py` (disk needs), `docs/reference/json-interface.md` (regenerated); tests `tests/test_topo_cli.py`, `tests/test_terrain_cli.py`, `tests/test_json_plan_terrain.py`, `tests/test_update*.py`.

**Produces:** `TerrainDisclosure.bare_earth: BareEarthDisclosure | None`, `TopoDisclosure` reused for FSTopo as `TerrainDisclosure.fstopo`; JSON `terrain.bare_earth` and `terrain.fstopo`; text blocks "USGS 3DEP bare-earth elevation (D-068)" with **size per region** and "FSTopo, Forest Service 7.5-minute quads (D-068)"; `plan_state` per provider; disk needs count 3DEP, FSTopo and the translated copies; `update` counts installed FSTopo sheets and 3DEP tiles.

- [ ] Tests: dry runs through `cli.main` for each unit with fake probes, text and JSON; existing goldens byte-identical; a run in copernicus mode with `dem-3dep` planned says so in a note.
- [ ] Implement; regenerate the JSON reference; commit.

### Task 9: manifests, profile, generated pages

**Files:** create `catalog/packages/usfs-fstopo.yaml`, `catalog/packages/dem-3dep.yaml`; modify `catalog/packages/ustopo-qmapshack.yaml` (`fstopo`), `catalog/packages/dem-qmapshack.yaml` (`alternative`), `catalog/profiles/navigation.yaml`; regenerate `docs/packages/`, the profile page, the capability matrix; catalog tests.

- [ ] Implement; run every generator with `--check`; commit.

### Task 10: one FSTopo sheet and one 3DEP tile, live

- [ ] Fetch one George Washington National Forest FSTopo sheet through `GatewayProbe` and `Fetcher.fetch_sized` into `.cache/`, record size and sha256 (not pinned: the maintainer pins), run `translate_argv` + `overviews_argv` + `gdalbuildvrt`, record times and sizes, delete.
- [ ] Fetch one Shenandoah 3DEP tile through `check_tile` and `Fetcher.fetch_etag` into `.cache/`, run `contour_argv` + `rasterize_argv` at 10,812 px, record times and sizes, delete. Update the estimates measured here.

### Task 11: documentation

- [ ] D-068 dated amendment (not a new number); spec §8 dated note; CLAUDE.md counts and table row; CHANGELOG under Unreleased; `docs/reference/cli.md` (`--dem-source`); station docs; the guide's official-topo section extended (FSTopo, 3DEP, why Copernicus stays the default: canopy versus bare earth, and size); not carried (1 m lidar, GeoPDF, Historical Topo); unmeasured: QMapShack drawing either mosaic, owed by the bench in a VM.

### Task 12: final review

- [ ] One whole-branch reviewer subagent on opus; fix what it finds; both gates green; report.
