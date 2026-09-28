<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Changelog

One entry per release, written from the merged pull requests, each line
naming the PR and the decision it rests on. Decisions are authoritative in
`docs/DECISIONS.md`; this file is the map from a version to them.

## Unreleased

Nothing yet.

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
