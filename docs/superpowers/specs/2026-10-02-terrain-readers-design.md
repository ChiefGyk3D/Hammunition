# Terrain readers: SPLAT! and Signal-Server from the station's elevation

**Status:** design for the gap report's item A5
(`docs/reference/catalog-gaps-2026-09.md`), written on the architectural
path without questions; Q-022 needs no ruling for it. The decision is a
dated amendment to D-061, written with the implementation.
**Evidence:** every number below was measured on 2026-10-01 on the
development host, in scratch, on one public Copernicus tile (Death Valley,
`Copernicus_DSM_COG_10_N36_00_W117_00_DEM`, chosen because it holds land
below sea level), synthetic `.hgt` files, and a rootless Podman build of
Signal-Server. The tile was verified against its ETag and deleted after.

## 1. The four readers A5 names, measured

A5 says the terrain layer D-061 built serves one reader (QMapShack, through
`dem-qmapshack`) and could serve four. Each reader, what it reads, and
whether a converter here serves it:

| Reader | Carried? | What it reads | Served by |
|---|---|---|---|
| QMapShack | yes | one GDAL VRT over the tiles (`dem-qmapshack`, D-061) | already served |
| `splat` / `splat-hd` | yes (apt, Blend, 1.4.2 on Parrot) | SPLAT Data Files: `.sdf` or `.sdf.bz2`, one per 1x1 degree, 1200 samples a side for `splat`, 3600 (`-hd.sdf`) for `splat-hd` | **`splat-sdf`, this design** |
| Signal-Server | no, **added here** | the same SPLAT Data Files under its own names (`36_37_116_117-hd.sdf.bz2`), from `-sdf <dir>` | **`splat-sdf`**, through a link per file |
| Xastir | yes (apt) | raster maps as GeoTIFF (`.tif`, DRG-style, with an optional `.fgd`) or any image GraphicsMagick reads with a `.geo` georeference beside it (`/usr/share/doc/xastir/README.MAPS`) | **not served**: an SDF is not a raster Xastir draws. The route is a hillshade raster per tile with a `.geo` file, a third `gdal-dem`-shaped output; carried as a gap (§9) |
| `gpredict`, `hamclock-next` | yes | nothing; a horizon mask from the DEM is what a satellite station would want | post-1.0, as A5 says |

So the converter serves two new readers, SPLAT and Signal-Server, and the
terrain layer serves three of the four A5 counts. Xastir is written down
with its route.

SPLAT also writes an Xastir overlay of its own: `splat -geo` beside `-o
map.ppm` writes a `.geo` georeference Xastir reads (`splat` usage text). A
coverage plot made from this terrain is therefore an Xastir layer today.
The guide says so.

## 2. The SDF format, from SPLAT's own tools

Measured by running Debian's `srtm2sdf` and `srtm2sdf-hd` (splat 1.4.2-3)
over synthetic `.hgt` files whose samples encode their row and column:

* **Name:** `<min_lat>:<max_lat>:<min_west>:<max_west>.sdf`, longitudes
  measured west and positive (0 to 360), so W117..W116 is `36:37:116:117`;
  `-hd.sdf` for the 3600-sample files.
* **Body:** four header lines (`max_west`, `min_lat`, `min_west`,
  `max_lat`), then IPPD x IPPD integers, one per line: 1,440,000 for
  `.sdf`, 12,960,000 for `-hd.sdf`. The outer loop runs from the south row
  northward; the inner from the east column westward. The `.hgt`'s north
  row and east column are dropped (the neighbour tile's).
* **`srtm2sdf-hd` is the one for 30 m data:** it reads a 3601 x 3601
  one-arc-second `.hgt`; `srtm2sdf` reads a 1201 x 1201 three-arc-second
  one.

**Measured finding: by default both tools erase every elevation below
zero.** `-n` is "the elevation below which SRTM data is replaced" and
defaults to 0, and with no USGS-derived SDF to copy from the samples are
replaced by neighbour averages. A synthetic 100 x 100 block at -50 m came
out at 104 m; the real tile's minimum of -91 m survived only with `-n
-32767`. Death Valley, the Dead Sea, the Netherlands and every coastal
polder would otherwise read as dry land at the neighbours' height. So the
converter passes `-d /dev/null -n -32767`: `/dev/null` is the manual's own
"prevents data replacement" (and stops the tool reading an operator's
`~/.splat_path`, which would be this converter's own output), and -32767
leaves only the true void value, -32768, to be averaged.

## 3. The converter's route: GDAL to `.hgt`, then SPLAT's own tools

Two routes were measured on one tile:

| Route | One HD tile | Peak RSS | Output |
|---|---|---|---|
| `gdalwarp` to SRTMHGT, then `srtm2sdf-hd` | 1.38 s + 4.53 s | 151 MB, 51 MB | the format by construction; voids averaged by SPLAT's code |
| `gdalwarp`, then a Python writer of our own | 1.38 s + 1.06 s | 183 MB | byte-identical except at a void (-32768 written as is) |

**Ruling: SPLAT's own tools.** Ours is four times faster on the second
step, and that is its only advantage. The tools define the format; they
handle voids the way SPLAT expects; and they keep the engine's rule that a
converter is an archive program run as the operator in staging, never the
engine's own parser of downloaded data under `sudo`. At about 15 s a tile in
all, a 90-tile region takes some 22 minutes, printed in the plan.

Per tile, in one working directory under the operator's staging tree
(`~/.cache/hammunition/build/splat-sdf/splat.work`, one `flock`, every run
and every clear under it, the `gdal-dem` shape):

1. `gdalbuildvrt -q -resolution highest window.vrt <tile> <installed
   neighbours>`: the tile and the installed tiles of the one-degree ring
   around it, from the same provider. A Copernicus tile's pixel centres sit
   on whole arc seconds from its north and west edges (measured:
   origin `-117.000139, 37.000139`, 1/3600 degree pixels), so its south
   row and east column belong to the neighbours; the mosaic supplies them.
2. `gdalwarp -q --config GDAL_PAM_ENABLED NO -r average -dstnodata -32768
   -te <w-h> <s-h> <e+h> <n+h> -ts 3601 3601 -ot Int16 -of SRTMHGT
   window.vrt hd/<NnnWwww>.hgt`, where h is half a sample. `average`
   copies a Copernicus sample exactly where the grids align (below 50
   degrees) and averages where they do not (the narrower Copernicus columns
   north of 50 degrees, and 3DEP's 1/3" samples). Anything no installed tile
   covers -- the edge row of a coastal tile, a neighbour not in any region
   -- becomes -32768, which `srtm2sdf-hd` fills from its neighbours
   (measured: the south row of the lone real tile read 779, 779, 780 against
   779, 779, 780 one row in).
3. `srtm2sdf-hd -d /dev/null -n -32767 <NnnWwww>.hgt` in `hd/`, then
   `bzip2 -9` of its output.
4. The same at 1201 x 1201 into `sd/`, `srtm2sdf`, `bzip2 -9`.
5. Both `.sdf.bz2` files published into
   `/usr/local/share/hammunition/data/splat-sdf/`, each only if it still
   hashes to what the operator's process measured, with a `.source` sidecar
   (the tile it was made from and `splat-sdf 1`) and, beside each, a
   symbolic link under Signal-Server's name.

**Ruling: compressed.** SPLAT reads `.sdf.bz2` (its manual; measured:
`splat-hd` loaded the `.bz2` and reported 699 m and -17 m where the source
tile has 699.2 and -16.7) and Signal-Server reads `.sdf.bz2` and `.sdf.gz`
(its `LoadSDF_BZ`). The real tile's HD file is 57,033,174 bytes as text
and 5,668,563 as bzip2, a tenth; `bzip2` took 6.65 s and SPLAT's
decompression on load 1.46 s. A 90-tile region is about 5.1 GB as text and
590 MB as written. The standard file is 6,336,641 bytes, 867,797 compressed.
So each tile costs about 6.6 MB under the prefix, carried as 7 MB, and at
most 120 MB of scratch at a time (the `.hgt`, the text SDF and its
compressed copy at HD), each "measured on one tile".

**Ruling: both resolutions.** `splat-hd` is built for "a region of 4
square degrees", `splat` for 8 (their usage text), and on the real tile a
20 km line-of-sight coverage map took `splat` 1.33 s and `splat-hd` 21.5 s.
The standard file is an eighth of the HD one, so both are written: the HD
one for a path profile, the standard one for a wide coverage map, and
either program finds its own.

### The record, the sidecars, and a change of source

Each output's sidecar is `<tile>\nconverter: splat-sdf 1\n`. A file is
current when it exists and its sidecar names the tile this run resolved for
its square with this converter. The SDF names are the same whichever
provider made them (a square is a square), but the tile names are not
(`Copernicus_DSM_COG_10_N36_00_W117_00_DEM` against `USGS_13_n37w117`), so
`hammunition station set --dem-source 3dep` makes every square's sidecar
name the wrong tile and every file is rebuilt; back to Copernicus, the same.
The block reads its `alternative` exactly as `gdal-dem` does (D-068,
amended 2026-10-01): with `3dep` chosen and the block naming `dem-3dep`,
the SDF files are made from 3DEP and a square 3DEP does not cover has none,
which the plan warns about as it already does for QMapShack's elevation.

A file for a square no region needs any more is removed with its sidecar
and its link. A tile that did not install, or a step that failed, is named
in the terrain ledger (D-061), the rest continues, and the ledger's last
step fails the run.

## 4. Signal-Server

**The repository the gap report names no longer holds the code.**
`github.com/Cloud-RF/Signal-Server` was reduced on 2025-08-28 to a README
recording its history: Cloud-RF stopped using it in 2019 and deleted the
code in 2023 "to focus community effort onto the leading fork(s)", naming
two. Measured on 2026-10-01 by cloning each once (D-032: the default
branch's head commit):

| Fork | Head of `master` | Licence | Build |
|---|---|---|---|
| `N9OZB/Signal-Server` | 2019-07-30, `1c365dd` | GPL-2.0 (`LICENSE`) | make |
| `W3AXL/Signal-Server` | **2026-01-30**, `7f6242a` ("Fix buffer overflows", merged) | GPL-2.0 (`LICENSE.txt`) | CMake, needs spdlog |

Neither has ever cut a tag, and no Debian-family archive packages either
(DragonOS carries one in its own image; which commit it builds is not
measurable from here). **Ruling: W3AXL's head commit, pinned under
D-024 with `basis: own_choice`.** It is the live fork, the one Cloud-RF's
README lists as current, and the one with the buffer-overflow fixes; N9OZB's
is seven years still.

**Built once in rootless Podman** (Debian 13, GCC 14.2, CMake 3.31.6,
spdlog 1.15.2), with the engine's own argv shape: configure 0.38 s, compile
38.4 s at 420 MB peak, install 0.02 s; three binaries,
`signalserver`, `signalserverHD`, `signalserverLIDAR`, the same program
choosing its resolution by the name it was started under.

**Measured finding: a release build crashes on every plot.** The engine
builds CMake projects with `-DCMAKE_BUILD_TYPE=Release`, which adds
`-DNDEBUG`, and Signal-Server allocates ITWOM's profile arrays inside
`assert()` (`src/models/itwom3.0.cc`, lines 2143 and 2196:
`assert((s = new double[n + 2])!=0)`). With `NDEBUG` the allocation is
compiled away and every ITM and ITWOM plot dies in `d1thx` (backtrace
taken; also LOS). `-O2` alone ran clean; `-O2 -DNDEBUG` crashed. The
manifest carries `-DCMAKE_CXX_FLAGS_RELEASE=-O2` as a configure argument:
the release flags without `NDEBUG`, no patch. Worth reporting upstream.

**Measured finding: the threaded plot races.** Built correctly, an HD plot
crashed 2 times in 10 and a standard one once in 20; with `-nothreads` 10
HD plots in 10 completed. The guide's command passes `-nothreads`.
Measured on the real tile at a 20 km radius: standard 1.17 s and 600 MB
peak; HD 11 to 18 s threaded and 21 to 29 s unthreaded, 1.36 GB peak. The
HD program allocates its 32 tile pages up front, so its memory is the same
for any plot.

Signal-Server finds a tile at `<-sdf dir>/<lat>_<lat+1>_<west>_<west+1>`
plus `-hd` for the HD program, then `.sdf`, `.sdf.bz2`, `.sdf.gz`; west
longitudes positive, as SPLAT's. It adds the trailing slash itself
(measured). A missing tile is **sea level with a warning and exit 0**
(measured), the same confident wrong answer SPLAT gives; the guide says so.

The unit is `signal-server`, a `git` block, `build_system: cmake`,
`project_file: src` (its `CMakeLists.txt` is in `src/`), in the `antenna`
profile beside `splat`. **The engine's CMake path ignored `project_file`**,
although the schema documents it as "qmake .pro / cmake subdir": the
configure step now passes `-S <tree>/<project_file>` when it is set. No
launcher: it is a command-line program (D-050's generated terminal entry
covers the menu).

## 5. Pointing the readers at the files

SPLAT looks in its working directory, then `-d <dir>`, then the one line of
`~/.splat_path` (measured: with or without the trailing slash). Signal-Server
takes `-sdf <dir>` and reads no file.

`hammunition maps splat`, per user and refused as root, the QMapShack
launcher's rule (D-061):

* no `~/.splat_path`: writes the directory, one line, mode 0644, atomically;
* one naming the directory already: says so and changes nothing;
* one naming another directory: the operator's choice, left alone, and the
  line says to pass `-d` for Hammunition's;
* a symbolic link or anything but a regular file there: refused, nothing
  changed.

It prints the Signal-Server `-sdf` argument either way, and says when no
SDF file is installed yet. It writes nothing during an install: an
install runs under `sudo` and the file is the operator's.

## 6. Units and profile

| Unit | Method | Notes |
|---|---|---|
| `splat-sdf` | `derived`, converter `splat-sdf`, `source: dem-copernicus`, `alternative: dem-3dep` | depends on `dem-copernicus`, `dem-3dep`, `splat`, `gdal-bin`, `bzip2` |
| `signal-server` | `git`, W3AXL `7f6242a`, `cmake`, `project_file: src`, `-DCMAKE_CXX_FLAGS_RELEASE=-O2` | build depends `cmake`, `build-essential`, `libspdlog-dev`, `libbz2-dev`, `zlib1g-dev` |

Both join `antenna`, where `splat` is. With no map regions set,
`splat-sdf` is deferred by name with the rest of the map data (D-057's
deferral reads a `derived` block over a `dem-tiles` source), and
everything else in the profile installs. With regions set, the profile now
fetches their Copernicus tiles and, through `dem-copernicus`'s dependency,
the regions' map extracts; the plan prints both before the confirmation.

## 7. The plan

The *Terrain* block gains a line under its own heading:

    Built for SPLAT! and Signal-Server (sizes an estimate, measured on one tile):
      SDF terrain for N tile(s)  about X (both resolutions, bzip2), up to 120 MB of scratch at a time

and the JSON plan `splat_tiles`, `splat_estimate`, `splat_estimate_human`
in `TerrainSectionView`. The disk check counts the scratch in the
converter's staging directory and the output under the prefix. A current
unit reads "already installed".

## 8. Schema

* `splat-sdf` joins the converter enum, with source method `dem-tiles`.
* `alternative` becomes readable by both `gdal-dem` and `splat-sdf`
  (`CONVERTER_INPUTS` keyed by field owner sets, not one owner per field).
* `PrefixWriter.link(dest, target)`: a symbolic link to a sibling name,
  refused unless the target is a bare file name; written beside the
  destination under a temporary name and renamed into place, through the
  runner where the prefix needs root.

## 9. Not carried, and why

* **An Xastir terrain layer.** Xastir draws a GeoTIFF or a `.geo`-described
  image; the route is a hillshade per tile (`gdaldem hillshade`, already in
  `gdal-bin`) with a `.geo` beside it, which is `gdal-dem`'s shape again.
  Not built here because nothing in Xastir's documentation or a run has
  measured which of the two it draws correctly from a geographic (not UTM)
  raster, and Xastir is a GUI this branch may not start. Recorded as a gap
  with that route.
* **A horizon mask for `gpredict` or `hamclock-next`.** Post-1.0, as A5 says.
* **Signal-Server's LIDAR mode** reads ASCII grids, not SDF; it installs and
  is not fed.
* **Signal-Server's web front ends** (thetacom's GUI, W5GFE's scripts):
  unmeasured, and the second is not in public version control.
* **The `usgs2sdf` route**: it reads the retired USGS 250K DEM format.

## 10. What is measured, and what the bench owes

Measured here: §2 to §5 on one real tile and synthetic files; the
Signal-Server build and plots in a container. Not measured, and owed by the
bench: the converter through `hammunition install` on a real region (time,
peak memory, scratch); SPLAT and Signal-Server plots over that region on
the field laptop; the threaded race on other hardware.
