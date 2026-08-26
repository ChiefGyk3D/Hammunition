# AHRL v27 Software Inventory

Extracted from Andy's Ham Radio Linux v27 (May 2026), by Andy Stewart (KB1OIQ),
distributed as `andy_v27.tar.gz` on SourceForge.

**Source of truth for this document:** the extracted tree in `reference/`
(`bin/install_ahrl`, 3911 lines; `share/desktop-directories/install_it`;
`share/applications/*.desktop`; `share/doc/Andy_Ham_Radio_Linux/*`;
`tarballs/`, 63 files, 779 MB).

This is an M2 measurement artifact. It records what AHRL v27 does, not what
Hammunition will do. No schema decisions are made here.

---

## Summary

AHRL v27 exposes **105 `INSTALL_<NAME>` toggles** in `install_ahrl`. Each toggle
maps to one `install_<name>()` shell function. That is the unit of installation
in AHRL, and it is the unit counted below.

| | Count |
|---|---:|
| `INSTALL_*` toggles defined | 105 |
| Enabled (`=1`) by default | 96 |
| Disabled (`=0`) by default | 9 |
| Enabled but never called from the main body (dead code) | 1 |
| **Units that actually execute on a default run** | **95** |
| Of those, AHRL infrastructure, wallpaper, dev tooling, or web bookmarks | 7 |
| **Distinct pieces of ham/SDR software and data installed** | **88** |

The last figure is 95 executing units minus 3 AHRL infrastructure units
(`ahrl_menus`, `ahrl_docs`, `ahrl_version`), 1 wallpaper archive, 1 developer-only
test harness (PyAutoGUI), and 2 units that are only web-bookmark launchers.

Additionally, **6 menu entries reference software or services that no install
function provides** (5 web bookmarks and 1 documentation-only entry), and
**63 upstream archives** ship inside the tarball at `/usr/local/tarballs`.

### Breakdown by install method

Counted over the 95 executing units. Where a unit uses more than one mechanism,
it is counted under its *primary* method — the one that puts the user-facing
program on the system. Build-time `apt` dependencies do not make a source build
count as apt.

| Method | Count | Notes |
|---|---:|---|
| apt (repository package is the deliverable) | 38 | Includes one conditional (js8call on Linux Mint 22.3) |
| Source build from bundled tarball | 35 | `./configure`, `cmake`, or `qmake` |
| Source build from network `git clone` | 1 | RTL-SDR Blog V4 driver |
| Prebuilt binary or data archive, bundled | 9 | `.deb`, Java `.jar`, Windows `.exe`, Mono, Perl scripts, data |
| Python venv or pipx | 4 | Three per-user venvs, one pipx |
| Python source run in place (no install step) | 2 | js8spotter, QtTinySA |
| Remote script piped into a shell | 1 | AIS-catcher |
| Generated launcher script only (no software) | 2 | RF exposure calculator, solar data |
| AHRL infrastructure (menus, docs, version) | 3 | |
| **Total** | **95** | |

### Cross-cutting mechanisms

Beyond the per-package methods, AHRL v27 performs these system modifications:

- **Third-party APT repository (conditional):** `mozillateam/ppa` is added via
  `add-apt-repository`, with an APT pin written to
  `/etc/apt/preferences.d/mozilla-firefox`, but **only** when snapd is detected.
  No signing key is pinned by AHRL itself.
- **Foreign architecture:** `dpkg --add-architecture i386` for Wine (x86_64 only).
- **udev rules:** `rigexpert-usb.rules` → `/usr/lib/udev/rules.d/` (AntScope2);
  `rtl-sdr.rules` → `/etc/udev/rules.d/` (RTL-SDR Blog driver).
- **Kernel module blacklist:** `blacklist dvb_usb_rtl28xxu` written to
  `/etc/modprobe.d/blacklist-dvb_usb_rtl28xxu.conf`.
- **Group membership:** the named default user is added to `adm`, `sudo`,
  `lpadmin`, `dip`, `plugdev`, `netdev`, `cdrom`, `dialout`, `xastir-ax25`,
  `svxlink`. `install_svxlink` and `install_xastir` are deliberately run *before*
  `get_username` because they create the last two groups.
- **Package purges:** `brltty` (breaks USB serial adapters) and `xtrx-dkms`
  (purged three separate times — before update, after update, and again after
  gqrx installs, because dependencies keep pulling it back).
- **Library shadowing:** the RTL-SDR Blog V4 driver install `rm -fr`s the distro
  `librtlsdr*`, `rtl-sdr*` headers and `rtl_*` binaries from both `/usr` and
  `/usr/local`, then hand-creates `.so` symlinks in `/usr/lib/$(arch)-linux-gnu`.
  This is deliberate (V4 dongles need it) and destructive.
- **Repository packages purged before source install:** `fldigi`, `flrig`,
  `quisk`, `wfview`, `wsjtx` are `apt purge`d so the source build wins.
- **Runtime package-name resolution:** four names are resolved at runtime by
  probing `apt-cache`, because they differ across targets (see
  [Per-distro package-name variants](#per-distro-package-name-variants)).

### Not apt-installable — the list that matters

**57 of the 95 executing units cannot be satisfied by `apt` alone.** This is the
measurement that drives M3 backend scope.

Grouped by the backend each would require:

**Source build — bundled tarball (35).** These need a source backend with
per-package build recipes (`configure`/`cmake`/`qmake`), a build-dependency
list, and patch application for four of them.

`aa-analyzer`, `Coil64`, `cwwav`, `direwolf`, `dump1090` (FlightAware),
`ESPHamClock`, `flaa`, `flcluster`, `fldigi`, `fllog`, `Fl_MoxGen`, `flnet`,
`flrig`, `flwkey`, `freedv-gui`, `glfer`, `gpredict`, `gqrx`, `gsmc`,
`gspiceui`, `js8call` (JS8Call-improved), `linrad`, `MSHV`, `owx` (Open Wouxun),
`qgrid`, `QLog`, `quisk`, `SatDump`, `SDR++`, `tqsl`, `wfview`, `wsjtx`,
`wsjtx-improved`, `xlog`, `xnec2c`, `xwefax`.

*(36 names, 35 counted. `js8call` is listed here because it is a source build on
every target except Linux Mint 22.3, but it is counted under apt in the totals.)*

**Source build — network clone (1).** `rtl-sdr-blog` V4 driver, `git clone`d at
install time from GitHub. No pinned revision, no signature.

**Prebuilt binaries and data archives (9).** Need a `.deb` backend, a Java-wrapper
pattern, a Wine-wrapper pattern, and a plain-archive-plus-launcher pattern.

`antscope2` (vendor `.deb`, x86_64 only), `GridTracker2` (vendor `.deb`,
arch-specific), `FoxTelem` (Java jar + generated launcher), `YAAC` (Java jar +
generated launcher), `Morse Runner` (Windows `.exe` under Wine, x86_64 only),
`Virtual Radar Server` (Mono `.exe` + config patch tarball), `wordsworth`
(Perl scripts copied from a tarball), `backdrops` (wallpaper archive), and
`cty.dat` country files (data archive fanned out to six directories).

**Python (6 executing, plus 1 disabled).** Four distinct patterns, no two alike:

| Software | Pattern |
|---|---|
| `chirp` | `pipx install --system-site-packages` from a bundled `.whl` |
| `nanovna-saver` | per-user venv + `git clone` + `pip install .` |
| `not1mm` | per-user venv + `pip install not1mm` from PyPI |
| `pyautogui` | per-user venv + `pip install` (AHRL developer tooling only) |
| `js8spotter` | source zip unpacked into `$HOME`, run in place |
| `QtTinySA` | source zip unpacked to `/usr/local/src`, run in place |
| `radiosonde_auto_rx` | *(disabled)* venv + `pip install -r requirements.txt` |

**Remote script (1).** `AIS-catcher` — installed by piping a downloaded script
straight into `bash`. See [Security-relevant findings](#security-relevant-findings).

**Generated launchers (2).** `rf_exposure_calc` and `solar_data` are not software
at all — they are two-line shell scripts that open a URL or `wget` a GIF.

**AHRL infrastructure (3).** `ahrl_docs`, `ahrl_menus`, `ahrl_version` —
Hammunition equivalents, not ports.

---

## Menu categories

AHRL's menu is built by `share/desktop-directories/install_it`, which calls
`xdg-desktop-menu install` once per category under a top-level
`Andy_Ham_Radio_Linux` directory. These are the closest thing AHRL has to
profiles, and they are **overlapping, not partitioning** — `direwolf`,
`fldigi`, `flamp`, `flmsg`, `gnuradio`, `gpredict`, `satdump`, `sdrpp`,
`arduino`, `chirp`, `AIS-catcher`, `yaac`, `virtual_radar_server` and
`xastir` each appear in two or three categories.

| Category | Entries | Purpose |
|---|---:|---|
| ARRL_Teachers_Institute | 12 | Cross-cutting educational bundle; deliberately duplicates entries from other categories |
| Antenna | 5 | Analyzers, modelling, RF exposure |
| CW | 5 | Morse practice, keyers, ebook conversion |
| Digital_Modes | 20 | FT8/JS8/PSK31/SSTV/WEFAX/FreeDV/Echolink. 17 unique — `flamp`, `fldigi` and `flmsg` are each listed twice in `install_it`. |
| Documentation | 5 | HTML/PDF doc launchers |
| Documentation → Command_Line_Docs | 12 | `man`-page and HOWTO launchers for CLI-only tools |
| Electronic_Design | 10 | EDA, SPICE, VNA, Smith chart |
| HF_Propagation | 15 | Clocks, cluster, propagation web services, grid tools |
| Logging | 8 | QSO loggers and LoTW |
| NBEMS | 4 | Emergency-comms subset (fldigi/flmsg/flamp + mail client) |
| Rig_Control | 4 | CAT control and radio programming |
| Satellites | 3 | Tracking and telemetry |
| SDR | 6 | SDR receivers and cleanup helper |
| Tracking | 4 | APRS, AIS, ADS-B |
| Workarounds | 1 | `fix_sound` |

Two category files ship but are **never installed**: `M17.directory` and
`Miscellaneous.directory`. M17 is orphaned because both M17 programs
(`droidstar`, `mvoice`) were removed in v26e and v27 respectively.

---

## Per-distro package-name variants

`install_ahrl` resolves four package names at runtime by probing the package
database, plus one by `apt-cache search` regex. This is AHRL's entire mechanism
for cross-distro variance and is worth reading closely.

```
package_name "CHROMIUM"        "chromium"                     "chromium-browser"
package_name "LIBOSMOSDR"      "libgnuradio-osmosdr0.2.0t64"  "libgnuradio-osmosdr0.2.0"
package_name "LIBVOLK"         "libvolk-dev"                  "libvolk2-dev"
package_name "USR_BIN_DISPLAY" "imagemagick-7.q16"            "graphicsmagick-imagemagick-compat"

LIBWXGTK_DEV=`apt-cache search libwxgtk | grep dev | grep -v media | grep -v webview | awk '{print $1}'`
```

`package_name()` tries the first candidate, falls back to the second, and prints
`AHRL: ERROR: no suitable package for X exists` if neither is present — then
continues anyway with an empty variable.

---

## Conditional logic

Everything in `install_ahrl` that is not unconditional.

### Architecture (`$(arch)`)

`check_arch()` accepts only `x86_64` and `aarch64` and exits otherwise.

| Software | Behaviour |
|---|---|
| `antscope2` | **x86_64 only.** On aarch64 prints "cannot run antscope2 on Raspberry Pi - sorry." The source-build attempt is commented out in place. |
| `morse_runner` | **x86_64 only.** Depends on Wine. |
| `wine` | **x86_64 only.** aarch64 skipped entirely. |
| `not1mm` | Installed everywhere, but its `.desktop` file is deleted on aarch64 after menu install |
| `GridTracker2` | Arch-specific `.deb`: `-arm64.deb` vs `-amd64.deb` |
| `MSHV` | Arch-specific qmake project: `MSHV_ARM_PI.pro` vs `MSHV_x86_64.pro`; the generated launcher differs to match |
| `noaa-apt` *(disabled)* | Arch-specific prebuilt zip |
| `rtl-sdr-blog` driver | Library paths use `$(arch)-linux-gnu` |
| `gspiceui` | Hardcodes an **aarch64-only** wx setup.h symlink path (see Known defects) |
| WSJT-X Wayland warning | Post-install advice printed only on aarch64 |

### Distribution

| Software | Behaviour |
|---|---|
| `js8call` | On Linux Mint 22.3, installs apt `js8call` because Mint ships Qt 6.4.2 and JS8Call 2.5.2 needs Qt 6.5. Everywhere else, builds JS8Call-improved 2.5.2 from source. **The detection is broken** — see Known defects. |
| `firefox` | Three-way branch: snapd present → add mozillateam PPA, pin, `snap remove firefox`, install deb; snapd absent and only `firefox-esr` available (Debian) → install `firefox-esr`; otherwise → install `firefox` |
| `chromium` | Name resolved at runtime (`chromium` vs `chromium-browser`) |

### Hardware / environment

| Check | Effect |
|---|---|
| `check_root` | Must run as root, else exit |
| `check_storage` | Requires ~18 GB free on `/`, else exit (docs say 10 GB on Pi, 25–30 GB on x86_64 — the script and the docs disagree) |
| `check_memory` | <2 GB exit; <4 GB warn and continue |
| `check_network` | `nslookup www.google.com`; installs `bind9-dnsutils` if missing; exits if DNS fails |
| `NUM_CPUS` | Defaults to 1. User edits by hand for parallel `make`. |

---

## Full inventory

Ordered as the main body of `install_ahrl` executes them, numbered 1–95 to match
the 95 units that actually execute. `hamclock_next` is deliberately absent — it is
enabled but never called (see [Known defects](#known-defects-in-ahrl-v27)).
"Method" is the primary mechanism; build dependencies are listed separately where
they matter.

### Phase 1 — prerequisites (installed first because others depend on them)

| # | Software | Method | apt package(s) | Non-apt source / build | Menu category | Conditional |
|---:|---|---|---|---|---|---|
| 1 | Firefox (browser) | apt (+PPA) | `firefox` \| `firefox-esr` \| `software-properties-common` | mozillateam PPA when snapd present | — | Three-way distro branch; `$BROWSER` is never assigned (see defects) |
| 2 | libhamlib4 | apt | `libhamlib4` | — | — | — |
| 3 | pipx | apt | `pipx` | — | — | — |
| 4 | Source build toolchain | apt | `build-essential`, `libncurses-dev`, `libqt5multimediawidgets5`, `libqt5widgets5`, `qtbase5-dev`, `qt5-qmake`, `cmake`, `unzip`, `wget`, `git`, `autoconf`, `automake`, `libtool` | — | — | — |
| 5 | Wine | apt | `wine32:i386`, `winbind` | `dpkg --add-architecture i386` | — | x86_64 only |
| 6 | RTL-SDR Blog V4 driver | source (git clone) | build deps: `libusb-1.0-0-dev`, `git`, `cmake`, `pkg-config` | `git clone https://github.com/rtlsdrblog/rtl-sdr-blog`, cmake `-DINSTALL_UDEV_RULES=ON` | — | Purges distro librtlsdr; installs udev rules; blacklists `dvb_usb_rtl28xxu` |
| 7 | SvxLink | apt | `svxlink-server` | — | Digital_Modes (`qtel`) | Run early — creates the `svxlink` group |
| 8 | Xastir | apt | `xastir` | — | Tracking, Documentation | Run early — creates the `xastir-ax25` group; `chmod o+x /usr/bin/xastir` |
| 9 | dump1090 | source (tarball) | build dep: `librtlsdr-dev` | `dump1090-master.zip` (FlightAware), `make` with a long explicit `DUMP1090_CFLAGS` | ARRL_Teachers_Institute, Command_Line_Docs | Run early — prompts the user |

### Phase 2 — apt-only installs

`atril` is also installed from apt, but by `install_ahrl_docs` as `$PDF_VIEWER`
rather than by a toggle of its own; it appears under Phase 8.

| # | Software | apt package(s) | Menu category | Notes |
|---:|---|---|---|---|
| 10 | Arduino IDE | `arduino` | ARRL_Teachers_Institute, Electronic_Design | |
| 11 | atlc | `atlc` | Command_Line_Docs | Transmission-line calculator; CLI + man page only |
| 12 | Claws Mail | `claws-mail` | NBEMS | Added in v27, replaced sylpheed |
| 13 | CQRLOG | `cqrlog` | Logging | |
| 14 | ebook2cwgui | `ebook2cwgui` | CW | |
| 15 | FLAMP | `flamp` | Digital_Modes, NBEMS | The only W1HKJ "fl" app taken from apt rather than source |
| 16 | FLMSG | `flmsg` | Digital_Modes, NBEMS | Also apt rather than source |
| 17 | FLWRAP | `flwrap` | Digital_Modes | Also apt rather than source |
| 18 | Fritzing | `fritzing` | Electronic_Design | |
| 19 | GNU Radio | `gnuradio` | ARRL_Teachers_Institute, SDR | |
| 20 | gpsman | `gpsman` | Command_Line_Docs | |
| 21 | grig | `grig` | Rig_Control | |
| 22 | JTDX | `jtdx` | Digital_Modes | From repo since v26a; previously a `.deb` |
| 23 | KiCad | `kicad` | Electronic_Design | Provides gerbview + pcbnew menu entries |
| 24 | KLog | `klog` | Logging | |
| 25 | LinPac | `libax25`, `linpac` | Command_Line_Docs | |
| 26 | ngspice | `ngspice` | Command_Line_Docs | |
| 27 | Notepadqq | `notepadqq` | ARRL_Teachers_Institute | |
| 28 | PuTTY | `putty` | ARRL_Teachers_Institute | |
| 29 | qrq | `qrq` | CW, Command_Line_Docs | |
| 30 | QSSTV | `qsstv` | Digital_Modes | |
| 31 | Qtel | `qtel` | Digital_Modes | Echolink client; part of svxlink |
| 32 | SPLAT! | `splat` | Command_Line_Docs | |
| 33 | Sunclock | `sunclock` | HF_Propagation | |
| 34 | SvxReflector | `svxreflector` | — | No menu entry |
| 35 | TkCVS | `tkcvs` | — | No menu entry |
| 36 | wwl | `wwl` | Command_Line_Docs | |
| 37 | xcwcp | `xcwcp` | CW | Part of unixcw |
| 38 | Xdx | `xdx` | HF_Propagation | |
| 39 | xosview | `xosview` | — | No menu entry |

### Phase 3 — source builds from bundled tarballs

All build in `/usr/local/src`, from archives in `/usr/local/tarballs`. Previous
build directories are moved to `/usr/local/src/delete_me` and removed at the end.

| # | Software | Bundled archive | Build | apt build deps | Menu category | Notes |
|---:|---|---|---|---|---|---|
| 40 | aa-analyzer 0.09 | `aa-analyzer-0.09.tar.gz` | `./install_it` (vendor script) | — | Command_Line_Docs | **Also installs a CPAN module**: `cpan install Device/SerialPort.pm` with `PERL_MM_USE_DEFAULT=1`. The only CPAN use in AHRL. |
| 41 | Coil64 2.4.39 | `Coil64-2.4.39.tar.gz` | `qmake` + `make` | — | Electronic_Design | |
| 42 | cwwav | `cwwav-master.zip` | `make install` | `libsndfile1-dev` | Command_Line_Docs | Unversioned `master` snapshot |
| 43 | Dire Wolf 1.8.1 | `direwolf-1.8.1.tar.gz` | `cmake` + `make install` + `make install-conf` | `libhamlib-dev`, `libgpiod-dev`, `libavahi-common-dev`, `libavahi-client-dev`, `libgps-dev`, `libasound2-dev`, `libudev-dev` | ARRL_Teachers_Institute, Digital_Modes | Copies `direwolf.conf` into the user's home |
| 44 | ESPHamClock 4.23 | `ESPHamClock-V4.23.zip` | `make` **four times** | `curl` | HF_Propagation | Produces four binaries — 800x480, 1600x960, 2400x1440, 3200x1920 — one menu entry each |
| 45 | flaa 1.0.2 | `flaa-1.0.2.tar.gz` | `./configure` + `make install` | `libfltk1.3-dev` | Antenna | |
| 46 | flcluster 1.1.01 | `flcluster-1.1.01.tar.gz` | `./configure` + `make install` | `libpng-dev`, `libxft-dev`, `libfltk1.3-dev` | HF_Propagation | |
| 47 | fldigi 4.2.11 | `fldigi-4.2.11.tar.gz` | `./configure` + `make install` | `libportaudio2`, `libportaudiocpp0`, `libportaudio-ocaml-dev`, `libudev-dev` | Digital_Modes, NBEMS | **`apt purge fldigi` first.** Also provides `flarq`, which gets its own menu entry with no install function of its own. |
| 48 | fllog 1.2.9 | `fllog-1.2.9.tar.gz` | `./configure` + `make install` | `libfltk1.3-dev` | Logging | |
| 49 | Fl_MoxGen 1.01 | `Fl_MoxGen-1.01.tar.gz` | `make install` | `libfltk1.3-dev`, `libhpdf-dev` | Antenna | |
| 50 | flnet 7.5.0 | `flnet-7.5.0.tar.gz` | `./configure` + `make install` | `libsamplerate0-dev` | Logging | |
| 51 | flrig 2.0.10 | `flrig-2.0.10.tar.gz` | `./configure` + `make install` | — | Rig_Control | **`apt purge flrig` first** |
| 52 | flwkey 1.2.4 | `flwkey-1.2.4.tar.gz` | `./configure` + `make install` | — | CW | |
| 53 | FreeDV GUI 2.2.1 | `freedv-gui-2.2.1.tar.gz` | `./build_linux.sh` (vendor script) | `$LIBWXGTK_DEV`, `libspeexdsp-dev`, `libsamplerate0-dev`, `libasound2-dev`, `libao-dev`, `libgsm1-dev`, `python3-dev`, `python3-numpy`, `libpulse-dev`, `libsndfile1-dev`, `sox` | Digital_Modes | |
| 54 | glfer 0.4.2 | `glfer-0.4.2.tar.gz` | `./configure` + `make install` | `libgtk2.0-dev`, `libglib2.0-dev`, `libgdk-pixbuf-2.0-dev`, `fftw2` | Digital_Modes | Needs `-Wno-incompatible-pointer-types -Wno-deprecated-declarations -Wno-implicit-function-declaration` to compile at all |
| 55 | Gpredict 2.5.1 | `gpredict-2.5.1.tar.bz2` | `./configure` + `make install` | `intltool`, `libcurl4-openssl-dev`, `libgtk-3-dev` | ARRL_Teachers_Institute, Satellites | |
| 56 | Gqrx 2.17.7 | `gqrx-2.17.7.tar.gz` | `cmake` + `make install` | `$LIBOSMOSDR`, `libqt5svg5-dev` | SDR | Calls `purge_xtrx_dkms` afterwards |
| 57 | gsmc | `gsmc-master.zip` | `./configure` + patched `make install` | `libgdk-pixbuf-2.0-dev` | Electronic_Design (as "Smith_Chart") | Patches the Makefile in place to add `-Wno-incompatible-pointer-types`. Unversioned `master` snapshot. |
| 58 | GSpiceUI 1.2.87 | `gspiceui-v1.2.87.tar.gz` | patched `make install` | `$LIBWXGTK_DEV`, `libgtk-3-dev`, `libgtkmm-3.0-dev`, `wx3.2-headers` | Electronic_Design | Creates two `/usr/include` symlinks and rewrites `src/Makefile` 3.0→3.2. One symlink path is aarch64-only. |
| 59 | JS8Call-improved 2.5.2 | `JS8Call-improved-release-2.5.2.tar.gz` | `cmake` + `make` | `qt6-multimedia-dev`, `qt6-serialport-dev` | Digital_Modes | **apt `js8call` instead on Linux Mint 22.3** (Qt version floor) |
| 60 | Linrad 05-02 | `lir05-02.zip` | `./configure` + `make xlinrad64` | `nasm` | SDR | Needs `-Wno-stringop-truncation` |
| 61 | MSHV 2.76.5 | `MSHV_2765_Full_Source_Code.zip` | `qmake` + `make` | `libqt5websockets5-dev`, `libasound2-dev` | Digital_Modes | Arch-specific `.pro` file; generated launcher must `cd` into the build dir |
| 62 | Open Wouxun (owx) | `owx-20220525.tar.gz` | `make install` | — | — | Date-stamped 2022; no menu entry |
| 63 | qgrid 3.2 | `qgrid_3_2.tgz` | `qmake` + `make install` | `libqt5widgets5`, `libqt5multimediawidgets5` | HF_Propagation | |
| 64 | QLog 0.49.1 | `QLog-0.49.1.zip` | `qmake` + `make install` | `qtbase5-dev`, `qtchooser`, `qt5-qmake`, `qtbase5-dev-tools`, `libsqlite3-dev`, `libhamlib++-dev`, `libqt5charts5-dev`, `qttools5-dev-tools`, `libqt5keychain1`, `qt5keychain-dev`, `qtwebengine5-dev`, `build-essential`, `libqt5serialport5-dev`, `pkg-config`, `libqt5websockets5-dev` | Logging | Heaviest build-dependency list in AHRL |
| 65 | QUISK 4.2.50 | `quisk-4.2.50.tar.gz` | `make` + generated launcher | `python3-setuptools` | SDR | **`apt purge quisk` first.** Runs from `/usr/local/src`, not installed into a prefix. |
| 66 | SatDump | `SatDump-master.zip` | `cmake -DCMAKE_BUILD_TYPE=Release` + `make install` | `g++`, `pkgconf`, `libfftw3-dev`, `libpng-dev`, `libtiff-dev`, `libjemalloc-dev`, `$LIBVOLK`, `libnng-dev`, `libhackrf-dev`, `libairspy-dev`, `libairspyhf-dev`, `libglfw3-dev`, `zenity`, `libzstd-dev`, `libomp-dev`, `ocl-icd-opencl-dev`, `libhdf5-dev` | ARRL_Teachers_Institute, Satellites | Unversioned `master` snapshot. A pinned `SatDump-1.2.2.zip` also ships but is unused. |
| 67 | SDR++ | `SDRPlusPlus-master.zip` | `cmake -DCMAKE_POLICY_VERSION_MINIMUM=3.5` + `make install` | `libfftw3-dev`, `libglfw3-dev`, `$LIBVOLK`, `libzstd-dev`, `libairspy-dev`, `libairspyhf-dev`, `librtaudio-dev`, `libhackrf-dev`, `libiio-dev`, `libad9361-dev`, `libsoapysdr-dev` | ARRL_Teachers_Institute, SDR | Unversioned `master` snapshot |
| 68 | TQSL 2.8.4 | `tqsl-2.8.4.tar.gz` | `cmake .` + `make install` + `ldconfig` | `openssl`, `libssl-dev`, `expat`, `zlib1g-dev`, `libsqlite3-dev`, `libcurlpp-dev`, `$LIBWXGTK_DEV` | Logging | ARRL Logbook of the World |
| 69 | wfview 2.11 | `wfview-v2.11.tar.gz` | `qmake` + `make install` | `libqt5gamepad5-dev`, `libqt5serialport5`, `libqt5serialport5-dev`, `qtmultimedia5-dev`, `libqcustomplot-dev`, `libqcustomplot2.1`, `libhidapi-dev` | Rig_Control | **`apt purge wfview` first** |
| 70 | WSJT-X 3.0.0 | `wsjtx-3.0.0.tar.gz` | `cmake` + `cmake --build --target install` | `gfortran`, `libboost-all-dev`, `qttools5-dev-tools`, `qttools5-dev`, `qtmultimedia5-dev`, `libqt5serialport5`, `libqt5serialport5-dev`, `libfftw3-dev`, `libreadline-dev`, `libusb-1.0-0-dev`, `libudev-dev` | Digital_Modes | **`apt purge wsjtx` first.** Binary renamed to `wsjtx_orig`, then renamed back after wsjtx-improved installs. |
| 71 | WSJT-X improved 3.1.0 | `wsjtx-3.1.0_improved_PLUS_260418.tgz` | `cmake` + `cmake --build --target install` | same as WSJT-X | Digital_Modes | **Ordering-coupled to #71**: installs over `wsjtx`, renames it to `wsjtx_improved`, then restores `wsjtx_orig` → `wsjtx`. Both must run, in order, or one binary is wrong. |
| 72 | xlog 2.0.25 | `xlog-2.0.25.tar.gz` | `./configure` + `make install` | `libhamlib-dev` | Logging | Source because 2.0.25 postdates the repo's 2.0.24. Needs six `-Wno-*` flags. |
| 73 | xnec2c 4.4.18 | `xnec2c-4.4.18.zip` | `./autogen.sh` + `./configure` + `make install` | — | Antenna | |
| 74 | xwefax 2.4.4 | `xwefax-2.4.4.tar.bz2` | `./configure` + `make install` | `libgtk-3-dev` | Digital_Modes | |

### Phase 4 — prebuilt binaries and data archives

| # | Software | Method | Bundled archive | Menu category | Notes |
|---:|---|---|---|---|---|
| 75 | AntScope2 1.4.15 | vendor `.deb` | `antscope2_1.4.15_ubuntu.deb` | Antenna | **x86_64 only.** Also installs `rigexpert-usb.rules` to `/usr/lib/udev/rules.d/`. The aarch64 source build is commented out, having failed. |
| 76 | GridTracker2 2.260421.1 | vendor `.deb` | `GridTracker2-…-amd64.deb` / `-arm64.deb` | Digital_Modes | 112 MB / 107 MB — the two largest files in the tarball |
| 77 | FoxTelem 1.12z3 | Java jar + generated launcher | `FoxTelem_1.12z3_linux.tar.gz` | Satellites | Launcher runs `java -Xmx512M -jar ./FoxTelem.jar` from the src dir. **No JRE dependency is declared** (relies on YAAC's). |
| 78 | YAAC | Java jar + generated launcher | `YAAC.zip` | ARRL_Teachers_Institute, Tracking | apt: `default-jre-headless`, `libjssc-java` |
| 79 | Morse Runner 1.85.3 | Windows `.exe` under Wine | `Morse.Runner.1.85.3.zip` | CW | **x86_64 only.** Launcher copies the app into `$HOME` on first run, refuses to run as root, then `wine ./MorseRunner.exe`. |
| 80 | Wordsworth 0.3 | Perl scripts from tarball | `wordsworth_0.3.tar.gz` | — | Copies `text_to_cw.pl` and `gen_cw_words.pl` into `/usr/local/bin`. No compilation, no menu entry, no man page — CLI only. Upstream is Andy's own SourceForge project. |
| 81 | Virtual Radar Server | Mono `.exe` + config patch | `VirtualRadar.tar.gz` + `VirtualRadar.exe.config.tar` | ARRL_Teachers_Institute, Tracking | apt: `mono-complete`. Second tarball is a runtime-error patch. Launcher starts `dump1090 --net`, opens a browser, then kills dump1090 on exit. |
| 82 | Backdrops | data archive | `backdrops.tar.gz` | — | 20 MB of wallpapers to `/usr/local/share/ahrl/backdrops` |
| 83 | Country files (cty.dat) | data archive | `cty-3616.zip` | — | Copied into **six** directories: `/usr/share/hamradio-files`, `/usr/share/jtdx`, `/usr/share/wsjtx`, `/usr/share/xdx`, `/usr/share/xlog`, `/usr/local/share/xlog/dxcc`. Runs last so nothing overwrites it. |

### Phase 5 — Python

| # | Software | Method | Source | Menu category | Notes |
|---:|---|---|---|---|---|
| 84 | CHIRP 20260501 | pipx | bundled `chirp-20260501-py3-none-any.whl` | ARRL_Teachers_Institute, Rig_Control | `pipx install --force --system-site-packages` run as the user via `pkexec`; apt `python3-wxgtk4.0`. Generates `run_chirp` wrapper because pipx installs to `$HOME/.local/bin`. |
| 85 | NanoVNA-Saver | venv + git clone + pip | `git clone https://github.com/NanoVNA-Saver/nanovna-saver` at install time | Electronic_Design | apt `libxcb-cursor0`. Creates `$HOME/.venv_nanovna_saver`. **No pinned revision.** Removed in v26e, re-added in v27. |
| 86 | not1mm | venv + PyPI | `pip install not1mm` | Logging | apt `libxcb-cursor0`. Creates `$HOME/.venv_not1mm`. **No pinned version.** `.desktop` removed on aarch64. |
| 87 | js8spotter 1.18 | source zip, run in place | `js8spotter-118_src.zip` | Digital_Modes (menu installed per-user) | apt `python3-tk`, `python3-tksnack`, `python3-pil`, `python3-pil.imagetk`. Unpacked into `$HOME`; AHRL generates the `.desktop` file line by line and installs it via a second generated script. Andy's own comment on the pattern: "this is fugly ...". |
| 88 | QtTinySA 1.2.2 | source zip, run in place | `QtTinySA-1.2.2.zip` | Electronic_Design | apt `python3-pyqt5.qtsql`, `python3-platformdirs`, `python3-serial`. Generated `run_qttinysa` wrapper `cd`s into the src dir. |
| 89 | PyAutoGUI | venv + PyPI | `pip install pyautogui`, `pip install psutil` | — | **AHRL developer tooling, not ham software.** Builds `$HOME/.venv_pyautogui` and installs `test_menus.py` for menu regression testing. apt `python3-tk`, `python3-dev`, `scrot`. |

### Phase 6 — remote script

| # | Software | Method | Menu category | Notes |
|---:|---|---|---|---|
| 90 | AIS-catcher | **remote script piped to bash** | ARRL_Teachers_Institute, Tracking | `bash -c "$(wget -qO- https://raw.githubusercontent.com/jvde-github/AIS-catcher/main/scripts/aiscatcher-install)"`. apt build deps: `curl`, `libsoxr-dev`, `libsamplerate0-dev`. Ships `start_AIS-catcher` which runs it on port 8100 and opens a browser. |

### Phase 7 — generated launchers (no software installed)

| # | Name | What it actually is | Menu category |
|---:|---|---|---|
| 91 | RF Exposure Calculator | Two-line script opening `http://hintlink.com/power_density.htm` in the browser | Antenna |
| 92 | Solar Data | `wget http://www.hamqsl.com/solar101vhf.php` then `display /tmp/solar.gif`. apt `$USR_BIN_DISPLAY` (ImageMagick or GraphicsMagick compat) | HF_Propagation |

### Phase 8 — AHRL infrastructure

| # | Unit | What it does |
|---:|---|---|
| 93 | `ahrl_docs` | Installs `atril`; regenerates `PACKAGES` from `dpkg-query --list` and `VERSIONS` from the tarball filenames |
| 94 | `ahrl_menus` | Runs `desktop-directories/install_it`; installs the js8spotter menu per-user; deletes 8 obsolete `.desktop` files (`arduinoide`, `gridtracker`, `gwave`, `nanoVNA-saver`, `pota_putter`, `pylogjam`, `sdrangel`, `tinySA-saver`) and 2 more (`noaa-apt`, `xwxapt`); on aarch64 deletes `antscope2`, `morse_runner`, `not1mm` |
| 95 | `ahrl_version` | Generates `/usr/local/bin/version` printing the AHRL version string |

### Disabled in v27 (`INSTALL_*=0`)

Andy's own comments, verbatim where present.

| Software | Method it would use | Why disabled |
|---|---|---|
| ARDOP 1.0.4.1.3 | source (`ardop-1.0.4.1.3.tar.gz`) | *"Removed v27 - compiler error on Xubuntu 26.04 / in function 'client_handler': too many args to function 'process_http_req'"* |
| Dream 2.1.1 | source (`dream-2.1.1-svn808.tar.gz`) | *"no webkitwidgets"* — `libqt5webkit5-dev` is gone from Debian 13. Build needed two in-place `sed` patches even when it worked. |
| ibp 0.21 | source (`ibp-0.21_x.tar.gz`) | *"many, many compiler errors"* |
| mfc_gpl | — | *"use old libserial library version or update the code"*. Function body is a **stub with no code**, only commented tarball names. Docs: *"This program may be considered obsolete."* |
| mvoice | source (`mvoice-main.zip`) | *"no openhdt"* — `libopendht-dev` is gone from Debian 13. M17 support is now entirely absent. |
| noaa-apt 1.4.1 | prebuilt zip | *"All NOAA satellites are out of service. 09-Nov-2025"* |
| radiosonde_auto_rx | venv + git | *"I can't figure out how this is supposed to work. It is another one of the PITA python programs that only installs in the user's home directory and uses a venv. The scripts hardcode 'pi' as the username… No thanks...way too much work. AMS 28-apr-2026"* |
| tt3_gpl | — | *"use old libserial library version or update the code"*. Function body is a **stub with no code**. |
| xwxapt 3.4.3 | source (`xwxapt-3.4.3.tar.bz2`) | *"All NOAA satellites are out of service. 09-Nov-2025"* |

### Menu entries with no install function

These appear in AHRL's menus but nothing installs them.

| Entry | Category | What it is |
|---|---|---|
| DXLook | HF_Propagation | Browser bookmark → `http://dxlook.com` |
| HamTab | HF_Propagation | Browser bookmark → `http://hamtab.net` |
| OpenHamClock | HF_Propagation | Browser bookmark → `http://openhamclock.com` |
| PSKReporter | HF_Propagation | Browser bookmark → `https://pskreporter.info/pskmap.html` |
| VOACAP | HF_Propagation | Browser bookmark → `http://www.voacap.com/hf/` |
| acarsdec | Command_Line_Docs | Opens a HOWTO only. The software itself is **not installed** — the HOWTO tells the user to build it by hand. |
| flarq | Digital_Modes | Ships as part of the fldigi source build (#48) |
| HamClock-Next | HF_Propagation | Menu entry exists, install function exists, **install function is never called** |

---

## Known defects in AHRL v27

Found while reading the script. Recorded so we don't reproduce them, and because
several point straight at requirements for our own design.

1. **`install_hamclock_next` is never called.** The function is defined at
   line 1859, `INSTALL_HAMCLOCK_NEXT=1` is set, `hamclock-next.desktop` is
   installed into the HF_Propagation menu, `hamclock-next-1.5.tar.gz` ships in
   the tarball, and the CHANGES file lists "added hamclock-next" as a v27
   feature. The call is simply missing from the main body. Users get a dead
   menu entry. *A generated call list, or a manifest-driven engine, makes this
   class of bug impossible.*

2. **`$BROWSER` is never assigned.** `install_browser` branches on
   `[ "$BROWSER" = "firefox" ]` and otherwise runs `$APT_INSTALL $BROWSER`, but
   no assignment exists anywhere in the script. On a system where the
   environment happens to export `BROWSER` (many desktops do), behaviour depends
   on that value; where it doesn't, the else branch runs `apt install -y` with no
   package name.

3. **The Linux Mint detection is inverted and always false.**
   ```
   IS_LINUX_MINT=`cat /etc/lsb-release | grep LinuxMint | echo $?`
   ```
   `echo $?` reports the exit status of `cat`, not `grep`, and it runs in a
   pipeline where its own stdin is the grep output it never reads. The variable
   is `0` on essentially any system with an `/etc/lsb-release`, and the script's
   own comment acknowledges the confusing polarity. The Mint-specific js8call
   path is therefore unreliable.

4. **`gspiceui` hardcodes an aarch64 library path** on all architectures:
   `ln -s /usr/lib/aarch64-linux-gnu/wx/include/gtk3-unicode-3.2/wx/setup.h …`.
   On x86_64 this creates a dangling symlink. Both `ln -s` calls also fail
   noisily on any re-run, since the script never checks whether the link exists.

5. **`sdr_cleanup` and the shipped `start_virtual_radar_server` still reference
   `dump1090-mutability`,** which v27 replaced with FlightAware `dump1090`.
   `install_virtual_radar_server` overwrites its launcher with a corrected one,
   so that path recovers; `sdr_cleanup` does not, and its menu entry is a no-op.

6. **Idempotency is partial.** Re-running is the documented upgrade path
   ("just install it on top of the old AHRL version"), and most builds handle it
   by moving the old source directory to `delete_me`. But the generated launcher
   scripts are all built with `>>` after an `rm -f`, symlink creation is
   unguarded, `dpkg --add-architecture` and `add-apt-repository` are re-run, and
   the RTL-SDR driver deletes and re-creates system libraries every time.

7. **No verification of anything.** The tarball ships an MD5 checksum on
   SourceForge for the tarball itself, and that is the only integrity check in
   the entire chain. Bundled upstream archives carry no checksums. The three
   network fetches — the AIS-catcher installer, the rtl-sdr-blog clone, the
   nanovna-saver clone — are unpinned and unverified.

8. **Failures do not stop the run.** There is no `set -e` and no exit-status
   checking after any `apt install`, `make`, or `cmake`. A failed build prints
   errors and the script continues to the next program. This is why
   `find_errors_ahrl` exists: it greps a 2.5-hour transcript for error strings
   afterwards. Andy's own comment on it: *"It doesn't identify EVERY error...yet(?)."*

9. **Three unversioned `master` snapshots** ship as if they were releases:
   `SatDump-master.zip`, `SDRPlusPlus-master.zip`, `gsmc-master.zip`,
   `cwwav-master.zip`, `dump1090-master.zip`, `mvoice-main.zip`,
   `AntScope2-master.zip`. The `VERSIONS` file generated at install time derives
   version strings from these filenames, so it reports "SatDump-master" as a
   version. Notably a pinned `SatDump-1.2.2.zip` also ships but is unreferenced.

---

## Security-relevant findings

Recorded against `CLAUDE.md`'s security requirements, which several of these
directly motivate.

| Finding | Location | Our requirement it maps to |
|---|---|---|
| Remote script piped into `bash` | `install_ais_catcher` | "Never pipe remote content into a shell" |
| Unpinned `git clone` at install time, no signature | `install_rtl_sdr_v4_driver`, `install_nanovna_saver` | "Verify checksums/signatures for any non-apt source; refuse to install if absent" |
| Unpinned PyPI install | `install_not1mm` (`pip install not1mm`) | Same |
| Third-party PPA added with no key pinning and no user prompt | `install_browser` (`mozillateam/ppa`) | "Third-party apt repos must be declared… with the signing key pinned" and shown to the user first |
| No checksums on any of the 63 bundled archives | `tarballs/` | Same |
| Whole script runs as root; no privilege drop except `pkexec --user` for four Python installs | throughout | "Drop to user where possible; sudo only for apt/udev" |
| Destructive removal of distro libraries with no record and no undo | `install_rtl_sdr_v4_driver` | Transaction log + `uninstall` |
| No dry-run capability at all | — | "`--dry-run` must be complete and accurate" |

---

## Operational knowledge worth preserving

Hard-won field knowledge from AHRL's docs and script comments. This is the
material `CLAUDE.md` calls out as worth capturing in manifests rather than
rediscovering.

- **Prefer X11 over Wayland.** WSJT-X renders without window borders or
  decorations under Wayland on Raspberry Pi. Documented fix: `raspi-config` →
  Advanced Options → Wayland → "Openbox with X11 backend", then reboot.
- **Purge `brltty`.** It claims USB serial adapters and breaks rig control. AHRL
  purges it unconditionally at the start of every run.
- **Purge `xtrx-dkms`.** Pulled in as a dependency, causes problems, and must be
  purged repeatedly — Andy's comment: *"Purging it over and over again is like
  playing 'whack a mole'."*
- **Reference rigs by `/dev/serial/by-id/…`, never `/dev/ttyUSB0`.** AHRL's
  TROUBLESHOOTING doc is explicit: *"if one hardcodes /dev/ttyUSB0 (for example)
  into wsjt-x, and if that gets mapped to a different device on a different day,
  your ham radio stuff won't work as expected, and that's quite frustrating."*
  This is exactly the problem our persistent udev symlinks solve, and it
  independently confirms that feature's value.
- **`dialout` group membership is mandatory** for any USB-connected rig.
- **The ALSA/PipeWire sound problem.** A "Dummy Output"-only device list is
  common. `alsa force-reload` fixes it on ALSA systems, must be re-run after
  most reboots, and has **no known workaround on PulseAudio/PipeWire**. On Linux
  Mint 22, Andy reports success with `apt purge pipewire && apt install pulseaudio`.
- **Build time and resources.** ~2.5 hours single-CPU on the author's machine;
  1.75 hours on a Pi 5 with `NUM_CPUS=4`. Storage: ~10 GB on Pi, 25–30 GB on
  x86_64 (the script's own check demands 18 GB, disagreeing with both). Memory:
  2 GB is a hard floor, 4 GB workable, 8 GB comfortable.
- **Reboot is required** after install, for group membership to take effect.
- **Only Raspberry Pi 4 and 5 are supported** (including Pi 400 and 500).

---

## Tarball contents

63 files, 779 MB, at `/usr/local/tarballs`. Every one is referenced by
`install_ahrl` except where noted.

| Archive | Used by | Note |
|---|---|---|
| `AntScope2-master.zip` | — | aarch64 build attempt, commented out |
| `SatDump-1.2.2.zip` | — | Superseded by `SatDump-master.zip`, still shipped |
| `rigexpert-usb.rules` | `install_antscope2` | udev rules, not an archive |
| `VirtualRadar.exe.config.tar` | `install_virtual_radar_server` | Runtime patch |
| *(59 others)* | as listed in the inventory above | |

Eight archives correspond to installs that are disabled in v27 and ship anyway:
`ardop-1.0.4.1.3.tar.gz`, `dream-2.1.1-svn808.tar.gz`, `ibp-0.21_x.tar.gz`,
`mvoice-main.zip`, `noaa-apt-1.4.1-aarch64-linux-gnu.zip`,
`noaa-apt-1.4.1-x86_64-linux-gnu.zip`, `xwxapt-3.4.3.tar.bz2`, and
`radiosonde_auto_rx-1.8.2.tar.gz`. Together with `hamclock-next-1.5.tar.gz`
(shipped, buildable, never invoked) that is roughly 90 MB of dead weight.

---

## Upstream sources

AHRL's `00_SOURCES` file lists upstream project URLs for the non-apt software.
It is the authoritative provenance record for the bundled tarballs and should be
consulted directly when writing manifests — it is reproduced in the reference
tree at `reference/share/doc/Andy_Ham_Radio_Linux/00_SOURCES`.

Andy's own framing there is worth quoting, because it is the same principle as
our "upstream packages wherever they exist":

> It is my preference to get files from a repository, as that makes it
> easier for everybody.  However, many things are not available from
> a repository.  Often, the repository verion is quite old.

---

## Provenance

Package names, version numbers, upstream URLs and install mechanisms are facts
about third-party software and are freely usable. This document records those
facts. AHRL's own scripts are GPL-3.0-or-later (see
[Licensing](#licensing) below); no AHRL code is copied here or into Hammunition.

## Licensing

`bin/install_ahrl` and `bin/test_menus_debian13.py` carry a GPL-3.0-or-later
header:

> This program is free software: you can redistribute it and/or modify it under
> the terms of the GNU General Public License as published by the Free Software
> Foundation, either version 3 of the License, or (at your option) any later
> version.

with:

> Copyright 2024, Andy Stewart (KB1OIQ)
> Copyright 2025, Andy Stewart (KB1OIQ)

No `LICENSE` or `COPYING` file ships at the top level of the tarball, and the
remaining AHRL-authored files — the seven helper scripts in `bin/`, all
`.desktop` and `.directory` files, and the documentation under
`share/doc/Andy_Ham_Radio_Linux/` — carry **no license notice at all**.
