# Prior Art and Related Projects

Landscape survey for Hammunition. All dates and licenses verified 2026-09-06 against
primary sources (GitHub, Debian ftp-master changelogs, tracker.debian.org,
blends.debian.org, project sites). Anything not verifiable from a primary source is
marked as such.

Already covered elsewhere in the docs and deliberately not repeated here: Andy's Ham
Radio Linux (AHRL), 73Linux, Skywave Linux, DragonOS, EMCOMM Tools.

Categories:

- **Peer** = same architecture as Hammunition (layer onto an existing install)
- **Upstream** = something Hammunition should depend on rather than reimplement
- **Prior art** = ships its own ISO or image; different architecture, useful lessons
- **Dead** = recorded so nobody spends a weekend rediscovering it

---

## 1. Direct peers: overlays and installers, not ISOs

These are the projects Hammunition is actually competing with and learning from.

### FISSURE (AIS)

`https://github.com/ainfosec/FISSURE` | GPL-3.0 | last push 2026-09-05 | 2,042 stars

The RF reverse-engineering framework from Assured Information Security. Menu-driven
`./install` script with GUI component selection, dependency handling and automated
post-install verification. Covers GNU Radio 3.8 through 3.10, USRP / HackRF / RTL2832U
/ LimeSDR / bladeRF / PlutoSDR / RSPplay, signal detection and classification, protocol
discovery, fuzzing, packet crafting, TAK integration.

**Why this is the single most important entry on the list:** its supported-OS matrix
already includes **Parrot Security 6.1 in beta**, alongside Ubuntu 20.04/22.04/24.04,
Kali, Raspberry Pi OS, DragonOS Noble and Windows 11 WSL2. It is GPL-3.0, so it is
legally reusable. Hammunition should either depend on it for the RF-RE tier, contribute
Parrot 6.x/7.x support to promote it out of beta, or at minimum mirror its OS-detection
logic so the two installers do not fight over the same GNU Radio tree.

### RF Swift (PentHertz)

`https://github.com/PentHertz/RF-Swift` | GPL-3.0 | v3.0.1 2026-08-20 | last push 2026-09-06

Containerized RF and hardware-security toolbox. Go launcher plus pinned Docker tool
stacks, running on Linux, Windows and macOS across x86_64, ARM64 and RISC-V, without
mutating the host. This is the closest thing to a working SIGINT metapackage that
exists, and it is the strongest argument for the "container tier" option in
Hammunition's design: hard-to-package, fast-moving tools go in a container instead of
into apt.

Worth deciding explicitly in DESIGN.md whether Hammunition delegates the volatile RF
security tier to RF Swift rather than building it.

### EmComm Tools OS Community (already known, but two corrections)

`https://github.com/thetechprepper/emcomm-tools-os-community` | last push 2026-09-06 | 144 stars

Two things worth capturing that are easy to get wrong:

- **License is dual and split.** The `LICENSE` file contains an Apache-2.0 grant for the
  software (Copyright 2024 The Tech Prepper LLC), preceded by a separate **Brand Logo
  and Image Notice**: non-commercial only, attribution required, no modification, no
  implied endorsement. So the code is reusable under Apache-2.0; the branding is not.
  Strip assets before borrowing.
- **The `et-radio` / `et-mode` abstraction is the best UX idea in this whole space.** One
  command reconfigures rig, audio routing and digital mode together, across 16
  operational modes (VARA HF/FM, JS8Call, VarAC, YAAC, fldigi, Winlink, Chat, BBS,
  APRS) and 24+ radio models. Apache-2.0 means Hammunition can lift it directly. This is
  the highest-value borrow available.

### LiaisonOS

`https://github.com/LiaisonOS/debian` | `https://liaisonos.com` | Ms-PL | v2.4.2 | last push 2026-09-06

Bilingual FR/EN EMCOMM distro by Sylvain Deguire VA2OPS, a downstream fork of EmComm
Tools Community, **built on Debian 13 Trixie rather than Ubuntu**. Bundles Pat, JS8Call,
VarAC, VARA HF/FM, WSJT-X, fldigi, YAAC, linBPQ, offline Navit maps and offline
Wikipedia.

Architecturally the nearest existing precedent to what Hammunition is doing: Debian
family, EMCOMM focus, layered tooling. It does ship an ISO, so it is not a pure peer,
but its package selection and its Debian-13 dependency resolution work are directly
applicable.

Note the license divergence: LiaisonOS claims Ms-PL over an Apache-2.0 ETC derivative.
Resolve that before copying from either.

### KM4ACK pi-build / Build-a-Pi

`https://github.com/km4ack/pi-build` | **no license file** | deprecated 2024-04-18

Superseded by 73Linux per its own README, but the architecture is documented prior art
worth citing. Driver script plus `functions/` modules (`base.function`,
`flsuite.function`, `additional.function`, `utility.function`), `yad` checklist UI, and
a single state dotfile at `${HOME}/.config/KM4ACK` that makes the script re-run as an
updater. Dispatch works by executing the selected checklist string as a shell function
name.

### 73Linux, licensing correction

`https://github.com/km4ack/73Linux` | **no license file, verified 404** | last push 2026-06-20 | 277 stars

Since the design docs list 73Linux as a possible base, this needs flagging: **73Linux
has no license at all.** `LICENSE`, `LICENSE.md`, `LICENSE.txt` and `COPYING` all return
404, and the GitHub API reports `license: null`. That is all-rights-reserved by default.
Hammunition cannot vendor, fork or copy code from it.

The patterns can still be reimplemented cleanly:

- **`.bapp` plugin model.** Each installable app is a discrete `.bapp` file, globbed by
  architecture (`armv7l|aarch64` vs `x86_64`). Clubs and users can drop community
  `.bapp` files into a community directory and the menu auto-discovers them.
- **`cache/` marker files** for state: `cpu.bap` (hardware probe cache, doubles as
  first-run detection), `MYCALL.${CALLSIGN}` (callsign encoded in the filename),
  `install-path.bap`, `.community`, `.remove`.
- **Real uninstall support** via `bin/remove.sh`, which pi-build lacked.

If a base is still wanted, asking KM4ACK to add a license is the cheap first move.

### Nexus DR-X (AG7GN)

`https://github.com/AG7GN/images` | image dead 2021

Included because the maintainer's stated reason for killing the image is directly
relevant to Hammunition's thesis. From his 2021-12-31 announcement: there is no longer a
special Nexus image, "it was just too time consuming to maintain," replaced by an
install script on stock Raspberry Pi OS. That is exactly the AHRL failure mode
Hammunition exists to avoid, stated by someone who lived it.

---

## 2. Upstreams to depend on rather than rebuild

### Debian Hamradio Pure Blend

`https://blends.debian.org/hamradio/` | Debian Hamradio Maintainers (`debian-hams@lists.debian.org`)

This should be Hammunition's base tier. It is already installable on stock Parrot:
`debian-hamradio` 0.10 is present in Parrot's own pool
(`mirrors.mit.edu/parrot/pool/main/d/debian-hamradio/`), no third-party repo needed.

152 packages across 12 tasks. The **14 metapackages** in trixie, verified against the
pool, are:

```
hamradio-all          hamradio-antenna     hamradio-datamodes   hamradio-digitalvoice
hamradio-logging      hamradio-morse       hamradio-nonamateur  hamradio-packetmodes
hamradio-rigcontrol   hamradio-satellite   hamradio-sdr         hamradio-tasks
hamradio-tools        hamradio-training
```

Two more `hamradio-*` binaries exist from other source packages: `hamradio-files`
(callsign and prefix lists) and `hamradio-maintguide`.

Naming gotchas worth putting in the docs: CW is `hamradio-morse`, not `hamradio-cw`;
packet is `hamradio-packetmodes`, not `hamradio-packet`; there is no `hamradio-aprs`.

`hamradio-sdr` alone pulls 54 packages: aethersdr, cubicsdr, cutesdr, gqrx-sdr,
inspectrum, quisk, sdrangel, sdrpp, gnuradio, gnss-sdr, gr-osmosdr, airspy, airspyhf,
bladerf, gr-hpsdr, gr-limesdr, hackrf, limesuite, miri-sdr, osmo-sdr, rtl-sdr,
qthid-fcd-controller, langford-utils, uhd-host, soapysdr-tools, soapyremote-server, 15
`soapysdr-module-*`, uhd-soapysdr.

Mechanics worth knowing:

- `hamradio-all` uses `Recommends:`, not `Depends:`. Blend convention: `Depends:` in a
  tasks file is emitted as `Recommends:` in `debian/control` so the metapackage stays
  installable when a member drops out of testing.
- `hamradio-tasks` only depends on `tasksel` and registers the tasks in the tasksel menu.
- Tasks files support an **`Ignore:`** field for tracking software that is not packaged
  yet. That is a ready-made pattern for Hammunition's wishlist.
- Release cadence is slow but accelerating: 0.8 (2022-01-05, bookworm), 0.10
  (2024-10-10, trixie and Parrot), 0.11 (2026-01-25), 0.12 (2026-06-06, sid/forky).
- Contribution route: MR against `salsa.debian.org/blends-team/hamradio` or mail to
  debian-hams. New packages follow the Debian Hamradio Maintainers Guide
  (`https://www.debian.org/doc/manuals/hamradio-maintguide/`).

**The strategic consequence:** if the blend is the base tier, Hammunition's actual job
shrinks to the delta. That delta is roughly the 30% Debian cannot ship: VARA and other
proprietary blobs, fast-moving upstreams, Winlink tooling, and the RF security half.

### Kali kali-tools-sdr, as a taxonomy not a dependency

`https://www.kali.org/tools/kali-meta/` | source `kali-meta` | 2026.3.3 into kali-rolling 2026-09-03

Do not add Kali's archive to Parrot. Do steal two structural ideas:

1. **Tiering.** `kali-linux-core` / `-headless` / `-default` / `-large` / `-everything`
   gives users a size ladder. Debian's hamradio blend has nothing equivalent, and it is
   the most obviously missing affordance in the whole space.
2. **A second orthogonal axis.** `kali-tools-identify/protect/detect/respond/recover`
   groups the same tools by NIST CSF function. A ham/SIGINT equivalent (by band, by
   mission, by deployment scenario) would be genuinely novel.

For reference, `kali-tools-sdr` is only 12 packages: chirp, gnuradio, gqrx-sdr,
gr-air-modes, gr-iqbal, gr-osmosdr, hackrf, inspectrum, kalibrate-rtl, multimon-ng,
uhd-host, uhd-images. Notably thin next to Debian's 54, and missing URH, SDR++, rtl_433
and SigDigger.

### radioconda

`https://github.com/radioconda/radioconda-installer` | BSD-3-Clause | Ryan Volz (MIT Haystack) | last push 2026-06-16

Do not install it. It would shadow apt's GNU Radio with a parallel prefix. **Do mine
`radioconda.yaml`,** which is the best-curated SDR package list in existence and the de
facto successor to PyBOMBS: GNU Radio 3.10 plus roughly 25 `gnuradio-*` OOT modules
(adsb, dect2, fosphor, ieee802_11, ieee802_15_4, iridium, leo, lora_sdr, radar, rds,
satellites and more), airspy, bladerf, digital_rf, codec2, gnss-sdr, gqrx, hackrf,
hamlib-all, inspectrum, libiio, libm2k, limesuite, mirisdr, m17-cxx-demod, pyadi-iio,
pyfda, rtl-sdr, soapysdr plus 14 modules, uhd.

Note that `conda-forge::gnuradio` is still on 3.10.12.0 (2025-02-20).

### nixpkgs `hardware.rtl-sdr.nix`

`nixos/modules/hardware/rtl-sdr.nix` in nixpkgs master

Lift this recipe verbatim into Hammunition's udev/modprobe layer: install udev rules,
ensure the `plugdev` group, and blacklist `dvb_usb_rtl28xxu`, `e4000` and `rtl2832`.
It is the single most commonly botched piece of RTL-SDR setup.

Also worth a look: `lasandell/nixpkgs-radio` (MIT, last commit 2026-06-05), the only ham
project found that ships both an overlay and system modules. Good reference for keeping
"packages" and "system config" as separate concerns.

### CGRAN

`https://www.cgran.org` | index of roughly 150 GNU Radio OOT modules with GR-version
compatibility columns. Thinning (many entries last touched 2013 to 2015) but still the
canonical source list for OOT coverage.

---

## 3. Prior art: distributions and images

Not Hammunition's architecture, but the landscape it will be compared against.

### Alive

| Project | Maintainer | Base | Scope | State |
|---|---|---|---|---|
| **Pi-Star** `pistar.uk` | Andy Taylor MW0MWZ | Raspbian Bullseye; new **Pi-Star_OS** is Pi kernel + Alpine with A/B root and atomic OTA | DV hotspot (D-STAR, DMR, YSF, P25, NXDN, M17) | Alive and revived. V4.3.7 2026-05-01; Pi-Star_OS releases through 2026-07-01. GPL-2.0. Pi-Star_OS is CI-built and PR-able |
| **WPSD** `w0chp.radio/wpsd` | W0CHP + small team | Raspberry Pi OS Trixie since 2025-09-15 | DV hotspot, part of the M17 Project | Alive, rolling updates. Highest bus-factor risk here: self-hosted Gitea, deliberately not on GitHub, forks discouraged, unofficial-fork traffic blocked, image-only install |
| **AllStarLink ASL3** | AllStarLink org | Debian 13 Trixie | RoIP and repeater linking (Asterisk app_rpt) | Very active. Pi image builder last commit 2025-12-19, x86 ISO repo created 2026-04-24, appliance packages 2026-08-26/31. AGPL-3.0 / GPL-3.0. Real org, open PRs, CI builds |
| **AREDN** | AREDN team | OpenWrt firmware | Mesh networking, emcomm | Very active. 4.26.7.0 released 2026-07-11, last commit 2026-09-05. GPL-3.0 plus AREDN trademark restrictions |
| **SatNOGS client images** | Libre Space Foundation | Raspberry Pi OS via pi-gen fork | Satellite ground station | Alive. Stable 2026070200-arm64 released 2026-07-02. BSD-3-Clause, GitLab CI, foundation-backed |
| **Pentoo** `pentoo.ch` | Pentoo team | Gentoo hardened live ISO | Pentest with a large SDR/RF toolset | Daily autobuilds, ISO dated 2026-09-06. **amd64 only**, x86 dead since 2024-01-11 |
| **Portsdown 4** | British Amateur TV Club | Install script over stock Raspberry Pi OS Buster Lite | DATV transmit and receive | Alive, last commit 2026-08-20. GPL-3.0. Note it is a script build, not an ISO, so it is arguably a peer. **portsdown4ng is dead** (2023-01-10) |
| **KiwiSDR** | John Seamons ZL/KF6VO | BeagleBone/BeaglePlay Debian appliance | 0 to 30 MHz multi-user WebSDR | Alive, last commit 2026-09-01. Single maintainer. The old `jks-prv/Beagle_SDR_GPS` repo is archived, do not cite it |
| **HamLinux** `i8zse.it` | Giorgio Rutigliano I8ZSE | Debian | General ham and digital modes, portable/emcomm framing | **New 2026 entrant.** v3.0.0 June 2026, both Pi and x86_64 images. Single maintainer, hand-built images, no public source repo, license not stated. Promising but unproven, and it repeats the AHRL failure mode |

### Degraded

- **KrakenSDR.** `krakensdr_doa` software last commit 2025-12-13 (GPL-3.0), but the Pi
  4/5 SD images are hand-built, distributed via MEGA and Google Drive, and last dated
  2024-10-30.
- **OpenWebRX+ (luarvique fork).** Software is extremely active (last commit 2026-09-06,
  AGPL-3.0, own apt repo for Bullseye/Bookworm/Trixie and Ubuntu 22.04/24.04), but the
  **prebuilt SD images are stale at 1.2.117 from 2024-06-26** and the project says so
  itself. Package the software, ignore the images.
- **OpenRepeater.** Code has 2026 activity (last commit 2026-06-04) but the shipped image
  is from 2021-03-20 on Raspbian Buster, and there is **no LICENSE file in the repo**.
- **SigintOS.** Ubuntu-based SIGINT ISO, 2.0 Community Edition around March 2024 with GNU
  Radio 3.8. No public repo, no changelog, no stated license, no visible activity in
  2025 or 2026. Treat as dormant and untrusted-provenance.

### Category corrections

Three things commonly listed that should not go in Hammunition's docs as they are
usually described:

- **There is no Fedora Labs Amateur Radio spin.** fedoraproject.org/labs lists exactly
  seven labs and amateur radio is not among them. The Fedora Amateur Radio SIG wiki still
  lists "create a Fedora Hams SIG Spin" as a future goal and its status log ends
  2016-11-03. There are ham packages in Fedora, no comps group, no image.
- **Arch has no official hamradio group.** Verified against the full list of 117 x86_64
  groups. Ham and SDR software lives as loose extra/AUR packages. There is at least one
  AUR grouping helper, `hamradio-menus`, but it is a desktop-menu category package, not a
  dependency metapackage. (AUR itself is behind Anubis anti-bot, so this is
  unverified-negative on AUR metapackages specifically.)
- **Radioberry and piHPSDR are alive but are not distributions.** Radioberry (pa3gsb,
  2026-06-07) is a cape and FPGA firmware; piHPSDR (g0orx 2026-06-03, dl1ycf 2026-09-02)
  is an application. Neither ships an OS image.

### Dead, do not recommend

| Project | Last activity | Note |
|---|---|---|
| **HamPi / HamPC** (W3DJS) | commit 2024-04, last real release v3.0 2022-05-30 "Final Release" | Ansible-playbook build, GPL-3.0, reproducible. The only newer image is a 32-bit alpha. Package list is still a decent coverage checklist |
| **PiSDR** (Luigi Cruz) | 2022-10-04 / v7.0.0-alpha2 2023-12-19 | MIT, pi-gen. Maintainer moved to CyberEther |
| **HamVoIP** (K4FXC) | 1.7-01, 2022-05 | Arch ARM AllStar image, closed, hand-built. Users migrating to ASL3 |
| **jketterl/openwebrx** | 2024-12-11 | Superseded by OpenWebRX+ |
| **raspberry-noaa-v2** | 2024-10-26 | GPL-3.0, dormant |
| **GNU Radio Live SDR Environment** | Ubuntu 16.04 / GR 3.7.11 | Officially retired by GNU Radio |
| **Gorizont-rtlsdr** | 2022-03-08 | Xubuntu 18.04 ISO |
| **hamOS** | 2012 | The maintainer's own 2020 readme says to use something current |
| **LibreHamOS** (nr0q) | 2020-09-12 | LibreELEC fork, GPL-2.0 |
| **AFU-Knoppix**, **Harv's Hamshack Hack (AI9NL)** | last decade | Still listed on DXZone. Abandoned |

---

## 4. Tooling notes that affect the install matrix

These are live facts about Debian and upstream churn that will break a naive package
list. Worth encoding as tests in the installer.

**`ax25-tools` was removed from Debian testing on 2026-09-01** (blocked by bug #1143282,
"introducing regressions"). It survives in trixie stable
(`0.0.10-rc5+git20230513+d3e6d4f-3`) and in unstable. `ax25-apps` and `libax25` are
unaffected. Parrot tracks testing/sid, so pin the trixie version or vendor the salsa
snapshot rather than assuming apt has it.

Related: **do not prefer the VE7FET `linuxax25` fork.** Its last release tag is
`ax25tools-1.0.4` from 2018-08-28, it has no LICENSE file, and its own README says it is
not the official home. Debian's `git20230513` snapshot is newer.

**`gr-gsm` is marked for autoremoval from Debian testing on 2026-10-12** (transitive
dependency on `sphinx-autodoc-typehints`, bug #1146084). Upstream `ptrkrysik/gr-gsm` is
effectively abandoned (last push 2025-03-10, still targeting GNU Radio 3.8) and the
`velichkov` fork Debian snapshotted has not been pushed since 2022-07-28. If Hammunition
wants GSM, build **`bkerler/gr-gsm` branch `maint-3.10_with_multiarfcn`** from source.

**JS8Call development moved.** `js8call/js8call` is frozen at v2.3.1 (last push
2025-12-05) and its own README redirects to the community fork. Reference
**`JS8Call-improved/JS8Call-improved`** (GPL-3.0, v3.0.3 2026-07-13, last push
2026-09-06). Debian already tracks the fork: sid ships `js8call 3.0.3+ds-1`.

**SDR++ is now packageable.** It entered Debian unstable 2026-05-28 and there is a
trixie-backports build. That removes a build-from-source item from the matrix.

**`multimon-ng` in Debian is stale** at 1.3.1+dfsg across all suites while upstream is at
1.6.0 (last push 2026-07-27). Candidate for a Hammunition-built package.

**`dump1090` is dead in all its classic forms.** antirez's is dead since 2014,
mutability's is dead, and Debian's `dump1090-mutability` is a 2018 snapshot that was
removed from testing in Aug 2024 and has been blocked from migrating since Apr 2026. Use
**`wiedehopf/readsb`**, or FlightAware's fork for FA feeders.

**VARA cannot be redistributed.** VARA HF 4.9.0 / FM 4.4.0 / SAT 4.4.5 / Chat 1.4.2 /
Terminal 1.2.2 are proprietary paid Windows binaries from EA5HVK, run under Wine on
Linux. Pat, LiaisonOS and EMCOMM Tools all just wrap it. Hammunition can ship an
installer helper at most. The license-clean substitute is **`ardopcf`** (pflarue, MIT,
last push 2026-09-01), which now has a WebGUI.

**Must build from source, nothing in Debian:** URH, SigDigger, rfcat, sdrtrunk, DSD-FME,
OP25, Trunk Recorder, KrakenSDR DoA, gr-iridium, ardopcf, linBPQ, Reticulum and NomadNet
(PyPI), MeshCore, OpenRTX, meshtasticd (third-party OBS repo), RF Swift.

**`python3-meshtastic` is marked for autoremoval from testing on 2026-10-03** (RC bugs in
three dependencies). `meshtasticd` was never in Debian at all; it comes from
`download.opensuse.org/repositories/network:/Meshtastic:/{beta,alpha,daily}/Debian_13/`.

### Individual tools worth adding to the inventory

Alive and not in the current AHRL-derived list: **Universal Radio Hacker** (v2.10.0
2025-12-17, GPL-3.0, PyQt6, not in Debian), **rfcat** (v3.0.0 2026-08-11, first real
release in years, Py3 + PySide6, BSD), **SigDigger** with suscan and sigutils (LGPL-3.0,
active but tag-starved, build from git not releases), **DSD-FME** (release 20260715,
ISC), **OP25 boatbod fork** (2026-08-23, the live P25 fork; the Osmocom original is
dead), **Trunk Recorder** (2026-09-01), **SatDump** (in Debian, sid has
`1.2.2+git20260527`), **rtl_433** (25.12, Debian sid has 25.12-1), **gr-satellites**
(v5.9.0 2025-12-14, in Debian), **PortaPack Mayhem firmware** (v2.4.0 2026-03-24, HackRF
Pro support), **readsb**, **Pat** (v1.0.0 2026-04-19, Debian sid has 1.0.0-2),
**Direwolf** 1.8.1, **linBPQ** (very active, but no OSI license and the repo is a
drop-box, not a collaboration space), **OpenRTX** (2026-09-05), **MeshCore** (MIT,
2026-09-05, the main Meshtastic challenger), **Reticulum / LXMF / NomadNet**.

Dead individual tools, worth an explicit "we looked, do not bother" note: **Salamandra**
(2021-01-11, no license, trivially reimplemented over `rtl_power`), **Chattervox**
(2020-01-04), **Crocodile Hunter / EFF** (2023-02-16), **LTESniffer** (2024-10-23,
academic drop), **kalibrate-rtl** (2023-08-15, works but frozen, still shipped by Kali),
**RFQuack** (2024-12-23, 21 months idle), **qFlipper** (2024-06-11, use `ufbt` or the
web updater), **PyBOMBS** (2022-04-25, de-recommended by GNU Radio itself, not archived
which misleads people). **sdrtrunk**'s repo is alive (2026-08-01) but its last release is
v0.6.1 from 2024-12-03 and it is Java/Gradle with no Debian packaging, so it is a
downloaded-JAR decision.

---

## 5. The gap nobody has filled

Exhaustive search found **no maintained, general-purpose configuration-management layer
for a ham shack.** No Ansible Galaxy collection, no Puppet module, no Chef cookbook. The
only candidates are four personal dotfile-grade repos (`hestela/ham-ansible`, MIT, 0
stars, 2026-02-26; `nq0m/ham-ansible`, GPL-3.0, 1 star, 2023; `dl1igc/hamsible`, stale,
no license; `jared-bloomer/KW4JLB_Install-HamClock`, archived). The only credible Nix
entry is `lasandell/nixpkgs-radio`.

HamPi is the only project in the entire survey that used a declarative build (Ansible),
and it is dormant. Every living peer is an imperative bash installer.

An idempotent, declarative, re-runnable layer would be the first of its kind in this
space, and it is directly responsive to the AHRL complaint that started Hammunition: the
reason single-maintainer ham distros die is that hand-built images do not survive their
maintainer's attention budget. Declarative build definitions do.

Also empty: no Flathub amateur-radio collection or runtime extension, no curated Snap
bundle. The only good curated-collection model found outside apt is
`gm5dna/homebrew-amateur-radio` (MIT tap metadata, 100+ formulae and casks, last commit
2026-09-06), which is macOS only but is a well-run example of exactly the curation job
Hammunition is taking on. openSUSE's `hardware:sdr` OBS project has 184 packages but 77
build errors, so it is a cautionary example rather than a model.

---

## 6. Licensing hazards, summarized

| Project | Status | Consequence |
|---|---|---|
| **73Linux** | No license file (verified 404 on LICENSE, LICENSE.md, LICENSE.txt, COPYING) | All rights reserved. Cannot vendor, fork or copy. Reimplement patterns only |
| **km4ack/pi-build** | No license file | Same |
| **EmComm Tools Community** | Apache-2.0 for code, separate restrictive notice for The Tech Prepper brand logos and images | Code is reusable. Strip branding assets |
| **LiaisonOS** | Ms-PL, over an Apache-2.0 upstream | Discrepancy unresolved. Check before borrowing from either |
| **linBPQ** | No OSI license; repo is a source drop-box | Install-time download, not vendoring |
| **VARA family** | Proprietary, paid, Windows-only | Installer helper at most, no redistribution |
| **AREDN** | GPL-3.0 plus trademark restrictions | Do not use the AREDN name or marks |
| **OpenRepeater** | No LICENSE file despite active code | Treat as all-rights-reserved |
| **SigintOS**, **HamLinux** | No stated license, no public source | Reference only |
| **FISSURE** | GPL-3.0 (verified) | Fully reusable. Best license situation of any direct peer |
| **RF Swift** | GPL-3.0 | Fully reusable |
| **Debian blend** | Per-package DFSG | Depend freely |

---

## Suggested actions for Hammunition

1. **Make `hamradio-*` the base tier.** It is already in Parrot's pool at 0.10. That
   inherits 152 curated packages plus Debian QA, and reduces Hammunition's scope to the
   delta Debian cannot ship.
2. **Decide the FISSURE relationship explicitly.** It has a Parrot code path in beta and
   is GPL-3.0. Contributing there beats duplicating it, and it is the natural bridge
   between Parrot's security identity and the ham side. At minimum, do not collide with
   its GNU Radio install.
3. **Decide the RF Swift relationship explicitly.** Delegating the volatile RF security
   tier to containers is a real architectural option and would cut long-term maintenance
   substantially.
4. **Lift ETC's `et-radio` / `et-mode` abstraction** under Apache-2.0, stripped of
   branding. Best single borrow available.
5. **Reimplement 73Linux's `.bapp` plugin model and `cache/` markers.** Proven answer to
   installed-state tracking and third-party contribution, but unlicensed, so clean-room it.
6. **Add Kali's size ladder.** `core` / `default` / `large` / `everything` tiers. Nobody in
   the ham space has this.
7. **Mine `radioconda.yaml` and the Debian blend tasks files for coverage**, then use the
   blend's `Ignore:` convention for the not-yet-packaged wishlist.
8. **Encode the churn from section 4 as installer tests**, not as a static package list.
   `ax25-tools` and `gr-gsm` are both leaving testing inside the next six weeks.
9. **Consider a declarative build definition** as the differentiator. It is the only
   unoccupied position in the space and it is the direct structural answer to the AHRL
   maintainability complaint.

---

## Verification caveats

`salsa.debian.org`, `gitlab.com`, `aur.archlinux.org`, `wiki.archlinux.org`,
`packages.debian.org`, `sources.debian.org` and `api.github.com` were all blocked from
the research environment by robots rules, Anubis anti-bot or proxy policy. Debian facts
were confirmed instead against `metadata.ftp-master.debian.org` changelogs,
`tracker.debian.org`, `blends.debian.org` and the raw Debian and Parrot mirror pools, all
of which are authoritative. GitHub dates came from `ungh.cc` (unauthenticated API mirror)
and from HTML release pages. Licenses were read from the actual `LICENSE` and `COPYING`
blobs on `raw.githubusercontent.com`, not from search results.

Not verified: `kali-meta`'s internal `debian/control` layout, any AUR `hamradio*`
metapackage beyond the existence of `hamradio-menus`, and WPSD commit dates
(`repo.w0chp.net` returned proxy 403).
