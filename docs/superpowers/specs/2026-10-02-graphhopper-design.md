# Navigation: GraphHopper, the browser map's router

**Status:** the coordinator's brief of 2026-10-01 asks for GraphHopper as
Hammunition's optional second router, now that the browser map (D-071)
exists to consume it; the routing spike's recommendation 3 named it "the
candidate once a local tile server gives it a map". The design below is the
architectural path taken without questions; its rulings are recorded in
D-076, and the maintainer decides them at review.
**Decision record:** D-076 (D-073 to D-075 are taken on other branches).
**Evidence:** the routing spike of 2026-09-29 (GraphHopper 11.1 on
Delaware, a public example state), and the measurements of 2026-10-01 in
§7, made on the development host against the pinned jar with a synthetic
region near Montpelier, VT.

## 1. What this piece delivers

| Need | Answer |
|---|---|
| Routes drawn on the browser map | A *Route* control on `/map/`, drawing GraphHopper's answer as a line |
| Car, bike, foot and hiking routes | GraphHopper's bundled custom models `car`, `bike`, `foot`, `hike`; `hike` routes on `sac_scale`, `foot` refuses `sac_scale` 2 and above |
| Start from where you are | The route starts at the tether's `/position` when one has arrived |
| Offline, from checked data only | One graph built on the machine from the regions Hammunition already fetched and verified; the jar pinned by Maven Central's sha256 |
| Nothing new listening beyond the machine | GraphHopper on 127.0.0.1 at a port the system chooses, reached through `reference serve`'s own Host-checked route |

QMapShack cannot use GraphHopper (it has Routino and BRouter only), and
GNOME Maps' GraphHopper URL is hardcoded online, so the browser page is its
only consumer here.

## 2. Units

### `graphhopper` (binary, a single jar installed as a tree)

`graphhopper-web-11.1.jar` from Maven Central, the release the spike
measured: 47,331,301 bytes, sha256
`8462f758d9ea49edaded557cec5c687a0a24f004ec371cd4daaeb0534824ea33`, equal to
Central's `.sha256` beside it, with Central's `.sha512` also equal
(downloaded once on 2026-10-01). Central serves an `.asc` signature by key
ID `11FA9E0B0E2FBADB` (issuer fingerprint
`43BFB8BF924D7792531DC63F11FA9E0B0E2FBADB`), recorded as `signature_url` and
not verified: the engine verifies no signature, and the plan says so in the
words every declared signature gets. No distribution packages GraphHopper
(D-024: our own pin, from upstream's release). Java from the archive:
`depends: [default-jre-headless]`; the jar's manifest says `Build-Jdk
17.0.20.1` and the spike read class files at major 61, so the floor is 17.
Licence Apache-2.0.

**Ruling: a single file installed as a tree.** The binary backend's
`executable` format puts one file in `bin/` with mode 0755; a jar is not a
program the shell runs. A `tool` on the derived block (D-067's shape) is
fetched for the converter only, and `reference serve` also runs this jar.
So `executable` with `install_tree: true` and no `binaries` now installs the
file as the tree's marker under `/usr/local/share/hammunition/graphhopper/`,
mode 0644, through the same `tree_install_commands` every tree uses, so
uninstall, the effect check and `already_built` need nothing new. The
schema requires the marker to be a plain file name there.

### `graphhopper-graph` (derived, converter `graphhopper-import`)

`source: osm-regions`, `program: graphhopper`, `depends: [osm-regions,
graphhopper, osmium-tool]`, licence ODbL-1.0. One graph over every region:
two regions or more are merged first with `osmium merge`, as BRouter's
build does (D-063), because `import` reads one file and a route must cross
from one region into the next. Built as the operator in
`<builds>/graphhopper-graph/graphhopper.work/` under one lock, through
`Staging`:

1. check the jar (exactly one `graphhopper-web-*.jar` in the tree) and each
   region's file; clear the working directory;
2. `osmium merge <pbf>... -o merged.osm.pbf --overwrite` with two regions or
   more;
3. write `config.yml` (the engine's text, checked by digest after the
   operator's `sh` writes it), then `java -Xmx4000m -jar <jar> import
   config.yml`; the graph must hold `properties` and every file is digested;
4. publish every graph file under a temporary name, rename them in, remove
   files no longer built, write the record `graph.source`: all or none.

The record: a `<slug> <snapshot>` line per region, `program <jar>` (from
the plan, so a GraphHopper bumped in the same run rebuilds the graph),
`profiles car bike foot hike`, `file <name>` per graph file, last
`converter: graphhopper-import 1`. Current when the record less its `file`
lines is what this run would write and every file exists. With no regions
set the unit is deferred by name with the other map units.

**The profiles** are the engine's, never the catalog's: car with
contraction hierarchies, bike, foot and hike with landmarks, the encoded
values the spike's config listed, `import.osm.ignored_highways: ""` (now
mandatory), `prepare.min_network_size: 200`, RAM store. Elevation is off:
GraphHopper's providers fetch SRTM or CGIAR online, and none reads the
Copernicus GeoTIFFs; recorded as a gap.

### Cost, from one measurement

Delaware (22.1 MB download): import 58.5 s on a loaded 8-core host, peak
1.18 GB of memory under `-Xmx2g`, a 78 MB graph; the server up in 9 s at
316 MB resident. The plan counts the graph at 3.7x all the downloads
together (78 / 22.1 = 3.5, rounded up in case the spike's MB were MiB),
under the prefix and again in scratch while it builds, plus the merged
input with two regions or more. The memory is disclosed as one measurement;
the heap is capped at 4 GB, BRouter's figure.

## 3. Serving: `reference serve` starts it, and the page reaches it through the same server

**Ruling: `reference serve`, not a separate `maps router` command.** The
page is served there; one process means one Ctrl-C, one Host rule, and a
same-origin route request. A separate command would leave the page calling
another origin, which needs GraphHopper's CORS, which is the problem below.

When the graph is installed and current and `java` is on the PATH,
`reference serve`:

1. asks the system for a free loopback port (bind `127.0.0.1:0`, read it,
   close it);
2. in `~/.cache/hammunition/reference/graphhopper/`, writes `config.yml`
   (the same profiles, `graph.location` the link directory, one application
   connector on `127.0.0.1:<port>`, `admin_connectors: []`) and refills
   `graph/` with one symbolic link per installed graph file;
3. starts `java -Xmx4000m -jar <jar> server config.yml` as a child, its
   output to `graphhopper.log` beside the config;
4. answers `GET /map/route?point=LAT,LON&point=LAT,LON&profile=P` (after the
   Host rule) by building GraphHopper's query itself: two points checked as
   finite numbers in range, a profile from the record, plus
   `points_encoded=false&instructions=true&calc_points=true&locale=en`, and
   `ch.disable=true` for every profile but car (measured: GraphHopper
   refuses a non-CH profile otherwise). The answer is relayed with its
   status. GraphHopper not answering yet is a 503 "still starting";
   GraphHopper gone is a 503 naming its exit and its log.

**Ruling: the graph is served through links, because GraphHopper locks.**
Measured: with the graph read-only, the server refuses to start
("To avoid reading partial data we need to obtain the read lock but it
failed"), because it creates `gh.lock` in the graph directory whenever
writes are allowed, and `allow_writes` is not a configuration key in 11.1
(read from the class). A directory of links in the operator's cache, with
the files themselves root's and read-only, started, routed, and left no lock
behind on stop.

**Ruling: a router that fails never stops the page.** The books and the
map keep serving; the terminal names the exit code and the log once, and
the Route control says the router stopped. (kiwix-serve's exit still stops
the page, as D-066 rules.)

**Residual exposure, documented.** GraphHopper 11.1 sends
`Access-Control-Allow-Origin: *` on every answer (its `CORSFilter`, hardcoded,
measured), and checks no Host header. While `reference serve` runs, a page
from elsewhere in the operator's browser that finds GraphHopper's port
could ask it for routes over the operator's regions. The port is the
system's choice each run and is never linked; the operator's own page uses
the Host-checked route on `reference serve`. GraphHopper's own `/maps/` page
is reachable on that port and loads online base maps; it is never linked or
used, and the guide says so.

The child is stopped with the server (SIGTERM, 5 s, then SIGKILL), and on
Linux is asked to receive SIGTERM if `reference serve` dies first
(`PR_SET_PDEATHSIG`), since GraphHopper has no `-a PID` as kiwix-serve does.

## 4. The page

With a router, the bar gains a profile selector (car, bike, foot, hike, as
the record lists them), *Route* and *Clear*. *Route* starts picking: with a
position from the tether, one click sets the destination and the start is
the position; without, the first click sets the start. The line is drawn
from the GeoJSON `LineString` GraphHopper returns with
`points_encoded=false` (measured), the map fits it, and the bar shows the
distance, the time and the instructions in a collapsed list. A changed
profile routes the same two points again. `#route=LAT,LON;LAT,LON;PROFILE`
in the address routes on load, which a person can bookmark and the headless
test uses. Everything still loads from this server only.

## 5. Profile membership

**Ruling: installed by name, not in `navigation`.** The graph is 3.7x the
downloads, the largest per-region factor of any converter in the profile
(Navit 0.9x, Garmin 0.85x, Routino 0.67x, vector tiles 0.91x, BRouter 0.2x);
the import took 1.2 GB of memory on Delaware and is unmeasured on anything
larger; and the profile already carries three offline routers (Routino,
BRouter, CoMaps). Its one consumer is the browser page. `hammunition install
graphhopper-graph` brings `graphhopper` with it.

## 6. What else changes

- `update`'s rebuild command names `graphhopper-graph` when the regions or
  `graphhopper` are behind.
- The disk refusal counts the graph with the other map parts.
- The guide's section 16 gains *Routes on the browser map*, and its routing
  material says what each of Routino, BRouter and GraphHopper is for; the
  disk table gains the graph; cli.md, the CHANGELOG, D-076, CLAUDE.md's row
  and counts, the package pages.
- No JSON document changes: `reference serve` has none, and the plan's
  steps carry the disclosure.

## 7. Measured on 2026-10-01, and owed

On the development host, with the archive's OpenJDK 25 and osmium, against
the pinned jar in a scratch directory, over a synthetic 20 by 20 grid of
roads near Montpelier, VT with one `sac_scale=mountain_hiking` path: the
import (2.8 s, 198 MB); the server on 127.0.0.1 only (`ss`), up from a
read-only graph through links, 260 MB resident; `/health` OK; `/route` with
`points_encoded=false` returning a GeoJSON `LineString` and instructions;
`foot` going round the path (4.5 km) and `hike` taking it (4.1 km); `ch.disable`
needed for every profile but car; `admin_connectors: []` accepted; CORS `*`.

**Owed by the bench:** a real region through `hammunition install
graphhopper-graph`, with its time, memory and scratch; the Route control in
a desktop browser with a real receiver's position; Java on the targets other
than Parrot.
