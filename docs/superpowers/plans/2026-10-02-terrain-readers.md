# Terrain readers: implementation plan

**Spec:** `docs/superpowers/specs/2026-10-02-terrain-readers-design.md`.
**Branch:** `terrain-readers`, from `origin/main` at `05a062a`.
**Method:** test first for every engine change; one commit per task; the
ledger at the end records each task's result and every ruling.

## Tasks

1. **Schema.** `splat-sdf` in `DerivedDataInstall.converter` and
   `CONVERTER_SOURCE_METHOD` (`dem-tiles`); `alternative` read by both
   `gdal-dem` and `splat-sdf` (a field may have several owners). Tests:
   a `splat-sdf` block validates with and without `alternative`; another
   converter carrying `alternative` is still refused; the catalog-wide
   provider check covers the new owner.
2. **`PrefixWriter.link`.** A symbolic link to a bare sibling name, direct
   and through the runner; refuses a target with a slash or `..`. Tests for
   both paths and the refusal.
3. **CMake `project_file`.** The configure step passes `-S
   <src>/<project_file>` when it is set. Test on `build_commands`.
4. **The converter**, `src/hammunition/backends/splat_sdf.py`: names
   (`sdf_name`, `signal_server_name`, `hgt_name`), argv builders
   (`window_argv`, `warp_argv`, `convert_argv`, `compress_argv`),
   `pending`, `current`, `steps` (per tile: convert as the operator, then
   publish both files, sidecars and links), removal of squares no longer
   needed, the ledger. Tests with fake tools in the `gdal-dem` style:
   argv, one working directory and lock, `-n -32767`, outputs checked not
   exit codes, a failed tile named in the ledger, a provider change
   rebuilding, removal, links.
5. **Plan and disk.** `splat` on `TerrainRun` and `build_terrain_run`;
   `TerrainDisclosure.splat_tiles`; estimates and scratch in
   `src/hammunition/backends/terrain.py`; the text block and the JSON
   fields in `src/hammunition/interface/plan.py`; "already installed"
   when current. Tests on the
   disclosure, the needs, the text and the JSON.
6. **`hammunition maps splat`.** Per user, refused as root; writes
   `~/.splat_path` only when absent; leaves another path alone; refuses a
   symlink. Tests with a temporary HOME.
7. **Catalog.** `catalog/packages/splat-sdf.yaml`,
   `catalog/packages/signal-server.yaml`, both in
   `catalog/profiles/antenna.yaml`; `splat.yaml`'s prerequisites and the
   profile's prose updated. Tests: the manifests load, the profile plans
   with `splat-sdf` deferred when no regions are set.
8. **Docs.** The propagation guide's "Terrain for coverage plots" (with
   the Signal-Server command from `FN31pr`'s centre), `docs/reference/cli.md`,
   `CHANGELOG.md` under Unreleased, a dated amendment to D-061, the gap
   report's A5 line, CLAUDE.md's counts; regenerate the package pages, the
   profile pages and the JSON reference.
9. **A real converter run** through the engine's code over the one
   verified Death Valley tile, in scratch, timed with peak RSS; then the
   tile deleted.
10. **Close.** Merge `origin/main`, regenerate, `make check` and the full
    suite under `unshare -r`, one whole-branch review on sonnet (the
    maintainer's ruling of 2026-10-01 replaced opus), fixes, report.

## Ledger

| Task | Commit | Result |
|---|---|---|
| Spec and plan | `50f838b` | written from the measurements of 2026-10-01 |
| 1. Schema | `3de3388` | tests red first (enum), then green |
| 2. `PrefixWriter.link` | `6ec27c8` | tests red first, both writer paths |
| 3. CMake `project_file` | `b0458df` | test red first; `project_file` validated inside the tree |
| 4. Converter | `ba3e5f9` | fakes plus a real-tools test; the real test found gdalwarp refusing the second `.hgt` (fixed by removing it between resolutions) |
| 5. Plan and disk | `29db5df` | tests written after the wiring and passing; the converter set in `test_terrain_cli.py` updated |
| 6. `maps splat` | `4b1e02e` | tests isolated from the machine's prefix |
| 7. Catalog | `41d90c6` | profile plans with `splat-sdf` deferred without regions |
| 8. Docs | `e2a431a` | link check and docs tests green |
| 9. Real run | (no commit) | engine code over Death Valley's tile: 16.3 s, 151.2 MB, current after; SPLAT! and Signal-Server read the output |
| 10. Merge, checks, review | `20b33bc`, `e29374f` | `make check` 0 and the suite under `unshare -r` 0 before review; the review's one Important finding (the link not checked by `pending`) fixed test-first |

**Rulings made on the way** (each in the spec or D-061's amendment):
SPLAT's own converters, not a writer of ours; `-n -32767 -d /dev/null`;
compressed files at both resolutions; W3AXL's fork at its head, own-choice
review; `-DCMAKE_CXX_FLAGS_RELEASE=-O2` rather than a patch; `-nothreads`
in the guide; `antenna` as the profile, where `splat` is; Xastir recorded
as a gap with its route, not built; the final review on sonnet (the
maintainer's ruling of 2026-10-01).
