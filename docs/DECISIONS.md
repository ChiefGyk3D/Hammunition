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
| **CPAN** | **1 real use** | **Eliminated by supersession, 2026-08-25 — revisit only if a second consumer appears.** Originally: Missing from the original breakdown. `install_aa_analyzer` runs `(export PERL_MM_USE_DEFAULT=1; cpan install Device/SerialPort.pm)`. **Security note:** unpinned CPAN fetch, no checksum, and `PERL_MM_USE_DEFAULT=1` auto-accepts configuration prompts — it is a network install that answers its own questions. Superseded: `aa-analyzer` → `flaa` removes the only CPAN consumer in the inventory, and with it the backend. If `aa-analyzer` is carried as a CLI alternative, satisfy it from Debian's `libdevice-serialport-perl`, never from CPAN. See D-014's worked example. |
| `snap` | 11 occurrences | **Not a backend — an anti-dependency.** Every occurrence is *removal* of snap Firefox, plus an APT pin to keep it off. Belongs in `system_modifications` as a package to purge and pin against, never as an install method. |

**Measured backend set required for 1.0** (AHRL parity + packet core): apt,
source-from-tarball, source-from-git, binary/`.deb`/archive, Python venv, pipx,
and launcher generation. **CPAN is not in the set** — see the amendment above.
Nothing else is justified by data.

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
`PARITY-POLICY.md` disposition.

### Correction, 2026-08-25 — three units were misclassified by their filenames

The original text of this resolution read: *"Pi-system helpers (PISTATS, PITERM,
VNC, CONKY, BATT) are RETIRE-as-out-of-scope."* **Three of those five were wrong,
and the error was mine.** I classified them from the `PI*` filename prefix
without reading the `.bapp` headers. The prefix is 73Linux's naming convention,
not a statement about the software.

| Unit | What I said | What it actually is | Corrected |
|---|---|---|---|
| `PITERM` | Pi system helper | **QtTermTCP** (G8BPQ) — packet terminal over TCP | **1.0 packet core** |
| `QTSOUND` | *(not considered)* | **QtSoundModem** (UZ7HO / Wiseman port) — soundcard packet modem, a direct alternative to Direwolf | **1.0 packet core** |
| `PIAPRS` | *(not considered)* | **Pi-APRS** — APRS messaging client | **1.0 packet core** |
| `PISTATS` | Pi system helper | Pi3/4 stats monitor | RETIRE — correct as stated |
| `CONKY`, `BATT`, `VNC` | Out of scope | System monitor, battery test, RealVNC viewer | RETIRE — correct as stated |

**The 1.0 packet core is therefore eight units, not five:** PAT, AX.25, BPQ,
ARDOP, Direwolf-with-configuration, **QtTermTCP, QtSoundModem, and Pi-APRS**.
QtTermTCP and QtSoundModem are the same author's stack as BPQ, which is why they
belong together.

**Method note:** classify from the manifest header or the source, never from the
filename. The `.bapp` `Comment=` field carried the correct answer the whole time
and cost one HTTP request to read.

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

### Worked example, 2026-08-25 — the dead menu entry has a real victim

This stopped being hypothetical. The never-called function is
`install_hamclock_next`, and the software it fails to install is **the
replacement for software that has since been discontinued**.

- HamClock's author, Elwood Downey (WB0OEW), became a Silent Key **2026-01-29**.
- HamClock was reported to stop functioning **end of June 2026**.
- **AHRL v27 shipped May 2026** — after the announcement, before the sunset.
- v27 builds ESPHamClock **four times** (800x480, 1600x960, 2400x1440,
  3200x1920) and every menu entry hardcodes `-b hamclock.com:80`.
- v27 also ships `hamclock-next-1.5.tar.gz`, defines `install_hamclock_next()`,
  installs `hamclock-next.desktop` into the HF_Propagation menu, and lists
  "added hamclock-next" in CHANGES.
- **The call is missing from the main body.**

So AHRL v27 installs four copies of a discontinued client pointed at a
discontinued server, ships the maintained successor in the same tarball, and
never installs it. A user who wanted the working one got a dead menu entry.

Full sourcing in `reference/licence-verification.md`. Two consequences:

1. **The catalog's call list must be generated.** Not reviewed, not linted —
   generated, so a defined unit that is never installed is unrepresentable.
2. **Service endpoints are manifest fields, never launcher constants.** Had the
   backend URL been a field, repointing every HamClock install at the Open
   HamClock Backend would be a one-line catalog change. Hardcoded into four
   generated launchers, it is not. This is shape 7 in the schema.

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

### Worked example, 2026-08-25 — CPAN, justified by one package, eliminated by one supersession

CPAN entered the backend set correctly: measurement found it, convention had
missed it, and exactly one unit required it — `aa-analyzer`, which needs the
Perl module `Device::SerialPort`.

Then the disposition pass found `flaa`: an actively maintained W1HKJ GUI for the
same RigExpert AA-\* analyzers. Superseding `aa-analyzer` → `flaa` removed the
only CPAN consumer in the inventory, and with it:

- an entire backend we would have had to build, test per-distro, and maintain
- an unpinned network install with no checksum
- `PERL_MM_USE_DEFAULT=1`, which auto-accepts configuration prompts — a network
  install that answers its own questions, in direct conflict with our security
  requirements

**The rule this adds:** measurement justifies a backend; it does not oblige us to
build one. Before committing to a backend whose justification is a single
package, check whether that package has a maintained replacement. A backend with
one consumer is a liability with a dependency.

**Order matters:** run dispositions before finalising backend scope. Had we built
CPAN support first, we would have maintained it for a package we then superseded.

**Closes:** the unexamined backend list in `CLAUDE.md` M3, `DESIGN.md` §6, and
the `backends/` line in the repo layout.

---

## D-015 — Qt5 exposure is a standing register, not a one-time audit

**Decided:** The catalog carries a **queryable Qt5 exposure register** as data:
which units depend on Qt5, which specific Qt5 components, and whether a Qt6 path
exists upstream. It is maintained continuously and reported, not audited once.

**Evidence:** Qt5 is not a per-package risk — it is one systemic risk with many
faces, and it has **already claimed two units**. `dream` died on
`libqt5webkit5-dev` and `mvoice` on `libopendht-dev`, both removed in Debian 13.
AHRL discovered each failure one package at a time, by compile error, after the
fact.

Units still on Qt5 in the inventory: **QLog** (qtbase5, qtwebengine5, qt5charts,
qt5keychain — the heaviest exposure in the catalog), **wsjtx**,
**wsjtx_improved**, **MSHV**, **gqrx**, **qgrid**, **QtTinySA**, **Coil64**,
**AntScope2**, **wfview**.

**Flagged no-migration-path:** `wfview` requires `libqt5gamepad5-dev`. **Qt
Gamepad was deprecated in Qt 5.15 and never carried into Qt6** — there is no Qt6
equivalent to migrate to. Upstream must drop or reimplement the feature. This is
qualitatively different from a module that merely needs porting, and the register
must distinguish the two.

**Register fields, per unit:** `qt_major`, the specific component list, an
upstream Qt6 status (`ported` | `in-progress` | `no-path` | `unknown`), and the
date that status was last checked.

**Why data and not a document:** a document goes stale silently. A register in
the catalog can be queried (*"what breaks when Debian drops Qt5?"*), reported in
CI, and diffed between releases. It is the same argument as **D-005**'s status
field — knowledge that currently lives in a maintainer's head becomes something
the tool can answer.

**Generalises:** Qt5 is the instance, not the rule. Any shared dependency whose
removal would take out multiple units warrants a register — GTK2 is the next
candidate (`glfer` needs `libgtk2.0-dev`, and GTK2 is EOL).

---

## D-016 — The engine fails loudly on any unresolvable dependency

**Decided:** An unresolvable dependency is a hard error that stops the run. Never
a warning, never a log line the run continues past.

**Evidence:** AHRL has **no `set -e` and checks no exit status anywhere** across
3,911 lines. Every `apt install`, `make`, and `cmake` may fail and the script
proceeds to the next program. This is why `bin/find_errors_ahrl` exists — it
greps a 2.5-hour install transcript for error strings *afterwards*, and its own
comment concedes *"It doesn't identify EVERY error...yet(?)."*

The consequence is silent partial installs. Several AHRL dependency lines are
suspected already-failing and nobody would know:

| Dependency | Unit | Problem |
|---|---|---|
| `fftw2` | `glfer` | FFTW **version 2** |
| `libgtk2.0-dev` | `glfer` | GTK2 is EOL |
| `python3-tksnack` | `js8spotter` | Snack toolkit, very old |
| `libportaudio-ocaml-dev` | `fldigi` | An **OCaml** binding fldigi does not use — almost certainly a copy-paste error that has never surfaced because nothing checks |

**This restates `CLAUDE.md`'s "fail loudly, never silently degrade" as a specific,
testable engine requirement**, because the failure mode it prevents is the single
most common defect in the prior art.

**Consequences:**
- Dependency resolution is a distinct pre-flight phase. Resolve everything for
  the whole transaction, report every failure together, then install — do not
  discover failures one package at a time, mid-run.
- `--dry-run` must resolve dependencies for real. A dry run that cannot tell you
  a package is unobtainable is not complete, and **D-004** requires completeness.
- Partial success is reported explicitly: what installed, what did not, why.

### Latent bugs to fix rather than inherit

Carried across from AHRL and corrected in our manifests:

| Bug | Fix |
|---|---|
| `default-jre-headless` for **FoxTelem** and **YAAC** | Both are **Swing GUI** applications; a headless JRE is precisely the one without the AWT display stack. Use a full JRE. |
| `libportaudio-ocaml-dev` in **fldigi** deps | Spurious. Remove. |
| `LIBWXGTK_DEV` resolved by `apt-cache search libwxgtk \| grep dev \| grep -v media \| grep -v webview` | Replace with **explicit per-distro package names**. The wxWidgets 3.2 → 3.3 transition changes the name and the pipeline silently returns the wrong package or nothing. Affects `freedv`, `gspiceui`, `tqsl`, `xwxapt`. |
| `install_gspiceui` hardcodes an `aarch64-linux-gnu` symlink path on every arch | Dangling symlink on x86_64. Use the `arch` selector (**D-002**). |
