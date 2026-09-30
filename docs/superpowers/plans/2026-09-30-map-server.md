# The local map server — implementation plan (D-071)

Spec: `docs/superpowers/specs/2026-09-30-map-server-design.md`. Executed
inline, test first; each task ends with its tests green and one commit.

1. **Archive members** — `DataArtifact.members` and `into` (archives only;
   `into` a plain name; a unit with two archives, or an archive beside
   files, needs `into` on every archive); `extract(..., members=)` in
   `src/hammunition/backends/source.py` extracts only the named files and `dir/` prefixes
   and refuses a name that matched nothing; the data backend extracts into
   `<data>/<unit>/<into>`. Tests: `tests/test_data_members.py`.
2. **Schema** — converter `tilemaker-pmtiles` (source `osm-regions`), field
   `kit` (required for it, refused elsewhere, in `depends`, a `data` unit
   catalog-wide). Tests: `tests/test_pmtiles_schema.py`.
3. **Converter** — `src/hammunition/backends/pmtiles.py`: `TilesConverter`, `TilesLedger`,
   argv, clip box, effect check, sidecar, removal, disk needs; `tiles_plan.py`
   builds the run. Fake `tilemaker`/`ogr2ogr`. Tests:
   `tests/test_pmtiles.py`.
4. **Plan floor** — `TILEMAKER_FLOOR` checked against the probe; deferral
   and refusal by name; note without lists. Tests:
   `tests/test_pmtiles_plan.py`.
5. **Install wiring** — `cmd_install` builds the tiles run, adds its
   converter, its disk needs and idle set; `leftover_maps_note` and
   `update`'s rebuild command know `.pmtiles`/`osm-pmtiles`.
6. **Catalog** — `vector-map-kit.yaml`, `osm-pmtiles.yaml`, `navigation`
   profile. Tests: `tests/test_tiles_catalog.py` (pins equal the measured
   digests, credit and licences present, profile members).
7. **Range server and page** — `map_page.py` (shelf, page, regions JSON,
   file map); `reference.py` routes, Range, Host check, landing section;
   `reference serve --position-port`. Tests: `tests/test_map_serve.py`.
8. **Position** — tether HTTP listener, SSE clients in the fan-out, Host
   and Origin rules, `--position-port`. Tests: `tests/test_gps_position.py`.
9. **Headless render** — `tests/test_map_render.py` with a synthetic
   PMTiles writer (`tests/pmtiles_fixture.py`); skipped by name without
   Chromium or the kit archives.
10. **Docs** — D-071, CLAUDE.md row and counts, CHANGELOG, cli.md,
    offline-navigation and offline-reference guides, regenerated pages.
11. **Verify** — `make check` and the suite under `unshare -r`; the one
    reviewer; fixes; report.
