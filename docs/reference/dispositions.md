# Dispositions — every unit, one classification

Applies `PARITY-POLICY.md` to `ahrl-inventory.md` and the 73Linux delta.

**Scope:** 105 AHRL `INSTALL_*` toggles (95 executing + 9 disabled + 1 dead
code) and 28 73Linux delta units. **133 units, none unclassified.**

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

| Disposition | AHRL | 73Linux delta | Total |
|---|---:|---:|---:|
| CARRY | 61 | 2 | 63 |
| SUPERSEDE | 12 | 0 | 12 |
| REVIVE | 6 | 0 | 6 |
| RETIRE | 10 | 12 | 22 |
| ADD | — | 11 | 11 |
| NEEDS-DECISION | 10 | 3 | 13 |
| Reserved to maintainer | 6 | 0 | 6 |
| **Total** | **105** | **28** | **133** |

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

**Action:** CARRY `hamclock-next` (REVIVE from dead code), SUPERSEDE
ESPHamClock, and make the backend URL a configurable field rather than a
hardcoded launcher argument.

---

### 2. Open Wouxun (`owx`) → CHIRP

**Trade-off:** *CHIRP supports the Wouxun KG-UV family with an active
release cadence and a GUI, where `owx` is a 2022 CLI snapshot that needs
`-Wno-*` flags to compile.*

AHRL installs both. Keep `owx` as an alternative for any model CHIRP lacks —
but the default should be the tool that gets updated.

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

CARRY `grig` as an alternative — it is a thin, dependency-light hamlib GUI and
some operators prefer that — but `flrig` is the default. For Icom, `wfview` is
better still.

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

**High value if true.** Needs a container check of the actual `librtlsdr`
version on each target. If false, CARRY the blog driver but express the deletion
honestly in `system_modifications` and warn in `--dry-run`.

---

### 7. gpsman → GPSBabel + gpsd

**Trade-off:** *`gpsd` plus `GPSBabel` covers device access and format
conversion with active maintenance, where `gpsman` is a Tcl/Tk application
whose upstream has been dormant for years.*

Low stakes — `gpsman`'s menu entry is documentation-only in AHRL.

---

### 8–11. Infrastructure superseded by our own engine

| AHRL unit | Superseded by | Trade-off |
|---|---|---|
| `source_libs` | `build_depends` in the schema | *A declared per-package field is queryable and dry-runnable, where a hardcoded 12-package array is neither.* |
| `ahrl_menus` | Generated desktop entries from `categories` | *A generated call list cannot drift from the catalog — which is exactly the bug that leaves `hamclock-next` dead (**D-013**).* |
| `ahrl_docs` | Generated package reference | *Generated docs cannot contradict the manifests; `dpkg-query --list` dumped to a text file can.* |
| `ahrl_version` | `hammunition --version` | *Standard CLI behaviour beats a generated shell script that echoes a string.* |

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
| Claws Mail | In scope? It is in AHRL's **NBEMS** menu because EMCOMM workflows need local mail, and Winlink/PAT makes that more relevant, not less. But it is a general mail client. **Question: does the packet/Winlink profile carry a mail client, or do we document "install one" and stop?** |
| PuTTY | Same shape. On Linux `ssh` is built in, but PuTTY is genuinely useful as a *serial terminal* for radio programming. **Question: carry as a serial-terminal tool, or retire as out-of-scope and point at `minicom`/`picocom`?** |
| RF Exposure Calculator | It is a two-line script opening `hintlink.com/power_density.htm`. **Question: do we ship browser bookmarks at all?** If yes they need liveness checks — a bookmark to a dead site is worse than no bookmark. Same for AHRL's five HF_Propagation bookmarks (DXLook, HamTab, OpenHamClock, PSKReporter, VOACAP). |
| Solar Data | Same, plus it depends on `display` from ImageMagick, which IM7 deprecated in favour of `magick display`. **Question: retire, or reimplement as a real fetch-and-render?** |
| `xwefax` vs `fldigi` | fldigi has a built-in WEFAX mode. **Question: is `xwefax` superseded by fldigi, or does it do something fldigi does not?** Needs someone with radiofax experience, not a spec comparison. |
| JTDX | Development has been comparatively quiet against WSJT-X, wsjtx-improved and MSHV. **Question: CARRY as-is, or mark deprecated in favour of the others?** I will not call this — JTDX has a devoted user base and I have no maintenance data good enough to justify demoting it. |
| FT8 family default | We carry `wsjtx`, `wsjtx_improved`, `jtdx`, `mshv`, `js8call`. The policy requires marking a recommended default where several tools overlap. **Question: which one?** |
| HamClock default | After SUPERSEDE #1: is the default `hamclock-next`, or ESPHamClock repointed at Open HamClock Backend? **Question: which, and do we carry both?** |
| FoxTelem | Decodes AMSAT Fox-series telemetry. Some Fox satellites have re-entered. **Question: is enough of the constellation alive to justify carrying it?** Needs an AMSAT status check, not a guess — and it is a *partial* world-changed case, unlike NOAA APT which is total. |
| `libhamlib4` vs `libhamlib-dev` | AHRL installs the runtime as a unit and the dev package as a build dependency of others. **Question: is hamlib a catalog unit at all, or purely a dependency?** It has no menu entry. |
| `country_files` (cty.dat) | Not software — a data file, fanned out to six directories, that goes stale monthly. **Question: is this a package, or the first instance of a "data asset with an update cadence" that the schema needs a shape for?** |
| `wine` | In AHRL it exists solely for Morse Runner. **Question: if the Morse Runner call goes against Wine, does Wine leave 1.0 entirely?** VARA needs a Wine *prefix* post-1.0 regardless. |

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

**Recommendation:** separate `electronics` profile, not removal; move the five
left-hand units; keep the right-hand column in ham-core. **Your call.**

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
documented gap. **Your call.** If Wine leaves, note that VARA reintroduces it
post-1.0 anyway — so the decision is about 1.0 scope, not about Wine forever.

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

### ADD — the 1.0 packet core (D-008)

| Unit | What it is | Backend |
|---|---|---|
| **PAT** | Winlink client (`la5nta/pat`) | Vendor `.deb` from GitHub Releases, per-arch |
| **AX.25** | `ax25-tools` + `ax25-apps` + `/etc/ax25/axports` config | apt + **templated config** |
| **BPQ** (linbpq) | BBS / Winlink gateway node (G8BPQ) | Binary — *but see verification problem* |
| **ARDOP** | ARDOP modem | Prebuilt release asset (also REVIVEs AHRL's `ardop`) |
| **Direwolf** | Soundcard TNC — *with configuration* | Already CARRY'd from AHRL; the ADD is the config |

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

**Recommendation:** QtSoundModem and QtTermTCP should be evaluated for the 1.0
packet core alongside BPQ — they are the same author's stack and the same use
case. GARIM likewise. **This is a scope question, so I am not deciding it**, but
the D-008 note that put them out of scope was based on my misreading of their
names and should not stand as evidence.

### CARRY / post-1.0

| Unit | Disposition | Note |
|---|---|---|
| ARDOPGUI | CARRY (post-1.0) | GUI for ARDOP; pairs with the 1.0 ARDOP |
| PATMENU3 | NEEDS-DECISION | KM4ACK's own menu wrapper for PAT — licence blocked. Question: do we write our own equivalent, or does PAT's native UI suffice? |
| VARA | ADD (post-1.0) | Closed-source freeware, needs Wine prefix. Settled post-1.0 by D-008. |
| HAMRS | ADD (post-1.0) | Proprietary freemium, AppImage, upstream scrapes its own download page. Settled post-1.0. |
| GPS | CARRY | `gpsd` — we need it anyway for the hardware layer |
| REPEAT | NEEDS-DECISION | RepeaterSTART is third-party; question is scope, not licence |
| M0IAX | NEEDS-DECISION | JS8Call utilities, third-party. Question: does the JS8 profile want them? |

### RETIRE — 73Linux delta

| Units | Reason | Note |
|---|---|---|
| EES, GPSUPDATE, SHOWLOG, SECURITY, GRIDCALC, DIPOLE, BATT, PIQSO, PATMENU | **3** (and licence-blocked) | KM4ACK's own scripts in an unlicensed repo. Several are genuinely useful — EES is an emergency email server, DIPOLE and GRIDCALC are calculators — but we cannot ship them. Where the function matters (dipole calculator, grid calculator) we write our own or find a licensed equivalent. |
| CONKY, PISTATS | **3** | System monitors. Not radio. |
| VNC | **3** | RealVNC viewer — proprietary, general-purpose remote desktop. |

---

## Complete index — all 133 units

Sorted for completeness-checking. `S` = SUPERSEDE, `R` = REVIVE, `X` = RETIRE,
`C` = CARRY, `A` = ADD, `?` = NEEDS-DECISION, `M` = reserved to maintainer.

**AHRL (105):**

`aa-analyzer` S · `ahrl_docs` S · `ahrl_menus` S · `ahrl_version` S ·
`AIS-catcher` C · `AntScope2` C · `ardop` R · `arduino` M · `atlc` C ·
`backdrops` X · `browser` X · `chirp` C · `claws-mail` ? · `Coil64` C ·
`country_files` ? · `cqrlog` C · `cwwav` C · `direwolf` C · `dream` R ·
`dump1090` S · `ebook2cwgui` C · `ESPHamClock` S · `flaa` C · `flamp` C ·
`flcluster` C · `fldigi` C · `fllog` C · `Fl_MoxGen` C · `flmsg` C · `flnet` C ·
`flrig` C · `flwkey` C · `flwrap` C · `FoxTelem` ? · `freedv` C · `fritzing` M ·
`glfer` C · `gnuradio` C · `gpredict` C · `gpsman` S · `gqrx` C ·
`GridTracker2` C · `grig` S · `gsmc` C · `gspiceui` M · `hamclock_next` R ·
`ibp` R · `js8call` C · `js8spotter` C · `jtdx` ? · `kicad` M · `klog` C ·
`libhamlib4` ? · `linpac` C · `linrad` C · `mfc_gpl` X · `morse_runner` M ·
`MSHV` C · `mvoice` R · `nanovna-saver` C · `ngspice` M · `noaa-apt` X ·
`not1mm` C · `notepadqq` X · `owx` S · `pipx` C · `putty` ? · `pyautogui` X ·
`qgrid` C · `QLog` C · `qrq` C · `qsstv` C · `qtel` C · `QtTinySA` C ·
`quisk` C · `radiosonde_auto_rx` R · `rf_exposure_calc` ? · `rtl_sdr_v4` S ·
`SatDump` C · `SDR++` C · `solar_data` ? · `source_libs` S · `splat` C ·
`sunclock` C · `svxlink` C · `svxreflector` C · `tkcvs` X · `tqsl` C ·
`tt3_gpl` X · `virtual_radar_server` S · `wfview` C · `wine` ? · `wordsworth` C ·
`wsjtx` C · `wsjtx_improved` C · `wwl` C · `xastir` C · `xcwcp` C · `xdx` C ·
`xlog` C · `xnec2c` C · `xosview` X · `xwefax` ? · `xwxapt` X · `yaac` C

**73Linux delta (28):**

`ARDOPGUI` C · `AX25` A · `BATT` X · `BPQ` A · `CONKY` X · `DIPOLE` X · `EES` X ·
`GARIM` A · `GPS` C · `GPSUPDATE` X · `GRIDCALC` X · `HAMRS` A · `M0IAX` ? ·
`PAT` A · `PATMENU` X · `PATMENU3` ? · `PIAPRS` A · `PIQSO` X · `PISTATS` X ·
`PITERM` A · `QTSOUND` A · `REPEAT` ? · `SECURITY` X · `SHOWLOG` X · `VARA` A ·
`VARIM` A · `VNC` X · `XYGRIB` A

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
