<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Catalog gap analysis — 2026-09-30

A deep dive over every category in `catalog/categories.yaml`: what the
catalog carries, what the wider field has that it does not, what the
project *planned* and has not yet delivered, and where a configuration or
a page would do more than another manifest. Prompted by the maintainer's
own find, 2026-09-28: the GPS and navigation software was missing, and it
became **D-057** and **D-061**. This page asks what else is missing the
same way, one category at a time.

**What this page is.** A measured list of candidates and gaps with a
recommendation on each, written for the maintainer to rule on. Nothing on
it is decided; the decisions it asks for are collected as **Q-022** in
`docs/QUESTIONS.md`.

**What this page is not.** Not a disposition (`docs/reference/dispositions.md`
is the index of the six sources' units, and this page does not change it);
not a claim that any candidate installs on any target — see *How it was
measured*, which says exactly what was and was not checked; and not a
re-litigation of anything in `docs/DECISIONS.md`. The RF-security group
(Wi-Fi, Bluetooth, cellular, RFID, sub-GHz) is **deliberately out of this
pass** except for two plan-versus-delivery notes: SCOPE.md's post-1.0
tracks and D-034/D-046 already govern it, and a comparison of that tooling
is a separate job.

## Headline

The catalog is broad where the six sources are broad. The Debian
Hamradio Blend is carried whole — every backticked package in
`docs/reference/blend-inventory.md` resolves to a manifest or to an apt
block. Where the catalog is thin is not where the sources are thin; it is
where the *engine's own plans* outran the manifests:

| Gap | Planned by | Delivered |
|---|---|---|
| Station config consumed by the units that need a callsign | D-004, D-008 ("Direwolf *with configuration*"), D-035 | One manifest (`linbpq`) carries a `config_files` block. Direwolf, pat, WSJT-X, fldigi, JS8Call, Xastir, YAAC, gpredict and the loggers all still ask the operator to type the callsign a second time |
| A rig as station data, one CAT connection shared by every program | D-042 (the ETC rig model, "reimplemented as catalog data") | Not started. Station config has no rig field; nothing runs `rigctld` |
| GPS-disciplined time on the field laptop | The `station` profile's own summary ("time, position") | `gpsd` is in `station`; nothing feeds it to the clock. FT8 without the internet — the D-057 scenario — fails at ±1 s |
| Audio routing for digital modes | The documentation standard in CLAUDE.md ("fresh Parrot to a working digital-modes station without asking anyone") | No unit, no guide, no troubleshooting entry. Every digital mode needs it |
| Kismet | `rf-security` profile prose: "held back until the third-party apt repo path is implemented" | D-040 implemented that path on 2026-09-03. Kismet is still absent and the prose is stale |
| The task-oriented guides | CLAUDE.md's `docs/guides/` list: digital modes, APRS, satellite, packet, SDR | Four guides exist: conference operating, offline navigation, propagation, Rayhunter. None of the five named ones |

Those six are the findings that change what the project does next. The
per-category candidates that follow are real, but most are one manifest
each; these are the ones an operator hits on the first evening.

## How it was measured

- **The catalog:** 266 manifests read with the loader's own YAML, tagged
  against the 56-tag vocabulary; `status` and `config_files` counted;
  `system_modifications` kinds counted (two `apt_pin`, two
  `group_membership` — nothing writes a service or a config file except
  `linbpq`).
- **The record:** SCOPE.md, DECISIONS.md D-046 through D-061,
  `not-carried.md`, `parity-coverage.md`'s *outstanding* table,
  `prior-art.md` §4 and §5, and the seven open GitHub issues.
- **Upstreams:** web search on 2026-09-30 for each candidate's current
  release, licence and activity. Where the result names a date it is the
  search result's date, not a head-commit check; **D-032's rule (the
  default branch's head commit, never `updated_at`) has not been applied
  to any candidate here**, and must be before any manifest is written.
- **Archives:** this session could not reach `packages.debian.org`,
  `sources.debian.org`, `tracker.debian.org` or Launchpad (egress policy),
  and the seven-target `apt-cache policy` sweep needs Podman. So **every
  "in Debian" claim below is from a web search result and is marked
  `unmeasured` until `scripts/apt-policy-sweep.sh --all` says otherwise.**
  A candidate is not a manifest until that sweep has run for it (D-014,
  D-025).

### Measured since, 2026-09-30 — the apt adds of D.6

`scripts/apt-policy-sweep.sh`, one target at a time, over the eight apt
candidates of item 6 in section D. `-` means the archive has no candidate.

| Package | Debian 13 | Ubuntu 26.04 | Ubuntu 24.04 | Kali | Parrot 7 | Mint 22.3 | Debian 13 arm64 |
|---|---|---|---|---|---|---|---|
| `predict` | - | - | - | - | - | - | - |
| `gr-fosphor` | 3.9~git20240323.74d54fc-1+b10 | 3.9~git20240323.74d54fc-1ubuntu1 | 3.9~git20230826.e02a2ea-1build3 | 3.9~git20240323.74d54fc-2+b1 | 3.9~git20240323.74d54fc-1+b10 | 3.9~git20230826.e02a2ea-1build3 | 3.9~git20240323.74d54fc-1+b10 |
| `libiio-utils` | 0.26-2 | 0.26-2build2 | 0.25-4build2 | 0.26-2+b2 | 0.26-2 | 0.25-4build2 | 0.26-2 |
| `stm32flash` | 0.7-1 | 0.7-1build1 | 0.7-1 | 0.7-1 | 0.7-1 | 0.7-1 | 0.7-1+b1 |
| `ser2net` | 4.6.4-1 | 4.6.5-1 | 4.6.0-1build2 | 4.6.5-1 | 4.6.4-1 | 4.6.0-1build2 | 4.6.4-1 |
| `qpwgraph` | 0.8.2-1 | 0.9.9-1 | 0.6.1-1build3 | 1.0.3-1 | 0.8.2-1 | 0.6.1-1build3 | 0.8.2-1 |
| `gpsprune` | 25.2-1 | 26.1-1 | 23.2-1 | 27+ds-1 | 25.2-1 | 23.2-1 | 25.2-1 (all) |
| `opencpn` | 1:5.10.2+dfsg-1 | 1:5.12.4+dfsg-1 | 5.8.4+dfsg-1build4 | 1:5.14.1+dfsg-4 | 1:5.10.2+dfsg-1 | 5.8.4+dfsg-1build4 | 1:5.10.2+dfsg-1 |

What that changed below, each noted at its row:

- **`predict` is in no target's archive**, and not in Debian 12 or
  unstable either (`apt-cache search` in `debian:12`, `debian:13` and
  `debian:sid`, 2026-09-30). The search result's "in testing" was wrong.
  Debian's packaging repository (salsa `debian-hamradio-team/predict`)
  was last touched on 2018-12-30, with an upload marked UNRELEASED. Not
  added; `satellite-tracking` stays a one-member category until a
  maintained route is found.
- **`gr-fosphor` is offered on all seven targets and is added**, but it is
  not a Blend `sdr` task member: `blend-inventory.md`, generated from the
  task files, does not list it. The row below said it was.
- **`stm32flash`: no owned device is recorded as using the STM32
  serial bootloader.** The hardware catalog's STM32 entries
  (`flipper-zero`, the `dmr-radio` class) use USB DFU (`0483:df11`),
  which is `dfu-util`'s job; NanoVNAs, named in the row below, are not
  catalogued as devices at all. The unit is added and links to no device.
- **`ser2net` starts a service on install.** Read from the Debian 13
  .deb and measured in a container: the postinst enables
  `ser2net.service`, which runs as root, and the shipped configuration
  listens on loopback ports 2000, 2001, 3000 and 3001 for `/dev/ttyS0`
  and `/dev/ttyS1`. Added, but not to `station` as the brief placed it:
  install it by name.
- **`gpsprune` is offered on all seven targets and is not added**,
  because the decision record already ruled on it: **D-061** (and the
  2026-09-28 note under D-057) says GPSPrune was measured and is not
  carried, because it uses online tiles, and the `navigation` profile's
  exclusions say the same. This report recommended it without citing
  that. Carrying it would need the maintainer to amend D-061; nothing
  here does.

## A. Cross-cutting gaps — plans the catalog has not caught up with

### A1. Station config is built and almost nobody reads it

`hammunition station set` stores callsign, grid square and node alias at
mode 0600 (D-035), and the plan defers a file whose value is missing
rather than refusing the unit. Exactly one manifest uses it. These are the
units whose first run asks for the same two values, with where each keeps
them. Every one is a candidate `config_files` block; the third column is
the risk that decides whether a block is right or a page is:

| Unit | File and keys | Shape | Risk |
|---|---|---|---|
| `direwolf` | `direwolf.conf`: `MYCALL`, `ADEVICE`, `PTT` | Whole file from the shipped example, callsign filled | Low. D-008 promised this by name. Audio device and PTT stay the operator's; a file with `MYCALL` set and the rest commented is still the right starting point |
| `pat` | `config.json`: `mycall`, `locator`, `secure_login_password` | Merge into JSON | Medium: the password must never be templated (it is not station data and is not stored), and pat rewrites its own file |
| `ax25-tools` | `/etc/ax25/axports`: the `wl2k ${MYCALL}` line 73Linux writes | Append (`append: true` exists in the schema) | Low, and already named in CLAUDE.md as the case that forced D-004 |
| `xastir`, `yaac` | Xastir's `config/xastir.cnf` (`STATION_CALLSIGN`, `STATION_LAT/LONG`); YAAC's `YAAC.conf` (`callsign`, `latitude`, `longitude`) | Whole file on first run only | Medium: both rewrite on exit; `backup_existing` covers the first run, a second install must not clobber |
| `wsjtx`, `wsjtx-improved`, `jtdx`, `mshv`, `js8call` | `WSJT-X.ini` etc.: `MyCall`, `MyGrid` under `[Configuration]` | Merge into INI | **High.** Qt writes the whole file on exit and the first-run wizard exists for a reason. Recommend a page, not a block: the settings dialog with the two fields named |
| `fldigi` (and the fl* family) | `fldigi_def.xml`: `<MYCALL>`, `<MYQTH>`, `<MYLOC>`, `<MYNAME>` | Merge into XML | High, same reason |
| `gpredict` | `~/.config/Gpredict/` QTH file: `LAT`, `LON` from the grid square | Whole file | Low. The grid-to-lat/lon conversion is four lines and the engine already has a locator |
| `cqrlog`, `klog`, `qlog`, `xlog`, `pyqso`, `tlf`, `not1mm` | Each its own; `tlf`'s `logcfg.dat` is plain text (`CALL=`, `MYLOCATOR=`) | `tlf` whole file; the GUI loggers a page | Low for `tlf`; the others run a wizard |
| `aprx`, `uronode`, `linpac`, `fbb` | Plain-text configs with a callsign line | Whole file | Low; same class as `linbpq` |
| `hamclock-next`, `openhamclock` | Grid square on first run | A page | The value is entered once in a GUI |

**Recommendation.** Write the blocks for the low-risk plain-text units
(`direwolf`, `ax25-tools`, `gpredict`, `tlf`, `aprx`, `uronode`, `linpac`,
`fbb`), in that order, each behind the D-035 deferral. For the Qt and
XML units, a page: the *digital-modes* guide (A9), section "Enter your
callsign and grid once", with the dialog path for each program. Do not
template a password anywhere; `pat`'s block sets `mycall` and `locator`
and leaves the password key absent, and the plan says so.

### A2. The rig is not station data, so every program is configured separately

D-042 approved reimplementing ETC's rig model as catalog data and named it
sub-project work. Nothing has started. What the model needs, in this
project's shape:

1. **A `rig` hardware class** (`catalog/hardware/classes/`), alongside
   `gps-receiver` and `dmr-radio`: the USB-serial CAT interface, its
   `dialout` membership, and the D-028 warning that a CP2105 or FTDI
   identifier names a chip, not a radio. The maintainer's FT-991A
   enumerates as a CP210x pair (audio on a separate USB audio class device).
2. **Station fields:** `rig` (a hamlib model number or name),
   `rig_device` (a `/dev/serial/by-id/` path, never `/dev/ttyUSB0`),
   `rig_baud`. All three are D-035 values: missing defers, nothing guesses.
3. **One `rigctld`, shared.** `libhamlib-utils` gains a systemd *user*
   service (`~/.config/systemd/user/`, `scope: user`) running
   `rigctld -m <rig> -r <device> -s <baud>`, and every CAT-capable unit's
   page says "Hamlib NET rigctl, localhost:4532". `flrig` is the
   alternative for operators who prefer it and is already carried; the
   guide states the trade-off (flrig has the panel, rigctld has no UI and
   no conflicts).
4. **`ser2net`** (apt, `unmeasured`) for the rig on another machine, the
   same service in reverse. One unit, `serial-terminals`.

**Recommendation.** Do 1 to 3 as one sub-project after A1, since the
service is a `config_files` block plus a `system_modifications` entry the
schema does not yet have (a user service is neither a group nor a pin).
Record the new `kind` in D-035's amendment.

### A3. Audio routing has no unit, no guide and no troubleshooting entry

Every digital mode needs the radio's audio in and out of the program, and
on every 2026 target that is PipeWire. What is missing:

- **A patchbay.** `qpwgraph` (apt on every target that ships PipeWire;
  `unmeasured`) is the program an operator uses to see which device WSJT-X
  is actually listening to. `pavucontrol` is the fallback. One unit,
  tagged `device-support`, in `digital-modes` and `station`.
- **Virtual cables.** SDR-to-decoder (SDR++ audio into WSJT-X, gqrx into
  fldigi) needs a loopback: `pw-loopback` or a `libpipewire-module-loopback`
  stanza under `~/.config/pipewire/pipewire.conf.d/`. That is a
  `config_files` block with `scope: user` — and a known failure to record:
  JS8Call-improved and Qt6 WSJT-X builds do not list PipeWire virtual
  devices as inputs on some systems (upstream issue #120, reported on Arch
  with PipeWire), with the ALSA `snd-aloop` route as the workaround.
- **The audio level page.** Direwolf's manifest already says transmit
  level is the biggest cause of a station that is heard by nobody; the
  same is true of every mode and nothing says it in one place.

**Recommendation.** A new guide, *audio-routing*, under `docs/guides/`, first (it is the page
the documentation standard requires), then the `qpwgraph` unit, then the
loopback block as a `digital-modes` profile option once the Qt6 input bug
has been measured on the field laptop.

### A4. GPS time: `gpsd` is installed and the clock ignores it

The `station` profile's summary is "rig control, time, position", and it
installs `gpsd`. Nothing connects `gpsd` to the system clock. On the
field laptop with the network down — the case D-057 was written for —
FT8, FT4, JS8 and WSPR all need the clock within about a second, and a
laptop's RTC drifts past that in days.

- **`chrony`** with `refclock SHM 0 refid GPS` (or the SOCK refclock,
  which chrony's own documentation prefers over SHM for permissions) and
  `refclock PPS /dev/pps0 lock GPS` where the receiver has PPS. Debian 13
  installs `systemd-timesyncd` by default; whether Parrot, Kali and the
  Ubuntu targets ship `chrony` already is `unmeasured` and matters (D-022:
  coexist and disclose, never remove silently — replacing timesyncd is a
  disclosed system modification).
- The receiver itself: `ubxtool` is already carried in `gpsd-clients`.
  **PyGPSClient** (PyPI, BSD-3, tkinter; the u-center replacement that
  configures u-blox receivers' output protocols and rates, plus NTRIP for
  RTK) is a `venv` unit for the `gps-gnss` tag.
- The field laptop's planned GNSS module (CLAUDE.md: not fitted) is the
  measurement rung; a USB puck is the meantime. `docs/reference/bench-verification-5430.md`
  is where the result goes.

**Recommendation.** A `chrony` manifest with one `config_files` block and a
`system_modifications` entry naming the timesyncd displacement, in
`station`; a troubleshooting entry "my FT8 decodes nothing: check the
clock" in `docs/troubleshooting/running.md`.

### A5. The terrain layer D-061 built serves one reader and could serve four

D-061 fetches Copernicus GLO-30 tiles, hashed and verified, for QMapShack's
contours. Three carried units want the same elevation data and get none:

| Unit | What it reads | Route from the GLO-30 tiles |
|---|---|---|
| `splat` | SDF files made by `srtm2sdf` / `srtm2sdf-hd` from SRTM `.hgt` | `gdal_translate -of SRTMHGT` per tile, then `srtm2sdf-hd`; a `derived` converter (`splat-sdf`) beside `gdal-dem` |
| `xastir` | GeoTIFF or DRG topo layers | GDAL already carried (`gdal-bin`); a `derived` converter producing the tiled GeoTIFF Xastir reads |
| `signal-server` (candidate, below) | SPLAT's SDF | Same converter as `splat` |
| `gpredict`, `hamclock-next` | Nothing — but a horizon mask from the DEM is what a satellite station actually wants | Post-1.0 |

**Recommendation.** One converter, `splat-sdf`, in the `derived` method's
enum, and `splat` and `signal-server` become readers of the station's
regions the way QMapShack is. It closes "propagation prediction with no
network", which the `propagation` profile page currently cannot promise.

### A6. Offline reference data the D-049 shape can now carry

D-049 gave the catalog a `data` method; D-057 gave it regional and dated
fetches. `country-files` (cty.dat) is carried. Two more belong in the same
shape and are missing:

- **The FCC amateur licence database.** `l_amat.zip` from
  `data.fcc.gov/download/pub/uls/complete/`, regenerated every Sunday,
  public domain, on the order of 200 MB. Every carried logger does its
  lookups against QRZ or HamQTH over the network; with this file on disk,
  a US station can look up any callsign with the network down. The
  file's freshness is D-057's `weekly` case, not a pin. What reads it is
  the open question: `cqrlog` and `klog` have no offline-callbook
  importer, so the first reader would be a small tool of ours
  (`references`) or a documented `sqlite` recipe.
- **Band plans and a repeater directory.** An ARRL band-plan chart is
  data with a licence to check. RepeaterBook's export is *not* freely
  licensed and cannot be a data unit; the retired 73Linux `REPEAT` entry
  was a client for it, and that ruling stands. Note the gap, carry
  nothing.

### A7. Kismet: the blocker moved and the profile did not notice

`catalog/profiles/rf-security.yaml` says Kismet "is held back until the
third-party apt repo path is implemented rather than shipped as a profile
that half-installs." D-040 implemented that path on 2026-09-03, with
`code` and `codium` as its exercised cases. Kismet is apt on Kali and
Parrot, and elsewhere comes from its own signed repository with Debian 13
packages (the project refreshed its signing key in February 2026 for the
new apt signature requirements — the fingerprint in a manifest must be
the *current* one, read from the key, per `src/hammunition/openpgp.py`).
The maintainer's CatSniffer V3 is a Kismet datasource (Zigbee and BLE),
so the device page and the unit belong together.

**Recommendation.** A `kismet` manifest: apt block selected for Kali and
Parrot, `apt_repos` block elsewhere, `rf-security` profile; update the
profile's `deliberately_excludes` prose in the same commit.

### A8. Waiting items whose blocker has changed since they were written

| Item | Recorded as | What changed | Recommendation |
|---|---|---|---|
| `ARDOPGUI` | CARRY, post-1.0 (parity-coverage) | `ardopcf` 1.0.4.1.2 added a built-in browser GUI (`ardopcf -G 8514`, then `localhost:8514`); the catalog carries 1.0.4.1.3 | SUPERSEDE by `ardopcf` itself; the packet profile page documents the flag, as it does `pat http` |
| Morse Runner | Reserved to maintainer, conditional: "if Morse Runner CE builds, that is carried and Wine leaves 1.0" | Morse Runner Community Edition (`w7sst/MorseRunner`, Lazarus/Free Pascal) has a Linux port and 1.86 in preparation as of September 2026 | Test the build on Debian 13 (Lazarus is apt: `lazarus`, `fpc`); carry on success under `morse-training`, which settles the conditional |
| `chattervox` | The one NEEDS-DECISION unit | Last release 0.7.0 (2020); README last touched 2019; prior-art.md already lists it dead | RETIRE, world-changed/abandoned, on a D-032 head-commit check — the same verdict `prior-art.md` reached, not yet applied to `dispositions.md` |
| `tar1090` | "documented gap rather than a shim" (readsb's manifest) | Unchanged upstream: a `curl \| bash` installer. But what it installs is static files plus a lighttpd or nginx stanza and a systemd unit — nothing a pinned `git` unit with `install_tree` and a `config_files` block cannot express | A `tar1090` manifest from a tagged release, serving under lighttpd; the web-server dependency is disclosed |
| `dream` | REVIVE, blocked on `libqt5webkit5-dev` | Unchanged; the question in `not-carried.md` (is WebKit only the optional dashboard?) still needs the source read | No change |
| `FoxTelem` | Post-1.0 pending an AMSAT census | Unchanged | No change |
| VARA / VARIM | Post-1.0, Wine prefix | **Mercury** (below) is an open VARA-API-compatible modem released May 2026; the case for a Wine prefix is weaker | Re-rank after Mercury is measured |

### A9. The guides the standard requires do not exist

CLAUDE.md names `docs/guides/` as "task-oriented: digital modes, APRS,
satellite, packet, SDR" and sets the bar at a licensed ham reaching a
working digital-modes station from a fresh Parrot install without asking
anyone. Four guides exist under `docs/guides/` (conference operating, offline navigation,
propagation, Rayhunter); the five named ones do not. The profile pages
carry good `manual_configuration` prose but no walk-through. The order
that serves the standard (each a new page under `docs/guides/`):

1. *digital-modes* — rig, audio (A3), time (A4), the
   callsign dialogs (A1), the first FT8 decode, the first QSO.
2. *packet* — Direwolf's file, KISS to pat, `pat http`,
   the first Winlink message; ARDOP with its web GUI.
3. *aprs* — Direwolf as the modem, Xastir or YAAC, the
   iGate decision (the Direwolf manifest already says why it is a decision).
4. *satellite* — gpredict, TLEs, Doppler over `rigctld`, a
   rotator over `rotctld`, SatDump for the images.
5. *sdr* — which receiver for which job (the
   `overlaps.md` verdicts, as a page), the first decode with each carried
   decoder.

Each guide is also where the A1 "type it once" instructions live for the
programs that get a page rather than a block.

## B. Per-category findings

Abbreviations in the *route* column: **apt** (a distribution package;
`unmeasured` means no target sweep yet), **source**, **git**, **binary**,
**venv**, **data**, **apt_repos** (D-040), each an existing backend. Every
candidate needs a D-032 liveness check, a licence check
(`docs/reference/licence-verification.md`'s shape) and the archive sweep
before a manifest. Nothing here is transmit-capable except where said.

### Group 1 — Operate the Station

| Category | Carried | Candidate | What it adds | Route | Recommendation |
|---|---|---|---|---|---|
| `rig-control` | 12 | **piHPSDR** (`g0orx/pihpsdr`, DL1YCF and G0ORX, GPL-3.0; issues active September 2026) | The operator program for OpenHPSDR protocol 1 and 2 radios: ANAN and the **Hermes Lite 2**, which has one of the largest homebrew-SDR communities there is. `gr-hpsdr` is carried and gives those owners a GNU Radio source and nothing to operate with | source (make) | ADD, `rig-control` + `sdr-receivers`; `deskhpsdr` (DL1BZ) is the desktop-oriented fork and the `overlaps.md` row |
| `rig-control` | | `rigctld` as a service; `ser2net` | See A2 | config + apt | A2 |
| `rig-control` | | *Documentation gap:* the maintainer's own **FT-991A** is not in CHIRP (chirpmyradio issues 6685, 7987, 9073: no developer with the radio) and is programmed by Yaesu's Windows-only ADMS-991A; the **BTECH UV-50PRO** has no CHIRP driver and is programmed only through BTECH's Bluetooth phone app | — | — | Say so on the `chirp` page's `known_problems` and on a `hardware/` page for each radio; both radios are CAT-controllable through hamlib (`3073` for the FT-991), which is the part that matters for the station |
| `logging` | 13 | — | Coverage is complete against every source; the gap is offline lookup (A6) | | No add |
| `contest` | 5 | `so2sdr` (N4OGW, GPL-3.0; apt `unmeasured`) | An SO2R-capable contest logger with a Linux-native GUI, the shape `not1mm` and `tlf` do not have | apt | Measure the sweep; ADD if in Debian 13 |
| `dx-cluster` | 2 | — | The Reverse Beacon Network is a cluster feed and needs a page, not a unit | | A sentence in the DX-cluster pages |
| `time-frequency` | 3 | `chrony` | See A4 | apt + config | A4 |
| `gps-gnss` | 7 | **PyGPSClient** (PyPI `pygpsclient`, BSD-3; NMEA, UBX, RTCM3, NTRIP) | Receiver configuration with a GUI; the u-center replacement | venv | ADD |
| `gps-gnss` | | `gpsprune` (apt, in trixie per the search result; measured 2026-09-30: all seven targets), `gpxviewer` (trixie), `foxtrotgps` (sid) | Track viewing and editing; `gpsbabel` converts but shows nothing | apt | ~~ADD `gpsprune`~~ Not added: **D-061** measured it and does not carry it (see *Measured since*); `foxtrotgps` is online-first and adds nothing over Navit |
| `gps-gnss` | | `rtklib` (RTK and PPK post-processing; apt `unmeasured`) | Centimetre positioning for antenna surveys | apt | Post-1.0 on demand |
| `navigation-maps` | 14 | **OpenCPN** (Debian 13 `1:5.10.2+dfsg-1` per the search result, confirmed by the 2026-09-30 sweep, which found it on all seven targets; GPL-2.0) | A marine chart plotter that takes position from `gpsd` and AIS targets from `rtl-ais` or `ais-catcher` over NMEA — the one program that makes the `ships` category more than a decoder. Charts are data: NOAA ENC and RNC are public domain and fetched by region, the D-057 shape again | apt now; charts as a `data`/regional unit later | ADD, tagged `ships` + `navigation-maps` (added 2026-09-30, `navigation`); charts a follow-on |
| `navigation-maps` | | Organic Maps (Linux desktop: a Qt 6 source build the project says needs 20 GB and has no feature parity; Flathub only) | Turn-by-turn on the desktop with a modern UI | none acceptable today (Flatpak is a measured zero, D-014) | Not carried; revisit if a distribution packages it |
| `navigation-maps` | | `qgis`, `kiwix`, `dict`, `mbtileserver` | Already waiting on ETC sub-project 5 | | No change |
| `locators`, `dashboards` | | — | | | No add |

### Group 2 — Digital Modes & Morse

| Category | Carried | Candidate | What it adds | Route | Recommendation |
|---|---|---|---|---|---|
| `weak-signal` | 8 | — | Coverage complete. `wsprdaemon` is a KiwiSDR/RX888 appliance, not a station program; not carried | | No add |
| `keyboard-modes`, `nbems` | 6, 5 | — | Complete (`linpsk` is dead: last in buster) | | No add |
| `digital-voice` | 2 | **FreeDV 2.x with RADEV1** | The catalog's `freedv` is apt **1.8.11**; the neural RADE mode that made FreeDV competitive with SSB shipped in 2.0 (January 2025) and 2.2.x (2026), and is not in any target's archive. Upstream's Linux route is an AppImage (refused by name) or a build script | source (cmake, with the RADE dependencies) | ADD as a second block or a `freedv-rade` unit; the apt one stays for operators who want the packaged version |
| `digital-voice` | | **DroidStar** (`nostar/DroidStar`, AD8DP, GPL-3.0; Linux `.deb` and AppImage from the 9M2PJU distribution) | DMR, D-STAR, YSF, P25, NXDN and **M17** over reflectors with no radio; the built-in vocoders are the point. Gives the M17 roadmap (D-007) something to run today while `mvoice` is blocked | binary (`.deb`, pinned and hashed) or source (Qt) | ADD; state that reflector traffic is transmit in the network sense and needs a callsign registration, not a consent gate |
| `digital-voice`, `sdr-receivers` | | **QRadioLink** (Codeberg, GPL-3.0; needs GNU Radio 3.10, Qt 5.15; upstream Debian 12 `.deb`s only) | A full SDR transceiver with Codec2/Opus digital voice for Pluto, LimeSDR, USRP; transmit-capable | source (qmake) | ADD post-1.0, consent-gated on transmit (D-021) |
| `sstv-atv` | 3 | `hamfax` (apt; radiofax), `slowrx` (SSTV receive-only), `leansdr` (DATV receive; all `unmeasured`) | `xwefax` already covers fax; `qsstv` covers SSTV both ways | apt | Low; measure and ADD only where the sweep finds them |
| `echolink-repeaters` | 6 | — | Track B (D-046) | | No change |
| `cw`, `morse-training` | 17, 10 | Morse Runner CE | See A8 | source (Lazarus) | Test the build |

### Group 3 — Packet, Mesh & Emergency Comms

| Category | Carried | Candidate | What it adds | Route | Recommendation |
|---|---|---|---|---|---|
| `soundcard-modems`, `winlink` | 8, 4 | **Mercury** (Rhizomatica, GPL-3.0, C; released May 2026; Debian binaries and source) | An open HF OFDM ARQ modem that speaks **VARA's TCP API**, so `pat` (which already supports VARA) uses it unchanged. Rhizomatica's own comparison has it level with VARA HF at good SNR and ahead in noise. The first free answer to the VARA gap this project deferred post-1.0 | source | ADD to the packet core; it re-ranks VARA (A8). Transmit-capable in the ordinary station sense, like `ardopcf` |
| `soundcard-modems`, `winlink` | | **FreeDATA** (`DJ2LS/FreeDATA`, GPL-3.0; v0.17.x, active July 2026; codec2 modems, server plus GUI client) | Messaging and file transfer over HF with its own protocol and station-to-station chat; not Winlink | source or venv (the server is Python) | ADD, `winlink`-adjacent under `soundcard-modems`; pair with Mercury in one `overlaps.md` row |
| `soundcard-modems` | | `soundmodem` (Thomas Sailer; apt `unmeasured`) | The other soundcard modem; Direwolf superseded it in practice | apt | Not carried unless asked |
| `packet-nodes`, `winlink` | 8, 4 | **`rmsgw`** (`nwdigitalradio/rmsgw`, GPL with one binary-only library; last commit December 2024) | The Linux Winlink RMS gateway — the category summary promises "gateways" and none is carried. A gateway needs Winlink sysop authorisation and a password, which is a secret, not station data | source (autotools) | ADD post-1.0, with the note that the password is entered by the operator and never templated (A1) |
| `packet-nodes`, `aprs` | | `aprsc` (APRS-IS server; apt `unmeasured`) | Running your own APRS-IS server; niche | apt | On demand |
| `winlink` | | `ARDOPGUI` | See A8: `ardopcf` now has it built in | | SUPERSEDE |
| `mesh` | 2 | Reticulum, MeshCore, `meshtasticd`, `tncattach`, PlatformIO | All in issue #105 (track C) | | No change here |
| `emcomm`, `weather-sensors` | 9, 4 | **EAS/SAME alerts from NOAA Weather Radio** | `multimon-ng` (carried) decodes EAS; `dsame3` (Python 3 fork of `dsame`) turns the header into readable text and can run a command. `rtl_fm` to `multimon-ng -a EAS` to `dsame3` is the whole pipeline and it is exactly what an EMCOMM laptop should be doing in the background with the network down | venv for `dsame3` (licence to check), plus a page | ADD the page first; the unit follows |
| `weather-sensors` | | `weewx` (own signed apt repository; not in Debian, which has only `indi-weewx-json`) | Weather-station software for fifty station models, many of which `rtl-433` already hears | apt_repos (D-040) | Post-1.0 on demand |
| `email-clients` | 5 | — | | | No add |

### Group 4 — SDR & Listening

| Category | Carried | Candidate | What it adds | Route | Recommendation |
|---|---|---|---|---|---|
| `sdr-receivers` | 10 | **OpenWebRX+** (`luarvique`; signed repository with Debian 13 packages) | A multi-user web receiver: share one SDR with the whole EMCOMM room, or with yourself on a phone. Also the missing half of the Skywave on-ramp — Skywave's users connect to servers like this one | apt_repos (D-040) | ADD post-1.0; the server-on-a-laptop case needs a page on what it exposes |
| `sdr-receivers` | | **ka9q-radio** (Phil Karn; GPL; RTL-SDR, Airspy, Funcube, RX888, optionally Fobos, HydraSDR, HackRF, BladeRF) | Demodulate every channel in a band at once; `radiosonde-auto-rx` (carried) documents running on top of it | git (untagged? — D-024 check needed) | Post-1.0; measure the pin source first |
| `sdr-receivers` | | `kiwiclient` | Already in `skywave-inventory.md` as the maintained KiwiSDR client | venv | ADD, cheap |
| `sdr-hardware` | 33 | **HydraSDR RFOne** (`libhydrasdr` 1.1.1, `SoapyHydraSDR`, `hydrasdr_433`; the 2025–26 Airspy successor; not in any archive) | A device the catalog has no entry for at all: hardware class entry, host library, Soapy module | source (cmake) ×2 | ADD a device and two units when a unit of hardware is available to measure; `maintainer_verified: false` until then (D-027) |
| `sdr-hardware` | | **Fobos SDR** (`rigexpert/libfobos`, `SoapyFobosSDR`; the vendor of `antscope2`, already carried) | Same shape as HydraSDR | source ×2 | Same |
| `sdr-hardware` | | `libiio-utils`, `iio-oscilloscope` (apt; libiio is in trixie per the search result; measured 2026-09-30: `libiio-utils` on all seven targets) | The PlutoSDR's own tools; the device page already says the Pluto is "reached through libiio" and nothing installs it | apt | ADD `libiio-utils` beside the Pluto device (added 2026-09-30) |
| `sdr-toolkits` | 12 | `gr-fosphor` (trixie `3.9~0.974ab2f-1+b15` per the search result; measured 2026-09-30: `3.9~git20240323.74d54fc-1+b10`, all seven targets) | The GPU waterfall every GNU Radio demo uses; ~~a Blend `sdr` task member~~ not in the Blend's task files (`blend-inventory.md`), and not in the catalog | apt | ADD (added 2026-09-30) |
| `sdr-toolkits` | | `gr-dab`, `gr-ais`, `gr-iqbal` (`unmeasured`) | Tier 3 governs the rest | apt where packaged | Measure; ADD only the packaged ones |
| `signal-analysis` | 4 | URH, SigDigger | DragonOS Tier 2 (SCOPE.md stage 7) | | No change |
| `signal-analysis`, `broadcast` | | `redsea` (RDS decoder, CLI; apt `unmeasured`) | The command-line RDS decoder beside `gr-rds` | apt | Measure; ADD if packaged |
| `broadcast` | 7 | **nrsc5** (`theori-io/nrsc5`, GPL-3.0; cmake) with **NRSC5 Studio** (Rust GUI, June 2026, Linux) | HD Radio — the only digital broadcast standard in North America, and the catalog has DAB twice and HD Radio not at all | source | ADD `nrsc5`; the GUI once it has a tagged release |
| `broadcast` | | Qt-DAB (JvanKatwijk; active 2026; source build by script) | A third DAB decoder beside `welle-io` and `dablin` | source | Not carried; two DAB decoders is enough (SCOPE.md: "four ADS-B decoders and no opinion") |
| `aircraft` | 10 | **dump978-fa** (FlightAware; C++ over SoapySDR; `.deb` built from source with debhelper) | **978 MHz UAT**, the second ADS-B link, used by US general aviation below 18,000 ft. The category has 1090 MHz three ways and 978 not at all | source (cmake) | ADD; US-only relevance stated on the page |
| `aircraft` | | `tar1090` | See A8 | git | ADD as described |
| `aircraft` | | `piaware` / `dump1090-fa` (FlightAware apt repository), the adsb.fi and ADS-B Exchange feeders | Feeding a network is the operator's choice and each network has its own client; `mlat-client-adsbfi` is carried | apt_repos | A page listing the feeders, no more units |
| `aircraft` | | JAERO, OGN (`ogn-rf`) | Tier 2; low | | No change |
| `ships` | 4 | OpenCPN (measured 2026-09-30: all seven targets) | See Group 1 | apt | ADD (added 2026-09-30, `navigation`) |
| `ships` | | *Gap:* NAVTEX is decoded by `fldigi` (carried) — say so on the page. No open DSC decoder exists | — | — | A sentence; nothing to carry |
| `pagers-decoders` | 3 | — | | | No add |

### Group 5 — Satellites & Propagation

| Category | Carried | Candidate | What it adds | Route | Recommendation |
|---|---|---|---|---|---|
| `satellite-tracking` | **1** | **`predict`** (KD2BD, GPL-2.0; apt, in testing per the search result — **wrong: in no archive, measured 2026-09-30**, see *Measured since*) | The one-member category. PREDICT is the terminal tracker `gpredict` grew from, runs headless with a network server other programs poll, and is what a Pi ground station uses | ~~apt~~ none packaged | ~~ADD~~ Not added: no target offers it |
| `satellite-tracking` | | **SatNOGS client** (2.1.1, December 2025; pip; needs hamlib and gpsd Python bindings) | Turns the station into a ground station for the network — the open-source satellite community's own project | venv | ADD post-1.0 as an appliance unit; needs a page on what it uploads |
| `satellite-tracking` | | `rotctld` configuration | `libhamlib-utils` carries it; nothing configures a rotator | config + page | Part of A2 |
| `satellite-decoding` | 3 | `goestools` (`pietern/goestools`; GOES HRIT/LRIT) | SatDump (carried) decodes GOES; goestools' `goesrecv` is still the community's lock-and-signal-strength tool for aiming a dish | source (cmake) | Optional; a note on the SatDump page is enough until asked |
| `propagation` | 7 | **Signal-Server** (Cloud-RF, the multi-threaded SPLAT fork; carried by DragonOS) | Coverage maps in minutes instead of hours, from the same terrain (A5) | source (make) | ADD with the `splat-sdf` converter |

### Group 6 — Antennas, Bench & Programming

| Category | Carried | Candidate | What it adds | Route | Recommendation |
|---|---|---|---|---|---|
| `antenna` | 10 | `necpp`, `linsmith`, `transcalc`, `antennavis`, `meep`, `openems` | The Blend's `electronics-radio-dev` metapackage *recommends* antennavis, gsmc, meep, nec2c, openems, transcalc, xnec2c, yagiuda and *suggests* linsmith, qucs, xsmc-calc; the catalog carries that metapackage with `install_recommends` at the default, so the recommended ones already arrive **without a manifest, a page or a menu entry** | apt | Give each Recommends member its own manifest so the menu and the package reference see them; `xnecview` is dead (last in bullseye) |
| `antenna-analysers` | 3 | **LibreVNA GUI** (`jankae/LibreVNA`, GPL-3.0; 1.6.5; Qt; Ubuntu binary and source) | The open-hardware VNA that `nanovna-saver` does not speak to | source (qmake/cmake) | ADD |
| `spectrum-analysers` | 2 | — | `hackrf_sweep` is in `hackrf`; the RF Explorer's Python library is niche | | No add |
| `electronics` | 6 | The other Blend electronics metapackages: `electronics-pcb` (KiCad), `electronics-simulation` (ngspice, Qucs-S), `electronics-microcontrollers`, and `sigrok`/`pulseview` | The catalog carries one Debian Electronics task; the bench needs three more, in the same metapackage shape | apt | ADD the metapackages, not the members |
| `radio-programming` | 4 | **`k5prog`** (`sq5bpf/k5prog`, GPL; C) and the UV-K5 CHIRP drivers (`egzumer`, `armel/F4HWN`) | The Quansheng UV-K5 is the most-modified handheld of the decade; `chirp` (carried) programs it only through a firmware-specific driver, and flashing custom firmware on Linux is `k5prog` | source (make); the CHIRP driver is a file the page points at | ADD `k5prog`; page on the driver |
| `radio-programming`, `dmr` | | **OpenRTX `radio_tool`** | Flashes OpenRTX (M17-capable) onto TYT MD-UV380/390 and others from Linux; D-026 says carry the means of talking to the device | source (cmake) | ADD |
| `radio-programming` | | `editcp` (AnyTone) | `qdmr` covers AnyTone; editcp is dormant | | Not carried |
| `programmer` | 8 | `stm32flash` (trixie; measured 2026-09-30: 0.7 on all seven targets), `teensy-loader-cli` (trixie), `dfu-programmer`, `bossa-cli`, `picotool`, `mspdebug` (`unmeasured`) | STM32 serial bootloaders are how MMDVM boards, NanoVNAs and many radios are flashed; RP2040/RP2350 boards need `picotool` | apt | ADD `stm32flash` (added 2026-09-30) and `picotool` first; the class file is generated (`gen_programmer_class.py` reads the rules) |
| `programmer` | | **`adafruit-nrfutil`** (PyPI) and a UF2 note | The maintainer's nRF52840, T-Echo and RAK nodes all flash by UF2 drag-and-drop or `adafruit-nrfutil dfu serial`; nothing in the catalog says so | venv + page | ADD, with the Meshtastic device page carrying the UF2 procedure |
| `programmer` | | **`cc2538-bsl`** and `catnip` (Electronic Cats) | The CatSniffer V3's firmware loader; Electronic Cats' own docs prefer `catnip`, and Kismet's page says `cc2538-bsl` worked and `catnip` did not in their testing | venv (pyserial, intelhex) | ADD `cc2538-bsl` on the CatSniffer page; the device is owned, so this is measurable now |
| `programmer` | | `pyocd`, `platformio` | `pyocd` for nRF and STM32 over SWD; PlatformIO is the Meshtastic/MeshCore build tool (#105) | venv | On demand |
| `serial-terminals` | 5 | `ser2net` (measured 2026-09-30: all seven targets) | See A2 | apt | ADD (added 2026-09-30, in no profile: see *Measured since*) |
| `device-support` | 8 | `qpwgraph` (measured 2026-09-30: all seven targets), `pavucontrol` | See A3 | apt | ADD (`qpwgraph` added 2026-09-30, `digital-modes`) |

### Group 7 — RF Security & Research

Out of this pass except: **A7 (Kismet)**, the CatSniffer loader above, and
one observation for the record — the maintainer's owned devices in this
group (CatSniffer, Minino, Free-WiLi 2, Clip-Boy, C5 Wardriver) each have
a `hardware/` page, and none yet lists the *software* that talks to it
beyond the flasher. That is a per-device page task under D-029, not a
catalog gap.

### Group 8 — Learn & Practise

| Category | Carried | Candidate | Recommendation |
|---|---|---|---|
| `exams` | 3 | — | Complete for US and Canada; a UK (RSGB) or Australian source would be an ADD on request |
| `morse-training` | 10 | Morse Runner CE | A8 |
| `references` | 2 | FCC ULS (A6); `kiwix`, `dict` (sub-project 5) | A6 |

### Group 9 — Workstation

No gaps. `usbip` (sharing a USB SDR or rig to another machine over the
network, in `linux-tools`) would be a page under troubleshooting, not a
unit.

## C. Thin categories, for the record

A category with one or two members is not wrong — the vocabulary is cut
fine on purpose (D-055) — but each is worth a glance:

| Category | Members | Note |
|---|---|---|
| `satellite-tracking` | 1 | SatNOGS above; `predict` is in no archive (2026-09-30) |
| `dx-cluster` | 2 | Complete |
| `locators` | 2 | Complete |
| `mesh` | 2 | Issue #105 |
| `digital-voice` | 2 | FreeDV 2.x, DroidStar, QRadioLink above |
| `spectrum-analysers` | 2 | Complete for the carried hardware |
| `references` | 2 | A6 |
| `dmr` | 2 | `radio_tool` above |

## D. Recommended order

Ranked by how many operators hit the gap on the first evening, against
the cost:

1. **A3 + A9.1** — the audio-routing guide and the digital-modes guide.
   Documentation only; unblocks the standard.
2. **A1** — `config_files` for the eight plain-text units; `direwolf`
   first, because D-008 promised it by name.
3. **A4** — `chrony` in `station`. One manifest, one page.
4. **A7** — Kismet, and fix the stale prose.
5. **Mercury and FreeDATA** — the open HF-modem pair; re-rank VARA after.
6. **`predict`, `gr-fosphor`, `libiio-utils`, `stm32flash`, `ser2net`,
   `qpwgraph`, `gpsprune`, OpenCPN** — apt units, one PR each, after the
   sweep confirms them. (2026-09-30: swept, see *Measured since*;
   `predict` is in no archive and is not added; `gpsprune` is not added
   because D-061 rules it out.)
7. **A2** — the rig as station data. A sub-project with a spec, like the
   navigation ones under `docs/superpowers/specs/`.
8. **A5** — the `splat-sdf` converter and Signal-Server.
9. **A8** — the three re-rulings: ARDOPGUI, Morse Runner CE, Chattervox.
10. **Source-built adds** — piHPSDR, FreeDV 2.x, DroidStar, dump978-fa,
    nrsc5, LibreVNA, k5prog, radio_tool, tar1090; each a pinned build
    with a D-032 check first.
11. **Hardware without hardware** — HydraSDR and Fobos entries wait for a
    unit to measure with (D-027).

What needs the maintainer, and only the maintainer, is in **Q-022**.
