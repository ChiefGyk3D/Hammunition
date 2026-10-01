# CoMaps and its maps (D-069) — design

**Status:** approved by the maintainer, 2026-09-29, as the brief for this
sub-project. No open questions; the rulings below are the implementer's,
recorded so they can be reviewed.

**Rests on:** the navigation-apps spike (CoMaps and Organic Maps sections) and
the CoMaps source build measured on the development host the same day. Both are
session scratch notes, not repository files; every figure used here is repeated
in D-069 with its date.

## What is carried

1. **`comaps`** — the CoMaps desktop app (Apache-2.0), built from source by the
   `git` backend at tag `v2026.08.31-14`, which must resolve to commit
   `72632e4de65a98dfed827d8e447f0287168639d0`. D-024: Flathub, nixpkgs and the
   AUR all build this commit, so the pin is a distribution's, not ours.
2. **`comaps-maps`** — a D-049 data unit: CoMaps' own `.mwm` map files for the
   station's map regions, fetched from CoMaps' CDN and checked against the
   index at the pinned commit.
3. **The position gap**, documented and not faked: CoMaps on Linux reads
   GeoClue2 only.

Not carried: **Organic Maps** (the same build from the same tree family; one of
the two, and Flathub keeps CoMaps current while Organic Maps' Flathub build is
four months behind); **Flatpak** as a backend (D-014 measured it at zero users;
the Flathub key fingerprint is recorded in D-069 for a future D-040 case).

## The build, as the engine will run it

The spike's build worked with this sequence; the engine reproduces it with
catalog data only and every command owned by the engine:

1. `git init`, `remote add`, `fetch --depth 1 origin v2026.08.31-14`,
   `checkout FETCH_HEAD`, tag recreated — the existing git backend.
2. **Pin check against the commit.** New field `commit:` on a git block whose
   `ref` is a tag. `verify_pin` compares `git rev-parse HEAD` with it and
   refuses a re-cut tag. Until now a tag's resolution was only recorded.
3. **Submodules.** New field `submodules: true`. The git backend did not handle
   submodules at all: it fetched the superproject alone. With the field it runs
   `git submodule update --init --recursive --depth 1` (upstream's own
   `configure.sh` runs exactly this), then reads `git submodule status
   --recursive` and refuses unless there is at least one entry and every entry
   is checked out at its gitlink (a leading space; `-`, `+` and `U` refuse). The
   spike cloned with full history (9.7 GB, ICU alone 5.6 GB); the shallow form
   is upstream's path and is unmeasured here — the bench owes it.
4. **A build-time Python.** New field `build_python:` — hash-pinned requirement
   lines, validated exactly as a venv block's. The engine makes a venv at
   `<build>/build-python` with its own interpreter, installs with
   `--require-hashes`, and gives the prepare, configure and compile commands
   `VIRTUAL_ENV` and a `PATH` with the venv first. CoMaps' CMake refuses
   Debian's protobuf (4.21 reports `__version__` 4.21.12; it wants >= 3.20,
   < 4.0), so `protobuf==3.20.3` with the PyPI wheel's sha256 is the one line.
   **Ruling:** a field on the git block, not the venv backend. The venv backend
   installs a program for the operator into XDG data and puts wrappers on the
   PATH; a build dependency lives and dies with the build directory.
5. **A prepare script.** New field `prepare: {script, args, env, produces}`.
   The engine runs `./configure.sh --skip-map-download` in the tree with
   `SKIP_PYTHON_VENV=1` (so the script does not run its own unpinned `pip
   install`) and `CMAKE_BUILD_PARALLEL_LEVEL` set to the engine's job count
   (the script builds `skin_generator_tool` with a bare `cmake --build`).
   **`produces`** is a list of globs relative to the tree, each of which must
   match at least one non-empty regular file afterwards, or the step fails
   naming the glob: CoMaps' `generate_symbols.sh` exits 0 with no symbols
   when optipng is missing (D-031). CoMaps names
   `data/symbols/*/light/symbols.png` and `data/drules_proto.bin`.
6. `cmake --fresh -S src -B build -DCMAKE_INSTALL_PREFIX=/usr/local
   -DCMAKE_BUILD_TYPE=Release -G Ninja -DSKIP_TESTS=1 -DSKIP_TOOLS=1` — the
   spike's line minus its sysroot flag, the same as Flathub's `config-opts`.
7. `cmake --build build --parallel N`, N from the existing rule
   (`default_jobs`: one per CPU, capped at one per 2 GiB of memory plus swap).
   The measured peak was 1.9 GiB for one compiler process, inside that budget,
   so no per-unit override. **Ruling:** the brief's `-j2` is the fallback "if
   there is no rule"; there is one.
8. `cmake --install build`.
9. **Extra files.** New field `extra_files:` — files the install rule leaves
   out, installed after it with `install -D -m 0644`, after an `rm -f` so a
   symlink at the destination is replaced and never written through. Each is
   either a pinned artifact (`url`, `sha256`, `size`) or a file from the built
   tree (`from_tree`). CoMaps needs three: `World.mwm` and `WorldCoasts.mwm`
   (sha256 from Flathub's manifest, verified by the spike, also matching the
   index's SHA-1) as regular files at `share/comaps/data/`, and
   `categories_brands.txt` from `data/`, which Flathub also installs by hand.
   With `--skip-map-download` and nothing placed, `install_resources` in
   `qt/CMakeLists.txt` skips the missing World files outright; the spike's
   dangling symlinks came from symlinks it had placed itself. Either way the
   engine's files are what land.
10. `installed_files` names the World maps, the symbols sprite and the drules,
    so the effect check reads them back (a dangling symlink fails `exists()`).

`build_depends` is the archive list the spike found present plus the four it
found missing: `qt6-positioning-dev`, `qt6-svg-dev`, `optipng`, `ninja-build`,
and `python3-venv` for the build venv.

**Uninstall** of a `cmake --install` build with a real install rule is refused
today (no file manifest to reverse); CoMaps joins that set and says so.

## Launching

`hammunition maps comaps` is what the `comaps-offline` launcher runs
(`Terminal=false`, category `navigation-maps`). Per user, refused as root:

- **EULA.** CoMaps shows a modal licence dialog until `EulaAccepted=true` is in
  `~/.config/CoMaps/settings.ini` (`qt/main.cpp`). The file is `key=value`
  lines with no sections, and a duplicated key fails a `VERIFY`
  (`string_storage_base.cpp`), so the line is added only when the key is
  absent. A present key, whatever its value, is left alone. A symlink or
  anything but a regular file is refused and CoMaps not started. **Ruling:** at
  launch, per user, not at install, where root would be writing into a home.
- **Maps.** `MWM_WRITABLE_DIR` is set to `~/.local/share/CoMaps` and
  `MWM_RESOURCES_DIR` to the installed data, both measured by the spike. Each
  installed map is linked into `<writable>/<version>/` (CoMaps scans version
  directories with `stat`, which follows symlinks: `platform_unix_impl.cpp`).
  A regular file there (a map the operator downloaded in the app) is left;
  our own links whose targets are gone are removed.
- Then `exec /usr/local/bin/CoMaps`. `--configure-only` stops before it.

The upstream `app.comaps.comaps.desktop` also installs and appears in the
system menu under its own categories; it starts CoMaps without the above.
Documented, not removed.

## `comaps-maps`

- New install method `mwm-regions`, `provider: comaps`, `licence`,
  `licence_url`. Deferred with no regions set, exactly as `osm-regions`.
- `catalog/data/comaps-pins.yaml`, generated by `scripts/gen_comaps_pins.py`
  from `data/countries.txt` at the commit `comaps.yaml` pins: every map's
  `size` and `sha1_base64`, the version (`260830`) and map series
  (`2026.06.28`), and a `regions:` table mapping Geofabrik region paths to
  CoMaps map ids. The table comes from a rule, not a hand list: a region's last
  path component matched against its parent's CoMaps children (prefix
  stripped), else against the top level for a continent's child, with a short
  reviewed alias table (`north-america/us` is "United States of America";
  District of Columbia is `US_Maryland_and_DC`). Every map in the world is
  pinned, so the file says nothing about whose regions matter.
- A region with no row is named in the plan and fetches nothing; the others
  install.
- **Verification.** The SHA-1 is CoMaps' own index at a pinned commit — the
  publisher's check, weaker than a sha256 Hammunition measured, and the plan
  says so on every map line. The size must match exactly: CoMaps' mirrors
  answer a missing file with 200 and an HTML page, so the check is size and
  hash, never status. The fetched bytes' sha256 is written into the step's
  outcome, so the transaction log carries it.
- **Plan.** Each map's size and "ODbL-1.0" print before the confirmation.
  Every map not yet installed is HEAD-checked at plan time: 200 **and** the
  pinned `Content-Length`, else the plan refuses naming the map and the
  regeneration.
- Installed at `<prefix>/share/hammunition/data/comaps-maps/<version>/<id>.mwm`;
  a map no region needs is removed.
- **Expiry.** The CDN keeps a map version about four months (measured on
  Organic Maps' CDN; CoMaps' retention is unmeasured). `update --upstream`
  gains a `comaps_maps` probe: it HEADs the pinned `World.mwm`, reporting
  `pin expired` (the reference branch's wording, same constant) when it is gone
  or the wrong size, `pin expiring` from 90 days after the version date, and
  `current` otherwise. The weekly pin-review job runs the generator's `--check`.

## The position gap

CoMaps on Linux asks Qt Positioning for the `geoclue2` plugin by name. No gpsd
client, no NMEA reader. The route is GeoClue's network-NMEA source fed by the
tether, plus an `[app.comaps.comaps] allowed=true` entry in `geoclue.conf`
(Parrot's whitelist names no KDE agent). Both unmeasured, both system
modifications this project would have to disclose, neither made here. The guide
and the manifest say plainly: no "you are here" on the laptop yet.

## Unmeasured, said plainly

- US address search quality: the desktop app has no scriptable search; the
  bench owes it.
- The whole build through the engine, the shallow submodule fetch, and the
  launcher's map links on a running CoMaps.
