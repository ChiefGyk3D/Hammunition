# Dispositions — every unit, one classification

Applies `PARITY-POLICY.md` to `ahrl-inventory.md`, the 73Linux delta, the
Skywave delta (`skywave-inventory.md`) and the DragonOS Tier-1 set
(`dragonos-tier1-inventory.md`) — all five sources now dispositioned.

**Scope:** 105 AHRL `INSTALL_*` toggles (95 executing + 9 disabled + 1 dead
code), 28 73Linux delta units, 9 Skywave delta units, and the 8 genuinely-new
of DragonOS's 24 Tier-1 units (the other 16 are CARRY cross-references to AHRL
or the Blend). **150 units, none unclassified.**

**Method:** dispositions follow the policy's bars. Where the policy already
settled a case, it is recorded here and **not re-argued**. Two clusters are
reserved to the maintainer — investigated and recommended below, not decided.
Where I could not decide, the unit is `NEEDS-DECISION` with the specific
question, not a guess.

**Verification status:** upstream-project facts (project sunset, licence,
support upstreamed) were checked and are cited. Debian/Ubuntu **package
availability was not checked** — this is a Pop!_OS workstation, not a target
distro, and `CLAUDE.md` forbids testing against the dev machine. Every claim
depending on distro package state is marked *(verify in container)*.

---

## Summary

| Disposition | AHRL | 73Linux delta | Skywave delta | DragonOS T1* | Total |
|---|---:|---:|---:|---:|---:|
| CARRY | 67 | 2 | 0 | 0 | 69 |
| SUPERSEDE | 13 | 0 | 1 | 0 | 14 |
| REVIVE | 6 | 0 | 0 | 0 | 6 |
| RETIRE | 13 | 14 | 0 | 0 | 27 |
| ADD | — | 11 | 7 | 8 | 26 |
| NEEDS-DECISION | 0 | 1 | 1 | 0 | 2 |
| Reserved to maintainer | 6 | 0 | 0 | 0 | 6 |
| **Total** | **105** | **28** | **9** | **8** | **150** |

\* **DragonOS Tier 1 is 24 units; only the 8 genuinely-new ones are counted
here.** The other 16 arrive through AHRL parity or the Debian Blend — CARRY by
cross-reference, already counted under AHRL, and listed in the Tier-1 section
above rather than double-counted.

Counts are derived from the complete index at the foot of this document, not
maintained by hand. Two overlap decisions (the FT8-family default and the
HamClock default) are recorded under NEEDS-DECISION but are not units and are
not counted.

**The headline:** one unit changed disposition because the world moved while
AHRL v27 was in the oven. **HamClock's author became a Silent Key on
2026-01-29 and the project's data feed sunset in June 2026.** AHRL v27 shipped
in May 2026 with four HamClock menu entries hardcoded to `-b hamclock.com:80`.
As of today (2026-08-25) that sunset has passed. See SUPERSEDE #1.

---

## Settled by PARITY-POLICY.md — recorded, not re-argued

| Unit | Disposition | Policy reason |
|---|---|---|
| `noaa-apt` | RETIRE | World changed — NOAA APT satellites out of service 2025-11-09. Point to SatDump. |
| `xwxapt` | RETIRE | Same, same pointer. |
| `mfc_gpl` | RETIRE | Never worked — empty stub. |
| `tt3_gpl` | RETIRE | Never worked — empty stub. |
| `ardop` | REVIVE | Upstream `pflarue/ardop` active; also in the 1.0 packet core. |
| `radiosonde_auto_rx` | REVIVE | Upstream healthy; venv backend handles what bash couldn't. |
| `ibp` | REVIVE | IBP beacons still transmit. Falls back to SUPERSEDE, never RETIRE. |
| `dream` | REVIVE-or-SUPERSEDE | May be the only DRM decoder. Check before retiring. |
| `mvoice` | REVIVE-or-SUPERSEDE | Was AHRL's only M17 path. Find the maintained successor. |
| `glfer`, `gsmc`, `owx`†, `linrad`, `qgrid` | CARRY with attention | Build only with `-Wno-*`. Record flags, add CI. |
| `dump1090` | SUPERSEDE | → `readsb` / `dump1090-fa`. |
| `cqrlog`, `xlog` | CARRY all three | QLog is the recommended default. |
| Unversioned snapshots | CARRY, pinned | Packaging fix, not a replacement. |

† `owx` appears in the policy's compiler-flag set. I am proposing it also be
SUPERSEDE'd — see SUPERSEDE #2. The two are not in conflict: if superseded, the
flags stop mattering.

---

## SUPERSEDE — additions to the policy's table

Each meets all four bars. Trade-off stated in one sentence, as required. Per the
policy, none is a silent substitution and none removes working software: the
original stays in the catalog with `superseded_by:`.

### 1. ESPHamClock → hamclock-next (+ Open HamClock Backend)

**This is the most consequential finding in the inventory.**

Elwood Downey (WB0OEW), HamClock's author, [became a Silent Key on
2026-01-29](https://www.arnewsline.org/news-text/2026/1/30/silent-key-elwood-downey-wboew-creator-of-hamclock).
The project receives no further updates and [data was expected to stop being
pushed by June
2026](https://daily.hamweekly.com/2026/01/hamclock-creator-elwood-downey-wb0oew-silent-key-hamclock-to-shut-down/).
That date has passed.

AHRL v27 (May 2026) builds ESPHamClock 4.23 **four times** — 800x480, 1600x960,
2400x1440, 3200x1920 — and every menu entry hardcodes `-b hamclock.com:80`.
Anyone installing AHRL v27 today gets four menu entries pointing at a
discontinued backend.

**Replacement:** `hamclock-next` (K4DRW, SDL2 rewrite) as the maintained client,
and/or repointing the existing client at the **Open HamClock Backend**
(`ohb.works`). Note ESPHamClock is preserved under MIT by community mirrors, so
carrying it is legally clean.

**Trade-off:** *hamclock-next is a maintained rewrite with an active backend,
where ESPHamClock is frozen at its author's death and pointed at a server that
stopped feeding it.*

**The irony worth recording:** AHRL v27 already ships `hamclock-next-1.5.tar.gz`
and defines `install_hamclock_next()` — and never calls it (**D-013**). AHRL
accidentally shipped the successor and installed four copies of the deceased
original instead. This is the D-013 argument with a real user consequence
attached, not a hypothetical.

**Action — accepted 2026-08-25, treated as priority.** CARRY `hamclock-next`
(REVIVE from dead code), SUPERSEDE ESPHamClock, and make the backend URL a
**manifest field**, never a hardcoded launcher argument. Recorded as the worked
example in **D-013**; this is schema shape 7.

### CORRECTION 2026-08-25 — tested, and the forecast was wrong

The text below this correction was written from *reporting*. Instructed to test
it, I did, and one claim does not survive.

**Retracted:** that AHRL v27 leaves users with "four menu entries pointing at a
discontinued backend." AHRL passes `-b hamclock.com:80`, and **hamclock.com is
up** — HTTP 200, `Last-Modified 2026-08-07`, and `/ham/HamClock/version.pl`
returns **4.27** with a changelog of new features. HamClock did not stop; it was
continued by someone else, past the version AHRL ships.

**Confirmed:** Elwood's own server is gone. `clearskyinstitute.com:80` refuses
TCP outright. The sunset was real — it landed on the original host, not on the
hostname AHRL uses.

**New:** hamclock.com is now a third-party, patron-funded operation ("$4.99/month
is what keeps the backend on the air"), with an Amazon Appstore listing. Not the
author's service, and its commercial trajectory is not ours to predict.

**Also resolves the 4.22-vs-4.23 discrepancy:** neither was final. Newsline was
right in January, AHRL was right in May, and the live backend is on 4.27.

**What this changes for the disposition.** SUPERSEDE still stands, but for a
different and better reason. Not "the original is dead" — it isn't. Rather:
AHRL's four builds are pinned to a frozen 4.23 while the ecosystem moved to 4.27
across two maintained MIT forks, and AHRL's backend host is now a commercial
third party its users never chose. **Shape 7 is what matters here**, and the
testing strengthened it: the backend landscape moved twice in seven months, which
a launcher constant cannot follow and a manifest field can.

Full probe results and limits in `docs/reference/licence-verification.md`.
Successor choice is **Q-006** — there are four options, not three.

---

**Sourcing.** Verified against primary reporting and quoted in full in
`licence-verification.md`. Two things that must not be overstated in public
copy:

- We have **not tested a live client**. Correct phrasing is *reported to stop
  functioning end of June 2026*, not *stopped*.
- Amateur Radio Newsline reports the final release as **4.22**; AHRL v27 ships
  **4.23**. Unresolved discrepancy; it does not change the conclusion.

There are **four** options, not three — see Q-006. Both candidate clients are
**MIT** and clean under D-011: `accius/openhamclock` (455 stars, pushed
2026-08-22) and `k4drw/hamclock-next` (34 stars, pushed 2026-06-23, and it
carries Elwood's copyright forward explicitly). The other two —
`hamclock.com` and `ohb.works` — are backend *services*, not software.

---

### 2. Open Wouxun (`owx`) → CHIRP

**Trade-off:** *CHIRP supports the Wouxun KG-UV family with an active
release cadence and a GUI, where `owx` is a 2022 CLI snapshot that needs
`-Wno-*` flags to compile.*

AHRL installs both. **Accepted 2026-08-25: CARRY both, mark CHIRP the
recommended default.** `owx` stays for any model CHIRP lacks — superseding is not
an excuse to remove working software.

---

### 3. aa-analyzer → flaa

**Trade-off:** *`flaa` is an actively maintained W1HKJ GUI for the same
RigExpert AA-\* analyzers, where `aa-analyzer` is a Perl CLI depending on
`Device::SerialPort`, a CPAN module unmaintained for roughly a decade.*

**This supersession removes an entire backend.** `aa-analyzer` is the *only*
CPAN consumer in the inventory (D-004 amendment). Superseding it deletes the
CPAN backend, its unpinned-network-install security problem, and its
`PERL_MM_USE_DEFAULT=1` auto-accept from the 1.0 scope.

Worth weighing against D-014: a backend justified by exactly one package, where
that package has a maintained replacement, is a backend we should not build.
Recommend CARRY `flaa` as default, CARRY `aa-analyzer` only if someone wants the
CLI — and if so, satisfy it from Debian's `libdevice-serialport-perl` rather
than CPAN.

---

### 4. Virtual Radar Server → readsb + tar1090

**Trade-off:** *`tar1090` on `readsb` is the current ADS-B web UI and shares a
backend with the already-agreed `dump1090` → `readsb` supersession, where
Virtual Radar Server is a Mono application and Mono was handed off by Microsoft
in 2024 and is being wound down across distros.*

This makes the ADS-B stack coherent: one decoder (`readsb`), one web UI
(`tar1090`), no Mono runtime, no `.exe` config-patch tarball, and no launcher
that starts a decoder and `killall -9`s it on exit.

---

### 5. grig → flrig

**Trade-off:** *`flrig` is actively maintained by W1HKJ and already in the
catalog, where `grig` is a generic hamlib front-end with no meaningful upstream
activity in a decade.*

**Accepted 2026-08-25: CARRY both, mark `flrig` the recommended default.**
`grig` stays — it is a thin, dependency-light hamlib GUI and some operators
prefer that. For Icom, `wfview` is better still.

---

### 6. RTL-SDR Blog V4 driver → distro `librtlsdr` *(verify in container)*

**Trade-off:** *If the distro `librtlsdr` now carries V4 support, using it
removes the single most destructive operation in the entire inventory.*

The V4/R828D patch [was upstreamed to Osmocom
`rtl-sdr`](https://github.com/rtlsdrblog/rtl-sdr-blog). If Debian 13 / Ubuntu
26.04 ship a new enough `librtlsdr`, AHRL's approach becomes unnecessary — and
AHRL's approach is:

```
rm -fr /usr/lib/librtlsdr* /usr/local/lib/librtlsdr*
rm -fr /usr/include/rtl-sdr* /usr/local/include/rtl-sdr*
rm -fr /usr/local/bin/rtl_*
```

…followed by hand-created `.so` symlinks in `/usr/lib/$(arch)-linux-gnu`. It
deletes distro-managed libraries with no record and no undo, every run.

**High value if true — accepted 2026-08-25 as the highest-value item on this
list.** Container-check the actual `librtlsdr` version **per target**; the answer
may differ between Debian 13, Ubuntu 26.04, Parrot and Raspberry Pi OS.

**Where it does not hold, the replacement is not silent.** The driver swap must
appear in `system_modifications` **in full** and be printed by `--dry-run` in
full: every deleted path, every created symlink, the udev rules file, and the
modprobe blacklist. A user is entitled to know before we delete distro-managed
libraries, not after.

---

### 7. gpsman → GPSBabel + gpsd

**Trade-off:** *`gpsd` plus `GPSBabel` covers device access and format
conversion with active maintenance, where `gpsman` is a Tcl/Tk application
whose upstream has been dormant for years.*

Low stakes — `gpsman`'s menu entry is documentation-only in AHRL.

---

### 8–12. Infrastructure superseded by our own engine

| AHRL unit | Superseded by | Trade-off |
|---|---|---|
| `source_libs` | `build_depends` in the schema | *A declared per-package field is queryable and dry-runnable, where a hardcoded 12-package array is neither.* |
| `ahrl_menus` | Generated desktop entries from `categories` | *A generated call list cannot drift from the catalog — which is exactly the bug that leaves `hamclock-next` dead (**D-013**).* |
| `ahrl_docs` | Generated package reference | *Generated docs cannot contradict the manifests; `dpkg-query --list` dumped to a text file can.* |
| `ahrl_version` | `hammunition --version` | *Standard CLI behaviour beats a generated shell script that echoes a string.* |
| `libhamlib4` | apt `depends` resolution | *A shared library with no operator surface is a dependency, not a unit — every rig-control manifest that needs it declares it, and `libhamlib-utils` is the operator-facing hamlib manifest. Ruled by the maintainer 2026-08-30 (Q-015 decision 3).* |

---

## REVIVE

| Unit | What I would try |
|---|---|
| `ardop` | **Try the install method before the build.** 73Linux does not compile ARDOP — it pulls upstream's prebuilt release asset via the GitHub Releases API. AHRL's compile error may be irrelevant. Cheapest possible revival: change the backend, not the code. |
| `radiosonde_auto_rx` | Standard venv install from the pinned upstream tag. AHRL's objection was that it hardcodes `pi` as the username and lives in `$HOME` — exactly what `scope: user` plus a venv backend exists to handle. |
| `ibp` | Build current source with the `-Wno-implicit-int -Wno-deprecated-declarations` family, as AHRL itself did before disabling. If it still fails, SUPERSEDE — find what shows IBP beacon status now. Never RETIRE: the beacons still transmit. |
| `dream` | Establish whether Qt5 WebKit is genuinely required or only for an optional dashboard. If required, look for a maintained fork; if none, this is a documented gap, not a quiet removal. |
| `mvoice` | `libopendht-dev` is the blocker. Check whether OpenDHT is packaged again, vendorable, or whether a maintained M17 client supersedes mvoice entirely (**D-007** says M17 is ours to build regardless). |
| `hamclock-next` | **Revive AHRL's own dead code.** The function, the tarball, the menu entry and the changelog entry all exist; only the call is missing. Verify the build, then carry it as the HamClock successor (SUPERSEDE #1). |

---

## RETIRE — beyond the settled four

Reason codes are the policy's three: **(1) world changed**, **(2) never
worked**, **(3) out of scope**.

| Unit | Reason | Evidence |
|---|---|---|
| Firefox / `install_browser` | **3** | We do not install web browsers. Every target ships one. AHRL's browser logic is also its buggiest — `$BROWSER` is never assigned, and the snapd branch adds an unpinned PPA plus an APT pin. Depend on `x-www-browser` existing; do not manage it. |
| Notepadqq | **3** | General-purpose text editor. Present for the ARRL Teachers Institute menu, not for radio. |
| TkCVS | **3** + **1** | A Tk GUI for CVS and Subversion. CVS is dead; this has no menu entry in AHRL and no connection to radio. |
| xosview | **3** | X11 system load monitor from the 1990s. No menu entry, not radio. |
| Backdrops | **3** | 20 MB of desktop wallpapers. We are not a desktop theme. |
| PyAutoGUI | **3** | AHRL's own menu-regression harness. Becomes our CI, not a catalog entry. |
| `mfc_gpl` | **2** | Settled. |
| `tt3_gpl` | **2** | Settled. |
| `noaa-apt` | **1** | Settled. |
| `xwxapt` | **1** | Settled. |
| Arduino IDE | **3** | Debian ships IDE **1.x**, deprecated upstream. Shipping a deprecated IDE is worse than shipping nothing — document and point at arduino.cc. Accepted 2026-08-25. |

**All six proposed RETIREs accepted 2026-08-25**, plus Arduino from the EDA
split. `install_browser` in particular: depend on `x-www-browser`, never manage a
browser.

**Deliberately *not* retired**, though each looks like a candidate:

- `atlc`, `wwl`, `sunclock`, `qgrid`, `Fl_MoxGen` — old, but finished and
  correct. The policy explicitly forbids retiring for age.
- `wordsworth` — two Perl scripts, but they work and nothing replaces them.
- `linpac` — superficially superseded by the new packet stack, but keyboard-to-
  keyboard packet is a different workflow from Winlink. CARRY both.
- `xwefax` — HF radiofax is **still transmitted** (NOAA, DWD, JMA). Not a world-
  changed case, unlike `xwxapt`. See NEEDS-DECISION on fldigi overlap.

---

## NEEDS-DECISION — AHRL

| Unit | The specific question |
|---|---|
| Claws Mail | **RESOLVED 2026-08-30 (Q-015 #1):** neither carried-by-default nor documented-away. The packet profile *detects* an existing mail client and respects the system's choice; only when none is found does an interactive run offer an open-source selection — Thunderbird, Claws Mail, Evolution, Geary — each now a catalog manifest, none ever installed silently, `--yes` skipping with a note (the D-035 shape). Claws Mail is CARRY as one option among four. |
| PuTTY | **RESOLVED 2026-08-30 (Q-015 #2):** CARRY, as the recommended option in the workstation profile's serial-terminal suggestion group (detect-respect-offer, same mechanism as the mail client). Offered alongside CuteCom, picocom, tio and minicom; Termius (proprietary freemium) and MobaXterm (Windows-only) are named in the docs but not offered. |

---

## Reserved to the maintainer — investigated, not decided

### The EDA / electronics cluster

The policy lists `kicad`, `pcb`, `gerbv`, `gspiceui`, `gwave`, Arduino IDE and
Fritzing, proposing a separate `electronics` profile.

**What the investigation adds — the cluster as listed is not homogeneous.**
There is a defensible line inside it, and it does not fall where the list does:

| Genuinely general electronics | Genuinely RF/antenna |
|---|---|
| KiCad (+ gerbview, pcbnew) | `xnec2c` — antenna modelling |
| Fritzing | `Coil64` — coil inductance |
| GSpiceUI + ngspice | `atlc` — transmission-line calculator |
| Arduino IDE | `gsmc` — Smith chart |
| | `Fl_MoxGen` — Moxon antenna design |
| | `flaa` / `antscope2` — antenna analysers |
| | `nanovna-saver`, `QtTinySA` — VNA / spectrum analyser |

The right-hand column is radio work that happens to involve components. It
belongs in ham-core. The left-hand column is a hobby that overlaps.

**Two facts for the decision:**
- `gspiceui` needs fixing either way — it hardcodes an `aarch64-linux-gnu`
  symlink path on every architecture and leaves a dangling symlink on x86_64.
- The Debian `arduino` package is Arduino IDE **1.x**. IDE 2.x is distributed by
  arduino.cc as a `.deb`/AppImage. Carrying the apt package means shipping a
  deprecated IDE. If the cluster is carried at all, this is a SUPERSEDE.

`pcb`, `gerbv` and `gwave` are **not in AHRL v27** — v26a removed `gwave` and
replaced `pcb`/`gerbv` with KiCad's equivalents. Only KiCad, Fritzing, GSpiceUI,
ngspice and Arduino are live decisions.

### Resolved 2026-08-25 — split accepted

- **ham-core:** `xnec2c`, `Coil64`, `atlc`, `gsmc`, `Fl_MoxGen`, `flaa`,
  `nanovna-saver`, `QtTinySA`. Antenna and RF test work.
- **`electronics` profile, opt-in:** `kicad`, `fritzing`, `gspiceui`, `ngspice`.
- **Arduino — RETIRE, reason (3).** Do **not** carry the Debian `arduino`
  package: it is Arduino IDE **1.x**, and shipping a deprecated IDE is worse than
  shipping nothing. Document the omission and point users at arduino.cc for
  IDE 2.x.
- **`pcb`, `gerbv`, `gwave` — out of consideration entirely.** Not in AHRL v27;
  v26a removed `gwave` and replaced `pcb`/`gerbv` with KiCad equivalents.
- `gspiceui`'s hardcoded `aarch64-linux-gnu` symlink is fixed via the `arch`
  selector regardless of profile (**D-016**).

---

### Morse Runner

**What the investigation adds:** carrying Morse Runner means carrying Wine into
the core for a single CW trainer — and it is x86_64-only, so every ARM user
(Raspberry Pi, uConsole) already gets nothing. AHRL deletes its `.desktop` file
on aarch64.

**Alternatives exist and are real:**
- **Morse Runner CE** (community edition, `w7sst/MorseRunner`) — the fork AHRL
  already pulls, still a Windows binary.
- **`qrq`** — already in the catalog, native, actively maintained; a CW *speed*
  trainer rather than a contest simulator, so not a straight replacement.
- **`ebook2cwgui`, `xcwcp`, `wordsworth`** — also already carried, also native,
  also not contest simulators.

**The honest position:** nothing native replicates Morse Runner's contest
simulation. The choice is a Wine dependency for one x86_64-only trainer, or a
documented gap.

### Resolved 2026-08-25 — conditional

**If Morse Runner CE or a native alternative builds, carry that and drop the Wine
prefix from 1.0.** If neither does, **defer Morse Runner post-1.0 alongside
VARA** rather than pulling Wine into core for a CW trainer.

Either way Wine leaves the 1.0 core: it exists in AHRL solely for this unit, and
VARA reintroduces it post-1.0 regardless. Disposition stays `M` pending the build
attempt — this is a testable condition, not an open opinion.

---

## 73Linux delta — 28 units

### A licensing constraint that governs most of this table

73Linux has no licence (**D-001**). That is survivable for *third-party*
software, because we take facts — names, versions, URLs, methods — and write our
own manifests. It is **not** survivable for software KM4ACK wrote himself: those
are original works in an unlicensed repository, and we cannot redistribute them
or derive from them.

Roughly half the delta is KM4ACK's own scripting. Those units are RETIRE
regardless of merit — not because they are bad, but because we have no right to
ship them. **If the licence question is ever resolved with Jason (D-001's
suggested email), most of this section reopens.**

### ADD — the 1.0 packet core (D-008), corrected to eight units

**Correction accepted 2026-08-25.** `PITERM`, `QTSOUND` and `PIAPRS` were
misclassified as Pi system helpers on the strength of their filename prefix. They
are QtTermTCP, QtSoundModem and an APRS messaging client — third-party packet
software. All three move into the 1.0 packet core. See D-008's correction.

| Unit | What it is | Backend |
|---|---|---|
| **QtTermTCP** (`PITERM`) | Packet terminal over TCP (G8BPQ) — pairs with BPQ | Binary |
| **QtSoundModem** (`QTSOUND`) | Soundcard packet modem (UZ7HO / Wiseman port) — alternative to Direwolf | Binary |
| **Pi-APRS** (`PIAPRS`) | APRS messaging client | Binary |
| **PAT** | Winlink client (`la5nta/pat`) | Vendor `.deb` from GitHub Releases, per-arch |
| **AX.25** | `ax25-tools` + `ax25-apps` + `/etc/ax25/axports` config | apt + **templated config** |
| **BPQ** (linbpq) | BBS / Winlink gateway node (G8BPQ) | Binary — *but see verification problem* |
| **ARDOP** | ARDOP modem | Prebuilt release asset (also REVIVEs AHRL's `ardop`) |
| **Direwolf** | Soundcard TNC — *with configuration* | Already CARRY'd from AHRL; the ADD is the config |

#### Status, 2026-08-28 — five of eight, and four by a better route

| Unit | Manifest | How, against how 73Linux does it |
|---|---|---|
| PAT | `pat` | apt — 73Linux fetches a vendor `.deb` per architecture |
| AX.25 | `ax25-tools`, `ax25-apps` | apt. The `/etc/ax25/axports` config is still open |
| BPQ | `linbpq` | source from upstream's own tag — 73Linux takes an unversioned prebuilt from a directory named Beta |
| ARDOP | `ardopcf` | source from upstream's release tag — 73Linux pulls a prebuilt release asset |
| Direwolf | `direwolf` | apt. The ADD is the configuration, still open |
| QtTermTCP | — | binary backend, not written |
| QtSoundModem | — | binary backend, not written |
| Pi-APRS | — | binary backend, not written |

None of the three outstanding is packaged on any target: `apt-cache policy`
finds no candidate for `qttermtcp`, `qtsoundmodem`, `garim` or `varim` on
Debian 13, Ubuntu 26.04 or Kali (2026-08-28). `xygrib`, listed further down as
an ADD candidate, **is** in apt on all three and now has a manifest.

The two open items are the same one: station-local configuration. `axports`
and `direwolf.conf` both need a callsign, which is the question CLAUDE.md
records as blocking and which `linbpq`'s `config_files` block already depends
on.

### ADD candidates — third-party, genuinely useful, not yet scoped

**I flagged these as "Pi-system helpers, out of scope" in D-008. That was wrong
and I am correcting it.** The `PI*` prefix is 73Linux's naming, not a statement
about the software. Three of them are G8BPQ packet tools:

| Unit | What it actually is | Why it matters |
|---|---|---|
| **QTSOUND** | **QtSoundModem** (UZ7HO / Wiseman port) | A real soundcard packet modem. Direct alternative to Direwolf for some setups. Belongs in the packet discussion, not a helper bucket. |
| **PITERM** | **QtTermTCP** (G8BPQ) | Packet terminal over TCP. Pairs with BPQ. |
| **PIAPRS** | APRS messaging client | Overlaps Xastir/YAAC but is messaging-focused |
| **XYGRIB** | GRIB weather viewer | Third-party, open source, genuinely absent from ham catalogs |
| **GARIM / VARIM** | ARIM / VARIM file transfer over ARDOP / VARA | Core EMCOMM file transfer; GARIM is open, VARIM pairs with closed VARA |

**Resolved 2026-08-25:** QtSoundModem, QtTermTCP and Pi-APRS move into the 1.0
packet core. GARIM/VARIM and XYGRIB remain ADD, scoped with VARA post-1.0 where
they depend on it.

### CARRY / post-1.0

| Unit | Disposition | Note |
|---|---|---|
| ARDOPGUI | CARRY (post-1.0) | GUI for ARDOP; pairs with the 1.0 ARDOP |
| PATMENU3 | RETIRE | KM4ACK's menu wrapper for PAT — licence blocked, and ruled 2026-08-30 unneeded: `pat http` ships the interface the wrapper fronts. Documented in the packet profile. |
| VARA | ADD (post-1.0) | Closed-source freeware, needs Wine prefix. Settled post-1.0 by D-008. |
| HAMRS | ADD (post-1.0) | Proprietary freemium, AppImage, upstream scrapes its own download page. Settled post-1.0. |
| GPS | CARRY | `gpsd` — we need it anyway for the hardware layer |
| REPEAT | NEEDS-DECISION | RepeaterSTART is third-party; question is scope, not licence |
| M0IAX | RETIRE (revisit on demand) | JS8Call utilities, third-party. Ruled 2026-08-30: no measured demand; revisit when a JS8 profile user asks. |

### RETIRE — 73Linux delta

| Units | Reason | Note |
|---|---|---|
| EES, GPSUPDATE, SHOWLOG, SECURITY, GRIDCALC, DIPOLE, BATT, PIQSO, PATMENU | **3** (and licence-blocked) | KM4ACK's own scripts in an unlicensed repo. Several are genuinely useful — EES is an emergency email server, DIPOLE and GRIDCALC are calculators — but we cannot ship them. Where the function matters (dipole calculator, grid calculator) we write our own or find a licensed equivalent. |
| CONKY, PISTATS | **3** | System monitors. Not radio. |
| VNC | **3** | RealVNC viewer — proprietary, general-purpose remote desktop. |

---

## Skywave delta — 9 units

Applies the policy to `skywave-inventory.md`'s measured delta. Every one is
**absent from Debian, stable and unstable** (measured in `debian:13` and
`debian:sid`), so none can arrive by apt and each names the backend it forces.
This is the cluster that justifies the **source-from-git** backend more than any
single AHRL unit does: a coherent aeronautical/maritime decoding domain no other
source in the union — and no Debian release — covers. **None has a manifest yet.**

| Unit | Disposition | Upstream (resolved, D-018) | Licence | Backend | Note |
|---|---|---|---|---|---|
| **LibACARS** | ADD | `szpajder/libacars` | MIT | source-from-git (CMake) | Dependency of the four decoders below; `depends` for each. |
| **Acarsdec** | ADD | `f00b4r0/acarsdec` | GPL-2.0-only | source-from-git | Install from the maintained successor; `TLeconte/acarsdec` is archived. Skywave 5.10 already ships the f00b4r0 line (v4.4.1). |
| **Acarsserv** | ADD | `TLeconte/acarsserv` | GPL-2.0 | source-from-git | The one at-risk unit: **archived, and untouched since 2018-12-19** (re-verified 2026-08-28; the archive *date* previously stated here was not sourceable). Still the SQLite companion `acarsdec` documents. Carry, and record the archived-upstream risk (**D-024** territory — pin the commit a distribution packages; here none does, so pin our own and watch for a successor). |
| **DumpHFDL** | ADD | `szpajder/dumphfdl` | GPL-3.0 | source-from-git (CMake) | Active (2026-08-07). Depends on LibACARS. |
| **VDLM2dec** | **SUPERSEDE** → `dumpvdl2` | `szpajder/dumpvdl2` | GPL-3.0 | source-from-git (CMake) | Meets all four SUPERSEDE bars: same function, maintained, same install, one-sentence trade-off — *dumpvdl2 is the maintained VDL Mode 2 decoder; vdlm2dec is archived.* Skywave ships the archived `vdlm2dec 2.3`; we carry the successor and record `superseded_by:`. |
| **RTLSDR-Airband** | ADD | `rtl-airband/RTLSDR-Airband` | GPL-2.0 | source-from-git (CMake) | Active, v5.3.0 (2026-08-16) — Skywave ships 4.0.2. Canonical repo resolved past two redirects. |
| **Kalibrate-RTL** | ADD | `steve-m/kalibrate-rtl` | BSD-2-Clause | source-from-git (autotools) | **Dormant, not active** — last commit on master is **2022-02-01**, and it has never cut a tag (re-verified 2026-08-28; the "active" claim came from GitHub's `updated_at`, which moves when somebody stars a repository). Consequence for the manifest: no tag to pin, so it needs a commit pin with a `pin_review` (**D-024**). Kali packages it and Debian does not, so the basis can be `distribution_pin` rather than `own_choice` if Kali's revision is identifiable. |
| **SuperSDR** | **NEEDS-DECISION** (Q-007) | `mcogoni/supersdr` | **none — default copyright** | source-from-git / python-in-place | The headline listening client, and it carries no licence — no `LICENSE`, no header, checked in-tree. The other two KiwiSDR clients in AB9IL's set are no better. **Also dormant: last commit 2022-12-31** (re-verified 2026-08-28; the earlier "active (2026-02-18)" was GitHub's `updated_at`). Unlicensed *and* three and a half years untouched is a materially weaker case than Q-007 was posed with. Reserved to the maintainer. |
| **Reticulum MeshChat** | ADD (post-1.0) | `liamcottle/reticulum-meshchat` | MIT | AppImage | Ships Linux only as an AppImage — a cleaner second consumer than HAMRS (ordinary GitHub release assets, no page-scraping). Lands in the post-1.0 `mesh` profile, so it does not promote AppImage into 1.0, but the backend now has two independent users (**D-014**). |

**Backend tally.** Seven 1.0 units (six ADD + the dumpvdl2 SUPERSEDE) are
**source-from-git**; LibACARS is a shared `depends` for four of them. MeshChat is
the post-1.0 AppImage. SuperSDR would be an eighth source build if Q-007 carries
it. Skywave adds **no** backend requirement AHRL did not already impose — but it
is the densest single argument for finishing source-from-git, because the whole
delta needs it and buys a domain nothing else covers.

**Profile placement.** All eight decoders/clients land in `listening`
(`profile-sizing.md` sized it with room); MeshChat in post-1.0 `mesh`.

---

## DragonOS Tier 1 — 24 units

Applies the policy to `dragonos-tier1-inventory.md`. Membership was decided by an
`apt-cache policy` probe in all four x86 targets, not by the list in `SCOPE.md`.
The headline is that **Tier 1 is mostly already ours**: 16 of the 24 arrive
through AHRL parity or the Debian Blend and are CARRY, cross-referenced below and
not re-argued. The 8 genuinely-new SIGINT units are ADD — and **seven already
have manifests**; the catalog anticipated them. Only `sdrangel` remains to write.

### The 16 already covered — CARRY (cross-reference)

Not re-classified here; each is dispositioned where it first appears.

| Via AHRL (already CARRY/SUPERSEDE) | Via Debian Blend |
|---|---|
| `fldigi`, `js8call`, `wsjtx`, `qsstv`, `gpredict`, `gnuradio`, `gqrx`, `cubicsdr`, `direwolf`, `satdump`, `AIS-catcher` — and `sdrpp` = AHRL's `SDR++` (CARRY, pinned — the unversioned-snapshot fix, not a replacement) | `soapysdr-tools`, `uhd-host`, `multimon-ng`, `hacktv`, `gpsd`/`ffmpeg`/`sox` (infrastructure) |

### The 8 new — ADD

All eight are the RF-security/SIGINT contribution. Backend is apt except the two
`.deb` units, which need **per-target install blocks** (`Selector` already
expresses this) because apt has no candidate on some targets.

| Unit | Manifest | apt coverage | Backend | Note |
|---|---|---|---|---|
| **wireshark** | ✅ written | all four | apt + `group_membership` | Capture without root needs the `wireshark` group — a disclosed modification. |
| **aircrack-ng** | ✅ written | all four | apt | Wi-Fi audit suite. |
| **hcxdumptool** | ✅ written | all four | apt | WPA capture. Transmit-adjacent; RF-security profile. |
| **hcxtools** | ✅ written | all four | apt | Companion conversion tools. |
| **ubertooth** | ✅ written | all four | apt | BLE/BT sniffer host tools. Owned hardware (issue #9). |
| **rtl-433** | ✅ written | all four | apt | ISM 433/868/915 decoder. |
| **inspectrum** | ✅ written | all four | apt | Offline signal visualiser. |
| **sdrangel** | ❌ **to write** | Kali only | upstream `.deb` per-target | `f4exb/sdrangel` ships `sdrangel_7.27.2_ubuntu-26.04_amd64.deb`; tested to install on Ubuntu 26.04 only, apt on Kali. Needs a `Selector` block, not one URL. |

**Two `.deb` cautions carried from the inventory, both pin/hash-database work,
neither a blocker here.** `sdrangel`'s artifact installs only on the base it was
built for (per-target blocks required); **`sdrpp` has no pinnable release** — its
assets hang off a rolling `nightly` tag, so the URL is stable and the artifact
behind it is not. Record both against the pin/hash sub-project `SCOPE.md` names.

**Backend tally.** Six apt (all written), one apt-with-group (`wireshark`,
written), one upstream `.deb` with a per-target selector (`sdrangel`, to write).
DragonOS Tier 1 adds **no source build** — it is the cheapest of the five deltas,
exactly as `SCOPE.md`'s staging predicted, and it is nearly done.

**Profile placement.** All eight in `rf-security` (the opt-in SIGINT profile).
Cellular/EW is deliberately **not** here — 20 units, transmit-capable, blocked on
**Q-008**.

---

## REVIVE — verification log

Three of the six REVIVE units were tested on **2026-08-28** in a Debian 13
container. `PARITY-POLICY.md` requires a REVIVE to be attempted rather than
assumed, and two of these had inherited verdicts that measurement changed.

| Unit | Tested | Result |
|---|---|---|
| `ardop` | build from tag `1.0.4.1.3` | **Revived.** Now `catalog/packages/ardopcf.yaml`. |
| `mvoice` | dependency availability | **Still blocked.** Reason confirmed. |
| `dream` | dependency availability | **Still blocked.** Reason confirmed. |

**`ardop` — AHRL's error was not the error.** AHRL v27 disabled it with
"compiler error on Xubuntu 26.04 / in function `client_handler`: too many args
to function `process_http_req`". On Debian 13 the build fails somewhere else
entirely: three `-Wint-conversion` errors at `lib/rawhid/rawhid.c:361`, because
GCC 14 promoted that warning to an error. With `-Wno-int-conversion` the build
succeeds and produces `ardopcf`. Upstream's `master` head
(`a7c92289b569`, 2025-05-27, read from the branch — **D-032**) fails
identically, so the release tag is the right pin and this is a current defect
rather than one a newer revision has fixed.

The flag silences a genuine bug rather than a pedantic warning: the CM108 HID
path passes a `hid_device *` to `read()`, `write()` and `close()` on the
non-Windows branch. The manifest records that CM108 push-to-talk should be
tested before it is relied on, and that serial and VOX keying are unaffected.
Reporting it upstream has not been done from here.

The suggestion in the table above — take 73Linux's prebuilt release asset
instead of compiling — turned out to be unnecessary. Compiling works.

**`mvoice` — the blocker is real and measured.** `libopendht-dev` has **no
candidate on Debian 13** (`apt-cache policy`, 2026-08-28), which is exactly
what AHRL's "no openhdt" comment claimed. Upstream is alive: head of `master`
is `7589795c7ca0`, 2026-06-12. Its README acknowledges the situation directly
and instructs the user to build OpenDHT from source — a build dependency that
must itself be built, which is a shape no manifest in this catalog can express
today. **The disposition stands and the reason is now tested rather than
inherited.**

**`dream` — same shape.** `libqt5webkit5-dev` has **no candidate on Debian 13**
(measured the same way). AHRL's "no webkitwidgets" comment is confirmed. What
is still open is the question the table above asks: whether Qt5 WebKit is
genuinely required or only for an optional dashboard. That needs reading the
source, not probing the archive.

`ibp`, `radiosonde_auto_rx` and `hamclock-next` were not attempted in this
round. `hamclock-next` already has a manifest; `radiosonde_auto_rx` waits on
the venv backend by design.

---

## Complete index — all 150 units

Sorted for completeness-checking. `S` = SUPERSEDE, `R` = REVIVE, `X` = RETIRE,
`C` = CARRY, `A` = ADD, `?` = NEEDS-DECISION, `M` = reserved to maintainer.

133 AHRL + 73Linux units, plus **9 Skywave delta** and **8 new DragonOS Tier-1**
units. The other 16 DragonOS Tier-1 units are cross-references to units already
listed under AHRL or covered by the Blend, and are not re-indexed here.

**AHRL (105):**

`aa-analyzer` S · `ahrl_docs` S · `ahrl_menus` S · `ahrl_version` S ·
`AIS-catcher` C · `AntScope2` C · `ardop` R · `arduino` M · `atlc` C ·
`backdrops` X · `browser` X · `chirp` C · `claws-mail` C · `Coil64` C ·
`country_files` C · `cqrlog` C · `cwwav` C · `direwolf` C · `dream` R ·
`dump1090` S · `ebook2cwgui` C · `ESPHamClock` S · `flaa` C · `flamp` C ·
`flcluster` C · `fldigi` C · `fllog` C · `Fl_MoxGen` C · `flmsg` C · `flnet` C ·
`flrig` C · `flwkey` C · `flwrap` C · `FoxTelem` C · `freedv` C · `fritzing` M ·
`glfer` C · `gnuradio` C · `gpredict` C · `gpsman` S · `gqrx` C ·
`GridTracker2` C · `grig` S · `gsmc` C · `gspiceui` M · `hamclock_next` R ·
`ibp` R · `js8call` C · `js8spotter` C · `jtdx` C · `kicad` M · `klog` C ·
`libhamlib4` S · `linpac` C · `linrad` C · `mfc_gpl` X · `morse_runner` M ·
`MSHV` C · `mvoice` R · `nanovna-saver` C · `ngspice` M · `noaa-apt` X ·
`not1mm` C · `notepadqq` X · `owx` S · `pipx` C · `putty` C · `pyautogui` X ·
`qgrid` C · `QLog` C · `qrq` C · `qsstv` C · `qtel` C · `QtTinySA` C ·
`quisk` C · `radiosonde_auto_rx` R · `rf_exposure_calc` X · `rtl_sdr_v4` S ·
`SatDump` C · `SDR++` C · `solar_data` X · `source_libs` S · `splat` C ·
`sunclock` C · `svxlink` C · `svxreflector` C · `tkcvs` X · `tqsl` C ·
`tt3_gpl` X · `virtual_radar_server` S · `wfview` C · `wine` X · `wordsworth` C ·
`wsjtx` C · `wsjtx_improved` C · `wwl` C · `xastir` C · `xcwcp` C · `xdx` C ·
`xlog` C · `xnec2c` C · `xosview` X · `xwefax` C · `xwxapt` X · `yaac` C

**73Linux delta (28):**

`ARDOPGUI` C · `AX25` A · `BATT` X · `BPQ` A · `CONKY` X · `DIPOLE` X · `EES` X ·
`GARIM` A · `GPS` C · `GPSUPDATE` X · `GRIDCALC` X · `HAMRS` A · `M0IAX` X ·
`PAT` A · `PATMENU` X · `PATMENU3` X · `PIAPRS` A · `PIQSO` X · `PISTATS` X ·
`PITERM` A · `QTSOUND` A · `REPEAT` ? · `SECURITY` X · `SHOWLOG` X · `VARA` A ·
`VARIM` A · `VNC` X · `XYGRIB` A

**Skywave delta (9):**

`acarsdec` A · `acarsserv` A · `dumphfdl` A · `kalibrate-rtl` A · `libacars` A ·
`reticulum-meshchat` A · `rtlsdr-airband` A · `supersdr` ? · `vdlm2dec` S

**DragonOS Tier-1 — new units (8):**

`aircrack-ng` A · `hcxdumptool` A · `hcxtools` A · `inspectrum` A · `rtl-433` A ·
`sdrangel` A · `ubertooth` A · `wireshark` A

*(The 16 already-covered Tier-1 units — `fldigi`, `js8call`, `wsjtx`, `qsstv`,
`gpredict`, `gnuradio`, `gqrx`, `cubicsdr`, `direwolf`, `satdump`, `AIS-catcher`,
`sdrpp`=`SDR++`, `soapysdr-tools`, `uhd-host`, `multimon-ng`, `hacktv`,
`gpsd`/`ffmpeg`/`sox` — are indexed under AHRL or arrive via the Blend.)*

---

## What this classification depends on

Three claims carry weight and should be re-verified before the catalog hardens:

1. **HamClock's sunset** — cited above, two independent sources. Highest
   confidence, and it changes a user-visible outcome today.
2. **RTL-SDR V4 upstreaming** — upstream fact confirmed; the *distro* half is
   unverified and needs a container check on each target.
3. **73Linux's missing licence** — verified 2026-08-25 (no LICENSE/COPYING, no
   header on `73.sh`, GitHub licence API null). This governs roughly half the
   delta table, so if it changes, re-run this section.
