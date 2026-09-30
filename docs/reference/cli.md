<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# CLI reference

The `hammunition` command, at **v0.7.0 (alpha)**. Six backends are
implemented: **apt**, **source**, **git**, **binary**, **venv** (per-user
virtualenvs, hash-pinned end to end with `pip --require-hashes`) and **node**
(Node.js applications from a verified archive, D-037 — Node only ever from
the distribution's `nodejs`, refused at plan time when absent or too old, and
the registry fetch disclosed in the plan). pipx and CPAN re-measured to zero
users and left the 1.0 list (D-014 amendment, 2026-08-30); a package
declaring one is still **refused by name**. The
install/configure/remove cycle is VM-verified on Parrot, Kali and Debian 13
(`docs/reference/vm-verification-parrot.md` and siblings).

The source backend is the expensive half of the parity target: **57 of AHRL's
95 units cannot be satisfied by apt**, and 35 of those are source builds from
bundled tarballs.

## Installing the engine

A git clone is the supported install. The wheel carries the engine; the catalog
is a separate tree, and the CLI finds `catalog/` by walking up from its own
location, so running it from a checkout needs no configuration.

```
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
scripts/path-link.sh "$PWD"
hammunition status
```

`scripts/path-link.sh` is what `./bootstrap.sh` runs to put `hammunition`
on the PATH: it links `~/.local/bin/hammunition` to this checkout's
`.venv/bin/hammunition`, and the rules it follows are under `doctor` below.
Every example on this page is written `hammunition ...`. Where the shell
says `command not found` (bootstrap has not run, `~/.local/bin` is not on
the PATH until your next login, or the link was refused), run the checkout's
`.venv/bin/hammunition` by its full path, e.g.
`~/src/Hammunition/.venv/bin/hammunition status`.
`docs/getting-started/install.md` covers each case.

Override the catalog location with `--catalog DIR` or `HAMMUNITION_CATALOG`.
A directory with no `packages/` inside it is an error rather than an empty
catalog, because an empty catalog makes `list` print nothing and look like an
answer.

## Global flags

`--version` prints the engine version and exits. `--catalog DIR` points at a
catalog other than the checkout's own.

`--json`, before or after the verb, prints one JSON document on stdout instead
of text, for a front end to read; diagnostics go to stderr and the exit code is
unchanged. Every document, and which commands have one, is in
[json-interface.md](json-interface.md), generated from the code (**D-059**).
`install` and `uninstall` accept it only with `--dry-run`: a real install is
never driven through JSON. A command with no JSON form refuses it and runs
nothing.

No long option is accepted abbreviated, with or without `--json`:
`--dry` is `unrecognized arguments`, never `--dry-run` (**D-059**). A CLI
that guards installs and consent gates behind exact flags does not guess
which one was meant.

## Verbs

### `hammunition status`

What this machine is, what the catalog holds, and what has been done here.

```
Target: Debian GNU/Linux 13 (trixie) (ID=debian, version=13, arch=x86_64)
Debian family: yes
Catalog: /home/op/Hammunition/catalog
  58 packages, 56 of which resolve on this target
  4 profiles
Transaction log: /home/op/.local/state/hammunition/transactions.jsonl
  no transactions recorded
```

The target line reports what `/etc/os-release` said, not what we concluded from
it. A system that declares no `ID` is an error, never a guess — see
`docs/DESIGN.md` §8.

With `--json`, prints a `status` document
([json-interface.md](json-interface.md)): the same target, catalog and log,
and every unit a transaction here has named. A front end derives which
profiles those units belong to from `list --json`.

### `hammunition update [NAME...] [--user NAME] [--upstream]`

Installed versus the catalog, as a report. Nothing runs, nothing is fetched,
and no network is used (**D-053**). With no names it compares every unit
the transaction log has ever named here; with names it resolves them the
way `install` does, profiles included, and compares those.

```
Comparing the 171 unit(s) the transaction log has ever named here.
Target: Parrot Security 7.3 (echo) (ID=parrot, version=7.3, arch=x86_64)
Units (171):
  a2d                     up to date             a2d 2.0.5-2
  acarsdec                behind the pin         on disk, but not attributed at ref v4.6: built at an earlier pin, or never verified here; `install acarsdec` rebuilds
  artemis                 re-checked on install  pip resolves the venv on every install; nothing to compare offline
  libacars                unknown                declares no binaries and no tree marker, so nothing on disk can be checked
  mshv                    manual                 Upstream posts numbered zips; re-pin by hand. (more in the manifest)
  …
145 up to date, 0 with a different apt candidate, 17 behind the catalog's pin, 0 not installed, 2 unknown, 4 re-checked on install, 3 manual.
apt lists: last refreshed 2026-09-12 06:38 EDT (`sudo apt-get update` refreshes them; this report does not)

To rebuild at the catalog's pin:
  $ hammunition install coil64 cwwav flaa … dumpvdl2

Upstream was not consulted: 27 unit(s) declare a probe that would ask GitHub, PyPI or a version file. …

Nothing above was executed.
```

Each row is one of seven states, and each state is a comparison against a
fact the engine already has:

| State | Which units | What it compared |
|---|---|---|
| `up to date` | apt units; built units | Every apt package installed at apt's candidate; or the build on disk and attributed by the log at the catalog's pin (**D-051**); or a vendor `.deb` this engine installed (#67) |
| `candidate differs` | apt units | An installed version that is not apt's candidate, both printed. The exact `apt-get install --only-upgrade --no-remove` command follows, never run: apt decides, and it never removes or downgrades through that command |
| `behind the pin` | built units; vendor `.deb`s | The effect is on disk but the log does not attribute it at the current pin: built at an earlier pin, or never verified here. `install NAME` rebuilds, and the command is printed |
| `not installed` | any | An apt package missing, or nothing declared is on disk |
| `unknown` | built units | The manifest declares no `binaries` and no tree marker, so there is nothing to check; the same units **D-051** cannot decide |
| `re-checked on install` | venv and node units | pip and npm resolve on every install; there is nothing to compare offline |
| `manual` | strategy `manual` | The first sentence of the manifest's cadence hint |

The apt comparison is against the archive **as the local lists describe
it**, and the report says when those lists were last fetched. It does not
refresh them: a report that ran `apt-get update` would be changing the
machine, and a laptop that last updated before a trip is told which day it
is comparing against.

Without `--upstream` it does not ask upstream. Twenty-seven of this
laptop's units declare a GitHub, PyPI or version-file probe; whether the
catalog's *pin* is behind upstream is a question about the catalog, answered
over the network, and that is what the flag adds:

```
$ hammunition update --upstream
…
Upstream (25 asked):
  ais-catcher         current          catalog 0.70  upstream v0.70  (latest release of jvde-github/AIS-catcher)
  hamclock-next       newer upstream   catalog 1.5  upstream v1.6  (latest release of k4drw/hamclock-next)
  linbpq              newer upstream   catalog 25.39  upstream 25.40  (highest of 112 tag(s) at https://github.com/g8bpq/LinBPQ)
  yaac                current          catalog 1.0-beta230(03-Sep-2026)  upstream 1.0-beta230(03-Sep-2026)  (label at …, compared verbatim)
  …
22 current, 3 with a newer upstream, 0 differing in a way the numbers do not order, 0 unanswered.
A newer upstream is a catalog question: re-pin the manifest, measure the build, then
`hammunition install hamclock-next linbpq openhamclock` on a machine rebuilds at the new pin.
Answers came from GitHub, git hosts, PyPI or a version file; nothing was downloaded or written.
```

Each probe method asks one place: `github_release` reads the latest
release's tag from GitHub's API (a `GITHUB_TOKEN` in the environment is sent
there and nowhere else, for the rate limit); `github_tags` lists the tags
with `git ls-remote`, which needs no token on any host, and takes the highest
by its numeric parts; `pypi` reads the project's JSON; `label_file` fetches
the one-line label and compares it verbatim. The repository comes from the
probe's `repo`, else the git block, else a GitHub source URL. *Newer
upstream* is said only when the numbers order that way; anything else the
numbers cannot order is *differs*, with both versions shown. A probe that
cannot be answered (a timeout, a 404, nothing derivable) is an *unanswered*
row, never a crash. `apt_policy` and `binary_version` are not upstream
questions and are not asked.

Measured on the field laptop, 25 probes answered in 7.5 s, none
unanswered, and three pins found behind upstream the first time it ran.

For `osm-regions`, every installed region's `.source` sidecar is compared
to the pinned snapshot the station's own freshness mode would resolve to
*today* — the same one-period-back fallback `resolve()` itself uses when
this year's or this month's file is not yet pinned — never the newest pin
of any snapshot: that reported a yearly install at `260101` behind a
`260901` pin forever, since a yearly install never resolves to a
monthly-shaped snapshot and so never clears it. Offline, like the rest of
this report (D-053). The row is a count, never a region name or path — the
same reason `station show` prints a count (D-057; a region list says where
somebody lives or travels): `2 regions installed; 1 behind the pin (newer
map data pinned: 260101)`. Nothing installed is `not installed`; nothing
behind is `up to date`. `hammunition install osm-regions osm-navit` (the
footer's own command, since `install osm-regions` alone never reconverts
the derived maps) fetches and converts the newer file.

For `dem-copernicus` the row is a count, never a tile name, because a tile
name is a latitude and longitude: `43 terrain tile(s) installed; a tile
changes only when the publisher's tile list does`, or `no terrain tiles
installed`. Regions whose records say Copernicus publishes no tile for any
of their squares are counted on the end, again without a name: `; 1
region(s) with no published tile at Copernicus GLO-30 (sea, or land it does
not release)`. When `osm-regions` is behind, the footer's command also names
`osm-garmin` and `osm-routino` if they are installed, since they are built
from the same regions.

With `--json`, prints an `update` document
([json-interface.md](json-interface.md)) with the same rows, counts and
commands. It keeps the text's count-only rule: `osm-regions` is a count
there too, never a region name.

### `hammunition maps regions [FILTER]`

Every region path Geofabrik's region index names, one per line, sorted.
`FILTER` is an optional case-insensitive substring; with none, every region
prints. The index (`index-v1-nogeom.json`, 0.51 MB, measured live
2026-09-28: 555 regions — smaller than `index-v1.json`'s 3.79 MB for the
same `properties.urls.pbf` shape) is fetched only when this command runs —
network on request, the same as `update --upstream`, never as a side
effect of any other command.

```
$ hammunition maps regions vermont
north-america/us/vermont
```

A region path here is what `hammunition station set --map-regions` takes,
comma-separated, and what `catalog/data/geofabrik-pins.yaml` pins. A
network failure (unreachable, a non-2xx response) is a named error and a
non-zero exit; nothing is downloaded or written.

With `--json`, prints a `regions` document
([json-interface.md](json-interface.md)): the filter and the matching region
paths. It is Geofabrik's list, nothing of yours.

### `hammunition maps qmapshack [--configure-only]`

What the `qmapshack-offline` launcher runs (**D-061**). It adds
Hammunition's map, elevation and routing directories to QMapShack's own
settings, `$XDG_CONFIG_HOME/QLandkarte/QMapShack.conf` (by default
`~/.config/QLandkarte/QMapShack.conf`), then starts `qmapshack`. The keys
are `mapPath` (the Garmin maps and the contour map) and `demPaths` (the
elevation) under `[Canvas]`, and `Route/routino/paths` (the Routino
database) under `[Route]`: the names read from QMapShack 1.17.1's binary,
the groups measured on the field laptop (2026-09-29). An earlier version
wrote the two lists under `[General]`, which QMapShack ignores; its own
directories are taken out of those two `[General]` keys, a key left empty is
removed, and any other value there stays. Each
directory is added only if absent. Every value already there is kept in its
place, and nothing else in the file changes. A key holding `@Invalid()`,
which is how Qt writes an empty list, counts as empty. A new file is
created mode 0600. `--configure-only` edits and does not start QMapShack.

It also sets `routino\database=0` under `[Route]` when that key is absent
or negative, and leaves a value of 0 or more alone, since that is a choice
made in QMapShack. The key is the index of the database selected in the
Routing dock's *Database* list. Measured on the field laptop on 2026-09-29:
with `-1` there, QMapShack loaded the `hammunition` database and selected
nothing, and routing gave up without a message. QMapShack writes the index
back when it exits, so a `-1` stays until something changes it.

It refuses, exit 1, changing nothing and starting nothing:

- under root, whose settings are not the operator's;
- when the file holds a line that is neither a `[section]`, a comment nor
  `key=value`;
- when one of those keys holds a quoted value or any other `@`-typed one;
- when the file is a symbolic link, not a regular file, or not UTF-8.

It prints a line to stderr for each kind of change it made: the
directories, and the database selection. A missing
`qmapshack` is a named error, exit 1, after the edit. There is no `--json`
form, because it replaces itself with a GUI (D-059).

### `hammunition maps gps-tether [--gpsd HOST[:PORT]] [--port N]`

What the `gps-tether` launcher runs (**D-061**). It watches gpsd's JSON, as
`xgps` and Navit do, and writes `$GPRMC` and `$GPGGA` for every position
with a 2D or 3D fix. It serves them on **127.0.0.1 port 10110 only**, for
QMapShack's *Realtime → Add source → GPS TCP/IP* and any other NMEA client, and prints
the host and port to enter:

```
Serving gpsd's position as NMEA on 127.0.0.1 port 10110, to this machine only.
In QMapShack: Realtime, Add source, GPS TCP/IP; host 127.0.0.1, port 10110.
Reading gpsd at 127.0.0.1 port 2947. Any number of NMEA programs may connect at once.
Options: --gpsd HOST[:PORT] for a gpsd on another machine, --port N if 10110 is taken.
Ctrl-C stops it. Navit reads gpsd directly and needs none of this.
```

| Option | Default | What it does |
|---|---|---|
| `--gpsd HOST[:PORT]` | `127.0.0.1:2947` | The gpsd to read: a host name or address, port 2947 when none is given. An IPv6 address goes in brackets (`[::1]`, `[2001:db8::7]:2947`); a bare one, an unclosed bracket, an empty host or a port outside 1 to 65535 is refused by name. |
| `--port N` | `10110` | The port to serve on, still on 127.0.0.1 only. 1024 to 65535; below 1024 (only root may listen there, and the tether refuses root) and above 65535 are refused by name, and so is anything that is not a number. |

Neither option widens the bind: the feed is a position without
authentication, so another machine reaches it through
`ssh -L 10110:127.0.0.1:10110 <laptop>`, never a wider listener.

Any number of clients may connect at once, and each receives every
sentence. One gpsd connection is opened when the first client connects,
shared while any is connected, and closed when the last one leaves, so
every client gets the same bytes and gpsd is not watched while nobody
listens; if gpsd closes it, every client is closed and may reconnect. A
client that has already gone is noticed before the next is counted. Sends
never block: a client with more than 64 KiB waiting is dropped alone, and
the others keep receiving. A field gpsd did not give is an empty field,
except the time: with none from gpsd, the system clock in UTC is used.
Altitude is given on a 3D fix only. Satellites and HDOP come from gpsd's
latest `SKY`. On stderr it prints a line when a client connects, goes or
is dropped, with how many are connected; when gpsd cannot be reached or
closes the connection; and once when no position with a fix has arrived in
10 s.

It runs in the foreground until Ctrl-C (exit 0), closing every client and
the gpsd connection; nothing is installed as a service, and nothing is
executed. It refuses root, exit 1. A refused option is exit 1 with nothing
opened. A port already in use is a named error, exit 1. There is no
`--json` form, because it is a server, not a document (D-059): `--json`
with any options gives the same one error document. The setups these
options are for (a gpsd on a Pi or a phone, a Bluetooth or serial
receiver, a rig's built-in GPS, a second machine) are in
`docs/guides/offline-navigation.md`, section 12.

### `hammunition list [all|packages|profiles]`

Everything in the catalog, with each package's install method **on this
machine**. A package that does not resolve here says `unsupported here` rather
than being hidden; a package with a recorded `broken` or `retired` status is
flagged with it.

With `--json`, prints a `catalog` document
([json-interface.md](json-interface.md)): every profile and package it
lists, with each package's method on this machine.

### `hammunition show PROFILE`

A profile's documentation, its package list, and — for a gated profile — the
full consent disclosure, printed without installing anything. This is how an
operator reads a disclosure before deciding, rather than while being asked.

With `--json`, prints a `profile` document
([json-interface.md](json-interface.md)), the disclosure included. Under
`--json` only, `show` also accepts a unit's name and prints a `unit`
document carrying its manifest; the text `show` still describes profiles
only.

### `hammunition install NAME... [--dry-run] [--yes] [--no-refresh] [--user NAME] [--callsign CALL] [--grid-square LOC] [--node-alias NAME]`

**A re-run rebuilds nothing it has already built** (**D-051**): a source, git
or prebuilt-archive unit whose binaries are on the machine *and* whose build
the transaction log attributes to this engine at the manifest's current pin
reads `already installed`, and only its launcher and config steps are
planned. A build whose transaction never verified -- it failed after the
build steps -- is rebuilt, because nothing confirmed it.

Names may be packages or profiles, mixed freely.

| Flag | Effect |
|---|---|
| `--dry-run` | Resolve everything, print exactly what would run, change nothing |
| `--yes` | Skip the confirmation. **Does not satisfy a consent gate** (D-021). Also suppresses the station prompt |
| `--no-refresh` | Skip the `apt-get update` that otherwise opens every transaction with apt work (**D-044**). For a local mirror, or a station with no uplink. `--refresh` is the default and still parses |
| `--user NAME` | Who to add to groups. Defaults to `$SUDO_USER`, then `$USER` |
| `--callsign CALL` | Station callsign for this run. Overrides the saved value |
| `--grid-square LOC` | Maidenhead locator, four or six characters |
| `--node-alias NAME` | Short packet node alias, up to six characters |

**Offline data (D-049).** A unit whose `install` method is `data` — a map
tileset, a Wikipedia ZIM, the DX-cluster `cty.dat` — is not software: the
engine fetches and verifies its files like any other download and puts them
under `<prefix>/share/hammunition/data/<name>/`, executing nothing. The plan
prints, before the confirmation, every artifact's size and URL, the unit's
licence and where it is stated, and the install directory, under the heading
*Offline data that will be downloaded and installed*. `uninstall` removes
the directory whole; it is namespaced, so it can only be ours.

**Map regions (D-057).** `osm-regions` and `osm-navit` take their regions
from station config (`station set --map-regions`, below), so before the
plan prints it asks Geofabrik which dated file each region resolves to and
how large it is, and discloses them under *Map regions, from station
config*:

```
Map regions, from station config (D-057):
  will be downloaded and installed:
    north-america/us/vermont        260101    44.4 MB  sha256, pinned by Hammunition
    north-america/us/new-hampshire  260101    68.1 MB  sha256, pinned by Hammunition
  will be converted for Navit (map sizes an estimate, measured on three regions, scratch on one):
    north-america/us/vermont        260101  about 40.0 MB
    north-america/us/new-hampshire  260101  about 61.3 MB
      licence: ODbL-1.0, stated at https://www.openstreetmap.org/copyright
      download total: 0.11 GB; about 0.21 GB of disk with Navit's maps (estimate, measured on three regions, scratch on one)
      installs under <prefix>/share/hammunition/data/
```

Each region line is the region, the snapshot (`YYMMDD`), the size, and how
the download is verified: **`sha256, pinned by Hammunition`** when the
region and snapshot have a row in `catalog/data/geofabrik-pins.yaml`,
otherwise **`MD5 from Geofabrik only; not pinned`**. `--yes` does not change
it. A region already installed at its snapshot is listed under *already
installed, current* and not downloaded again; one that could not be checked
(no network, Geofabrik down) but is installed is kept as it is, with a line
saying so and why. The commands section shows each fetch, each `maptool`
conversion (run as the operator in `~/.cache/hammunition/build/osm-navit/`,
with its output and scratch estimates), each install into the prefix, the
removal of any region no longer in station config, and Navit's
configuration written last.

It refuses at plan time, exit 2, changing nothing, when a region cannot be
resolved and is not already installed (named, with `maps regions` as the
way to check it), when a region that is about to be fetched — pinned or
not — cannot be reached (a pinned region resolves from the pin list with
no network at all, so this is checked explicitly rather than discovered
mid-transaction after apt has already run; an already-installed region is
never probed), when `/etc/navit/navit.xml` is missing and navit is not
in the transaction, and when a file system is short of the estimated space
(the download in the cache and the prefix, the converted map at 0.9× and
maptool's scratch at 2× the download; the map factor measured on three
regions — 0.77× on a country-sized one, 0.874× and 0.856× on two
US-state-sized ones — and the scratch factor on one;
the refusal prints the estimate and what is free). With no regions set the
two units are deferred by name and the rest installs (**D-035**). A region
that fails during the run — a download that does not verify, a conversion
that writes nothing — does not stop the others; the run ends exit 1 naming
every region that did not install.

**Terrain and QMapShack's maps (D-061).** When the plan holds
`dem-copernicus`, `osm-garmin`, `osm-routino` or `dem-qmapshack`, the map
section gains a *Terrain* block. Before the plan prints, each region's tiles
are read from its record (`dem-copernicus/<slug>.tiles`) or, until its
terrain is first installed, chosen from its Geofabrik outline
(`<region>.poly`), fetched again by every plan until then and said so. Each
tile not installed is resolved from its pin or, unpinned, by a `HEAD` to the
bucket for its size and ETag; a pinned tile is asked with a `HEAD` too, so
an unreachable bucket refuses the plan rather than the transaction. From the
golden test's synthetic plan:

```
  Terrain, Copernicus GLO-30 elevation (D-061):
    atlantis/oceania  2 tile(s), 2 square(s) with no published tile (sea, or land Copernicus does not release); 39.1 MB to download
    atlantis/lemuria  1 tile(s); 25.2 MB to download
    atlantis/mu       0 tile(s), 3 square(s) with no published tile (sea, or land Copernicus does not release)
    warning: no terrain available for atlantis/mu from Copernicus GLO-30; its maps still install
    (a region's tiles are read from its outline at Geofabrik, fetched again
    by every plan until its terrain is installed and its record written)
    will be downloaded (2 tile(s), 64.3 MB):
      Copernicus_DSM_COG_10_N00_00_E000_00_DEM    39.1 MB  sha256, pinned by Hammunition
      Copernicus_DSM_COG_10_S01_00_W001_00_DEM    25.2 MB  MD5 from the publisher's object metadata; not pinned by Hammunition
    already installed: 1 tile(s)
      licence: Copernicus DEM licence, stated at https://spacedata.copernicus.eu/
  Built for QMapShack (sizes an estimate, measured on one region):
    Garmin map  atlantis/oceania  260101  about 44.6 MB (0.85x the download)
    Routino database over 2 region(s)  about 42.2 MB (0.67x the downloads together)
    contours for 2 tile(s)  about 11.0 MB, with up to 98.0 MB of scratch at a time
      about 0.16 GB of disk for terrain and QMapShack's maps (measured on one region)
```

Each tile line ends with how it is verified: **`sha256, pinned by
Hammunition`** when it has a row in
`catalog/data/copernicus-glo30-pins.yaml`, otherwise **`MD5 from the
publisher's object metadata; not pinned by Hammunition`**. The pin file
ships empty, so today every tile gets the second.

A square with no published tile is counted as such and never called sea:
the carried list cannot tell open sea from land Copernicus does not release.
A region with no published tile at all gets the `warning:` line, fetches
nothing and does not fail the run; its maps still install (D-061).

The commands section shows each tile's fetch (all fetches first, as every
download is), each install, each region's record, each Garmin build and the
Routino build (as the operator, in `~/.cache/hammunition/build/osm-garmin/`
and `.../osm-routino/`), each tile's contours (`.../dem-qmapshack/`), the two
virtual rasters, and a last step that fails the run by name if any of this
did not install. It refuses at plan time, exit 2, changing nothing:

- when a region's outline or a tile not installed cannot be resolved (every
  such one named together), including a tile whose ETag is not a
  single-part MD5 and an outline edge that jumps across ±180 in one segment;
- when the carried tile list is missing, empty or malformed;
- when the carried pins file (`catalog/data/copernicus-glo30-pins.yaml`)
  does not parse, has no `pins:` list, or has a row missing a key or
  carrying a malformed value or a tile pinned twice; the refusal names the
  file, and under `--json` it is one refused plan document;
- when a disk is short of piece 1's and piece 2's estimates together.

With no regions set, all four units are deferred by name with the rest of
the map data.

**Recommends, per unit (D-052).** Recommends are not suppressed globally —
that would deviate from what every target distribution does, and several ham
applications get their runtime data that way. A single manifest may opt its
own packages out with `install_recommends: false`, for the measured case
where a package's Recommends conflict with the target's desktop stack:
Debian's `morse` Recommends `pulseaudio`, which `Conflicts: pipewire-alsa`,
so on a PipeWire desktop apt would satisfy the transaction by removing the
machine's audio routing and the plan refuses it (**D-022**, issue #61). Such
a unit's packages become a second apt set, simulated with
`--no-install-recommends` and installed by a second `apt-get install`
carrying it. The plan prints the set under *apt packages installed without
Recommends*, naming the units that asked, and both apt commands appear under
*Commands*. `--no-remove` is on both: the flag buys a unit its own apt
invocation, never an exemption from **D-022**.

**Suggestion groups.** A profile may suggest one-of-several optional
companions (the packet profile's mail client is the first): the run
*detects* first — any of the group's known commands on PATH means the
system's own choice is respected and nothing is offered — and only an
interactive run without `--yes` gets the selection, every option an
open-source catalog manifest, with skip always an answer. Non-interactive
runs note the skip and never block (the D-035 shape). Nothing from a
suggestion group is ever installed silently.

**With `--json` and `--dry-run`**, prints the plan as a `plan` document
([json-interface.md](json-interface.md)): exactly what the text plan prints,
section by section. A plan that refuses is still a `plan`, with `outcome:
"refused"`, every blocker, and exit code 2. **Without `--dry-run`, `--json`
is refused** with an `error` document and nothing runs: a real install is
never driven through JSON (**D-059**). A front end runs the ordinary command
in your terminal, where sudo, every consent gate and every disclosure are
this CLI's, then reads `status --json`. The plan names your account, paths
in your home and the station's map regions, so the document is for a local
program, not for pasting into an issue. It never carries a rendered
configuration file, so the callsign in one is not in it.

### `hammunition uninstall NAME... [--dry-run] [--yes] [--user NAME]`

Removes what Hammunition itself installed, and only that (**D-004**). Names
may be packages or profiles, mixed freely.

| Flag | Effect |
|---|---|
| `--dry-run` | Resolve the removal, print exactly what would run, change nothing |
| `--yes` | Skip the confirmation |
| `--user NAME` | Whose transaction log to read. Defaults to `$SUDO_USER`, then `$USER` |

"Installed by Hammunition" is read from the transaction log, by replaying the
recorded commands that actually exited 0 — not from what a run *intended*.
Four attribution routes, each exact:

- **apt packages** — the recorded `apt-get install`/`remove` commands.
- **files under `/usr/local`** — the engine's own `install -D` commands (and
  the executable format's recorded destination). A same-named file the
  operator put there is not in the log and is never touched.
- **vendor `.deb`s** — the fetch cache names artifacts by their sha256, so
  the recorded install carries the manifest's own digest; the manifest's
  `deb_package` field names what to hand to `apt-get remove`.
- **namespaced trees and venvs** — `share/hammunition/<name>` and
  `venvs/<name>` can only be ours.
- **third-party apt repositories** — the two `install -D` commands that
  wrote `<name>.sources` and `<name>.gpg` (**D-040**). Both are removed
  and `apt-get update` runs afterwards so the lists forget the repository.
  A same-named file the log does not attribute is left in place and named.

Wrappers and desktop entries in your home are removed only after being read
back: the file must carry the engine's generated marker, or it is reported
and left. The plan partitions honestly and prints every part:

- **Removing** — attributed apt packages (one `apt-get remove`, never
  `purge`: configuration a user may have edited stays on disk).
- **Removing artifacts** — venvs, installed trees, copied binaries,
  wrappers, desktop entries — each printed with the *basis* for believing
  it is ours: `namespaced`, `log`, or `marker`.
- **Left in place** — installed, but not installed by Hammunition; or
  present but unattributed by the log. Removing it would exceed the promise.
- **Already absent** — attributed but no longer installed.

What it deliberately does not reverse, and says so in every plan:
dependencies apt pulled in (`sudo apt autoremove` clears orphans), group
memberships, and any configuration files written — all recorded in the log.
A source or git unit whose build ran a real `make install` into `/usr/local`
is refused with the gap named: there is no file manifest to reverse, and a
file sweep pretending otherwise is the shim CLAUDE.md forbids. A staged,
recorded install is the planned fix.

After the commands complete, the removal is **verified** the same way an
install is (**D-031**): apt is re-probed, every removed artifact path is
re-checked absent, and the run is only reported clean when both confirm. A
removal apt quietly declined exits 1 with `verified: false` in the log.

With `--json` and `--dry-run`, prints the removal as a `plan` document
([json-interface.md](json-interface.md)), the same shape as an install's
with `removal` filled in. Without `--dry-run`, `--json` is refused and
nothing is removed, as for `install`.

### `hammunition menus apply [--gnome] [--menu-prefix PREFIX]`

Writes the curated **Hammunition** desktop-menu layer (**D-036**, **D-050**),
generated from the catalog's own category vocabulary — one taxonomy, no
second list. Per-user and unprivileged throughout.

- **Menu-spec desktops (KDE Plasma, Xfce):** a merged `.menu` tree shaped
  like Parrot's own tool menu — *Hammunition*, then eight groups in a
  declared order, titled as activities in plain words (*Operate the
  Station*, *Digital Modes & Morse*, *Packet, Mesh & Emergency Comms*,
  *SDR & Listening*, *Satellites & Propagation*, *Antennas, Bench &
  Programming*, *RF Security & Research*, *Learn & Practise*), then one
  submenu per catalog category — 56 of them (**D-055**'s 55, plus *Navigation & Maps*), each the thing
  a person looks for (*APRS*, *Winlink Email*, *Ships (AIS)*, *SSTV, Fax &
  Amateur TV*) — titled from the vocabulary with a gloss where the tag is
  jargon (*CW (Morse)*, *Rig Control (CAT)*; **D-054**). The groups are `catalog/categories.yaml`'s `groups:` list;
  every category belongs to exactly one, and the order is a menu-spec
  `<Layout>`, not the alphabet. A ninth group, *Workstation*, is declared
  `menu: false`: git, tmux and VS Code are catalog units, not radio
  software, so they get no submenu, no generated entry, and stay where the
  desktop already puts them. A unit whose manifest says `menu_submenu`
  (GNU Radio, 21 entries) gathers everything it ships into one nested
  submenu under its first category instead of listing it inline in every
  category it carries; a generated entry shows its manifest's
  `menu_title` (*Contest logger (tlf)*) with the unit's name kept in
  `Keywords=` for the launcher's search. Every apply also brings the
  launcher entries up to their manifests as they are now (categories,
  title, comment; the wrapper path is kept), generates an entry for a
  built unit from the binaries its manifest declares and the prefix holds,
  and writes a launcher a unit gained in the catalog after it was installed
  (D-050 amendment, 2026-09-13). Each
  submenu includes the `X-Hammunition-<category>` markers every generated
  desktop entry carries **and, by `<Filename>`, the desktop entries the
  installed catalog packages ship themselves** — mapped at apply time from
  `dpkg -L` of each manifest's apt package (or `.deb` name) to the
  manifest's categories, **then checked on disk**: Parrot's `parrot-menu`
  rewrites the launcher set from an apt hook after every apt run, so an
  entry that exists is placed as shipped, one that is gone is placed by
  `parrot-<package>.desktop` when that exists, and one with neither is
  reported under the count rather than counted (#64). Whatever else
  carries the freedesktop `HamRadio` category and no manifest claimed is
  gathered at the tree's top level. The desktop's own copies of every
  entry are untouched (D-022).
  **Which root menu it merges into is decided, never guessed:**
  `--menu-prefix` wins, then the session's `$XDG_MENU_PREFIX`, then the
  root menus installed under `$XDG_CONFIG_DIRS/menus/` — exactly one
  `<prefix>applications.menu` means that one; several and no session
  variable is a refusal that names them. **Which directory the root merges
  is measured per desktop:** Xfce's garcon reads `<prefix>applications-merged/`;
  **KDE's kservice ignores the prefix and reads `applications-merged/`** —
  on the field laptop (Plasma 6, 2026-09-12) a tree written to
  `plasma-applications-merged/` produced no menu and every generated
  entry sat in *Lost & Found*. The file goes where the desktop reads, and a
  copy left in a directory it does not read is removed. On Plasma,
  `kbuildsycoca6` runs afterwards (disclosed) so the tree shows now.
- **A real `install` ends by re-applying this**, quietly, for the user who
  ran it: placement happens at apply time, and a tree applied before an
  install left 42 of 60 new entries loose under *Hammunition* on the field
  laptop. The plan discloses it before the confirmation; where no root menu
  can be decided (bare SSH) the install says so in one line and succeeds.
- **An entry for every installed radio unit (D-050).** Parrot's menu does
  this for 572 of its 671 entries, and the launcher's search is only as
  good as what has an entry. For each installed catalog unit that ships no
  desktop entry, declares no `launchers`, and has a category outside the
  hidden group, a per-user `hammunition-cli-<unit>.desktop` is generated:
  the unit's name, its manifest summary as the Comment, its categories as
  Keywords, `Terminal=true`, and the executable — the one named like the
  unit, else the package's only one. Several executables and none named
  like the unit (`rtl-sdr`: eight tools) is a guess this refuses to make;
  the summary names the unit and a `launchers` block in its manifest is
  the fix. A unit whose executables are all under `/usr/sbin` is a
  service, not an application, and is skipped with that reason. Generated
  entries and directory files from an earlier run that this run did not
  produce are removed; a launcher's `hammunition-<name>.desktop` is never
  touched.
- **GNOME:** one app-folder per visible group — *Hammunition · Station*
  and so on, since GNOME cannot nest — populated by the group's
  `X-Hammunition-<category>` markers (no app list to maintain) plus the
  placed entries under those categories unioned into its `apps` list, for
  the ones a distribution tagged some other way (Kali's `gqrx` and `chirp`
  carry `kali-radio-frequency`). Written 2026-09-12; **not yet run on a
  GNOME machine**. Applied only when `XDG_CURRENT_DESKTOP` says GNOME (or
  `--gnome` forces it), and it needs your desktop session's bus: over bare
  SSH it fails loudly rather than pretending. Lists are appended to, never
  replaced.
- **COSMIC:** unmeasured. Nothing is written for it until the Pop!_OS VM
  has been read.

### `hammunition doctor [--user NAME]`

A **read-only** health check: is this machine ready, and what is not yet set
up. It changes nothing, and it is the first thing to run on a fresh machine
or when something misbehaves — it turns the failures the engine would
otherwise hit mid-transaction into a report you read up front, each with the
one command that fixes it. Seventeen checks across four severities:

- **fail** — the engine cannot work until fixed (not a Debian-family system;
  no catalog). Exits non-zero.
- **warn** — a whole class of installs will fail or a feature is unavailable
  until fixed (no `python3-venv`, no compiler, no callsign, missing device
  group), but the engine runs and everything else works.
- **info** — a true fact that is not a problem (no ham hardware attached
  right now; udev rules not yet applied on a machine with no radios).
- **ok** — checked and healthy.

The **desktops** check is always information (**D-060**): the desktops
the session files in `/usr/share/xsessions` and `/usr/share/wayland-sessions`
(and the same under `/usr/local/share`) offer, which is what `install` decides a unit for one desktop against, and
the desktop of the session you are in, from `$XDG_CURRENT_DESKTOP`. Under
`sudo` that variable is usually gone, and the line says the session's
desktop is not known rather than guessing. A machine with no session files
(a server, a container) is reported as such. Session files that name no
desktop the catalog knows (COSMIC, Sway) are named as read, so a graphical
machine is never reported as a server. See `docs/desktops.md`.

The **time** and **hardware clock** checks (**D-058**) say what the clock
follows (the network or the GPS, with ntpd's offset), or that it follows
nothing and for how long (information under a day, a warning past one), read
with `ntpq -pn` and `ntpq -c rv` and no privilege. It warns when a GPS mode is
set but ntpd lacks the two grants `hardware apply` installs, when `gps-only`
is set with the receiver parked, and when ntpd runs on a DHCP-supplied
configuration. A machine with no battery-backed hardware clock (`/sys/class/rtc`
empty) is warned on any target, naming the fix: fit an RTC module. On a target
whose time daemon is not ntpsec the line is information naming the gap. See
`docs/guides/gps-time.md`.

The **hammunition** check (**D-059**) asks whether `hammunition` resolves on
your `PATH`, and to the checkout `doctor` is running from. `./bootstrap.sh`
puts it there as a link, `~/.local/bin/hammunition` pointing at the
checkout's `.venv/bin/hammunition`, made by `scripts/path-link.sh`: it prints
each change before making it, creates `~/.local/bin` (mode 0755) only when
it is absent, never edits a shell rc file, and never replaces a file, or a
link it did not create. The check's fix follows the same rule:

- **Not on `PATH` at all:** re-run `./bootstrap.sh`.
- **The bootstrap's link, pointing at a *different* checkout:** the one
  `ln -sfn` command that switches it, with both paths shell-quoted.
- **Something else at `~/.local/bin/hammunition`** (a pipx install, a
  wrapper): it is named with how to inspect it, and no command that would
  replace it is printed.
- **Another `hammunition` earlier on `PATH`:** that path is named; relinking
  `~/.local/bin` would not clear it, so it is not offered.

Paths are compared resolved, so in a git worktree whose `.venv` is a symlink
to another checkout's, the check names that checkout's venv. When
`~/.local/bin` is itself missing from `PATH`, the bootstrap prints the one
line to add to `~/.profile`. Remove the link with
`rm ~/.local/bin/hammunition`.

The **qmapshack** check (**D-061**) appears only when `qmapshack` is on the
`PATH` and `/usr/share/routino/translations.xml` is missing: QMapShack stops
at startup with "The specified translations XML file did not exist" until
the file is back. It is a warn, with `sudo apt-get install --reinstall
routino-common` as the fix.

The closing line counts each, and the exit code is non-zero only when
something is **blocking**. It is the natural first command after installing
from the checkout, and the one to paste when asking for help.

With `--json`, prints a `doctor` document
([json-interface.md](json-interface.md)): each check's name, severity,
detail and fix, and the counts. The exit code is the text run's. It keeps
the count-only rule the text follows: no callsign, grid square or region
name.

### `hammunition hardware list`

What is plugged in, what the catalog recognises, and what setup a device
needs — the permissions-and-udev half of the device role (**D-029**). Reads
`/sys/bus/usb/devices` directly (never `lsusb`, which may not be installed
and whose output is a screen-scrape), matches against the device catalog,
and reports three things: **recognised** devices attached (an ambiguous
identifier is flagged as a candidate, not a conclusion — **D-028**),
**unrecognised** attached devices (a prompt to contribute one), and whether
the udev rules and your access-group membership are already in place.
Detection drives nothing: it reports, and you decide (**D-020**).

### `hammunition hardware apply [--dry-run] [--yes] [--user NAME]`

Writes the whole catalog's udev rules to
`/etc/udev/rules.d/65-hammunition.rules`, reloads and triggers udev, adds
you to the device-access groups the catalog needs (`plugdev`, `dialout`),
and — since **D-056** — installs the two artefacts device power control
needs: a root-owned helper at `/usr/local/libexec/hammunition-devctl`
(`0755`) and a polkit action at
`/usr/share/polkit-1/actions/com.chiefgyk3d.hammunition.devctl.policy`
(`0644`), which is what lets `hardware park`/`wake` ask `pkexec` to run that
helper as root. See `docs/hardware/power-control.md` for what those two
files contain and what installing them means.

- **All the rules, not only attached devices' —** a udev rule is declarative
  and harmless for a device that is not present, so applying the whole set
  means a supported device works the moment you plug it in, not only if it
  happened to be attached when you ran this.
- **Idempotent.** A rules file, helper or policy file that already matches
  what would be written is a no-op, and a group you are already in is
  skipped. Re-running when nothing has changed reports "nothing to do".
- **Disclosed and verified.** Every privileged command is printed before it
  runs (`--dry-run` prints and stops); afterwards the rules file and the
  polkit artefacts are re-read against what was written and each group
  re-checked (**D-031**) — an exit code is not taken as proof. The rules file
  is refused a rule for any device whose identifier is ambiguous without a
  distinguishing product string, and each such omission is printed with why
  (`docs/reference/device-naming.md`).
- **Can refuse outright, or ask for a typed confirmation, before installing
  the helper or the policy.** Before writing either polkit artefact, `apply`
  checks whether the Python interpreter it would bake into the helper, and
  the `hammunition` package directory that helper imports, could be
  tampered with by anyone other than root. If either is writable by more
  than its own owner — world-writable, or group-writable by a group another
  account can hold — or could not even be `stat`'d, `apply` refuses
  outright — exit code `2` — because another account could then replace
  what root is about to run. If either is merely owned by one non-root
  account — the ordinary shape of a venv under `$HOME`, and this project's
  own documented install, including one group-writable only by the owner's
  own user-private group under a `0002` umask — `apply` is not refused, but it prints the path
  and asks `Proceed? [yes/no]:` once; `--yes` does not answer it (**D-021**,
  **D-056**), and anything but `yes` exits `3`.
- **Group membership applies at next login.** The command says so; log out
  and back in before expecting device access.
- **GPS time (D-058), where ntpsec is the time daemon.** Installs the two
  grants ntpd needs to read gpsd's time: a systemd drop-in,
  `/etc/systemd/system/ntpsec.service.d/hammunition-gps.conf`, with
  `AmbientCapabilities=CAP_IPC_OWNER`, and `capability ipc_owner,` added as a
  marked block to `/etc/apparmor.d/local/usr.sbin.ntpd`, with the profile
  reloaded. The plan says in so many words that CAP_IPC_OWNER bypasses
  permission checks on all System V IPC. It creates `/etc/ntpsec/ntp.d` and
  sets the first time mode (`auto`, or the mode already recorded) through the
  helper, which restarts ntpsec; when a mode is already applied and only the
  grants change, it restarts ntpsec instead. On a machine with no hardware
  clock (`/sys/class/rtc` empty) and no `fake-hwclock`, it installs
  `fake-hwclock`, disclosed as a stopgap. Each GPS time step is logged
  (`time_grants`) and read back afterwards. See `docs/guides/gps-time.md`.

### `hammunition hardware unapply [--dry-run] [--yes] [--user NAME]`

Removes the power-control helper and its polkit action — the two files
`hardware apply` installs at `/usr/local/libexec/hammunition-devctl` and
`/usr/share/polkit-1/actions/com.chiefgyk3d.hammunition.devctl.policy` — and,
if present, `/etc/udev/rules.d/66-hammunition-kept.rules`, the kept-off rules
file `park` writes to by default (**D-056**, amended 2026-09-28). Removing it
reloads udev, so every device it was holding parked wakes from the next boot
on. Nothing else is touched.

- **Not part of `uninstall`.** `uninstall` resolves the names it is given
  against the package and profile catalogs; there is no unit named
  `hardware` to give it. This is its own verb for that reason.
- **Removes only what the transaction log says this engine installed for the
  given operator**, never a path merely expected to exist and never anything
  a log entry names besides those two exact paths — a `path` the log
  contains that is not one of them is reported and skipped, not removed.
- **The udev rules file is never touched.** It is declarative, harmless for a
  device that is not attached, and removing it would take away device access
  still in use — power control is the reversible half of this feature,
  device permissions are not.
- **Disclosed and verified**, the same as `apply`: every command is printed
  before it runs (`--dry-run` prints and stops), and `rm` exiting 0 is not
  trusted — each path is re-checked for absence afterwards (**D-031**).
- **Takes GPS time back exactly (D-058)**, by content rather than by the
  log: `/etc/ntpsec/ntp.conf`'s marked lines go back byte for byte as the
  package shipped them (`dpkg --verify ntpsec` then prints nothing for it);
  `/etc/ntpsec/ntp.d/hammunition-gps.conf`, `/etc/hammunition/time.yaml` and
  the ntpsec drop-in are removed only when they start with the header
  Hammunition writes; only Hammunition's block leaves
  `/etc/apparmor.d/local/usr.sbin.ntpd`, the rest of that file stays; then
  systemd and AppArmor are reloaded and ntpsec restarted. `fake-hwclock`, if
  it was installed, stays; `sudo apt remove fake-hwclock` removes it.

Exit codes: `0` for a removal that verified absent, nothing recorded to
remove, every recorded artefact already gone, a `--dry-run`, or declining the
confirmation prompt; `1` if the operator could not be determined, a removal
command failed, or a path is still present after the run; `2` when
`ntp.conf`'s marked lines were edited by hand, refused before anything runs.

### `hammunition hardware park NAME [--until-reboot] [--dry-run]`

Detaches a catalogued, attached device and lets its port suspend — writes `0`
to its sysfs `authorized` file, the same effect as unplugging it. `NAME` is
the catalog name (`gps-receiver`), or `NAME@ADDRESS` when two of the same
kind are attached and the plain name would be a guess. Only a device whose
catalog entry carries a `power_control` block is ever offered (**D-056**);
see `docs/hardware/power-control.md` for what parking does and does not do,
and which devices carry that block today.

**Kept parked by default (D-056, amended 2026-09-28).** Alongside the sysfs
write, `park` adds two lines to `/etc/udev/rules.d/66-hammunition-kept.rules`
— a `# kept: NAME` comment, then a rule naming the device's port and
vendor/product pair; udev re-applies `authorized=0` when the device is added
— at boot, and on a replug into the same port — with nothing of
Hammunition's needing to run. A suspend/resume is not claimed: a resume is
normally not a udev `add` event. That mechanism is built; whether the device
actually comes back parked across a real reboot has not yet been measured on
hardware — see "Kept off across reboots" in `docs/hardware/power-control.md`.
`--until-reboot` adds no rule and removes any kept entry an earlier `park`
wrote for the device: it parks now and a reboot wakes it, the pre-amendment
behaviour. `wake` (below) removes the kept entry.

The privileged write goes through one polkit action,
`com.chiefgyk3d.hammunition.devctl`, `hardware apply` installs the helper it
authorises. `--dry-run` prints every write it would make, whether a kept
entry is added, and the `pkexec` call itself, then stops.

Exit codes: `0` parked and verified (or a `--dry-run`); `1` a write did not
verify, or the command otherwise failed to run; `2` unplannable — the helper
is not installed, `pkexec` is not on `PATH`, or `NAME` does not resolve to a
parkable attached device; `3` the authentication prompt was declined or
denied and nothing was changed.

### `hammunition hardware wake NAME [--dry-run]`

The reverse of `park`: writes `1` back to the device's `authorized` file so
the kernel re-enumerates it, and removes the device's kept entry from
`66-hammunition-kept.rules`, if it has one, so a later reboot does not park
it again. Same `NAME` syntax, same `--dry-run`, same exit codes as `park`.
`NAME@ADDRESS` also resolves a kept entry whose device is **not** currently
attached, so a stale entry for something already unplugged can be cleared
without plugging it back in.

### `hammunition hardware state`

Lists every catalogued device that is both attached now and parkable, and
whether each one is parked — read fresh from `/sys/bus/usb/devices` on every
call, never cached — plus any device kept parked (**D-056**) whose entry
names a port nothing answers on right now. Needs no privilege: reading
sysfs is unprivileged, only writing to it is. Always exits `0`; an empty
report is not a failure.

The table shown by the CLI adds a `kept` column next to `state`
(`parked`/`awake`), and lists devices kept-but-absent separately under "Kept
parked, not attached", with the `wake NAME@ADDRESS` command that clears each
one. The JSON the root helper prints (`hammunition-devctl state`, what the
tray applet polls) gives one object per row with `"kept": bool` alongside
`"parked"`; a kept device with nothing attached gets `"attached": false` and
`"parked": null`, since there is no sysfs node to read a live answer from.

With `--json`, prints a `hardware` document
([json-interface.md](json-interface.md)): one object per row with the same
keys the helper prints, plus any error reading the kept-off rules.

### `hammunition time`

What the clock follows now (the network, the GPS, or nothing, with how long it
has been in holdover), the time mode and whether it was ever set, whether a GPS
receiver is attached and awake, and whether ntpd can read it. Reads only:
`ntpq -pn` and `ntpq -c rv` answer any local user, so there is no prompt. On a
target whose time daemon is not ntpsec it says so and names the gap (D-058).

### `hammunition time mode MODE [--dry-run]`

`MODE` is one of `auto` (the default), `prefer-gps`, `ntp-only`, `gps-only`.
Prints every write before it happens: `/etc/hammunition/time.yaml`, the whole of
`/etc/ntpsec/ntp.d/hammunition-gps.conf`, the marked lines of
`/etc/ntpsec/ntp.conf` that move, and the `systemctl restart ntpsec` that
follows; then runs `pkexec /usr/local/libexec/hammunition-devctl time mode MODE`.
A parked receiver never feeds the clock whatever the mode says. Refused with
exit 2 when ntpsec is not installed, when the helper is not, or when `ntp.conf`
no longer has the line an edit anchors to. If ntpsec will not restart on the new
files, the helper puts the old ones back and starts ntpsec on them. Exit 3 when
the authentication prompt is dismissed.

### `hammunition station show` / `hammunition station set`

The values only you can supply — callsign, grid square, packet node alias,
and the regions to carry offline maps for. Some
manifests write configuration files templated with them: `linbpq` needs a node
callsign, AX.25 needs one in `/etc/ax25/axports`, Direwolf needs one in its
own configuration.

```
hammunition station set --callsign M0ABC --grid-square IO91wm
hammunition station show
```

| Flag | Effect |
|---|---|
| `--callsign CALL` | Station callsign |
| `--grid-square LOC` | Maidenhead locator |
| `--node-alias NAME` | Short packet node alias |
| `--map-regions R[,R…]` | Geofabrik region paths for offline maps, e.g. `north-america/us/vermont,north-america/us/new-hampshire`. Replaces the whole list. Checked for shape only (lowercase words joined by `/`); whether Geofabrik has the region is checked at plan time (**D-057**) |
| `--map-freshness MODE` | `yearly` (the default when unset), `monthly` or `latest`: which dated file each region resolves to, and so how it can be verified |

A region list says where the operator lives or travels, so `station show`
and `station set` print how many regions are set, never their names; the
install plan is the one place the text prints them, and `station show
--json` carries them for a local front end. `docs/guides/offline-navigation.md`
is the operator's walk-through.

Saved to `$XDG_CONFIG_HOME/hammunition/station.yml`, mode 0600, resolved
owner-aware so that running under `sudo` still writes to the invoking user's
home rather than root's.

**A value you have not supplied does not block an install.** The package is
installed and the file that needed the value is reported under *Will NOT
happen*, with the command that would let it be written. That is deliberate
(**D-035**): a nineteen-package profile refusing entirely because one file
needed a callsign got an operator nowhere.

**Nothing is invented.** There is no default callsign and no placeholder,
because a configuration file written with a made-up callsign would transmit
it. An interactive run offers to prompt for what the request actually needs;
`--yes`, a pipe, or a value that is already known all skip the question.

`station show --json` prints a `station` document
([json-interface.md](json-interface.md)) carrying the values themselves:
callsign, grid square, node alias, and every map region by name, because a
local front end needs them to fill in a form. It is for local programs, not
for pasting into an issue, a forum or a chat: a callsign resolves to a name
and a licence address, and a grid square or a region says where the station
is. `station set` has no JSON form.

## Launchers and menu entries

A manifest may declare `launchers` — programs that need a working directory,
a service-endpoint argument, or that simply have no `.desktop` of their own
(Java jars, run-in-place trees; 14 units measured). For each one the run
generates two per-user artifacts, unprivileged, printed like every other
step: a wrapper script in `~/.local/bin` with `{endpoint:NAME}` substituted
from the manifest's `service_endpoints` (the repointable-backend rule — a
dead upstream is fixed by editing the catalog, not launchers), and a desktop
entry in `~/.local/share/applications` whose `Categories=` are mapped from
the manifest's own category tags, `HamRadio` first (**D-036**). Entries
carry `X-Hammunition-Package` so later tooling can find its own work. The
curated per-DE submenu layer (Xfce `.menu`, GNOME app-folders, COSMIC) is
D-036's next, measured step.

## How a run is ordered

Resolution is a distinct phase that finishes before anything is executed
(**D-016**). In order:

1. **Detect the target** from `/etc/os-release`. A non-Debian-family system is
   refused here; there is no shim that makes it appear to work.
2. **Expand** the requested names — profiles into their packages, and any
   `depends` that names another manifest.
3. **Order** by `after`, which is sequencing rather than dependency. A cycle is
   reported; it does not hang.
4. **Resolve** each manifest against `(distro, version, arch)`. No matching
   install block means this target is genuinely unsupported for that package.
5. **Check what this engine can actually do** — see below.
6. **Ask apt once**, about every distro package the whole transaction needs —
   the manifests' own packages, their `depends`, and the `build_depends` of any
   source build, together. This is how a stale build dependency is caught before
   a compiler is installed rather than after `./configure` fails: glfer's
   `build_depends` name `fftw2` and `libgtk2.0-dev`, two of the four AHRL
   dependency lines **D-016** records as suspected-stale, and nothing in AHRL
   ever asked apt whether they still exist. Then apt is asked a second
   question, once, whenever anything is outstanding: whether the whole set
   installs *together*, and what the apt step would pull in (`apt-get install
   --simulate`, unprivileged, no lock) — because `apt-cache policy` knows
   that `jtdx` exists, not that installing it brings `wsjtx-data`, and knows
   that `libcurl4-openssl-dev` exists, not that this machine's `libcurl4t64`
   is from backports at a version it cannot depend on. If apt refuses because
   an installed package would be downgraded, and every such package came from
   one release, the question is asked a third time with `--target-release`
   naming it; a yes is carried into the apt command and the plan lists what
   that release supplies (**D-038**). Any other refusal is the plan's. The
   same simulate is read for what apt would **remove** (`Remv` lines): a
   package that `Breaks:` an installed one is "resolved" by apt removing
   the installed one, and the plan refuses that by name rather than let
   the apt step do it unseen (**D-022**, issue #42). A unit whose manifest
   sets `install_recommends: false` makes this two questions rather than
   one: its packages are a second set, asked with
   `--no-install-recommends` and installed by a second `apt-get install`
   carrying the same flag, so the `Remv` lines the plan refuses on are the
   ones the command that runs would produce (**D-052**). Both commands
   carry `--no-remove`, both appear under *Commands*, and a measured
   `--target-release` governs both.
7. **Defer what the target does not offer** — but only for a member that
   reached the plan through a *profile*, and only for one of three reasons
   that are facts about the target: no install block matches this
   distro/version/arch, apt on this release has no candidate for the unit's
   *own* packages, or the distribution's Node is below the manifest's floor
   — and for one fact about the *machine*: the running kernel lacks a
   subsystem the manifest's `requires_kernel` names (**D-041**; Linux 7.1
   removed AX.25, and Kali on 7.1.5 defers eight `packet` members) — and
   for another: the unit's `desktops` names none of the desktops the
   session files under `/usr/share/xsessions` and
   `/usr/share/wayland-sessions` (and the same under `/usr/local/share`)
   offer (**D-060**; `station` defers the
   Plasma applet `hammunition-tray` on an Xfce or LXQt machine rather than
   pull in `plasma-workspace`). When a unit declares `desktops`, the plan
   prints *Desktops read from session files* with what they offered, and
   any file it read that named no desktop the catalog knows. A dependent of
   a unit deferred this way, and a profile of nothing else, name the
   desktop as the cause rather than the target.
   The member and its catalog dependents are listed under *Will NOT happen*
   with the reason, and the rest of the profile installs (**D-039**). A
   name you typed is never deferred: `hammunition install satdump` on
   Ubuntu 24.04 shows the refusal in full. An engine gap, a missing
   `depends` or `build_depends`, a retired status, and a profile with every
   member deferred all still refuse the transaction.
8. **Print the plan**, in full, for every run and not only for `--dry-run`.
9. **Present any consent gate**, then confirm, then execute — in this order:
   **every download first**, fetched into the cache and verified against the
   manifest's sha256 (**D-018**), so a wrong hash or a dead URL refuses on a
   machine nothing has touched — a repository signing key is one of these
   downloads, verified against the manifest's pinned fingerprint instead of
   a sha256 (**D-040**); then, when the plan adds a repository, its two
   files are written as root (`install -D -m 0644`); then `apt-get update`
   when the transaction has apt work — an apt step or a vendor `.deb` — and
   `--no-refresh` was not given, or whenever a repository was added
   (**D-044**); then, when the plan
   holds a vendor `.deb` or added a repository, one more `apt-get install
   --simulate` over the apt packages and the downloaded file together,
   because apt can only resolve a `.deb` from its file and can only see a
   repository's packages after the update — the plan-time simulate in step
   6 could include neither; then debconf preseeds, the apt step, the
   builds and installs in catalog order, configuration files, launchers,
   and group membership last (several groups are created by the package
   being installed). A `git` clone is a command that needs `git` from apt,
   so it stays in build order rather than moving up with the fetches.

If anything in steps 2–7 fails, **every** failure is printed together and
nothing is changed. Reporting only the first would have the same shape as the
defect this is built against: fix one, re-run, meet the next.

## What it refuses

Each of these is a named refusal with a remedy, never a silent skip. A
capability matrix that reports coverage the engine does not have is the shim
`CLAUDE.md` forbids.

| Situation | What you see |
|---|---|
| A `pipx` install block | the backend named — re-measured to zero users (D-014 amendment) and unwritten |
| A `source` or `git` block whose `build_system` is `custom` | the build system named. No manifest uses it, so it is an unimplemented gap rather than a regression (**D-014**) |
| A `data` artifact whose download is not the declared `size` | the URL, the declared and the received byte counts — the digest matched, so the manifest's declaration is what is wrong, and the plan printed a size that was not true (**D-049**) |
| A `patches` entry with no `unified_diff` | a description alone cannot be applied — building unpatched source would produce a binary the manifest does not describe. (Declared diffs stage and apply with patch(1) since v0.4.0.) |
| A `build_depends` package apt has no candidate for | which name, marked `build_depends`, **before** the toolchain is installed |
| A manifest declaring third-party `apt_repos` whose `/etc/apt/sources.list.d/<name>.sources` or `/etc/apt/keyrings/<name>.gpg` already exists **with content this engine did not write** | the file by path, marked foreign — a source under our name that somebody else wrote is never overwritten (**D-040**). Both files present with our content and still no candidate means the lists are stale; that says `--refresh` instead |
| A fetched signing key whose primary fingerprint is not the one the manifest pins | both fingerprints, and the key is discarded. A file that is not OpenPGP, fails its armor CRC, is truncated, or carries two primary keys is refused by name |
| A vendor `.deb` whose declared `conflicts_with_repo_package` is installed | the colliding packages by name, with the removal command — a dpkg file collision mid-transaction is the refused alternative |
| An apt step apt can only complete by **removing an installed package** — a `Breaks:` against something already there, the archive's `wsjtx-improved` against `wsjtx` being the measured case | every package apt would remove, with its installed version, attributed to the unit whose `conflicts_with_repo_package` declares it (or, when none does, named as a catalog gap), and the removal command so the operator can do it deliberately. Read from the same `apt-get install --simulate`; before it was read, a Kali guest with `wsjtx` installed planned clean, printed no removal, and would have lost three packages at the apt step (2026-09-07). The apt step itself now runs with `--no-remove`, so apt errors rather than removes if the real solve ever disagrees with the simulation (**D-022**) |
| A vendor `.deb` whose declared conflict is something **this same transaction's apt step would install** — directly, or as a dependency apt resolves | the package by name and both halves of the remedy: leave out the `.deb` unit, or the unit that pulls the conflict in. Found by the one `apt-get install --simulate` every transaction with apt work gets. A clean machine has nothing installed, so the row above is silent there; this one caught `digital-modes` planning clean and failing after forty-four commands (Kali, 2026-09-02) |
| An apt transaction apt itself **cannot resolve** as one `apt-get install` — the packages all exist, and the set of them still does not install | `apt: cannot resolve this transaction as one apt-get install`, then apt's own words, indented, and the simulate command that reproduces it. When the reason is that an installed package would be downgraded and it is installed from one other release, the plan is first retried from that release (**D-038**) and this row is reached only if that fails too. Five Parrot profiles passed the plan and died at the first apt command before this row existed (2026-09-02) |
| A `system_modifications` kind other than `group_membership` | the kind, by name |
| A package whose status is `broken` or `retired` | the recorded reason, verdict and date |
| A dependency apt has no candidate for | which name, and whether it came from `install` or `depends`. A *profile* member whose own `install` packages are the ones missing is deferred instead (**D-039**), and the row above still applies to its `depends` |
| A profile every member of which this target cannot install | the profile by name, with each member's reason — installing nothing and reporting success is not an outcome (**D-039**) |
| No apt package lists at all, and `--no-refresh` | that this is a stale-lists problem, and that dropping `--no-refresh` lets this run fix it. Without the flag, the run's own `apt-get update` comes first and the plan says instead that the candidate check cannot be done before it |
| A group membership with no identifiable operator | that `--user` is needed |
| A unit whose `requires_kernel` names a subsystem the running kernel's module tree lacks | the unit, the kernel release and the merge that removed the subsystem, with the remedies that exist: a distribution kernel that still carries it, or the userspace path (Direwolf's KISS/AGW ports serve pat, LinBPQ, YAAC and Xastir without kernel AX.25). Never an offer to build the module — no distribution packages one, and Hammunition builds no kernel modules (**D-041**). A *profile* member is deferred instead, the D-039 shape. No module tree for the running kernel at all — a container — is disclosed as *cannot be checked* and the unit plans |
| A unit whose `desktops` names none of the desktops this machine's session files offer | the unit, the desktops it is for and the ones the machine has (`(it has no session files)` on a server or container, and `(its session files name none the catalog knows: …)` on a machine whose only desktop the catalog does not name), and the remedy: the unit its manifest names in `desktop_alternative` when that one serves a desktop the machine has, otherwise installing a session for the unit's desktop first. A *profile* member is deferred instead, the D-039 shape (**D-060**) |

The dependency check is the one that earns its keep. **D-016** names four AHRL
dependency lines suspected of failing silently for years — `fftw2` (FFTW
version 2), `libgtk2.0-dev` (EOL), `python3-tksnack`, and an OCaml binding
fldigi does not use. The only reason nobody knows is that nothing ever asked
apt. This asks.

## Privilege

`requires_root` is a property of each command, not of the run. Unprivileged
commands stay unprivileged, `sudo` is added in exactly one place, and
resolution never asks for it at all — so `--dry-run` works as a normal user.

Three kinds of privileged command exist today: `apt-get`, `gpasswd --add` for a
manifest's declared `group_membership`, and the final install step of a source
build (`make install`, `cmake --install`). Each is printed before it runs and
recorded in the transaction log.

**A source build compiles as the operator, not as root.** Only the install into
`/usr/local` is escalated. A build run wholly as root would leave a tree of
root-owned object files in the operator's own cache for no benefit.

## How a source build works

A `source` install block becomes six steps, all of them printed before any of
them happens.

```
  # Install 3 package(s) with apt
  $ sudo env DEBIAN_FRONTEND=noninteractive apt-get install --yes --no-remove -- fftw2 libgdk-pixbuf-2.0-dev libgtk2.0-dev
  # Download and verify the glfer source archive
  $ [fetch] https://www.qsl.net/in3otd/glfer-0.4.2.tar.gz -> ~/.cache/hammunition/artifacts/06aad6fa…-glfer-0.4.2.tar.gz (sha256 verified)
  # Unpack the glfer source
  $ [extract] ~/.cache/hammunition/artifacts/06aad6fa…-glfer-0.4.2.tar.gz -> ~/.cache/hammunition/build/glfer-06aad6fa/src
  # Configure glfer
  $ cd ~/.cache/hammunition/build/glfer-06aad6fa/src && CFLAGS='-Wno-incompatible-pointer-types …' ./configure --prefix=/usr/local
  # Compile glfer (8 parallel jobs; sized to CPUs and memory)
  $ cd ~/.cache/hammunition/build/glfer-06aad6fa/src && CFLAGS='…' make -j 8
  # Install glfer into /usr/local
  $ cd ~/.cache/hammunition/build/glfer-06aad6fa/src && sudo make install
```

A `[fetch]` or `[extract]` line is a step the engine performs **itself**, in
process, rather than a command you could paste — which is why it is bracketed
rather than rendered as a shell line. Both could have been shelled out to
`sha256sum` and `tar`, and both are safer here: the file handle and the
extraction filter are ours, so a redirect to `file://` and an archive member
named `../../etc/cron.d/x` are refused by construction rather than by whatever
the local tool happens to default to.

Everything else is an ordinary `Command` with a working directory, rendered as a
leading `cd` so the line stays copy-pasteable and an operator reproducing the
plan by hand runs it in the right place.

**Where things go.** Verified archives land in
`$XDG_CACHE_HOME/hammunition/artifacts`, named by their own sha256 — the path
encodes the expectation, so a file at that path can only be content that matched
it. Build trees go in `$XDG_CACHE_HOME/hammunition/build`. Both are caches in
the real sense: deleting them costs a re-download and a rebuild and nothing else.
Under `sudo` they follow the operator, not root, for the same reason the
transaction log does.

**Verification is not optional and cannot be skipped.** The schema requires
`sha256` on every remote artifact, so an unverified download cannot be expressed
in the catalog; the fetcher streams to a temporary file, hashes as it writes, and
moves the result into place only on a match. A mismatch deletes the download and
stops the run. A cached artifact is re-hashed on every use rather than trusted
for having been verified once.

Signature verification is **not** implemented. `signature_url` and
`signing_key_fingerprint` are carried in the catalog and are not checked, so an
artifact declaring them is digest-pinned rather than signed, and the plan says so.

**Build systems:** `cmake`, `autotools`, `qmake` and `make`, which is what the
catalog uses (6 / 2 / 2 / 2). `custom` is a measured zero and is refused by name
(**D-014**).

**Parallelism is sized to memory, not only to CPUs:** one job per CPU, capped
at one per 2 GiB of RAM plus swap, never below one. `-j$(nproc)` assumes the
machine was sized for it; JS8Call's Qt sources were OOM-killed at four jobs on
a 3.9 GB guest without swap and built at four on the same guest with 3 GB of
swap (2026-09-01), and a four-core Raspberry Pi with 4 GB is the same shape.
The job count is in the compile step's comment, so a slow build on a small
machine is explained before it starts.

## How a prebuilt binary is installed

Eight units in the dispositions wait on this and nothing else — QtTermTCP,
QtSoundModem and Pi-APRS from D-008's packet core, GARIM, ARDOPGUI, AntScope2,
GridTracker2, and `sdrangel` on the five targets that do not package it.

Four formats, and the differences are the design:

| Format | What happens |
|---|---|
| `deb` | Fetched, verified, then **`apt-get install ./file.deb`** |
| `tarball`, `zip` | Fetched, verified, unpacked, and the files named in `binaries` installed |
| `executable` | Fetched, verified, installed under the one name `binaries` gives it |
| `appimage` | **Refused by name.** Post-1.0 per `docs/SCOPE.md` |

**A `.deb` goes through apt, never `dpkg -i`.** apt resolves the package's
dependencies; dpkg installs it and leaves them broken, which is the classic way
a vendor package wedges a machine. It also means the result is an ordinary
installed package apt knows about, so removing it later is `apt remove` rather
than archaeology. If apt refuses — usually a `.deb` built for a different
release — that is the correct outcome and the transaction stops there.

**Nothing here is unverified.** `sha256` is mandatory in the schema and the
fetcher refuses a mismatch, leaving nothing usable behind. That matters more
than for a source build, because nobody is going to read a `.deb`.

**An archive naming no `binaries` is refused at plan time**, because unpacking
it would leave a directory in a cache and install nothing while reporting
success. The unpack directory is keyed by the artifact's digest, so a vendor
who republishes under the same URL does not get their new files layered over
the old ones.

## How a git build works

A `git` block builds the same way once the tree is there; only how it *arrives*
differs, and so does the question that has to be answered about it.

```
  # Clear any previous ais-catcher checkout
  $ [prepare] ~/.cache/hammunition/build/ais-catcher-v0.70/src (removed if present, then recreated)
  # Start an empty repository for ais-catcher
  $ git init --quiet ~/.cache/hammunition/build/ais-catcher-v0.70/src
  # Point it at https://github.com/jvde-github/AIS-catcher
  $ git -C … remote add origin https://github.com/jvde-github/AIS-catcher
  # Fetch ais-catcher at v0.70
  $ git -C … fetch --depth 1 origin v0.70
  # Check out v0.70
  $ git -C … checkout --quiet FETCH_HEAD
  # Confirm ais-catcher is at the pinned revision
  $ [verify-pin] git rev-parse HEAD in … must be v0.70
```

**The archive backend asks *are these the right bytes*; this one asks *is this
the right revision*.** A sha256 answers the first. Nothing about a successful
clone answers the second: `git` can exit 0 having handed over a different commit
than the catalog was written against — a re-cut tag, a moved branch, a server
that ignored what was asked for. So the pin is **checked after the checkout and
before the build** (**D-031**). A commit pin must match exactly or the run stops;
a tag has nothing to compare against, so the revision it resolved to is recorded
instead — which is the raw material of the pin database, because the day a tag is
re-cut the log says what it used to be.

**A moving ref cannot be expressed.** The schema refuses `master`, `main`,
`HEAD`, `trunk` and `develop`, and a bare commit SHA requires a `pin_review`
naming who reviewed it, when, and why that commit (**D-024**). A tag carries an
upstream signal that somebody thought a revision worth naming; a SHA carries
none, so pinning one moves a judgement upstream stopped making onto us, and it is
recorded beside the pin rather than implied by it.

The fetch is shallow and by ref, so a pinned commit costs one object walk rather
than a project's whole history.

## Consent gates

A gated profile presents its disclosure before anything runs. `--yes` is
accepted by the call and deliberately never read: a gate a convenience flag
walks through is not a gate (**D-021**). In a script, set the profile's own
`HAMMUNITION_ACCEPT_*` variable to `1`. With no terminal and no variable, the
run stops — silence is not consent, and "nobody was asked" is recorded
differently from "somebody said no".

**A third-party apt repository has a gate of its own** (**D-040**), presented
after any profile gate and once per repository, whether the unit was
named or reached through a profile. The disclosure names the unit, the
URI, suites and components, the key's primary fingerprint, and the two
files that will be written — `/etc/apt/sources.list.d/<name>.sources` and
`/etc/apt/keyrings/<name>.gpg`, the latter in binary OpenPGP form, the
former with `Signed-By:` naming it and nothing wider. The variable is
`HAMMUNITION_ACCEPT_APT_REPO_<NAME>` (the repository's `name`, upper-cased,
`-` and `.` as `_`), and **its value must be the fingerprint itself**, not
`1`: checking the fingerprint against the publisher's own page is the one
step the engine cannot do for you, and a variable set to `1` would be
`--yes` again under another name. A `1` is refused with the value it
should hold. The plan prints the variable and the fingerprint together.
The affirmation is logged as `consent_affirmed` with profile
`apt-repo:<name>`, so the log records who trusted which key and when.

The repository is added only when the target's own archive offers no
candidate for the unit's packages (**D-022**): on Parrot, `codium` installs
from Parrot's archive and VSCodium's repository is neither added nor asked
about. A `depends` the archive lacks is never a reason to add one.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success — every command ran **and** its effect was confirmed afterwards |
| 1 | A command failed while running, a completed command's effect could not be confirmed (D-031), or the system is unsupported |
| 2 | The transaction could not be planned — every blocker is printed |
| 3 | A consent gate was declined, or could not be presented |

## What is recorded

Every run appends to the transaction log — format in
`docs/reference/transaction-log.md`. Each command is logged **before** it runs
and its outcome after, so a run killed mid-`apt-get` leaves a record that the
command was started. That is the state an operator needs to see, and a log
written only on success would hide it.

The log is itself a modification, so the plan discloses it: a **Records**
section names the destination path, and under `sudo` — where root writes into
the operator's home — it says the log and the directories created for it are
handed back to that operator (`chown`). The path shown is the path the run
uses, so if the operator cannot be resolved and it falls back to root's home,
the plan says so rather than redirecting in silence.

**A command exiting 0 is not recorded as an effect.** `apt-get install` can
exit 0 having installed nothing a held or broken package quietly refused, and
`gpasswd` exits 0 whether or not the membership took (**D-031**). So after every
command has completed the run **re-reads** what it claimed to change — from the
same sources resolution used pre-flight, `apt-cache policy` for a package,
the group database for a membership, and the filesystem for every binary a
source, git or binary unit declares (`<prefix>/bin/<install_as>` must exist and
be executable — js8call's `cmake --install` exits 0 and installs nothing, and
was recorded confirmed on four targets before this check existed) — and
records the confirmed state, not the exit code, in `transaction_end`. That is the record `uninstall` will trust, and
it must not say "installed" on the strength of a return value. A completed run
whose effect cannot be confirmed prints exactly what did not take and exits 1;
its log entry carries `verified: false`.

`hammunition status` reads that log back and reports how the **most recent
transaction ended** — completed, failed after N commands, or interrupted with
no ending recorded — never just what it set out to do, and for a completed run
whether its effects were **confirmed afterwards** or came back unverified. A run
that died partway is not reported as if it finished. What that run **deferred
by design** — a profile member the target does not offer (**D-039**), a
configuration file a station value was missing for (**D-035**) — is listed
after the packages it intended, from the `deferred` entry the log has carried
since `transaction_begin` version 2, so a profile that landed eighteen of
twenty-two still reads that way a week later.

Hammunition does not roll back. It tells you what it did (**D-004**). On a
failure the run stops at that command, and the count that completed is printed
along with the log's location.

One failure is diagnosed rather than merely printed. When an `apt-get install`
fails with `404 Not Found` on files in the pool, the package lists on the
machine are older than the archive: the plan resolved against those lists,
so the catalog is not at fault, and apt downloads every archive before it
unpacks any, so the command installed nothing. The message says so, names
the files by version, and gives the remedy — `sudo apt-get update`, or the
same run without `--no-refresh`. Six of fifteen profiles on a four-day-old
Parrot guest died this way (2026-09-03), each report ending in seven URLs and
apt's own hint under them; that campaign is why the refresh became the
default (**D-044**). The diagnosis still exists for the two runs it can
reach: one under `--no-refresh`, and one where the mirror moved between the
run's own update and the fetch. A `5xx` or a timeout is a mirror problem and gets
no such diagnosis; sending an operator to refresh lists that are fine would
be a wrong answer with a confident tone.

## What is not here yet

`uninstall` reverses apt, venv and binary installs, copied binaries,
installed trees, wrappers and desktop entries. What it still refuses, by
name: a source or git build that ran a real `make install` into `/usr/local`
— no file manifest exists to reverse, and the planned fix is a staged
install that records one. udev rules and group memberships are recorded but
not yet reversed.
