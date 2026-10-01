<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Changelog

One entry per release, written from the merged pull requests, each line
naming the PR and the decision it rests on. Decisions are authoritative in
`docs/DECISIONS.md`; this file is the map from a version to them.

## Unreleased

- **Infrastructure and EMCOMM layers on the maps** (D-075). `hammunition
  maps infra import --from-osm` filters the installed region extracts with
  osmium into eight layers (medical, responders, supply, shelter
  candidates, which say "candidate, not a designated shelter", transport,
  power, telecom, water), each a GPX, a QMapShack POI collection, a Navit
  map and a GeoJSON in `~/.local/share/hammunition/overlays/infra/`;
  nothing is downloaded. Three new data units in no profile:
  `faa-nasr-airports` (FAA NASR cycle 2026-10-01), `eia-860m` (August 2026)
  and `wri-power-plants` (v1.3.0, outside the US only), read by
  `--from-nasr`, `--from-eia` and `--from-wri` and kept to the regions'
  boxes; their pins are written by `scripts/gen_nasr_pin.py`,
  `scripts/gen_eia860m_pin.py` (with `--follow-move` for EIA's monthly
  archive move) and `scripts/gen_wri_pin.py`, all three in the weekly pin
  review. `fetch-fcc-asr` (only the registration and coordinate records;
  the owners' contact file is never opened) and `fetch-nwr` (the live
  status dropped) fetch on request, unverified. `maps infra remove
  [--layer ID]`; documents `infra` and `infra-removed`. The browser map's
  tiles gain an `infra` layer (the converter is `tilemaker-pmtiles 2`, so
  each region is rebuilt once), power coloured by Open Infrastructure Map's
  voltage ramp under its BSD-3-Clause notice, and every infra layer is a
  toggled overlay with its licence in the credit. The operator's Navit copy
  and QMapShack's `poiPaths` now carry repeater and infrastructure layers
  together.

- **`hammunition-tray` and `hammunition-tray-qt` re-pinned to v0.4.0**
  (GPS-time plan Task 11, D-058). Both catalog manifests moved from v0.3.0
  to the v0.4.0 release assets, measured against the published SHA256SUMS:
  `hammunition-tray_0.4.0_all.deb` (15270 bytes,
  `451bea9322376dbb9cd00834834f96e0f5d5ce487735d5fbe2349e2ae41e97bd`) and
  `hammunition-tray-qt_0.4.0_all.deb` (18198 bytes,
  `21ccc91e2f8a46a5213c9200fc0f33661d2075bfaee360cc50b0158981a46527`); both
  Depends lines are unchanged from 0.3.0. 0.4.0 adds the Time section to
  both trays: what the clock follows and the four GPS-time modes, read
  without a password and changed through one polkit prompt to
  `hammunition-devctl`, needing Hammunition 0.18.0 or later. Both
  `what_it_does` fields gain a sentence for it, and the two places that had
  written "its 0.3.0" for the still-unreleased Time section
  (`docs/guides/gps-time.md` §5, D-058's "The tray" paragraph) are corrected
  to 0.4.0.

- **Kiwix books come through the LAN mirror, and `artifacts` lists them**
  (issue #159, D-070 amended 2026-10-01, D-066). The books backend fetched
  from download.kiwix.org only, whatever the station's mirror; it now asks
  `<mirror>/kiwix-library/<book id>` first and Kiwix second, the same pinned
  sha256 and size checked either way, the plan line saying so and the log
  recording `source`, `fetched_from` and `mirror_failure` as a `data` fetch
  does. `hammunition artifacts --reference-books ID,ID` lists each book
  (`check: sha256`, its own licence line) from the carried pins, no station
  read; with none given `kiwix-library` is deferred as *no books selected*,
  and it is now among the default units. The `artifacts` document gains
  `reference_books`. Books are the largest data the catalog fetches, up to
  127 GB.
- **`import hammunition.fetch` no longer raises a circular `ImportError`
  when it is the first `hammunition` import in the process** (issue #158).
  `src/hammunition/backends/__init__.py` eagerly imports every backend, six of
  which (`apt_repo`, `binary`, `data`, `git`, `node`, `regions`, `source`,
  `venv`) named `hammunition.fetch` symbols at module scope purely for type
  annotations or late-needed helpers; `hammunition.cli.main`'s own import
  order happened to prime `sys.modules` around it, which is why the engine's
  CLI never hit it while Hammunition Bunker's `enginelib.py` did. Those
  imports now move under `TYPE_CHECKING` (annotations, deferred by
  `from __future__ import annotations` anyway) or become local imports at
  their one or two call sites (`MirrorPath`, `fetch_disclosure`,
  `record_fetch`, `safe_name`, `operator_dir`, `remove_tree`,
  `UrllibTransport`) — never a bare `try`/`except ImportError`.
  `tests/test_import_isolation.py` imports every `hammunition` module alone
  in a fresh subprocess so this cannot come back silently.

- **The GPS receiver gets a resume step** (issue #177, D-058 amended
  2026-10-01). Measured on the field laptop: a USB receiver is not
  re-enumerated across a suspend, so gpsd can keep a tty that has gone quiet
  and the fix does not come back. Where gpsd is installed,
  `hammunition hardware apply` now installs
  `/usr/local/libexec/hammunition-gps-resume` and
  `hammunition-gps-resume.service`, a oneshot that runs after every suspend
  or hibernation. It does nothing when no `/dev/gpsN` exists, so a parked
  receiver stays parked. Otherwise it runs `gpsdctl remove` and `add` for
  each receiver, and `systemctl try-restart gpsd.service` if gpsd then
  reports no device, logging one journal line per action. It makes no
  check that data flows, so a receiver gpsd still lists but that stays
  silent is left to the manual steps: a gpsd restart, then park and wake.
  Both files are printed in the plan, read back after the run and removed
  by `hardware unapply`. `--no-gps-resume` opts
  out, and `doctor` reports the step when a receiver is attached. The
  catalog names the step (`resume: {step: gpsd_reopen}` on the
  `gps-receiver` class), and that class's page gains "After suspend". It
  has not yet run on the field laptop; the bench steps are on the issue.
  After merge: `hammunition hardware apply`.
- **Repeater data beyond RepeaterBook, one layer per source** (D-074).
  `open-repeater` is a new data unit: Open Repeater's CC0 list (241 kB,
  461 repeaters, none yet in the US), pinned by sha256 in its manifest by
  `scripts/gen_open-repeater-pin.py`, checked weekly, mirrorable through a
  Bunker. `hammunition maps repeaters import` gains
  `--from-open-repeater [FILE]`, `--from-osm` (the repeaters tagged in the
  region extracts already installed, filtered by osmium, nothing
  downloaded) and `--from-direwolf-log FILE...` (the APRS repeater objects
  your station heard, its own layer, never merged). `fetch-etcc` (the
  UK's RSGB list) and `fetch-brandmeister` (DMR repeaters only; every
  hotspot dropped before anything is written) fetch on request and are
  marked unverified. Each source is its own layer; with two or more,
  `repeaters-all.gpx` joins them by a stated precedence and counts every
  join. `maps repeaters remove --layer ID` removes one. The `repeaters`
  and `repeaters-removed` documents gain `layer_id`, `layers` and
  `all_sources`. RepeaterBook bulk, RadioReference, RFinder, the ARRL
  directory, FCC ULS, RadioID, the WIA list, repeatermap.de and the D-STAR,
  YSF and NXDN lists are documented as not carried; ACMA's register is
  named as a later data unit.

- **A generated launcher no longer takes a PATH binary's name** (issue
  #174). `~/.local/bin/rigctl`, libhamlib-utils' launcher, ran ahead of
  hamlib's `/usr/bin/rigctl`, ignored its arguments and opened the
  dummy-rig shell, so every guide's `rigctl -l | grep …` waited for Enter.
  Sixteen more catalog launchers had the same shape, and `gpa`'s
  `exec gpa` ran itself. All seventeen are renamed for what they do, titles
  kept (D-054): `rigctl-dummy`, `hackrf_info-check`, `rtl_test-tuner`,
  `yagiuda-input`, `axlisten-all`, `mheard-stations`, `bladeRF-cli-shell`,
  `cgps-fix`, `gpsctl-device`, `grgsm_livemon-window`,
  `osmocom_fft-spectrum`, `gr_satellites-list`, `nfc-list-check`,
  `st-info-probe`, `ubertooth-util-version`, `gpa-window` and
  `hamclock-next-window` (the last two gain titles). The schema refuses a
  launcher named like the bare command it runs or a binary its manifest
  installs; the generator refuses, at plan time and again when it writes, a
  name found on the PATH outside `~/.local/bin` or in the unit's apt file
  list. `hammunition menus apply` removes a generated launcher that shadows
  a PATH binary, with its menu entry, and writes the renamed one; `doctor`'s
  launchers check names one. After merge: `hammunition menus apply`.
- **CoMaps can show "you are here", through GeoClue** (D-069, amended
  2026-10-01). `hammunition maps gps-tether` gains `--nmea-socket PATH`: a
  unix socket, mode 0660 in GeoClue's group, fed by the same fan-out as TCP
  10110; it is on by default once GeoClue is set up, and `--no-nmea-socket`
  turns it off. `hammunition hardware apply` writes
  `/etc/geoclue/conf.d/90-hammunition-gps.conf` (GeoClue's network-NMEA
  source reads that socket) and `/etc/tmpfiles.d/hammunition-gps.conf`
  (`/run/hammunition-gps`, 2750, setgid `geoclue`), with every file, the
  inspect and reverse steps and four disclosures in the plan; GeoClue's own
  beacondb and GeoIP lookups are not changed, and the plan says so.
  `--no-geoclue` skips it, and `hardware unapply` removes it by content.
  `doctor` reports the files, the directory and whether GeoClue's demo
  agent is running. `comaps` depends on `geoclue-2.0` and
  `libqt6positioning6-plugins`. No `[app.comaps.comaps]` entry: a native
  CoMaps is a system app to GeoClue. Measured with Debian's GeoClue in a
  private namespace, not yet on a desktop; the guide's section 17 lists
  what the bench owes. After merge: `hammunition hardware apply`, then log
  out and back in. Where CoMaps is already built, `hammunition install
  comaps --dry-run` shows whether the two new packages are planned (not
  checked on a machine with CoMaps at its pin); if they are not,
  `sudo apt install geoclue-2.0 libqt6positioning6-plugins` adds them.

- **`CHECKS` now names `sha1-publisher`** (**D-070**, **D-069**). The
  `artifacts` document's `check` field was already described as able to
  carry `sha1-publisher` — the SHA-1 and size `comaps-maps` reads from
  CoMaps' own map index — but the `CHECKS` tuple Hammunition Bunker imports
  as the enumeration of valid values never listed it, so a `comaps-maps`
  entry carried a value its own published contract did not name.

## v0.18.0 — 2026-10-01 — the 2026-09 gap analysis: guides, station config for the packet units, GPS time, chrony, Kismet, the HF modems, six apt units, three re-rulings

Ten pull requests since v0.17.0 (#149, #153, #124, #162, #165, #167, #168, #170, #171, #172), 7 entries.

- **Three re-rulings from the gap analysis** (Q-022 #5, report section
  A8). `ARDOPGUI` is superseded by `ardopcf`'s own web GUI (`-G 8514`),
  which the catalog's pin already serves; the packet profile and the
  Winlink guide say so, and that both of ardopcf's ports listen on every
  interface. **Morse Runner is carried natively** as `morse-runner`:
  the Community Edition (v1.86) does not build outside Windows, and the
  Lazarus port of 1.68 built, drew its window and made sound on Debian
  13, which is the second clause of the maintainer's 2026-08-25
  conditional. It installs by name, not on Kali, x86-64 only. `chattervox`
  is retired: no upstream since 2019, and under D-037's `--ignore-scripts`
  its serial layer cannot load (D-048 amended). Nothing awaits the
  maintainer in `dispositions.md` any more.

- **Kismet in `rf-security`** (Q-022 #4; **D-040**, amended). `kismet` is
  apt from the archive on Kali and Parrot, and from the Kismet project's own
  signed release repository on Debian 13 (`release/trixie`), Ubuntu 24.04
  and Mint 22.3 (`release/noble`), behind the D-040 fingerprint gate
  (`ADA09A0E9B80ACCCE8FE6BB65345B8BF43403B93`). Ubuntu 26.04 has no release
  tree and defers it. An `apt_repos` entry may now carry `when:`, so one
  manifest can name one repository per release. Adds the operator to the
  `kismet` group; discloses that Kali's and Parrot's kismet-core enables a
  root `kismet.service` and that the web interface listens on every
  interface by default. The CatSniffer V3's Kismet helpers are in no
  release yet. New page `docs/rf-security/kismet.md`; generated package
  pages now list a unit's third-party repositories and fingerprints.
- **GPS time where the daemon is not ntpsec: the `chrony` unit** (**D-072**,
  proposed; gap analysis §A4, Q-022 #3). `hammunition install chrony` writes
  `refclock SHM 0 refid GPS poll 2 delay 0.2` to
  `/etc/chrony/conf.d/hammunition-gps.conf` and a gpsd.service drop-in
  giving gpsd `-n`, without which gpsd publishes no time to anybody. Not in
  `station`: the three time daemons conflict, and the plan refuses to remove
  systemd-timesyncd or ntpsec, printing the `apt-get remove` for the operator
  instead. Root config writes now `mkdir -p` a missing directory as a
  printed step. **PyGPSClient** 1.7.7 is a hash-pinned venv unit for the
  `gps-gnss` tag. The *Time and position* guide routes by daemon (ntpsec to
  D-058), and troubleshooting gains *FT8 decodes nothing: check the clock*.
  Evidence: `docs/reference/time-daemons.md`.

- **GPS time** (D-058). `hammunition time` says what the clock follows (the
  network, the GPS, or holdover and for how long) without a password;
  `hammunition time mode auto|prefer-gps|ntp-only|gps-only` prints every
  write, then sets it through the one helper and polkit action. A parked
  receiver never feeds the clock. `hardware apply` installs the two grants
  ntpd needs to read gpsd's time, disclosed as widening a network-facing
  daemon's privilege, only where gpsd is installed, and prints every
  `ntp.conf` line the first mode moves and what that costs; `--no-gps-time`
  leaves all of it alone. It also runs gpsd with `-n` (the drop-in
  `/etc/systemd/system/gpsd.service.d/hammunition-gps.conf`, the same file
  and text as the `chrony` unit's), because gpsd publishes no time while no
  client is connected (measured on #162); a reboot after apply lets gpsd
  take it, and `unapply` leaves it while the `chrony` unit still uses it.
  It installs `fake-hwclock` only where there is no hardware clock;
  `hardware unapply` takes all of it back, `ntp.conf` byte for byte. `doctor` reports the time source, holdover, and a machine
  with no RTC. Parrot (ntpsec) only; built and not yet run on the field
  laptop. Guide: `docs/guides/gps-time.md`.

- **Two free HF modems join the packet core** (gap analysis section B
  Group 3, **Q-022** #6, branch `gap-05-hf-modems`). `mercury`
  (Rhizomatica, GPL-3.0) speaks VARA HF's TCP interface, so Pat's
  `varahf://` transport drives it unchanged: apt on Kali (1.9.13), a `make`
  build of v1.9.15 elsewhere, the release Debian unstable packages
  (**D-024**). `freedata` (DJ2LS, GPL-3.0) is station-to-station messaging
  and file transfer with a browser interface, a hash-pinned venv of the
  0.18.2 wheel, x86-64 only. Both are in `packet` and both transmit when a
  client keys them; the pages say so. `overlaps.md` gains an HF-modem
  section, `dispositions.md` records both as ADD outside the six sources,
  and `SCOPE.md` re-ranks VARA's Wine prefix as post-1.0 and optional. The
  packet-and-Winlink guide gains the modem choice. Measured: Pat 0.16.0 to
  Mercury 1.9.15 peer to peer, two instances back to back with no radio.
  Not measured: either modem over the air, FreeDATA's server and window.
- **Station config reaches six more units** (Q-022 #1, gap analysis A1;
  D-035 amendment of 2026-09-29). `direwolf` writes `/etc/direwolf.conf`
  (MYCALL and the KISS/AGW ports; the sound card and PTT stay yours),
  `ax25-tools` appends the `wl2k` port to `/etc/ax25/axports` once and never
  as a duplicate libax25 would refuse, `gpredict` writes its default ground
  station from the grid square, `tlf` writes `~/tlf/logcfg.dat` (CALL,
  MYQRA), `aprx` sets `mycall` on Debian's receive-only login, and
  `uronode` sets the node identity. Each was measured from the package's
  own files; each manifest says what it writes, how to inspect it and how
  to undo it. `linpac` and `fbb` configure themselves and get no block.
  The engine gains derived station values (`latitude`, `longitude` from the
  grid square; `ax25_callsign`, which defers a file rather than trim
  `W1AW/4`), `~/` paths written into the operator's home without following
  a symlink, `skip_if_present` for appends, and a dry run that names the
  station values each file is filled from.

- **Apt units from the gap analysis** (section D.6, branch
  `gap-06-apt-adds`). The eight candidates were swept on the seven targets
  first; `catalog-gaps-2026-09.md` carries the table and corrects the
  report where it was wrong. `predict` is in no archive (not in Debian 12,
  13 or unstable either) and is not added. `gr-fosphor` joins `sdr`: GNU
  Radio's GPU spectrum and waterfall blocks, offered on all seven targets;
  its .deb pulls `gnuradio-dev` and only the OpenCL loader, so the page
  says an OpenCL driver is the operator's to install. Not run on any GPU.
  `libiio-utils` joins `electronics` beside `m2kcli` and is linked from
  the `plutosdr` device: `iio_info -S`, as the `iio_scan` launcher, is
  the first check that libiio sees a Pluto or an ADALM2000. No such
  device is owned; nothing was scanned.
  `stm32flash` joins `electronics` beside `stlink-tools`: the STM32's
  built-in serial bootloader over a USB-serial adapter. No device the
  hardware catalog carries flashes that way (its STM32 entries use USB
  DFU), so none links to it; nothing was flashed.
  `ser2net` is carried but in no profile: installing the package enables
  a root `ser2net.service` whose shipped configuration listens on four
  loopback ports for `/dev/ttyS0` and `/dev/ttyS1` (read from the .deb,
  measured in a Debian 13 container), which a base profile should not
  do to every station; its page says how to inspect and disable it, and
  the rig-control guide gains a section on a radio on another machine.
  `qpwgraph`, the PipeWire patchbay the radio-audio guide already told
  people to install with apt, joins `digital-modes`, and the guide now
  links its page.
  `gpsprune` is offered everywhere and is not added: D-061 already
  measured it and left it out for its online tiles, and the report now
  says so.
  `opencpn`, the marine chart plotter that draws AIS ships from
  `rtl-ais` or `ais-catcher` and the position from gpsd or `gps-tether`,
  joins `navigation`; not opened on any target, so its OpenGL display on
  the field laptop and every one of those connections are unmeasured.

## v0.17.0 — 2026-09-30 — official topo sheets, CoMaps, and the offline browser map

Three pull requests since v0.16.0 (#161, #163, #164), 3 entries.

- **CoMaps: offline address search and routing like a phone app, with its
  own maps for your regions** (D-069). Two units join the `navigation`
  profile. `comaps` is built from source at the tag Flathub, nixpkgs and
  the AUR build (`v2026.08.31-14`), refused if the tag no longer resolves
  to its commit; the git backend gains what it needed, each a catalog
  field the engine runs: submodules fetched shallow and read back at their
  recorded commits, a hash-pinned build Python (CoMaps' CMake refuses
  Debian's protobuf 4.x), upstream's `configure.sh` with the files it must
  produce (its symbol step exits 0 without optipng), and files the install
  rule leaves out (the World maps, sha256-pinned). `comaps-maps` fetches
  CoMaps' own maps for your map regions through a generated table
  (`catalog/data/comaps-pins.yaml`, all 1,150 maps, 262 Geofabrik regions
  including every US state and DC), each checked by the SHA-1 and exact
  size in CoMaps' own index, which the plan says on every line, and from a
  LAN mirror first when one is set (D-070; `hammunition artifacts` lists
  them as `sha1-publisher`); an expired pin refuses the plan, and `update
  --upstream` says `pin expiring` or `pin expired`. `hammunition maps
  comaps`, the `comaps-offline` launcher, records CoMaps' licence answer and links your maps where it looks. CoMaps
  reads its position from GeoClue only, so there is no "you are here" on
  the laptop yet; the guide says what the route would be. Organic Maps and
  Flatpak are not carried. The build through the engine and US address
  search are owed by the bench.

- **An offline map in the browser** (**D-071**, branch `map-server`).
  `osm-pmtiles` turns each map region into vector tiles with the archive's
  tilemaker (3.0 or newer; Ubuntu 24.04's 2.4 defers it by name), and
  `vector-map-kit` pins the fixed files: tilemaker's OpenMapTiles profile,
  Natural Earth's ocean and land cover, the OSM Bright style, sprite and
  fonts, MapLibre GL JS 6.11.2 and pmtiles.js 4.5.0. Both join
  `navigation`. `hammunition reference serve` now also serves the map at
  `http://127.0.0.1:8480/map/`, with HTTP byte ranges, each file by its
  installed name, and refuses any request that does not name 127.0.0.1 or
  localhost. The page draws "© OpenMapTiles © OpenStreetMap contributors" on
  the map. `hammunition maps gps-tether` also serves your position to it as
  an event stream on 127.0.0.1:10111 (`--position-port`); a tether started
  with `--port 10111` now needs `--position-port` as well. A `data` archive
  can list its `members` and the subdirectory it goes `into`. Not yet run
  with a real tilemaker; the bench owes it.

- **Official topographic maps: USGS US Topo** (**D-068**). For US map
  regions, the `navigation` profile gains `usgs-ustopo` (the 7.5-minute
  sheets a region's outline touches, chosen offline from the carried index
  `catalog/data/ustopo-quads.txt`, generated by
  `scripts/gen_ustopo_index.py`, each checked against the publisher's S3
  ETag, multipart included) and `ustopo-qmapshack` (each sheet warped to Web
  Mercator with its collar cropped, and one `ustopo.vrt` that
  `hammunition maps qmapshack` adds to QMapShack's maps). The plan's Terrain
  block gains a US Topo part; `update` counts sheets with a newer indexed
  edition. QMapShack drawing the mosaic is not yet measured. FSTopo and USGS
  3DEP are next.

## v0.16.0 — 2026-09-30 — the navigation sweep: BRouter, repeaters, phone maps, the reference layer, the LAN mirror, and the documentation site

Six pull requests since v0.15.0 (#151, #150, #154, #157, #152, #155), 5 entries.

- **A LAN mirror for offline data, and `hammunition artifacts`** (**D-070**,
  branch `artifacts-mirror`). `hammunition station set --mirror URL` names a
  machine on your own network; every data download (a `data` unit's files, a
  map region, a terrain tile) asks it first at `<mirror>/<unit>/<name>` and
  its publisher on any failure, the same sha256 or publisher MD5 checked
  either way. The plan gains a *Data mirror* section and names both sources
  per download; `install --no-mirror` ignores the mirror for a run;
  `--clear-mirror` removes it; the transaction log records where each
  download came from. `hammunition artifacts [--json]` lists every remote
  data artifact for regions, a freshness and units given on the command
  line, reading no station: the contract
  [Hammunition Bunker](https://github.com/ChiefGyk3D/hammunition-bunker)
  mirrors from. `station show` gains a `mirror` line and its document a
  `mirror` field; plan steps gain `sources`. Guide:
  `docs/guides/lan-mirror.md`.

- **Repeaters on the offline maps** (**D-064**). `hammunition maps repeaters
  import FILE...` converts your own export, with no network, into a GPX, a
  QMapShack POI collection and a Navit layer in
  `~/.local/share/hammunition/overlays/repeaters/` (mode 0600). It reads a
  RepeaterBook GPX export, a RepeaterBook CSV export with Lat and Long,
  hearham.com's JSON or a CSV you type; CHIRP files and CSVs without
  positions are refused by name, since they carry no coordinates. Rows are
  merged on callsign, output frequency and position to 0.01°, and the
  merges are counted. RepeaterBook's attribution and terms are printed at
  import; nothing is ever fetched from RepeaterBook. `maps repeaters
  fetch-hearham` fetches hearham's open list on request, records the
  sha256 it saw and marks the layer unverified. `maps repeaters remove`
  undoes it. `import` and `remove` take `--json` (`repeaters`,
  `repeaters-removed`), carrying counts and paths, never a callsign or a
  position. The `navit-offline` launcher now runs `hammunition maps
  navit`, which adds the layer to your own copy of Navit's configuration;
  `hammunition menus apply` updates an installed launcher. Drawing on
  screen is not yet measured.
- **BRouter: a second offline router for QMapShack, with trail difficulty
  and climbs** (D-063, amending D-061's "BRouter stays out"). Three units
  join the `navigation` profile: `brouter` (upstream's v1.7.10 zip, checked
  by its sha256, with Java from the archive), `brouter-mapcreator-profiles`
  (the two map-creator filters the zip lacks, pinned by the tag's commit)
  and `brouter-segments`, whose new `brouter-mapcreator` converter builds
  BRouter's routing files on the machine from your regions with the
  Copernicus elevation folded in, as you, in one locked staging directory,
  and rebuilds them when a region, snapshot, tile or BRouter changes.
  brouter.de's routing files are never downloaded: they are rebuilt weekly
  with no checksum. The plan's *Terrain* block and its JSON say what is
  built; `hammunition maps qmapshack` points QMapShack's local BRouter at
  it, set to 127.0.0.1 with bind-to-host on, and leaves a BRouter you set
  up yourself alone (QMapShack honours the bind only once it has read
  BRouter's version; the guide says how to check). The
  map creator now runs with `-DavoidMapPolling=true`, which removes a 120 s
  wait its parser adds to every input under 100 MB. Measured end to end on
  synthetic regions against the pinned jar; a route drawn in QMapShack is
  owed by the bench.
- **The offline reference layer** (D-066). A `reference` profile (post-1.0)
  with `kiwix-tools`, `kiwix`, `dictionaries` (dictd with GCIDE, WordNet,
  FOLDOC and VERA acronyms, on 127.0.0.1 as Debian ships it) and
  `goldendict-ng` from the archive; `kiwix-library`, the Kiwix books chosen
  with `hammunition station set --reference-books`, each pinned by size and
  sha256 from its `.meta4` (`catalog/data/kiwix-pins.yaml`, generated by
  `scripts/gen_kiwix_pins.py` from the hand-written 27-book list in
  `catalog/data/kiwix-books.yaml`) with its licence printed in the plan;
  and `ics-forms`, FEMA's 39 ICS PDFs pinned by Hammunition's own sha256.
  A pin Kiwix has dropped refuses the plan by name and is never replaced by
  the newer file. `hammunition reference books` lists the books (`--json`:
  a `books` document); `hammunition reference serve` serves the books, the
  forms and the dictionaries on 127.0.0.1:8480, with kiwix-serve as a
  child always started with `-i 127.0.0.1`. `hammunition update` reports
  the books against their pins, and `--upstream` warns before a pin
  expires. The weekly pin review runs the new generator's `--check`.
  `docs/guides/offline-reference.md` is the walk-through. Three corrections
  from the spike: `zim-tools` ships `zimwriterfs` in Debian 13; libzim
  9.2.3 reads today's format-6.3 ZIMs; `hamradio-maintguide` is a packaging
  guide.
- **Phone maps from the laptop** (D-067). Two new units build, from the
  station's regions, a Mapsforge map (`mapsforge-map`) and a Mapsforge
  points-of-interest file (`mapsforge-poi`) per region, as the operator,
  with the archive's osmosis; the POI writer, packaged nowhere, is fetched
  from Maven Central and checked against a sha256 Hammunition measured. They
  are a new post-1.0 profile, `phone-maps`; `navigation` is unchanged.
  `hammunition maps phone` copies the phone files, Garmin maps included,
  into one folder with a `SHA256SUMS` and prints the ways to carry them to a
  phone: the laptop's hotspot with a web server bound to the hotspot's
  address, USB, and `adb` or KDE Connect as opt-ins. It transfers nothing.
  None of the files has been loaded on a phone yet. OsmAnd `.obf`,
  Organic Maps and CoMaps `.mwm`, PocketMaps and Transportr are not
  carried, each with its reason and route in D-067.
- `scripts/check_artifact_urls.py` no longer crashes on a derived unit, whose
  `source` is a unit name, and sweeps a converter's pinned tool (D-067).

## v0.15.0 — 2026-09-29 — sudo asked once per run; launchers by absolute path

Two pull requests since v0.14.3 (#146, #147).

- **Generated launchers run Hammunition by its full path** (issue #145).
  `qmapshack-offline` and `gps-tether` said `hammunition maps ...`, and
  Plasma starts a menu entry as a systemd user service whose `PATH` has no
  `~/.local/bin`: both failed from the menu with "hammunition: not found".
  A launcher now names `~/.local/bin/hammunition` when that is bootstrap's
  link to the engine that wrote it (so a moved checkout is mended by
  `./bootstrap.sh`), otherwise the engine's own `.venv/bin/hammunition`; the
  plan prints which. The device park and wake menu entries do the same.
  `hammunition menus apply` rewrites a launcher written before this, and
  `hammunition doctor` gains a **launchers** check naming any launcher whose
  engine is a bare name or a path that is gone, with the fix. The offline
  navigation guide's "QMapShack does not start from the menu" says what
  "not found" means now.
- **An install run as a user asks sudo once and keeps its ticket valid
  until the run ends** (D-062, issue #137). A `navigation` install waited
  7.8 hours at a second `sudo` prompt after 30 minutes of work: sudo's
  cached password had expired during a long conversion that runs as the
  operator. When a plan mixes root steps with unprivileged ones, it now
  prints a *sudo* section, runs `sudo -v` once before the first step, and
  refreshes the ticket with `sudo -n -v` every 4 minutes from the same
  process, stopping when the run ends. A refresh that fails is reported
  once and not retried. `--no-sudo-keepalive` turns it off, and the plan
  then says a later step may prompt again. The JSON plan carries it as
  `install.sudo`; the log records `sudo_keepalive_begin` and
  `sudo_keepalive_end`. The offline navigation guide's new troubleshooting
  entry keeps the manual refresh loop as the fallback.

## v0.14.3 — 2026-09-29 — the GPS tether on other setups

One pull request since v0.14.2 (#142).

- **The GPS tether takes `--gpsd` and `--port`, and any number of
  clients** (D-061, amended 2026-09-29). `--gpsd HOST[:PORT]` reads a gpsd
  on a Pi, a phone or a shack computer (IPv6 in brackets); `--port N` serves
  another port, 1024 to 65535. It still listens on 127.0.0.1 only; another
  machine reaches it through `ssh -L`. Every connected client gets every
  sentence from one shared gpsd watch, closed when the last client leaves,
  and a client that stops reading is dropped alone. The offline navigation
  guide gains section 12, *Other setups*: a remote gpsd, a phone, a
  Bluetooth or serial receiver, a rig's built-in GPS and the port it then
  cannot share with rig control, a parked receiver, and what of each is
  measured.

## v0.14.2 — 2026-09-29 — QMapShack selects its routing database; bench session 12

One pull request since v0.14.1.

- **QMapShack's routing database is selected** (D-061, amended
  2026-09-29). With `[Route] routino\database=-1` in its settings,
  QMapShack 1.17.1 loaded the `hammunition` Routino database and selected
  nothing, so routing did nothing without a message, and it wrote the `-1`
  back on exit. `hammunition maps qmapshack` now sets the key to 0 when it
  is absent or negative and leaves 0 or more alone.
- **Bench session 12 recorded** in
  `docs/reference/bench-verification-5430.md`: the two-region
  `install navigation` verified whole (294 commands, a 7.8-hour wait at an
  expired `sudo` prompt, issue #137), QMapShack listing the maps and
  drawing hillshade, and the rewritten GPS tether giving QMapShack a
  position from a real receiver. The guide's QMapShack section says where
  the Routino path dialog is, that the *Database* dock is not the routing
  database, that QMapShack reconnects to the tether by itself, and what
  the hatching is. A route on foot is still not recorded.

## v0.14.1 — 2026-09-29 — bench fixes: QMapShack's paths, the GPS tether

One pull request since v0.14.0, from bench session 12 on the field laptop.

- **The GPS tether makes its own NMEA** (D-061, amended 2026-09-29).
  `hammunition maps gps-tether` reads gpsd's JSON and writes `$GPRMC` and
  `$GPGGA` on 127.0.0.1:10110; no socat or gpspipe, the loopback bind
  in its own code, and a plain message when gpsd has no fix. The old
  tether sent nothing on the field laptop while gpsd reported no position. `socat` leaves the `navigation`
  profile and is kept in the catalog as retired, so `hammunition uninstall
  socat` still works where v0.14.0 installed it.
- **QMapShack's map and elevation lists go under `[Canvas]`** (D-061,
  amended 2026-09-29), where QMapShack reads them; the launcher moves its
  own directories out of `[General]`, where the first version put them.

## v0.14.0 — 2026-09-28 — trails, terrain and offline routing on foot

One pull request since v0.13.0: navigation piece 2, for daily hiking and
for the day nothing else works.

### Engine

- Three new converters, run as the operator under one lock per region or
  per build, scratch cleared only by the operator under that lock, root
  never removing a working directory: `mkgmap` (a Garmin image per region,
  0.85× the extract), `routino-planetsplitter` (one Routino database over
  every region, installed all-or-nothing, 0.67× of the sum) and `gdal-dem`
  (a VRT for hillshade and slope, and a 20 m contour overlay, 5.4 MB per
  tile measured). Converter versions in sidecars trigger exactly one
  rebuild; mkgmap's heap arrives through `JAVA_TOOL_OPTIONS`, because
  Debian's wrapper ignores `JAVA_OPTS` (#135, D-061).
- A `dem-tiles` install method: Copernicus GLO-30 elevation tiles for every
  square a region's Geofabrik outline touches, each verified by a sha256
  pinned by Hammunition or by the publisher's single-part ETag MD5, said
  which per tile in the plan; a carried tile list of 26,450 names with a
  weekly check; a square with no published tile is reported as exactly
  that, never "sea", and a region with no terrain available is warned
  about while its maps still install (#135).
- `hammunition maps qmapshack` (starts QMapShack after additively adding
  our directories to its per-user config) and `hammunition maps
  gps-tether` (gpsd → NMEA over TCP on 127.0.0.1:10110 only); a `doctor`
  check for Routino's translations file (#135).
- The plan's Terrain block, text and JSON from one object; the disk check
  counts tiles, images, databases, contours and scratch; `update` reports
  terrain as counts only (#135).
- Navit's dropped children now get the operator's minimal environment,
  not root's (#135).

### Catalog

- `qmapshack`, `routino`, `gdal-bin`, `mkgmap`, `mkgmap-splitter`, `socat`
  from apt; `dem-copernicus`, `osm-garmin`, `osm-routino`, `dem-qmapshack`;
  all in `navigation` (#135).

### Documentation

- D-061; the guide's trails-and-terrain sections, "find an address in
  Navit, walk it in QMapShack", the bridge, and the gaps; the CLI
  reference. What has not run on a desktop yet is marked so: bench
  session 12 on the field laptop is the check (#135).

## v0.13.0 — 2026-09-28 — Navit finds your towns

One pull request since v0.12.0, from the first address search on the bench.

### Engine

- Navit's town index was nearly empty on every Geofabrik sub-country extract:
  the extract carries only the in-extract pieces of the country's boundary
  relation, so `maptool` logged "Broken country polygon" and filed almost no
  town while still drawing them. The `navit-maptool` converter now merges a
  closed country border, synthesised from Natural Earth's admin-0 data for
  the region's country, into the extract with `osmium` before running
  `maptool -U`; a region passes only when maptool recognises each merged
  border as a country. On one US-state-sized region the index went from
  about a dozen items to over four thousand, nearly all with state and
  county (#133, D-057 amendment).
- Maps built by the old converter rebuild once: the sidecar records a
  converter version, and the plan says "will convert (converter changed)"
  (#133).
- maptool runs stay sequential: its fixed-name temp files make two runs in
  one directory crash, measured on the bench (#133).

### Catalog

- `country-boundaries`: Natural Earth 1:10m admin-0 countries, public
  domain, sha256 computed and pinned by Hammunition because upstream
  publishes none; a dependency of `osm-navit`, with `osmium-tool` (#133).
- `catalog/data/geofabrik-countries.yaml`: each Geofabrik region's country,
  generated from Geofabrik's index and checked weekly (#133).

### Documentation

- The guide's "Find an address" section (Actions → Town, the flag button,
  street and house-number icons, Set as destination); bench session 11
  (#133).

## v0.12.0 — 2026-09-28 — the engine speaks JSON, and `hammunition` is on the PATH

One pull request since v0.11.0: piece 1 of the console. The front ends that
follow (`hammunition-console`, its own project) drive the engine through
this interface and never import it.

### Engine

- A global `--json` flag: with it a command prints exactly one document on
  stdout (`schema: hammunition/1`, a `kind`, the engine version), diagnostics
  go to stderr, and the exit code is the text form's. That holds on success,
  on a refusal, on an argparse error and on an unexpected exception. Covered:
  `status`, `list`, `show`, `install`/`uninstall --dry-run`, `station show`,
  `hardware state`, `maps regions`, `update`, `doctor`. Text and JSON are
  rendered from one object per command, so they cannot drift; golden tests
  pin both (#127, D-059).
- A real install is never driven through `--json`; only `--dry-run` is
  accepted. Abbreviated flags are refused on every parser, because `--js`
  used to route around that guard (#127).
- `status --json` records removals: `removed`, `removal failed`,
  `removal interrupted`; a reinstall reads `completed` again (#127).
- Privacy: the `plan` document never carries rendered config or the
  callsign; `update` and `doctor` never name a map region in either output,
  and tests fail if they do; `station show --json` carries station values
  for local front ends and the reference says it is not for pasting (#127).
- `bootstrap.sh` links `~/.local/bin/hammunition` to the checkout's venv
  through `scripts/path-link.sh`: every change printed first, nothing it did
  not create replaced, no shell rc file touched. `doctor` checks where
  `hammunition` resolves; it offers a quoted switch only for our own link,
  names a foreign file or an earlier PATH entry without touching it, and on
  a fresh install says to log out and back in (#127).
- The Packages list and the Map regions section agree: `osm-regions` and
  `osm-navit` read "already installed" when nothing is left to fetch or
  convert (#127).

### Documentation

- `docs/reference/json-interface.md`, generated from the dataclasses and
  checked in CI; D-059; examples written as bare `hammunition`, with the
  full `.venv/bin/hammunition` path wherever a reader could meet the command
  before bootstrap has linked it; a "command not found" section in
  getting-started (#127).

## v0.11.0 — 2026-09-28 — lighter desktops welcomed, and Navit opens on your maps

Two pull requests merged since v0.10.0. Parrot and KDE Plasma stay first;
Xfce and LXQt (Lubuntu) are welcomed, and nothing about them is claimed
until the VM runs.

### Engine

- Desktop detection from the session files a display manager lists
  (`DesktopNames=`, with a measured fallback for LXDE and Cinnamon, whose
  files carry none). A new `desktops` / `desktop_alternative` manifest pair
  lets a unit serve particular desktops: a profile member for a desktop the
  machine lacks is deferred by name and the rest installs; typed by name, it
  is refused with the alternative named. `doctor` reports the desktops read
  (#129, D-060).
- Navit opens on the maps and follows the GPS. The generated config used to
  keep Navit's stock start point, Munich, and never followed the gpsd
  vehicle, so it showed a blank screen even with a 3D fix. It now centres on
  the first region's bounding box, read from the PBF header (bounded, and
  only the header), and adds `follow="1"`. Both are soft: when either cannot
  be done, the config is still written and the step says why (#130, D-057
  amendment).
- Navit's map size estimate goes from 0.8x to 0.9x of the download, after
  two US-state-sized regions converted at 0.874x and 0.856x on the field
  laptop. maptool's scratch files are removed once a region's map is
  installed (#130).

### Catalog

- `hammunition-tray-qt`, the tray for Xfce, LXQt, LXDE, MATE and Cinnamon,
  pinned from hammunition-tray v0.3.0, and `hammunition-tray` re-pinned to
  v0.3.0 with `desktops: [kde]`; both in `station`, each naming the other.
  `station` no longer pulls the Plasma shell onto a machine without it
  (#129).

### Documentation

- `docs/desktops.md`: every desktop's menu mechanism, tray and weight,
  unmeasured marked unmeasured; Lubuntu is LXQt, not LXDE.
  `docs/reference/vm-campaign-desktops.md` is the Xubuntu and Lubuntu
  checklist, not yet run (#129).
- `docs/guides/offline-navigation.md`: "Navit opens on a blank map", and
  that scratch stays after a failed conversion (#130).

## v0.10.0 — 2026-09-28 — device power control, offline navigation, the family's own units

14 pull requests merged between 2026-09-13 and 2026-09-28. Still beta: the
1.0 checklist in `docs/reference/release-1.0-checklist.md` is unchanged in
kind. What is new is the station switching its own radios off, finding its
way with no network, and carrying the other Hammunition projects as ordinary
pinned units.

### Engine

- Device power control: park and wake a catalogued device from the CLI,
  generated menu entries and a tray applet, through one root helper at
  `/usr/local/libexec/hammunition-devctl` behind one polkit action;
  `power_control` on a manifest names a method from a fixed enum, so the
  catalog never carries a command (#117, D-056). Installing the helper asks
  one `yes` that `--yes` cannot answer (#118), and refuses a tree another
  account can write, the owner's private group excepted.
- Kept off: a parked device stays parked across reboots, one rewritten-whole
  udev rule per device; `--until-reboot` opts out; `state` shows intent and
  reality side by side (#119, D-056 amendment). The reboot itself is not yet
  measured on the bench.
- Offline navigation: `osm-regions` fetches OpenStreetMap extracts from
  Geofabrik, pinned by sha256 for the yearly snapshot of every US state and
  DC, MD5-checked from Geofabrik for anything else the operator picks;
  `osm-navit` converts them with Navit's `maptool` as the operator, one
  region at a time, a failed region never taking the others with it; the
  selection lives in station config (#121, D-057). `hammunition maps
  regions` lists what can be chosen.
- Menus: every installed unit is placed on the day the menu is applied, not
  only those installed through the engine (#114, D-050 amendment).

### Catalog

- `skid-finder`, the maintainer's passive BLE-spam and Wi-Fi-attack
  detector, carried as an ungated `rf-security` unit from its tagged
  pre-release tarball, v0.6.0-alpha.1 (#116).
- `hammunition-tray`, the Plasma applet for park and wake, carried as a
  pinned `.deb` in `station` (#122); re-pinned to v0.2.0 here, which adds
  the kept-off label, Forget, and one notice per login.
- `navit`, `osm-regions`, `osm-navit`, and a post-1.0 `navigation` profile
  under a new `navigation-maps` category (#121).
- `wsjtx` claims its aggregator entry in the menu (#115).

### Documentation

- The Hammunition family (hill, tray, skid-finder) described from the main
  README, and power control in the status (#120).
- `docs/guides/offline-navigation.md`: choosing regions, disk and time
  measured on a 6.1 GB country-sized region, and what works with the network
  off (#121). `docs/hardware/power-control.md` for park, wake and kept off
  (#117, #119).
- The rebuilt menu verified as data on GNOME and Xfce (no one has opened
  either on a VM yet), and COSMIC and Pop!_OS
  recommendations toward 1.0 (#115).
- README: socials and donation rows (#109–#113).

## v0.9.0 — 2026-09-13 — beta: feature-complete for 1.0, verification remains

79 pull requests merged between 2026-09-02 and 2026-09-13. Every 1.0 stage
of SCOPE.md is in the catalog, the seven backends are written and reversed
by `uninstall`, M5 is met on six VMs, and the whole catalog installed and
verified on the field target. What separates this from the 1.0 tag is
verification and one decision, listed with owners in
`docs/reference/release-1.0-checklist.md`; that is the 0.1 that is missing.

### Engine

- Every download is fetched and verified before anything installs; a
  vendor `.deb` is simulated with the apt step before either runs (#15).
- Third-party apt repositories against a pinned key fingerprint; consent is
  the fingerprint itself; both files come out on uninstall (#16, D-040).
- A profile member the target does not offer is deferred by name and the
  rest installs (#14, D-039); a whole-profile plan names every deferral (#32).
- Mixed-release targets resolve from the release the machine already
  installs from, never downgrading (#12, D-038); an apt 404 from the pool is
  diagnosed as stale lists (#20); `install` refreshes the lists by default,
  `--no-refresh` opts out (#54, D-044).
- `requires_kernel`: the plan reads the running kernel's module tree and
  refuses or defers by name; Linux 7.1 removed AX.25 (#28, D-041). The packet
  core is userspace-primary and installs without `ax25.ko` (#55, D-045).
- The effect check reads back installed trees and launchers (#33), declared
  binaries (#79) and, for a library, its declared `installed_files` (#92).
- An installed tree is handed to the operator by an explicit `chown` step the
  plan prints (#52, D-043); a single prebuilt executable is installed by a
  privileged `install` command, not an in-process copy (#72); a venv is built
  with the resolved interpreter (#74).
- apt removals are refused by name, never performed (#50, D-022 enforced).
- A build already installed at its pin is already installed: the effect on
  disk plus the log's attribution (#75, D-051); per-block `binaries` for
  per-architecture archives (#86); a git block may carry patches (#97).
- A unit may install its apt packages without Recommends, as a second
  simulated apt command (#85, D-052).
- `hammunition update`: installed against the catalog, offline, nothing run
  (#91, D-053); `update --upstream` asks GitHub, git tags, PyPI or a label
  file whether the pin is current (#94). The first run found three pins
  behind and they were re-pinned the same night (#97).
- Node backend: a Vite application from the distribution's Node, refused when
  Node is absent or too old, never fetched (#11, D-037).
- A cmake build pulls cmake into the apt set (#21); `.venv` symlink untracked
  and the ignore rule tested (#25).

### Catalog

- 249 manifests. The EmComm Tools OS Community delta: paracon, artemis and
  gpa carried, chattervox left with test results (#58, D-048); the offline
  `data` install method for maps and reference sets (#59, D-049).
- `hammunition-hill`, the family's own dashboard (#39); rayhunter on
  x86_64, aarch64 and armv7l with upstream's digests (#71, #86); nanovna-saver
  and qlog from the archive (#41); wsjtx-improved from Kali's archive (#50);
  yaac re-pinned to the author's build label as its update probe (#23, #35).
- The vocabulary recut from 26 to 55 tags, each the thing a person looks for,
  every unit retagged (#103, D-055).
- morse installs on a PipeWire desktop again (#65, #85, #87).
- 26 units carry launchers; each launcher has a title; a terminal launcher
  holds its window, never shadows its own tool, and exits with the tool's
  status (#71, #82, #89, #100). 47 generated entries carry a `menu_title`
  (#101).

### Hardware

- brltty measured on all seven targets; the udev sweep reads every rule
  syntax (#57, D-047). limesdr's identifier from an owner's capture (#36).
  orbic-rc400l, the Rayhunter hotspot, unconfirmed until it is on the bench
  (#73). The Kali archive gaps say why (#29).

### Desktop menus

- Parrot's shape: one top menu, ordered groups, one submenu per category, a
  generated entry for every installed unit that ships none, placed filenames
  checked on disk, Parrot's replacement entries honoured (#66, #68, #77,
  D-050). Icons on every entry and directory; an install ends by re-applying
  the menu (#80, #83).
- Activity groups in plain words, a toolkit unit nested as one line, titled
  entries (#102, D-054); 55 submenus (#103, D-055); a source build's own
  desktop entry placed from the local prefix (#104).

### Targets, CI and verification

- Ubuntu 24.04 declared; the matrix stops reporting unswept names as absent
  (#17). The arm64 target runs natively (#60). The target image's apt steps
  retry when the mirror is mid-sync (#93). The weekly udev-citation job
  imports its parser again; the orphan test measured under load (#88).
- Every page generator takes `--check`; a missing probe is an error (#51).
- Campaign reports carry their evidence (#26); the GUI smoke lane reads
  stderr and owns its deadline (#37, #43).
- The field target is the Dell Latitude 5430 Rugged: nine bench sessions
  recorded, the whole catalog installed and verified there (#62, #78, #90,
  #99).

### Documentation and governance

- Release procedure with SSH-signed tags (#13). The landscape survey and the
  AHRL-versus-Blend coverage matrix (#40). EmComm Tools OS Community as the
  sixth inventory source (#44, D-042). Post-1.0 tracks for trunked and
  digital-voice listening and for repeaters (#53, #56, D-046); the mesh and
  Reticulum track (#106, SCOPE stage 11, #105).
- Hammunition is the one-stop shop for everything radio: nothing is out of
  scope, and what cannot work yet is a documented gap (#70).
- README and CLAUDE.md brought current against measured state; the 1.0
  checklist (#18, #47, #49, #84, #106).

## v0.7.0 — 2026-09-02

The last release cut from a direct push to `main`. The core cycle — resolve,
disclose, install, configure, verify, remove — VM-verified on Parrot, Kali,
Debian 13 and Ubuntu 26.04 with zero hard install failures across the
catalog. Annotated, not signed: no key existed.
