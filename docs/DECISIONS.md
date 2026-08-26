# Hammunition — Decision Record

Decisions settled by evidence. Each entry names what was decided, what decided
it, and what it closes. Supersedes anything in `CLAUDE.md` or `DESIGN.md` that
disagrees.

Amendments are appended and dated rather than rewritten, so the reasoning trail
survives. Where an amendment supersedes the original text, it says so.

`PARITY-POLICY.md` governs per-unit disposition (CARRY / SUPERSEDE / REVIVE /
RETIRE / ADD) and carries the M5 exit criteria. Where it and D-005 differ, it
wins — see the D-005 amendment.

---

## D-001 — 73Linux is an inventory source, not a base

**Decided:** Do not fork, port, or build on 73Linux. Treat it as a second
inventory source alongside AHRL.

**Evidence:** No LICENSE or COPYING in the repo, no header on `73.sh`, GitHub's
license API returns null. Default copyright applies — all rights reserved.
GitHub's ToS grants the right to view and fork on GitHub and nothing else.
This is a weaker position than AHRL, which at least carries GPL-3.0-or-later
headers on its installer.

Architecturally it is also the thing our inventory argued against: a `.bapp` is
executable bash with a metadata header. It supplies five easy fields (id, name,
description, website, version string); every hard field still lives inside the
imperative `INSTALL()` body where it cannot be queried, dry-run, diffed, or
consumed by a non-executing tool.

**Closes:** "Could we build on 73Linux?" — no.

**Action:** If we ever want the option open, one email to Jason (KM4ACK) asking
him to add a license file. Cheap, and it either unblocks or closes cleanly.

---

## D-002 — Architecture is a first-class selector, day one

**Decided:** `arch` is a structural selector in the manifest schema, present from
M1. Not deferred, not retrofitted.

**Evidence:** Nine AHRL units are arch-conditional; arch conditionals are
threaded throughout. 73Linux ships arch-partitioned trees (`app/stable/pi/`,
`app/stable/x86_64/`) from the start. Two independent projects in this niche both
treat arch as structural.

The cost of retrofitting is visible in AHRL's `install_gspiceui`, which hardcodes
an `aarch64-linux-gnu` path on all architectures and leaves a dangling symlink on
x86_64.

**Closes:** `DESIGN.md` §8 open question on ARM-as-day-one. Answer: yes.

---

## D-003 — Profiles are flat tags with overlap, not a tree

**Decided:** Packages carry a list of categories/profiles. Profiles do not nest
or depend on other profiles.

**Evidence:** AHRL's menu categories overlap heavily but never nest — 14 programs
appear in two or three. NBEMS is a 4-entry subset of Digital_Modes;
ARRL_Teachers_Institute deliberately cuts across six other categories. The one
nested case (Documentation → Command_Line_Docs) is a doc menu, not a software
grouping. 73Linux uses a flat checklist. These are tags, not a tree.

**Closes:** `DESIGN.md` §15.1.

---

## D-004 — Source builds are the core engineering problem, not an edge case

**Decided:** The source-build backend and its verification story are first-class
M3 scope, sized accordingly.

**Evidence:** 57 of 95 AHRL install units are not apt-installable — 35 source
builds from bundled tarballs, 9 prebuilt binaries and data archives, 4 Python
venv/pipx, 2 Python-run-in-place, 3 infrastructure, 2 launcher-only, 1 network
git clone, 1 remote script piped into bash.

An apt-only tool covers 40% of the parity target. The non-apt packages are
precisely the ones users cannot easily install themselves — the reason to exist.

**Consequence:** We must build and maintain our own pin/hash database. AHRL ships
zero checksums across 63 archives plus three unpinned network fetches, and
73Linux discovers tarballs by scraping web directory listings. Neither upstream
gives us anything to inherit. Sourcing and verifying every non-apt artifact is a
named sub-project, not a field in a YAML file.

### Amendment, 2026-08-25 — backend list corrected by measurement

The original entry inherited a candidate backend list from `CLAUDE.md` and
`DESIGN.md` without checking it. Verified counts across all 3,911 lines of
`bin/install_ahrl`:

| Backend | Occurrences in AHRL v27 | Verdict |
|---|---:|---|
| `cargo` | 0 | **Zero occurrences; not required for parity.** Retained here as a recorded negative, not deleted — `noaa-apt` is written in Rust but ships as a prebuilt binary, so Rust in the tree does not imply a cargo backend. |
| `flatpak` | 0 | **Zero occurrences; not required for parity.** |
| `appimage` | 0 in AHRL | **Not required for AHRL parity. Post-1.0**, required by the 73Linux delta — HAMRS is an AppImage whose upstream is discovered by scraping `hamrs.app`. |
| Wine *prefix* | 0 in AHRL | AHRL's Morse Runner needs bare `wine` only. **Post-1.0**, VARA needs a configured prefix: `WINEARCH=win32`, `winetricks winxp`, `winetricks sound=alsa`. A prefix backend is more than `apt install wine`. |
| **CPAN** | **1 real use** | **Required.** Missing from the original breakdown. `install_aa_analyzer` runs `(export PERL_MM_USE_DEFAULT=1; cpan install Device/SerialPort.pm)`. **Security note:** unpinned CPAN fetch, no checksum, and `PERL_MM_USE_DEFAULT=1` auto-accepts configuration prompts — it is a network install that answers its own questions. Either pin it, package the Perl dependency ourselves, or use the Debian `libdevice-serialport-perl` package if it satisfies the build. |
| `snap` | 11 occurrences | **Not a backend — an anti-dependency.** Every occurrence is *removal* of snap Firefox, plus an APT pin to keep it off. Belongs in `system_modifications` as a package to purge and pin against, never as an install method. |

**Measured backend set required for 1.0** (AHRL parity + packet core): apt,
source-from-tarball, source-from-git, binary/`.deb`/archive, Python venv, pipx,
CPAN, and launcher generation. Nothing else is justified by data.

### Amendment, 2026-08-25 — 1.0 packet core needs no new backend

Checked against the 73Linux delta admitted to 1.0 by D-008:

| Unit | Install shape | Backend |
|---|---|---|
| PAT | vendor `.deb` from GitHub Releases, per-arch | binary/`.deb` — **have it** |
| ARDOP | prebuilt release asset via GitHub Releases API | binary — **have it** |
| Direwolf | `git clone` + cmake | source-from-git — **have it** |
| AX.25 | apt (`ax25-tools`, `ax25-apps`) + config generation | apt — **have it** |
| BPQ (linbpq) | loose binaries + zips via `wget` | binary — **have it**, but see below |

**No new backend is required.** Three findings that are not backend gaps but do
need decisions:

1. **BPQ breaks pin-and-verify.** linbpq is fetched as individual files from a
   personal website's `/Downloads/Beta/` directory — unversioned URLs, no release
   structure, no checksums, and the word *Beta* in the path. We can hash what we
   download, but the URL's contents change under us with no version to pin to.
   This is the first unit in the catalog that cannot satisfy D-004's verification
   requirement as upstream currently publishes. Needs a policy: mirror it
   ourselves with our own hashes, carry it as `status: unverifiable` with an
   explicit user opt-in, or exclude it from 1.0.

2. **ARDOP's revival path is "don't build it."** AHRL disabled ardop over a
   compile error. 73Linux downloads upstream's *prebuilt release binary* instead.
   The REVIVE in `PARITY-POLICY.md` may need no code fix at all — just a change
   of install method. Test this before spending effort on the build.

3. **AX.25 needs templated config generation, not just installation.** Its
   install writes an operator-specific line into `/etc/ax25/axports`:
   `echo "wl2k ${MYCALL} 1200 255 7 Winlink" | sudo tee -a /etc/ax25/axports`.
   This makes `DESIGN.md` §15.3 (station-local configuration — callsign, grid,
   device paths) **blocking for the 1.0 packet core**, not a deferred question.
   It also exceeds `system_modifications` as scoped in D-012, which covers udev,
   groups, and blacklists but not templated config files.

---

## D-005 — Parity means coverage with honest status, not universal success

**Decided:** M5 parity is: every AHRL (and 73Linux delta) unit resolves to a
manifest carrying a `status`. Not: every unit installs successfully.

**Evidence:** Nine AHRL toggles ship disabled, with reasons in shell comments —
NOAA satellites out of service (noaa-apt, xwxapt), compiler errors (ibp, ardop),
empty stub functions (mfc_gpl, tt3_gpl), Debian 13 dropping Qt5 components
(dream, mvoice), packaging abandoned (radiosonde_auto_rx).

That knowledge is the single most valuable thing in the tree and it currently
lives in comments. In our catalog it is queryable data.

**Schema consequence:** `status` (supported | broken | retired) with a `reason`
string and a `date`.

### Amendment, 2026-08-25 — "has a status" is too weak a bar

Superseded in part by `PARITY-POLICY.md`. Coverage alone is not parity.

M5 requires that every unit **either installs successfully on at least one
supported distro, or carries a `broken`/`retired` status verified by us** — not
inherited from an AHRL shell comment.

- **Never inherit a verdict.** Re-attempt `ardop`, `radiosonde_auto_rx`, and the
  compiler-flag-fragile set (`glfer`, `gsmc`, `owx`, `linrad`, `qgrid`) on
  current sources, on our supported distros, before accepting any verdict.
- **Record the attempt**, not just the conclusion: date tried, version tried,
  distro, and the actual failure. The next person needs to know what was tested.
- **Exit criterion:** our install-success fraction must be **at least as good as
  AHRL's own**. AHRL ships 95 units with 9 disabled. Shipping 95 manifests with
  40 marked broken is not parity, however complete the coverage looks.
- **Inherited verdicts count against us.** Tested-and-confirmed-dead does not.

---

## D-006 — Do not carry forward

**Retired — the world changed, no substitute exists:**
- `noaa-apt`, `xwxapt` — all NOAA APT satellites out of service as of 2025-11-09

**Dead — do not port:**
- `ibp` — upstream 0.21 predates modern C, many compiler errors
- `mfc_gpl`, `tt3_gpl` — empty stub functions, shipped as no-ops for years;
  AHRL's own docs call them obsolete
- `dream`, `mvoice` — architecturally stuck on Qt5 components removed in
  Debian 13

**Revisit, not abandoned:**
- `ardop` — v27 compile error, but upstream (pflarue/ardop) is alive
- `radiosonde_auto_rx` — AHRL gave up packaging it; upstream active. Our venv
  backend should handle what defeated a bash script.

**Alive but fragile — needs `compiler_flags` to build at all:**
- `glfer` (2003-era), `gsmc`, `owx` (2022 snapshot), `linrad`, `qgrid`

**Unpinnable as shipped — needs our own version pinning:**
- SatDump, SDR++, gsmc, cwwav, dump1090, AntScope2 ship as unversioned
  master/main snapshots. (A pinned `SatDump-1.2.2.zip` sits unused in the AHRL
  tarball.)

**Needs our own recipe:**
- AIS-catcher — good software, installed via the one method our security rules
  flatly prohibit (remote script piped into bash)

---

## D-007 — M17 support is ours to build, not to port

**Decided:** M17 is a genuine gap we fill on our own terms.

**Evidence:** AHRL v27 has zero M17 support — `droidstar` was removed in v26e and
`mvoice` is broken on Debian 13. There is nothing to port.

---

## D-008 — Winlink/packet/EMCOMM is a parity gap AHRL cannot fill

**Decided:** Add the 73Linux delta cluster to the 1.0 target. Reconsider whether
"AHRL parity" alone is a defensible 1.0.

**Evidence:** 73Linux carries PAT, PATMENU3, BPQ, AX25, ARDOP, ARDOPGUI, VARA,
GARIM, VARIM. AHRL has no Winlink client at all, no BPQ node, and its lone
`ardop` is disabled. A large fraction of the EMCOMM audience runs Winlink; an
AHRL-derived catalog leaves them stranded.

Secondary from 73Linux: XYGRIB (GRIB weather), HAMRS (logging), M0IAX. Pi-system
helpers (PISTATS, PITERM, VNC, CONKY, BATT) are out of scope.

### Resolved, 2026-08-25 — split the delta

**In 1.0 — the packet core:** PAT, AX.25 stack, BPQ, ARDOP, and Direwolf *with
configuration, not merely installation*.

**Post-1.0:** VARA (needs a configured Wine prefix; closed-source freeware) and
HAMRS (needs an AppImage backend, and its upstream is discovered by scraping a
webpage).

**1.0 is therefore: AHRL parity + the packet core.** Verified against the
measured backend set — none of the five 1.0 units requires a backend we do not
already need (see the D-004 amendment of the same date), so the split costs no
new engineering. Two caveats recorded there: BPQ cannot satisfy pin-and-verify as
upstream publishes it, and AX.25 makes station-local config generation blocking
rather than deferred.

Secondary 73Linux units (XYGRIB, M0IAX) remain unclassified pending
`PARITY-POLICY.md` disposition. Pi-system helpers (PISTATS, PITERM, VNC, CONKY,
BATT) are RETIRE-as-out-of-scope.

---

## D-009 — Community side-loading, with review tiers, from day one

**Decided:** Ship a three-tier catalog — core / community / local — where
dropping an entry in the community tier surfaces it automatically, and users
choose whether to enable unreviewed entries.

**Evidence:** This is 73Linux's genuinely good idea and the direct answer to our
founding objection to AHRL (single maintainer, contribution-hostile release
process). It is why 73Linux has contributors and AHRL does not.

**Difference:** signed catalog entries, not unreviewed bash inheriting cached
sudo.

---

## D-010 — Add an `update` block (schema field 15)

**Decided:** Every manifest carries an update descriptor: a version-probe method
(binary `--version` parse, `apt policy`, GitHub releases API, tag list) plus an
upgrade strategy.

**Evidence:** 73Linux's `VERSION()` is a first-class concept and the field our
schema list was missing. AHRL has no update story at all — install once, rot
forever. Being able to answer "installed versus upstream" is what makes the
project maintainable past 1.0.

---

## D-011 — Provenance: facts only, from both sources

**Decided:** Reuse package names, versions, upstream URLs, install mechanisms,
build flags, `-Wno-*` workarounds, and patch sets. These are facts and not
copyrightable. Write the engine from the inventory.

**Do not reuse:** AHRL's `.desktop` files (105), `.directory` files (18), menu
structure, or documentation prose — no license notice on any of them, status
genuinely unclear. `bin/install_ahrl` and `bin/test_menus_debian13.py` are
GPL-3.0-or-later (Copyright 2024/2025, Andy Stewart KB1OIQ); porting their logic
would be viral. Nothing from 73Linux's code — unlicensed.

**Credit both projects in the README.**

---

## D-012 — Schema fields required by real data

The `CLAUDE.md` sketch is insufficient. Required additions:

**Structural:**
- `install` is a **list of typed method blocks**, not a map of distro → package.
  Resolution is (distro, version, arch) → method, and the *method itself* varies:
  js8call needs apt on Mint 22.3 and a cmake source build everywhere else;
  GridTracker2 needs a different `.deb` per architecture; MSHV needs a different
  `.pro` file per arch.
- `arch` as a first-class selector (see D-002)
- `build_depends` separate from `depends` — 34 source builds carry apt
  build-dependency lists (QLog's is 15 packages). Install-time only; must not
  appear in "what this profile installs."
- `provides` — fldigi's source build also produces flarq, which has its own menu
  entry and no install function. Without this, M5 reports a false gap.
- `conflicts_with_repo_package` — five packages require `apt purge` of the repo
  version first (fldigi, flrig, quisk, wfview, wsjtx). Destructive; must be
  declared, printed in `--dry-run`, and logged.
- **Ordering constraints** — `install_wsjtx` renames its binary to `wsjtx_orig`
  and `install_wsjtx_improved` renames it back; run one without the other and a
  binary is wrong. `svxlink` and `xastir` must run before user creation because
  they create groups. A flat dependency list expresses "requires," not "after."

**Security and provenance:**
- `source` block with `url`, `sha256`, `signature`
- `apt_repo` with `key_fingerprint` and `key_url` — AHRL adds mozillateam/ppa
  plus an APT pin file, unpinned and unprompted
- `system_modifications` — udev rules, modprobe blacklists,
  `dpkg --add-architecture`, groups created, files shadowed. AHRL deletes distro
  librtlsdr and hand-symlinks replacements with no record.

**Honesty and operation:**
- `status` + `reason` + `date` (see D-005)
- `compiler_flags` / `patches` — six builds need `-Wno-*` flags or in-place sed
  patches, or they do not build
- `launcher` — 14 units need a generated wrapper: pipx installs to
  `$HOME/.local/bin`; quisk, QtTinySA, and MSHV must `cd` into their source dir;
  Java needs `java -jar`; Morse Runner needs wine
- `scope: system | user` — five Python installs land in a specific user's `$HOME`
  via `pkexec --user`. AHRL asks for one username and hardcodes it; a second user
  gets nothing.
- `categories` as a **list**, not a string (see D-003)
- `update` block (see D-010)

---

## D-013 — The dead-menu-entry bug is the design argument

`install_hamclock_next` is defined, enabled, has a menu entry, has a tarball, is
listed in CHANGES as a v27 feature — and is never called from the main body.
Users get a dead menu entry. Six more defects of that shape exist, including a
`$BROWSER` variable never assigned and an inverted Linux Mint detection that is
always false.

A generated call list makes this class of bug structurally impossible. When
justifying the declarative catalog to anyone, this is the example.

---

## D-014 — Backends are justified by measurement, not convention

**Decided:** No backend enters the roadmap without a named package in the
inventory that requires it. Every backend carries its justifying unit.

**Evidence:** `CLAUDE.md` and `DESIGN.md` both listed `cargo`, `flatpak`, and
`appimage` as candidate backends. Measurement found zero occurrences of any of
them in AHRL v27. They were on the list because installers usually have them —
convention, not data.

The same blind spot ran the other way: **CPAN** was in nobody's list and is
genuinely required by `aa-analyzer`. Convention predicted three backends we do
not need and missed one we do.

**Rule:** a backend proposal names the unit(s) requiring it, or it does not ship.
When a backend is considered and rejected, record it as a measured zero rather
than deleting it — the negative result is evidence, and it stops the next person
re-adding it from the same convention.

**Closes:** the unexamined backend list in `CLAUDE.md` M3, `DESIGN.md` §6, and
the `backends/` line in the repo layout.
