# Navigation, phone maps: the laptop makes the team's phone maps

**Status:** design approved by the maintainer's controller on 2026-09-29, on
the spike report measured the same day; this document is written for the
record and for the implementation plan.
**Decision record:** D-067, written with the implementation. It extends D-057
(regions are station data; derived data by a converter enum) and D-061 (the
converters run as the operator through one `Staging`), and takes one pin under
D-024's shape.
**Origin:** the spike "the laptop as the map factory for the team's phones"
(2026-09-29), measured on the development host in a rootless container built
from `parrotsec/core`, on Geofabrik's Delaware extract (22,139,742 bytes).
No maintainer region was read.

## 1. What this piece delivers

| Need | Answer | Measured (Delaware, 22 MB) |
|---|---|---|
| A vector map an Android app can read offline | **Mapsforge `.map`** per region, from the archive's `osmosis` 0.49.2 with `libmapsforge-java` 0.20.0's map writer | 3:38 wall, 1.04 GB peak with `-Xmx2g`, `type=hd`, 17,127,551 bytes, file version 3, offline |
| Points of interest to search for on the phone | **Mapsforge `.poi`** per region, the same osmosis with `mapsforge-poi-writer` 0.25.0 from Maven Central | 0:23, 0.47 GB, 4,546,560 bytes, 22,785 POIs, offline |
| A Garmin handheld or an app that reads `.img` | the `osm-garmin` map D-061 already builds | nothing new |
| Getting them onto phones with no network | `hammunition maps phone`: copies them to one directory with a `SHA256SUMS` and prints the ways across | nothing transferred by the engine |

## 2. Units

### `mapsforge-map` (derived, converter `mapsforge-map`)

One Mapsforge map per region from the region's installed `.osm.pbf`. Debian's
`/usr/bin/osmosis` does not load the packaged writer (its classworlds file
loads `/usr/share/osmosis/*.jar`, and the writer is in `/usr/share/java/`:
"Task type mapfile-writer doesn't exist"), so the engine runs
`java -Xmx2g -Djava.io.tmpdir=<work> -cp <classpath>
org.openstreetmap.osmosis.core.Osmosis -q --rbf file=<pbf> --mapfile-writer
file=<work>/<slug>.map type=hd`, with the classpath the spike measured:
every `/usr/share/osmosis/*.jar` and 23 named jars in `/usr/share/java/`. No
system file is changed. `java.io.tmpdir` points into the working directory so
the writer's `hd` scratch lands in staging, is counted, and is cleared, not in
`/tmp`. Depends: `osm-regions`, `osmosis`, `libmapsforge-java` (Java arrives
through osmosis's own dependency on `default-jre-headless`, as `mkgmap`'s
does).

### `mapsforge-poi` (derived, converter `mapsforge-poi`, one pinned tool)

One POI file per region. The writer is not packaged (Debian's
`mapsforge-poi` jar holds only the storage classes). Maven Central's
`mapsforge-poi-writer-0.25.0-jar-with-dependencies.jar`, 18,827,962 bytes,
is pinned by a sha256 measured for this piece,
`85dd23488511f51a710139dffc8c622d184ea93e817c4ec27dde1c222b7432a7`, which
matches Central's own `.sha256`. Its `.asc` (key ID `B51D6498DA0031B6`) is
recorded and not verified; the fetch step says so in the words every other
declared-but-unverified signature gets. The pin is carried on the derived
block as a new optional field, `tool`, required for this converter and
refused for every other: the catalog supplies a URL and a digest, the engine
owns the command line.

The jar is fetched into the shared cache and verified, then installed at
`<prefix>/share/hammunition/mapsforge-poi/<jar>` (0644, re-verified on the
way in); `uninstall` removes that directory with the unit's data. The run is
`java -Xmx2g -Djava.io.tmpdir=<work> -Dorg.sqlite.tmpdir=<work> -cp
<osmosis jars>:<8 named jars>:<the pinned jar> org.openstreetmap.osmosis.core.Osmosis
-q --rbf file=<pbf> --poi-writer file=<work>/<slug>.poi`. The jar bundles
sqlite-jdbc 3.43.0, which unpacks a native library to its temporary
directory at run time; both properties put that in the working directory.

The spike's summary gave `c132d97d…4b68` as the poi-writer's sha256. Its own
saved `.sha256` files say that digest is the **map-writer** jar's; the
download made for this piece hashed to `85dd2348…32a7` and matched Central's
file for the poi-writer. The pin is the measured one.

### Shared by both

Each region: **convert** as the operator in `<staging>/<slug>.work/` under
its lock (D-061's `Staging`), then **install** into
`<prefix>/share/hammunition/data/<unit>/<slug>.{map,poi}` re-verified, with a
`.source` sidecar (`<snapshot>\nconverter: mapsforge-map 1`, or
`mapsforge-poi 1 <first 12 of the jar's sha256>` so a new pin rebuilds). The
effect is checked, not the exit status: the output exists, is non-empty, and
starts with its format's magic (`mapsforge binary OSM`, `SQLite format 3`),
read by the operator's own `head -c`. A region already built from the same
snapshot by the same converter is skipped; a region dropped from station
config has its file removed as its own step; a region that did not install
is not converted; one that fails is recorded in a phone ledger and the run's
last step fails by name. With no regions set both units are deferred by name
(D-057's rule; no new code).

The classpath is resolved when the conversion runs, after apt: a jar missing
from it fails the region naming the jar and the packages that install it. It is
not resolved at plan time, where on a fresh machine none of it exists yet.

### Disk and time

Output factors, measured on one region: `.map` 0.78× the download, `.poi`
0.21×. Scratch: the kernel's count of blocks written by each run (GNU time's
file-system outputs) is 318 MB for the map run and 9.4 MB for the POI run,
output included, which is 14.4× and 0.43× the download. A temporary file
deleted before it reached disk would not add to that count, so it is the best
measurement available, not a bound; the plan allows **15×** and **0.5×** and
says "measured on one region". The disk check counts them with piece 1's and
piece 2's needs.

## 3. `hammunition maps phone`

Unprivileged, refused as root. Reads
`/usr/local/share/hammunition/data/{mapsforge-map,mapsforge-poi,osm-garmin}/`
for `*.map`, `*.poi`, `*.img`, copies each into
`~/.local/share/hammunition/phone/` as `<slug>.<ext>`, hashing the source as
it copies and the copy after, and writes `SHA256SUMS` in `sha256sum -c`
format. A copy whose hash already matches is left alone. A file of ours
(`.map`, `.poi`, `.img` at the top of that directory) whose region is gone is
removed; nothing else in the directory is touched. Refused before copying,
by name, when the directory's file system has not got room. Nothing found
installed is not an error: it says which units to install, exit 0.

Then it prints the routes, filled in with the directory:

1. **Laptop hotspot and a web server bound to the hotspot's address.**
   `nmcli device wifi hotspot ...` (NetworkManager's shared mode gives the
   laptop 10.42.0.1 unless configured otherwise), then
   `python3 -m http.server 8000 --bind 10.42.0.1 --directory <dir>`. Bound to
   that one address so the files are served on the hotspot link and not on
   any other network the laptop is joined to; never without `--bind`, whose
   default is every interface. A loopback line (`--bind 127.0.0.1`) is given
   to check the listing on the laptop first. Nothing to install; every phone
   has a browser; many phones at once; plain HTTP on a local link, so the
   `SHA256SUMS` is served beside the files.
2. **USB (MTP).** On KDE, `kio-extras` (already installed with Plasma):
   Dolphin shows the phone once it is set to "File transfer". Elsewhere,
   `gvfs-backends`, `jmtpfs` or `mtp-tools`.
3. **`adb`, opt-in.** Package `adb`, which brings `android-udev-rules`, a
   system modification. The phone needs Developer options and USB debugging.
4. **KDE Connect, opt-in.** Package `kdeconnect`. The phone needs the KDE
   Connect app, installed while it had internet, and pairing.

The engine transfers nothing. Which apps read the files is quoted from their
documentation only (Cruiser, Locus Map, OruxMaps, c:geo for Mapsforge; a
Garmin handheld or OruxMaps for `.img`), and none has been loaded on a phone.

`--json` prints one `phone` document: the directory, each staged file (unit,
name, size, sha256, whether it was copied or already current, the removed
names) and the routes as data (D-059).

## 4. Profile

A new flat profile, `phone-maps` (post-1.0): `osm-regions`, `mapsforge-map`,
`mapsforge-poi`. Not in `navigation`: that profile is the laptop's own
navigator, and every member of a profile is built for every region: at the
measured rate a 1.3 GB state's map would take hours for phones the operator
may not have. Profiles overlap by design (D-003), so an operator who wants
both installs both. `osm-garmin` stays in `navigation`; the command stages
its `.img` when it is installed.

## 5. Not carried, with the route

- **OsmAnd `.obf`.** The best single phone file (map, routing, address, POI:
  3:40, 3.1 GB, 50 MB on Delaware), but its generator is a 152 MB nightly
  replaced daily with no checksum, signature or tag. Route: build
  OsmAnd-tools from a source commit under D-024; not attempted.
- **Organic Maps and CoMaps `.mwm`.** The generator must match the app
  release and needs the planet's coastline for any coastal region. Route: the
  publishers' own `.mwm` files, checked by their per-file hashes (BLAKE3-72,
  SHA-1), which D-069 handles.
- **PocketMaps.** Measured possible (GraphHopper 0.13.0 plus a `.map`), not
  carried: the engine is from 2019 and the app has had no commit since
  2024-10.
- **Transportr.** Online transit queries only; nothing to build.

## 6. Not measured

- Any file loaded on a real phone, in any app. The bench owes it.
- The engine's own converters on a real osmosis: `osmosis` and
  `libmapsforge-java` are not installed on the development host, and this
  piece installs nothing there. Tests run the converters against a fake
  `java` that records its argv.
- The factors on more than one region, and a region larger than Delaware.
- Which Android apps read Mapsforge files, beyond their documentation.
