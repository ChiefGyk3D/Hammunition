# GraphHopper: implementation plan

Spec: `docs/superpowers/specs/2026-10-02-graphhopper-design.md`. Decision:
D-076. Each task is test first (red, then green), then `ruff` and `mypy
--strict` on what it touched, then one commit.

## Task 1: a single jar installed as a tree

- Test (`tests/test_graphhopper_schema.py`, `tests/test_binary_tree_file.py`):
  `format: executable` with `install_tree: true` and a marker with a `/` is
  refused; with a plain marker it validates; the binary backend's steps for
  it are fetch, a staging action, then `tree_install_commands`' four steps,
  the staged file named the marker; `binaries` beside it is refused.
- Code: `BinaryInstall._tree_marker`; `BinaryBackend.steps`.

## Task 2: the converter enum, its input, and the shared refusal loop

- Test: a `graphhopper-import` block needs `program`; `program` on
  `gdal-dem` is still refused; `brouter-mapcreator` still validates; the
  catalog-wide method check names a `program` that is not a `binary` tree.
- Code: the enum, `CONVERTER_SOURCE_METHOD`, `GRAPHHOPPER_INPUTS`,
  `CONVERTER_INPUTS`; the validator refuses a field unless the block's own
  converter lists it.

## Task 3: the shared GraphHopper text and the record

- Test (`tests/test_graphhopper.py`): the import config names the input and
  graph absolutely, JSON-quoted; four profiles, car under CH, the rest under
  LM; the serve config has no input, binds 127.0.0.1 on the given port and
  has `admin_connectors: []`; the record renders and parses; `find_graph`
  is ready only with the converter line, a jar that matches the installed
  one, and every file present, and says why not otherwise.
- Code: `src/hammunition/graphhopper.py`.

## Task 4: the converter

- Test (`tests/test_graphhopper_converter.py`): pending/current from the
  record; steps for one region (no merge) and two (merge); a fake `java` on
  PATH writing a graph; the config written by the operator's `sh` and
  checked; the effect check (no `properties` fails by name); publish all or
  none; stale files removed; a failed region skips the build; the ledger.
- Code: `src/hammunition/backends/graphhopper.py`.

## Task 5: the plan, the disk, the CLI wiring, update

- Test: `routing_plan.GraphRun.needs` (3.7x under the prefix and in scratch,
  plus the merged input with two regions); `graphhopper_pins` from the plan;
  `combined_shortfall` names the graph note; `install graphhopper-graph
  --dry-run` with regions set prints the steps; without regions it is
  deferred by name; `rebuild_command` names the graph.
- Code: `src/hammunition/routing_plan.py`, `terrain.combined_shortfall`,
  `cli/main.py`, `update.rebuild_command`.

## Task 6: the catalog units

- Test (`tests/test_graphhopper_catalog.py`): the pins (URL, sha256, the
  `.asc` URL, marker equal to the URL's file name), `depends`, licence, not
  in `navigation`, in no profile.
- Code: `catalog/packages/graphhopper.yaml`,
  `catalog/packages/graphhopper-graph.yaml`; the navigation profile's prose.

## Task 7: the route through `reference serve`

- Test (`tests/test_reference_router.py`): the query check (two points,
  ranges, finite, profile from the record, nothing else passed through);
  `ch.disable` for non-car; the proxy against a loopback fake GraphHopper
  (port 0) answering `/route`; 503 while not listening; 503 naming the exit
  once the child is gone; the Host rule first; `prepare_router` writes the
  config 0600 and refills the link directory (a stale link and `gh.lock`
  removed, nothing else touched); `run()` spawns the child argv, logs the
  route line, keeps serving when the child exits, stops it on Ctrl-C; the
  CLI starts no router without `java` or with a stale graph, and says why.
- Code: `src/hammunition/reference.py`, `src/hammunition/graphhopper.py`,
  `cli/main.py`.

## Task 8: the page

- Test (`tests/test_map_serve.py` additions): with a router the page has the
  profile selector, the Route and Clear buttons, names only `/map/route` and
  loopback; without, none of it. A headless-Chromium test beside the
  existing one (skipped without the pinned kit, as that one is) routes from
  `#route=` against a fake GraphHopper and asserts the line was drawn and
  every request stayed on 127.0.0.1.
- Code: `src/hammunition/map_page.py`.

## Task 9: one real build and serve, in scratch

The engine's converter run with the real jar, the archive's Java and osmium
over two synthetic regions near Montpelier; the CLI's router preparation
against the result; a route through the proxy. Recorded in D-076. Then the
jar is deleted from `.cache/`.

## Task 10: the documents

The guide (section 16's routes; what Routino, BRouter and GraphHopper are
each for; disk planning; troubleshooting; not measured), `docs/reference/cli.md`,
the CHANGELOG under Unreleased, D-076, CLAUDE.md's row and counts, the
generated pages, `mkdocs.yml` if a page is new.

## Task 11: merge `origin/main`, regenerate, final checks, review

`make check` (log, `$?`) and the suite under `unshare -r`; one whole-branch
review (sonnet, per the maintainer's ruling of 2026-10-01); act on it.
