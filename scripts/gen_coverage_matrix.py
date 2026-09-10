#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Generate docs/reference/coverage-matrix.md — AHRL's 95 executing units
reconciled against the Debian Hamradio Blend as Parrot ships it.

The landscape survey (`docs/reference/prior-art.md`) proposes the blend's
`hamradio-*` metapackages as Hammunition's base tier. This report measures
what that would leave: for every unit AHRL v27 installs, whether the blend
already covers it, whether Parrot's archive carries it outside the blend, or
whether nothing in the archive does and the unit stays ours to build.

## Classes

Each unit gets exactly one:

- **COVERED** — some `hamradio-*` metapackage Depends on or Recommends the
  package AHRL installs, and Parrot's version is within a patch level of
  AHRL's.
- **COVERED_STALE** — covered, but AHRL bundles a materially newer upstream
  (major or minor version ahead; a date-versioned release more than six
  months ahead). Both versions are shown.
- **DELTA_APT** — Parrot's archive carries it, no metapackage lists it.
- **DELTA_UPSTREAM** — nothing in the archive; upstream publishes a binary
  and the catalog installs that.
- **DELTA_SOURCE** — nothing in the archive; built from source (or a
  Python venv), with the canonical repository and licence named.
- **DELTA_NONFREE** — nothing free in the archive because the software is
  not free; the free substitute is named.
- **DEAD** — upstream is gone, superseded, or the unit was never software
  (AHRL's own tooling, wallpapers, a browser). The replacement, or "drop",
  is named.

## What is measured and what is judged

The facts come from three parsed sources and are never typed here:

- `docs/reference/ahrl-inventory.md` — the 95 units, their bundled versions
  and the apt package names AHRL uses (`parse_ahrl_units`).
- `reference/probes/blend-metapackages-parrot-echo.tsv` — Parrot's archive,
  fetched by `--fetch`: which package each `hamradio-*` metapackage lists,
  and the candidate version of every package across the four suites.
- `catalog/packages/` — which manifest carries the unit, by what method,
  with what upstream URL.

The judgement is `CURATION` below: which manifest and which apt name stand
for each unit, and — for units the evidence cannot classify on its own —
the class and a URL that supports it. Every override cites; a test holds
that. Where the archive or the catalog is enough, `classify` decides and the
citation is the pool directory or the manifest's upstream.

## The probe

`--fetch` downloads `Release` for `echo` and the sixteen `Packages.gz`
indexes (four suites by four components, amd64) from `deb.parrot.sh`, and
writes the probe. The candidate version is the highest across `echo`,
`echo-updates` and `echo-security`, which pin equal; `echo-backports` pins
lower and is the candidate only when nothing else offers the package. That
is apt's rule (**D-038**), and the doc states which suite each version came
from so a backports candidate is visible as one.
"""

from __future__ import annotations

import argparse
import gzip
import re
import sys
import urllib.request
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from hammunition.manifest.load import load_catalog  # noqa: E402
from hammunition.manifest.schema import (  # noqa: E402
    AptInstall,
    BinaryInstall,
    GitInstall,
    NodeInstall,
    PackageManifest,
    SourceInstall,
    VenvInstall,
)

CATALOG = REPO_ROOT / "catalog" / "packages"
INVENTORY = REPO_ROOT / "docs" / "reference" / "ahrl-inventory.md"
DISPOSITIONS = REPO_ROOT / "docs" / "reference" / "dispositions.md"
PROBE = REPO_ROOT / "reference" / "probes" / "blend-metapackages-parrot-echo.tsv"
OUT = REPO_ROOT / "docs" / "reference" / "coverage-matrix.md"

ARCHIVE = "https://deb.parrot.sh/parrot"
SUITES = ("echo", "echo-updates", "echo-security", "echo-backports")
COMPONENTS = ("main", "contrib", "non-free", "non-free-firmware")
ARCH = "amd64"
#: Suites apt pins equally on Parrot 7; backports pins one lower.
PREFERRED_SUITES = SUITES[:3]

CLASSES = (
    "COVERED",
    "COVERED_STALE",
    "DELTA_APT",
    "DELTA_UPSTREAM",
    "DELTA_SOURCE",
    "DELTA_NONFREE",
    "DEAD",
)

# --------------------------------------------------------------------------
# AHRL inventory


@dataclass(frozen=True)
class Unit:
    number: int
    name: str
    version: str | None
    apt_packages: list[str]


#: "Dire Wolf 1.8.1" → ("Dire Wolf", "1.8.1"). A version starts with a digit
#: and is the last word; "Firefox (browser)" and "libhamlib4" have none.
_NAME_VERSION = re.compile(r"^(?P<name>.*?)\s+(?P<version>\d[\w.\-]*)$")
_ROW = re.compile(r"^\|\s*(?P<number>\d+)\s*\|(?P<rest>.*)\|\s*$")
_CELL_PACKAGE = re.compile(r"`([^`]+)`")


def parse_ahrl_units(text: str) -> list[Unit]:
    """Every numbered row between "## Full inventory" and the disabled
    table, in order. The apt column is the third cell where the table has
    one; source-build phases record their build deps there, which are not
    what the unit installs, so those rows get no packages."""
    _, _, body = text.partition("## Full inventory")
    body, _, _ = body.partition("### Disabled in v27")
    units: list[Unit] = []
    header: list[str] = []
    for line in body.splitlines():
        if line.startswith("| #"):
            header = [cell.strip() for cell in line.strip("|").split("|")]
            continue
        match = _ROW.match(line)
        if not match:
            continue
        cells = [cell.strip() for cell in match.group("rest").split(" | ")]
        raw = cells[0].strip("`")
        parsed = _NAME_VERSION.match(raw)
        name, version = (parsed.group("name"), parsed.group("version")) if parsed else (raw, None)
        packages: list[str] = []
        if "apt package(s)" in header:
            column = header.index("apt package(s)") - 1  # `rest` starts after the '#' cell
            if column < len(cells):
                packages = _CELL_PACKAGE.findall(cells[column])
        units.append(Unit(int(match.group("number")), name, version, packages))
    return units


# --------------------------------------------------------------------------
# Packages indexes


def _stanzas(text: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for block in re.split(r"\n\s*\n", text.strip()):
        stanza: dict[str, str] = {}
        key = ""
        for line in block.splitlines():
            if line[:1].isspace():
                stanza[key] += "\n" + line.strip()
            elif ":" in line:
                key, _, value = line.partition(":")
                stanza[key] = value.strip()
        if "Package" in stanza:
            out.append(stanza)
    return out


def _relation_names(value: str) -> list[str]:
    """`a (>= 1), b | c [amd64]` → ["a", "b"]: first alternative, constraints
    stripped."""
    names = []
    for clause in value.split(","):
        first = clause.split("|", 1)[0]
        name = re.sub(r"\s*[(\[<].*$", "", first.strip())
        if name:
            names.append(name)
    return names


def parse_metapackages(text: str) -> dict[str, dict[str, list[str]]]:
    """Blend task → relation → member packages. A task metapackage is a
    `hamradio-*` package that depends on `hamradio-tasks`; that excludes
    `hamradio-tasks` itself and the unrelated `hamradio-files` and
    `hamradio-maintguide`. Other `hamradio-*` names inside a relation are
    task cross-references, not software, and are dropped."""
    out: dict[str, dict[str, list[str]]] = {}
    for stanza in _stanzas(text):
        name = stanza["Package"]
        if not name.startswith("hamradio-"):
            continue
        if "hamradio-tasks" not in _relation_names(stanza.get("Depends", "")):
            continue
        relations: dict[str, list[str]] = {}
        for relation in ("Depends", "Recommends", "Suggests"):
            members = [
                m
                for m in _relation_names(stanza.get(relation, ""))
                if not m.startswith("hamradio-")
            ]
            if members:
                relations[relation] = members
        out[name] = relations
    return out


def parse_index(text: str) -> dict[str, str]:
    return {s["Package"]: s["Version"] for s in _stanzas(text)}


# --------------------------------------------------------------------------
# Debian versions


def _order(char: str) -> int:
    if char == "~":
        return -1
    if char.isalpha():
        return ord(char)
    if char:
        return ord(char) + 256
    return 0


def _compare_fragment(a: str, b: str) -> int:
    """Debian policy §5.6.12: alternate non-digit and digit runs."""
    while a or b:
        a_nd = re.match(r"\D*", a).group()  # type: ignore[union-attr]
        b_nd = re.match(r"\D*", b).group()  # type: ignore[union-attr]
        a, b = a[len(a_nd) :], b[len(b_nd) :]
        width = max(len(a_nd), len(b_nd))
        for x, y in zip(a_nd.ljust(width, "\0"), b_nd.ljust(width, "\0"), strict=True):
            if _order(x if x != "\0" else "") != _order(y if y != "\0" else ""):
                return _order(x if x != "\0" else "") - _order(y if y != "\0" else "")
        a_d = re.match(r"\d*", a).group()  # type: ignore[union-attr]
        b_d = re.match(r"\d*", b).group()  # type: ignore[union-attr]
        a, b = a[len(a_d) :], b[len(b_d) :]
        if int(a_d or 0) != int(b_d or 0):
            return int(a_d or 0) - int(b_d or 0)
    return 0


def compare_versions(a: str, b: str) -> int:
    """<0, 0, >0 as `dpkg --compare-versions`."""

    def split(v: str) -> tuple[int, str, str]:
        epoch, _, rest = v.partition(":") if ":" in v else ("0", "", v)
        upstream, _, revision = rest.rpartition("-") if "-" in rest else (rest, "", "")
        return int(epoch), upstream, revision

    ea, ua, ra = split(a)
    eb, ub, rb = split(b)
    if ea != eb:
        return ea - eb
    return _compare_fragment(ua, ub) or _compare_fragment(ra, rb)


def upstream_version(debian: str) -> str:
    """`1:20250530-1parrot1` → `20250530`; the repack suffixes Debian adds
    are removed, a `+git…` snapshot marker is upstream identity and stays."""
    _, _, rest = debian.rpartition(":")
    upstream = rest.rsplit("-", 1)[0] if "-" in rest else rest
    return re.sub(r"\+(?:dfsg|repack|ds)\d*.*$", "", upstream)


_DATE = re.compile(r"^\d{8}$")


def _components(version: str) -> list[int]:
    return [int(n) for n in re.findall(r"\d+", version)]


def materially_behind(ahrl: str, debian: str) -> bool:
    """AHRL's bundled version is ahead of Debian's by more than a patch
    level. Date-versioned upstreams are compared as dates: six months."""
    if _DATE.match(ahrl) and _DATE.match(debian):
        return _days(ahrl) - _days(debian) > 182
    a, d = _components(ahrl), _components(debian)
    for index in range(2):
        x = a[index] if index < len(a) else 0
        y = d[index] if index < len(d) else 0
        if x != y:
            return x > y
    return False


def _days(yyyymmdd: str) -> int:
    return date(int(yyyymmdd[:4]), int(yyyymmdd[4:6]), int(yyyymmdd[6:])).toordinal()


# --------------------------------------------------------------------------
# Classification


@dataclass(frozen=True)
class Facts:
    metapackages: list[str]
    parrot_version: str | None
    ahrl_version: str | None = None
    method: str | None = None
    status: str | None = None
    override: str | None = None


def classify(facts: Facts) -> str:
    if facts.override is not None:
        return facts.override
    if facts.status == "retired":
        return "DEAD"
    if facts.metapackages:
        if (
            facts.ahrl_version
            and facts.parrot_version
            and materially_behind(facts.ahrl_version, upstream_version(facts.parrot_version))
        ):
            return "COVERED_STALE"
        return "COVERED"
    if facts.parrot_version:
        return "DELTA_APT"
    if facts.method and facts.method.startswith("binary"):
        return "DELTA_UPSTREAM"
    if facts.method in {"source", "git", "venv", "node"}:
        return "DELTA_SOURCE"
    raise ValueError(f"cannot classify from the evidence alone: {facts}")


# --------------------------------------------------------------------------
# Curation — the judgement, one entry per unit


@dataclass(frozen=True)
class Curated:
    """`toggle` is the unit's name in `dispositions.md`; `manifest` the
    catalog entry that stands for it; `apt` the Parrot package name(s) to
    look up when neither the manifest nor AHRL's own apt column is the right
    one. `override`, `cite` and `licence` are the judgement the evidence
    cannot make: a class and the URL that supports it."""

    toggle: str
    manifest: str | None = None
    apt: tuple[str, ...] = ()
    override: str | None = None
    cite: str = ""
    licence: str = ""
    note: str = ""


AHRL_PROJECT = "https://sourceforge.net/projects/kb1oiq-andysham/"
POOL = f"{ARCHIVE}/pool/main"

CURATION: dict[int, Curated] = {
    # --- Phase 1: prerequisites
    1: Curated(
        "browser",
        override="DEAD",
        cite=f"{POOL}/f/firefox-esr/",
        note="drop — a browser is the operating system's, not a ham unit; Parrot ships `firefox-esr`",
    ),
    2: Curated(
        "libhamlib4",
        manifest="libhamlib-utils",
        apt=("libhamlib4t64", "libhamlib-utils"),
        note="the runtime library every rig-control package pulls in; trixie renamed it `libhamlib4t64` (Provides `libhamlib4`) and the catalog carries `libhamlib-utils`",
    ),
    3: Curated("pipx", manifest="pipx"),
    4: Curated(
        "source_libs",
        override="DEAD",
        cite=f"{POOL}/b/build-essential/",
        note="drop — the build toolchain is each manifest's `build_depends`, resolved per unit (D-016)",
    ),
    5: Curated(
        "wine",
        apt=("wine",),
        override="DEAD",
        cite=f"{POOL}/w/wine/",
        note="drop from 1.0 — only Morse Runner needs it; a configured Wine prefix is post-1.0 (SCOPE.md); Parrot carries `wine` 10.0",
    ),
    6: Curated(
        "rtl_sdr_v4",
        manifest="rtl-sdr",
        apt=("rtl-sdr",),
        note="AHRL purges Debian's librtlsdr for the Blog fork; Debian's 2.0.x carries V4 support, and D-022 says coexist, never remove silently",
    ),
    7: Curated("svxlink", manifest="svxlink-server"),
    8: Curated("xastir", manifest="xastir"),
    9: Curated(
        "dump1090",
        manifest="readsb",
        apt=("dump1090-mutability", "readsb"),
        override="DEAD",
        cite="https://github.com/flightaware/dump1090",
        note="replacement: `readsb` (dispositions S) — FlightAware's `dump1090` is maintained (pushed 2026-08-14) but Debian packages `readsb`, not it, and Parrot has no `dump1090-*` package",
    ),
    # --- Phase 2: apt
    10: Curated("arduino", manifest="arduino-cli", apt=("arduino", "arduino-cli")),
    11: Curated("atlc", manifest="atlc"),
    12: Curated("claws-mail", manifest="claws-mail"),
    13: Curated("cqrlog", manifest="cqrlog"),
    14: Curated("ebook2cwgui", manifest="ebook2cwgui"),
    15: Curated("flamp", manifest="flamp"),
    16: Curated("flmsg", manifest="flmsg"),
    17: Curated("flwrap", manifest="flwrap"),
    18: Curated("fritzing", apt=("fritzing",)),
    19: Curated("gnuradio", manifest="gnuradio"),
    20: Curated(
        "gpsman",
        manifest="gpsbabel",
        apt=("gpsman",),
        note="in the archive, in no task; the catalog supersedes it with `gpsbabel` + `gpsd` (dispositions S)",
    ),
    21: Curated(
        "grig",
        manifest="flrig",
        apt=("grig",),
        note="`hamradio-rigcontrol` recommends it; the catalog supersedes it with `flrig` (dispositions S) — `grig` stays on the machine for the operators who prefer it",
    ),
    22: Curated("jtdx", manifest="jtdx"),
    23: Curated("kicad", apt=("kicad",)),
    24: Curated("klog", manifest="klog"),
    25: Curated("linpac", manifest="linpac"),
    26: Curated("ngspice", apt=("ngspice",)),
    27: Curated(
        "notepadqq",
        override="DEAD",
        cite=f"{POOL}/n/notepadqq/",
        note="drop — a text editor, not a ham unit; Parrot carries it for anyone who wants it",
    ),
    28: Curated("putty", manifest="putty"),
    29: Curated("qrq", manifest="qrq"),
    30: Curated("qsstv", manifest="qsstv"),
    31: Curated("qtel", manifest="qtel"),
    32: Curated("splat", manifest="splat"),
    33: Curated("sunclock", manifest="sunclock"),
    34: Curated("svxreflector", manifest="svxreflector"),
    35: Curated(
        "tkcvs",
        override="DEAD",
        cite=f"{POOL}/t/tkcvs/",
        note="drop — a CVS front end, not a ham unit; Parrot carries it",
    ),
    36: Curated("wwl", manifest="wwl"),
    37: Curated("xcwcp", manifest="xcwcp"),
    38: Curated("xdx", manifest="xdx"),
    39: Curated(
        "xosview",
        override="DEAD",
        cite=f"{POOL}/x/xosview/",
        note="drop — a system monitor, not a ham unit; Parrot carries it",
    ),
    # --- Phase 3: source builds from bundled tarballs
    40: Curated(
        "aa-analyzer",
        manifest="flaa",
        override="DEAD",
        cite="https://sourceforge.net/projects/aa-analyzer/",
        note="replacement: `flaa` (dispositions S) — the same RigExpert AA-series analyzers from a maintained W1HKJ GUI, where `aa-analyzer` is a Perl CLI on a CPAN module unmaintained for a decade; it was the only CPAN consumer (D-014 amendment)",
    ),
    41: Curated("Coil64", manifest="coil64", licence="GPL-3.0"),
    42: Curated(
        "cwwav", manifest="cwwav", licence="GPL-3.0", note="upstream last pushed 2018-06-06"
    ),
    43: Curated("direwolf", manifest="direwolf"),
    44: Curated(
        "ESPHamClock",
        manifest="openhamclock",
        override="DEAD",
        cite="https://github.com/openhamclock/hamclock/",
        note="replacement: `openhamclock` (Q-006, dispositions S) — ESPHamClock is frozen at its author's death and points at a backend that no longer answers; the community mirror is what AHRL now builds",
    ),
    45: Curated("flaa", manifest="flaa", licence="GPL-3.0-or-later"),
    46: Curated("flcluster", manifest="flcluster", licence="GPL-3.0-or-later"),
    47: Curated(
        "fldigi",
        manifest="fldigi",
        licence="GPL-3.0-or-later",
        note="the catalog builds AHRL's 4.2.11 from source and displaces the archive's 4.2.06 — a patch level, which this matrix does not count as stale",
    ),
    48: Curated("fllog", manifest="fllog", licence="GPL-3.0-or-later"),
    49: Curated("Fl_MoxGen", manifest="fl-moxgen", licence="GPL-3.0-or-later"),
    50: Curated("flnet", manifest="flnet", licence="GPL-3.0-or-later"),
    51: Curated("flrig", manifest="flrig"),
    52: Curated("flwkey", manifest="flwkey", licence="GPL-3.0-or-later"),
    53: Curated("freedv", manifest="freedv", apt=("freedv",)),
    54: Curated(
        "glfer", manifest="glfer", licence="GPL-2.0", cite="https://www.qsl.net/in3otd/glfer.html"
    ),
    55: Curated("gpredict", manifest="gpredict"),
    56: Curated("gqrx", manifest="gqrx-sdr"),
    57: Curated("gsmc", manifest="gsmc", licence="GPL-3.0", note="upstream last pushed 2016-09-13"),
    58: Curated(
        "gspiceui",
        apt=("gspiceui",),
        override="DELTA_SOURCE",
        cite="https://sourceforge.net/projects/gspiceui/",
        licence="GPL-3.0",
        note="no manifest yet — reserved to the maintainer (dispositions M); absent from trixie and Parrot; AHRL's build hardcodes an aarch64 path (D-002)",
    ),
    59: Curated("js8call", manifest="js8call"),
    60: Curated(
        "linrad",
        manifest="linrad",
        licence="MIT",
        cite="https://sourceforge.net/projects/linrad/",
        note="needs a patch the source backend cannot yet apply (`source-build-gaps.md`)",
    ),
    61: Curated("MSHV", manifest="mshv", licence="GPL-3.0", cite="https://lz2hv.org/node/10"),
    62: Curated(
        "owx",
        manifest="chirp",
        override="DEAD",
        cite="https://chirpmyradio.com/",
        note="replacement: `chirp` (dispositions S) — Open Wouxun is a 2022 CLI snapshot; CHIRP drives the same radios with a GUI and a release cadence, and Parrot packages it",
    ),
    63: Curated(
        "qgrid",
        manifest="qgrid",
        licence="GPL-2.0-or-later",
        cite="https://www.qsl.net/on4qz/qgrid/index.html",
    ),
    64: Curated(
        "QLog",
        manifest="qlog",
        licence="GPL-3.0",
        note="Parrot's backports carry 0.52.0, ahead of AHRL's 0.49.1; the manifest installs that on Parrot and Kali and builds the same tag elsewhere (corrected 2026-09-06 -- it used to say only Kali packages it)",
    ),
    65: Curated("quisk", manifest="quisk"),
    66: Curated("SatDump", manifest="satdump"),
    67: Curated("SDR++", manifest="sdrpp"),
    68: Curated("tqsl", manifest="trustedqsl"),
    69: Curated("wfview", manifest="wfview"),
    70: Curated(
        "wsjtx",
        manifest="wsjtx",
        licence="GPL-3.0",
        note="the catalog builds 3.0.0 from git and purges the archive's 2.7.0 first",
    ),
    71: Curated(
        "wsjtx_improved",
        manifest="wsjtx-improved",
        licence="GPL-3.0",
        note="Parrot packages `wsjtx-improved` (2.8.0, a minor behind AHRL's 3.1.0) where the manifest fetches SourceForge's vendor `.deb`, measured installing there and a year newer; the archive package `Breaks: wsjtx`, which the plan has refused by name since 2026-09-07 (D-022 amendment), and Kali -- where the vendor `.deb` cannot install -- takes its archive's 3.1.0 (2026-09-07)",
    ),
    72: Curated("xlog", manifest="xlog"),
    73: Curated("xnec2c", manifest="xnec2c"),
    74: Curated("xwefax", manifest="xwefax", licence="GPL-3.0", cite="https://www.qsl.net/5b4az/"),
    # --- Phase 4: prebuilt binaries and data archives
    75: Curated(
        "AntScope2",
        manifest="antscope2",
        cite="https://github.com/rigexpert/AntScope2",
        licence="MIT",
        note="vendor `.deb`; MIT per `LICENSE.txt` (Rig Expert Ukraine), not proprietary as the survey assumed",
    ),
    76: Curated(
        "GridTracker2",
        manifest="gridtracker2",
        cite="https://gitlab.com/gridtracker.org/gridtracker2",
        licence="BSD-3-Clause",
        note="vendor `.deb`; BSD-3-Clause per the GitLab project, not proprietary as the survey assumed",
    ),
    77: Curated(
        "FoxTelem",
        licence="GPL-3.0",
        override="DELTA_UPSTREAM",
        cite="https://github.com/ac2cz/FoxTelem",
        note="post-1.0 (Q-015); AMSAT publishes a Java tarball, no manifest yet",
    ),
    78: Curated(
        "yaac",
        manifest="yaac",
        licence="LGPL-3.0-or-later",
        note="per `docs/license.html` inside `YAACMain.jar`; the bundled OpenMap carries its own licence",
    ),
    79: Curated(
        "morse_runner",
        licence="MPL-2.0",
        override="DELTA_UPSTREAM",
        cite="https://github.com/w7sst/MorseRunner",
        note="reserved to the maintainer (dispositions M): a Windows binary under Wine; post-1.0 with the Wine prefix",
    ),
    80: Curated("wordsworth", manifest="wordsworth", licence="GPL-3.0"),
    81: Curated(
        "virtual_radar_server",
        manifest="readsb",
        override="DEAD",
        cite="https://www.virtualradarserver.co.uk/",
        note="replacement: `readsb` + `tar1090` (dispositions S) — a maintained Mono application whose Linux build AHRL patches at install time; the catalog supersedes it rather than carry the patch",
    ),
    82: Curated(
        "backdrops",
        override="DEAD",
        cite=AHRL_PROJECT,
        note="drop — AHRL's wallpapers, not software",
    ),
    83: Curated(
        "country_files",
        override="DELTA_UPSTREAM",
        cite="https://www.country-files.com/",
        licence="MIT-style (AD1C, `copyright.txt`)",
        note="post-1.0 (Q-015): the cty.dat archive as a zip; Parrot's `hamradio-files` 20250523 carries Debian's copy, which is the 1.0 answer",
    ),
    # --- Phase 5: Python
    84: Curated("chirp", manifest="chirp"),
    85: Curated(
        "nanovna-saver",
        manifest="nanovna-saver",
        licence="GPL-3.0-or-later",
        note="AHRL installs it with pipx; the manifest hash-pinned a venv on the claim that no distribution packages it, and since 2026-09-06 installs Parrot's 0.7.3 with the PySide6 dependency the package forgot (Debian #1112747)",
    ),
    86: Curated("not1mm", manifest="not1mm", licence="GPL-3.0"),
    87: Curated(
        "js8spotter",
        manifest="js8spotter",
        licence="MIT",
        cite="https://kf7mix.com/js8spotter.html",
    ),
    88: Curated("QtTinySA", manifest="qttinysa"),
    89: Curated(
        "pyautogui",
        override="DEAD",
        cite=f"{POOL}/p/pyautogui/",
        note="drop — AHRL's own menu-regression harness, not ham software; Parrot carries `python3-pyautogui`",
    ),
    # --- Phase 6-8: scripts and AHRL's own tooling
    90: Curated("AIS-catcher", manifest="ais-catcher", licence="GPL-3.0"),
    91: Curated(
        "rf_exposure_calc",
        override="DEAD",
        cite=AHRL_PROJECT,
        note="drop — a two-line script opening `hintlink.com/power_density.htm` in the browser; not software",
    ),
    92: Curated(
        "solar_data",
        override="DEAD",
        cite=AHRL_PROJECT,
        note="drop — `wget` of one image from hamqsl.com; not software",
    ),
    93: Curated(
        "ahrl_docs",
        override="DEAD",
        cite=AHRL_PROJECT,
        note="drop — AHRL's own; the generated package reference replaces it",
    ),
    94: Curated(
        "ahrl_menus",
        override="DEAD",
        cite=AHRL_PROJECT,
        note="drop — AHRL's own; D-036 generates menus per DE",
    ),
    95: Curated(
        "ahrl_version",
        override="DEAD",
        cite=AHRL_PROJECT,
        note="drop — AHRL's own; `hammunition --version` is the engine's",
    ),
}


def parse_dispositions_index() -> list[tuple[str, str]]:
    _, _, index = DISPOSITIONS.read_text().partition("## Complete index")
    return [
        (m.group(1).strip(), m.group(2))
        for m in re.finditer(r"`([A-Za-z0-9_.+\- ]+)`\s*([SRXCAM?])", index)
    ]


# --------------------------------------------------------------------------
# The probe


@dataclass
class Probe:
    header: dict[str, str] = field(default_factory=dict)
    metapackages: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    #: name → (version, suite, pool directory)
    packages: dict[str, tuple[str, str, str]] = field(default_factory=dict)


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "hammunition-coverage-matrix"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return bytes(response.read())


def fetch() -> None:
    release = _get(f"{ARCHIVE}/dists/{SUITES[0]}/Release").decode()
    release_fields = {
        k: v
        for k, _, v in (ln.partition(": ") for ln in release.splitlines())
        if k in {"Origin", "Suite", "Codename", "Date"}
    }

    candidates: dict[str, tuple[str, str, str]] = {}
    metapackages: dict[str, dict[str, list[str]]] = {}
    blend_version = ""
    for suite in SUITES:
        for component in COMPONENTS:
            url = f"{ARCHIVE}/dists/{suite}/{component}/binary-{ARCH}/Packages.gz"
            text = gzip.decompress(_get(url)).decode()
            print(
                f"  {suite}/{component}: {text.count(chr(10) + 'Package: ') + 1} stanzas",
                file=sys.stderr,
            )
            if suite == SUITES[0] and component == "main":
                metapackages = parse_metapackages(text)
            for stanza in _stanzas(text):
                name, version = stanza["Package"], stanza["Version"]
                pool = stanza.get("Filename", "").rpartition("/")[0]
                if name == "hamradio-tasks" and suite == SUITES[0]:
                    blend_version = version
                current = candidates.get(name)
                if current is None:
                    candidates[name] = (version, suite, pool)
                    continue
                if current[1] in PREFERRED_SUITES and suite not in PREFERRED_SUITES:
                    continue
                preferred_now = suite in PREFERRED_SUITES and current[1] not in PREFERRED_SUITES
                if preferred_now or compare_versions(version, current[0]) > 0:
                    candidates[name] = (version, suite, pool)

    lines = [
        "# Parrot archive probe for the coverage matrix — scripts/gen_coverage_matrix.py --fetch",
        f"# fetched: {date.today().isoformat()}",
        f"# archive: {ARCHIVE}",
        f"# suites: {' '.join(SUITES)}",
        f"# components: {' '.join(COMPONENTS)}",
        f"# arch: {ARCH}",
        "# release: " + " ".join(f"{k}={v}" for k, v in release_fields.items()),
        f"# debian-hamradio: {blend_version}",
        "# rows: meta<TAB>metapackage<TAB>relation<TAB>member | pkg<TAB>name<TAB>version<TAB>suite<TAB>pool",
    ]
    for task, relations in sorted(metapackages.items()):
        for relation, members in relations.items():
            lines.extend(f"meta\t{task}\t{relation}\t{member}" for member in members)
    lines.extend(
        f"pkg\t{name}\t{v}\t{suite}\t{pool}"
        for name, (v, suite, pool) in sorted(candidates.items())
    )
    PROBE.parent.mkdir(parents=True, exist_ok=True)
    PROBE.write_text("\n".join(lines) + "\n")
    print(
        f"wrote {PROBE.relative_to(REPO_ROOT)}: {len(metapackages)} tasks, {len(candidates)} packages",
        file=sys.stderr,
    )


def read_probe() -> Probe:
    probe = Probe()
    for line in PROBE.read_text().splitlines():
        if line.startswith("# "):
            key, _, value = line[2:].partition(": ")
            probe.header[key] = value
            continue
        cells = line.split("\t")
        if cells[0] == "meta":
            probe.metapackages.setdefault(cells[1], {}).setdefault(cells[2], []).append(cells[3])
        elif cells[0] == "pkg":
            probe.packages[cells[1]] = (cells[2], cells[3], cells[4])
    return probe


# --------------------------------------------------------------------------
# Rows


@dataclass(frozen=True)
class Row:
    unit: Unit
    entry: Curated
    manifest: PackageManifest | None
    method: str | None
    apt_name: str | None
    parrot: tuple[str, str, str] | None
    metapackages: list[str]
    cls: str
    cite: str


def _method(manifest: PackageManifest | None) -> str | None:
    """The method that classifies the manifest: apt where it offers apt,
    else the first block's. `classified_rows` swaps to a non-apt block when
    the archive turns out not to carry the package."""
    if manifest is None:
        return None
    kinds = [_method_of(block.install) for block in manifest.install]
    for preferred in ("apt", "source", "git", "venv", "node"):
        if preferred in kinds:
            return preferred
    return kinds[0] if kinds else None


def _apt_names(unit: Unit, entry: Curated, manifest: PackageManifest | None) -> list[str]:
    """Every name worth looking up in the archive, most specific first.

    The manifest's own name and the toggle come last, so that a unit the
    catalog builds from source is still found where the archive packages it
    — `fldigi` is in `hamradio-datamodes` whether or not the manifest says
    apt, and a matrix that missed that would mis-state the blend."""
    names: list[str] = list(entry.apt)
    if manifest is not None:
        for block in manifest.install:
            if isinstance(block.install, AptInstall):
                names.extend(block.install.packages)
        names.append(manifest.name)
    names.extend(unit.apt_packages)
    names.append(entry.toggle.lower())
    return list(dict.fromkeys(names))


def classified_rows() -> list[Row]:
    probe = read_probe()
    catalog = load_catalog(CATALOG)
    units = parse_ahrl_units(INVENTORY.read_text())
    member_of: dict[str, list[str]] = {}
    for task, relations in probe.metapackages.items():
        for relation in ("Depends", "Recommends"):
            for member in relations.get(relation, []):
                member_of.setdefault(member, []).append(task)

    rows: list[Row] = []
    for unit in units:
        entry = CURATION[unit.number]
        manifest = catalog[entry.manifest] if entry.manifest else None
        names = _apt_names(unit, entry, manifest)
        apt_name = next((n for n in names if n in probe.packages), None)
        parrot = probe.packages.get(apt_name) if apt_name else None
        tasks = sorted({t for n in names for t in member_of.get(n, [])})
        method = _method(manifest)
        if method == "apt" and parrot is None and manifest is not None:
            # The manifest offers apt where the archive has it and something
            # else where it does not; classify by the something else.
            fallbacks = [m for m in (_method_of(b.install) for b in manifest.install) if m != "apt"]
            method = fallbacks[0] if fallbacks else "apt"
        facts = Facts(
            metapackages=tasks,
            parrot_version=parrot[0] if parrot else None,
            ahrl_version=unit.version,
            method=method,
            status=manifest.status.value if manifest else None,
            override=entry.override,
        )
        try:
            cls = classify(facts)
        except ValueError as exc:
            sys.exit(f"#{unit.number} {unit.name}: {exc}")
        cite = entry.cite
        if not cite:
            if cls in {"COVERED", "COVERED_STALE", "DELTA_APT"} and parrot:
                cite = f"{ARCHIVE}/{parrot[2]}/"
            elif manifest is not None and manifest.documentation.upstream_url.startswith(
                "https://"
            ):
                cite = manifest.documentation.upstream_url
        rows.append(Row(unit, entry, manifest, method, apt_name, parrot, tasks, cls, cite))
    return rows


def _method_of(block: object) -> str:
    if isinstance(block, AptInstall):
        return "apt"
    if isinstance(block, SourceInstall):
        return "source"
    if isinstance(block, GitInstall):
        return "git"
    if isinstance(block, BinaryInstall):
        return f"binary:{block.format}"
    if isinstance(block, VenvInstall):
        return "venv"
    if isinstance(block, NodeInstall):
        return "node"
    return type(block).__name__


# --------------------------------------------------------------------------
# Rendering


def _md(text: str) -> str:
    return text.replace("|", "\\|")


def render() -> str:
    probe = read_probe()
    rows = classified_rows()
    counts = {cls: sum(1 for r in rows if r.cls == cls) for cls in CLASSES}
    tasks = sorted(probe.metapackages)
    header = probe.header

    lines = [
        "# Coverage matrix — AHRL v27 against the Debian Hamradio Blend on Parrot",
        "",
        "> Generated by `scripts/gen_coverage_matrix.py`. Do not edit by hand.",
        "> The facts are parsed from `docs/reference/ahrl-inventory.md`, the",
        "> catalog and a fetched Parrot archive probe; the judgement is the",
        "> generator's `CURATION` table, every override of which cites a URL.",
        "",
        f"**Generated:** {date.today().isoformat()}",
        "",
        "## What this answers",
        "",
        "`docs/reference/prior-art.md` proposes the blend's `hamradio-*`",
        "metapackages as the base tier. This matrix measures what that leaves",
        "Hammunition to do: for each of the 95 units AHRL v27 executes, whether",
        "a metapackage already lists the package, whether Parrot's archive",
        "carries it outside any metapackage, or whether nothing in the archive",
        "does. One class per unit; a URL for every class but `COVERED`.",
        "",
        "## The archive that was measured",
        "",
        f"- Archive: `{header.get('archive', '')}`, suites `{header.get('suites', '')}`,",
        f"  components `{header.get('components', '')}`, `{header.get('arch', '')}`; fetched {header.get('fetched', '')}.",
        f"- `Release`: {header.get('release', '')}.",
        f"- Blend: `debian-hamradio` **{header.get('debian-hamradio', '')}** — {len(tasks)} task metapackages",
        f"  ({', '.join(f'`{t}`' for t in tasks)}).",
        "- Parrot 7 `echo` is Debian 13 *trixie* stable plus backports (**D-038**), not",
        "  testing or sid. The candidate is the highest version across `echo`,",
        "  `echo-updates` and `echo-security`; `echo-backports` only when nothing else",
        "  offers the package, and the suite column says so when that happens.",
        "- A unit counts as blend-covered when a metapackage **Depends** on or",
        "  **Recommends** its package. `Suggests` is not installed by default and is",
        "  not counted.",
        "",
        "## Counts",
        "",
        "| Class | Units | Meaning |",
        "|---|---:|---|",
    ]
    meanings = {
        "COVERED": "a metapackage lists it; Parrot is within a patch level of AHRL",
        "COVERED_STALE": "a metapackage lists it; AHRL bundles a materially newer upstream",
        "DELTA_APT": "Parrot's archive carries it; no metapackage lists it",
        "DELTA_UPSTREAM": "not in the archive; upstream publishes a binary",
        "DELTA_SOURCE": "not in the archive; built from source or a venv",
        "DELTA_NONFREE": "not free software; free substitute named",
        "DEAD": "superseded, sunset, or never software — replacement or drop named",
    }
    lines.extend(f"| `{cls}` | {counts[cls]} | {meanings[cls]} |" for cls in CLASSES)
    lines.append(f"| **total** | **{len(rows)}** | |")

    lines += [
        "",
        "## The matrix",
        "",
        "AHRL's version is what the v27 tarball bundles or, for apt units, blank",
        "(AHRL takes whatever the target offers). Parrot's is the candidate version",
        "and its suite. *Task* is every metapackage that Depends on or Recommends",
        "the package. *Carried as* is the catalog manifest and its install method,",
        "or `—` where none exists.",
        "",
        "| # | Unit | AHRL | Parrot | Task | Class | Carried as | Licence | Source / note |",
        "|---:|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        parrot = f"`{upstream_version(row.parrot[0])}` ({row.parrot[1]})" if row.parrot else "—"
        if row.parrot and row.apt_name and row.apt_name != row.unit.name.lower():
            parrot += f" as `{row.apt_name}`"
        tasks_cell = ", ".join(f"`{t.removeprefix('hamradio-')}`" for t in row.metapackages) or "—"
        carried = f"`{row.entry.manifest}` ({row.method})" if row.entry.manifest else "—"
        licence = row.entry.licence
        if not licence and row.cls in {"DELTA_SOURCE", "DELTA_UPSTREAM"}:
            licence = "?"
        note_parts = []
        if row.cite:
            note_parts.append(f"<{row.cite}>")
        if row.entry.note:
            note_parts.append(_md(row.entry.note))
        lines.append(
            f"| {row.unit.number} | {_md(row.unit.name)} | {row.unit.version or '—'} | {parrot} | {tasks_cell} "
            f"| `{row.cls}` | {carried} | {licence or '—'} | {' — '.join(note_parts)} |"
        )

    stale = [r for r in rows if r.cls == "COVERED_STALE"]
    lines += [
        "",
        "## Covered but stale",
        "",
        "Where AHRL builds a newer upstream than the blend installs. These are the",
        "units where taking the blend as the base costs a version, and the only",
        "ones where a blend-first Hammunition would owe a source build for a",
        "package the archive already has.",
        "",
        "| # | Unit | AHRL bundles | Parrot installs | Gap |",
        "|---:|---|---|---|---|",
    ]
    for row in stale:
        assert row.parrot
        lines.append(
            f"| {row.unit.number} | {_md(row.unit.name)} | {row.unit.version} | "
            f"{upstream_version(row.parrot[0])} ({row.parrot[1]}) | {_gap(row.unit.version or '', upstream_version(row.parrot[0]))} |"
        )

    dead = [r for r in rows if r.cls == "DEAD"]
    dropped = [r for r in dead if (r.entry.note or "").startswith("drop")]
    superseded = [r for r in dead if r not in dropped]
    unmanifested = [r for r in rows if r.manifest is None and r.cls.startswith("DELTA")]
    built_anyway = [r for r in rows if r.parrot and r.method not in (None, "apt")]
    lines += [
        "",
        "## Where the seven classes do not fit",
        "",
        f"`DEAD` was defined as *upstream gone or superseded*. {len(dropped)} of the",
        f"{len(dead)} units in it are not ham software — AHRL's own wallpapers,",
        "menu tooling and version stamp, a browser, an editor, a system monitor,",
        "a build toolchain, Wine, two scripts that fetch a web page. They are",
        "marked `DEAD` with the note *drop* because the matrix was asked for",
        "exactly seven classes; they are not dead upstreams, and a reader counting",
        f"dead ham software should subtract them. The {len(superseded)} that remain",
        f"({', '.join(_md(r.unit.name) for r in superseded)}) are superseded in the",
        "catalog, and only ESPHamClock's upstream is actually gone.",
        "",
        f"{len(unmanifested)} units are `DELTA_*` with no manifest",
        f"({', '.join(_md(r.unit.name) for r in unmanifested)}). The electronics",
        "tools and GSpiceUI are reserved to the maintainer (dispositions M),",
        "FoxTelem and the country files are post-1.0 by Q-015, and Morse Runner",
        "is a Windows binary. They are classified by what AHRL does with them,",
        "not by what the catalog does.",
        "",
        f"{len(built_anyway)} units the archive carries are built or fetched by the",
        f"catalog anyway ({', '.join(_md(r.unit.name) for r in built_anyway)}).",
        "Each row's note says why. When this probe first ran (2026-09-06) it",
        "contradicted three manifests — that no distribution packages",
        "NanoVNA-Saver, that only Kali packages QLog, that the archive's WSJT-X",
        "is the only one — and they were corrected the same day: the first two",
        "now install from the archive where it offers them, and the third names",
        "the archive package and why the engine does not use it yet.",
        "",
        "## What the blend as base tier leaves to Hammunition",
        "",
    ]
    lines.append(_scope_paragraph(rows, counts))
    lines += [
        "",
        "## Reproducing",
        "",
        "```",
        "python3 scripts/gen_coverage_matrix.py --fetch   # rewrites reference/probes/blend-metapackages-parrot-echo.tsv",
        "python3 scripts/gen_coverage_matrix.py           # rewrites this file",
        "python3 scripts/gen_coverage_matrix.py --check   # CI: fail if stale",
        "```",
        "",
        "`tests/test_gen_coverage_matrix.py` holds the parsers to fixtures, every",
        "unit to exactly one curated entry, every override to an `https://`",
        "citation, and regeneration to a no-op.",
        "",
    ]
    return "\n".join(lines)


def _gap(ahrl: str, debian: str) -> str:
    if _DATE.match(ahrl) and _DATE.match(debian):
        return f"{_days(ahrl) - _days(debian)} days"
    a, d = _components(ahrl), _components(debian)
    if a and d and a[0] != d[0]:
        return "major"
    return "minor"


def _scope_paragraph(rows: list[Row], counts: dict[str, int]) -> str:
    covered = counts["COVERED"] + counts["COVERED_STALE"]
    apt = counts["DELTA_APT"]
    ours = counts["DELTA_UPSTREAM"] + counts["DELTA_SOURCE"] + counts["DELTA_NONFREE"]
    dead = counts["DEAD"]
    live = len(rows) - dead
    source_names = ", ".join(_md(r.unit.name) for r in rows if r.cls == "DELTA_SOURCE")
    nonfree = (
        f" and {counts['DELTA_NONFREE']} proprietary tools"
        if counts["DELTA_NONFREE"]
        else " and no proprietary tools"
    )
    return (
        f"With the blend installed as the base tier, {covered} of AHRL's {len(rows)} units are already "
        f"on the machine and {apt} more are one `apt install` away — together {covered + apt} of the "
        f"{live} units that are not `DEAD`, or {100 * (covered + apt) // live}% — if the operator "
        f"installs all twelve task metapackages, which is what *base tier* would mean. That is the "
        f"measured version of the survey's claim that the blend makes most of AHRL redundant, and it "
        f"holds. What it leaves is {ours} units: {counts['DELTA_SOURCE']} source builds the archive "
        f"does not carry ({source_names}), {counts['DELTA_UPSTREAM']} upstream binaries"
        f"{nonfree}. Plus the {counts['COVERED_STALE']} stale rows, "
        f"where the operator who wants AHRL's version needs a build the blend cannot give them. "
        f"Hammunition's actual scope on the amateur side is therefore not a catalog of {live} "
        f"programs but a build layer for roughly {ours + counts['COVERED_STALE']} of them — the "
        f"W1HKJ suite, the Qt and FLTK one-offs, the Python venvs — sitting on a base someone else "
        f"maintains; and the tiering, hardware, station configuration and SDR/SIGINT profiles that "
        f"no metapackage attempts. The {dead} `DEAD` units are the explanation AHRL never wrote down."
    )


GENERATED_LINE = re.compile(r"^\*\*Generated:\*\*")


def _without_date(text: str) -> list[str]:
    return [line for line in text.splitlines() if not GENERATED_LINE.match(line)]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--fetch", action="store_true", help="download Parrot's indexes and rewrite the probe"
    )
    parser.add_argument("--check", action="store_true", help="fail if the document is out of date")
    args = parser.parse_args()

    if args.fetch:
        fetch()
    if not PROBE.exists():
        print(f"{PROBE.relative_to(REPO_ROOT)} is missing; run with --fetch", file=sys.stderr)
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
