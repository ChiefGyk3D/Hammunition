# Navigation: BRouter routing beside Routino

**Status:** design approved by the maintainer in conversation 2026-09-29
(BRouter as a pinned binary unit, a `brouter-segments` converter building
its routing files from the station's own regions with Copernicus elevation,
the QMapShack launcher registering it). This document is written for the
record and for the implementation plan.
**Decision record:** D-063, written with the implementation. It amends
D-061, whose gaps list said "BRouter stays out".
**Evidence:** the routing spike of 2026-09-29 (five engines measured on
Delaware, a public example state), and the synthetic end-to-end run in §6
below.

## 1. What this piece delivers

| Need | Answer |
|---|---|
| Hiking routes that know trail difficulty | BRouter's `hiking-mountain` profile reads `sac_scale`; Routino's foot profile does not (D-061 gap) |
| Bike, gravel, MTB and car routes that weigh climbs | BRouter's 26 shipped profiles, over our own elevation |
| Voice hints and elevation on the route | BRouter's output, drawn by QMapShack |
| Offline, and from checked data only | Routing files built on the machine from the regions Hammunition already fetched and verified, with the Copernicus tiles it already fetched and verified |

QMapShack 1.17.1 (already carried) has a real local BRouter backend
(`CRouterBRouterLocal`): it starts `java -cp <jar> btools.server.RouteServer
<segments> <profiles> <customprofiles> <port> <threads> [<host>]` itself as a
`QProcess`, in `localDir`, and talks HTTP to it. Nothing is installed as a
service; BRouter runs only while QMapShack uses it.

## 2. Units

### `brouter` (binary, zip, installed as a tree)

`brouter-1.7.10.zip` from the v1.7.10 GitHub release: 6,724,983 bytes,
sha256 `023fec3ba997758e8cd7ab9e1bae52e962af3f00b57683e3de86b84ffad01532`,
GitHub's own asset digest, measured equal on 2026-09-29. No signature
exists. The zip has one top directory, stripped by the binary backend's
extraction; the tree lands at `/usr/local/share/hammunition/brouter/`:
`brouter-1.7.10-all.jar` (the router and the map creator, protobuf
included), `brouter-1.7.10-ro.jar`, `lib/`, `profiles2/` (26 profiles and
`lookups.dat`) and the Android APK, which nothing uses and which is not
worth a special case. `tree_marker: brouter-1.7.10-all.jar`. No launcher:
QMapShack starts BRouter. `depends: [default-jre-headless]` (class files
major 55, Java 11; Debian 13's default is 21). Licence MIT (the GitHub API;
QMapShack's about text still says GPLv3, which is stale).

### `brouter-mapcreator-profiles` (data, two files)

The map creator needs `all.brf` (what to keep) and `softaccess.brf`, which
are in the source tree (`misc/profiles2/`) and not in the release zip. They
are not routing profiles: if they sat in `profiles2`, QMapShack would list
"all" and "softaccess" as profiles to route with, so they live in their own
data unit, not in the `brouter` tree.

The v1.7.10 source tarball (`archive/refs/tags/v1.7.10.tar.gz`, 2,037,047
bytes, sha256 `cb83f220332de8223476e029a9b075157fb74401c69a991ceaa013486c29760f`,
our own measurement, since GitHub publishes none for archives) was
downloaded and its two members hashed. **Ruling 1:** the unit fetches the two
files from `raw.githubusercontent.com` at the tag's commit
(`4d2639af77ea5ed9c30d3e400764eb6f9e8522da`), each pinned by the sha256 of
the tarball member (`all.brf` 511 bytes `87d49d6a…f144`, `softaccess.brf`
631 bytes `0c04a588…7190`), rather than the tarball itself. Same bytes, same
pin discipline; but a commit-addressed file is immutable where GitHub's
generated archive tarballs are not guaranteed byte-stable (they changed
checksum in January 2023), and a `data` tarball would install a whole
source tree, under a versioned top directory the engine would then have to
guess at, for 1.1 KB. The manifest records the tarball's digest and the
equality.

### `brouter-segments` (derived, converter `brouter-mapcreator`)

BRouter's `.rd5` routing files, one per 5°×5° square, built from every
installed region with Copernicus elevation folded in, installed under
`/usr/local/share/hammunition/data/brouter-segments/`. The block names four
units, each also in `depends` (checked per manifest) and each checked
catalog-wide for its method (the `CONVERTER_SOURCE_METHOD` pattern):

| Field | Unit | Must be |
|---|---|---|
| `source` | `osm-regions` | `osm-regions` |
| `program` | `brouter` | `binary` with `install_tree` |
| `profiles` | `brouter-mapcreator-profiles` | `data` |
| `elevation` | `dem-copernicus` | `dem-tiles` |

`program`, `profiles` and `elevation` are refused on any other converter,
and `program` and `profiles` are required on this one; `elevation` is
optional (a build without it routes flat).

**brouter.de's segments are never fetched.** Its `segments4/` directory
publishes 1,142 files rebuilt weekly with no checksum of any kind, which is
why D-061 left BRouter out; building our own from checked inputs removes the
objection. The docs say so.

## 3. The converter

One build over every region, in one working directory
(`<staging>/brouter.work`, one lock), exactly Routino's shape. **Ruling 2:**
not one build per region, because output files are named by square and two
regions in one 5°×5° square would each produce `W80_N35.rd5`; one routing
file per square must come from every region in it. `OsmFastCutter` reads one
file, so more than one region is merged first.

Steps, each an `Action` run as the operator through `Staging`:

1. **Merge** (only with two regions or more): `osmium merge <pbf>... -o
   merged.osm.pbf --overwrite`. `osmium-tool` is a dependency (piece 1
   already carries it).
2. **Elevation**, one step per 5°×5° square holding an installed tile, when
   `elevation` is set: `gdalbuildvrt -q window.vrt` over the installed
   tiles in the square and the one-degree ring around it (the converter
   reads that ring for its border), then per tile `gdalwarp -q --config
   GDAL_PAM_ENABLED NO -te <lon−½″> <lat−½″> <lon+1+½″> <lat+1+½″> -ts 3601
   3601 -ot Int16 -of SRTMHGT window.vrt hgt/<N39W076>.hgt`, then `java
   -Xmx… -cp <jar> btools.mapcreator.ElevationRasterTileConverter
   srtm_<XX>_<YY> hgt bef 1`, and the `.hgt` files are removed before the
   next square. Warping from a mosaic of the window, not tile by tile, keeps
   the tile edges from reading as no-data.
3. **Cut**: `java … -DavoidMapPolling=true -DuseDenseMaps=true
   -Ddeletetmpfiles=true btools.mapcreator.OsmFastCutter lookups.dat
   nodetiles waytiles nodes55 waytiles55 bordernids.dat relations.dat
   restrictions.dat all.brf trekking.brf softaccess.brf <pbf>`.
4. **Unify**: `PosUnifier nodes55 unodes55 bordernids.dat bordernodes.dat
   bef`.
5. **Link**: `WayLinker unodes55 waytiles55 bordernodes.dat restrictions.dat
   lookups.dat all.brf segments rd5`.
6. **Install**: every `segments/*.rd5` published under `<name>.new`,
   verified, then renamed in, stale `.rd5` files removed, and the record
   written; all or none, the previous set kept whole on a failed publish
   (Routino's `_publish` shape with a variable file set); scratch cleared.

`-DavoidMapPolling=true` is **a measured finding**: without it `OsmParser`
waits in 10 s sleeps for the input to grow (upstream's planet script runs
`osmupdate` beside it), 120 s in all for any file under 100 MB. The spike's
"128 s" for Delaware was mostly that wait; on the synthetic region the cut
took 120.1 s without the property and 0.1 s with it.

Outputs checked, never exit statuses (D-031): each phase's expected file or
directory content is digested; no `.rd5` from the linker fails the build.
The heap is `-Xmx4000m` for every Java step (the elevation converter peaked
at 1.33 GB, the cutter at 593 MB on Delaware; bigger regions are
unmeasured, and the JVM takes only what it uses).

**The record**, `<data>/brouter-segments/segments.source`: one `<slug>
<snapshot>` line per region, one `elevation <tile>` line per tile folded in,
`program <jar name>`, each `segment <file>.rd5` installed, and last
`converter: brouter-mapcreator 1`. The build is current when the record,
less its `segment` lines, equals what this run would write and every named
segment exists. A new region or snapshot, a tile added or lost, a new
BRouter jar or a bumped converter version rebuilds it. Tiles recorded are
the ones on disk when the build ran, so a tile that failed to download is
built in on the next run.

**Deferred by name when regions are unset**, like every map unit (D-035,
D-057); `brouter` and its profiles still install. A region that did not
install fails the build (the Routino rule), as does a failed phase; failures
go to the terrain ledger and its last step fails the transaction by name.

## 4. The plan

The *Terrain* block gains one line when the segments are rebuilt: "BRouter
routing files over N region(s), about X (0.2x the downloads together), with
elevation from T tile(s)". The disk check counts the output under the
prefix, and in the staging directory up to 3x the downloads together (not
measured, an allowance), the merged copy (1x, with two regions or more), and
one square's elevation scratch (49 `.hgt` files of 25,934,402 bytes each,
measured, plus the `.bef`). The JSON plan carries the same
(`brouter_regions`, `brouter_estimate`, `brouter_tiles`), regenerated into
`docs/reference/json-interface.md`.

The output factor is Delaware's 3.3 MB of `.rd5` against its 22.1 MB
download, 0.15, rounded up to 0.2 and printed as "measured on one region".

## 5. QMapShack

`hammunition maps qmapshack` registers BRouter under `[Route]` (QMapShack's
group `Route/brouter`, keys read from `CRouterBRouterSetup.cpp` at tag
`V_1.17.1`), when the tree and at least one `.rd5` are installed:

| Key | Value |
|---|---|
| `brouter\installMode` | `local` |
| `brouter\localDir` | the `brouter` tree |
| `brouter\localBRouterJar` | the one `brouter-*-all.jar` in it |
| `brouter\localSegmentsDir` | the `brouter-segments` data directory |
| `brouter\localHost` | `127.0.0.1` |
| `brouter\localBindLocalonly` | `true` |
| `brouter\localJava` | `java` on the PATH, only when absent or empty |

`localProfileDir` is left at QMapShack's default `profiles2`, relative to
`localDir`, which is the tree's own. The rest (port, threads, Java options,
the custom profile directory) is QMapShack's and untouched.

**The rule for each key** is the Routino rule made scalar: a key absent, at
QMapShack's own default, or already ours is set to ours; a `localDir` that is
anything else is the operator's own BRouter, and then no BRouter key is
touched and one line says so. QMapShack's `save()` writes every key on exit,
so an absent key cannot be told from a default one, and a default
`localDir` (`.`) means no local BRouter was ever set up. `installMode=online`
is QMapShack's default and is switched to `local`, said on stderr. When the
tree is ours, `localHost` and `localBindLocalonly` are set to loopback
whatever they held: QMapShack passes the host to BRouter only when "bind to
hostname only" is on, and otherwise BRouter listens on every interface,
which QMapShack itself warns about; the engine's rule is loopback only
(D-061). A quoted or `@`-typed value in one of these keys is not ours and
is left alone rather than refused, so BRouter never stops QMapShack from
starting.

`localJava`: QMapShack saves `java`'s path on exit, so a run before Java was
installed leaves it empty and BRouter "not installed" for good. An empty or
absent key is set to `java` on the PATH; a path already there is left.

`Route/current` (which router the Routing dock shows) is not touched:
Routino stays the default, and the operator picks BRouter in the dock.

## 6. Measured, and what is not

Measured on 2026-09-29 on the development host, in scratch, with the pinned
zip and the two pinned files: two synthetic regions (a 4×4 road and path
grid, and a track sharing one node with it) merged by `osmium merge`; a
synthetic flat 42 m GeoTIFF on the Copernicus grid warped to
`N39W076.hgt` (25,934,402 bytes) and converted to `srtm_21_05.bef`
(2.3 s); the cut, unify and link above (0.1 s, 0.6 s, 0.1 s) wrote
`W80_N35.rd5`; `RouteServer` on 127.0.0.1 only (`ss` showed the one
loopback listener), with a custom-profile directory that does not exist,
answered `trekking` and `hiking-mountain` routes across both regions with
elevation 42 m on every point.

Not measured, and owed by the bench: a QMapShack route over BRouter (no GUI
runs on the development host); QMapShack's validation of the tree
(`checkLocalBRouterInstallation` runs the jar with no arguments and reads
"BRouter 1.7.10" within 3 s); the build on a real region through the
engine; heaps and scratch on anything larger than Delaware; Java on targets
other than Parrot.

## 7. Rejected

brouter.de's segments (no checksum, weekly). The source tarball as the
profiles' artifact (ruling 1). One build per region (ruling 2). Selecting
BRouter as QMapShack's router (the operator's choice). A service or a
launcher for BRouter (QMapShack starts it, and only while it is used).
GraphHopper, OSRM, Valhalla and ORS (the spike: no offline desktop consumer,
or no archive and no clean binary route); they stay documented, not carried.
