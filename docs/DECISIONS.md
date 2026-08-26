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

  *Amendment 2026-08-25:* **three of these six are packaged in Debian** —
  `satdump`, `sdrpp`, and `dump1090`'s supersession target `readsb`. Preferring
  the packaged version resolves the snapshot problem at zero cost rather than by
  building our own pin. See `reference/blend-inventory.md` and
  `reference/overlaps.md`. `gsmc`, `cwwav` and `AntScope2` still need pinning.

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

### Correction to worked example 1, 2026-08-25 — tested, and partly wrong

The example above was written from reporting. It was then tested, per the
maintainer's instruction to test rather than report, and **two of its statements
do not survive**. The original text is left intact above; this is the retraction.

**Retracted:** *"the software it fails to install is the replacement for software
that has since been discontinued"* and *"AHRL v27 installs four copies of a
discontinued client pointed at a discontinued server."*

**What testing found** (full probe results in
`reference/licence-verification.md`):

- `hamclock.com` is **up**: HTTP 200, `Last-Modified 2026-08-07`, and
  `/ham/HamClock/version.pl` returns **4.27** with a changelog of new features.
  HamClock was continued after its author's death, past the 4.23 AHRL ships.
- Elwood's own server, `clearskyinstitute.com`, **is** gone — it refuses TCP.
  The sunset was real; it landed on the original host, not on the hostname AHRL
  points at.
- `hamclock.com` is now a third-party, patron-funded operation.

**What survives, and it is the part that mattered:** `install_hamclock_next` is
still defined, enabled, menu-registered, changelog-announced, and **never
called**. The dead menu entry is real. Only the claim about *what the user lost*
was wrong — they lost access to a maintained fork, not a rescue from a dead one.

**The methodological point is worth more than the example.** A statement about
the world was recorded as settled on the strength of three consistent secondary
sources, and a single `curl` overturned it. `PARITY-POLICY.md` already says never
inherit a `broken` verdict without testing it; this extends that to **every**
external-state claim, including the ones that flatter our argument. Ours did, and
it was wrong.

---

### Worked example 2, 2026-08-25 — the collision that stopped existing

The first example shows the declarative catalog preventing a bug. This one shows
it **removing a problem from the design entirely**, which is the stronger claim.

AHRL installs WSJT-X and WSJT-X-improved in sequence. Both builds emit a binary
called `wsjtx`, so the second overwrites the first. AHRL choreographs around it:

```
install wsjtx          → mv /usr/local/bin/wsjtx  /usr/local/bin/wsjtx_orig
install wsjtx_improved → mv /usr/local/bin/wsjtx  /usr/local/bin/wsjtx_improved
                       → mv /usr/local/bin/wsjtx_orig /usr/local/bin/wsjtx
```

Four renames across two functions, order-dependent in both directions. Run
either half alone — which the `INSTALL_*` toggles explicitly permit — and a
binary ends up under the wrong name. Nothing detects it.

Our schema declares the mapping instead:

```yaml
# wsjtx.yaml                    # wsjtx-improved.yaml
binaries:                       binaries:
  - produced: wsjtx               - produced: wsjtx
    install_as: wsjtx               install_as: wsjtx-improved
```

The builds still emit the same filename. They can no longer collide, because
neither package controls its installed name — the manifest does. The ordering
constraint is not automated or made safe; **it stops existing.** `after:` is
retained for genuine ordering (units that must create groups before user
creation), and `wsjtx-improved` declares it for determinism, but correctness no
longer depends on it. A schema validator rejects duplicate `install_as` outright.

**The general principle:** when imperative install logic needs a careful
sequence, check whether the sequence is inherent or an artifact of the tooling.
AHRL's rename dance looks like a hard ordering requirement and is in fact a
naming collision that better modelling deletes. Prefer making a bad state
unrepresentable over making it survivable — the same reasoning that removed
`method: script` and optional `sha256` from the schema.

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

---

## D-017 — 1.0 is the five-source union, not AHRL parity alone

**Decided:** `docs/SCOPE.md` governs 1.0 scope. **1.0 = Debian Blend + AHRL
parity + 73Linux packet core + Skywave listening delta + DragonOS Tier 1**
(`SCOPE.md` staging 1–5).

**Supersedes** the "1.0 = AHRL parity + packet core" formulation in `CLAUDE.md`
and `DESIGN.md` §14, both reconciled 2026-08-25. **D-008** is unchanged: it
settled the packet-core split, which remains stage 3 of five.

**Evidence gathered since D-008:** the Debian Blend is 152 packages of
team-governed, signed, machine-readable coverage
(`reference/blend-inventory.md`), and **11 of AHRL's 35 source builds are already
packaged there**. Blend-first is not merely cheap — it shrinks the source-backend
problem that D-004 identifies as the core engineering cost. Staging AHRL ahead of
it would have meant building a source backend for software Debian already ships.

**DragonOS is tiered, and the tiers are not one job.** Tier 1 (apt or upstream
`.deb`) is the 1.0 SIGINT profile. Tier 2 is post-1.0. **Tier 3 — GNU Radio
out-of-tree modules — must not be attempted before the source backend and pin
database are solid**, and each module records the GNU Radio version it was built
against. Where nothing maintained exists, document the gap rather than carrying a
fork we cannot sustain.

---

## D-018 — Every external-state claim is tested before it is published

**Decided:** Any claim about the outside world — a service being down, a project
being dead, a package being unavailable — is **tested** before it enters a
document a user might read. Secondary sources establish what to test, never the
conclusion.

**Evidence:** the HamClock case. Three consistent secondary sources — Amateur
Radio Newsline, ARRL Eastern Massachusetts, Amateur Radio Daily — supported the
conclusion that HamClock stopped functioning in June 2026. It was recorded as
settled and written into `dispositions.md`. One `curl` overturned it: the backend
serves version 4.27 with an active changelog.

The claim was wrong in the direction that flattered our argument, which is
precisely when scrutiny is weakest.

**Generalises `PARITY-POLICY.md`'s rule.** That document already forbids
inheriting a `broken` verdict without testing it. This extends the same standard
from package build status to every external fact, and adds: **record what was
not tested.** The HamClock probe used guessed endpoint paths and ran no client
end to end, and the write-up says so.

**Cheap to comply with.** The tests that overturned this were a DNS lookup, a TCP
connect, and two HTTP GETs.

---

## D-019 — Blend task membership is a category, not an install default

**Decided:** A package's presence in a Debian Hamradio Blend task means *"this
belongs to this category."* It does **not** mean *"install this."* Our profiles
import Blend task membership as tagging and decide inclusion separately.

**Evidence:** measured in `docs/reference/blend-inventory.md`. Of 160 task
entries, **155 are `Recommends` and 5 are `Suggests`. There is not one
`Depends`.** The Blend's metapackages are opt-out by construction: `apt install
hamradio-datamodes` pulls every recommendation unless the operator knows to pass
`--no-install-recommends`.

Our profiles are opt-in (**D-003**). Importing task membership as an install
list would make every profile maximal — the exact DragonOS-scale complaint
`SCOPE.md` names — and would do it silently, because the Blend's own metadata
looks like a package list until you read the relation column.

**Second, related finding: "in the Blend" is not "installable."** A probe of all
152 Blend packages inside a `debian:13` container found **8 that do not install
on Debian 13**: `aethersdr`, `dump1090-mutability`, `fbb`, `not1mm`,
`odr-audioenc`, `qlog`, `sdrangel`, `sdrpp`. Seven are present in unstable, so
most of it is ordinary release lag — the Blend tracks unstable and we target
stable. `odr-audioenc` is in neither.

That is 94% coverage on stable, not 100%, and the residual lands on packages we
had already chosen: `qlog` is `overlaps.md`'s recommended logging default, and
`sdrpp` and `sdrangel` are in the Blend's `sdr` task. Per **D-005**, coverage
counts only where it installs.

**Consequences.**

- Profile manifests state their own membership. Blend tasks seed it; they do not
  define it.
- Every Blend package a profile includes is checked against the target before
  the capability matrix claims it.
- `SCOPE.md`'s "cheapest coverage in the project" stands, qualified: cheapest,
  and 94% rather than complete on a stable base.

---

## D-020 — Detected hardware drives profile resolution

**Decided:** Profile resolution consults detected hardware. A profile may declare
packages as *available-not-installed*, selected only when the matching device is
present. This is a structural requirement on M4, not an optimisation.

**Evidence, from two independent sources.** The Blend's `sdr` task is 39
packages, of which **12 are `soapysdr-module-*`** — per-device backends for
airspy, bladerf, hackrf, lms7, mirisdr, osmosdr, redpitaya, remote, rfspace,
rtlsdr, uhd and audio. Skywave Linux ships **the same full set** in its 5.10.0
release, and DragonOS ships it too.

All three do it for the same reason: **a live ISO cannot know what will be
plugged in.** Skywave and DragonOS boot from USB on an unknown machine; the
Blend is a metapackage with no host to inspect.

**We are not in that position.** We run on an installed system with the device
attached, which is the whole premise of the project. Installing eleven backends
for hardware the operator does not own is exactly the bloat all three of those
projects are forced into and we are not.

Measured effect: **11 of the 12 removed from the common case**, from the single
largest profile in the catalog.

**Consequences.**

- The manifest schema needs a way to express "install when this device is
  present" — a hardware selector alongside the existing `distro`, `arch` and
  version selectors (**D-002**).
- `hammunition --dry-run` must show which modules were selected and why, because
  a resolution that depends on hidden state is exactly what the dry-run
  requirement exists to prevent.
- With no device attached, resolution installs `soapysdr-tools` and nothing
  device-specific, and says so rather than failing.
- This generalises past SoapySDR: firmware packages, udev rules and DKMS modules
  have the same shape. It is the same mechanism that makes persistent udev
  symlinks by serial worth building.

**Not a substitute for honesty.** If detection fails or is ambiguous, the engine
reports it and installs the conservative set. Guessing at hardware would be a
silent degradation, which **D-016** forbids.

---

## D-021 — Consent gates disclose a risk category; they never give legal advice

**Decided:** A profile whose lawful use depends on the operator's authorization
is **consent-gated**. Installing it requires an affirmative act that a
convenience flag cannot supply.

### The mechanism

| Requirement | Rule |
|---|---|
| Interactive by default | The gate prompts on a TTY and blocks until answered. |
| `--yes` must not satisfy it | `--yes`/`-y` means *"do not ask me to confirm routine steps."* A gate that a convenience flag walks through is not a gate. |
| Scripted path is separate and explicit | The profile declares its own environment variable, e.g. `HAMMUNITION_ACCEPT_RF_RESEARCH=1`. Nothing else sets it, and setting it is recorded. |
| Recorded | The transaction log stores who affirmed, when, which risk categories were disclosed, the exact disclosure text, and whether it came from a prompt or the variable. |
| Specific | The disclosure names the **risk category**, never a generic warning. |
| No TTY and no variable | Refuse and explain. Never assume consent from silence. |

### What the gate must not do

**It must not tell the user what is legal where they are.** We cannot determine
a user's jurisdiction, their licence class, their employer's authorizations, or
the terms of an engagement they may be operating under. We are not lawyers and
this software is not legal advice.

The gate therefore **discloses and asks**; it does not adjudicate:

- ✅ *"This profile installs software that can cause connected hardware to
  transmit. Transmitting may require a licence or authorization. Do you affirm
  you have the authorization required for how you intend to use it?"*
- ❌ *"Transmitting on these frequencies is illegal without an amateur licence in
  most countries."*

The second sentence is an opinion about law. The first is a disclosure and a
question. **Any wording that reads as legal advice is a defect.** Write it so a
lawyer reading it sees a disclosure, not an opinion — no jurisdictions, no
statutes, no "illegal", no "you may/may not".

The corollary matters as much: **we do not decide for the user either.** A
consent gate that refuses to install because we guessed the user is unauthorized
would be the same error in the opposite direction. The user affirms; we record.

### Risk-category taxonomy

Categories describe **what the software can do**, not what any jurisdiction says
about it. That is what keeps them stable and keeps us out of the advice business.

| Category | The capability being disclosed |
|---|---|
| `unlicensed_transmission` | Can cause connected hardware to emit RF, on frequencies, power levels or modes that may require a licence or authorization. |
| `protected_communications` | Can receive, decode, store or display communications that may be protected from interception. |
| `identifier_collection` | Can collect identifiers associated with people or their devices — IMSI, IMEI, MAC, serial numbers, subscriber records. |
| `third_party_systems` | Can interact with, probe or test systems and networks; doing so needs the owner's authorization. |
| `spectrum_disruption` | Can degrade or deny service to other users of the spectrum, whether or not that is the intent. |
| `credential_recovery` | Can recover, crack or replay authentication material. |

A profile lists every category that applies. `rf-research` under **Q-008** would
carry `unlicensed_transmission`, `protected_communications`,
`identifier_collection` and `spectrum_disruption`.

### Where it applies, and where it deliberately does not

Gates attach to **profiles**, not packages. A gate on every package would train
users to click through, which is the failure mode this exists to avoid — the
prompt has to be rare enough to be read.

`rf-security` as scoped in `profile-sizing.md` — Wireshark, aircrack-ng,
inspectrum, rtl_433 — is **not** gated by this decision on its own. Those tools
ship in Debian and Kali without ceremony and gating them would be theatre.
Gating is for the profile where the capability itself is the hazard.

**This is a mechanism decision, not a scoping one.** Which profiles are gated
follows from **Q-008**, which is open.

### Why a mechanism and not a warning

`--dry-run` already prints every system modification (CLAUDE.md, security
requirements) and the transaction log already records what happened. Neither
records that a human took responsibility. That record is the point: it is what
distinguishes a tool that was used with authorization from one that was not, and
it belongs in the log next to the packages it authorized.


---

## D-014 amendment, 2026-08-26 — cargo tested against its best candidate, and stays at zero

**D-014** records `cargo` at **zero occurrences** and says a backend is added
only when a unit requires it. Rayhunter was the strongest candidate to overturn
that, and it does not.

**Evidence.** `EFForg/rayhunter` is a Rust project — 2.6 MB of Rust, `Cargo.toml`
and `Cargo.lock` at the repository root, GPL-3.0, 5,700 stars, pushed within the
last week. If any unit in scope needed a cargo backend it should have been this
one.

Upstream publishes **prebuilt Linux binaries for x86-64, aarch64 and armv7**, and
the `linux-x64` archive contains the installer, the `rayhunter-check` analyser,
the on-device daemon and its init scripts. Nothing compiles on the user's
machine. The **binary backend, already required for 1.0, covers it completely.**

**cargo stays at zero.** The point of D-014 is that a backend costs maintenance
forever and must be earned by a named unit; the best candidate examined so far
does not need one.

**Second finding, and the more valuable one.** `SCOPE.md` says of the pin/hash
database that *"not one of them publishes checksums we can inherit"* — across
AHRL's 63 archives, 73Linux, Skywave and DragonOS. **Rayhunter publishes a
`.sha256` beside every release asset.** Verified 2026-08-26: the published digest
for `rayhunter-v0.12.0-linux-x64.zip` matches the computed one.

That makes it the first manifest in the catalog that can carry an **inherited**
hash rather than one we pinned ourselves, and it is worth recording which
project made that possible.

**Third, a smaller one.** The installer statically links EFF's fork of the
`adb_client` crate and speaks USB through `nusb`, so deploying to a hotspot needs
**no `adb` package**. The obvious dependency is not a dependency.

See `docs/guides/rayhunter.md`, including what was not tested — no device was
attached and no capture analysed.

---

## D-022 — Displacing software the distribution chose: coexist, disclose, never remove silently

**Decided:** A manifest may offer software that competes with something the
distribution deliberately ships. It may not quietly replace it. Five rules, and
they are general — the VS Code case is the first instance, not the subject.

### 1. Coexistence is the default; replacement is a separate, explicit act

If both can be installed, install both. Wanting package B is not a request to
remove package A, and treating it as one is how a tool ends up making decisions
that were not asked of it. Removal requires the operator to say so, on its own.

### 2. Never remove silently

The displaced package is declared in `conflicts_with_repo_package`, printed by
`--dry-run`, recorded in the transaction log with a `reverse_hint`, and
reversible with one apt command that the documentation states.

**This is the AHRL pattern we exist to fix.** AHRL removes the distribution's
`librtlsdr` to install its own, with no record and no way for the operator to
know it happened. Being newer is no excuse for repeating it.

### 3. A third-party repository gets the full treatment

Declared in the manifest as an `AptRepo`, signing key fingerprint pinned, and
the rationale shown to the operator **before** the repository is added. Already
a security requirement in CLAUDE.md; restated because this is the case that will
tempt someone to skip it.

Adding a vendor's repository is a larger act than installing a package: it grants
that vendor the ability to ship updates to any package name they choose,
forever. The disclosure must say that, not just name the URL.

### 4. State the distribution's reasoning as a reason, not as an obstacle

A distribution that ships B instead of A usually had a reason. Repeat it
accurately and neutrally, then state the counter-argument with equal care.

**Do not editorialise in either direction.** Not "Parrot ships VSCodium for
ideological reasons but most people want real VS Code", and not "VS Code is
proprietary spyware". The operator is choosing for their own machine and needs
the facts, not our opinion. This is the same discipline **D-021** imposes on
consent gates: disclose, do not adjudicate.

### 5. Never the default, never in a base profile

Software that displaces a distribution choice is opt-in, and does not belong in
any profile an operator installs to get started.

### Why this is a decision and not a manifest comment

The first instance is an editor and it feels minor. The pattern is not: it will
recur for `dump1090-mutability` versus `readsb`, for a vendor SDR driver against
the distribution one, for anything where upstream ships a newer build than the
archive. Writing the rule once means the tenth case is not argued from scratch.

**First instance:** `catalog/packages/code.yaml`, offering Microsoft's VS Code
build alongside — never instead of — the `codium` that Parrot ships.

---

## D-023 — Two licences, split on the architectural boundary

**Date:** 2026-08-26. **Status:** accepted. **Closes:** Q-009.

`LICENSE` — **GPL-3.0-or-later**, covering `src/`, `scripts/`, `tests/`, `docs/`
and the repository's own build and CI files.

`catalog/LICENSE` — **CC0-1.0**, covering everything under `catalog/`.

### Why a split rather than one licence

The repository already has an architectural boundary and CLAUDE.md states it as
an invariant: the catalog is data that **must remain usable by an engine that
isn't ours**, and the engine is replaceable software. A single licence would
have to lose one of those two properties.

**Copyleft on the engine is the point.** This project exists because of a
governance problem, not a software problem — AHRL's bus factor of one, 73Linux's
missing licence file, contribution by emailing the maintainer. A permissive
licence would let a fork close the source and reproduce the exact failure mode
the project was founded to answer. GPL-3.0-or-later also matches the ecosystem
this audience already runs: hamlib, fldigi, WSJT-X, GNU Radio, and AHRL's own
installer.

**Copyleft on the catalog would defeat its purpose.** A GPL manifest tree is one
an alternative engine cannot freely consume, which contradicts the invariant
directly. CC0 is not a concession here — it is what the data already is. A
manifest records that `fldigi` is packaged as `fldigi` on Debian and needs
`hamlib` configured first. Those are **facts about the world**, and the thin
copyright interest anyone could claim in an arrangement of them is not worth the
friction it would impose on the thing we most want reused. CC0 removes an
ambiguity rather than making a grant.

### What this does not do

It does not relicense anything the catalog *describes*. Every piece of software
in the inventory keeps its own licence, recorded in
`docs/reference/licence-verification.md`, and CC0 on a manifest says nothing
about the program the manifest installs.

`docs/` is GPL-3.0-or-later by default rather than by argument — it falls under
the repository licence because nothing said otherwise. CC-BY-4.0 would be a
defensible refinement for prose and is not worth a third licence today. The
generated reference under `docs/packages/` is derived from CC0 manifests, which
constrains nothing, since CC0 imposes no conditions to inherit.

### Mechanics

SPDX headers per the REUSE specification: `SPDX-FileCopyrightText` and
`SPDX-License-Identifier` on every source and manifest file, `REUSE.toml` for
formats where a comment is unwelcome, and verbatim texts under `LICENSES/`.

The texts are **copied from Debian `base-files`** (`/usr/share/common-licenses/`)
rather than transcribed, and their checksums are recorded in `REUSE.toml`:
GPL-3 `8ceb4b9e…65b903`, CC0-1.0 `a2010f34…cf0499`. A licence reproduced from
memory is a licence with an unknown diff in it.

`tests/test_licensing.py` asserts every file carries the identifier its tree
requires, so a new manifest cannot arrive unlicensed and a new engine module
cannot arrive under CC0 by copy-paste.

### The reason this could not stay open

D-001 declines to build on 73Linux because it ships no licence file. Q-007 flags
SuperSDR for the same thing. Publishing a public repository in that state while
making that criticism twice in the decision record is not a position that
survives anyone reading both documents. `why-hammunition.md` now answers it in
the same document that raises it.

### Still open

Whether contributions carry a DCO sign-off or a CLA. Recommendation stands from
Q-009: **DCO, not a CLA** — a CLA is a barrier to exactly the drive-by manifest
contributions this project wants.

### Amendment, 2026-08-26 — the holder, and no CLA

Both of the "still open" items above are closed.

**Copyright holder: `Copyright (C) 2026 Renegade Penguin LLC`** (Q-012). An LLC
is a legal person and can enforce a licence; a handle cannot. It also keeps the
maintainer's legal name out of a public repository. Applied to every SPDX header,
`REUSE.toml`, `CONTRIBUTING.md` and the README footer — and deliberately **not**
to `LICENSE` or `catalog/LICENSE`, which are verbatim texts whose checksums are
asserted; a copyright line inserted into a licence corrupts it.

**No CLA and no copyright assignment.** Contributors keep copyright on their own
work, licensed under GPL-3.0-or-later (CC0-1.0 in `catalog/`) by the act of
contributing. This is the ordinary GPL arrangement and is written into
`CONTRIBUTING.md` because a company name in the headers invites the opposite
assumption. A CLA would be a barrier to exactly the drive-by manifest and `lsusb`
contributions this project most wants.

---

## D-024 — A commit pin carries no upstream signal, so it carries ours

**Date:** 2026-08-26. **Status:** accepted. **Resolves:** Q-013, as general
policy rather than as one manifest.

**Rule.** Where upstream has stopped tagging, pin a commit SHA — never a branch,
never a rolling release artifact. A SHA pin **must** carry a `pin_review`
recording `last_reviewed`, `reviewed_by`, a `rationale` for *that* commit, and a
`cadence_days` after which it must be looked at again. A tag must **not** carry
one.

### Why the field, and not just a convention

A tag carries an upstream signal: someone decided that revision was worth
naming. A commit SHA carries none. It is perfectly pinned and perfectly
arbitrary.

That makes the two failure modes symmetric, and both are "nobody looked":

| | |
|---|---|
| **An abandoned tag** | SDR++'s newest release tag is `1.0.4`, 2021-10-18. Master moved in July 2026, 541+ commits later. Pinning the tag ships a five-year-old program nobody runs. |
| **An unreviewed commit** | Fully pinned, fully reproducible, and in four years indistinguishable from the case above. |

Pinning a commit is the right answer to a project that stopped tagging, and it
**moves a judgement upstream stopped making onto us**. Recording that judgement
is what separates a pin from a guess that happens to be reproducible.

### Enforced, not encouraged

`GitInstall` rejects a SHA with no `pin_review` and rejects a tag that has one —
the second because a review on a tag would read as though someone vetted a
revision choice that upstream actually made. `rationale` has a minimum length
because *"HEAD at the time"* is the absence of a rationale rather than a short
one.

**Staleness is checked on a schedule, not on every push.** Whether a pin is
well-formed is a property of the code, asserted in tests that run on every
commit. Whether it is stale is a property of the calendar. Failing an unrelated
pull request because a date rolled over would teach people to ignore the job,
which is the one outcome that makes the mechanism worthless.
`scripts/check_pin_reviews.py` runs weekly in CI and prints what to do.

Its instructions end with the part that matters: **do not bump `last_reviewed`
without reading upstream's log and testing any move.** A date bumped to silence
a check certifies nothing, and would make this worse than having no field.

### The preferred method: check what the distributions pin first

**Before choosing a commit, look at what packages it.** If a distribution ships
a git snapshot, pin *their* commit.

This is not a tiebreaker, it is the main rule, and the reasoning is stronger
than "someone else looked":

1. **It is the review signal upstream stopped providing.** A Debian, Kali or
   Parrot maintainer picked that revision, built it, and shipped it to users who
   would complain. That is a vetting process we do not have and cannot cheaply
   reproduce.
2. **It collapses two revisions into one.** A user who installs from apt and a
   user who builds from source end up running the same code. Without this they
   run different programs under the same name, and a bug report from one does
   not transfer to the other.
3. **Independent agreement is evidence.** Kali and Parrot both landed on
   SDR++ `36ea9a1`. Two maintainers hitting the same missing-tags problem and
   answering it the same way is a stronger signal than either alone.

Recency is not a reason. Master HEAD is newer and nobody has vetted it.

**Choosing our own commit is legitimate and more expensive.** When nothing
packages the project, `basis: own_choice` is correct — and the rationale must
then say *which distributions were checked and what they ship instead*, so the
next reviewer can see whether that has changed. The schema enforces the
difference: `distribution_pin` must name the distributions, `own_choice` must
not name any and needs a fuller rationale.

`scripts/check_pin_reviews.py` prints the basis on every line and flags
own-choice pins with a note to re-check whether anything packages them now.

### First instance — `catalog/packages/sdrpp.yaml`

Apt on Kali and Parrot; a reviewed SHA everywhere else.

`basis: distribution_pin`, `distributions: [kali, parrot]`. Both package SDR++
as a git snapshot at `36ea9a1`, two commits behind master, and taking theirs is
worth those two commits for every reason in the section above.

Same reasoning as `proxmark3.yaml`, which pins `v4.21611` because that is the
release Kali packages, and where a client/firmware mismatch would otherwise be
silent.

**Explicitly not used:** SDR++'s `nightly` release assets. A URL that never
changes with an artifact behind it that does, no version, no published checksum.
`RemoteArtifact` requires a `sha256` and the reason to have a mandatory field is
that it does not bend when bending would be convenient.

---

## D-025 — A claim gets re-verified when it becomes decisive, not only when gathered

**Date:** 2026-08-26. **Status:** accepted.

**Rule.** Gathering standards and decision standards are different bars. A fact
collected in passing may be inherited, cited or estimated. **The moment a claim
is promoted to decisive for a decision, it is re-verified against a primary
source, and the verification is dated in the document that relies on it.**

### The four instances that produced this

Four bugs, one shape: *something was checked once, in a narrower context than
the one it ended up carrying.*

| | What happened |
|---|---|
| **HamClock** | Three secondary sources said it would stop working in June 2026. Never probed. Written into `dispositions.md` as evidence for our own argument. It was live at 4.27. |
| **`check_doc_links.py`** | The checking tool, unchecked. It skipped `docs/reference/` and reported success over seven files it never opened. The first regression test reimplemented the bug and passed. |
| **`src/hammunition/state/`** | Written, tested, type-checked, never committed. mypy, pytest and ruff all read the working tree; only git read the index. |
| **Kali `proxmark3`** | A narrow probe became the decisive argument in Q-010 without re-verification. Kali packages it. |

The first and fourth are the same error at different scales. The second and
third are its reflexive form: *the instrument was never pointed at itself.*

### What this actually requires

Not "verify everything", which is unaffordable and would mean verifying nothing.
Three concrete obligations:

1. **When a claim becomes load-bearing, re-check it then.** The trigger is
   promotion, not age. A fact that was fine as background becomes a different
   kind of object when an argument rests on it.
2. **Date the verification in the document that relies on it**, so the next
   reader can see how old the support is without going looking. This is already
   the house style in `docs/reference/`; D-025 makes it a rule.
3. **Point every checking tool at itself.** A checker gets a test that fails
   when its own bug is reintroduced — verified by reintroducing it, not by
   assuming. `scripts/audit_gitignore.py` was written this way and both
   historical bugs were re-added to confirm it catches them.

### The failure this does not prevent

A claim that was true when verified and became false afterwards. Dating the
verification is what makes that recoverable rather than invisible: a reader can
see the support is two years old and go looking. An undated claim gives them
nothing to be suspicious of.

### Relationship to D-018

D-018 says external claims are tested before published — it governs what we say
outward. D-025 governs what we let ourselves rely on inward. The HamClock
retraction produced the first; Q-010's retraction produced the second, and
should have been prevented by it.

---

## D-026 — We install tooling for a device; we do not install the device's capability

**Date:** 2026-08-26. **Status:** accepted.

**Rule.** A manifest that installs the means of *talking to* a device — a
flasher, a serial console, a udev rule, a driver, a configuration client — is
neutral tooling and is not consent-gated, **regardless of what the device can
do once it is running**. Firmware that comes from upstream and executes on the
device is not something this project installs, and treating it as though we did
would be a claim we cannot support.

### Why this needs stating

Without it, every flasher becomes a gating argument. `esptool` writes an image
to an ESP32; some of those images do things that fall squarely inside the D-021
taxonomy. If the flasher inherits the gate, then so does `tio`, because you can
drive the same firmware over a serial console — and so does `screen`, and so
does `usbutils`, because enumeration is the first step of everything.

That is the reductio, and it lands somewhere worse than "too many prompts": a
gate that appears in front of routine software is one people learn to dismiss,
which is exactly what would make the `rf-research` gate useless at the moment it
matters. **D-021's gates work only because they are rare.** Diluting them is not
a cautious error.

### Where the line actually falls

| | Gated |
|---|---|
| Installing `esptool`, `tio`, a udev rule, a driver | **No** — this is how a computer talks to a peripheral |
| A package whose own function is a capability in the D-021 taxonomy — `gr-gsm` decoding cellular signalling on the host | **Yes** |
| Firmware fetched from upstream and run on the device | **Not installed by us at all**, so there is nothing to gate |

The test is *what does the thing we install do on the machine we install it on*.
`gr-gsm` decodes cellular signalling on the host; that is the capability, and
`rf-research` gates it. `esptool` copies bytes to a serial port.

### Applied

**ESP32 Marauder firmware**, as run by boards such as the C5 Wardriver — it
includes active features (deauthentication,
beacon spam, captive-portal impersonation) that are transmit-side under the
Q-008 tiering. Hammunition installs `esptool` and a serial console. It belongs
in `rf-security`, ungated. This decides the WiFi Pineapple and the USB Rubber
Ducky identically, which is the point of writing it as a rule.

### What the documentation must still do

Neutral tooling is not silent tooling. The device entry states plainly what the
hardware does, including the active features, so nobody discovers them by
surprise. It also says that operating those features against networks you do not
own or are not authorised to test is a separate matter from installing a
flasher.

That sentence is deliberately about *what is being installed*, not about what is
lawful. **Same discipline as D-021: describe capability, do not adjudicate
legality.** The `ConsentGate` wording validator exists because that line is easy
to cross by accident, and it is just as easy to cross in prose.

---

## D-027 — "Supported" and "we have run it" are separate claims

**Date:** 2026-08-26. **Status:** accepted.

**Rule.** A device manifest carries two independent fields:

| Field | The claim |
|---|---|
| `status: supported` | The identifiers are correct and the setup recipe works. |
| `maintainer_verified` | Somebody on this project plugged the hardware in. |

Neither implies the other, and the generated capability reporting shows both.

### Why they must not be one field

`usrp` forced the distinction. Its seven USB identifiers come from Debian's own
`60-uhd-host.rules` — a primary source, maintained by people who ship the driver
— and every rule generated from them will match. That is a real, useful,
evidenced claim. **Nobody on this project owns a USRP.**

Collapse the two and one of two bad things happens:

- **Require hardware for `supported`** and we throw away good evidence. The
  entry would have to say "untested" while holding a citation to the
  distribution's own rule file, which is worse information than the truth.
- **Let `supported` imply verification** and we have claimed support we never
  tested. That is the exact failure D-018 exists to prevent for external claims
  and D-025 for internal ones, applied to hardware.

Two fields cost one column in a table. The alternative costs either evidence or
honesty.

### Not a boolean

`maintainer_verified` is a record, not a flag: date, who, which distribution, and
what actually happened. A bare `true` would be a claim with no evidence behind
it — the same defect one level down, and the reason `UsbId.evidence` and
`PinReview.rationale` exist. *"It works"* fails the minimum length on purpose;
*"enumerated, rules matched, `rtl_test` found the tuner"* is a test result.

Two contradictions are rejected outright: a verification alongside
`gap_closure: unverified_by_maintainer`, and a verification on `status: planned`.
Somebody either ran the hardware or did not.

### What it looks like today

**6 of 20 devices claim `supported`. 0 have been run here.**

That is printed at the top of `docs/reference/hardware-gaps.md`, and the gap is
not a defect to be closed by relaxing either column. It is the honest state of a
project whose hardware layer is built out of distribution udev rules, and saying
so is the point.

### Relationship to `gap_closure`

Three fields now describe a device's evidential position, and they are genuinely
orthogonal:

- `status` — are the identifiers and recipe right?
- `maintainer_verified` — has anyone here run it?
- `gap_closure` — if something is unknown, who could find out?

`usrp` is `supported`, unverified, with no gap. `catsniffer-v3` is `untested`,
unverified, with a gap closable on this bench. `limesdr` is `untested`,
unverified, with a gap closable only by an owner. Each combination means
something different to a user deciding whether to buy the hardware.

---

## D-028 — An identifier that names a chip may not name a `/dev` node

**Date:** 2026-08-26. **Status:** accepted.

**Rule.** A USB identifier that names a *bridge chip* or a *function* rather
than a product cannot be the sole basis for a device-specific udev symlink. A
rule resting on one must also carry `match_product` or `match_serial`, or emit
no symlink at all. Enforced by `DeviceManifest`, `DeviceClass` and
`load_hardware`, not by review.

### The failure, which we had already shipped

The `badgelife` class emitted `/dev/badge-<serial>` for every identifier it
carried. All of them are bridge chips: the kernel binds `10c4:ea60` to `cp210x`
and `1a86:7523` to `ch341`, and `303a:1001` is Espressif's chip-level constant.

So the rule claimed **every CP2102 adapter on the machine** — a rig-control
cable, a GPS puck, a Meshtastic node — after whichever badge it was written for.
The operator gets a symlink pointing at the wrong hardware and no error
anywhere in the chain.

**That is the `rtl-sdr` failure pointed the other way.** There, three
identifiers where Debian had 42 meant a Hauppauge stick got no symlink and no
error. Here, one identifier covering a whole chip family means somebody else's
device gets *our* symlink. **Under-matching is silent and over-matching is
silent**, so neither can be left to review — the same argument that made
`method: script` unrepresentable and `sha256` mandatory.

### Evidence, not opinion

`catalog/hardware/ambiguous-ids.yaml` is generated from two measured sources by
`scripts/gen_usb_ambiguity.py`:

| Basis | Source |
|---|---|
| `kernel_generic_driver` | The kernel's own `modules.alias`, generated by `depmod` from the module tree. A pair in `cp210x`'s or `ftdi_sio`'s table is one the kernel maintainers put in a *bridge* driver. |
| `shared_across_products` | The archive-wide udev sweep found the pair in two or more packages' rules **under different device names**. `0483:df11` is in `qflipper`'s rules and in `dmrconfig`'s, where it is a TYT MD-UV380. |

Two further bases exist for cases no probe reaches and are recorded by hand:
`vendor_chip_default` (Espressif's `303a:1001`, which esptool calls
`USB_JTAG_SERIAL_PID`) and `generic_function_name` (`usb.ids` naming a function
— "Virtual COM Port", "CP210x UART Bridge").

**`303a:1001` stopped being an inference on 2026-08-26.** Three unrelated
products were captured on one machine on one day — a Clip-Boy, a Minino, and the
ESP32-S3 inside a Free-WiLi 2 — and all three report the identical vendor,
product **and product string**: `Espressif` / `USB JTAG/serial debug unit`. Only
the serial differs, and a serial is per-unit.

Three observations beat any argument from a vendor constant, and they settle the
design question underneath the rule: **none of those three devices can carry a
catalog-wide symlink**, because no attribute a rule could match on distinguishes
one from the other two. Their MAC-address serials *are* distinct, so
`/dev/serial/by-id/` separates them — the mechanism systemd already ships works
here and ours would not.

**Deliberately over-inclusive.** A pair in a bridge driver's table is *not*
automatically generic: vendors buy identifier blocks from FTDI and Silicon Labs,
so many are device-specific. The discriminator is what `usb.ids` calls it — a
product name means a vendor bought an id, and **777 pairs are excluded on that
basis**. An *unknown* name counts as chip-like, because the two error directions
cost very different amounts: a false positive costs one `match_product` line in
a manifest, a false negative costs a symlink silently naming the wrong device.

The list is enforced at load: an identifier on it, carried without an
`ambiguity` block, fails the catalog. Without that the downstream symlink check
keys off a block nobody wrote, and passes.

### The corollary — where an ambiguous identifier is still correct

An ambiguous pair is the *right* thing to match on for **permissions** and for
**firmware tools**, because there the operator has already chosen the device. It
is unsafe only as a name in `/dev`, where the kernel matches whatever is
attached.

Stated as a rule so it is not re-derived per entry:

> **Identifiers that select hardware belong in `usb_ids`. Identifiers that
> describe a mode the operator deliberately enters belong in `firmware`.**

`flipper-zero` records `0483:df11` under `firmware` for exactly this reason: as
a DFU target it is correct, and as a symlink rule it would name a TYT radio.

### What replaces the symlink

For USB-serial devices, **the kernel already solved this**. systemd's
`60-serial.rules` populates `/dev/serial/by-id/` from the manufacturer, product
and serial strings in the descriptor, per unit, with no help from us. A board
carrying a serial is already distinguishable there.

That narrows what our own symlinks are *for*, and it is worth being honest that
this is a reduction in scope for the hardware role: **an operator-chosen role
name** — `/dev/rig-991a` is more memorable than any by-id path — which belongs
in station-local configuration with a `match_serial` for that unit, not in a
catalog-wide class rule. For libusb devices such as SDRs, which get no `/dev`
node at all, udev rules were always about *access* rather than naming.

### Consequences applied

- `badgelife` emits no symlink; all four bridge identifiers carry `ambiguity`.
- `flipper-zero` emits no symlink: `0483:5740` is `usb.ids`' "Virtual COM Port",
  ST's reference identifier. One `ATTRS{product}` capture would fix it, and
  writing one we have not read would be guessing.
- `nfc-reader` keeps its symlink: `pn533_usb` is a device driver, not a bridge
  driver. The rule distinguishes them by an explicit list, because `pn533_usb`
  also ends in `_usb` and getting that backwards would suppress a valid symlink.

---

## D-029 — The hardware layer is permissions and mapping; stable naming is mostly solved

**Date:** 2026-08-26. **Status:** accepted. **Supersedes** the claim in
`DESIGN.md` §9 that persistent udev symlinks are "the highest-value single
feature in the project", and the same claim in `CLAUDE.md`.

**Rule.** The hardware role's stated purpose is **permissions, composite-device
mapping, firmware-mode identification, and honest documentation of the cases
nothing solves.** A udev symlink is one tactic among those, used where evidence
supports one — not the headline. Every device records what kind of interface it
presents (`node_kind`), and `scripts/gen_device_naming.py` keeps the accounting
current in `docs/reference/device-naming.md`.

### What forced it

D-028 already conceded, at the end, that systemd's `60-serial.rules` populates
`/dev/serial/by-id/` from the descriptor strings with no help from us, and
called that "a reduction in scope for the hardware role". It did not count.

The Proxmark3 capture is what made counting necessary, and it cuts the other
way from what the concession implied. `2d2d:504d` is proxmark.org's own
registered vendor identifier, so the pair is *unambiguous* — D-028's problem
does not apply. What the device supplies is nothing else: no product string and
**no serial**, byte-identical descriptors across two different boards. by-id
composes its path from manufacturer, product and serial, so two Proxmarks
collide *there* exactly as they would under a naive symlink. Only
`/dev/serial/by-path/` separates them, and by-path is topology: it changes when
the operator moves the cable.

So the honest conclusion was neither "by-id wins" nor "symlinks win". It was
that **neither mechanism solves the identical-device case**, and what we can
offer is the documentation that says so, in the entry's known-problems where
somebody with two boards will find it.

### The accounting

Generated, not asserted. 21 devices in `catalog/hardware/devices/`:

| | Devices |
|---|---|
| by-id covers every confirmed identifier | 5 |
| covers some identifiers and not others | 3 |
| covers none at all — nothing they present is serial | 9 |
| not yet recorded either way | 4 |
| **by-id insufficient for at least one reason** | **17 of 21** |
| carry a udev symlink from this catalog | 5 |
| …of which duplicate a path by-id would have given anyway | **0** |

The last row is the finding, and it was not designed for: every symlink written
so far is on a libusb device that systemd's *serial* rule never sees. The two
mechanisms have not overlapped once. Nothing in the catalog is redundant, and
nothing in it was the main event either.

### What by-id does not give

- **Permissions.** A device only root can open is unusable however stable its
  path. This is what actually stops people, and by-id does nothing for it.
- **Non-serial devices.** Every SDR here, the Ubertooth, and the Proxmark in
  client mode are libusb devices with no `/dev/serial/` entry at all. 12 of 21.
- **Identical units.** The Proxmark case above.
- **Knowing which interface is which.** The Free-WiLi 2 presents four CDC ports
  on one interface. by-id gives each a stable path and labels none of them; a
  stable path to a port you cannot identify is not an answer.

### Consequences applied

- `UsbId` records `node_kind`, `ports`, `port_roles`, `product_string` and
  `reports_serial`. Only the first is required to answer the accounting; the
  rest are what make an answer *useful*.
- **`composite: true` is a declared shape.** Declaring it obliges every
  identifier to say what kind of interface it is, because the point of the
  declaration is answering "which of these is the debug probe" — a question
  by-id structurally cannot answer and a catalog can.
- **`port_roles` takes every port or none.** A partial map reads as a complete
  one.
- **A `match_product` must equal a `product_string` some identifier records
  having read.** `hackrf-one` failed this the moment it was enforced: it shipped
  `match_product: HackRF One` on the strength of nothing, the maintainer owning
  a Pro. Guessing a product string is the mirror image of guessing a VID:PID and
  is just as silent. Closed by mining upstream's USB descriptor, not by asking
  for hardware.
- `DESIGN.md` §9, `CLAUDE.md` and `why-hammunition.md` are rewritten to lead
  with access and mapping rather than with symlinks.

### What this does not change

Symlinks stay. An **operator-chosen role name** — `/dev/rig-991a` beats any
by-id path nobody memorises — remains worth having, and for a libusb device a
symlink is the only stable name there is. What changes is that a symlink now
has to earn its place against a mechanism that already exists, rather than being
assumed to be the deliverable.

---

## D-030 — Evidence flows upward: a class carries only confirmed identifiers

**Date:** 2026-08-26. **Status:** accepted.

**Rule.** A `DeviceClass` may carry **only identifiers confirmed against
hardware or cited to a distribution rule**. Devices contribute identifiers
upward into a class; a class never predicts them downward. Enforced by
`DeviceClass`, not by review. Negative evidence lives in `rejected_ids`, which
cannot generate a udev rule and cannot be inherited.

### Two misses, one shape

`badgelife` was written to generalise: ESP32 badges all need a serial console,
a flasher and rules for native USB plus the bridge chips older designs use.
Build the class once and every badge works. That reasoning is sound and the
class still exists. What was wrong was the *direction* of the inference.

Two boards were flashed and captured, and the class had mispredicted both:

| Device | Class predicted | Hardware presented |
|---|---|---|
| CatSniffer v3 | An ESP32 behind a bridge chip | `2e8a:00c0` — a bare RP2040, no ESP32 in it at all |
| C5 Wardriver v1.1 | Espressif native USB, `303a:1001` | `1a86:55d3` — a WCH CH343 bridge |

Neither is a near miss that better guessing would have caught. The CatSniffer
left the class entirely. The C5 Wardriver landed one hex digit from an
identifier the class was *already carrying* on reputation — `1a86:55d4`, "widely
reported" for the CH9102F — which is the worst possible outcome, because a rule
built on `55d4` would silently never match and look exactly like a bad cable.

Two misses is a pattern, not bad luck. An unconfirmed identifier in a class is
not an isolated guess: **it is a guess with a distribution mechanism**, inherited
by every device that joins.

### The C5 capture's real lesson

The stated reason for waiting until the board was flashed was that an unflashed
ESP32 sits in ROM bootloader mode and presents a different identifier. That was
not the payoff. The payoff is that this board never presented `303a:1001` in any
mode — so a pre-flash capture would have been read as *confirming* a false
assumption rather than exposing one. The discipline was right for a better
reason than the one given for it.

### Why `rejected_ids` rather than deletion

Deleting `1a86:55d4` would lose the finding, and the next person would re-add it
from the same forum posts. Keeping it in `usb_ids` with `confirmed: false` keeps
it able to generate a rule and be inherited. So it moves to a field that can do
neither, alongside what it was assumed to be and what it cost to find out. It is
kept as the worked example, and it is **the last identifier this class will
carry on report alone**.

### Consequences applied

- `DeviceClass` refuses any `usb_ids` entry with `confirmed: false`.
- `badgelife`'s six remaining identifiers each name the capture or the Debian
  source they came from; `1a86:55d4` is in `rejected_ids`.
- `test_unconfirmed_identifiers_are_visibly_unconfirmed` has now been pointed at
  three worked examples and lost two of them, which is the healthy direction. It
  no longer asserts that any unconfirmed identifier exists anywhere — an empty
  list is the goal state, not a reason to keep one around to satisfy a test.
