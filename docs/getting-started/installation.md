<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Installation

This page takes you from a fresh machine to an installed profile, one numbered
step at a time. Every command is written out in full and every block of output
was captured from a real run, with a note saying where. Nothing here asks you
to trust the tool: the engine prints each change before it makes it, and the
plan is the same text the real run shows.

If you only want the five-minute version, [Installing the
engine](install.md) is the short form. If you want to know how much disk to
set aside first, [How much disk you need](disk-space.md) says, with the source
of every figure.

**What you will have at the end:** the `hammunition` command on your PATH, your
callsign and grid square saved once, the device rules and groups applied, and
one profile installed and verified, with a way to see what was done and to
undo it.

**What this page does not need:** a radio, an SDR or a GPS. Installing the
software needs none of them. They matter when you operate, and each profile
page says what it assumes.

## Contents

1. [What you need before you start](#1-what-you-need-before-you-start)
2. [Which system you have](#2-which-system-you-have)
3. [Update the system and get the tools](#3-update-the-system-and-get-the-tools)
4. [Get the engine](#4-get-the-engine)
5. [Run the health check](#5-run-the-health-check)
6. [Tell the engine who you are](#6-tell-the-engine-who-you-are)
7. [Choose a profile](#7-choose-a-profile)
8. [Read the plan](#8-read-the-plan)
9. [The consent prompts](#9-the-consent-prompts)
10. [Run the install](#10-run-the-install)
11. [Apply the hardware rules](#11-apply-the-hardware-rules)
12. [See what was done](#12-see-what-was-done)
13. [Keep it current](#13-keep-it-current)
14. [Take it off again](#14-take-it-off-again)
15. [Where everything lands](#15-where-everything-lands)
16. [When something fails](#16-when-something-fails)
17. [Differences on other systems](#17-differences-on-other-systems)

## 1. What you need before you start

| You need | Why | Notes |
|---|---|---|
| A Debian-family system | The engine reads `/etc/os-release` and installs with `apt`. | Anything else is refused by name, not guessed at. Section 2 lists what is measured. |
| A normal account with `sudo` | The engine runs as you and puts `sudo` only in front of the steps that need root. | Do not run it as root and do not type `sudo hammunition`. See step 4. |
| An internet connection | Packages come from your distribution's archive. Anything else is fetched from its publisher and checked against a pinned checksum before it runs. | Nothing unverified is installed, and nothing is piped into a shell. |
| `git` and Python 3.11 or newer | To get the engine and run it. | Parrot 7.4 here has Python 3.13.5. Step 3 checks yours. |
| Free disk | One or two profiles fit in about 5 GB, the whole catalog in about 55 GB. | Offline maps and Wikipedia are what make a disk large, and you choose each one. [The disk page](disk-space.md) has every figure and its source. |
| Time | Most profiles install from apt in minutes. Source builds dominate. | `digital-modes` builds six programs and took 44 commands and 1.28 GB on a Kali VM (2026-09-02). Whole profiles on an Ubuntu 24.04 VM took from 101 seconds (`satellite`) to 819 seconds (`propagation`) (2026-09-03, [the Ubuntu campaign](../reference/vm-campaign-ubuntu.md)). |

You do not need to be root to plan anything. `list`, `show`, `status`,
`doctor`, `station show` and `--dry-run` need no privileges.

## 2. Which system you have

Parrot OS is the primary target and the one every step below was written on.
The table says what has been measured for each other system and what has not.
A VM campaign means every unit was installed by name or every profile whole
from a clean snapshot, with the engine re-reading the effect afterwards
(D-031). A capability-matrix row means the manifests resolve against that
target's archive and nothing more.

| System | Status | What is measured, and where |
|---|---|---|
| Parrot OS 7 (Security or Home) | Primary | Parrot 7.3 VM: whole profiles installed and confirmed, 13 of 15 on the second pass after the mixed-release fix (D-038). The field laptop runs Parrot Security 7.4, where the whole catalog installed. See [Parrot VM](../reference/vm-verification-parrot.md) and [the Ubuntu campaign](../reference/vm-campaign-ubuntu.md). |
| Debian 13 | Declared target | VM 2026-08-29: station installed, idempotent, uninstalled. Whole profiles: 13 installed and confirmed, one stopped at its consent gate, one refused (since fixed). A netinst needs `python3-venv` first. See [Debian 13 VM](../reference/vm-verification-debian13.md). |
| Ubuntu 24.04 | Declared target | VM 2026-09-02: 243 units by name, 224 installed and confirmed, 0 failed, 19 refused at plan time. Some members are deferred because the archive lacks them or is too old (for example Node 18 for `openhamclock`). See [the Ubuntu campaign](../reference/vm-campaign-ubuntu.md). |
| Ubuntu 26.04 | Declared target | Same campaign: 234 confirmed, 0 failed, 9 refused at plan time. |
| Kali rolling | Declared target | VM 2026-08-29 (Kali 2026.3): station installed and uninstalled cleanly. `digital-modes` whole was confirmed after a fix, 1.28 GB. Kali's current kernel has no `ax25.ko`, so the kernel AX.25 stack defers there (D-041). See [Kali VM](../reference/vm-verification-kali.md). |
| Linux Mint 22.3 | Declared target | A capability-matrix row only. Mint installs from Ubuntu 24.04's archive, so the Ubuntu 24.04 campaign is the nearest evidence. No Mint VM run is recorded. |
| Pop!_OS 24.04 | Not a declared target | VM 2026-09-04: 224 of 243 units confirmed, 14 of 16 profiles whole. Evidence for a decision, not a promise. See [the Pop!_OS campaign](../reference/vm-campaign-pop.md). |
| Raspberry Pi OS (64-bit) | Declared as the Debian 13 arm64 target | A capability-matrix row, and the engine's `arch` selector is structural. No run on Pi hardware is recorded here. Several units have no arm64 block. 32-bit Pi OS is unmeasured. |

[The capability matrix](../reference/capability-matrix.md) is generated and
lists every manifest against every target. It is the weaker of the two checks:
a package being offered by an archive is not proof that it installs.

**Desktop.** Parrot with KDE Plasma comes first for the menu and the tray. Xfce
and LXQt are the next to be measured. Almost all of the software does not care
which desktop you run. [What works on which desktop](../desktops.md) says what
is measured.

## 3. Update the system and get the tools

These are ordinary system commands, not Hammunition's. Bring the system up to
date, then check the two tools the engine needs.

```sh
sudo apt update
sudo apt full-upgrade
```

On Parrot, `parrot-upgrade` is Parrot's own wrapper for the same job. Either is
fine. The engine runs its own `apt-get update` at the start of any install that
has apt work (D-044), because stale package lists are the commonest way a
correct plan fails, but updating first is good practice and means the engine's
refresh finds nothing new.

Install `git`, and check Python:

```sh
sudo apt install git
python3 --version
```

On Parrot 7.4 the second command prints:

```text
Python 3.13.5
```

You need 3.11 or newer. A Debian netinst or a minimal image may also lack the
venv module the engine builds its own environment with. Install it now so
bootstrap does not have to:

```sh
sudo apt install python3-venv
```

Parrot and Kali ship it. A Debian netinst does not (measured on a Debian 13
VM, 2026-08-29), and bootstrap installs it for you, telling you first, if you
skip this.

## 4. Get the engine

Hammunition is a Python engine plus a catalog of YAML manifests. The supported
way to run it is from a git checkout:

```sh
git clone https://github.com/ChiefGyk3D/Hammunition.git
cd Hammunition
./bootstrap.sh
```

`bootstrap.sh` does five things, in this order, and prints each as a line
starting `==>`:

1. Checks the system is Debian-family and finds a Python 3.11 or newer.
2. Installs `python3-venv` with `sudo apt-get install` only if it is missing,
   and says so first. It is the only thing bootstrap does as root.
3. Creates `.venv` in the checkout and installs the engine into it.
4. Links `~/.local/bin/hammunition` to the checkout's `.venv/bin/hammunition`,
   so every command in these docs works as typed.
5. Runs `hammunition doctor` and prints three next commands.

It is safe to run again after a `git pull`. The link step is run by
`scripts/path-link.sh`, which prints each change before it makes it. Here is
its real output, captured against an empty home directory:

```text
==> creating /home/op/.local/bin (mode 0755)
==> linking /home/op/.local/bin/hammunition -> /home/op/Hammunition/.venv/bin/hammunition
!   /home/op/.local/bin is not on your PATH, so `hammunition` will not be found yet.
!   Add this line to ~/.profile, then log out and back in:
    export PATH="$HOME/.local/bin:$PATH"
```

On a system whose login scripts already add `~/.local/bin` to the PATH when the
directory exists (Parrot and Debian 13 do), the last three lines do not appear
once you log out and back in. On a system that never adds it, put the line it
printed in `~/.profile`. Bootstrap never edits a shell rc file, and it never
replaces a `~/.local/bin/hammunition` it did not create. A pipx install or a
link to a different checkout is left alone and named.

Check that the shell finds it:

```sh
hammunition --version
```

```text
hammunition 0.19.0
```

The version number moves with each release; yours will be newer.

### If the shell says `hammunition: command not found`

Run the checkout's own copy by its full path until you have logged out and back
in:

```sh
~/Hammunition/.venv/bin/hammunition doctor
```

(Replace `~/Hammunition` with wherever you cloned it.) You do not need `sudo` in
front of `hammunition`. Run it as yourself and it adds `sudo` to the steps that
need it. If you do type `sudo hammunition`, sudo replaces your PATH with its own
`secure_path`, which does not include `~/.local/bin`, so you get `command not
found` even though the command works without `sudo`.

### The manual route

If you would rather not run a script:

```sh
git clone https://github.com/ChiefGyk3D/Hammunition.git
cd Hammunition
python3 -m venv .venv
.venv/bin/pip install -e .
scripts/path-link.sh "$PWD"
hammunition doctor
```

Now ask the engine what machine it thinks it is on:

```sh
hammunition status
```

```text
Target: Parrot Security 7.4 (echo) (ID=parrot, version=7.4, arch=x86_64)
Debian family: yes
Catalog: /home/op/Hammunition/catalog
  321 packages, 319 of which resolve on this target
  19 profiles
Transaction log: /home/op/.local/state/hammunition/transactions.jsonl
  no transactions recorded
```

Reading it: the **Target** line is what `/etc/os-release` says, not what the
engine concluded from it. **Debian family: yes** means the engine will install
here. The **Catalog** lines say how many manifests exist and how many resolve
to an install method on this target; the difference (two here) is manifests
that declare no block for it, such as the two that are Kali-only. The
**Transaction log** is the machine's record of everything the engine does, and
it is what `uninstall` stands on. Before your first install it is empty.

## 5. Run the health check

```sh
hammunition doctor
```

`doctor` is read-only. It changes nothing, it exits non-zero only when
something blocks the engine, and it names the one command that fixes each gap.
It is the output to paste when you ask for help. This is a real run on the
developer's Parrot Security 7.4 laptop with no station set yet:

```text
Hammunition health check

  [✓] system         Parrot Security 7.4 (echo) (ID=parrot, version=7.4, arch=x86_64)
  [✓] catalog        321 packages, 19 profiles loaded
  [✓] python venv    python3 -m venv is available
  [✓] PATH           ~/.local/bin is on PATH
  [✓] hammunition    on PATH: /home/op/Hammunition/.venv/bin/hammunition
  [✓] compiler       a C toolchain is present for source builds
  [✓] git            git is present for git-source builds
  [!] station        no callsign/grid set — packet and logging configs are deferred until you set them
      → hammunition station set --callsign YOURCALL --grid-square AB12cd
  [✓] device groups  in every device-access group
  [✓] udev rules     the catalog's udev rules are installed
  [✓] hardware       8 catalogued device(s) attached — see `hardware list`
  [·] desktops       session files offer KDE Plasma; also lightdm-xsession.desktop, which names no desktop the catalog knows; this session is KDE Plasma
  [✓] time           the clock follows the GPS (mode auto, offset +10.0 ms)
  [✓] geoclue        GeoClue reads the tether's socket at /run/hammunition-gps/nmea.sock while `hammunition maps gps-tether` runs
  [✓] geoclue agent  Debian's GeoClue demo agent is running
  [✓] gps-resume     the resume step is installed: gpsd gets a fresh open of the receiver after a suspend
  [✓] launchers      3 launchers run hammunition by a path that exists
  [✓] state dir      the transaction log directory is writable
  [·] rig            no station rig is set; the shared rigctld is not configured

18 ok, 1 to look at, 0 blocking.
The engine works; the items marked ! limit what you can install until fixed.
```

Your list will differ: this laptop has a GPS, a rig-less station and some
hardware attached, which a fresh machine does not. The marks are:

| Mark | Meaning |
|---|---|
| `[✓]` | Checked and healthy. |
| `[!]` | A whole class of installs or a feature is unavailable until you fix it. The engine still runs. |
| `[·]` | A true fact that is not a problem, such as no hardware attached. |
| `[✗]` | The engine cannot work until you fix it (not Debian-family, no catalog). Exit code is non-zero. |

What each line means:

| Line | What it checks | If it is not green |
|---|---|---|
| `system` | `/etc/os-release` names a Debian-family system. | The engine refuses the machine. Nothing to fix from here. |
| `catalog` | The manifests loaded and validated. | A broken checkout. `git status`, then re-clone. |
| `python venv` | `python3 -m venv` works. | `sudo apt install python3-venv`. |
| `PATH` | `~/.local/bin` is on your PATH. | Log out and back in, or add the line bootstrap printed to `~/.profile`. |
| `hammunition` | The `hammunition` your shell finds is this checkout's. | Re-run `./bootstrap.sh`, or run the printed `ln -sfn` to switch checkouts. |
| `compiler` | A C toolchain is present for source builds. | `sudo apt install build-essential`. Many units build from source. |
| `git` | `git` is present for git-source builds. | `sudo apt install git`. |
| `station` | Your callsign and grid square are saved. | Step 6. Until then packet and logging configs are deferred, not refused. |
| `device groups` | You are in every group the catalog's devices need (`plugdev`, `dialout`). | Step 11, then log out and back in. |
| `udev rules` | The catalog's udev rules are installed. | Step 11. On a machine with no radios this is information, not a warning. |
| `hardware` | How many catalogued devices are attached right now. | Information. `hammunition hardware list` shows them. |
| `desktops` | Which desktops the login screen offers, and which one this session is. | Information. It decides which tray the `station` profile installs. |
| `time` | What the clock follows (the network or a GPS) and how far off it is. | Important for FT8, which fails if the clock is more than about a second out. [Time and position](../guides/time-and-gps.md). |
| `geoclue`, `geoclue agent` | Appear only where GeoClue is installed; they check the map position bridge. | Only matters for the offline maps. [Offline navigation](../guides/offline-navigation.md). |
| `gps-resume` | Appears only with a GPS attached: the resume step after suspend is in place. | `hammunition hardware apply`. |
| `launchers` | Every generated launcher that runs the engine names an engine that exists. | `hammunition menus apply`. |
| `state dir` | The transaction log directory is writable. | Fix the permissions on `~/.local/state/hammunition`. |
| `rig` | The station's radio and the shared `rigctld`. | Information until you name a radio. [Rig control](../guides/rig-control.md). |

Other lines can appear: `run logs` once you have run something, and a `qmapshack`
check where it is installed.

## 6. Tell the engine who you are

Some software writes configuration files containing your callsign and grid
square: a packet node transmits, and its identity is yours. **Nothing is ever
invented.** There is no default callsign. Set your own once:

```sh
hammunition station set --callsign N0CALL --grid-square FN31pr
```

Use your own values. `N0CALL` and `FN31pr` are placeholders, and the real run
below used `N0TST`. The values are saved to `~/.config/hammunition/station.yml`,
readable only by you (mode 0600).

```text
Saved to /home/op/.config/hammunition/station.yml (mode 0600).
  callsign       N0TST
  grid_square    FN31pr
```

Read them back:

```sh
hammunition station show
```

```text
Station configuration: /home/op/.config/hammunition/station.yml

  callsign       N0TST
  grid_square    FN31pr
  node_alias     (not set)
  rig            (not set)
  rig_baud       (not set)
  rig_device     (not set)
  rig_owner      (not set)
  rig_ptt_line   (not set)
  map regions    (not set)
  map freshness  yearly
  mirror         (not set)
  dem_source     copernicus
  topo radius    100 km (the default)
  topo regions   (not set)
  topo all       no
```

`station show` is fine on your own screen. Do not paste its output into a forum
or an issue: a callsign resolves to a name and an address, and a grid square
says where the station is. Where the docs show a value, it is a placeholder.

A value you have not set does not stop an install. The package installs, and
the one file that needed the value is reported under *Will NOT happen* with the
command that would let it be written (D-035).

### Every station value

| Flag | What it holds | Who reads it |
|---|---|---|
| `--callsign` | Your callsign. | Direwolf (`/etc/direwolf.conf`), the AX.25 port file (`/etc/ax25/axports`), `aprx`, `uronode`, LinBPQ (`/etc/bpq32.cfg`) and the TLF contest logger (`~/tlf/logcfg.dat`), all written for you when it is set. |
| `--grid-square` | Your Maidenhead locator, four or six characters. | gpredict's ground station (`~/.config/Gpredict/sample.qth`, with the latitude and longitude derived from it), LinBPQ, TLF, and the US Topo and terrain selection for the navigation profile. |
| `--node-alias` | A short packet node alias, up to six characters. | LinBPQ and `uronode`. |
| `--map-regions` | Geofabrik region paths to carry offline maps for, comma-separated. | The map units: Navit, QMapShack, CoMaps, BRouter, the browser map, `phone-maps` and the terrain for `antenna`. Without it they are deferred by name. `hammunition maps regions <filter>` finds a path (it asks Geofabrik, so it needs the network). |
| `--map-freshness` | `yearly` (the default), `monthly` or `latest`. | Which dated file each region resolves to. |
| `--reference-books` | Kiwix book ids, from `hammunition reference books`. | The `reference` profile's book unit. |
| `--topo-radius-km`, `--topo-regions`, `--topo-all` | How far from your grid square's centre topographic sheets and terrain are fetched. | The navigation profile. 100 km by default. |
| `--dem-source` | `copernicus` (the default) or `3dep`. | Which elevation QMapShack draws from. |
| `--mirror`, `--clear-mirror` | A LAN machine each data download asks first. | Every data download. [A LAN mirror](../guides/lan-mirror.md). |
| `--rig`, `--rig-device`, `--rig-baud`, `--rig-ptt-line`, `--rig-owner` | Your radio, its serial port, speed and keying line, and who holds the port. | `rig-service` (the shared `rigctld`) and gpredict's rig file. [Rig control](../guides/rig-control.md). |
| `--unattended` | Keep the rig service running with nobody logged in. | The rig service, through the power-control helper. |

A region list says where you live or travel, so `station show` prints how many
regions are set and never their names. [Your callsign in each
program](../guides/station-settings.md) says where to type the same values into
the programs that keep their own.

## 7. Choose a profile

A profile is a named bundle of software that belongs together. Profiles are
flat tags that overlap and never nest, so you combine them freely.

```sh
hammunition list profiles
```

```text
Profiles (19):
  antenna          1.0        12 pkg  installed 0 of 12
      Antenna modelling, transmission lines and coverage prediction
  digital-modes    1.0        22 pkg  installed 0 of 22
      FT8, JS8, PSK31, SSTV, digital voice and the rest of the keyboard modes
  editors          post-1.0    2 pkg  installed 0 of 2
      VS Code and VSCodium, opt-in, each behind its publisher's apt repository
  electronics      1.0        14 pkg  installed 0 of 14
      Bench electronics, instruments and device programmers
```

(The listing continues through all nineteen. The count after each name is how
many of its members you have installed.)

The full table, with what each profile assumes, what it leaves out and which
consent gates it carries, is on [the profiles index](../profiles/index.md),
followed by a "which profile do I want" table by goal. The short answer:

1. **Install `station` first.** Rig control, a correct clock and a position
   source, which every other profile quietly assumes.
2. **Then the profile for what you do.** `digital-modes` for FT8, `packet` for
   Winlink and APRS, `sdr` or `listening` for a dongle, `satellite`,
   `navigation`, and so on.
3. **Read before you install.** `hammunition show <profile>` prints what it
   installs, why those things belong together, its disk footprint, what it
   leaves out and what you configure by hand afterward. It changes nothing.

```sh
hammunition show satellite
```

The security profiles are separate on purpose. `rf-security` is ungated and
passive. `rf-research` is behind a consent gate (step 9).

## 8. Read the plan

Every install can be planned first. `--dry-run` resolves the whole transaction,
prints every command it would run and changes nothing. It is the same text the
real run prints, so the real run holds no surprises.

```sh
hammunition install station --dry-run
```

Here is a real plan for the `satellite` profile, captured on the developer's
Parrot Security 7.4 laptop, where most of it was already installed. A fresh
machine shows `will install` where this shows `already installed`.

```sh
hammunition install satellite --dry-run
```

```text
Target: Parrot Security 7.4 (echo) (ID=parrot, version=7.4, arch=x86_64)

Packages (5):
  gnuradio                     already installed  [dependency of gr-satellites]
      = gnuradio
  gpredict                     already installed  [profile satellite]
      = gpredict
  gr-satellites                already installed  [profile satellite]
      = gr-satellites
  libhamlib-utils              already installed  [profile satellite]
      = libhamlib-utils
  satdump                      already installed  [profile satellite]
      = satdump

Configuration that will be written:
  /home/op/.config/Gpredict/sample.qth  (written, mode 0644, existing file backed up)  [gpredict]  fills grid...

Will NOT happen (the rest of the transaction still will):
  gpredict: will not write /home/op/.config/Gpredict/hwconf/hammunition.rig
      why: station values not set: rig_device
      → run `hammunition station set --rig-device <value>` and install again, or write
      the file by hand. The package itself installs either way.

Records:
  transaction log written to /home/op/.local/state/hammunition/transactions.jsonl

Commands (5):
  # Write /home/op/.config/Gpredict/sample.qth for gpredict
  $ [config] mode 0644, existing file backed up
  # Generate the gr_satellites-list launcher for gr-satellites
  $ [wrapper] /home/op/.local/bin/gr_satellites-list
  # Add gr_satellites-list to the desktop menus
  $ [desktop-entry] /home/op/.local/share/applications/hammunition-gr_satellites-list.desktop
  # Generate the rigctl-dummy launcher for libhamlib-utils
  $ [wrapper] /home/op/.local/bin/rigctl-dummy
  # Add rigctl-dummy to the desktop menus
  $ [desktop-entry] /home/op/.local/share/applications/hammunition-rigctl-dummy.desktop

Afterwards: the Hammunition menu is re-applied for this user (per-user files, unprivileged, D-050).

Dry run: nothing above was executed.
Log: /home/op/.local/state/hammunition/logs/20261003T125900Z-install-987576.log
```

How to read it, section by section.

**Target.** What the engine detected. If this is wrong, stop.

**Packages.** One line per unit, with where it came from in brackets:
`[profile satellite]` is a member you asked for, `[dependency of gr-satellites]`
is something a member needs, `[requested]` is a name you typed. The state is one
of:

| State | Meaning |
|---|---|
| `already installed` | Present, and for builds, attributed to this engine at the catalog's pinned version (D-051). Nothing to do. |
| `will install` | An apt package to be installed. The `+` lines are what apt will pull in. |
| `will build` | A source or git build. The `= name  (to build)` lines are the build dependencies apt installs first. |
| `will fetch+install` | A pinned download (a vendor `.deb`, a tarball) checked against its sha256 before it runs. |

A line starting `=` under a package is a dependency the plan checked against
apt's lists.

**Configuration that will be written.** Files the engine writes from your
station values, with the mode and whether an existing file is backed up first.
Here it fills gpredict's ground station from your grid square.

**Will NOT happen.** The most useful section. It lists what the transaction
will skip and why, and the rest of the transaction still runs. Each entry says
what, why, and the one command that fixes it (here, gpredict's rig file waits
for `--rig-device`). A deferral is never a failure. A profile member your
target's archive lacks appears here too, by name (D-039). On the navigation
profile with no regions chosen, the real plan says:

```text
Will NOT happen (the rest of the transaction still will):
  brouter-segments: will not be installed: it is map data for regions you have not chosen
      why: no map regions set
      → run `hammunition station set --map-regions <region>[,<region>…]` and install
      again. Everything else installs either way.
  comaps-maps: will not be installed: it is map data for regions you have not chosen
      why: no map regions set
      → run `hammunition station set --map-regions <region>[,<region>…]` and install
      again. Everything else installs either way.
```

**Records.** The transaction log the run will append to.

**Commands.** Every command, in order. `[fetch]`, `[config]`, `[wrapper]` and
the like are the engine's own steps, not shell. A `$ sudo ...` line is the only
kind that runs as root. Sources are fetched and hashed before any build runs.

**Afterwards.** The Hammunition desktop menu is rebuilt for you, per-user and
unprivileged (D-050).

**Dry run.** The last line says nothing above was executed, and the **Log** line
names the plain-text run log (step 12).

### Reading a plan that does more

A larger plan has more sections. These are from a real `hammunition install
morse --dry-run`:

```text
Installed distribution packages displaced or shadowed (D-022):
  pipewire-alsa  — declared by morse-classic; the distribution package stays installed, see that manifest's notes

apt packages installed without Recommends (D-052):
  morse-classic asked for --no-install-recommends in the manifest, because the
  Recommends of these packages conflict with software this target installs; a second
  apt-get install carries the flag for them alone. Everything else in this transaction
  keeps apt's defaults, and both commands run with --no-remove:
      morse

sudo (D-062):
  sudo's ticket is kept valid for the length of this transaction; it is not extended
  beyond it. The password is asked once, by `sudo -v`, before the first step; then `sudo
  -n -v`, which cannot prompt, refreshes the ticket every 4 minutes from this process
  until the run ends. If a refresh fails it is reported once and not retried, and the
  next root step asks as it would have. --no-sudo-keepalive turns this off.

Records:
  transaction log written to /home/op/.local/state/hammunition/transactions.jsonl

Commands (20):
  # Download and verify the flwkey source archive
  $ [fetch] https://w1hkj.org/files/flwkey/flwkey-1.2.4.tar.gz -> /home/op/.cache/hammunition/artifacts/e36e86788d7543261cd8f80...
  # Download and verify the ibp source archive
  $ [fetch] http://www.pa3fwm.nl/software/ibp/ibp-0.21.tgz -> /home/op/.cache/hammunition/artifacts/b3b118ca83619f0a5605652a0a8...
  # Refresh apt package lists
  $ sudo env DEBIAN_FRONTEND=noninteractive apt-get -o Acquire::Retries=3 update
  # Install 1 package(s) with apt without Recommends
  $ sudo env DEBIAN_FRONTEND=noninteractive apt-get -o Acquire::Retries=3 install --yes --no-remove --no-install-recommends -- ...
  # Clear any previous cwwav checkout
```

- **Installed distribution packages displaced or shadowed (D-022).** Where a
  unit coexists with a package your distribution already carries, the plan names
  it. The engine never silently removes a distribution choice.
- **apt packages installed without Recommends (D-052).** `morse` is installed
  with `--no-install-recommends` because its Recommends would have removed a
  PipeWire desktop's audio routing. The plan says so and shows the second `apt-get`
  command that carries the flag. Everything else keeps apt's defaults, and both
  commands run with `--no-remove`.
- **sudo (D-062).** When a plan mixes root steps with long unprivileged work, the
  engine asks for your password once, by `sudo -v`, before the first step, then
  refreshes the ticket every 4 minutes with `sudo -n -v`, which cannot prompt,
  until the run ends. A long map conversion would otherwise outlive sudo's 15
  minute cache and wait at a second prompt nobody is watching (issue #137). The
  engine never reads or stores the password. `--no-sudo-keepalive` turns it off.
- **Commands.** `apt-get update` comes first when there is apt work. Disable it
  with `--no-refresh` on a local mirror or an offline station.

A unit that does the same thing for hundreds of items (a map sheet, a terrain
tile, a Kiwix book) is printed once as a template with the first item written
out and every item's values on a line. `--dry-run --full` prints every step
expanded, and `--dry-run --json` always carries every step.

### Blockers

If the plan cannot be made, it says so before anything runs and exits with code
2. A name that is not in the catalog:

```sh
hammunition install nosuchprofile --dry-run
```

```text
1 problem block this transaction:
  nosuchprofile: is not a package or profile in the catalog
    → `hammunition list` shows everything the catalog contains

Nothing was changed. Resolution happens before installation so that a failure is a report rather than a half-installed machine (D-016).
Log: /home/op/.local/state/hammunition/logs/20261003T130511Z-install-1013361.log
```

Resolution happens before installation, so a failure is a report and not a
half-installed machine (D-016). The same section lists any other blocker, such
as a build tool the target lacks or a kernel subsystem the running kernel does
not provide (D-041).

## 9. The consent prompts

Two kinds of prompt exist, and `--yes` can answer neither.

**A profile consent gate (D-021).** Software whose capability, not its
difficulty, is the reason it is kept separate. Today that is `rf-research`. The
plan lists the gate it will present:

```sh
hammunition install rf-research --dry-run
```

```text
Consent gates that will be presented:
  rf-research (HAMMUNITION_ACCEPT_RF_RESEARCH)
      - unlicensed_transmission: Can cause connected hardware to emit radio frequency
        energy, including on frequencies, at power levels, or in modes that may require
        a licence or other authorization.
      - protected_communications: Can receive, decode, store or display communications
        that may be protected from interception.
      - identifier_collection: Can collect identifiers associated with people or their
        devices, such as IMSI, IMEI, MAC addresses, or subscriber records.
      - spectrum_disruption: Can degrade or deny service to other users of the radio
        spectrum, whether or not that is the intent.
```

`hammunition show rf-research` prints the full disclosure, ending with the
question *Do you affirm that you have the authorization you need for how you
intend to use this software?* Hammunition cannot know your location, licence
class or the terms of any authorisation you hold, and it does not give legal
advice. You are asked to affirm your own authorisation. A person types the
answer; or, in a script, sets the profile's variable (`HAMMUNITION_ACCEPT_RF_RESEARCH=1`).
`--yes` is accepted by the command and deliberately never read: a gate that a
convenience flag walks through is not a gate. With no terminal and no variable the
run stops with exit code 3.

**A third-party apt repository (D-040).** A unit that needs a publisher's
repository (VS Code, VSCodium, and Kismet on some targets) can only add one
when your archive offers nothing, and only after the plan has printed the
repository, the two files it will write
(`/etc/apt/sources.list.d/<name>.sources` and `/etc/apt/keyrings/<name>.gpg`) and
the key's **fingerprint**. The variable `HAMMUNITION_ACCEPT_APT_REPO_<NAME>` must
equal that fingerprint, not `1`. Checking the fingerprint against the
publisher's own page is the one step only you can do. Uninstalling removes both
files. On Parrot, `codium` comes from the distribution and no repository is
added.

**Other typed confirmations.** `hardware apply` asks for a typed `yes` before
installing the power-control helper if the interpreter it would run as root is
owned by a non-root account (the ordinary shape of a venv under `$HOME`). A
navigation selection over 10 GB asks you to type `yes`, and `--yes` does not
answer that either.

## 10. Run the install

When the plan reads the way you expect, run the same command without
`--dry-run`:

```sh
hammunition install station
```

What happens:

1. The plan prints again, identical to the dry run.
2. It asks `Proceed with the commands above?` and waits for you to type `yes`.
   `--yes` skips this one prompt and nothing else.
3. If the plan has root steps and is not already root, it runs `sudo -v` once,
   so your password is asked once, here, on the terminal.
4. Each command prints as `$ ...` as it runs and is logged before it starts and
   after it ends. A failure stops the run at that command.
5. After the last command, the engine **re-reads what it changed**. It asks apt
   again, checks the group database and checks that every installed binary
   exists and is executable. A command that exits 0 is not proof that it did
   anything, so the run is only reported clean when the effect is confirmed
   (D-031).
6. It prints `Done. N command(s) completed and confirmed.`, rebuilds your desktop
   menu, and, if it added you to a group, reminds you to log out and back in.

The exit codes:

| Code | Meaning |
|---|---|
| 0 | Every command ran and its effect was confirmed. |
| 1 | A command failed, or a completed command's effect could not be confirmed, or the system is unsupported. |
| 2 | The transaction could not be planned. Every blocker is printed. |
| 3 | A consent gate was declined or could not be presented. |

Install more than one thing in one run by naming them: `hammunition install
station digital-modes`. Names may be packages or profiles, freely mixed. A
re-run is safe: a unit already installed at its pinned version plans nothing, so
a second run of the same command prints `Nothing to do.`

Other flags you will meet: `--no-refresh` skips the opening `apt-get update`;
`--recheck` asks every data item's publisher again; `--no-mirror` ignores a LAN
mirror for the run; `--callsign`, `--grid-square` and `--node-alias` override the
saved value for one run.

## 11. Apply the hardware rules

Some devices need a udev rule so they open without root, and a group so you may
open them. `hardware apply` does both from the catalog. Plan it first:

```sh
hammunition hardware apply --dry-run
```

```text
Hardware setup for 'op'

Catalogued but deliberately not given a rule (see device-naming.md):
  airspy: no /dev/airspy symlink — serial_suffix is unset, meaning nobody has checked whether this device reports a serial. P...
  bladerf: no /dev/bladerf symlink — serial_suffix is unset, meaning nobody has checked whether this device reports a serial....
  fobos-sdr: no /dev/fobos-sdr symlink — serial_suffix is unset, meaning nobody has checked whether this device reports a ser...
  hydrasdr-rfone: no /dev/hydrasdr-rfone symlink — serial_suffix is unset, meaning nobody has checked whether this device rep...
  nfc-reader: no /dev/nfc symlink — serial_suffix is unset, meaning nobody has checked whether this device reports a serial. ...
  ubertooth-one: no /dev/ubertooth symlink — serial_suffix is unset, meaning nobody has checked whether this device reports a...

Nothing to do: the rules file already matches, you are in every access group, the power-control helper and its polkit action ...
The helper is hammunition-tray's (hammunition-devctl contract 1); this engine no longer writes it.
```

(This is real output from a laptop where the rules were already in place, so it
reports nothing to do. On a fresh machine it prints each command.) What it
writes:

| What | Where | Why |
|---|---|---|
| The whole catalog's udev rules | `/etc/udev/rules.d/65-hammunition.rules` | A rule is harmless for a device that is not attached, so applying all of them means a supported device works the moment you plug it in. |
| Your group memberships | `plugdev`, `dialout` | Device access. **Takes effect at your next login.** |
| A polkit action, and the helper behind it | `/usr/share/polkit-1/actions/com.chiefgyk3d.hammunition.devctl.policy` and `/usr/local/libexec/hammunition-devctl` | Lets the tray and `hardware park` and `wake` switch a device off and on. The helper now belongs to hammunition-tray and is left alone when it is already there. |
| Where ntpsec is the time daemon: two grants and a gpsd drop-in | `/etc/systemd/system/ntpsec.service.d/hammunition-gps.conf`, an AppArmor local rule, `/etc/systemd/system/gpsd.service.d/hammunition-gps.conf` | So the clock can follow a GPS. The plan says plainly that `CAP_IPC_OWNER` bypasses permission checks on System V IPC. `--no-gps-time` leaves it out. |
| GeoClue's GPS socket | a `conf.d` drop-in and a tmpfiles line for `/run/hammunition-gps` | For the offline maps. `--no-geoclue` leaves it out. |

Run it:

```sh
hammunition hardware apply
```

**Log out and back in afterward.** A group you were just added to does not
reach a session that is already open, which is why a dongle that works under
`sudo` and not otherwise is nearly always this.

**Inspect it.** `cat /etc/udev/rules.d/65-hammunition.rules`, `id` for your
groups, `systemctl cat gpsd` for the drop-in, and `hammunition doctor` for the
`udev rules`, `device groups` and `time` lines.

**Reverse it.** `hammunition hardware unapply --dry-run`, then without
`--dry-run`. It removes the power-control helper and polkit action and the GPS
time files, and leaves the udev rules file alone, because it is declarative and
removing it would take away access you are still using. A group membership is
recorded but not reversed.

To see what is attached and what each device needs, `hammunition hardware list`.
[The hardware pages](../hardware/index.md) cover each device.

## 12. See what was done

```sh
hammunition status
hammunition logs
hammunition transactions
```

`status` shows the most recent transaction and how it ended: completed, failed
after N commands, or interrupted. It also lists what that run deferred by
design, so a profile that landed eighteen of twenty-two still reads that way a
week later.

`logs` lists the plain-text log each run left behind (D-077): when it started,
which command, its size and how it ended.

```text
5 run log(s) in /home/op/.local/state/hammunition/logs (59 KB; keeps at most 30 files and 0.21 GB):
  2026-10-03 12:59:10 UTC  hardware-apply              2 KB  ok
  2026-10-03 12:59:05 UTC  install                    23 KB  ok
  2026-10-03 12:59:02 UTC  install                     5 KB  ok
  2026-10-03 12:59:00 UTC  install                     6 KB  ok
  2026-10-03 12:58:56 UTC  install                    23 KB  ok
`hammunition logs --last` prints the newest; `--path` prints where it is.
```

`hammunition logs --last` prints the newest in full, and `hammunition logs
--path` prints where it is, for `tail -f` while a long run is going. It holds
each command with its output and exit code, is mode 0600, and records station
flags redacted. At most 30 files and 200 MB are kept. `transactions` is the full
history, oldest first, and is the record `uninstall` reads. Both files are in
`~/.local/state/hammunition/`. See [Run logs](../reference/run-logs.md) and
[the transaction log](../reference/transaction-log.md).

## 13. Keep it current

```sh
hammunition update
```

`update` is a report. It compares what you have installed to the catalog and
runs nothing. Apt units are compared to the local package lists, and built units
to the version the catalog pins, with the age of your lists shown.

```text
Target: Parrot Security 7.4 (echo) (ID=parrot, version=7.4, arch=x86_64)
Nothing to compare: the transaction log records no install request here (/home/op/.local/state/hammunition/transactions.jsonl). Name units or profiles to compare them anyway.
Log: /home/op/.local/state/hammunition/logs/20261003T125911Z-update-988209.log
```

(The real output on a machine with history lists each unit. This one has none
yet, because it is the scratch state used for these captures.) The states are
`up to date`, `candidate differs`, `behind the pin`, `not installed`, `unknown`,
`re-checked on install` and `manual`. For a unit that is behind its pin, it
prints the `hammunition install` command that rebuilds it. `--upstream` opts in
to asking GitHub, git tags, PyPI or a version file whether the pin itself is
current.

To update the engine and catalog, `git pull` in the checkout and run
`./bootstrap.sh` again. To upgrade apt packages, run your usual `sudo apt update
&& sudo apt full-upgrade`.

## 14. Take it off again

```sh
hammunition uninstall satellite --dry-run
```

```text
Target: Parrot Security 7.4 (echo) (ID=parrot, version=7.4, arch=x86_64)


Removing artifacts (4):
  gr-satellites                wrapper        /home/op/.local/bin/gr_satellites-list  [marker]
  gr-satellites                desktop-entry  /home/op/.local/share/applications/hammunition-gr_satellites-list.desktop  [marker]
  libhamlib-utils              wrapper        /home/op/.local/bin/rigctl-dummy  [marker]
  libhamlib-utils              desktop-entry  /home/op/.local/share/applications/hammunition-rigctl-dummy.desktop  [marker]

Left in place — installed, but not installed by Hammunition:
  gpredict                     gpredict
  gr-satellites                gr-satellites
  satdump                      satdump
  libhamlib-utils              libhamlib-utils

Not reversed, by design: dependencies apt pulled in (run `sudo apt autoremove` to clear orphans), group memberships, and any co...

Commands (4):
  # Remove gr-satellites's wrapper (only if ours)
  $ [remove-wrapper] /home/op/.local/bin/gr_satellites-list
  # Remove gr-satellites's desktop-entry (only if ours)
  $ [remove-desktop-entry] /home/op/.local/share/applications/hammunition-gr_satellites-list.desktop
  # Remove libhamlib-utils's wrapper (only if ours)
  $ [remove-wrapper] /home/op/.local/bin/rigctl-dummy
  # Remove libhamlib-utils's desktop-entry (only if ours)
  $ [remove-desktop-entry] /home/op/.local/share/applications/hammunition-rigctl-dummy.desktop

Dry run: nothing above was executed.
Log: /home/op/.local/state/hammunition/logs/20261003T125913Z-uninstall-988260.log
```

`uninstall` removes what Hammunition itself installed, read from the transaction
log, and nothing else. In this real example the profile's packages were already
on the machine before the engine touched it, so they appear under *Left in
place*: removing them would exceed the promise. Run it without `--dry-run` to do
it. It removes apt packages with `apt-get remove`, never `purge`, so a
configuration file you edited stays. Wrappers and desktop entries are only
removed if they carry the engine's marker.

It does not reverse, and says so in every plan: dependencies apt pulled in
(`sudo apt autoremove` clears orphans), group memberships and configuration
files it wrote. Afterward it re-checks that what it removed is gone.

A source or git build that ran a real `make install` into `/usr/local` is
refused by name: there is no file manifest to reverse, and a file sweep that
pretended otherwise would be a lie. Hammunition does not roll back. It tells you
what it did.

## 15. Where everything lands

| What | Where |
|---|---|
| The engine and its virtualenv | The checkout you cloned, in `.venv` |
| The `hammunition` link | `~/.local/bin/hammunition` |
| Your station values | `~/.config/hammunition/station.yml`, mode 0600 |
| The transaction log | `~/.local/state/hammunition/transactions.jsonl` |
| Run logs | `~/.local/state/hammunition/logs/`, 30 files at most |
| Downloaded artifacts and build trees | `~/.cache/hammunition/` (`artifacts/`, `build/`). Safe to delete between runs; they are rebuilt. |
| Source builds and prebuilt trees | `/usr/local`, owned by root unless the plan hands a tree to you (D-043) |
| Offline data (maps, books, terrain) | `/usr/local/share/hammunition/data/` |
| Per-user launchers and menu entries | `~/.local/bin/` and `~/.local/share/applications/` |
| Python venv units | `~/.local/share/hammunition/venvs/` |
| udev rules | `/etc/udev/rules.d/65-hammunition.rules` |
| Third-party apt repositories (only if you affirmed one) | `/etc/apt/sources.list.d/<name>.sources` and `/etc/apt/keyrings/<name>.gpg` |

Run under `sudo`, the engine still writes to the invoking user's home, never
root's. The plan's **Records** section names the exact path it will use.

## 16. When something fails

1. **Read the last lines.** A failed run prints `Failed:` with the command and
   its error, and the log's location. Nothing after the failed command ran.
2. **Run `hammunition doctor`.** It turns most causes into a named fix.
3. **Open the run log.** `hammunition logs --last` has every command with its
   output and exit code.
4. **Look up the symptom.** [Troubleshooting](../troubleshooting/index.md) is
   organised by what you see. *Installing* covers a plan that hangs, a publisher
   that is not answering, a 404 on a source URL, a held-broken apt on Parrot, a
   `python3 -m venv` failure and a package that is refused by name. *Running*
   covers a program that installed but misbehaves: blank GUIs on Wayland,
   serial permission denied, a clock that breaks FT8.
5. **A 404 from apt** means your package lists are older than the archive. The
   engine refreshes them by default for this reason; the remedy is `sudo apt-get
   update`, or the same run without `--no-refresh`.
6. **Ask for help** with the output of `hammunition doctor` and the run log.
   Remove your callsign and grid square first; both are redacted from the log's
   argv but not from every file a program writes.

A failed or interrupted install is safe to re-run. Units already installed at
their pin plan nothing, and a build whose transaction never verified is rebuilt
because nothing confirmed it.

## 17. Differences on other systems

Steps 3 to 16 are the same everywhere. What differs is below. See step 2 for the
measured status of each.

### Debian 13

- A **netinst** has no `python3-venv`. Install it first with `sudo apt install
  python3-venv`, or let bootstrap do it.
- GNOME is the default desktop. The app-folder menu is written for it and has
  not been looked at on GNOME since the menu was rebuilt (D-036). Run
  `hammunition menus apply --gnome` to ask for it.
- A few members are not in Debian 13's archive; the plan defers them by name.

### Ubuntu 24.04 and Linux Mint 22.3

- Mint installs from Ubuntu 24.04's archive, so the same members are missing.
- 24.04's Node.js is 18.19, below the 20.19 that `openhamclock` needs, so the
  `propagation` profile defers it by name and installs the rest.
- Qt 6.4 is below DroidStar's 6.5 floor, so `digital-modes` installs without it.
- Several decoders (`readsb`, `rtl-ais`, `satdump`, `mlat-client-adsbfi`) have no
  archive candidate and are deferred in `listening` and `satellite`.
- Mint's Cinnamon is a desktop the tray supports through `hammunition-tray-qt`.

### Ubuntu 26.04

- Fewer members are missing than on 24.04 (9 refused at plan time against 19 in
  the 2026-09-02 campaign). `gr-gsm` was not in the archive then, so
  `rf-research` defers it by name.

### Kali rolling

- Kali ships `python3-venv` (measured on the Kali VM, 2026-08-29).
- Its current kernel has no `ax25.ko`, so the kernel AX.25 stack defers. The
  userspace packet route (Direwolf with Pat) does not need it and works.
- `arduino-cli` and `soapysdr-module-plutosdr` have an install block only for
  Kali. On the 2026-08-29 Kali VM, `sdrpp` also arrived by apt where other
  targets build it.
- Never add Kali's apt archive to another distribution; the engine never does.

### Pop!_OS 24.04

- Not a declared target, so the engine reads it as Ubuntu-like through
  `ID_LIKE`. The Ubuntu 24.04 notes apply. See the Pop campaign for what failed
  and was fixed.

### Raspberry Pi OS

- Use the 64-bit image. The arm64 target is Debian 13's.
- Source builds are slow on a Pi. Allow time and a heat-sinked board, and keep
  an eye on memory: the engine sizes build parallelism to your CPUs and memory.
  A four-core Pi with 4 GB is the shape the sizing notes describe.
- Some units have no arm64 block and are deferred by name. Nothing here has been
  run on Pi hardware, so treat the first install as a measurement and tell us
  what happened.

### A system the engine does not know

If `/etc/os-release` names a system that is not Debian-family, `hammunition
status` says `Debian family: no` and installs refuse. If it is a Debian
derivative that declares itself oddly, `hammunition doctor` shows exactly what it
read.

## Next

- [Your first profile](first-profile.md) walks the same ground in less words,
  from `station` to a mode profile.
- [Profiles](../profiles/index.md): all nineteen, what each installs and leaves
  out, and which one you want for your goal.
- [The guides](../guides/index.md): rig control, radio audio and the clock first,
  then FT8, Winlink, APRS, SDR listening and satellites.
- [Troubleshooting](../troubleshooting/index.md), by symptom.
- [The command line reference](../reference/cli.md): every verb and flag.
