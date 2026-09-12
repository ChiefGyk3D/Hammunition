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

### Amendment, 2026-09-10 — the packet core is userspace-primary (D-045)

The resolution above names "the AX.25 stack" as a member of the packet core
and the profile prose described the station as the kernel stack with Direwolf
feeding it. Linux 7.1 removed the kernel stack (**D-041**), and on every 7.1
kernel — Kali today, the maintainer's own laptop, Ubuntu 24.04 the day its
HWE kernel moves — the userspace half is the whole station: Direwolf or
QtSoundModem as the modem, pat, LinBPQ, YAAC and Xastir over KISS or AGW.
**The packet core is that userspace path.** The kernel stack — `ax25-tools`
and what sits on it: `axports`, `kissattach`, `ax25d`, NET/ROM, packet
connections as sockets — is the fuller station where the kernel carries it,
and is planned or deferred by name per D-041. The eight units are unchanged;
what changed is which of them is the foundation. `z8530-utils2`, never a
core member, is retired by the same record.

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

### Amendment, 2026-09-07 — the engine could not see a removal, and now refuses one

Rule 2 was documented and not enforced. `backends/apt.py parse_simulation`
read only the `Inst` lines of `apt-get install --simulate` and its docstring
said so; the install runner was `apt-get install --yes` with no
`--no-remove`. So a package that `Breaks:` an installed one — the archive's
`wsjtx-improved` against `wsjtx`, found while correcting its install notes
(#41, issue #42) — would pass the plan, print no removal under `--dry-run`,
and apt would remove the installed package at the apt step. Measured on a
Kali guest with the archive's `wsjtx 3.0.2+dfsg-2` installed:

```
Remv wsjtx [3.0.2+dfsg-2]
Remv wsjtx-data [3.0.2+dfsg-2]
Remv wsjtx-doc [3.0.2+dfsg-2]
Inst wsjtx-improved-data (3.1.0+260522+repack-1 kali-rolling [all])
```

Three removals, and the engine passed that transcript unchanged.

**What changed.** `parse_removals` reads the `Remv` lines (package and
installed version, architecture qualifier dropped); `AptSimulation` carries
them as `removes`; the plan refuses any transaction whose simulation removes
anything, naming every package with its version, attributing it to the unit
whose `conflicts_with_repo_package` declares it — or, when no unit does,
naming that as the catalog gap — and printing the `apt-get remove` the
operator can run *deliberately*. The apt install step, the vendor-`.deb`
install and the executor's post-fetch simulate all run with `--no-remove`,
so if the real solve ever disagrees with the plan-time simulate apt exits
100 (`Packages need to be removed but remove is disabled`, measured the same
day) rather than removing. The plan-time simulate deliberately runs
*without* it, because the `Remv` lines have to exist to be named.

**Why refuse rather than disclose.** Rule 1 says coexistence is the default
and replacement is a separate act. A `Breaks:` is the case where coexistence
is impossible — apt will not install the one beside the other — so the only
honest shapes are refuse, or remove on the operator's say-so. Removal on
their say-so is `sudo apt-get remove <name>`, which the refusal prints; an
engine flag that removes for them would be `--yes` under another name
(D-021's objection, applied to removal). The refusal keeps the operator's
hand on the one command that takes something off their machine.

**What it unblocks.** Rule 2's mechanism was the reason `wsjtx-improved`
stayed on a vendor `.deb` that cannot install on Kali (issue #24). With
removals seen and refused, an archive `wsjtx-improved` block with
`conflicts_with_repo_package: wsjtx` is exactly the disclosed displacement
this decision describes.

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


### D-028 amendment, 2026-08-27 — a distribution says it out loud

The strongest evidence for this decision was not ours and had been sitting in
the archive the whole time. Debian ships `gpsd`'s `60-gpsd.rules` with **five
identifiers commented out**, each under the line:

```
# !!! rule disabled in Debian as it matches too many other devices
```

They are `0403:6001` (FTDI FT232), `10c4:ea60` and `10c4:ea71` (Silicon Labs
CP210x and CP2108), and `067b:2303` (Prolific PL2303) **twice**. Two of those
are identifiers this project had already had to stop claiming, for the same
reason pointed the other way: `10c4:ea60` is what `badgelife` was naming
`/dev/badge`, and `0403:6001` is the pair D-028's opening paragraph uses as its
example. A distribution maintainer reached this conclusion independently, about
the same silicon, and acted on it in a file they ship.

The same rules file opens with the GPSD project stating the principle outright,
in 2010:

> GPSes don't have their own USB device class. They're serial-over-USB devices,
> so what you see is actually the ID of the serial-over-USB chip.

**What this changes.** `AmbiguityBasis` gains `distribution_disabled`, ranked
above every existing basis, because it is not an inference from a driver table
or a name — it is a maintainer's conclusion, with their reason attached.
`scripts/udev-sweep.sh` now extracts commented-out rules deliberately rather
than discarding them as comments.

**Corrected 2026-08-27, same day.** This paragraph first read "13 identifiers
across five packages — `gpsd`, `dfu-util`, `argyll`, `ponyprog` and `knxd`" and
said `dfu-util` disables `0483:df11`. Both were wrong, from reading a sweep row
instead of opening the file. dfu-util's rule for `0483:df11` is **live**, as
`TAG+="uaccess"`; what is commented out below it is an alternative `plugdev`
form offered "on older systems". ponyprog's are CH341 modes it does not use and
knxd's is `dead:beef`.

The distinction was already in the data and went unused: **only a
commented-out rule with a stated reason is evidence.** The generator now
requires one, which is the difference between a maintainer's judgement and a
line of documentation. Archive-wide the honest figure is **5 rows, 4 distinct
identifiers, all in `gpsd`** — `0403:6001`, `10c4:ea60`, `10c4:ea71` and
`067b:2303` twice. Fewer, and every one of them a bridge chip, which is the
claim that mattered.

That this correction is D-031's own failure mode, made in the commit that
recorded a different instance of it, is not a coincidence worth softening: the
check catches commit messages, and nothing catches reading a column and
believing it.

`gps-receiver` carries those five in `rejected_ids` with Debian's own reason,
which is what that field was built for one decision earlier.

**A bug the same file exposed.** The sweep attributed the wrong description to
`1546:01a9`, calling a u-blox 9 a Silicon Labs CP210x. The extractor rejected
any comment of 60 characters or more as boilerplate — the u-blox line is 73 —
and then *kept the previous comment* rather than clearing the field. 156 of
2,750 rows carried a description that long. A rejected comment now clears it:
no description is honest, someone else's is not.

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

---

## D-031 — Verify the effect, not the exit status

**Date:** 2026-08-26. **Status:** accepted.

**Rule.** A tool reporting success is not evidence that the tool did anything.
Before claiming a change, **check the artefact you meant to change**, and where
the claim is made in a commit message, let a hook check it rather than a person
remember to. `scripts/check_commit_claims.py` runs as a `commit-msg` hook and in
CI.

### Three bugs, one shape

| | What happened | What was read instead |
|---|---|---|
| The D-028 amendment | A `sed` anchor matched text that did not exist, so the edit no-oped. The commit message described a change the commit did not contain. | `sed`'s exit status, which is always 0, and a `grep` count checked *after* committing |
| The udev sweep | `dpkg-deb -x` writes files and *then* exits non-zero under rootless podman, so `\|\| continue` fired after the write. All 280 packages logged "bad archive" while 2,750 rows were emitted. | The row count. The log was never opened. |
| The `state/` directory | Written, and never committed, because a `.gitignore` pattern matched it. Nothing errored anywhere. | Nothing — that is the point. Absence of an error was taken as presence of a file. |

D-025 already says a claim gets re-verified when it becomes decisive. This is the
narrower and more embarrassing case: **verifying your own writes**, at the moment
you make them. The distance between them is the distance between "was this still
true a month later" and "did this happen at all".

### What the hook checks

Three things, chosen because each maps to one of the bugs above:

1. **Restated decisions.** A message asserting what a decision *says* — "D-028
   no longer rests on an esptool constant" — must touch that decision's own
   section. A mention of `D-028` elsewhere in the diff does not count, and that
   distinction is load-bearing: the first version of this check passed the very
   commit it was written for, because that commit added schema docstrings which
   happen to say "D-028" while never touching the decision.
2. **Claimed paths.** A message saying it adds
   `catalog/hardware/devices/minino.yaml` requires that path in the commit.
3. **Phantom paths.** Any path the message names that exists on disk but is
   neither tracked nor staged. That is the `state/` bug precisely, and it is the
   one no other tool reports.

Ordinary citation is deliberately untouched: "per D-014" asserts nothing about
the diff and does not fire. A check that flags correct behaviour gets switched
off, which would cost more than the bug it prevents.

### Verified by reintroducing the bug

The check was run against this repository's own history and refuses `717ba26`,
the commit whose amendment silently matched nothing, while passing every other
commit around it. The same method as `scripts/audit_gitignore.py`, and for the
same reason: **a checker that has never been shown to catch the thing it was
written for is itself an unverified claim.**

### The second half, added 2026-08-27

The commit above shipped with a gap stated in its own message: the hook catches
a message describing work a commit does not contain, and **nothing catches
reading a column and believing it.** One commit later that gap produced exactly
the predicted failure — a D-028 amendment asserting that `dfu-util` disables
`0483:df11`, drawn from a sweep row, with the rules file never opened. It does
not; the rule is live as `TAG+="uaccess"`.

`scripts/check_rule_citations.py` closes it for the case where these claims are
load-bearing. Most of the hardware catalog's identifiers cite a shipped rules
file by name, which makes the claim checkable against the same measurement it
came from:

- an identifier citing `60-gpsd.rules` must appear in a file of that name;
- a `rejected_ids` entry saying the distribution disabled a rule must match a
  sweep row that is commented out **and carries a reason**;
- an identifier carried in `usb_ids` must not be one that was commented out;
- and `basis: distribution_disabled` is checked against the whole archive rather
  than against whichever file the prose happens to name.

90 identifiers across 15 rules files, all verified. It runs in the test suite,
and weekly in CI — the sweep is 280 packages and ~264 MB, too expensive per
push, and failing an unrelated pull request because a Debian upload changed a
rule is how a check gets ignored.

**Falsified before being trusted**, and the first version failed that: citing
the wrong file went red and reintroducing the original `dfu-util` claim went
red, but *claiming a live rule was disabled* stayed green. Most of
`gps-receiver`'s `rejected_ids` say "disabled by Debian" without naming a file,
and the check only looked when a file was named — a hole precisely where the
claims are. Fixed, re-falsified, all three red.

**What it does not cover**, said plainly: prose in `docs/`. The wrong claim
appeared there too, and a check that pattern-matched English would be the kind
nobody trusts. The catalog is where a claim becomes load-bearing — it generates
rules — and that is where this is enforced.

### Enabling it

```
git config core.hooksPath .githooks
```

Not enabled automatically — git will not run hooks from a cloned repository, by
design, and a project that works around that is asking contributors to execute
code on clone. CI runs the same script over every commit in a pull request, so
the check is enforced whether or not a contributor opts in locally.

---

## D-032 — Upstream liveness is the default branch's head commit, never GitHub's activity fields

**Date:** 2026-08-28. **Status:** accepted.

**Rule.** When the catalog or an inventory states that an upstream project is
active, dormant, or dead, that claim is measured from **the newest commit on the
project's default branch**. GitHub's `updated_at` and `pushed_at` are not
evidence of development and must not be published as if they were.

```
gh api repos/<owner>/<repo> --jq .default_branch
gh api "repos/<owner>/<repo>/commits?sha=<branch>&per_page=1" --jq '.[0].commit.author.date'
```

### What the two rejected fields actually mean

| Field | Moves when | Why it is wrong here |
|---|---|---|
| `updated_at` | **Somebody stars the repository.** Also on a fork, a description edit, a topic change. | It measures attention, not work. A dead project that gets discovered looks freshly maintained. |
| `pushed_at` | A push to **any** branch, including a fork's. | The near-miss. Overstated 5 of the 9 upstreams in the Skywave delta. |

### What it cost

`skywave-inventory.md` published an "active (date)" column built from
`updated_at`, and `QUESTIONS.md` posed a maintainer decision on top of it:

| Unit | Published as | Actual last commit | Gap |
|---|---|---|---|
| Kalibrate-RTL | active (2026-08-19) | 2022-02-01 | 4.5 years |
| SuperSDR | active (2026-02-18) | 2022-12-31 | 3.7 years |
| directKiwi | last touched 2025-10-09 | 2023-03-03 | 2.5 years |

Both corrections changed something downstream. Kalibrate-RTL has also **never cut
a tag**, so its manifest needs a commit pin and a `pin_review` (**D-024**) rather
than the tag the "active" reading implied. And **Q-007** — whether to carry an
unlicensed KiwiSDR client — was asked with "upstream is active" in its premise;
on the corrected dates the recommended option carries software that is both
unlicensed *and* three and a half years stale, while the option previously
dismissed as "no improvement" is the only maintained client of the three.

The irony is recorded because it is the useful part: the paragraph immediately
below that table claimed the findings were *"tested against the repositories
rather than taken from GitHub's metadata"*. The prose asserting the discipline
sat directly beneath a table that had abandoned it.

### Relationship to the neighbours

**D-018** says an external claim is tested before it is published. **D-025** says
a claim is re-verified when it becomes decisive. This is the third face of the
same coin and the one neither covers: *the field you measured was never the field
you wanted*, so testing it again the same way would have confirmed the error.
When a metric is a proxy, name what it actually counts before publishing it as
what you meant.

**Consequence.** Any generator or document asserting upstream health records the
method beside the number, so the next reader can tell what was counted.
`gen_skywave_inventory.py` now carries the query in a comment and the doc carries
a `UPSTREAM_METHOD` section stating both the right field and the wrong ones.

---

## D-033 — An upstream with no licence is judged on adoption and on what we actually do with it

**Date:** 2026-08-29. **Status:** accepted. **Resolves:** Q-007.
**Decided by:** the maintainer.

**Rule.** A missing licence does not by itself keep software out of the catalog.
Weigh how widely the community already relies on it, and weigh what this project
actually does with the code. Where both point the same way, carry it, record the
licence state plainly in the manifest, and revisit if the situation changes.

### What "no licence" means, precisely

Default copyright: no grant to redistribute or to modify. That is a real
constraint and this decision does not pretend otherwise. What it does is
distinguish the constraint from the risk.

**We do not redistribute.** The catalog is data — a name, a URL, a digest and a
description of what the software does. Facts about third-party software are
freely usable, which `ahrl-inventory.md` already states about AHRL's own
provenance record. The bytes reach the operator's machine from the author's own
server or repository at install time, by the same act the operator would perform
by hand. **D-001** already forbids mirroring for an unrelated reason and that
prohibition does the work here too.

So the exposure of carrying an unlicensed upstream is closer to that of a
bookmark than of a fork. It is not zero, and it is not the exposure a
distribution takes on when it builds and ships a binary.

### Why adoption is the second input

The maintainer's reasoning, recorded because it is the load-bearing half:
**most authors of small ham and SDR utilities are not lawyers and do not
understand licence compliance.** A missing `LICENSE` file is very often an
oversight rather than a reservation of rights, and reading it as a deliberate
refusal would remove from the catalog software the community has depended on
for years — while doing nothing to make anyone safer.

Where a project is already carried by Skywave Linux, by AHRL, by a distribution,
or by a large body of users, that adoption is evidence about the author's actual
posture. It is not permission and the manifest must not imply that it is.

### What a manifest must still do

* **State the licence position in `upstream_support`.** "No LICENSE file, no
  header, checked in-tree on <date>" — the same standard
  `licence-verification.md` already applies. Never write "unlicensed" as if it
  were a licence, and never leave it unsaid.
* **Never mirror the source.** Fetch from the author's own URL, with a digest.
* **Prefer asking.** Where an author is reachable, a request for an explicit
  licence is worth more than this decision is, and one accepted pull request
  retires the question permanently.

### What this does not license

It does not extend to redistributing, vendoring, forking or relicensing, and it
does not apply to the engine — `catalog/` is CC0-1.0 and `src/` is
GPL-3.0-or-later (**D-023**), and neither may absorb third-party code without a
grant. If a rights-holder objects, the entry goes; that is the cost of the
position and it is a cheap one, because removing a manifest costs nothing but
the manifest.

**First consequence.** `supersdr` is carried. It has no LICENSE, no header and a
null GitHub licence field, and its last commit is 2022-12-31 — both measured.
Both facts go in the manifest.

---

## D-034 — Cellular tooling is staged, and the line is transmit

**Date:** 2026-08-29. **Status:** accepted. **Resolves:** Q-008.
**Decided by:** the maintainer.

**Rule.** The cellular cluster is carried in full, **staged rather than
filtered**, and every stage is behind an affirmative consent gate (**D-021**).

| Stage | Contents | Where |
|---|---|---|
| **1.0** | Receive and decode only — `gr-gsm`, `QCSuper`, the LTE decoders, IMSI-catcher-class receivers | the consent-gated `rf-research` profile |
| **post-1.0** | Transmit-capable network stacks — `srsRAN_4G`, the Osmocom core, `osmo-trx`, `OsmocomBB`, `intrusive-lte-mme`, `sni5gect` | a separate consent-gated `cellular` profile |

**The dividing line is transmit, not topic.** Receiving a signal already in the
air and operating a cellular network are different acts with different
authorisations behind them, and grouping them by subject would hide that.

### Why staged rather than excluded

The transmit stacks are legitimate software with legitimate users — authorised
engagements, shielded labs, vendors, academics — and DragonOS ships them. The
objection was never to the software. It was that a one-command installer aimed
at licensed hams is the wrong delivery mechanism *today*, before there is a
`cellular` profile with its own gate and before `docs/rf-security/` carries the
framing CLAUDE.md already requires of it.

So they are **scheduled, not refused**. Each excluded unit gets a catalog entry
recording that it is post-1.0 and why, per `PARITY-POLICY.md`'s rule against
silent drops. "Not yet" and "not ever" are different claims and the docs must
not blur them.

### What the gate does and does not do

Per **D-021** the gate discloses a capability and asks the operator to affirm
the authorisation they hold. It does not adjudicate law, in either direction —
it neither grants permission nor refuses on anyone's behalf, and `--yes` cannot
satisfy it. The post-1.0 `cellular` profile gets its own `env_var`, because a
shared one would let an opt-in to receiving satisfy an opt-in to transmitting.

**Consequence for 1.0.** `rf-research`'s contents are now settled rather than
provisional, and its `deliberately_excludes` says *post-1.0*, not *undecided*.

---

## D-035 — A missing station value defers one file; it does not refuse the transaction

**Date:** 2026-08-29. **Status:** accepted. **Closes:** DESIGN.md §15 question 5,
open and blocking since the 1.0 packet core was admitted.

**Rule.** Configuration this catalog writes on the operator's behalf is
templated from station-local values — callsign, grid square, node alias. When a
value is unknown, the file is **not written and is reported**, and everything
else in the transaction proceeds.

### Why deferral rather than refusal

The old behaviour was a blocker: any manifest with a `config_files` block
failed resolution, and because a profile fails if any member fails, the
**`packet` profile could not be installed by anyone**. Nineteen packages —
Direwolf, the AX.25 stack, Pat, Xastir, LinBPQ — refused because one of them did
not know a callsign. That is the profile the 73Linux delta was acquired for.

The maintainer's bar, recorded because it is the reasoning and not just the
verdict: *getting a user 95% of the way is a success as long as there are no
true blockers to 100% besides some user config.* An unknown callsign is user
config. It is not a true blocker, and treating it as one served nobody.

So `Deferral` sits beside `Blocker` in the planner and the two mean different
things. A blocker means the machine must not be touched. A deferral means most
of what was asked for happens, one part does not, and the report names it
precisely with the command that would let it.

### Three properties that are not negotiable

**Nothing is invented.** There is no default callsign, no placeholder, no
`CHANGEME`. A configuration file written with a made-up callsign would transmit
it, and the station identifier is the operator's legal identity on the air.

**A partial file is never written.** A config missing one of three values is
deferred whole. A file with `{station.callsign}` still in it looks configured
and is not, which is worse than an absent file because the operator has no
reason to look.

**Existing files are backed up before being replaced**, once. These paths
belong to the distribution's packages as often as to us — overwriting a
hand-tuned `/etc/ax25/axports` without a copy is damage no transaction log can
undo. The backup is written only if one does not already exist, so a second run
cannot replace the operator's original with our own previous output.

### How values arrive

Three sources, later winning: `$XDG_CONFIG_HOME/hammunition/station.yml`, then
`--callsign` and its siblings, then an interactive prompt. The prompt happens
only when the request **actually needs a value**, standard input and output are
both a terminal, and `--yes` was not given. Prompting for a callsign to install
a spectrum analyser is how people learn to dismiss prompts, which is precisely
what would make the consent gates of **D-021** worthless.

The file is mode 0600 and its path is resolved owner-aware, so running under
`sudo` still writes to the invoking user's home rather than root's.

### Relationship to D-012

**D-012** scoped `system_modifications` to udev rules, groups and blacklists
and explicitly did not cover templated config. This is that gap filled, and it
is filled as a separate concept rather than a fourth modification kind, because
a config file is the only one of the four that can be *partly* possible.

## D-036 — Desktop integration is curated submenus, generated per desktop environment

**Date:** 2026-08-29. **Status:** accepted (maintainer, during the first VM
verification campaign). **Depends on:** the M3 launcher-generation work, which
is the same unwritten machinery.

**Rule.** Hammunition organizes what it installs into curated submenus, the way
AHRL's menu tree did — and generates that organization from the catalog's
existing `categories` tags, per desktop environment. The DEs that must work,
set by the OS ladder we support: **GNOME** (Debian 13, Ubuntu), **COSMIC**
(Pop!_OS 24.04), **Xfce** (Kali's default, Parrot).

### What is measured and what is not yet

Today's state, measured on the Parrot VM (2026-08-29): apt-installed GUI
packages ship their own `.desktop` entries and appear in the DE's flat menus
(chirp 1, flrig 1, gpsd-clients 2); autotools `make install` frequently
installs one under `/usr/local/share/applications`; the 14 units needing a
*generated* launcher get nothing, because the schema's `Launcher` block has no
consumer. Curation rides on the same generator, so this decision and that gap
are one work item.

What is **not yet measured** and must be before implementation, in the spirit
of D-014 — one mechanism per DE, verified rather than assumed:

- **Xfce** consumes the freedesktop menu spec directly — `.menu` XML,
  `.directory` entries, `xdg-desktop-menu` — the mechanism AHRL already used.
  Expected to be the straightforward case; verify on Kali/Parrot.
- **GNOME Shell renders no nested menus.** Its app grid folders come from
  `org.gnome.desktop.app-folders` gsettings, a different mechanism entirely,
  and per-user rather than system-wide. Generating `.menu` XML alone would
  produce curation Xfce shows and GNOME silently ignores.
- **COSMIC** is new and its app-library folder story must be read from the
  code or tested on Pop 24.04, not inferred.

### Boundaries carried over from existing decisions

The organization is generated **from the catalog's flat `categories` tags**
(D-003: tags overlap, never nest — a program may appear in two submenus, as 13
AHRL programs did). Menu data the engine writes is a system modification like
any other: printed before it happens, recorded in the transaction log, removed
by uninstall. And per D-022, we add our curated tree alongside the DE's own
organization; we never rewrite or suppress what the distribution's packages
put in the standard categories.

## D-014 amendment, 2026-08-30 — pipx and CPAN re-measured, and both are zeros now

**D-014** justifies every backend by a named unit. Two of the backends still
listed as required for 1.0 no longer have one, because the catalog moved out
from under the requirement and nobody re-measured:

- **pipx** was required for exactly one unit: CHIRP, which AHRL installs as a
  bundled wheel through `pipx install --system-site-packages`. This catalog's
  `chirp` resolved to **apt on all five targets** (measured 2026-08-28, and
  the Parrot VM ran the apt install on 2026-08-29). The other AHRL pipx-family
  unit, `pyautogui`, was retired as developer tooling. Zero manifests declare
  `method: pipx`.
- **CPAN** was required for exactly one unit: `aa-analyzer`, whose install
  begins with `cpan install Device/SerialPort.pm`. `aa-analyzer` is
  **SUPERSEDE → `flaa`** (accepted; both are RigExpert analyser front ends).
  Zero manifests need a Perl module from anywhere.

**Consequence.** The 1.0 backend list contracts to: apt, source, git, binary
(all written) plus **venv** (real users: `not1mm`, `nanovna-saver`, and the
`radiosonde_auto_rx` REVIVE waits on it by design) and **launcher
generation** (14 units, now fused with D-036). The `PipxInstall` schema stub
stays — a community-tier manifest may one day declare it, and the engine
refuses it by name exactly as before — but nobody builds a backend for a
measured zero. This is the same motion as the cargo amendment above: the
requirement was real when measured, the world moved, and the measurement was
repeated before the work was done rather than after.

The station profile's `pipx` **apt package** is unrelated and stays: that is
a tool installed *for the operator*, not a backend the engine uses.

## D-036 addendum, 2026-08-30 — two of the three menu mechanisms measured

D-036 named three per-DE mechanisms and called all three unmeasured. Two are
now measured on the target VMs; COSMIC still waits for the Pop!_OS image.

- **GNOME (Debian 13 VM): fully drivable, and better than hoped.** The
  `org.gnome.desktop.app-folders` schema reads and writes headless via
  `dbus-run-session gsettings ...` (persisting through dconf's user
  database), and the relocatable per-folder schema carries `name`, `apps`,
  `excluded-apps` — and **`categories`**. A folder declaring
  `categories=['HamRadio']` populates itself from the same `Categories=`
  values the launcher generator already writes, so GNOME curation is one
  folder declaration, not a maintained app list. Verified round-trip:
  set `['HamRadio']`, read it back, restored the default.
- **Xfce (Kali VM): the classic path, present as expected.**
  `xdg-desktop-menu` is installed, the menu prefix is `xfce-`, and user
  merged menus belong in `~/.config/menus/xfce-applications-merged/`.
  File-level mechanics confirmed; whether the rendered menu looks right is a
  console-lane check, like every GUI claim.
- **COSMIC: still unmeasured.** Nothing asserted until Pop 24.04 exists on
  the ladder.

Implementation note for whoever builds it: both measured mechanisms are
per-user and unprivileged, exactly like the launcher generator's artifacts —
the whole menu layer can honour the privilege rule with zero sudo.

## D-036 addendum, 2026-09-01 — the curated tree was seven entries wide; it now places what the packages ship

The menu layer went into the engine on 2026-08-30 with submenus that
included by the `X-Hammunition-<category>` marker — which only the entries
Hammunition *generates* carry. Rendered on the Kali VM with the whole
catalog installed and parsed back with gnome-menus' implementation of the
spec, the Ham Radio tree held **7 entries** while **43** desktop entries the
distribution's own packages ship with `Categories=…HamRadio…` sat under
Internet (fldigi, xastir), Multimedia (wsjtx), Education (gpredict) and
Other (chirp). GNOME was better off by accident: its folder's
`categories=['HamRadio']` gathers those 43, though not the 23 entries
catalog packages ship under other tags (`kali-radio-frequency`,
`AudioVideo`, `Science`). "Alongside the DE's own organization" was true
and the curation was nearly empty — the "run it and look at it" class of
bug.

**Measured, then built.** `dpkg -S` on those 43 mapped 42 to a manifest
through the apt package that shipped them; the 43rd (`gridtracker2`) is a
`.deb` unit and maps through its `deb_package`. So `menus apply` now asks
`dpkg -L` for every catalog package present on the machine, places each
`.desktop` it ships under the submenu of every category its manifest
carries — the menu spec's `<Filename>` include — and gathers anything
`HamRadio`-tagged that no manifest claimed at the tree's top level, with
the placed ids excluded there so nothing shows twice. GNOME gets the same
ids unioned into the folder's `apps`. Re-measured on Kali: 73 entries
placed 130 times, every one under its submenu; the source-built units
(`fldigi`'s family, `wsjtx`, `qlog`, `garim` — installed by `make install`
under `/usr/local`, so no dpkg record) land at the top level as designed.
The GNOME half round-tripped headless on the Debian 13 VM (71 apps, the
same 71 on a second run).

**Boundaries kept.** One taxonomy: categories still come from
`catalog/categories.yaml`, which now also carries each tag's menu title
(the engine cannot know `sdr` is SDR and rendered "Sdr"). No maintained app
list: the desktop-file ids are read from the machine at apply time, never
typed into the catalog. The whole catalog is consulted rather than the
transaction log, because being in the catalog *is* the curation and an
operator's own earlier `apt install fldigi` deserves the same submenu. The
DE's own copies are untouched (D-022). Still open: a source build's entries
could be placed too, from cmake's `install_manifest.txt` where one exists;
and the menu files are not yet in the transaction log, so `uninstall` does
not remove them — both named here rather than left to be rediscovered.

## D-031 addendum, 2026-09-02 — the effect check now covers what a build installs

**The finding.** `js8call` was recorded `verified: true` on Parrot, Debian,
Kali and Ubuntu 26.04 — a full-catalog pass on each — and none of the four
has a `/usr/local/bin/js8call`. JS8Call-improved v3.0.3's `CMakeLists.txt`
has no install rule for its executable (the only `install()` is in
`resources/debian/CMakeLists.txt`, which nothing adds as a subdirectory), so
`cmake --install` exits 0, writes an empty `install_manifest.txt`, and
installs nothing. Every command in the transaction exited 0, and the effect
check re-read apt for the build dependencies and found them present. It
never asked whether the thing the operator wanted existed, because it had no
check for a built artefact at all — the D-031 shape exactly, one layer up
from the `sed` and `dpkg-deb` cases the decision was written from.

**The check.** `transaction_end` gains a `binary` kind: for every source,
git and non-`.deb` binary unit in the plan, each `binaries` entry must be an
executable at `<prefix>/bin/<install_as>` after the run. A `.deb`'s contents
are apt's to place and apt is asked about them; a venv's entry points are
wrappers in the operator's `~/.local/bin`, a different mechanism with its
own removal check.

**What it found on the first pass, before any VM was touched.** Two of the
26 manifests that declare `binaries` would have failed it. `js8call`, above,
needed `provides_install_target: false` — and that path then needed fixing
too, because the explicit copy looked for the build's output in the *source*
tree, where cmake never writes it; every unit that had used the path so far
was an in-tree qmake or make build, so nothing had noticed. `ais-catcher`
declared `install_as: ais-catcher` while its own install rule places
`AIS-catcher`, the name the manifest's launcher already execs. The `binaries`
field on a unit whose build installs itself is documentation, and this is the
check that makes documentation have to be true: `install_as` now has to say
what the install rule does. Both rebuilt and confirmed on a VM the same
night. Of the other 24 declarations, 23 match what the three full-catalog
VMs hold in `/usr/local/bin`, and the 24th (`nanovna-saver`'s
`NanoVNASaver`) belongs to its ARM-only binary block and is absent from all
three x86 VMs as it should be — the x86 block is a venv, which the check
does not read.

**Still not covered.** A build that installs itself under the name it
declares but is broken at runtime; and a unit that declares no `binaries`
at all, which this check cannot see — the schema does not require the field,
so a source unit with none is trusted on its install step's exit code as
before. The `m5-parity-verified.md` counts predate this check; they are
build-dependency counts for source units until re-run.

## D-036 addendum, 2026-09-02 — the merged file's name is decided from the machine, or refused

`menus apply` took the merged file's prefix from `$XDG_MENU_PREFIX` and
wrote `applications-merged/hammunition.menu` when the variable was unset.
Measured across every machine to hand — the four VMs and the maintainer's
laptop — **none has a bare `applications.menu`**: Parrot's `/etc/xdg/menus`
holds `kf5-`, `mate-`, `plasma-` and `xfce-` roots, Debian and the laptop
`gnome-`, Kali `xfce-`, the Ubuntu server images none. So every run made
over SSH, under `sudo`, or from a shell older than the login had written a
file no root menu merges, and reported success. The Debian "71 apps,
idempotent" measurement in the previous addendum was the GNOME gsettings
half; its file half had merged into nothing.

Now: an explicit `--menu-prefix`, else the session variable, else the one
prefixed root installed, else a refusal naming the candidates. Guessing
between Parrot's four would write the menu for the desktops the operator
does not log into. Verified on Parrot: the bare-SSH run refuses and lists
the four; `--menu-prefix plasma-` writes a file gnome-menus' spec parser
reads back from `plasma-applications.menu` as 25 populated submenus with
the source-built entries gathered at the top.

## D-037 — A `node` build is acceptable when it is disclosed as a requirement and refused when Node is absent or too old

**Date:** 2026-09-02. **Status:** accepted (maintainer, closing Q-016).
**Depends on:** D-014 (a backend is justified by a named unit), D-016
(refuse at plan time, never partway), D-021's spirit (disclose, do not
decide for the operator), Q-006 (openhamclock is the HamClock default).

**Rule.** The engine may build a unit with Node and npm. Two conditions,
both the maintainer's:

1. **Node is disclosed as a requirement of that unit**, in the manifest's
   documentation and in the plan the operator reads before anything runs —
   not discovered as a build failure. A unit that needs Node says so the way
   a unit that needs a transceiver says so.
2. **When Node does not exist on the machine, or the version is not new
   enough, the engine refuses at plan time** and says which: the floor the
   unit declares, the version found (or that none was), and where a
   qualifying one comes from. It never fetches Node itself.

**Where Node comes from.** The distribution's own `nodejs` and `npm`
packages, declared as build dependencies like any toolchain, so apt installs
them inside the transaction and `--dry-run` prints them. The floor is
checked against the archive's candidate (or the installed version), never
assumed — and the first unit needed that check on the first day: see the
second amendment, where Ubuntu 24.04's 18.19 turned out not to clear it.
NodeSource and every
other third-party Node repository are out: that is the third-party-apt-repo
backend, which is a separate security decision the maintainer has not made.

**What the build is.** The three npm invocations Q-016 measured, every one
with `--ignore-scripts` so no third-party lifecycle code runs: `npm ci`
against the lock file inside the sha256-pinned source tarball (728 tarballs,
each pinned by its sha512 `integrity` field — the closure is transitively
verified from one manifest hash), `npm run build`, `npm prune --omit=dev`.
The tree installs per-user like a venv unit; the launcher binds loopback
(`HOST=127.0.0.1`) because the code's own default is every interface.

**Why the conditions matter.** A registry fetch during a build is new here;
the operator reading the plan must see that a unit will do it and what it
needs before they say yes. And "install Node from somewhere" is exactly the
`curl | bash` habit AHRL's `aiscatcher-install` line shows and this project
exists to refuse — so the engine names the gap and stops.

**What this does not decide.** Whether the P.533 propagation WASM
(upstream's `prebuild` fetches it from a moving tag, skipped here) is carried
as a pinned artefact. The built-in model serves until an operator asks.

**Amendment, 2026-09-02 — what the loopback bind is and is not.** Written
while carrying the first unit. The engine's wrapper sets `HOST=127.0.0.1`
and the schema refuses a manifest that sets `HOST` at all, so the *engine's*
default is loopback and no catalog entry can widen it. openhamclock's own
config loader then reads the `.env` it creates beside `server.js` and writes
every key into the environment over whatever was there — its `.env.example`
says `HOST=localhost`, so the result is still loopback, but an operator who
edits that one line to `0.0.0.0` has widened it, and the wrapper does not
stop them. That is the right split: the engine chooses the safe default and
the operator's own config file is theirs to change (D-021's shape — disclose,
do not adjudicate). The manifest's `known_problems` says so, and says the
other thing `HOST` does not govern: the WSJT-X integration binds UDP 2237 on
every interface at start, and only `WSJTX_ENABLED=false` in that `.env` stops
it. Read from `server/config.js` and `server/routes/wsjtx.js` at v26.7.0, not
assumed from `.env.example`'s comments.

**Second amendment, 2026-09-02 — two claims above were false, and the fixes
are in the schema.** Both found by installing through the engine and
measuring, the same day the rule was written.

1. *"The code's own default is every interface"* understated it: v26.7.0
   ignores `HOST` entirely. `server.js:364` is `app.listen(PORT, '0.0.0.0',
   ...)`, so with the wrapper's `HOST=127.0.0.1` in force the first real
   install still showed `00000000:0BB9` in `/proc/net/tcp`. Upstream main
   has the same line. The fix is one token in one line, so `NodeInstall`
   gained `patches` — the same `Patch` model the source backend takes,
   applied after extraction and before the lock-file check, `patch` joining
   the build dependencies — and the manifest carries the diff with its
   evidence. With it, and the `.env` loader's `HOST=localhost`, the bind
   measures `[::1]:3001` only: Node binds `localhost` as IPv6 loopback, so
   the launcher opens `http://localhost:3001` rather than an IPv4 address.
   The rule stands; what changed is that the engine's loopback default now
   *has an effect* on this unit.
2. *"Every target's archive Node clears the floor"* was read from Vite's
   `engines` range, which describes the bundler. The server needs
   `require()` of an ES module (`axios-cookiejar-support` 6.x), which is Node
   20.19+, and on Ubuntu 24.04's 18.19 the build succeeds and the server
   dies at first start with `ERR_REQUIRE_ESM`. So the floor is **20.19**,
   and because it is a minor the schema field became `node_min_version`, a
   `MAJOR.MINOR` string compared on both numbers — `node_min_major: 20`
   would have admitted 20.18. Ubuntu 24.04 is now refused at plan time by
   name. That is the rule working as written: the requirement is disclosed,
   the refusal is specific, and Node is not fetched to meet it. A floor is
   measured by running the unit, never read from `engines`.

## D-038 — On a target that installs from more than one release, an apt transaction the default release cannot resolve is resolved from the release the machine already installs from, disclosed by name

**Date:** 2026-09-02. **Status:** accepted.
**Depends on:** D-016 (refuse at plan time, never partway), D-022 (coexist
and disclose, never remove or replace silently), D-025 (re-verify a claim
when it becomes decisive), D-031 (verify the effect, not the exit status).

**What was measured.** A clean Parrot 7.3 VM, restored to its
`clean-baseline` snapshot, ran every profile as one transaction. Eight
installed and confirmed, one stopped at its consent gate as it should, one
was refused by name for its `apt_repos` units, and **five passed the plan
and failed at the first apt command**, in about one second each —
`digital-modes`, `electronics`, `listening`, `logging` and `propagation`.
Every failure was the same text from apt 3.0.3:

```
E: Unable to correct problems, you have held broken packages.
   Unable to satisfy dependencies. Reached two conflicting decisions:
   1. libcurl4t64:amd64=8.14.1-2+deb13u5 is not selected for install
   2. libcurl4t64:amd64=8.14.1-2+deb13u5 is selected as a downgrade because:
      1. libcurl4-openssl-dev:amd64=8.14.1-2+deb13u5 is selected for install
      2. libcurl4-openssl-dev:amd64=8.14.1-2+deb13u5 Depends libcurl4t64 (= 8.14.1-2+deb13u5)
```

The cause is the target, not the catalog. Parrot's baseline installs
**197 of its 3,801 packages from `echo-backports`** — `apt-cache policy`
reads it as `o=Parrot,a=parrot-backports,n=echo-backports`, pinned 599
against the main release's 600 in `/etc/apt/preferences.d/`. The runtimes
came from backports; the `-dev` packages the catalog's build dependencies
name are still the main release's, and a Debian `-dev` package depends on
its runtime at an **exact** version. Three chains were confirmed on the
machine: `libcurl4t64` 8.21 (backports) against `libcurl4-openssl-dev` 8.14
(main); `gir1.2-atk-1.0` 2.61 against `libatk1.0-dev` 2.56;
`libqt6webenginecore6` 6.10 against `qt6-webengine-dev` 6.8. Every failed
profile pulls at least one of those three in. apt will not downgrade a
pinned-higher package to satisfy a dependency, and it is right not to.

This was not the first sighting. `vm-campaign-digital-modes.md` recorded
the same skew on 2026-08-30 — glfer and xwefax against the GTK dev chain —
and worked around it by hand on the VM. A workaround applied to an image
is exactly the evidence D-025 says to re-verify when it becomes decisive;
here it became decisive when a clean snapshot took five profiles down.

**What resolves it.** `apt-get install --simulate --yes --target-release
parrot-backports <the same list>` resolves all five failed lines that were
re-run by hand — digital-modes at 249 packages with 19 from backports,
electronics 110/3, listening 263/10, logging 124/12, propagation 531/11.
`-t` raises the named release's pin to 990 for candidate selection, so the
`-dev` package is taken from the release its runtime already came from and
the exact-version dependency is met by the version that is installed. The
dozen-or-so packages that move are the `-dev` halves of runtimes the target
chose to take from backports before this engine ran; nothing installed is
downgraded and nothing is replaced.

**Rule.** When apt refuses the transaction because an installed package
would have to be downgraded:

1. The engine reads **which** package from apt's own words (the `is
   selected as a downgrade` line) and **where it is installed from** with
   `apt-cache policy` — the archive on the `***` row of the version table.
2. If every such package is installed from **one** release, the plan is
   simulated again with `--target-release` naming that release. If apt
   accepts it, the apt step runs with that flag, and the plan the operator
   reads lists **every package that will be taken from that release and
   from nowhere else** under a heading that says why.
3. Otherwise — no downgrade line to read, more than one release, or apt
   still refusing — the plan is refused with apt's text and the simulate
   command that reproduces it (D-016). The engine does not try a second
   release, does not try releases the culprit is not installed from, and
   does not guess.

**What was rejected.**

- `-o APT::Solver::Strict-Pinning=false` also resolves the transaction —
  by **downgrading** `libcurl4t64` to main's 8.14. That satisfies the
  `-dev` package by changing what the target installed, which is D-022's
  forbidden shape: a distribution's choice, replaced silently.
- A narrow `libcurl4-openssl-dev/parrot-backports` pin instead of `-t`.
  Tried; the chain moves. Pinning the `-dev` package to backports made its
  own dependency the next exact-version mismatch, and the fix iterates
  through the dependency graph one refusal at a time — the "fix one, re-run,
  meet the next" loop D-016 exists to end.
- Declaring the backports release in the catalog. A manifest saying
  "on Parrot, take `libcurl4-openssl-dev` from backports" would freeze one
  evening's measurement of one machine's package state into data that is
  supposed to describe software. The capability-matrix note already records
  why `when:` selectors are not used for what apt can answer at plan time;
  this is the same argument.

**The general check this produced.** Until this measurement the engine
asked `apt-get install --simulate` only when a vendor `.deb` in the plan
declared a conflict. It now asks it **once, for every transaction with
outstanding apt work**, and refuses at plan time on any answer apt gives —
`apt-cache policy` proves that each package exists, not that the set of
them installs together. Five profiles reached the apt step and died there
with a plan that had said they would install; that is the gap D-016 was
written to close, and it was open because nothing had measured a target
whose baseline installs from two releases.

**What this does not decide.** Whether a target's *own* configuration is
sensible — Parrot's backports pin is Parrot's decision and this engine
neither judges nor changes it. And whether a release-specific plan should
be recorded in the transaction log beyond the argv it already carries; the
`--target-release` flag is in the printed and logged command, which is the
disclosure D-031 asks for.

## D-039 — A profile member the target does not offer is deferred by name and the rest of the profile installs; a member the operator named, an engine gap, or a manifest defect still refuses the transaction

**Date:** 2026-09-03. **Status:** accepted; resolves Q-017.
**Depends on:** D-016 (refuse at plan time, never partway), D-035 (a
missing value defers one file, never the transaction), D-037 (Node only from
the distribution), D-031 (verify the effect, not the exit status).
**Amends:** D-016, which held that a transaction resolves whole or not at
all. It still does, for everything the operator asked for by name. The
exception is drawn around one thing: a *profile* member that the *target*
does not offer.

**What was measured.** The full-catalog campaigns on Ubuntu 24.04 and 26.04
(`docs/reference/vm-campaign-ubuntu.md`, 2026-09-02): every unit planned
and installed by name, and then **five of fifteen profiles refused whole on
24.04, two on 26.04**, each over members refused for a reason true of the
target — `listening` withheld nineteen installable units because the 24.04
archive carries neither `readsb`, `rtl-ais`, `satdump` nor
`mlat-client-adsbfi`; `propagation` withheld everything because Node 18.19
is below openhamclock's 20.19 floor and 24.04 carries no `voacapl`. The
operator's remedy was to install the nineteen by name, which is the
fix-one-re-run loop D-016 exists to end, arriving from the other side.

**The rule.** A package that reached the plan only through a profile, or as
a catalog dependency of one, is **deferred** rather than refused when the
reason is one of exactly three, each a fact about the target:

1. the catalog declares no install block matching this distro, version and
   architecture (D-002's selector, honestly negative);
2. apt on this release has no candidate for **the unit's own packages** —
   the `packages:` of its apt block, and only those;
3. the distribution's `nodejs` is absent or below the manifest's floor
   (D-037).

A deferred member's catalog dependents defer with it, each naming the
dependency it lost. Deferrals are printed under *Will NOT happen*, written
to the transaction log (`transaction_begin` version 2, `deferred`), and
reported by `hammunition status` for as long as that transaction is the most
recent one.

**What still refuses, by name.** Everything that is not one of those three:

- **A name the operator typed.** `hammunition install satdump` on 24.04 is
  a request to see the refusal, and it sees it in full. A unit named both
  directly and through a profile is a named request.
- **An engine gap.** When this was written, `code` and `codium` were
  refused on every target because the engine had no `apt_repos` backend,
  not because any archive lacked them; deferring them would have made the
  missing backend invisible, and `workstation` refused whole until that
  backend existed — the test Q-017 set for the classification. D-040 built
  the backend the same day and moved both editors to their own opt-in
  `editors` profile; the classification stands for the next gap.
- **A missing `depends` or `build_depends`.** Those are the manifest's, not
  the target's: D-016 names four AHRL dependency lines that went stale
  exactly this way, and a deferral that swallowed them would hide the defect
  the check was written to find.
- **A retired or broken status**, a declined consent gate (D-021), a
  verification failure (D-018), a declared package conflict (D-022), and an
  apt simulation that cannot resolve (D-038). None is a fact about what the
  archive offers.
- **A profile whose every member is deferred.** Installing nothing and
  reporting success is the shape D-031 exists to catch; it refuses naming
  the profile and each member's reason.

**Why the line is here and not wider.** Q-017's three options were: defer
(this), fix each gap in the catalog with `when:` selectors, or a
`--defer-unavailable` flag. The selectors would freeze one evening's
`apt-cache policy` into data meant to describe software, and would still
produce the same partial install, made silently in the catalog instead of
reported by the engine. The flag is `--yes` for consent gates over again:
the option everyone passes, at which point it is the default with a worse
name (D-021). What makes deferral safe is not the mechanism but the
classification, so the classification is the decision.

**Rejected while building it:** deferring on any no-candidate result. A
unit's `depends` line naming a package the archive lacks is indistinguishable
from its own package being absent unless the plan checks which list the
name came from — so it checks, and defers only when every missing name is
in the unit's own `packages:`.

---

## D-040 — A third-party apt repository is added only against a key the manifest pins by fingerprint, only when the target's own archive offers nothing, only after the operator affirms that fingerprint, and it comes out whole on uninstall

**Date:** 2026-09-03. **Status:** accepted; built the same day.
**Depends on:** D-021 (consent gates disclose capability; `--yes` cannot
satisfy one), D-022 (coexist with a distribution's choice, never displace
it silently), D-031 (verify the effect, not the exit status), D-018
(external claims tested before published), D-039 (a member the target does
not offer is deferred; an engine gap refuses).
**Resolves:** the `apt_repos` engine gap that D-039 named and the `cli.md`
refusal table listed by name.

**What was measured.** Two manifests carry an `apt_repos` block: `code`
(Microsoft, `packages.microsoft.com/repos/code`) and `codium` (VSCodium,
`download.vscodium.com/debs`). Neither publisher's package is in Debian,
Ubuntu, Kali or Mint; Parrot carries `codium` in its own archive. The
Ubuntu campaigns (`vm-campaign-ubuntu.md`) showed the cost of not having
the backend: both units refused on every target as an engine gap, and
`workstation` — seven packages that need nothing beyond the archive —
refused whole with them. The two publishers also differ in a way that
decided the design below: Microsoft serves an armored `microsoft.asc`,
VSCodium a binary `pub.gpg`.

**The rule.**

1. **The manifest pins the key.** An `apt_repos` entry names the `uri`,
   `suites`, `components`, the `key_url` the key is fetched from, and the
   **primary key fingerprint** (40 hex for v4, 64 for v6). Both URLs must
   be `https://`. The fingerprint is the pin; the URL is only where to
   look. A key whose primary fingerprint is not the pinned one is
   discarded with both values printed. A file that is not OpenPGP, has no
   public-key packet, fails its armor CRC, is truncated, or carries two
   primaries is refused by name. The check is this engine's own packet
   parser (`openpgp.py`), so it does not depend on `gpg` being installed
   and cannot be satisfied by anything `gpg` would import silently.
2. **Two files, both named for the repository, both disclosed in the
   plan.** `/etc/apt/keyrings/<name>.gpg` holds the key in **binary**
   OpenPGP form — an armored file is dearmored before the fingerprint is
   computed, so the bytes on disk are exactly the bytes that were checked,
   and a file called `.gpg` never holds text (VSCodium's is already
   binary; calling Microsoft's dearmored key `.asc` would have been a
   false claim about its contents, which is D-018 applied to a filename).
   `/etc/apt/sources.list.d/<name>.sources` is deb822 with `Signed-By:`
   naming that keyring and nothing wider, so the key is trusted for this
   repository only, never archive-wide, and a marker comment names the
   unit that wrote it. Nothing is written to `/etc/apt/trusted.gpg.d/`,
   ever.
3. **Only when the archive offers nothing** (D-022). The repository is
   added when apt has no candidate for the unit's *own* packages and
   neither file exists. A candidate in the archive means the repository is
   not added and the plan says so; on Parrot, `codium` installs from
   Parrot's archive and VSCodium's repository is never mentioned to apt. A
   missing `depends` is never a reason to add a repository — that is the
   manifest's defect, and it stays a blocker (D-039's reasoning).
4. **Someone else's file of the same name is a refusal.** Plan-time
   reads the file system, never apt: *ours* when both files hold what this
   engine would write, *foreign* when a same-named file holds anything
   else, *absent* otherwise. Foreign refuses — overwriting a source under
   our name would silently change what that machine trusts. Ours with no
   candidate points at `--refresh`, because the repository is there and
   the lists are stale.
5. **The gate is per repository and the answer is the fingerprint.**
   `HAMMUNITION_ACCEPT_APT_REPO_<NAME>` must equal the pinned fingerprint.
   A bare `1` is refused with the value it should hold; `--yes` never
   satisfies it (D-021); an interactive prompt shows the disclosure —
   URI, suites, components, fingerprint, both file paths, the unit that
   wants it — and asks. The affirmation is logged as a `consent_affirmed`
   record with profile `apt-repo:<name>` so the log says who trusted
   which key and when. Making the operator type the fingerprint is the
   point: it is the one check the engine cannot do for them, and an
   environment variable that is just `1` is `--yes` with extra steps.
6. **Order is the security property.** The key fetch is a `fetch` action
   and runs with the other fetches, before anything touches the machine.
   Then the staged source, then `install -D -m 0644` of both files as
   root, then a forced `apt-get update`, then `apt-get install --simulate`
   over the whole apt step, then the install. A repository that does not
   carry what it promised refuses before the apt step, not partway.
7. **Reversal is whole.** `uninstall` attributes both files to the
   transaction that wrote them (every successful `install -D -m` in the
   log), removes them, and refreshes apt. A same-named file this engine
   did not write is left alone.

**What this is not.** Not a general repository manager: there is no
`add-repo` verb, no PPA shorthand, no way to add a repository the catalog
does not declare. Not `apt-key` — that is deprecated and archive-wide,
which is the property this decision exists to refuse. Not a fetch of
`gpg`'s output: the fingerprint is computed here from the packets, so a
key that `gpg --import` would accept with a warning is refused with a
reason.

**Consequences.** `code` and `codium` left `workstation` for an opt-in
`editors` profile, so an operator who wants `lsusb` never sees a
repository disclosure they did not ask for. The `cli.md` refusal table
loses its `apt_repos` row. `code.yaml`'s stated keyring path was corrected
to `microsoft-vscode.gpg` — the repository's `name`, which is what the
engine writes — from `microsoft.gpg`, which was a guess written before the
backend existed.

**Measured on 2026-09-03**, on the dev VMs, with this engine at the commit
that records it:

- **Ubuntu 24.04.4, apt 2.8.3.** `install code` with no variable and no
  terminal: exit 3, nothing written. With the variable set to `1`: exit 3,
  the refusal naming the fingerprint it should hold, nothing written. With
  the variable set to the fingerprint and `--yes`: seven commands
  completed and confirmed; Microsoft's armored `microsoft.asc` was kept as
  **640 bytes** of binary v4 OpenPGP (`file` reads it as *OpenPGP Public
  Key Version 4, RSA 2048*), `apt-get update` accepted the repository
  through `Signed-By`, the simulate resolved, and `code 1.136.0-1788342447`
  installed from `packages.microsoft.com/repos/code stable/main`. A second
  `install code` planned zero commands. `uninstall code` removed the
  package, both files and refreshed apt: `apt-cache policy code` reports
  no candidate afterwards. The log holds one `consent_affirmed` per
  affirmation with `profile: apt-repo:microsoft-vscode` and the
  fingerprint in `extra`.
- **Debian 13, apt 3.0.3.** `install editors --yes` with both variables
  set: two gates, two keys — VSCodium's binary `pub.gpg` kept untouched at
  **2256 bytes** (RSA 4096) — eleven commands confirmed, `code 1.136.0`
  and `codium 1.126.04524` installed from their publishers. `uninstall
  editors` removed both packages and all four files in six commands. A
  hand-written `vscodium.sources` with different content then made
  `install codium` refuse at plan time as foreign, exit 2, nothing changed.

- **Parrot 6.x.** `install codium --yes` with `codium` removed first and
  no variable set: one command, `apt-get install --yes -- codium`,
  confirmed, from `deb.parrot.sh/parrot echo/main`; the plan carried the
  note *the archive already offers codium; the vscodium repository the
  manifest declares is not added (D-022)*, no gate was presented, no
  file was written under `/etc/apt/keyrings/` or `sources.list.d/`, and
  the log holds no `consent_affirmed`. Rule 3, measured.

---

## D-041 — A manifest declares the kernel subsystems it cannot work without; the plan reads the running kernel's module tree and refuses or defers by name, never from the capability matrix, and never by building a module

**Date:** 2026-09-04. **Status:** accepted; built the same day, awaiting
the maintainer's review on the pull request.
**Depends on:** D-018 (external claims tested before published), D-024
(carry only what a distribution packages), D-031 (verify the effect, not
the exit status), D-039 (a profile member the target lacks is deferred by
name; a typed name still refuses), the rejected-list entry *a custom kernel*.
**Amends:** D-008's description of the packet core as resting on "the
kernel AX.25 stack" — see Q-019.

**What was measured.** Linux 7.1 removed the amateur-radio networking
subsystem — `net/ax25`, `net/netrom`, `net/rose`, every driver in
`drivers/net/hamradio` and their uapi headers — in merge
`64edfa65062dc4509ba75978116b2f6d392346f5` (2026-04-24). Debian removed
`ax25-tools` from testing on 2026-09-01 (#1143282: it no longer builds
without `linux/hdlcdrv.h`), which is the archive gap the Kali campaign
reported. On 2026-09-04, on the seven machines this project has:

| Kernel | `ax25.ko` |
|---|---|
| Debian 13 6.12.107, Parrot 7.3 7.0.13, Ubuntu 24.04 6.8.0, Ubuntu 26.04 7.0.0 | module; `socket(AF_AX25)` opens after `modprobe ax25` |
| Kali 7.1.5, Pop!_OS 24.04 VM 7.1.5, Pop!_OS 22.04 laptop 7.1.1 | absent; errno 97, `modprobe: FATAL: Module ax25 not found` |

The Pop!_OS VM still has its previous 7.0.11 tree installed, with
`ax25.ko.zst` in it, beside the 7.1.5 tree without. **The kernel is a fact
about the machine, not the distribution.** The overnight campaign
(`hammunition-overnight-2026-09-04`) had filed `packet` as installing
whole on Pop!_OS; every package arrived, and `kissattach` could never have
worked. Confirming by packages is necessary and not sufficient — issue
#27's shape, one layer down.

**The rule.**

1. **The manifest says what it needs.** `requires_kernel` is a list drawn
   from a closed vocabulary (`KernelFeature`, today `ax25` only). The
   vocabulary is exactly the set the probe can find — a test asserts the
   schema's `Literal`, the probe's module map and its description map are
   the same set — so a manifest can never name a subsystem the plan cannot
   check. It is declared only where the software opens `AF_AX25` sockets
   or configures the kernel stack and has no other mode: ten units, listed
   in `docs/reference/kernel-ax25.md`. Software with a userspace mode
   (Direwolf, pat, LinBPQ, YAAC, Xastir, QtSoundModem) declares nothing
   and its `known_problems` says which of its interfaces needs the kernel
   — for pat and Xastir read from their source, not their README.
2. **The plan reads `/lib/modules/<uname -r>/`**, never `lsmod` or
   `/proc/net/ax25`: on every kernel that carries it, `ax25` is a module
   nothing loads until a root `kissattach` does, and an unloaded module is
   not a missing one. Present as `kernel/net/ax25/ax25.ko*` or in
   `modules.builtin` → the unit plans. Present tree, absent module → a
   name the operator typed **refuses**, naming the unit, the release and
   the merge; a profile member **defers** with the same reason and the
   rest installs (D-039's shape, for a fact about the machine rather than
   the target). No module tree for the running kernel at all — a container
   on the host's kernel, which is every CI target — is **disclosed as
   unchecked** and the unit plans; absence of evidence is not evidence.
3. **The remedies are the ones that exist.** A distribution kernel that
   still carries the stack, or the userspace path. The refusal never
   offers to build the module: the out-of-tree `mod-orphan` suggested
   upstream is packaged by no distribution (D-024), and a kernel module
   we compile is a custom kernel by another name.
4. **It never enters the capability matrix.** The matrix is per target;
   this is per machine, and per reboot. Writing "Kali: ✗" would be false
   on a Kali box that kept its 7.0 kernel and would hide the same truth
   about an Ubuntu 24.04 box the day its HWE kernel crosses 7.1.

**What this is not.** Not a kernel-version check — a version number is a
proxy, and the module tree is the fact. Not a check that the module is
loaded, for the reason in rule 2. Not a general hardware-capability probe;
the vocabulary grows one measured entry at a time, and `netrom`, `rose`
and the `scc` driver are not in it because no manifest yet needs one that
`ax25` does not already settle.

**Consequences.** `z8530-utils2` declares `ax25` today and Q-019 asks
whether to retire it: its `scc` driver left in the same merge and the
hardware predates PCI Express. The `packet` profile page says which
members it withholds on such a kernel and that the Direwolf–pat–APRS
station still installs. `docs/reference/kernel-ax25.md` is the record and
carries the reproduction commands.

**Measured on 2026-09-04** with this engine (commit 383cf27) through
`scripts/vm_campaign.py`, each VM restored to its clean snapshot first:

| Machine | Unit | Outcome |
|---|---|---|
| Kali 2026.3, `7.1.5+kali-amd64` | `ax25-tools` | refused at plan time, two blockers: no apt candidate, *and* the kernel blocker naming `7.1.5+kali-amd64`, merge 64edfa65, the userspace path and D-024 |
| Kali 2026.3 | `linpac` | refused at plan time on the kernel blocker alone — the package is in Kali's archive, so the archive check would have let it through |
| Kali 2026.3 | `direwolf` | installed and confirmed, 5 s |
| Debian 13, `6.12.107+deb13-amd64` | `ax25-tools` | installed and confirmed, 4 s |
| Debian 13 | `linpac` | installed and confirmed, 2 s |

The `packet` profile as a whole, dry-run on the same Kali VM: eight members
deferred (`ax25-tools`, `linpac`, `aprsdigi`, `ax25-apps`, `ax25-xtools`,
`ax25mail-utils`, `axmail`, `uronode`), 23 apt packages and the four git
builds (`ardopcf`, `linbpq`, `qtsoundmodem`, `qttermtcp`) still planned,
exit 0. That run found one defect the unit tests had not: a member the
archive had already deferred (`ax25-tools`) had its reason *replaced* by the
kernel's, and the deferral's "a release that carries it needs no change
here" was then false of Kali's archive. A reason already recorded now
stands; the typed-name refusal shows every one. The other two declaring
units, `fbb` and `z8530-utils2`, are not `packet` members.

**Installed for real on 2026-09-05** (engine 6b8c080, the fix included,
both VMs restored to their clean snapshot first, `--whole-profiles`):

| Machine | `packet` | Deferred by name | Installed and confirmed |
|---|---|---|---|
| Kali 2026.3, `7.1.5+kali-amd64` | exit 0, 39 s | eight — `ax25-tools` and `ax25-xtools` on the archive (*apt on Kali GNU/Linux Rolling has no candidate*; both build from the `ax25-tools` source Debian removed), `linpac`, `aprsdigi`, `ax25-apps`, `ax25mail-utils`, `axmail`, `uronode` on the kernel | 29 checks: 24 apt packages, the four git builds executable under `/usr/local/bin`, `dialout` membership |
| Debian 13, `6.12.107+deb13-amd64` | exit 0, 61 s | none | 40 checks, the eight above among them |

Two things the real run corrected. The dry-run paragraph above had
`ax25-xtools` deferred on the kernel; that reading came from the pre-fix
output, where the kernel had overwritten every archive reason, and the
fresh run shows the archive reason it keeps. And the harness's own report
read *`packet` installed+confirmed* for Kali with no mention of the eight
— the deferrals are in the transaction log it filed (`transaction_begin`,
version 2), not in its table. That is the D-041 problem statement in
miniature, on the tool that exists to prevent it, and is fixed separately.
The campaign reports are under `~/.local/state/hammunition-campaigns/`
and the row-level evidence is in `docs/reference/kernel-ax25.md`.

## D-014 addendum, 2026-09-06 — venv loses a user, and three install notes are corrected by the archive

The landscape survey's Parrot probe (`docs/reference/coverage-matrix.md`)
contradicted three manifests' stated reasons for not using the archive.
Each was re-measured across the seven container targets and, where a
manifest changed, the change was run on a VM the same day.

- **`nanovna-saver` is apt on every target.** The manifest hash-pinned a
  venv on the claim that *no distribution packages it*; every target does
  (Debian 13 and Parrot 7 `0.7.3-1.1`, Kali and Ubuntu 26.04 `0.7.4~pre1-1`,
  Ubuntu 24.04 and Pop `0.6.3-1`). Debian's `0.7.3-1.1` is missing its
  PySide6 dependency (Debian #1112747, fixed in `0.7.3-2`, which trixie will
  not receive): the package installs and `NanoVNASaver` dies with
  `ModuleNotFoundError: No module named 'PySide6'`. The Debian/Parrot block
  installs `python3-pyside6.qtwidgets` beside it — what `0.7.3-2`'s control
  file adds — and cannot do so as a manifest-level `depends`, because Ubuntu
  24.04's `0.6.3` is PyQt6 and its archive has no `python3-pyside6.qtwidgets`
  (the plan refused on exactly that). Engine install and Xvfb launch on
  Debian 13, Parrot 7.3 and Ubuntu 24.04. The venv block and the ARM-only
  binary block the D-031 addendum above mentions are both gone; **venv's real
  users are now `not1mm`, `supersdr` and the `radiosonde-auto-rx` REVIVE.**
- **`qlog` is apt on Parrot and Kali** (`0.52.0-1~bpo13+1` from
  echo-backports, `0.52.0-1`), the same tag it builds from git elsewhere.
  The manifest had said only Kali packages it. Engine install and launch on
  both.
- **`wsjtx-improved` stays on the vendor `.deb`, and now says why.** Parrot
  and Debian 13 offer `wsjtx-improved` `2.8.0+250501+repack-1`, Kali
  `3.1.0+260522+repack-1`; the archive package carries `Provides: wsjtx`,
  `Breaks: wsjtx`, and its `-data` breaks `wsjtx-data`. Installing it beside
  the archive's `wsjtx` is exactly the D-022 displacement — and the engine
  cannot see it: `backends/apt.py parse_simulation` reads only `Inst` lines,
  `Remv` lines are ignored, and the runner is `apt-get install --yes` with
  no `--no-remove`. An apt block here would remove `wsjtx` silently. That
  was an engine gap, filed as issue #42 and closed by the D-022 amendment of
  2026-09-07; the manifest's archive block followed (issue #24).

Same shape as D-025: each claim was true, or believed, when written, and
became decisive only when a probe read the archive against it.

---

## D-042 — EmComm Tools OS Community is the sixth inventory source: its delta is measured, its rig model is studied and reimplemented as catalog data, and none of its code is taken

**Date:** 2026-09-06. **Status:** accepted (maintainer, from the landscape
survey in `docs/reference/prior-art.md`); the inventory is built and this
record accompanies it on the pull request. The four follow-on sub-projects
named under *Consequences* are each their own pull request and are not
decided by this record beyond their order.
**Depends on:** D-001 (an inventory source is never a base), D-011
(provenance rules), D-014 (backends by measurement), D-018 (external claims
tested before published), D-024 (pin what a distribution packages), D-028
(an identifier naming a chip may not name a `/dev` node), D-029 (the
hardware role), D-033 (weigh adoption, state the position).
**Amends:** D-017. "The five-source union" becomes six. Nothing in D-017's
staging moves: ETC's software delta is a sixth stage after the five it
lists — eleven units, most of them apt — and the 1.0 scope table in
`docs/SCOPE.md` gains a row. The rig model and the offline-data layer are
approved work in the order below and are not 1.0 gates unless the
maintainer stages them.

**What was measured.** EmComm Tools OS Community (ETC), by Gaston Gonzalez
(KT7RUN, The Tech Prepper LLC), studied at commit `4ec08ce` (2026-05-02),
release 2026.04.01.R6 (6.0.0), from a clone in the gitignored
`reference/` tree. `scripts/gen_etc_inventory.py` reads every script the
installer can run and renders `docs/reference/etc-inventory.md`; the
numbers below are that page's.

- **62 units** in `scripts/`; `install.sh` runs 59, one only with
  `ET_EXPERT` set. Curated: **11 delta, 21 overlap, 9 glue, 4 data, 17
  base**. The delta is the offline-cyberdeck layer — Navit with
  `maptool`, kiwix and the zim tools, `dict`/`dictd`/GCIDE, QGIS,
  mbtileserver, mbutil — plus two packet clients (Paracon, Chattervox),
  Artemis, GPA and Paranoia Text Encryption for the AmRRON signed-traffic
  workflow. Every overlap unit resolves to a manifest the catalog already
  carries; the inventory names the 24.
- **The base is Ubuntu 22.10 (kinetic).** `update-apt.sh` repoints apt at
  `old-releases.ubuntu.com`; kinetic reached end of life on 2023-07-20.
  ETC is an ISO built with Cubic on a release that receives no security
  updates, and the 140 apt package names it installs are that release's.
- **34 units fetch from the network; none verifies what it fetched.**
  `download_with_retries` in `et-common` accepts a sha256 as its third
  argument. Sixteen scripts call it; all sixteen pass two arguments.
  Seven fetch at `latest`, `master`, `nightly` or with no version at all —
  `linbpq` and `QtTermTCP` from cantab.net's download directory,
  `YAAC.zip`, SDR++'s nightly `.deb`, ETC's own dump1090 fork at
  `master.zip`, osmocom `rtl-sdr` at the branch head (after purging and
  `rm -rf`-ing the archive's `librtlsdr` — the D-022 pattern done harder),
  and the unused `install-qttermtcp-from-source.sh`.
- **The licence is split.** `LICENSE` carries Apache-2.0 for the scripts
  and overlay (Copyright 2024 The Tech Prepper LLC) behind a separate
  non-commercial, no-modification notice for the logos and images.
- **The rig model is not the naive symlink trap.** Sixteen udev rule files
  write four role symlinks: `/dev/et-cat` (11 rules), `et-audio` (13),
  `et-gps` (4), `et-sdr` (3). Chip identifiers repeat across rigs —
  `0d8c:0012` in four files, `08bb:2901` in four, `10c4:ea70` in three —
  and the rules disambiguate by `PROGRAM="udev-tester.sh <radio>"`, which
  reads `conf/radios.d/active-radio.json`: **the operator has said which
  radio is connected, and udev trusts the operator.** Twenty-one radio
  definitions, 40 `et-*` wrappers that configure each application for the
  active radio, and `et-radio`/`et-mode` to select them. An empty
  `85-brltty.rules` shadows the system one and `brltty-udev.service` is
  masked, because brltty claims serial adapters ETC's operators use.

**The rule.**

1. **ETC is an inventory source under D-001**, credited in the README and
   listed in `docs/SCOPE.md` and `CLAUDE.md` beside the five. Its
   inventory is generated and regenerable, never typed; the generator's
   curation is tested against the clone both ways — every shipped script
   curated, every catalog name real.
2. **No code is taken.** Apache-2.0 permits it, and `prior-art.md`'s survey
   called `et-radio`/`et-mode` the best borrow available. It is the best
   *idea* available. The code is 40 bash wrappers, each of which knows
   which application it wraps and where that application keeps its
   configuration — install logic and package list intertwined, the AHRL
   architecture this project exists to replace (D-001 gave the same answer
   for 73Linux for a different reason). What is reimplemented is the
   model: a radio is data (`catalog/hardware/devices/`, a `rig` class), an
   operator's selection is station configuration (the open question the
   D-004 amendment records), and an application's rig settings are a
   templated `config_files` block on the manifest that already carries
   its install. The reimplementation is sub-project 3 below and is not
   decided here.
3. **The role symlinks are not carried.** `/dev/et-cat` on `10c4:ea70` is a
   CP2105 claim, and the same identifier is a Digirig DR-891, an FTX-1 and
   an FT-991A in ETC's own rules (`08bb:2901` is four Icoms). ETC's answer — trust the operator's
   selection — is a real answer, and it is one radio at a time by
   construction. D-028's answer is the by-id path systemd already
   provides, plus permissions, plus a label only where the evidence
   supports one. The operator-selection idea survives in the station
   configuration, where it can name a `/dev/serial/by-id/` path without a
   symlink that lies when a second radio is plugged in.
4. **The delta is dispositioned one unit at a time**, not carried as a
   set, and every unit that arrives arrives pinned and verified (the
   security requirements are unchanged by the source having none). GPA is
   the first that cannot arrive by apt: Debian 13 offers no `gpa`
   candidate (measured 2026-09-06 on the campaign VM), so it is a tarball
   build or nothing. `mbutil` needs python2, which left Debian with
   bullseye; its disposition is not CARRY as it stands.
5. **The offline-data layer is a category of its own.** Maps, Wikipedia
   ZIMs and reference PDFs are not packages; they are large, versioned
   downloads with their own licences (Geofabrik ODbL, Wikimedia CC BY-SA)
   that belong in `/etc/skel` for ETC because ETC ships an image. What
   they are here — a `data` backend, a profile, or documentation that
   names the sources — is sub-project 5.

**Why the source is worth a decision.** ETC is the only project in the
landscape that treats *the rig* as the thing being configured rather than
the application, and the only one with an offline-data story. Both are the
questions this project's hardware role (D-029) and station configuration
(D-035) are circling, answered by someone who has shipped five recorded releases of
an answer. Reading it cost a clone and a parser; not reading it would have
meant rediscovering, in the field, that brltty claims a MicroFox-50.

**Consequences.** Five sub-projects, in order, one pull request each:

1. *This record and the inventory* — `gen_etc_inventory.py`,
   `etc-inventory.md`, the SCOPE row, the README credit, the `CLAUDE.md`
   source section, the dispositions section.
2. *brltty* — measure first whether any of the seven targets ships a
   brltty rule that claims a catalogued identifier, then decide whether a
   `file_shadow` system modification (an empty rule file in
   `/etc/udev/rules.d/` masking `/lib/udev/rules.d/`'s) is the right
   shape or whether the existing `distribution_disabled` basis covers it.
   **Done 2026-09-12, D-047:** neither; measured on all seven targets in
   `docs/reference/brltty-inventory.md`.
3. *Rig plug-and-play* — a `rig` hardware class, the FT-991A first because
   it is owned and on the bench, station configuration carrying the
   operator's selection.
4. *The software delta* — Paracon, Chattervox, Artemis, GPA and the
   `et-*` ideas as `config_files`, each dispositioned in
   `dispositions.md` with its licence and liveness re-verified (D-018,
   D-032: Chattervox's last tag is 2019-03 and its last push 2020-01).
   **Software done 2026-09-12, D-048:** three manifests, two retirements,
   Chattervox left to the maintainer with its test results. The `et-*`
   config ideas wait on station config and the rig class (sub-project 3).
5. *The offline-data layer.*

`docs/reference/prior-art.md`'s recommendation 4 ("lift `et-radio`
under Apache-2.0") is superseded by rule 2: same finding, different
conclusion, and this record says why.

## D-043 — An installed tree belongs to the operator the run is on behalf of, by an explicit step the log shows; never by what `cp -a` happens to preserve

**Date:** 2026-09-07. **Status:** accepted (maintainer, issue #38, option 1
of the two offered there). **Depends on:** D-018 (the claim was measured
before this record was written), D-031 (verify the effect, not the exit
status), CLAUDE.md's privilege rule (drop to user where possible).
**Amends:** nothing. It records what the engine already did and makes the
engine say so.

**What was measured.** On the Debian 13 guest, 2026-09-05, after
`hammunition install yaac` (binary, `install_tree: true`),
`radiosonde-auto-rx` (venv payload) and `mshv` (source,
`install_tree: true`):

```
root:root             755 /usr/local/share/hammunition
chiefgyk3d:chiefgyk3d 775 /usr/local/share/hammunition/yaac
drwxrwxr-x chiefgyk3d     /usr/local/share/hammunition/mshv
drwxrwxr-x chiefgyk3d     /usr/local/share/hammunition/radiosonde-auto-rx
```

The transaction log explained it: `["cp", "-aT", "<build>/src",
"/usr/local/share/hammunition/yaac"]` with `requires_root: true`. `-a`
preserves ownership, the build tree is unpacked by the operator, and root
copying it keeps the operator as owner. A `make install` under the same
prefix produces root-owned files. So tree units and binary units differed,
nobody had chosen it, and nothing in the docstring, this record,
`DESIGN.md` or `transaction-log.md` said trees were meant to be anyone's.
PR #35 originally claimed the tree was root-owned and was corrected after
this measurement (D-018).

Two units run *because* of the accident. MSHV reads settings, resources and
logs from directories beside its executable (`source-build-gaps.md` #6);
`radiosonde-auto-rx` writes `log/` under its working directory. A
root-owned tree would break both launchers on their first write.

Measured again on 2026-09-07, on the same guest, for this record:

- `sudo cp -aT --no-preserve=ownership <build>/src /tmp/np` gives
  `root:root` throughout; `sudo cp -aT` alone gives `chiefgyk3d:chiefgyk3d`
  throughout. The flag is what removes the accident.
- `sudo chown -R -h user: <tree>` changes the tree, its files and its own
  symlinks; a symlink inside the tree pointing at a root-owned file or
  directory outside it leaves the target root-owned. Without `-h`,
  `chown -R` also left targets alone, but `-h` is the documented guarantee
  and the one the command carries.
- With this change, `hammunition install yaac` on the guest: the plan
  prints `sudo chown -R -h -- chiefgyk3d: /usr/local/share/hammunition/yaac`
  under a description that says why; the run completes 10 of 10 commands
  confirmed; `/usr/local/share/hammunition` stays `root:root 755`; the tree
  is `chiefgyk3d:chiefgyk3d 775` and **0 of 526** entries under it are owned
  by anyone else; `hammunition uninstall yaac` removes it.

**The rule.**

1. **A tree installed under a privileged prefix is handed to the operator
   the run is on behalf of** — `--user`, else `$SUDO_USER`, else `$USER`,
   the same resolution that owns the transaction log, the artifact cache
   and the build tree. It is consistent with `paths.py`'s owner-aware
   directories and with "drop to user where possible", and it is what two
   shipped units need.
2. **The hand-over is its own step.** `tree_install_commands` copies with
   `cp -aT --no-preserve=ownership` and then plans
   `chown -R -h -- <operator>: <tree>` as a fourth, root-requiring command
   with a description saying who runs the software and why the tree is
   theirs. The plan prints it, `--dry-run` shows it, the transaction log
   records it. Ownership is never again a property of who unpacked the
   build.
3. **`-h` is not optional.** A tree may carry symlinks; `-h` changes the
   link and never follows it, so a link pointing outside the tree cannot
   hand root's files to the operator.
4. **Without an operator, root keeps the tree.** A run with nobody to hand
   the tree to (no `--user`, no `$SUDO_USER`, no `$USER`) plans no chown and
   gets what `--no-preserve=ownership` under root produces. A prefix that
   needs no root is written as the operator already and plans no chown
   either.
5. **The parent stays root's.** `/usr/local/share/hammunition` is created
   by `install -d` under root and is not chowned; only the unit's own tree
   is. An operator can replace the contents of their tree, not add or
   remove trees.
6. **Every tree unit discloses it.** `scripts/gen_package_reference.py`
   renders an *installed tree* bullet under "What it changes on your
   machine" for any manifest whose block carries a `tree_marker` — the
   schema makes that field mandatory exactly when a tree is installed, so
   the generator cannot miss one and nobody types it by hand. The bullet
   names the path, the hand-over, the reason, the shared-machine
   consequence, that the tree is replaced whole on every install, and the
   undo. `tests/test_docs_generated.py` asserts it for all five units:
   `yaac`, `mshv`, `js8spotter`, `radiosonde-auto-rx`, `supersdr`.
7. **`uninstall` has nothing new to undo.** The chown is a property of a
   tree the existing `rm -rf` step removes; the log records it for the
   reader, not for rollback.

**What this admits.** A launcher under `/usr/local` executes code the
installing user can modify. On a single-operator workstation that is one
trust domain; on a shared machine it is not, and the generated page says
so before anyone installs. An application's own updater can also rewrite
the tree (YAAC's *Help > Check for Updates*), after which the transaction
log describes a tree that no longer exists, and the next install of the
manifest replaces it whole — settings MSHV kept beside its executable
included. Both are consequences of the design that made these units run at
all, and this record's job is to have them written down rather than
discovered. Option 2 in the issue — root-owned trees with each
beside-the-executable writer relaunched from an operator-owned copy or an
XDG state directory — costs a manifest field and per-unit work for at
least four units, and is the shape to reach for if a shared-machine
deployment ever becomes a target. It is not one now.

**Consequences.** `tree_install_commands` takes `owner`; `SourceBackend`,
`GitBackend`, `BinaryBackend` and `VenvBackend` carry it and
`cmd_install` passes the operator it already resolves. Eight tests cover
the step, its absence, and all four backends; `docs/packages/` is
regenerated; `source-build-gaps.md` #6 records the closure. Issue #38 is
closed by this record.

## D-044 — `install` refreshes the apt lists by default, when the transaction has apt work; `--no-refresh` is the opt-out

**Date:** 2026-09-10. **Status:** accepted (maintainer, Q-018, option A as
recommended). **Depends on:** D-016 (the plan resolves before anything runs),
D-038 (one automatic retry of the *plan* is the precedent; a retry of a
*command* the dry run never printed is not), D-010 (install-once-and-rot is
the pattern to refuse, at every scale). **Amends:** nothing. `--refresh`
existed; this makes it the default.

**What was measured.** On the Parrot whole-profile campaign of 2026-09-03
(`docs/reference/vm-campaign-profiles.md`), the guest's `clean-baseline`
was four days old. Its lists named `glib2.0 2.84.4-3~deb13u3`; the pool
had moved to the next revision; and six of fifteen profiles — `digital-modes`,
`electronics`, `listening`, `logging`, `packet`, `propagation` — passed
the plan and died four commands in with `404 Not Found` on the pool. The
catalog was right and the machine was unchanged, because apt fetches every
archive before it unpacks any. Four days is an ordinary age for an
operator's lists. AHRL and 73Linux both run `apt update` unconditionally
before anything else, which is why neither has ever reported this failure.

Whether the lists are stale is **not measurable on Debian**: list files
carry the archive's own `Last-Modified` as their mtime, an `apt-get update`
that finds nothing changed touches nothing, and the
`/var/lib/apt/periodic/update-success-stamp` that Ubuntu writes comes from
a conf.d snippet Debian does not ship. So "refresh when old" (Q-018 option
B) was rejected on the evidence, and "retry on 404" (option C) was rejected
because it would run a command `--dry-run` never printed.

**Decision.**

1. **The refresh is the default.** `hammunition install` puts `apt-get
   update` at the head of the transaction. It is disclosed in the plan
   like every other command, so `--dry-run` shows it and the real run
   cannot differ.
2. **Only when apt will be asked to resolve something.** The update runs
   when the plan has an apt step or a vendor `.deb` (whose dependencies apt
   resolves from the lists). A re-run with everything already installed
   stays a no-op, and a source-only plan on a station with no uplink never
   opens with a network command. A just-added third-party repository
   (D-040) always gets the update, whatever the flag says — apt has no
   index for it until one runs.
3. **`--no-refresh` turns it off.** For a local mirror, or a field station
   with no uplink that knows its lists are current. `--refresh` still
   parses, so every documented example from before this record still runs.
4. **Empty lists under `--no-refresh` still refuse**, and the blocker
   names the flag to drop rather than one to add. Without the flag, empty
   lists are a sequencing fact: the plan says the candidate check cannot
   be done before the update, and proceeds.

**What this does not do.** The plan's candidate check still resolves
against the lists as they are when the plan is built; the refresh runs
after the plan is shown and confirmed. A package the fresh lists would
newly offer is still refused at plan time, and one they would newly lack
still fails at the fetch, one step later, with the stale-lists diagnosis
that already exists. Re-planning against the fresh lists — a second,
better plan, disclosed as such — is the follow-on Q-018 named, and it is
worth doing; it is not this record. The stale-lists diagnosis keeps the
two cases it can still reach: a `--no-refresh` run, and a mirror that
moved between the run's own update and the fetch.

**Consequences.** `--refresh` became `argparse.BooleanOptionalAction`
defaulting to true; `commands_for` emits the update only when
`apt_to_install` or a `.deb` is present, or a repository is added; the
empty-lists blocker and note, the stale-lists diagnosis and the
already-configured-repository remedy say what is now true; five tests
cover the default, the opt-out, the no-apt-work skip, and both empty-lists
paths through `main()`. `docs/reference/cli.md` documents `--no-refresh`
and the step order. Q-018 is closed by this record.
## D-045 — The packet core is userspace-primary; `z8530-utils2` is retired on tested evidence; the out-of-tree AX.25 module is measured, named, and not built until a distribution packages it

**Date:** 2026-09-10. **Status:** accepted (maintainer, Q-019: both
recommendations taken, with the module question asked and answered).
**Depends on:** D-041 (the plan reads the running kernel; never a module we
build), D-024 (carry what a distribution packages), D-018 (external claims
tested before published), D-032 (liveness is the head commit, never
`updated_at`), `PARITY-POLICY.md` (every unit gets a verdict we tested).
**Amends:** D-008 (the packet-core statement; amendment recorded there).

**What was measured.** Two things Q-019 rested on and one it did not ask.

1. `z8530-utils2` configures the `scc` driver for Z8530 HDLC cards. The
   driver left the kernel in the same merge as `net/ax25`
   (`64edfa65`, 2026-04-24; `git show --stat` lists
   `drivers/net/hamradio/scc.c`), the cards are ISA and early PCI, and the
   manifest already called both \"museum conditions\". Seven machines' module
   trees were read on 2026-09-04 (`docs/reference/kernel-ax25.md`). That is
   a verdict tested by us, not an AHRL comment inherited.
2. On every kernel this project has that is 7.1 or newer, the userspace
   packet path — Direwolf or QtSoundModem as the modem; pat, LinBPQ, YAAC
   and Xastir over KISS or AGW — installs and is the whole station. The
   `packet` profile was installed whole on Kali 7.1.5 and Debian 13 6.12 on
   2026-09-05 with that result (D-041's table). D-008 and the profile prose
   still described the core as the kernel stack fed by Direwolf.
3. The maintainer asked whether the kernel stack can be added back as a
   module. **It can, and it was measured on 2026-09-10** rather than
   assumed either way. The netdev maintainer who removed the subsystem
   publishes it as an out-of-tree tree, `linux-netdev/mod-orphan`, created
   2026-04-20: one `Kbuild` covering `net/ax25`, `net/netrom`, `net/rose`,
   `drivers/net/hamradio` and the merge's other orphans; `make` against
   the running kernel's headers with a force-included compatibility header;
   sources keep their kernel SPDX headers (GPL-2.0-or-later on `af_ax25.c`);
   **no tags, no releases, no README, no top-level licence file**; head
   commit 2026-06-16, last AX.25-family change 2026-06-01 (two ROSE fixes,
   Bernard Pidoux); **packaged by no distribution** — not Debian, not
   Ubuntu, not the AUR, on that date. **Built here, not loaded:** against
   the maintainer's laptop's 7.1.1 headers, `ax25.ko`, `netrom.ko` and all
   ten `drivers/net/hamradio` modules — `mkiss`, `6pack`, `bpqether`,
   `scc` among them — compile and link with a matching `vermagic`; the
   whole tree's `make` fails, because `net/rose` calls a kernel function
   whose signature changed and `net/atm` needs a header 7.1 no longer
   ships. Nothing was `insmod`ed and no socket was opened; the measurement
   is that the code compiles, not that it works.

**Decision.**

1. **`z8530-utils2` is retired**, `retire_reason: world_changed`,
   `status_verdict: tested`, with the merge as the evidence. The manifest
   stays in the catalog so an operator who looks finds the reason (D-005's
   shape, as `noaa-apt`); a 6.12 machine with an ISA slot can still install
   it by hand, and the manifest says so. That `scc.ko` compiles out of tree
   (point 3) does not move this: the driver is packaged by nobody and the
   cards have no modern host.
2. **D-008 is amended: the packet core is userspace-primary.** The kernel
   stack is the fuller station where the kernel carries it, planned or
   deferred by name per D-041, and a bonus rather than the foundation. The
   getting-started packet guide, when written, teaches Direwolf-to-pat first
   and `kissattach` second.
3. **The out-of-tree module is noted, not carried.** D-041's \"never a
   module we build\" stands, for three reasons that survive the module
   existing: a kernel module is the one artefact this project has said it
   will never build, and building one that has to be rebuilt for every
   kernel the machine boots means a DKMS wrapper that would be *our*
   packaging of code nobody else packages — precisely what D-024 refuses,
   and the tree's own `make` already fails on 7.1.1 without a `Kbuild` we
   would have to edit, which is the first patch of a fork;
   the code's own maintainers removed it for lack of maintenance, and a
   tree with no tags and no releases offers nothing to pin (D-024's review
   signal is absent by construction); and `ax25-tools` is leaving the
   archives regardless (#1143282), so the module would restore the sockets
   and not the tools that use them. **The condition that reopens this** is
   a distribution packaging the module — a `-dkms` package in Debian is the
   obvious shape. That is the signal D-024 asks for, and the day it exists
   the `requires_kernel` refusal gains a third remedy and this record is
   amended. Nobody watches GitHub for it; `kernel-ax25.md` says where to
   look.

**Consequences.** `z8530-utils2.yaml` carries the retired status block;
`catalog/profiles/packet.yaml` describes the station userspace-first;
`docs/reference/kernel-ax25.md` carries the module measurement and the
reopening condition; generated pages regenerated. Q-019 is closed by this
record. The remaining kernel-side question — the `scc`/`netrom`/`rose`
vocabulary — stays closed by D-041 until a manifest needs an entry `ax25`
does not settle.

## D-046 — Post-1.0: listening before repeaters; decoders in `listening`, recorders in `rf-security`; Pi-Star's binary set is a D-024 pin source; ASL3's repository is the D-040 case with no gate beyond the fingerprint

**Date:** 2026-09-12. **Status:** accepted (maintainer, Q-020, all four
calls as recommended). **Depends on:** D-003 (flat tags with overlap),
D-021 (disclose, never adjudicate), D-024 (pin what a distribution
packages), D-034 (the line is transmit, not topic), D-035 (a missing
station value defers one file), D-040 (third-party archives on the
fingerprint alone). **Amends:** nothing; it fills in the four blanks
`docs/SCOPE.md` stages 9 and 10 left open on 2026-09-07.

**What was measured** is in SCOPE.md's post-1.0 section and is not
repeated here: seventeen names across seven targets, two in any archive,
both already carried; OP25's live fork, Trunk Recorder, SDRTrunk and
DSD-FME's liveness and licences; the G4KLX suite untagged and unpackaged;
Pi-Star V4.3.7 (2026-05-01) as the one maintained thing that builds and
ships it; AllStarLink ASL3 only from its own repository.

**Decision.**

1. **Track A before Track B.** Trunked and digital-voice listening — OP25,
   Trunk Recorder, SDRTrunk, DSD-FME — is four units on backends 1.0
   ships, in profiles that exist, with no station-config dependency and
   nothing that transmits. Track B waits on station config (SvxLink), a
   D-040 manifest (ASL3) and a pin source plus hardware (MMDVM). The one
   piece of B that rides for free is SvxLink's `config_files` block, taken
   the day station config exists rather than when B begins.
2. **The decoders go in `listening`; OP25 and Trunk Recorder in
   `rf-security`.** An operator with one dongle who wants to hear the local
   P25 system belongs in the on-ramp profile; whole-network recording of
   trunked systems is the posture `rf-security` already frames. D-003's
   flat tags allow a unit in both where it fits both. SDRTrunk and Trunk
   Recorder do the same job on different stacks, and that overlap is one
   `overlaps.md` row, written by whichever manifest lands first.
3. **Pi-Star's shipped binary set counts as "a distribution packages it"
   for D-024.** The G4KLX suite pins the commits the current Pi-Star
   release ships. Pi-Star chose those commits, built them, and shipped
   them to the largest hotspot install base, which is the review signal
   D-024 asks for; its successor is CI-built and accepts pull requests, so
   the choice is reviewable. Reading the commits out of an image is a
   measurement to script and record, not a field to cite, and the script
   is part of the first G4KLX manifest. Pi-Star's ARM builds prove the
   commits, not our x86 builds; those are measured on our targets as every
   source unit is.
4. **ASL3's own apt repository is the D-040 case**, and the landscape
   survey's "never add a third-party APT archive" is read through D-040 as
   CLAUDE.md already reads it: the distribution offers nothing, the
   manifest pins the signing-key fingerprint, the archive is added only on
   the operator typing that fingerprint, never on `--yes`, and both files
   come out on uninstall. **No consent gate beyond the fingerprint.** A
   node on the amateur bands is licensed operation, the same thing `flrig`
   keying a transceiver is; the profile prose discloses coordination and
   unattended-station conditions (D-021's half) and adjudicates nothing.
   This is the second manifest family after `code`/`codium` to rely on the
   D-040 reading and the first with transmit behind it, and that fact is
   what this record exists to have written down.

**Consequences.** SCOPE.md stages 9 and 10 carry the rulings in place. No
manifest changes yet: everything here is post-1.0, and the first Track A
manifest is where the work starts. Q-020 is closed by this record, and no
question is open in `docs/QUESTIONS.md` on this date.

## D-047 — brltty is measured per target, not purged or shadowed; the sweep reads every syntax a rule can name a pair in

**Date:** 2026-09-12. **Status:** accepted; built the same day, awaiting
the maintainer's review on the pull request. **Depends on:** D-042
(sub-project 2 asked this), D-028 (an identifier naming a chip may not name
a device), D-029 (the hardware role includes honest documentation of what
nothing solves), D-031 (verify the effect, not the exit status), D-022
(coexist, disclose, never remove silently), CLAUDE.md's rejected-list entry
*anything that reconfigures the user's OS wholesale*. **Amends:** the
udev-inventory page's "nothing is filtered" claim, which was true of
packages and false of syntax.

**What was measured.** `scripts/run-brltty-probe.sh` downloaded each
target's `brltty` (never installed it) and read what it ships;
`scripts/gen_brltty_inventory.py` renders `docs/reference/brltty-inventory.md`
from the probes, with the catalog intersection computed live.

1. **Four of seven targets ship no brltty udev rules at all.** Debian 13
   (6.7-3.1+deb13u3, amd64 and arm64), Parrot 7.3 (the same package) and
   Kali (6.9.1+repack-1) put only *examples* under `/usr/share/doc/brltty/`.
   Nothing in those archives Depends on or Recommends brltty; `orca` and
   `speechd-el` Suggest it. There is nothing to shadow and nothing arrives
   by default.
2. **The Ubuntu family ships `85-brltty.rules` and installs brltty by
   default** — Recommends of `ubuntu-desktop`, `ubuntu-desktop-minimal`,
   `xubuntu-desktop` and six more desktops (Mint's own `mint-meta-*`
   metapackages do not name it; the rules arrive there through Ubuntu's).
   Ubuntu commented out the generic-bridge lines in 2022 (bug #1958224) and
   the file says so beside each one.
3. **What is still enabled and in our catalog.** On Ubuntu 24.04 and Mint
   22.3 (brltty 6.6-4ubuntu5): `0403:6001` only when the USB manufacturer
   string is `Hedo Reha Technik GmbH` or `Tivomatic Oy` — an FTDI rig
   cable's string is `FTDI` and never matches — and **`1a86:7523`, the
   CH340, only behind a `1a40:0101` parent hub.** That hub is the Terminus
   FE 1.1 inside the Zoomax display, and also inside a great many cheap
   four-port hubs. A CH340 cable through such a hub is claimed. On Ubuntu
   26.04 (6.7-1ubuntu6) the CH340 line is commented out too, and the two
   vendor-string FTDI lines are all that remain.
4. **The maintainer's own laptop** (Pop!_OS 22.04, brltty 6.4-4ubuntu3,
   not a target) carries the unqualified `ENV{PRODUCT}=="1a86/7523/*"`
   line, enabled: every CH340 on that machine is claimed, hub or no hub.
   Its `brltty-udev.service` is a static unit started by the rule.
5. **The udev sweep could not have seen any of this.** brltty writes
   `ENV{PRODUCT}=="403/de58/*"`; the sweep's parser read only
   `ATTRS{idVendor}`, and brltty had zero rows in an inventory that said
   nothing was filtered. Reading the two other syntaxes added 25 rows from
   six Debian 13 packages (tlp-rdw, udisks2, libhackrf0's rad1o lines among
   them), none touching a catalogued identifier — and one precedence bug
   caught by its own test: brltty's CH340 line names the device by
   `PRODUCT` and its *hub* by `ATTRS`, and a parser that tried `ATTRS`
   first filed the hub as a braille display.

**Decision.**

1. **No `file_shadow`, no `package_purge`, no engine change.** ETC's empty
   `85-brltty.rules` and AHRL's unconditional purge each remove a blind
   operator's braille support from every machine to fix a collision that
   exists on two of seven targets, for one chip, behind one hub. On the four
   Debian-family targets there is no file to shadow. A project that augments
   an existing system does not delete accessibility software as a side
   effect of installing a rig-control program.
2. **`distribution_disabled` does not cover it either.** That basis says an
   identifier does not name a device, citing a rule a distribution
   commented out. The colliding rule is *enabled*; the basis is the wrong
   shape for it, and D-028 already carries `1a86:7523` as
   `kernel_generic_driver`.
3. **The answer is the measurement and the troubleshooting entry.**
   `brltty-inventory.md` is generated and `--check`ed like every other
   reference page, so the day Ubuntu changes the file the page goes stale by
   name. `docs/troubleshooting/running.md` tells an operator whose CH340
   vanished on Ubuntu 24.04 or Mint what happened and the two fixes that
   exist — unplug from the hub, or remove `brltty` *if no one on the
   machine needs it*, which is the operator's call and never the engine's.
   The `badgelife` class entry for `1a86:7523` names brltty among the
   claimants.
4. **The sweep parser is a module with a test.** `scripts/udev_rule_pairs.py`
   reads `ATTRS{idVendor}`, `ENV{PRODUCT}` and `ENV{ID_VENDOR_ID}`, device
   syntaxes before parent-walking ones, mounted into the sweep container by
   the runner. Its tests carry the brltty lines that proved each case and
   the falsification that the old regex returns nothing for them.

**What would change this.** A target whose *default* brltty carries an
unqualified generic-bridge line again — the 2022 state — is the case for
carrying a targeted rule of our own that unsets what brltty's set for the
catalogued device, file-ordered after `85-brltty.rules`; a `udev_rule`
modification the schema already has, never a shadow of the whole file. No
target does today, and the page will say when one does.

**Consequences.** `scripts/brltty-probe.sh`, `scripts/run-brltty-probe.sh`,
`scripts/gen_brltty_inventory.py` (`--check`, in the no-op test),
`docs/reference/brltty-inventory.md`, seven probe files under
`reference/probes/`; `scripts/udev_rule_pairs.py` and
`tests/test_udev_rule_pairs.py`; the Debian 13 sweep re-run and
`udev-inventory.md`, `usb-ambiguity.md`, `ambiguous-ids.yaml` and
`programmer.yaml` regenerated from it; the troubleshooting entry; the class
note. D-042 sub-project 2 is closed by this record.

## D-048 — The EmComm Tools software delta: Paracon, Artemis and GPA carried on measured routes; Artemis's vendor `.deb` refused by name; Chattervox left to the maintainer with its test results

**Date:** 2026-09-12. **Status:** accepted; built the same day, awaiting
the maintainer's review on the pull request. **Depends on:** D-042
(sub-project 4), D-018 (claims tested before published), D-024 (never
build what apt provides; own pins only when nothing packages it), D-032
(liveness is the head commit), D-037 (Node only from the distribution,
never fetched), D-045 (the packet core is userspace-primary), D-022
(coexist, never displace silently), `PARITY-POLICY.md`. **Amends:**
nothing.

**What was measured, 2026-09-12.** Every upstream re-read by API (licence,
default-branch head, releases and their assets); every artifact fetched
and hashed from the download itself; `apt-cache policy` for every apt name
the three manifests use, on all seven targets; and each unit exercised on
a Debian 13 container.

1. **Paracon** (MIT, head 2025-10-12, release 1.3.0 the same day) is one
   `.pyz` with its dependencies inside. `paracon --version` printed
   `Paracon 1.3.0` on Python 3.13.5. It speaks AGWPE to Direwolf and never
   opens an `AF_AX25` socket, so it is the packet terminal that works on a
   7.1 kernel — the reason D-045 needed one.
2. **Artemis** (GPL-3.0, head 2026-07-22, release 4.2.0) stopped shipping
   the Linux zip ETC used; 4.2.0's Linux assets are a `.deb`, an Arch
   package and an RPM. The `.deb` was fetched (190 MB) and read: its
   control file says `Package: artemis`, and **every target's archive
   already has an `artemis`** — the Sanger genome browser, at 18.2.0.
   Installing the vendor file would put this program under that name one
   version *below* the archive's, and the next `apt upgrade` would replace
   it with a genome browser. It also Depends on `libpython3.12`, which
   Debian 13, Parrot, Kali and Ubuntu 26.04 do not carry. The upstream
   tree is a plain Python package with four PyPI dependencies, so it is
   carried as a venv — the 4.2.0 source tarball as payload, requirements
   compiled with hashes by uv — and the pinned set installed and
   `import artemis` succeeded on Python 3.13.5. The window has not been
   opened from that install; the manifest says so.
3. **GPA** 0.11.1 (2026-02-12, the release that builds against gpgme 2.x)
   is in Ubuntu 24.04 and Mint at 0.10.0 and Ubuntu 26.04 at 0.11.0, and in
   no Debian-family archive. The gnupg.org tarball's detached signature
   verified against the GnuPG distribution signing key; the four `-dev`
   packages configure.ac names have candidates on all seven targets;
   configure and make exit 0 on Debian 13 and `gpa --version` prints
   0.11.1.
4. **Chattervox** (GPL-3.0 by its LICENSE file, head 2019-03-17, every
   release a prerelease): the 0.7.0 bundle runs `--help`; the source
   builds on Debian 13's Node 20 with `npm ci --ignore-scripts` and runs
   `--version`; `kiss-tnc` loads without serialport's native build.
   Whether a KISS port *opens* without that build is untested — the
   container has no TNC — and two of its dependencies are git commits
   rather than registry packages.

**Decision.**

1. **Paracon, Artemis and GPA are ADD**, with manifests, on the routes
   above. GPA takes the archive's package where one exists and the tarball
   elsewhere, so its version differs by target and the manifest says why.
   Paracon joins `packet`; Artemis joins `listening` and `rf-security`
   (D-046's split, applied: a reference is for both); GPA joins no profile
   — `workstation`'s contents were fixed at acceptance (Q-011), and which
   EMCOMM profile a PGP front end belongs to is a placement question for
   the maintainer, so it installs by name.
2. **Artemis's vendor `.deb` is refused by name**, for the two reasons
   measured, and the refusal is written into the manifest so the next
   person to find the asset does not re-derive it.
3. **mbutil and pfte are RETIRE**, `not-carried.md` carries the reasons:
   a python2 script nothing calls, and a proprietary unsigned binary the
   security requirements refuse by name.
4. **Chattervox stays NEEDS-DECISION**, and the index says so. Both
   routes to it cross a rule: the bundle is a fetched Node runtime, which
   D-037 refuses; the source is the node backend fetching two git commits
   the registry does not carry, with a native serial layer the
   `--ignore-scripts` rule will not build. It is dormant six and a half
   years with only prereleases. The recommendation is not to carry it in
   1.0; the test results are recorded so the maintainer decides from
   evidence rather than from the dormancy alone.
5. **The five offline-data units keep their ADD and stay outstanding**
   with a recorded reason each, until sub-project 5 gives them a category.

**Consequences.** `paracon.yaml`, `artemis.yaml`, `gpa.yaml`; `packet`,
`listening` and `rf-security` gain a member each; the dispositions index
gains an `EmComm Tools OS delta (11)` block and the summary table a
column (the hygiene test holds both to each other); `not-carried.md` and
`parity-coverage.md` regenerated with the two retirements and five
reasons; the apt policy sweep re-run for the new names and the capability
matrix regenerated. D-042 sub-project 4's software half is closed by this
record; the `et-*` config ideas wait on station config and sub-project 3.

## D-049 — Offline data is a catalog unit: a `data` install method whose payload is the point, disclosed by size and licence before the confirmation, selected through station config

**Date:** 2026-09-12. **Status:** accepted (maintainer, Q-021, option A as
recommended, both rules). **Depends on:** D-042 (rule 5 named the layer),
D-048 (five readers decided ADD and unwritable), D-018 (every fetch
verified), D-035 (a missing station value defers one file, never the
transaction), D-021 (disclose, never adjudicate), Q-015 decision 8
(`country_files` deferred to exactly this question). **Amends:** nothing.

**What was measured** is in Q-021: ETC's three interactive, unverified
downloads into `/etc/skel`; its own tilesets at 0.69 GB (US) and 0.52 GB
(Canada) under ODbL; Geofabrik extracts from 0.05 GB (Vermont) to 1.33 GB
(California); the English Wikipedia ZIM unmeasured from here on the day.

**Decision.**

1. **A data artifact is a catalog unit**, on the package manifest, with
   `method: data`: one or more pinned, sha256'd artifacts installed under
   `<prefix>/share/hammunition/data/<name>/`, recorded in the transaction
   log like every other artefact so `uninstall` removes them, with an
   `update` block like every other unit. The reader (`kiwix`,
   `mbtileserver`, the logger that reads cty.dat) names the data unit in
   `depends`; the data unit names nothing.
2. **Size and licence are printed in the plan, before the confirmation.**
   Each artifact declares its `size` in bytes and the unit declares its
   `licence` and a `licence_url`; `--dry-run` shows both, and the real run
   shows the same text. A 1.33 GB download on a field connection is a
   decision, and a dataset under ODbL or CC BY-SA carries obligations the
   engine states and does not adjudicate (D-021's half).
3. **The operator's selection lives in station config.** Which state,
   which country, which language: a data unit whose artifact depends on a
   station value is deferred by name when the value is missing, and its
   reader installs regardless (D-035's shape). Nothing is guessed and no
   default region is invented.
4. **Built in this order**, each step its own measurement: the schema,
   fetcher and plan disclosure, proven on `country_files` — cty.dat, about
   200 KB, the smallest and oldest case; then ETC's tileset with
   `mbtileserver`; then Navit's extract with the station selection; then
   the ZIM with `kiwix`. `dict` is apt and needs none of this.

**What this is not.** Not a mirror: every artifact is fetched from its
publisher's own URL, never redistributed. Not `/etc/skel`: the data is
installed once, system-wide, for the operator who asked. Not a backend for
software — a `.pyz` is `binary`, a venv payload is `venv`; `data` is for
files the reader opens and the engine never executes.

**Consequences.** `DataInstall` in the schema (`artifacts`, each with
`url`, `sha256`, `size`, `install_as`; `licence`, `licence_url`); a data
backend that fetches, verifies and installs; the plan's disclosure; the
docs generator's rendering; `capability_matrix.py` knows the method.
`country_files.yaml` is the proof. Q-021 is closed by this record; Q-015
decision 8's deferral ends with it.

## D-050 — The menu is shaped like Parrot's: one top menu, ordered groups, one submenu per category, and an entry for every installed unit

**Date:** 2026-09-12. **Status:** accepted (maintainer, in the field-laptop
session: "that solution for menus looks correct"). **Depends on:** D-036
(curated submenus generated from `categories`), D-003 (categories are flat
tags and stay so), D-022 (the distribution's own entries are untouched),
D-031 (a count is not evidence; the file on disk is). **Amends:** the
D-036 addendum's measured menu-spec tree, which was one level.

**What was measured.** On the field target (Dell Latitude 5430 Rugged,
Parrot Security 7.3, KDE Plasma, 2026-09-12, `docs/reference/bench-verification-5430.md`):

- The D-036 tree rendered *Ham Radio* as **27 sibling submenus** in
  alphabetical order — more than Plasma's own top level carries — with
  visible overlap (Station / Timing / Tracking; CW / Training; Contest /
  Logging; Hardware / Programmer / Electronics). The maintainer's words:
  nobody can find anything in it.
- **Parrot's own tool menu**, the thing the rest of that desktop already
  uses: one top menu (*Parrot Security*), **14 numbered groups**
  (*01 Information Gathering* … *14 AI Tools*), numbered subcategories
  under each, the order fixed by a menu-spec `<Layout>` with separators,
  a hand-curated *Most Used Tools* group at the top, and entries free to
  appear in several places. **671 entries; 670 carry a `Comment`, 572
  launch in a terminal**, 6 carry `Keywords`. Categories in its desktop
  files are the group and subcategory tags (`01-info-gathering`,
  `01-04-network-scanners`).
- Of the **32 catalog units installed** on the laptop, **25 had no menu
  entry at all** — gpsd, rigctl, the RTL-SDR tools, tcpdump. An entry is
  what the launcher's search indexes; a unit without one is unfindable by
  name or by what it does, whatever the tree looks like.
- `parrot-menu` had removed the packaged `chirp.desktop` and
  `org.wireshark.Wireshark.desktop` from an apt `DPkg::Post-Invoke` hook
  and written `parrot-chirp.desktop` / `parrot-wireshark.desktop`; the tree
  placed the dead filenames and the summary counted them (#64).

**Rule.**

1. **Two levels, in a declared order.** `catalog/categories.yaml` gains a
   `groups:` list — `order`, `name`, `title`, `summary`, `categories` —
   and the tree is *Ham Radio* → group → category submenu. Eight groups:
   Station; Digital Modes; Packet & EMCOMM; SDR & Listening; RF Security;
   Hardware & Bench; Learning; Workstation (48 / 46 / 43 / 109 / 22 / 77 /
   13 / 23 catalog units respectively, measured 2026-09-12). Every category
   belongs to **exactly one** group (`tests/test_categories.py`); the
   order is a `<Layout>`, never the alphabet. A category no group claims
   still renders, beside the groups — the vocabulary test forbids the
   state, and the renderer is not a second place that silently drops it.
   **A group is where a submenu sits, not what a package is**: manifests
   keep tagging categories (D-003), and no other reader of the vocabulary
   consults groups.
2. **An entry for every installed unit.** `hammunition menus apply`
   generates, per user, `hammunition-cli-<unit>.desktop` for each
   installed catalog unit that ships no desktop entry and declares no
   `launchers`: the unit's name, the manifest summary as `Comment`, the
   categories as `Keywords`, `Terminal=true`, the `X-Hammunition-<category>`
   markers, and the executable. **The executable is the one named like the
   unit, else the package's only one; anything else is not guessed.**
   Several and none named like the unit (`rtl-sdr`: eight tools) is
   reported under the count with the fix named — a `launchers` block in
   the manifest. A unit whose executables are all under `/usr/sbin` is a
   service, not an application, and is skipped with that reason (`gpsd`'s
   generated entry ran the daemon in a terminal before this rule existed).
   Entries from an earlier run whose unit is gone are removed; a
   launcher's `hammunition-<name>.desktop` is never touched.
3. **Placed filenames are checked on disk** (#64): an entry that exists is
   placed as shipped, one that is gone is placed by
   `parrot-<package>.desktop` when that exists, otherwise it is reported,
   never counted. `dpkg -L` is what a package shipped, not what a
   distribution's hook left.
4. **KDE gets its cache rebuilt, and its file where KDE reads.** On a
   `plasma-` or `kf5-` prefix, `kbuildsycoca6` (or 5) runs afterwards as a
   disclosed, unprivileged command, so the tree shows now. And the merged
   file goes to `applications-merged/`, **not** `plasma-applications-merged/`:
   the spec says the prefixed directory and Xfce's garcon reads it, but
   KDE's kservice ignores the prefix — measured on the field laptop the
   same day, when the first apply of this rule wrote the prefixed file,
   `kbuildsycoca6` reported only `/etc/xdg/menus/applications-merged/*`
   as found, no *Ham Radio* menu appeared, and every generated entry sat in
   Kickoff's *Lost & Found* (an entry no menu allocates). Parrot's own menu
   ships in `applications-merged` for the same reason. A copy left in a
   directory the desktop does not read is removed on the next apply.
5. **Not taken from Parrot:** a *Most Used* group. Parrot curates it by
   hand; this project has no measurement to build one from, and a
   hand-kept list is the second taxonomy D-036 refuses.

**Measured after the rule, same machine, same day.** `menus apply`: 8
groups, 27 categories, 20 placed entries (CHIRP and Wireshark by Parrot's
replacements, zero dead filenames), **12 entries generated, 12 skipped
with the reason named** (11 with several executables and none named like
the unit; `gpsd` under the sbin rule), the earlier `gpsd` entry pruned,
`kbuildsycoca6` run. `hammunition-hill` gained a `service_endpoints` +
`launchers` pair (the browser at the loopback dashboard), so the
family's own dashboard is in *Station*, *HF Propagation* and *Satellite*
rather than nowhere.

**Second round, same day (maintainer, after seeing the tree in the
launcher).** Three amendments to the rule above:

6. **The menu is called *Hammunition*, not *Ham Radio*.** It is the
   project's tree, the way Parrot's is *Parrot Security*.
7. **A group can be hidden: `menu: false`.** *Workstation* is: git, tmux,
   screen, VS Code and VSCodium are catalog units because a station needs
   them, not because they are radio software, and the maintainer did not
   want them under Hammunition. A hidden group gets no submenu, no folder,
   no generated entry, and the packaged entries of a unit tagged only there
   are left where the desktop already puts them (VS Code stays under
   *Development*). A unit tagged workstation *and* a radio category
   (wireshark, esptool, tcpdump) still shows under the radio one, and the
   hidden tag is not a keyword on its entry. Measured on the laptop: 7
   groups shown, the git, screen and tmux entries pruned, 9 generated
   entries remain.
8. **Desktop parity is per mechanism, measured where it can be.** What
   Parrot already carries was measured too: under *Pentesting → Wireless
   Attacks* it lists 71 RF entries in five submenus and 15 of those
   packages are catalog units (gqrx, GNU Radio, the RTL-SDR and HackRF
   tools, Ubertooth, inspectrum, the NFC tools, aircrack, Wireshark, CHIRP,
   GPA, gr-air-modes); its KDE root has no `HamRadio` category at all, so
   the ham side had nowhere to go. Both copies stay (D-022), the way
   Parrot lists a tool in several places.

   | Desktop | Mechanism | State |
   |---|---|---|
   | KDE Plasma (Parrot) | menu-spec merge into `applications-merged/` (KDE ignores the prefix), `kbuildsycoca6` after | **Measured on the field laptop** 2026-09-12: tree present, groups in order, Lost & Found emptied |
   | Xfce (Kali, Parrot's alternative) | menu-spec merge into `<prefix>applications-merged/` | Measured on the Kali VM for the flat tree (2026-09-02); the grouped tree and `<Layout>` are the same mechanism and **await a re-run there** |
   | GNOME (Debian 13, Ubuntu) | one app-folder per visible group, *Hammunition · <title>*, populated by the group's `X-Hammunition-*` markers plus placed entries by name; GNOME cannot nest | Code and tests written this round; **awaits the Debian 13 VM** — nothing asserted until it has run |
   | COSMIC (Pop!_OS) | unknown; its app-library groups are not menu-spec | **Unmeasured.** The Pop VM exists; nothing is claimed until it is read |

   The three VM checks run from the hypervisor host, not the field laptop.

**Consequences.** The eleven skipped units on the laptop — `rtl-sdr`,
`libhamlib-utils`, `hackrf`, `ubertooth`, `libnfc-bin`, `libfreefare-bin`,
`hcxtools`, `gpsd-tools`, `pciutils`, `usbutils` and `gpsd`'s tools — are
the next `launchers` work, one manifest each, choosing which tool a menu
entry should open. Whether every terminal entry *makes sense* to open
(`git`, `tmux`) is the same question Parrot answered yes to for 572
entries; it is revisited only with a measurement of what operators
actually open. COSMIC stays unmeasured. The GNOME app-folder is unchanged:
it cannot nest, and one folder populated by `HamRadio` is what it can do.

## D-051 — A build already installed at its pin is already installed: the effect on disk plus the log's attribution, never one without the other

**Date:** 2026-09-12. **Status:** accepted (maintainer: "focus on delivering
more features"; this was the gap that had just cost him two rebuild rounds).
**Depends on:** D-031 (the effect, not the exit status), D-004 (the
transaction log is the record), the #67 rule for vendor .debs, which this
generalises. **Amends:** the Parrot VM page's finding 4 (2026-08-29), which
queued exactly this as engine work.

**What was measured.** The field laptop's first full-catalog install
(2026-09-12) ran 21 source and git builds, then failed at paracon (#72). The
resume rebuilt all 21, then failed at a virtualenv step (#74). The second
resume rebuilt them a third time. apt units reported *already installed*
throughout; every build unit reported *will build*, because
`_plan_state`'s rule was "already installed is apt's answer and only apt's"
and the executor had no way to know a build had happened.

**Rule.** `execute.already_built()` names the units whose build steps are
skipped, and it requires both halves:

1. **The effect is present.** Every declared `binaries` entry is executable
   at `<prefix>/bin/<install_as>`; where the block installs a tree, its
   `tree_marker` exists under the tree destination. A unit declaring neither
   cannot be checked and is never decided here -- it rebuilds.
2. **The log attributes it, at this pin.** A `verify-pin` or `extract`
   action whose detail names *exactly this build directory* -- the
   backends' `layout()` puts the ref or the digest prefix in that
   directory's name, so a moved ref or a re-pinned artifact is a different
   path and does not match -- followed, in the same transaction, by a
   `transaction_end` with `verified: true` that confirmed one of this unit's
   checks. A transaction that failed after the build steps attributes
   nothing: the paracon run's 21 builds are on disk and were still rebuilt
   once more, correctly, because nothing ever verified them.

Both halves come from what already existed: the effect checks are
`verify_effects`'s own probes, and the log entries are the ones every build
already writes. No log format change; the laptop's log from before this
rule attributes builds the moment a verified transaction has covered them.

A skipped unit keeps its launcher and config steps -- those are cheap,
idempotent, and the reason a profile is re-run in the first place. The plan
line reads *already installed*, the executor plans no fetch, unpack, build
or install for it, and `verify_effects` still checks the binary at the end,
so a unit deleted by hand between plan and run is caught there.

**Not decided here.** apt has `already_installed`; a .deb has #67; venv and
node units keep pip's and npm's own cheap idempotency. A unit whose pin
moved rebuilds, and that is the point: *at its pin*, not *at some pin*.

**Measured after the rule** (to be recorded on
`docs/reference/bench-verification-5430.md` once the laptop's second
resume ends with a verified transaction): a dry run of the profiles that
carry the 21 builds should plan launcher steps only.
