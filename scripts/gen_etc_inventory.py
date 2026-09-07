#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Generate docs/reference/etc-inventory.md from EmComm Tools OS Community's own scripts.

CLAUDE.md: "Generate what can be generated." EmComm Tools OS Community (ETC),
by Gaston Gonzalez (KT7RUN, The Tech Prepper LLC), publishes no package list;
its installer is ``scripts/install.sh`` running sixty-odd ``install-*.sh``
scripts in order, each of which is the whole record of what one unit is and
how it arrives. This generator reads every one of them:

* the ``apt install`` and ``apt purge`` lists, across backslash continuations;
* the ``VERSION`` and the fetched URL, with ``${VAR}`` references resolved from
  the script's own assignments, so a pin is read and never retyped;
* the install *method*, classified from the commands present -- a git build,
  a tarball build, a fetched ``.deb``, a prebuilt binary, a data download, an
  overlay copy, a plain apt list, or a removal;
* whether anything verifies what it downloaded;
* the system modifications on the way: udev rules, systemd units, an i386
  foreign architecture, a PPA or third-party apt source, ``/etc/skel``.

Curation -- which catalog manifest covers a unit, and whether it is base,
overlap, delta, ETC's own glue, or data -- is the one table a script cannot
derive, kept in ``CURATION`` below and tested against the clone: every script
upstream ships must be curated, and every catalog name curated must exist.

The upstream clone lives in the gitignored ``reference/`` tree::

    git clone https://github.com/thetechprepper/emcomm-tools-os-community \\
        reference/emcomm-tools-os-community

No code is taken from ETC (Apache-2.0; the logos carry a separate
non-commercial notice) -- this reads its scripts as data, the way the AHRL
inventory reads AHRL's.
"""

# No ``from __future__ import annotations``: the tests load this file by path
# without registering it in ``sys.modules``, and a dataclass whose annotations
# are strings then cannot resolve them. Python 3.11+ evaluates these directly.
import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CLONE = REPO_ROOT / "reference" / "emcomm-tools-os-community"
SCRIPTS = CLONE / "scripts"
OUT = REPO_ROOT / "docs" / "reference" / "etc-inventory.md"

UPSTREAM_URL = "https://github.com/thetechprepper/emcomm-tools-os-community"

#: Files under scripts/ that are not units: the two orchestrators, the shared
#: environment and function library, and the two non-script data files.
NOT_UNITS = (
    "install.sh",
    "install-ubuntu-image-tools-only.sh",
    "env.sh",
    "functions.sh",
)

# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

_ASSIGN = re.compile(r'^\s*(?:export\s+)?([A-Z][A-Z0-9_]*)=("([^"]*)"|\'([^\']*)\'|(\S*))\s*$')
_REF = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)")
_APT = re.compile(
    r"^\s*(?:sudo\s+)?(?:DEBIAN_FRONTEND=\S+\s+)?apt(?:-get)?\s+(install|purge)\s+(.*)$"
)
_APT_FLAGS = ("-y", "-f", "--no-install-recommends", "--fail")


@dataclass
class Facts:
    """What one upstream script does, read from its commands."""

    script: str
    apt_install: list[str] = field(default_factory=list)
    apt_purge: list[str] = field(default_factory=list)
    url: str | None = None
    version: str | None = None
    method: str = "unclassified"
    verifies_download: bool = False
    system_mods: list[str] = field(default_factory=list)


_HEREDOC = re.compile(r"<<-?\s*'?\"?([A-Za-z_][A-Za-z0-9_]*)")


def _join_continuations(text: str) -> list[str]:
    """Logical lines: a trailing backslash joins the next physical line.

    A heredoc body is dropped whole -- `install-js8call-dev-tools.sh` prints
    build notes containing `git clone` and `cmake`, and reading those as
    commands would classify an apt script as a git build."""
    out: list[str] = []
    pending = ""
    terminator: str | None = None
    for raw in text.splitlines():
        line = raw.rstrip()
        if terminator is not None:
            if line.strip() == terminator:
                terminator = None
            continue
        doc = _HEREDOC.search(line)
        if doc and not line.lstrip().startswith("#"):
            terminator = doc.group(1)
            line = line[: doc.start()].rstrip()
        if line.endswith("\\"):
            pending += line[:-1] + " "
            continue
        out.append(pending + line)
        pending = ""
    if pending:
        out.append(pending)
    return out


def _resolve(value: str, variables: dict[str, str], depth: int = 0) -> str:
    if depth > 8:
        return value

    def sub(m: re.Match[str]) -> str:
        name = m.group(1) or m.group(2)
        return variables.get(name, m.group(0))

    resolved = _REF.sub(sub, value)
    return resolved if resolved == value else _resolve(resolved, variables, depth + 1)


def _apt_packages(rest: str) -> list[str]:
    tokens = [t for t in rest.split() if t not in _APT_FLAGS and not t.startswith("-")]
    return tokens


def parse_script(name: str, text: str) -> Facts:
    """Read one script's facts from its commands. Pure; no filesystem."""
    facts = Facts(script=name)
    variables: dict[str, str] = {}
    lines = [ln for ln in _join_continuations(text) if not ln.lstrip().startswith("#")]
    body = "\n".join(lines)

    for line in lines:
        m = _ASSIGN.match(line)
        if m:
            value = m.group(3) if m.group(3) is not None else m.group(4)
            if value is None:
                value = m.group(5) or ""
            variables.setdefault(m.group(1), value)
            continue
        a = _APT.match(line)
        if a:
            target = facts.apt_install if a.group(1) == "install" else facts.apt_purge
            target.extend(_apt_packages(a.group(2)))

    if "VERSION" in variables:
        facts.version = _resolve(variables["VERSION"], variables)

    # The fetched thing: a clone URL for a git build, otherwise the first
    # URL-shaped variable. Data downloaders assemble theirs at run time from a
    # page they scrape, so the listing page is the best a static read gets.
    for key in ("GIT_URL", "REPO", "URL", "HTML_ZIP_URL", "DOWNLOAD_URL", "BASE_URL"):
        if key in variables:
            facts.url = _resolve(variables[key], variables)
            break

    # A command, not a word: `curl` is also a package name in install-base.sh.
    has_fetch = bool(
        re.search(r"^\s*(?:sudo\s+)?(curl|wget|download_with_retries)\b", body, re.M)
        or "git clone" in body
    )
    has_build = bool(re.search(r"^\s*(make|cmake|qmake|autoreconf|\./configure)\b", body, re.M))
    has_unpack = bool(re.search(r"\btar\s+-?x|\bunzip\b", body))
    has_purge = bool(facts.apt_purge)
    has_overlay = "../overlay/" in body or "systemctl" in body

    if "setup.py install" in body:
        facts.method = "python setup.py"
    elif "git clone" in body and has_build:
        facts.method = "git build"
    elif has_unpack and has_build:
        facts.method = "tarball build"
    elif re.search(r"\bdpkg -i\b", body):
        facts.method = "deb"
    elif has_fetch and (has_unpack or "chmod" in body):
        facts.method = "prebuilt binary"
    elif has_fetch:
        facts.method = "data download"
    elif has_build and not facts.apt_install:
        facts.method = "in-tree build"
    elif facts.apt_install:
        facts.method = "apt"
    elif has_purge:
        facts.method = "removal"
    elif has_overlay:
        facts.method = "overlay"
    elif "modprobe.d" in body or "/etc/" in body:
        facts.method = "config edit"

    # `download_with_retries <url> <file> [checksum]` verifies only when the
    # third argument is given -- on the same line, hence no `\s` across lines.
    facts.verifies_download = bool(
        re.search(r"\b(sha256sum|sha512sum|md5sum|gpg --verify)\b", body)
        or re.search(r"download_with_retries[ \t]+\S+[ \t]+\S+[ \t]+\S+", body)
    )

    mods: list[str] = []
    if re.search(r"rules\.d|udevadm|\budev\b", body):  # not libudev-dev
        mods.append("udev rules")
    if "systemctl" in body:
        mods.append("systemd")
    if "add-architecture i386" in body or ":i386" in body:
        mods.append("i386 multiarch")
    if "add-apt-repository" in body or "sources.list" in body:
        mods.append("apt source")
    if "/etc/skel" in body:
        mods.append("/etc/skel")
    if "modprobe.d" in body or "rmmod" in body:
        mods.append("kernel modules")
    if "sudoers" in body:
        mods.append("sudoers")
    if has_purge and facts.method != "removal":
        mods.append("purges packages")
    facts.system_mods = mods
    return facts


@dataclass(frozen=True)
class Step:
    script: str
    expert_only: bool


def parse_orchestrator(text: str) -> list[Step]:
    """The scripts install.sh runs, in order; ``ET_EXPERT``-gated ones flagged."""
    steps: list[Step] = []
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("#") or "./" not in line:
            continue
        m = re.search(r"\./([A-Za-z0-9_.-]+\.sh)", line)
        if not m or m.group(1) in ("env.sh", "functions.sh"):
            continue
        steps.append(Step(m.group(1), "ET_EXPERT" in line))
    return steps


# ---------------------------------------------------------------------------
# Curation. Everything above is read; this is judged, in one reviewable table.
#
# category: base    — the OS, its desktop, and general-purpose tools ETC
#                     installs for itself; out of scope for a catalog that
#                     augments an existing system
#           overlap — a catalog manifest already covers the unit
#           delta   — coverage ETC contributes that the other five sources lack
#           glue    — ETC's own integration layer (et-* wrappers, et-api,
#                     its .deb apps); studied, not carried (D-001 applies:
#                     the pattern may be reimplemented, the code is not taken)
#           data    — offline reference data ETC downloads into the image
# ---------------------------------------------------------------------------
BASE = "base"
OVERLAP = "overlap"
DELTA = "delta"
GLUE = "glue"
DATA = "data"


@dataclass(frozen=True)
class Curated:
    category: str
    catalog: tuple[str, ...]
    note: str


CURATION: dict[str, Curated] = {
    "bootstrap.sh": Curated(GLUE, (), "installs `et-log`, the logger every later script calls"),
    "update-apt.sh": Curated(
        BASE,
        (),
        "repoints apt at `old-releases.ubuntu.com` **kinetic** (22.10, end of life "
        "2023-07-20) and installs a crontab from the overlay",
    ),
    "install-base.sh": Curated(
        BASE,
        (),
        "build-essential, cmake, curl, a JDK, openssh-server, screen, stow, "
        "steghide and friends; `/etc/environment` and `/etc/motd` from the overlay",
    ),
    "install-dev-tools.sh": Curated(
        BASE,
        (),
        "fldigi's build dependencies plus git, meld, vim, and Cubic from a PPA "
        "for building the ISO",
    ),
    "install-pup.sh": Curated(BASE, (), "an HTML processor the map scripts use; from a GitHub zip"),
    "install-browser.sh": Curated(
        BASE,
        (),
        "Min from a GitHub `.deb` and Brave from its own apt repository, key "
        "fetched by `curl` with no fingerprint check",
    ),
    "remove-packages.sh": Curated(
        BASE,
        (),
        "purges LibreOffice, Thunderbird, snapd, unattended-upgrades and the "
        "update notifier -- the image, not the operator, decides",
    ),
    "install-branding.sh": Curated(BASE, (), "Plymouth boot logo and wallpaper"),
    "configure-gnome.sh": Curated(
        BASE, (), "gschema override, icons, touchscreen orientation lock"
    ),
    "configure-user.sh": Curated(
        GLUE,
        (),
        "creates the `et-data` group (gid 1981), replaces `/etc/skel`, and edits "
        "`adduser.conf` so every new user lands in `dialout` -- the permission "
        "problem the hardware role solves per device (D-029)",
    ),
    "install-emcomm-tools.sh": Curated(
        GLUE,
        (),
        "copies `/opt/emcomm-tools` from the overlay: 40 `et-*` wrappers, the "
        "radio definitions (`conf/radios.d/*.json`) and packet templates that "
        "make the rig plug-and-play story work",
    ),
    "fix-panasonic-brightness.sh": Curated(
        BASE, (), "a systemd unit for Toughbook backlight keys; hardware-specific"
    ),
    "install-hamlib.sh": Curated(
        OVERLAP,
        ("libhamlib-utils",),
        "builds 4.5 from the release tarball into `/opt` and stows it over "
        "`/usr/local`; the archive's Hamlib is what the catalog uses",
    ),
    "install-js8call-dev-tools.sh": Curated(
        BASE,
        (),
        "JS8Call's Qt5 build dependencies from apt, for ETC's own fork work; "
        "not run by `install.sh`",
    ),
    "install-js8call.sh": Curated(
        OVERLAP,
        ("js8call",),
        "a 2.2.0 `.deb` rehosted from ETC's own GitHub release, 22 Qt5 dependencies listed by hand",
    ),
    "install-udev.sh": Curated(
        GLUE,
        (),
        "16 rule files from the overlay writing four role symlinks -- "
        "`/dev/et-cat` (11 rules), `et-audio` (13), `et-gps` (4), `et-sdr` (3). "
        "Chip identifiers repeat across rigs (`0d8c:0012` in four files), and "
        "the rules disambiguate by asking `udev-tester.sh` which radio the "
        "operator selected with `et-radio`, not by the hardware. An empty "
        "`85-brltty.rules` shadows the system one, and `brltty-udev.service` "
        "is masked",
    ),
    "install-gps.sh": Curated(
        OVERLAP,
        ("gpsd", "gpsd-clients"),
        "gpsd, chrony and `at` from apt; replaces the gpsd default file and unit, "
        "disables gpsd at boot, adds GPS as a chrony time source",
    ),
    "install-navit.sh": Curated(
        DELTA, (), "offline turn-by-turn navigation from apt, with `maptool` and `osmium-tool`"
    ),
    "install-cat.sh": Curated(
        GLUE,
        (),
        "a `rigctld.service` unit from the overlay, disabled at boot; started by `et-radio`",
    ),
    "install-conky.sh": Curated(BASE, (), "desktop status overlay, from apt"),
    "install-direwolf.sh": Curated(
        OVERLAP,
        ("direwolf",),
        "1.7 from the tag tarball, cmake, into `/opt`; the catalog's direwolf "
        "carries the AHRL/73Linux configuration story (D-008)",
    ),
    "install-yaac.sh": Curated(
        OVERLAP,
        ("yaac",),
        "`YAAC.zip` at *latest* from ka2ddo.org, unversioned -- the same "
        "unpinned fetch the catalog's yaac replaced with a dated archive",
    ),
    "install-bbs-client.sh": Curated(
        DELTA,
        (),
        "Paracon 1.1.0, a Python packet terminal shipped as a single `.pyz` "
        "from GitHub releases (1.3.0 is current, 2025-10); MIT",
    ),
    "install-bbs-server.sh": Curated(
        OVERLAP,
        ("linbpq",),
        "`linbpq` at *latest* from cantab.net as an i386 binary with four :i386 "
        "libraries; the catalog's linbpq builds the tagged source",
    ),
    "install-chattervox.sh": Curated(
        DELTA,
        (),
        "Chattervox 0.7.0, a signed-message AX.25 chat client, as a prebuilt "
        "Node bundle from GitHub releases; GPL-3.0-or-later; 0.7.0 (2019-03) "
        "is the last tag and the last push was 2020-01",
    ),
    "install-qttermtcp.sh": Curated(
        OVERLAP,
        ("qttermtcp",),
        "an unversioned i386 executable from cantab.net's download directory; "
        "the catalog builds the GitHub tag (`install-qttermtcp-from-source.sh` "
        "is the unused alternative)",
    ),
    "install-qttermtcp-from-source.sh": Curated(
        OVERLAP,
        ("qttermtcp",),
        "not run by `install.sh`; builds `QtTermSource.zip` from cantab.net with "
        "qmake, unversioned",
    ),
    "install-packet.sh": Curated(
        OVERLAP,
        ("ax25-tools", "ax25-apps"),
        "ax25-tools and ax25-apps from apt, as the catalog does, plus sudoers "
        "rules and a group-writable `/etc/ax25/axports`",
    ),
    "install-ardop.sh": Curated(
        OVERLAP,
        ("ardopcf",),
        "ardopcf 1.0.4.1.3 as the prebuilt amd64 executable from GitHub releases; "
        "the catalog builds the same tag",
    ),
    "install-winlink.sh": Curated(
        OVERLAP, ("pat",), "Pat 0.16.0 from the upstream GitHub `.deb`, as the catalog does"
    ),
    "install-audio-tools.sh": Curated(BASE, (), "audacity, ffmpeg, sox from apt"),
    "install-wikipedia.sh": Curated(
        DELTA,
        (),
        "kiwix, kiwix-tools and the zim tools from apt -- the offline reader; "
        "Debian 13 has `kiwix`, `kiwix-tools` and `zim-tools` but no "
        "`zimwriterfs` (measured 2026-09-06)",
    ),
    "download-osm-maps.sh": Curated(
        DATA,
        (),
        "interactive: scrapes Geofabrik's US index, downloads one state's "
        "`.osm.pbf`, converts it for Navit with `maptool` into `/etc/skel`",
    ),
    "download-wikipedia.sh": Curated(
        DATA,
        (),
        "expert mode only, interactive: one English `nopic` ZIM from "
        "download.kiwix.org into `/etc/skel/wikipedia`",
    ),
    "install-wine.sh": Curated(
        BASE,
        (),
        "wine and winetricks from apt with i386 enabled -- the VARA prerequisite, "
        "post-1.0 here (SCOPE.md)",
    ),
    "install-mbtileserver.sh": Curated(
        DELTA,
        (),
        "mbtileserver 0.11.0, a Go tile server for offline maps, prebuilt from "
        "GitHub releases; ISC; no Debian 13 candidate",
    ),
    "install-python.sh": Curated(
        BASE,
        (),
        "installs **python2** and makes it `/usr/bin/python` -- for mbutil; "
        "python2 left Debian's archive with bullseye",
    ),
    "install-mbutil.sh": Curated(
        DELTA,
        (),
        "mbutil 0.3.0, MBTiles import/export, `python setup.py install` under "
        "python2; BSD-3-Clause; the 0.3.0 tag is from 2017",
    ),
    "install-gis-tools.sh": Curated(
        DELTA, ("gpsbabel",), "gpsbabel and its GUI (carried), sqlite3, and QGIS from apt"
    ),
    "install-rf-analysis-tools.sh": Curated(OVERLAP, ("splat",), "SPLAT! from apt"),
    "install-sdr-tools.sh": Curated(
        OVERLAP,
        ("rtl-sdr",),
        "purges the archive's librtlsdr, deletes its files by `rm -rf`, builds "
        "osmocom's `master` unpinned, blacklists the DVB driver, then rebuilds "
        "`.deb`s and installs those -- the AHRL librtlsdr pattern (D-022) done "
        "harder",
    ),
    "install-dump1090.sh": Curated(
        OVERLAP,
        ("readsb", "dump1090-mutability"),
        "ETC's own fork of dump1090 at `master.zip`, unpinned, `make` in place; "
        "the catalog's ADS-B default is readsb (`overlaps.md`)",
    ),
    "install-sdrpp.sh": Curated(
        OVERLAP,
        ("sdrpp",),
        "the *nightly* jammy `.deb` from GitHub, `dpkg -i` then `apt install -f`; "
        "the catalog pins a release",
    ),
    "download-et-maps.sh": Curated(
        DATA,
        (),
        "interactive: one of three `.mbtiles` tilesets (US z0-11, Canada z0-10, "
        "world z0-7) from ETC's own GitHub release into `/etc/skel`",
    ),
    "install-et-api.sh": Curated(
        GLUE,
        (),
        "et-api 1.3.0, a Java service from ETC's `et-api-java` releases, with "
        "five CSV datasets (FAA, licence, RMS list, zip-to-geo)",
    ),
    "install-et-aircraft.sh": Curated(
        GLUE, (), "et-aircraft-app 1.1.1 `.deb`, ETC's ADS-B map front end"
    ),
    "install-et-predict.sh": Curated(
        GLUE, (), "et-predict-app 1.5.2 `.deb`, ETC's VOACAP/Winlink prediction front end"
    ),
    "install-dictionary.sh": Curated(
        DELTA, (), "dict, dictd and GCIDE from apt -- offline dictionary"
    ),
    "install-doc-tools.sh": Curated(
        BASE, (), "pandoc and TeX Live; **commented out** of `install.sh`, so not installed"
    ),
    "install-voacap.sh": Curated(
        OVERLAP,
        ("voacapl",),
        "ETC's fork of voacapl at the branch head, autotools into `/opt`, "
        "`itshfbc` generated into `/etc/skel`; the catalog builds jawatson's tag",
    ),
    "install-fldigi.sh": Curated(
        OVERLAP,
        ("fldigi",),
        "4.2.09 from the SourceForge git tag, autotools into `/opt`; the "
        "`.desktop` Exec is rewritten to `et-fldigi start`",
    ),
    "install-flmsg.sh": Curated(
        OVERLAP,
        ("flmsg",),
        '4.0.24 from the git tag, with a `#include "pthread.h"` patched in by '
        "`sed -i` at line 46 -- the D-031 anchor-that-matches-nothing shape",
    ),
    "install-flamp.sh": Curated(
        OVERLAP, ("flamp",), "2.2.14 from the git tag, autotools into `/opt`"
    ),
    "install-et-portaudio.sh": Curated(
        GLUE, (), "ETC's own `et-portaudio` helper, built in-tree from `src/`"
    ),
    "install-artemis.sh": Curated(
        DELTA,
        (),
        "Artemis 4.1.0, a signal-identification reference (sigidwiki offline), "
        "prebuilt Linux zip from GitHub releases (4.2.0 is current, 2026-07); "
        "GPL-3.0",
    ),
    "install-minimodem.sh": Curated(OVERLAP, ("minimodem",), "from apt"),
    "install-gpa.sh": Curated(
        DELTA,
        (),
        "GNU Privacy Assistant 0.11.1 built from the gnupg.org tarball, for the "
        "AmRRON signed-traffic workflow; Debian 13 has no `gpa` candidate "
        "(measured 2026-09-06), so a build is the only route",
    ),
    "install-pfte.sh": Curated(
        DELTA,
        (),
        "Paranoia Text Encryption 15.0.8, a proprietary `.deb` from "
        "paranoiaworks.mobi; AmRRON's recommended text encryptor",
    ),
    "install-ventoy.sh": Curated(
        BASE, (), "Ventoy 1.1.10 from SourceForge into `/opt`; ISO tooling"
    ),
    "install-offline-lib.sh": Curated(
        DATA,
        (),
        "8 reference documents -- ARRL band chart, BPQ commands, Maidenhead map, "
        "AmRRON papers and public key, GhostNet, NOAA scales -- into "
        "`/etc/skel/Desktop/offline`, listed in `install-offline-lib.json`",
    ),
    "install-wsjtx.sh": Curated(
        OVERLAP,
        ("wsjtx",),
        "2.7.0 from the SourceForge `.deb` with six Boost/Qt dependencies by "
        "hand; the catalog uses the archive's",
    ),
    "patch-copy-fail.sh": Curated(
        BASE,
        (),
        "blacklists `algif_aead` (CVE-2026-31431) -- a kernel mitigation the "
        "distribution owes, not an installer",
    ),
}


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _clone_head() -> tuple[str, str]:
    """(short commit, ISO date) of the studied clone; both stated in the page."""
    try:
        out = subprocess.run(
            ["git", "-C", str(CLONE), "log", "-1", "--format=%h %cs"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()
        return out[0], out[1]
    except (subprocess.CalledProcessError, FileNotFoundError, IndexError):
        return "unknown", "unknown"


def _release() -> str:
    """The current release heading from RELEASES.md, e.g. `2026.04.01.R6 (6.0.0)`."""
    try:
        for line in (CLONE / "RELEASES.md").read_text().splitlines():
            if line.startswith("## "):
                return line[3:].replace(" Release Notes", "").strip()
    except OSError:
        pass
    return "unknown"


def read_all() -> dict[str, Facts]:
    facts: dict[str, Facts] = {}
    for path in sorted(SCRIPTS.glob("*.sh")):
        if path.name in NOT_UNITS:
            continue
        facts[path.name] = parse_script(path.name, path.read_text(errors="replace"))
    return facts


def _md(text: str) -> str:
    return text.replace("|", "\\|")


def render() -> str:
    facts = read_all()
    steps = parse_orchestrator((SCRIPTS / "install.sh").read_text())
    order = {s.script: i for i, s in enumerate(steps)}
    expert = {s.script for s in steps if s.expert_only}
    commit, when = _clone_head()

    units = sorted(facts, key=lambda s: (order.get(s, len(order)), s))
    by_cat: dict[str, list[str]] = {c: [] for c in (DELTA, OVERLAP, GLUE, DATA, BASE)}
    for name in units:
        by_cat[CURATION[name].category].append(name)
    methods: dict[str, int] = {}
    for f in facts.values():
        methods[f.method] = methods.get(f.method, 0) + 1
    apt_names = sorted({p for f in facts.values() for p in f.apt_install})
    fetching = [
        f
        for f in facts.values()
        if f.method
        in (
            "deb",
            "prebuilt binary",
            "tarball build",
            "git build",
            "data download",
            "python setup.py",
        )
    ]
    verified = [f for f in fetching if f.verifies_download]
    unpinned = [
        f
        for f in fetching
        if f.version in (None, "latest", "master", "nightly") and f.method not in ("data download",)
    ]
    covered = sorted({c for e in CURATION.values() for c in e.catalog})

    out: list[str] = [
        "<!-- Generated by scripts/gen_etc_inventory.py. Do not edit by hand -->",
        "",
        "# EmComm Tools OS Community inventory",
        "",
        "Generated by `scripts/gen_etc_inventory.py` from ETC's own installer",
        "scripts. Do not edit by hand — regenerate.",
        "",
        f"**Generated:** {date.today().isoformat()}  ",
        f"**Source:** <{UPSTREAM_URL}> at `{commit}` ({when}), release {_release()}  ",
        "**Method:** every `scripts/*.sh` that `install.sh` can run is parsed for",
        "its apt lists, its `VERSION` and fetched URL (variables resolved from the",
        "script's own assignments), its install method (classified from the",
        "commands present), whether it verifies a download, and the system",
        "modifications it makes. The *category* and *catalog* columns are curated",
        "in the generator and tested: every shipped script is curated, every",
        "catalog name exists.",
        "",
        "EmComm Tools OS Community is by Gaston Gonzalez (KT7RUN, The Tech",
        "Prepper LLC), Apache-2.0 for the scripts and overlay, a separate",
        "non-commercial notice for the logos. It is an installer layered onto",
        "**Ubuntu 22.10 (kinetic)** — `update-apt.sh` points apt at",
        "`old-releases.ubuntu.com`, kinetic having reached end of life on",
        "2023-07-20 — and is built into an ISO with Cubic. Its distinguishing work",
        "is the rig layer -- the operator selects a radio with `et-radio`, and",
        "21 per-radio JSON definitions, 16 udev rule files writing role",
        "symlinks, and 40 `et-*` wrappers configure each application for it --",
        "and the offline-data layer (maps, Wikipedia, reference PDFs).",
        "Nothing here takes ETC's code; the patterns are studied and, where they",
        "survive our decisions, reimplemented (D-001).",
        "",
        "## Summary",
        "",
        f"**{len(units)} units** in `scripts/`, of which {len(order)} are run by",
        f"`install.sh` ({len(expert)} only with `ET_EXPERT` set).",
        "",
        "| Category | Units | Meaning |",
        "|---|---:|---|",
        f"| delta | {len(by_cat[DELTA])} | coverage the other five sources lack |",
        f"| overlap | {len(by_cat[OVERLAP])} | a catalog manifest already covers it |",
        f"| glue | {len(by_cat[GLUE])} | ETC's own integration layer — studied, not carried |",
        f"| data | {len(by_cat[DATA])} | offline reference data downloaded into the image |",
        f"| base | {len(by_cat[BASE])} | the OS, its desktop, ISO tooling |",
        "",
        "| Method | Units |",
        "|---|---:|",
    ]
    for method, count in sorted(methods.items(), key=lambda kv: (-kv[1], kv[0])):
        out.append(f"| {method} | {count} |")
    out += [
        "",
        f"**{len(apt_names)} distinct apt package names** across every `apt install`.",
        f"**{len(fetching)} units fetch something from the network; {len(verified)}",
        "verify what they fetched.** `download_with_retries` in `et-common`",
        "accepts a checksum argument; no script passes one. "
        f"**{len(unpinned)} fetch at `latest`, `master`, `nightly` or with no version at all**: "
        + ", ".join(f"`{f.script}`" for f in unpinned)
        + ".",
        "",
        "The catalog manifests the overlap rows resolve to: "
        + ", ".join(f"`{c}`" for c in covered)
        + ".",
        "",
        "---",
        "",
        "## Delta — what ETC adds",
        "",
        "| Script | Version | Method | apt packages | Note |",
        "|---|---|---|---|---|",
    ]
    for name in by_cat[DELTA]:
        f = facts[name]
        out.append(
            f"| `{name}` | {f.version or '—'} | {f.method} | "
            f"{', '.join(f'`{p}`' for p in f.apt_install) or '—'} | {_md(CURATION[name].note)} |"
        )
    out += [
        "",
        "## Overlap — what the catalog already covers, and how ETC does it instead",
        "",
        "| Script | ETC version | ETC method | Catalog | Note |",
        "|---|---|---|---|---|",
    ]
    for name in by_cat[OVERLAP]:
        f = facts[name]
        out.append(
            f"| `{name}` | {f.version or '—'} | {f.method} | "
            f"{', '.join(f'`{c}`' for c in CURATION[name].catalog)} | {_md(CURATION[name].note)} |"
        )
    out += [
        "",
        "## Glue — ETC's own layer",
        "",
        "| Script | Version | Method | Note |",
        "|---|---|---|---|",
    ]
    for name in by_cat[GLUE]:
        f = facts[name]
        out.append(f"| `{name}` | {f.version or '—'} | {f.method} | {_md(CURATION[name].note)} |")
    out += [
        "",
        "## Data — the offline layer",
        "",
        "| Script | Run | Note |",
        "|---|---|---|",
    ]
    for name in by_cat[DATA]:
        run = "expert only" if name in expert else ("yes" if name in order else "no")
        out.append(f"| `{name}` | {run} | {_md(CURATION[name].note)} |")
    out += [
        "",
        "## Base — the OS and its tooling",
        "",
        "| Script | Method | apt packages | Note |",
        "|---|---|---|---|",
    ]
    for name in by_cat[BASE]:
        f = facts[name]
        pkgs = ", ".join(f"`{p}`" for p in f.apt_install) or "—"
        out.append(f"| `{name}` | {f.method} | {pkgs} | {_md(CURATION[name].note)} |")
    out += [
        "",
        "---",
        "",
        "## Every script, in `install.sh` order",
        "",
        "Order is the position in `install.sh`; a script it does not run sorts",
        "last with `—`. *Mods* are the system modifications read from the",
        "commands. *Verified* is whether any checksum or signature check follows",
        "the fetch.",
        "",
        "| # | Script | Category | Method | Version | Fetches | Verified | Mods |",
        "|---:|---|---|---|---|---|---|---|",
    ]
    for name in units:
        f = facts[name]
        pos = str(order[name] + 1) if name in order else "—"
        if name in expert:
            pos += " (expert)"
        url = f"<{f.url}>" if f.url and f.url.startswith("http") else (f.url or "—")
        verified_cell = ("yes" if f.verifies_download else "no") if f.url else "—"
        out.append(
            f"| {pos} | `{name}` | {CURATION[name].category} | {f.method} | "
            f"{f.version or '—'} | {_md(url)} | {verified_cell} | "
            f"{', '.join(f.system_mods) or '—'} |"
        )
    out.append("")
    return "\n".join(out)


def _without_date(text: str) -> list[str]:
    return [ln for ln in text.splitlines() if not ln.startswith("**Generated:**")]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if out of date")
    args = parser.parse_args()
    if not (SCRIPTS / "install.sh").exists():
        print(f"no upstream clone at {CLONE}; see the docstring", file=sys.stderr)
        return 2
    body = render()
    if args.check:
        if not OUT.exists() or _without_date(OUT.read_text()) != _without_date(body):
            print(f"{OUT.relative_to(REPO_ROOT)} is out of date; regenerate it")
            return 1
        print(f"{OUT.relative_to(REPO_ROOT)} is up to date")
        return 0
    OUT.write_text(body)
    print(f"wrote {OUT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
