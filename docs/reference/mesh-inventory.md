# Mesh and Reticulum inventory (Track C)

**Measured:** 2026-10-03 (UTC), network reads and one scratch virtualenv per tool;
nothing was installed outside a throwaway environment and nothing was run against a
radio or a node.
**For:** `docs/SCOPE.md` Track C and issue #105.
**Status:** evidence for the manifests that follow, not a manifest. Every figure
carries the command beside it, and a pin goes stale in days (see the cadence figure
under Reticulum), so none of these versions should be copied into a unit without
being re-read that day.

The method follows `docs/reference/etc-inventory.md`: the figure comes from the
source, the command is stated, and what could not be measured is listed at the end.

## Headline

| Finding | Figure |
|---|---|
| The Reticulum stack (`rns`, `lxmf`, `nomadnet`, `sbapp`, `lxst`) is in **no** apt archive on any of our seven targets | 0 of 5 names, checked on 7 targets |
| Reticulum's own licence is not OSI: field-of-use restrictions on harm and on AI training | `rns` and `lxmf` ship it; Sideband is CC BY-NC-SA 4.0, LXST CC BY-NC-ND 4.0 |
| Meshtastic's Linux daemon `meshtasticd` is in **no** distribution archive; it comes from an OBS repository (Debian and Raspbian) and a Launchpad PPA (Ubuntu) | two signing keys, two fingerprints, both read |
| Sideband installs from one 65 MB wheel, but the closure is **293 MB** installed, and on arm64 one dependency (`materialyoucolor`) has no wheel, so it builds from sdist | measured below |
| The pure-Python tools are small: `rns` 20 MB, `lxmf` 20 MB, NomadNet 27 MB, MeshCore's `meshcore-cli` 19 MB | `du -sh` of a scratch venv |
| MeshCore's tooling is MIT throughout and `meshcore-cli` plus `python-meshcore` sit in Debian **sid** only | not in trixie, not in Ubuntu 24.04 or 26.04 |
| `python3-meshtastic` is carried by Debian 13, Parrot, Kali and Ubuntu 26.04 but not by Ubuntu 24.04 | and Debian's 2.7.11-1 carries an autoremoval notice dated 2026-11-03 |

## 1. The Reticulum ecosystem on PyPI

Measured on 2026-10-03 with `GET https://pypi.org/pypi/<name>/json` for each name,
`gh api repos/<owner>/<repo>/commits?per_page=1` for the head commit of the default
branch (D-032: never `updated_at`), and a scratch virtualenv per tool
(`uv venv --python 3.13` then `uv pip install <name>`, Python 3.13.5, `du -sh` of the
whole environment).

| Package | Version | Released | PyPI licence field | Licence file shipped | Python floor | Venv size | Repo head commit |
|---|---|---|---|---|---|---|---|
| `rns` | 1.5.6 | 2026-10-02 | `Reticulum License` (free text, no classifier) | none in the wheel's `.dist-info`; repo `LICENSE` is the Reticulum License | 3.8 or lower | 20 MB | 2026-09-30 |
| `lxmf` | 1.2.0 | 2026-09-30 | `Reticulum License` | none in the wheel; repo `LICENSE` is the Reticulum License | 3.8 or lower | 20 MB | 2026-09-30 |
| `nomadnet` | 1.4.4 | 2026-09-30 | classifier `OSI Approved :: MIT License` | GNU GPL v3 (in the wheel and in the repo) | 3.9 | 27 MB | 2026-09-30 |
| `sbapp` (Sideband) | 2.2.0 | 2026-10-01 | classifier `Other/Proprietary License` | CC BY-NC-SA 4.0 | 3.11 (via `lxst`) | 293 MB | 2026-10-01 |
| `lxst` | 0.5.4 | 2026-10-01 | classifier `Other/Proprietary License` | CC BY-NC-ND 4.0 | 3.11 | 90 MB | 2026-09-26 |
| `rnsh` (PyPI, author `acehoss`) | 0.1.7 | 2025-10-17 | `MIT` | MIT | 3.8 or lower | 20 MB | 2026-01-12 (repo `acehoss/rnsh`, not archived) |
| `rnspure` | 1.5.6 | 2026-10-02 | `Reticulum License` | not read | not read | not measured | not read |

How the Python floor was measured: the oldest `--python-version` (lowest tried: 3.8) at which
`uv pip compile` resolves the pinned release (`rns==1.5.6` and so on), not the
`requires_python` string, which says 3.7 for `rns`, `lxmf` and `sbapp`. `sbapp` and
`lxst` resolve only from 3.11 because `lxst` declares `>=3.11`.

Console scripts found in the scratch venvs (`ls bin/`): `rns` installs `rnsd`,
`rnstatus`, `rnpath`, `rnprobe`, `rnodeconf`, `rncp`, `rnx`, `rnid`, `rnir`, `rnpkg`,
`rngit`, `rngcs`, `git-remote-rns` and **`rnsh`**; `lxmf` adds `lxmd`; `nomadnet`
adds `nomadnet` and `qr`; `sbapp` adds `sideband` and, through `lxst`, `rnphone`.

**`rnsh` is now inside `rns`.** `rns` 1.5.6 installs `RNS.Utilities.rnsh` and the
`rnsh` script, and the separate PyPI `rnsh` 0.1.7 (last release 2025-10-17) installs
a script of the same name from a different package. Installing both in one
environment gives one command two owners. A unit for remote shell should be `rns`,
not the PyPI `rnsh`.

**Release cadence.** `rns` has 144 releases on PyPI since 2020-04-27, three of them
in the 21 days from 2026-09-11 to 2026-10-02 (1.5.4, 1.5.5, 1.5.6); GitHub's latest
*release* for `markqvist/Reticulum` is 1.5.5 (2026-09-29), one behind PyPI
(`gh api repos/markqvist/Reticulum/releases/latest`). `lxmf` (75 releases), `nomadnet`
(97), `sbapp` (74) and `lxst` (22, first 2025-02-24) are moving at the same rate.
`lxmf>=1.2.0`, `nomadnet>=1.4.4` and `sbapp>=2.2.0` each demand `rns>=1.5.5`, so a
pin set has to move as a set.

### The licence finding

`rns` and `lxmf` are under the **Reticulum License**, a new licence that is not on the
OSI list and not an SPDX identifier (GitHub reports `NOASSERTION` for both repos). It
is the MIT text plus two added conditions, quoted from
[`markqvist/Reticulum/LICENSE`](https://github.com/markqvist/Reticulum/blob/master/LICENSE):

> - The Software shall not be used in any kind of system which includes amongst its
>   functions the ability to purposefully do harm to human beings.
> - The Software shall not be used, directly or indirectly, in the creation of an
>   artificial intelligence, machine learning or language model training dataset,
>   including but not limited to any use that contributes to the training or
>   development of such a model or algorithm.

Read by `diff` against the Reticulum copy: `lxmf`'s `LICENSE` differs only in the
copyright years (`2020-2025` rather than `2016-2026`). (`gh api
repos/markqvist/<repo>/contents/LICENSE`, 2026-10-03.)

The other two first-party applications are not under it:

| Package | Licence as shipped | What the README adds |
|---|---|---|
| Sideband | Creative Commons Attribution-NonCommercial-ShareAlike 4.0 | "Permission is hereby granted to use Sideband in binary form, for any and all purposes, and to freely distribute binary copies of the program, so long as no payment or compensation is charged or received for such distribution or use." |
| LXST | Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 | "You can deploy LXST freely for non-commercial, personal and humanitarian purposes. For commercial (including institutionalised educational) licensing, contact me." |
| NomadNet | the wheel says MIT in its classifiers and ships the GNU GPL v3 text; GitHub reports `GPL-3.0` | not read; the two statements disagree and this page does not pick one |

Two further measured facts: the Sideband and LXST READMEs both open with a notice
that several "LLM-generated fakes" of the projects are circulating and that grants
those make are "not recognized by the Sideband author" (`gh api repos/markqvist/<repo>/readme`,
2026-10-03); and `rnsh` (MIT) and every `meshcore`/`meshtastic` package below are
OSI-licensed, so the line between an OSI unit and a restricted one falls *inside* the
Reticulum family.

This is the D-033 situation with a different shape: the licence is present, it is
unusual, and it limits fields of use rather than granting nothing. The catalog names
URLs and digests and does not redistribute, and a venv unit fetches from PyPI onto
the operator's machine, which is the same posture as any D-033 unit. Whether the
Reticulum License's two clauses, and the two Creative Commons non-commercial
licences, change that is a ruling for the maintainer; this page records the text and
does not rule.

### Dependency closure

The closure is pinned with hashes the way the venv backend wants them
(`catalog/packages/artemis.yaml` is the shape: `requirements:` entries of
`name==version  --hash=sha256:...`). The full sets, one section per tool, are in
`docs/reference/mesh-venv-closures.txt`; this table is the summary.

Measured with `uv pip compile --python-platform x86_64-unknown-linux-gnu
--python-version 3.11 --generate-hashes --no-header --no-annotate -` on 2026-10-03
(uv 0.12.23, fed `<name>==<version>`). Hashes cover every file PyPI lists for each
pinned release, so one pin verifies on amd64 and arm64.

| Tool | Pinned packages | Hashes | Direct dependencies (PyPI `requires_dist`) |
|---|---:|---:|---|
| `rns` 1.5.6 | 5 | 165 | `cryptography>=3.4.7`, `pyserial>=3.5` |
| `lxmf` 1.2.0 | 6 | 167 | `rns>=1.5.5` |
| `nomadnet` 1.4.4 | 11 | 196 | `rns`, `lxmf`, `urwid>=3.0.5`, `qrcode` |
| `rnsh` 0.1.7 | 6 | 167 | `rns>=0.9.0` |
| `lxst` 0.5.4 | 9 | 270 | `rns`, `lxmf`, `numpy>=2.3.4`, `pycodec2>=4.1.0`, `cffi>=2.0.0`, `audioop-lts` (3.13+) |
| `sbapp` 2.2.0 | 27 | 637 | `rns`, `lxmf`, `lxst`, `kivy>=2.3.0`, `numpy`, `pillow`, `mistune`, `qrcode`, `materialyoucolor>=2.0.7`, `beautifulsoup4`, `pycodec2` |

`rns`, `lxmf` and `nomadnet` in one environment (the likely shape of a single
"Reticulum" unit) measured **27 MB** and 11 installed packages
(`uv pip install rns lxmf nomadnet`, `du -sh`). The closures were compiled for
Python 3.11 and the sizes installed on 3.13.5, so a pin set resolved for one is not
byte-identical to the other: `numpy` is 2.4.6 in the 3.11 closure and 2.5.3 in the
3.13 install.

### Wheels, architectures and Sideband's weight

Checked with `uv pip compile --only-binary :all: --python-platform <platform>
--python-version 3.13` for `x86_64-unknown-linux-gnu` and `aarch64-unknown-linux-gnu`:

| Tool | amd64, wheels only | arm64, wheels only |
|---|---|---|
| `rns`, `lxmf`, `nomadnet`, `rnsh`, `lxst`, `meshcore`, `meshcore-cli` | resolves | resolves |
| `sbapp` 2.2.0 | resolves | **does not**: `materialyoucolor` 3.0.4 publishes `manylinux_2_28_x86_64` wheels only; the resolver falls back to `sbapp` 0.7.9 |
| `meshtastic[cli]` 2.7.11 | does not: `pyqrcode` 1.2.1 is sdist-only | same |
| `esptool` 5.4.0 | does not: PyPI carries the sdist only | same |

So on arm64 Sideband builds `materialyoucolor` from its sdist. That sdist's
`pyproject.toml` requires `setuptools>=61`, `wheel` and `pybind11>=2.11.0`, i.e. a C++
compiler and Python headers on the target (not built here; `python3-dev` and
`build-essential` are in the Parrot archive at 3.13.5-1 and 12.12). Raspberry Pi OS
64-bit, the uConsole and any other arm64 desktop are affected. The sdist-only
`pyqrcode` and `esptool` are pure Python and build without a compiler.

What makes Sideband heavy, from `du -s` of the 293 MB scratch venv:
`sbapp` itself 95 MB (of which `assets` 62 MB and `share` 26 MB), `kivy` 69 MB,
`numpy` 30 MB plus its `numpy.libs` 26 MB, `cryptography` 15 MB, `pillow.libs`
13 MB, `LXST` 10 MB, `Kivy.libs` 7 MB. The Kivy wheel bundles SDL2, SDL2_image,
SDL2_mixer, SDL2_ttf and libpng (`ls Kivy.libs`). `ldd` over every `kivy/**/*.so`
reported no missing library on this machine; the OpenGL driver is loaded at run time
and was not measured (no GUI was launched). Debian's own `python3-kivy` 2.3.1-1+b1
declares `libgl1`, `libsdl2-2.0-0`, `libsdl2-image-2.0-0`, `libsdl2-mixer-2.0-0`,
`libsdl2-ttf-2.0-0`, `libfontconfig1`, `libfreetype6`, `libglib2.0-0t64`,
`libgstreamer1.0-0`, `libpango-1.0-0`, `libpangoft2-1.0-0`, `python3-gst-1.0`,
`fonts-dejavu-core`, `fonts-roboto` (`apt-cache depends python3-kivy`), which is the
list to start from for the system packages a wheel-based Sideband still wants at
run time.

Sideband also publishes `Sideband_2.2.0_x86_64.appimage` (151 MB) and
`Sideband_2.2.0_aarch64.appimage` (160 MB) as release assets, next to the 65 MB wheel
and an Android APK, each with a `.rsg` signature file (`gh api
repos/markqvist/Sideband/releases`); AppImage is post-1.0 in this project
(`docs/SCOPE.md`). Reticulum MeshChat (`liamcottle/reticulum-meshchat`, MIT, head
commit 2026-08-15, v2.4.0 released 2026-07-06) has **no PyPI package**
(`pypi.org/pypi/reticulum-meshchat/json` returns 404) and ships Linux only as
`ReticulumMeshChat-v2.4.0-linux.AppImage`, 154 MB; it is the unit already
dispositioned ADD (post-1.0) in `docs/reference/dispositions.md`.

### RNode and the other first-party pieces

- `rnodeconf` is part of `rns` (above). `HOME=<scratch> rnodeconf --help` lists
  `--autoinstall`, `--update`, `--fw-url url`, `--nocheck`, `--flash`, `--key` and
  `--firmware-hash`: it downloads firmware itself unless told otherwise. Where it
  fetches from and whether it verifies anything was **not** measured; it is the
  first thing to read before a unit exposes it, per D-024 and the "never pipe or
  trust an unverified fetch" rule.
- `markqvist/rnode-flasher` (MIT, not archived, head commit 2025-11-10) is a single
  `RNode_Flasher.html` plus a build script: a browser page, no package.
- `markqvist/RNode_Firmware` (GPL-3.0, head commit 2026-09-27) is the firmware source.
- PyPI first-party names checked and **not present**: `rnode-flasher`,
  `reticulum-meshchat`, `rnphone`, `rncp` (HTTP 404). `rnspure` exists (see table).
- The 71 repositories under `github.com/markqvist` were listed (`gh api
  users/markqvist/repos`); beyond those above, the relevant ones for a radio person
  are `tncattach`, `LXMF-Tools`, `lxmf_messageboard`, `reticulum-cpp`, `Retipedia`
  and `rnodeconfigutil`, none read here.

## 2. Which of these are in a Debian-family archive

Measured 2026-10-03. This machine (Parrot 7.4, `echo`): `apt-cache madison <name> |
wc -l` returned 0 for `rns`, `python3-rns`, `nomadnet`, `lxmf`, `python3-lxmf`,
`sideband`, `meshtasticd`, `meshcore`, `python3-meshcore`, `meshcore-cli`,
`reticulum`, `python3-reticulum`, `rnsh`. Debian by `GET
sources.debian.org/api/src/<name>/`; Ubuntu by Launchpad's `getPublishedSources` on
the primary archive (`status=Published`, `exact_match=true`); Kali by reading
`kali-rolling/main/binary-amd64/Packages.gz` (71,447 stanzas); Raspberry Pi OS's own
archive by reading `archive.raspberrypi.com/debian/dists/{bookworm,trixie}/main/binary-arm64/Packages.gz`
(2,113 and 1,471 stanzas). Ubuntu series: noble is 24.04, resolute 26.04, stonking
the development series after it.

| Package | Parrot 7 (echo) | Debian 13 | Ubuntu 24.04 | Ubuntu 26.04 | Kali rolling | Raspberry Pi OS | Pop!_OS 24.04 |
|---|---|---|---|---|---|---|---|
| `rns`, `lxmf`, `nomadnet`, `sideband`, `rnsh` | none | none | none | none | none | none | none |
| `meshtasticd` | none | none | none | none | none | none | none |
| `python3-meshtastic` (source `meshtastic`) | 2.6.0-1 | 2.6.0-1 (forky/sid 2.7.11-1) | **none** (first published in plucky) | 2.7.7-1 | 2.7.11-1 | none of its own, takes Debian's | none by inheritance |
| `gtk-meshtastic-client` | not read | 1.2-1 (forky/sid 1.5-1) | not read | 1.4-1 | not read | not read | not read |
| `meshcore-cli` and source `python-meshcore` (binary `python3-meshcore`) | none | **none** (sid only: 1.5.7-2 and 2.3.7-3) | none | none (stonking only, same versions) | none | none | none |
| `esptool` | 4.7.0+dfsg-0.1 | 4.7.0+dfsg-0.1 | 4.7.0+dfsg-0.1 | 4.7.0+dfsg-0.2 | 4.7.0+dfsg-0.2 | none of its own, takes Debian's | none by inheritance |
| `python3-kivy` | 2.3.1-1+b1 | 2.3.1-1 | not read | not read | 2.3.1-3+b1 | not read | not read |

"Takes Debian's" and "none by inheritance": Raspberry Pi OS and Pop!_OS layer their
own archive over Debian and Ubuntu respectively and the rows are those bases' rows.
Pop!_OS's own archive could not be read (`apt.pop-os.org/release/dists/noble/main/binary-amd64/Packages.xz`
returned 404), so the entry says "by inheritance" and nothing about System76 packages.
Raspberry Pi OS's own archive was read for arm64 only.

**The `python3-meshtastic` autoremoval.** `GET
udd.debian.org/cgi-bin/autoremovals.yaml.cgi` (read 2026-10-03T21:29Z) lists source
`meshtastic` 2.7.11-1 with `removal_date: 2026-11-03`, `dependencies_only: true`,
`buggy_dependencies: [python-anyio]`, `bugs_dependencies: ['1148561']`. The notice
covers the testing/unstable build; trixie's 2.6.0-1 (what Parrot and Debian 13 carry)
is not on that list, and Kali's rolling archive carries 2.7.11-1 today. Upstream PyPI
is at 2.7.11 (released 2026-07-17), so Debian 13 and Parrot are one minor behind
and the manifest already says so. `python3-meshtastic` is also **not available** on
Ubuntu 24.04 and Pop!_OS 24.04: it is absent, and the PyPI route
(`meshtastic[cli]` 2.7.11, 20 pinned packages, 339 hashes, 14 MB) is the one that
works there.

## 3. Meshtastic on Linux

### `meshtasticd` and its repositories

`meshtasticd` is the Linux-native Meshtastic node daemon. Neither Debian, Ubuntu nor
Kali carries it (section 2). Upstream publishes it in two places.

**openSUSE Build Service**, `https://download.opensuse.org/repositories/network:/Meshtastic:/<channel>/<release>/`,
read on 2026-10-03 by listing each directory and each `Packages.gz`. Channels are
`beta`, `alpha` and `daily` (plus a `build-tools` project); there is no channel called
`stable`. Releases published in each channel: `Debian_12`, `Debian_13`,
`Debian_Testing`, `Debian_Unstable`, `Raspbian_12`, `Raspbian_13`. **No Ubuntu
directory exists.**

| Channel | `Debian_13` version | `Debian_Testing` | Architectures on `Debian_13` |
|---|---|---|---|
| `beta` | 2.7.26.61~obs54e0d8d~beta | same | amd64, arm64, armhf, i386, ppc64el |
| `alpha` | 2.8.1.64~obs8e6a88d~alpha | same | same |
| `daily` | 2.8.1.752~obs790944a~unstable | 2.8.1.753~obsf5940ab~unstable | same |

`Debian_Unstable` lags (`beta` 2.7.15, `alpha` 2.7.16, `daily` 2.7.17) and carries
amd64, arm64 and ppc64el only. `Raspbian_13` carries armhf only, `Raspbian_12` arm64
and armhf. The `Debian_13` amd64 `.deb` for `beta` was downloaded (`curl -L`, 2,140,624
bytes) and its SHA-256, `324fd99ede031c662c2f483b9fd6ed82f238ee94143d5d6b473f51da53bf2104`,
equals the `SHA256:` in the repository's `Packages` index. It was unpacked with
`dpkg-deb -x` and never installed.

**Launchpad PPA**, for Ubuntu: `ppa:meshtastic/beta`, `ppa:meshtastic/alpha`,
`ppa:meshtastic/daily` (`GET api.launchpad.net/devel/~meshtastic/+archive/ubuntu/<channel>`
and `?ws.op=getPublishedSources&source_name=meshtasticd&status=Published`):

| PPA | jammy (22.04) | noble (24.04) | resolute (26.04) | other |
|---|---|---|---|---|
| beta | 2.7.26.61~ppa54e0d8d | same | same | questing |
| alpha | 2.8.1.64~ppa8e6a88d | same | same | stonking |
| daily | 2.8.2.757~ppa8b8dc61 | same | same | stonking |

Pop!_OS 24.04 is noble-based, so the noble PPA row is the one that applies. No PPA row
was installed or verified against Pop!_OS.

Which of our targets each reaches:

| Target | Source | Notes |
|---|---|---|
| Parrot 7 (Debian 13) | OBS `Debian_13`, amd64 | every `Depends:` has a candidate on this Parrot 7.4 machine (`apt-cache policy`, 14 packages, `libxkbcommon0` from backports) |
| Debian 13 | OBS `Debian_13` | same |
| Ubuntu 24.04, Pop!_OS 24.04 | PPA, noble | |
| Ubuntu 26.04 | PPA, resolute | |
| Kali rolling | OBS `Debian_Testing` is the nearest | Kali is not a listed release; not measured on Kali |
| Raspberry Pi OS | OBS `Raspbian_12`/`Raspbian_13` or `Debian_13` arm64 | `Raspbian_13` is armhf only; 64-bit Pi OS on trixie uses the `Debian_13` arm64 packages; neither was run |

**Signing keys, for D-040.** Both read on 2026-10-03.

| Repository | Full fingerprint | How read |
|---|---|---|
| OBS, all three channels (`Release.key` byte-identical across them, sha256 prefix `d546e147623ed42f`) | `426AA6B0285C2096B70D9FC2528423A469A77D9A` | `gpg --show-keys --with-colons` and `hammunition.openpgp.primary_fingerprints(...)` agree; uid `network OBS Project`, RSA 4096, created 2025-06-17, **expires 2027-08-26** |
| Launchpad PPAs, all three (same key) | `5E0A0F83F3DDE7AC55915B14F40C93FFA2CD17E3` | the Launchpad API's `signing_key_fingerprint`, then `keyserver.ubuntu.com/pks/lookup?op=get` read with `gpg --show-keys`: uid `Launchpad PPA for Meshtastic`, same fingerprint |

The OBS key belongs to the whole `network` project, not to Meshtastic's sub-project,
and it expires within a year: a pin carried in a manifest should record the expiry so
`update --upstream` can flag it. A unit that pins the OBS key is the D-040 case with
the archive offering nothing on any target.

### What `meshtasticd` installs, and what it assumes

From the `beta` amd64 `.deb` above, unpacked, never run:

- Installed size 9,395 KB; `Depends:` `adduser`, `libc6`, `libgcc-s1`, `libgpiod3`,
  `libi2c0`, `libinput10`, `liborcania2.3`, `libsdl2-2.0-0`, `libssl3t64`,
  `libstdc++6`, `libulfius2.7t64`, `libusb-1.0-0`, `libuv1t64`, `libx11-6`,
  `libxkbcommon0`, `libyaml-cpp0.8`.
- A systemd service `meshtasticd.service`, `User=meshtasticd`, `Restart=always`,
  `AmbientCapabilities=CAP_NET_BIND_SERVICE`, whose start script takes an optional
  instance id (`meshtasticd@<id>`). The `postinst` calls `deb-systemd-helper
  unmask` and `enable`, so installing the package enables a boot-time service.
- The `postinst` creates system groups `spi` and `gpio`, a system user and group
  `meshtasticd`, and adds that user to `spi` and `gpio`.
- `/usr/lib/udev/rules.d/60-meshtasticd.rules`: `spidev` to group `spi` mode 0660,
  `gpiomem` and `gpio` to group `gpio` mode 0660, and, for USB `1a86:5512`, a **mode
  0666 rule**, readable and writable by every account (CH341 USB-to-SPI modules).
  `1a86:5512` is the same kind of vendor-chip pair as the ambiguous ones in
  `docs/reference/lora-inventory.md`; a world-writable rule on it is a disclosure
  item under D-028.
- `/etc/meshtasticd/config.yaml` with `Lora: Module: auto` and `Webserver:` commented
  out, and 62 ready-made hardware files under `/etc/meshtasticd/available.d/`
  (SPI HATs such as RAK6421, Nebra, Zebra, MeshAdv; Pi Pico and Luckfox boards; `OpenWRT/`
  and `MUI/` subdirectories). The operator enables one by linking it into
  `config.d/`. Seven of the 62 declare `compatible: usb`: `lora-meshstick-1262`,
  `lora-piggystick-lr1121`, `lora-pinedio-usb-sx1262`, `lora-usb-meshstick-1262`,
  `lora-usb-meshtoad-e22`, `lora-usb-umesh-1262-30dbm`, `lora-usb-umesh-1268-30dbm`.
- A **simulation mode**: the shipped config documents `Module: sim` ("or use
  `--sim`"). A node with no radio is therefore a possible bench target.

Hardware assumption, measured from the above and not from a run: `meshtasticd` is
*not* a USB companion client. It runs the node itself on the machine, driving a LoRa
radio over SPI/GPIO (the HAT files) or over a USB CH341 SPI module (the seven USB
files). A laptop with a Meshtastic T-Deck or T-Echo on USB needs `python3-meshtastic`,
not this daemon, and a machine with neither a HAT nor a CH341 module runs only the
simulator. That settles which existing hardware entry a unit would be gated on:
none of `catalog/hardware/devices/meshtastic.yaml`'s USB identifiers (ESP32-S3 native
USB and nRF52840 bootloaders, from the board sweep) is the CH341 pair.

### Installed and run, 2026-10-05

Issue #308. Each target's repository was added by the engine itself
(`hammunition install meshtasticd`, the fingerprint typed through the variable the
plan names, `--yes` not enough) in a rootless Podman container of the harness's own
target image, built from `containers/Dockerfile.target`, as root in a container with
no systemd. `apt-get update` accepted the signed `InRelease` through `Signed-By`, the
simulate resolved, the package installed, `meshtasticd --version` printed 2.7.26, a
second `install` planned zero commands, and `uninstall` removed the package and both
repository files.

| Target (image) | Repository the unit declares | Package version | Daemon under `--sim` | `meshtastic --host` client |
|---|---|---|---|---|
| Debian 13 (glibc 2.41) | OBS `Debian_13`, flat | 2.7.26.61~obs54e0d8d~beta | listened on 0.0.0.0:4403 | connected, firmware 2.7.26 |
| Parrot 7.4 (glibc 2.41) | OBS `Debian_13`, flat | same | same | same |
| Kali rolling 2026.3 (glibc 2.43) | OBS `Debian_Testing`, flat | same | same | same |
| Ubuntu 24.04 | PPA `noble` | 2.7.26.61~ppa54e0d8d~noble | listener not looked at | no `python3-meshtastic` in the archive: not run |
| Linux Mint 22.3 | PPA `noble` | same | listened on 0.0.0.0:4403 | not run (as above) |
| Ubuntu 26.04 (glibc 2.43) | PPA `resolute` | 2.7.26.61~ppa54e0d8d~resolute | listened on 0.0.0.0:4403 | connected, firmware 2.7.26 |

What else was measured the same day:

- **Parrot cannot take the `Debian_Testing` build** (`Depends: libc6 (>= 2.43)`,
  `libyaml-cpp0.9`; Parrot has glibc 2.41), and **Kali's glibc 2.43 takes it**; Kali also
  simulated the `Debian_13` build. The unit gives Kali `Debian_Testing` because that is
  the suite built against its glibc; Debian 13's build is the fallback if Kali moves.
- **The OBS repositories are flat**: `Release` and `Packages` under the URI, no `dists/`.
  `apt` refuses a source file with an empty `Components:` line (a "Malformed stanza"),
  so the engine omits the line for a suite ending in `/` (D-040's amendment).
- **The OBS key** `426AA6B0285C2096B70D9FC2528423A469A77D9A` was fetched again from
  `.../beta/Debian_13/Release.key`: sha256 prefix `d546e147623ed42f` as before, identical in
  `alpha` and `daily`, expiry 2027-08-26 (`gpg --show-keys`), and `gpg --verify` accepts
  `beta/Debian_13`'s `InRelease` against it. **The PPA key**
  `5E0A0F83F3DDE7AC55915B14F40C93FFA2CD17E3` equals the Launchpad API's
  `signing_key_fingerprint`; no expiry.
- **The `.deb`** (Debian 13 amd64, `beta`, 2,140,624 bytes, sha256
  `324fd99ede031c662c2f483b9fd6ed82f238ee94143d5d6b473f51da53bf2104`) was unpacked with
  `dpkg-deb -I -c -e -x` on the maintainer's machine and installed only in containers. Its
  `60-meshtasticd.rules` has **four** rules (spidev to group spi 0660; USB `1a86:5512` mode
  0666; gpiomem and gpio to group gpio 0660), its `postinst` creates the groups `spi`,
  `gpio` and `meshtasticd` and the system user `meshtasticd` and adds it to eight groups
  where they exist, chowns `/etc/meshtasticd`, `/var/lib/meshtasticd` and
  `/usr/share/meshtasticd` to it, and enables and starts `meshtasticd.service`. The
  conffiles are `/etc/meshtasticd/config.yaml` and the 62 `available.d` YAML files plus a
  README. `apt-get remove` leaves the user, the groups, the config directory, `/var/lib` and
  the enablement symlink (purge clears the last two).
- **Without a radio the service exits**: the shipped config (`Module: auto`) printed
  "autoconf: Could not locate any devices" and the daemon exited 0 in about a second as
  the service user. Under `--sim` it ran and the Python client connected over TCP.
- **Sizes**: 152 packages are newly installed on a bare Debian 13 container (84 with
  `--no-install-recommends`).
- **Not measured**: a radio of any kind; the unit under systemd (so the restart limit and
  the enablement at boot are read from the unit, not observed); the udev rule against a
  plugged-in CH341; arm64 and armhf installs; Raspberry Pi OS and Pop!_OS; the web client's
  pages (the port opened and a certificate was written).

### The web client

Two things, measured separately.

- **Bundled in the daemon.** The `.deb` ships the built client under
  `/usr/share/meshtasticd/web/` (5.8 MB unpacked, with 20 locale directories), and the
  shipped config's commented defaults name `Webserver:` `Port: 9443`, `RootPath:
  /usr/share/meshtasticd/web` and generated `SSLKey`/`SSLCert` under
  `/etc/meshtasticd/ssl/`. So the daemon serves its own web client over TLS; there is
  no separate web package to install.
- **`meshtastic/web`** (GPL-3.0, head commit 2026-09-20) publishes releases whose only
  asset is `build.tar`: `v2.7.2` (2026-08-09), `v2.7.1` (2026-06-15), `v2.6.7`
  (2025-10-16) (`gh api repos/meshtastic/web/releases`). That is what a daemon-less
  host would serve statically. Whether the daemon's bundled copy is built from the same
  release was not compared.

### Flashing

| Route | What was measured |
|---|---|
| `esptool` from the archive | 4.7.0+dfsg-0.1 on Parrot 7 (installed here), Debian 13 and Ubuntu 24.04; 4.7.0+dfsg-0.2 on Ubuntu 26.04 and Kali. Already a catalog unit (`esptool`). PyPI is at **5.4.0** (2026-09-02, GPL-2.0-or-later, sdist only, Python >= 3.10), a major version ahead; its closure is 19 packages, 540 hashes, 34 MB installed. |
| `meshtastic` CLI | `meshtastic --help` (2.7.11) has `--ota-update FIRMWARE_FILE` (WiFi OTA to an ESP32 already running Meshtastic), `--reboot-ota` and `--enter-dfu`. It has **no** verb that flashes over USB. |
| Firmware repository scripts | `meshtastic/firmware` carries, in its `bin` directory, `device-install.sh`, `device-install.bat` and `native-install.sh` (names read via the contents API; the scripts' contents were not read). |
| Web flasher | `https://flasher.meshtastic.org` answers HTTP 200; the source is `meshtastic/web-flasher`. It is a web page, so a browser is the only way to use it: no Linux package exists in any archive read above, nor on PyPI. |
| Other Meshtastic repositories | `firmware-ota`, `firmware-ota-wifi`, `Meshtastic-Flasher-Apple-OTA-ESP32`, `web-flasher-events` (names only). |

Repository head commits, 2026-10-03: `meshtastic/firmware` 2026-10-03, `meshtastic/python`
2026-10-02, `meshtastic/web` 2026-09-20.

## 4. MeshCore on Linux

Measured 2026-10-03 with PyPI JSON, `gh api`, and scratch venvs as in section 1.

| Item | Version | Released | Licence | Python floor | Venv size | Closure | Repo head commit |
|---|---|---|---|---|---|---|---|
| `meshcore` (library, repo `meshcore-dev/meshcore_py`) | 2.3.14 | 2026-09-19 | MIT (PyPI `license_expression`, repo `LICENSE`) | 3.10 | 11 MB | 8 packages, 108 hashes | 2026-10-03 |
| `meshcore-cli` (repo `meshcore-dev/meshcore-cli`) | 1.6.4 | 2026-09-16 | MIT | 3.10 | 19 MB | 16 packages, 313 hashes | 2026-10-03 |

`meshcore` depends on `bleak`, `pycayennelpp`, `pycryptodome` and
`pyserial-asyncio-fast`; `meshcore-cli` adds `prompt-toolkit` and `requests`.
`meshcore-cli` installs the scripts `meshcore-cli` and `meshcli`, `meshcore` none.
Both resolve with wheels only on amd64 and arm64.

Licence split: every repository in the `meshcore-dev` organization carries MIT
(`gh api orgs/meshcore-dev/repos`: `MeshCore` firmware, `meshcore_py`, `meshcore-cli`,
`meshcore.js`, `flasher.meshcore.io`, `config.meshcore.io`, `map.meshcore.io`,
`meshcore-ha`, `nRF52-Flash-Format`), apart from the forked `Adafruit_nRF52_Arduino`
(`NOASSERTION`) and the blog (none). The `MeshCore` README says "released under the
MIT License ... for personal and commercial projects". So, unlike Reticulum, MeshCore's
firmware and its clients are under one licence.

**Desktop client for Linux.** None in the organization. `gh search repos "meshcore
desktop client"` and `"meshcore linux gui"` returned one repository
(`andyshinn/coresense`, no licence declared, 1 star, last pushed 2026-09-15); it was
not read. The first-party clients are web pages (`config.meshcore.io`,
`map.meshcore.io`) and mobile apps (not read). Hosted pages at
`client.meshcore.co.uk` and `app.meshcore.nz` answer HTTP 200; their operators and
contents were not read. A Linux operator's tools are
`meshcore-cli` and the `meshcore` library.

**Flashing** is the web flasher, `https://flasher.meshcore.io` (the `meshcore.dev`
hostname redirects to it; source `meshcore-dev/flasher.meshcore.io`, MIT): a browser
page, no package. The board identifiers it and `meshcore-cli` meet on a USB bus are
the ones `docs/reference/lora-inventory.md` already carries: its sweep read MeshCore's
PlatformIO board files with Meshtastic's (107 boards in all, 26 identifiers), so
`303a:1001` (49 boards) and the nRF52840 `239a:*` bootloader and application pairs
are covered there, and every one is marked ambiguous. Nothing new is needed for
MeshCore's USB side.

## 5. Transports Reticulum rides on that this catalog already has

`ls RNS/Interfaces/` in the `rns` 1.5.6 scratch venv lists: `AutoInterface`,
`AX25KISSInterface`, `BackboneInterface`, `I2PInterface`, `KISSInterface`,
`LocalInterface`, `PipeInterface`, `RNodeInterface`, `RNodeMultiInterface`,
`SerialInterface`, `TCPInterface`, `UDPInterface`, `WeaveInterface`.

Catalog units (`ls catalog/packages`) that a Reticulum interface can ride on or that
feed one, by name only:

- KISS and AX.25 TNCs: `direwolf`, `qtsoundmodem`, `ax25-tools`, `ax25-apps`,
  `ax25-xtools`, `linbpq`, `tmd710-tncsetup`
- serial: `minicom`, `esptool`
- network: the TCP and UDP interfaces need no unit
- LoRa through an RNode: `esptool` for the flash path; no catalog unit carries
  RNode firmware
- I2P: no unit matching `i2p` exists in the catalog

No claim is made here about how any of these combines with `rnsd`.

## 6. The TAK family (not in this pass)

Versions and licences only, 2026-10-03.

| Project | Where | Version or tag | Licence | Head commit |
|---|---|---|---|---|
| FreeTAKServer | PyPI `FreeTAKServer`, `FreeTAKTeam/FreeTakServer` | 2.2.1 (2024-05-10) | repo EPL-2.0; PyPI field empty | 2024-10-29 |
| taky | PyPI `taky`, `tkuester/taky` | 0.10 (2024-04-05) | MIT | 2024-04-05 |
| OpenTAKServer | PyPI `opentakserver`, `brian7704/OpenTAKServer` | 1.7.13 (2026-07-24) | GPL-3.0-or-later | 2026-10-01 |
| TAK Server | `TAK-Product-Center/Server` | 5.7-RELEASE-14 (2026-04-03) | GNU GPL v3 (`LICENSE.txt`; GitHub reports `NOASSERTION`) | 2026-04-03 |
| ATAK-CIV | `TAK-Product-Center/atak-civ` (the older `deptofdefense/AndroidTacticalAssaultKit-CIV` is archived) | 5.5.1.8 (2025-10-28), 1 release asset | GNU GPL v3 (`LICENSE.md`) | 2025-12-01 |
| PyTAK (library) | PyPI `pytak` | 7.6.1 (2026-08-23) | Apache-2.0 | not read |

`https://tak.gov/products/atak-civ` answers HTTP 302; the TAK.gov account gating on
the binary distribution was not followed and is not measured here.

## What this does not measure

Nothing here has run against a node, a radio or a bench. Specifically:

- No tool was started. `rnsd`, `lxmd`, `nomadnet`, `sideband`, `meshcore-cli`,
  `meshtastic` and `meshtasticd` were installed into or unpacked from scratch
  locations; only `--help` output, entry-point names and `ldd` were read.
- Sideband's GUI was not launched (no GUI spikes on the maintainer's desktop), so
  Kivy's OpenGL and window-provider needs at run time are unmeasured.
- The arm64 builds are inferred from the resolver and the sdist's declared build
  requirements. `materialyoucolor` was not built; its build time, compiler and
  memory needs are open.
- Sizes are for Python 3.13.5 on amd64; Python 3.11, 3.12 and arm64 sizes, and the
  difference between a `uv` install and the venv backend's `pip --require-hashes`
  install, were not measured.
- The closures were resolved for Python 3.11 on `x86_64-unknown-linux-gnu`. A pin
  set for 3.12 or 3.13 or for arm64 can differ in a package or two (`numpy` already
  does), and was not generated.
- `meshtasticd` was not installed in this pass. (It was on 2026-10-05, for issue #308:
  see "Installed and run, 2026-10-05" in section 3. Raspberry Pi OS and Pop!_OS are
  still matched to OBS and PPA releases by their base and were not tested.)
- Whether `rnodeconf --autoinstall` verifies what it downloads, and from where, was
  not read. Neither were `markqvist/tncattach` or `RNode_Firmware`'s release assets.
- The Reticulum License's two clauses were quoted, not interpreted, and the
  NomadNet licence disagreement (MIT classifier, GPL v3 text) is recorded, not
  resolved. No maintainer or upstream was asked.
- The `.rsg` and `.rsm` signature files on Sideband and NomadNet releases are
  Reticulum's own format; whether they can be checked with a standard tool, and
  whether a unit should pin them, was not measured.
- `rnspure`, `gtk-meshtastic-client` outside Debian and Ubuntu, `python3-kivy` on
  the Ubuntu targets, and the TAK projects' dependencies and sizes were read for a
  version and a licence only.
- Debian's `python-meshcore` and `meshcore-cli` binary package names were not read;
  the sources exist in sid and the Ubuntu development series only.
- The Meshtastic and MeshCore web flashers were not opened in a browser; "browser
  only" is inferred from their being hosted pages with no package anywhere.
- MeshCore's mobile apps, Meshtastic's, and `meshcore.js` were not read.
- Hammunition's own `hammunition.openpgp` was used as a library to read the OBS key;
  no manifest field for a PPA or an OBS key has been exercised, so whether the D-040
  `apt_repos` block as shipped can express a Launchpad PPA is not established.
