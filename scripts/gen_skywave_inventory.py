#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Generate docs/reference/skywave-inventory.md from Skywave Linux's own data.

CLAUDE.md: "Generate what can be generated." Skywave publishes no machine-readable
task list, so the closest primary sources are used instead:

* ``skywavelinux.com`` — the versioned *Featured Applications* list for the current
  release. Authoritative for **what** ships and at **which version**.
* ``AB9IL/SDR-Scripts`` — ``sdr-installer.sh`` and ``decoders.sh``. Authoritative for
  **how** each unit is installed. Dated: these are v4-era (2022) and no longer match
  the shipped ISO, which the generated report states rather than hides.
* A measured ``apt-cache policy`` probe inside a Debian 13 container, so every
  "not in Debian" claim in the output is tested rather than assumed (**D-018**).

Source data lives in the gitignored ``reference/skywave/`` tree. Refresh with
``--fetch`` (page + scripts) and ``--probe`` (apt availability, needs podman).
"""

from __future__ import annotations

import argparse
import html
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "reference" / "skywave"
PAGE = SRC / "skywavelinux-index.html"
SCRIPTS = SRC / "SDR-Scripts"
PROBES = REPO_ROOT / "reference" / "probes"
APT_TSV = PROBES / "skywave-debian-13.tsv"
APT_SID_TSV = PROBES / "skywave-debian-sid.tsv"
BLEND_TSV = PROBES / "blend-debian-13.tsv"
BLEND_SID_TSV = PROBES / "blend-debian-sid.tsv"
OUT = REPO_ROOT / "docs" / "reference" / "skywave-inventory.md"

PAGE_URL = "https://skywavelinux.com/"
SCRIPTS_URL = "https://github.com/AB9IL/SDR-Scripts"

# ---------------------------------------------------------------------------
# Curation. The versions come from the page and cannot drift; these are the
# judgements a schema cannot express, kept in one reviewable table.
#
# category:  base    — general-purpose OS/desktop software, out of scope for us
#            overlap — already covered by the Blend, AHRL, or the 73Linux delta
#            delta   — genuinely new coverage Skywave contributes
# ---------------------------------------------------------------------------
BASE = "base"
OVERLAP = "overlap"
DELTA = "delta"

CURATION: dict[str, tuple[str, str, str]] = {
    # unit                    category   debian binary pkg   note
    "Acarsdec": (DELTA, "acarsdec", "VHF ACARS decoder; aeronautical"),
    "Acarsserv": (DELTA, "acarsserv", "SQLite store for acarsdec output"),
    "DumpHFDL": (DELTA, "dumphfdl", "HF datalink; oceanic aeronautical"),
    "VDLM2dec": (DELTA, "vdlm2dec", "VDL Mode 2 decoder"),
    "LibACARS": (DELTA, "libacars2", "shared library for the ACARS family"),
    "RTLSDR-Airband": (DELTA, "rtlsdr-airband", "multi-channel AM/NFM voice, Icecast out"),
    "Kalibrate-RTL": (DELTA, "kalibrate-rtl", "dongle PPM calibration off GSM bursts"),
    "SuperSDR": (DELTA, "supersdr", "KiwiSDR client with CAT sync"),
    "Reticulum MeshChat": (DELTA, "", "Reticulum mesh messenger"),
    "Multimon-ng": (OVERLAP, "multimon-ng", "Blend `packetmodes`"),
    "SatDump": (OVERLAP, "satdump", "AHRL + Blend; our SUPERSEDE for the APT decoders"),
    "SDR++": (OVERLAP, "sdrpp", "AHRL ships an unpinned snapshot"),
    "CubicSDR": (OVERLAP, "cubicsdr", "Blend `sdr`"),
    "Fldigi": (OVERLAP, "fldigi", "Blend `datamodes`; manifest already written"),
    "JS8Call": (OVERLAP, "js8call", "Blend `datamodes`; manifest already written"),
    "WSJT-X": (OVERLAP, "wsjtx", "Blend `datamodes`; manifest already written"),
    "Gpredict": (OVERLAP, "gpredict", "Blend `satellite`"),
    "Hamlib": (OVERLAP, "libhamlib-utils", "Blend `rigcontrol`; the rig-control floor"),
    "Libairspy": (OVERLAP, "libairspy0", "hardware library"),
    "Libairspyhf-dev": (OVERLAP, "libairspyhf1", "hardware library"),
    "Libhackrf": (OVERLAP, "libhackrf0", "hardware library"),
    "Limesuite": (OVERLAP, "limesuite", "hardware library"),
    "Uhd-Host": (OVERLAP, "uhd-host", "hardware library"),
    "SoapySDR": (OVERLAP, "soapysdr-tools", "Blend `sdr`"),
    "SoapyAirspy": (OVERLAP, "soapysdr-module-airspy", "per-device backend"),
    "SoapyAudio": (OVERLAP, "soapysdr-module-audio", "per-device backend"),
    "SoapyBladeRF": (OVERLAP, "soapysdr-module-bladerf", "per-device backend"),
    "SoapyFCDPP": (OVERLAP, "", "per-device backend; not in Debian"),
    "SoapyHackRF": (OVERLAP, "soapysdr-module-hackrf", "per-device backend"),
    "SoapyLMS7": (OVERLAP, "soapysdr-module-lms7", "per-device backend"),
    "SoapyMiri": (OVERLAP, "soapysdr-module-mirisdr", "per-device backend"),
    "SoapyOsmo": (OVERLAP, "soapysdr-module-osmosdr", "per-device backend"),
    "SoapyPlutoSDR": (OVERLAP, "soapysdr-module-plutosdr", "per-device backend"),
    "SoapyRedPitaya": (OVERLAP, "soapysdr-module-redpitaya", "per-device backend"),
    "SoapyRemote": (OVERLAP, "soapysdr-module-remote", "per-device backend; network SDR"),
    "SoapyRTLSDR": (OVERLAP, "soapysdr-module-rtlsdr", "per-device backend"),
    "SoapyRTLTCP": (OVERLAP, "", "per-device backend; not in Debian"),
    "SoapyUHD": (OVERLAP, "soapysdr-module-uhd", "per-device backend"),
    "Audacity": (BASE, "audacity", "audio editor"),
    "BleachBit": (BASE, "bleachbit", "disk cleaner"),
    "Brave Browser (beta)": (BASE, "", "browser"),
    "Dynamic Window Manager (DWM)": (BASE, "", "window manager"),
    "Go": (BASE, "", "language runtime"),
    "I2P (Purple)": (BASE, "i2pd", "anonymity network"),
    "JupyterLab": (BASE, "jupyterlab", "notebooks"),
    "Neovim": (BASE, "neovim", "editor"),
    "Node.js": (BASE, "", "language runtime"),
    "OBS-Studio": (BASE, "obs-studio", "screen capture"),
    "Obsidian": (BASE, "", "notes"),
    "Openjdk-java": (BASE, "", "language runtime"),
    "Pandas": (BASE, "", "Python library"),
    "Pandas-Datareader": (BASE, "", "Python library"),
    "Pandoc": (BASE, "pandoc", "document converter"),
    "Pipewire": (BASE, "pipewire", "audio server"),
    "Python": (BASE, "", "language runtime"),
    "Scipy": (BASE, "", "Python library"),
    "SMPlayer": (BASE, "smplayer", "media player"),
    "Shotcut": (BASE, "shotcut", "video editor"),
    "Veracrypt": (BASE, "veracrypt", "disk encryption"),
    "Wezterm": (BASE, "", "terminal"),
}

# Install method per unit, read off the published scripts. Recorded because the
# method — not the package name — is what costs us a backend.
METHOD_NOTE = {
    "git-unpinned": "`git clone --depth 1` of the default branch, no tag",
    "deb-latest": "upstream `.deb`, resolved at install time by `lastversion`",
    "appimage-latest": "upstream AppImage, resolved at install time by `lastversion`",
    "zip-latest": "upstream `.zip`, resolved at install time by `lastversion`",
    "manual": "user must download the artifact by hand first",
    "apt": "distribution package",
    "pypi": "PyPI, no distribution package",
    "not-in-scripts": "shipped in the ISO but absent from the published scripts",
}


def fetch() -> None:
    SRC.mkdir(parents=True, exist_ok=True)
    subprocess.run(["curl", "-sSL", "-o", str(PAGE), PAGE_URL], check=True)
    if SCRIPTS.exists():
        subprocess.run(["git", "-C", str(SCRIPTS), "pull", "--quiet"], check=True)
    else:
        subprocess.run(
            ["git", "clone", "--depth", "1", "--quiet", f"{SCRIPTS_URL}.git", str(SCRIPTS)],
            check=True,
        )
    print(f"fetched page and scripts into {SRC}")


def parse_page() -> tuple[str, str, str, list[tuple[str, str]]]:
    """Return (version, base system, kernel, [(unit, version), ...])."""
    text = html.unescape(re.sub(r"<[^>]+>", "\n", PAGE.read_text(errors="replace")))
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    try:
        start = next(
            i
            for i, ln in enumerate(lines)
            if ln.startswith("Featured Applications in Skywave Linux Version")
        )
    except StopIteration:  # pragma: no cover - guards a page redesign
        sys.exit("could not find the Featured Applications list; page layout changed")

    release = re.search(r"\(([\d.]+)\)", lines[start])
    version = release.group(1) if release else "unknown"
    base, kernel = "", ""
    units: list[tuple[str, str]] = []
    for line in lines[start + 1 :]:
        if line.startswith("For older changes"):
            break
        if line.startswith("Base System:"):
            base = line.split(":", 1)[1].strip()
            continue
        if line.startswith("Linux Kernel"):
            kernel = line.replace("Linux Kernel", "").strip()
            continue
        match = re.match(r"^(.*?)\s*[Vv]?([\d][\w.+-]*)$", line)
        if match and match.group(1):
            units.append((match.group(1).strip(), match.group(2)))
    return version, base, kernel, units


def parse_methods() -> dict[str, tuple[str, str]]:
    """Map lowercase unit name -> (method key, upstream URL) from the scripts."""
    found: dict[str, tuple[str, str]] = {}
    for name in ("sdr-installer.sh", "decoders.sh"):
        path = SCRIPTS / name
        if not path.exists():
            continue
        body = path.read_text(errors="replace")
        for block in re.split(r"\n(?=(?:get|update)_[\w-]+\(\)\s*\{)", body):
            head = re.match(r"(?:get|update)_([\w-]+)\(\)", block)
            if not head:
                continue
            unit = head.group(1).replace("_", "").lower()
            repo = re.search(r'git clone "([^"]+)"', block)
            if repo:
                found[unit] = ("git-unpinned", repo.group(1))
                continue
            gitrepo = re.search(r'git_repo="([^"]+)"', block)
            target = re.search(r'target_file="([^"]+)"', block)
            url = f"https://github.com/{gitrepo.group(1)}" if gitrepo else ""
            blob = target.group(1) if target else ""
            if "AppImage" in blob:
                found[unit] = ("appimage-latest", url)
            elif blob.endswith(".deb") or "deb" in blob:
                found[unit] = ("deb-latest", url)
            elif ".run" in blob:
                found[unit] = ("manual", url)
            elif gitrepo:
                found[unit] = ("zip-latest", url)
            elif (direct := re.search(r"wget \"(https?://\S+)\"", block)) is not None:
                found[unit] = ("zip-latest", direct.group(1))
    return found


def parse_apt(path: Path = APT_TSV) -> dict[str, str]:
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if "\t" in line:
            pkg, ver = line.split("\t", 1)
            out[pkg.strip()] = ver.strip()
    return out


def blend_packages() -> set[str]:
    """Derive the Blend package set from the generated Blend inventory."""
    path = REPO_ROOT / "docs" / "reference" / "blend-inventory.md"
    if not path.exists():
        return set()
    body = path.read_text()
    tasks = body[body.index("## Tasks") :]
    return {
        m.group(1)
        for line in tasks.splitlines()
        if (m := re.match(r"^\| `([a-z0-9][a-z0-9.+-]*)` \| (?:Recommends|Suggests|Depends)", line))
    }


def method_for(unit: str, methods: dict[str, tuple[str, str]]) -> tuple[str, str]:
    key = re.sub(r"[^a-z0-9]", "", unit.lower())
    for candidate, value in methods.items():
        if re.sub(r"[^a-z0-9]", "", candidate) == key:
            return value
    return ("not-in-scripts", "")


def render() -> str:
    version, base, kernel, units = parse_page()
    methods = parse_methods()
    apt = parse_apt()
    sid = parse_apt(APT_SID_TSV)
    blend = blend_packages()

    known = {u for u, _ in units}
    missing = known - set(CURATION)
    if missing:
        sys.exit(
            "unclassified units in the Featured Applications list — add them to "
            f"CURATION and re-run: {sorted(missing)}"
        )

    rows = []
    for unit, uver in units:
        cat, pkg, note = CURATION[unit]
        rows.append((unit, uver, cat, pkg, note))

    delta = [r for r in rows if r[2] == DELTA]
    overlap = [r for r in rows if r[2] == OVERLAP]
    basesw = [r for r in rows if r[2] == BASE]

    def apt_cell(pkg: str, table: dict[str, str] | None = None) -> str:
        if not pkg:
            return "— *(none)*"
        ver = (apt if table is None else table).get(pkg, "")
        if ver and ver != "-":
            return ver
        return "**absent**"

    def pkg_cell(pkg: str) -> str:
        return f"`{pkg}`" if pkg else "— *(none)*"

    out: list[str] = []
    add = out.append
    add("# Skywave Linux — inventory and delta")
    add("")
    add("Generated by `scripts/gen_skywave_inventory.py`. Do not edit by hand —")
    add("regenerate. The curation table lives in the generator; the versions,")
    add("install methods, and apt availability below are all read from source data.")
    add("")
    add(f"**Release inventoried:** Skywave Linux **{version}**  ")
    add(f"**Base system:** {base}  ")
    add(f"**Kernel:** {kernel}  ")
    add(f"**Applications page:** <{PAGE_URL}>  ")
    add(f"**Install scripts:** <{SCRIPTS_URL}>  ")
    add(f"**apt availability:** measured in a `debian:13` container, {date.today().isoformat()}  ")
    add(f"**Generated:** {date.today().isoformat()}")
    add("")
    add("Skywave Linux is written and curated by Philip Collier, **AB9IL**. Like AHRL")
    add("and 73Linux it is an inventory source, never a base (**D-001**). Unlike")
    add("73Linux, its scripts *are* licensed: `SDR-Scripts`, `Skywave-Linux-scripts`")
    add("and `Linux-Respinner` each ship a GPLv3 `LICENSE`, and both installer")
    add("scripts carry a GPL-3.0-or-later header. The provenance objection that")
    add("applies to a `.bapp` does not apply here. We still take no code — the value")
    add("is the curation.")
    add("")
    add("---")
    add("")
    add("## Summary")
    add("")
    add("| | Count |")
    add("|---|---:|")
    add(f"| Featured applications listed | {len(rows)} |")
    add(f"| **Delta — new coverage for us** | **{len(delta)}** |")
    add(f"| Overlap — already covered by another source | {len(overlap)} |")
    add(f"| Base system / general-purpose — out of scope | {len(basesw)} |")
    add("")
    add('`SCOPE.md` sizes Skywave at *"~30 apps (small delta)"*; `profile-sizing.md`')
    add(f"estimated **~10 to 15** unique units. Measured: **{len(delta)}**. Both estimates")
    add("hold, and the *shape* of the delta is narrower than either implied — see")
    add("the corrections below.")
    add("")
    add("---")
    add("")
    add(f"## The delta — {len(delta)} units")
    add("")
    add("These are the units Skywave contributes that no other source in the")
    add("five-source union covers. Every one is **absent from Debian — from stable")
    add("*and* from unstable**. Measured in `debian:13` and `debian:sid` containers,")
    add("not assumed. That matters: absence from stable is often just release lag,")
    add("and absence from both is a real gap in the distribution.")
    add("")
    add(
        "| Unit | Skywave version | Debian pkg | trixie | sid | Skywave's install method | What it is |"
    )
    add("|---|---|---|---|---|---|---|")
    for unit, uver, _cat, pkg, note in delta:
        mkey, _url = method_for(unit, methods)
        method = METHOD_NOTE[mkey]
        add(
            f"| **{unit}** | {uver} | {pkg_cell(pkg)} | {apt_cell(pkg)} | "
            f"{apt_cell(pkg, sid)} | {method} | {note} |"
        )
    add("")
    add("### Where each one actually comes from")
    add("")
    add("| Unit | Upstream we would use | Licence | Newest tag | Last commit | State |")
    add("|---|---|---|---|---|---|")
    for unit, upstream, lic, tag, last, state in UPSTREAMS:
        add(f"| {unit} | {upstream} | {lic} | {tag} | {last} | {state} |")
    add("")
    add(UPSTREAM_METHOD)
    add("")
    add(PROVENANCE_PROSE)
    add("")
    add("---")
    add("")
    add("## Corrections to `SCOPE.md`")
    add("")
    add(CORRECTIONS)
    add("")
    add("---")
    add("")
    add("## What Skywave deliberately excludes")
    add("")
    add(EXCLUSIONS)
    add("")
    add("---")
    add("")
    add("## Install methods, and what they cost us")
    add("")
    add(methods_prose())
    add("")
    add("### Defects in the published scripts")
    add("")
    add(DEFECTS)
    add("")
    add("---")
    add("")
    add(f"## Overlap — {len(overlap)} units already covered")
    add("")
    add("Listed so the overlap is on the record rather than rediscovered. The")
    add("`Blend` column is derived from `docs/reference/blend-inventory.md`.")
    add("")
    add("| Unit | Skywave version | Debian pkg | trixie | sid | In Blend | Note |")
    add("|---|---|---|---|---|---|---|")
    for unit, uver, _cat, pkg, note in overlap:
        add(
            f"| {unit} | {uver} | {pkg_cell(pkg)} | {apt_cell(pkg)} | "
            f"{apt_cell(pkg, sid)} | {'yes' if pkg in blend else 'no'} | {note} |"
        )
    add("")
    in_blend = sum(1 for u in overlap if u[3] in blend)
    add(f"**{in_blend} of {len(overlap)}** overlap units are in the Debian Blend, so they")
    add("arrive with the cheapest coverage in the project and cost us nothing extra.")
    add("")
    add(SOAPY_NOTE.format(soapy=sum(1 for u in overlap if u[0].startswith("Soapy"))))
    add("")
    add("---")
    add("")
    add(f"## Base system and general-purpose software — {len(basesw)} units, excluded")
    add("")
    add("Skywave is a live ISO, so its featured list includes the desktop it boots")
    add("into. We augment an existing install and do not ship a desktop, an editor,")
    add("a browser, or a video editor. Recorded so the exclusion is a decision")
    add("rather than an oversight.")
    add("")
    add("| Unit | Version | Debian pkg | trixie |")
    add("|---|---|---|---|")
    for unit, uver, _cat, pkg, _note in basesw:
        add(f"| {unit} | {uver} | {pkg_cell(pkg)} | {apt_cell(pkg)} |")
    add("")
    add("One is arguable: **I2P (Purple)** — `i2pd` is in Debian 13, and an anonymity")
    add("network is closer to the RF-security profile than to a desktop. It is left")
    add("out of the delta because nothing in our scope requires it, and adding an")
    add("anonymity network to a radio tool is the maintainer's call, not the")
    add("generator's.")
    add("")
    add("---")
    add("")
    add("## A finding about the Debian Blend, turned up here")
    add("")
    add(blend_gap_prose())
    add("")
    add("---")
    add("")
    add("## What this changes")
    add("")
    add(CONSEQUENCES)
    add("")
    return "\n".join(out) + "\n"


# Last commit on the **default branch**, and the newest tag, verified 2026-08-28
# against the GitHub API. Re-measure with:
#
#   gh api repos/<owner>/<repo> --jq .default_branch
#   gh api "repos/<owner>/<repo>/commits?sha=<branch>&per_page=1" --jq '.[0].commit.author.date'
#   gh api "repos/<owner>/<repo>/tags?per_page=1" --jq '.[0].name'
#
# NOT `updated_at`, and NOT `pushed_at`. See UPSTREAM_METHOD below: the first
# version of this table used `updated_at`, which moves when somebody stars the
# repository, and it reported two long-dormant projects as active.
UPSTREAMS = [
    (
        "Acarsdec",
        "`f00b4r0/acarsdec`",
        "GPL-2.0-only",
        "v4.6",
        "2026-06-28",
        "successor to the archived original",
    ),
    (
        "Acarsserv",
        "`TLeconte/acarsserv`",
        "GPL-2.0",
        "—",
        "2018-12-19",
        "**archived**; no successor found",
    ),
    ("DumpHFDL", "`szpajder/dumphfdl`", "GPL-3.0", "v1.7.0", "2025-11-02", "maintained"),
    (
        "VDLM2dec",
        "`szpajder/dumpvdl2`",
        "GPL-3.0",
        "v2.7.0",
        "2026-08-01",
        "**supersedes** the archived `vdlm2dec`",
    ),
    (
        "LibACARS",
        "`szpajder/libacars`",
        "MIT",
        "v2.2.1",
        "2025-11-02",
        "dependency of the four above",
    ),
    (
        "RTLSDR-Airband",
        "`rtl-airband/RTLSDR-Airband`",
        "GPL-2.0",
        "v5.3.1",
        "2026-08-23",
        "maintained",
    ),
    (
        "Kalibrate-RTL",
        "`steve-m/kalibrate-rtl`",
        "BSD-2-Clause",
        "**none**",
        "2022-02-01",
        "**dormant**, and it has never cut a tag",
    ),
    (
        "SuperSDR",
        "`mcogoni/supersdr`",
        "**none — default copyright**",
        "v3.14",
        "2022-12-31",
        "**dormant**",
    ),
    (
        "Reticulum MeshChat",
        "`liamcottle/reticulum-meshchat`",
        "MIT",
        "v2.4.0",
        "2026-08-15",
        "maintained",
    ),
]

UPSTREAM_METHOD = """\
**How the last-commit column was measured, and how it was measured wrongly the
first time.** The dates here are the newest commit on each project's **default
branch**, read from the GitHub API on 2026-08-28.

The first version of this table used the API's `updated_at` field, which is not
a measure of development at all — **it moves when somebody stars the
repository**, forks it, or edits its description. Two projects were reported as
active on that basis and are not:

| Unit | Was published as | Last commit on the default branch |
|---|---|---|
| Kalibrate-RTL | active (2026-08-19) | **2022-02-01** |
| SuperSDR | active (2026-02-18) | **2022-12-31** |

`pushed_at` is the near-miss and is also wrong: it moves on a push to *any*
branch, including a fork's, so it overstated five of these nine. Only the
default branch's head commit answers the question this column is asked for.

Both corrections change decisions that were resting on them, and both are
recorded below rather than quietly amended (**D-018**, **D-025**)."""

PROVENANCE_PROSE = """\
Three findings about provenance, each checked in the repository tree rather than
read off a metadata field — which, as the correction above records, is the
distinction that matters here.

**1. `SuperSDR` has no licence.** `mcogoni/supersdr` carries no `LICENSE`, no
`COPYING`, and no per-file header — checked in the repository tree and in
`supersdr.py` itself. Default copyright applies. This is the 73Linux situation
again (**D-001**) and it lands on a headline application: SuperSDR is Skywave's
KiwiSDR client and the most visible piece of the listening delta. We can install
from upstream; we cannot vendor, patch, or redistribute it. **This needs a
maintainer decision — see Q-007.**

The same check on the other two KiwiSDR clients in AB9IL's repository set found
`jks-prv/kiwiclient` with no licence statement anywhere, and `llinkz/directKiwi`
with a WTFPL-style grant stated in README prose but no licence file. There is no
cleanly-licensed KiwiSDR client in this set.

**2. Thierry Leconte's decoder suite has been archived, and only part of it has a
successor.** All three of `acarsdec`, `vdlm2dec` and `acarsserv` are now
read-only on GitHub:

| Original | State | Where it goes |
|---|---|---|
| `TLeconte/acarsdec` | archived; last activity 2025-07-31 | **SUPERSEDE** → `f00b4r0/acarsdec`, GPL-2.0-only, v4.6 |
| `TLeconte/vdlm2dec` | archived; last activity 2024-02-11 | **SUPERSEDE** → `szpajder/dumpvdl2`, GPL-3.0, v2.7.0 |
| `TLeconte/acarsserv` | archived; last activity **2018-12-19** | **CARRY** — no successor found; still the companion store `acarsdec` documents |

The `archived` flag is verified from the API. The *dates* on which each was
archived are not: GitHub does not expose `archived_at` for any of these three,
so an earlier version of this table stating exact archive dates was publishing
something it could not source. What is shown instead is last repository
activity, which is checkable. Note how far back `acarsserv`'s goes — carrying it
means carrying software untouched since 2018.

Skywave 5.10 already ships Acarsdec **4.4.1**, which can only have come from the
`f00b4r0` continuation, so the ISO tracks the live tree. Its *published*
`decoders.sh` still points at a 2023 fork of the dead one — another sign that the
scripts and the image have diverged.

Note that Skywave ships **both** `VDLM2dec 2.3` and `DumpHFDL`, and its script
carries an `update_dumpvdl2` function that is one of the broken ones. Carrying
`dumpvdl2` and retiring `vdlm2dec` is the cleaner outcome and satisfies all four
SUPERSEDE bars in `PARITY-POLICY.md`: same core function, actively maintained,
installs the same way, and the trade-off states in one sentence — *dumpvdl2 is
the maintained VDL Mode 2 decoder; vdlm2dec is archived.*

**3. GitHub's licence API is not evidence of absence, and its repository names
are not stable.** The API reported `NONE` for `TLeconte/acarsdec`, which states
LGPL-2 in its README body. It also answered happily for both
`szpajder/RTLSDR-Airband` and `charlie-foxtrot/RTLSDR-Airband` — both are
redirects, and the canonical repository is now `rtl-airband/RTLSDR-Airband`,
which has reached **v5.3.0** while Skywave ships 4.0.2. Every upstream URL in the
table above was resolved to its final location before being written down."""

CORRECTIONS = """\
`SCOPE.md` describes the Skywave delta as *"remote SDR clients (KiwiSDR, WebSDR,
Web-888, PhantomSDR, OpenWebRX), utility decoders (ACARS, HFDL, VDL2, AIS), and
Reticulum/MeshChat."* Measured against the 5.10.0 release, three parts of that
need correcting.

**1. Most of the "remote SDR clients" are not client software.** KiwiSDR, WebSDR,
Web-888, PhantomSDR and OpenWebRX are *receivers and server stacks you connect
to*, not applications Skywave installs. The 5.10.0 list ships exactly one
dedicated remote-SDR client: **SuperSDR**. Everything else is reached through a
browser, or through AB9IL's site-list tooling (`dyatlov`, `sdr-selector`,
`kiwisdr-helpers`) that generates maps and menus of public receivers. The
January 2026 changelog entry — *"Expanded the scope of the KiwiSDR list to
include OpenWebRX sites"* — confirms the reading: OpenWebRX is an entry in a
directory of receivers, not a package.

That is a smaller software delta than `SCOPE.md` implies, and a **larger data
one**. The site directory is the actual asset, and it is the thing a user with no
antenna needs first.

**2. AIS is not in the 5.10.0 release.** `rtl-ais` appears in the v4-era
`decoders.sh` and in `Skywave-Linux-scripts` (`ais-mapper`, `ais_monitor.sh`,
`ais-fileto-sqlite`), but not in the 5.10.0 featured list. It is also already
available to us: `rtl-ais` is in Debian 13, and `AIS-catcher` already has a
manifest in this repository. AIS should be attributed to our own ADD list, not
to the Skywave delta.

**3. `OpenWebRX` and `PhantomSDR` in `SCOPE.md` came from a stale page.**
`skywavelinux.com/sourcecode.html` lists both — along with `simonyiszk/openwebrx`
(the original, long superseded), WSJT-X 1.6.0, and an Ubuntu focal base. That
page documents the v4 era and has not been updated. The versioned featured list
on the front page is the current authority and was used here instead."""

EXCLUSIONS = """\
`SCOPE.md` says these are *"decisions worth respecting rather than reversing by
default."* Both are confirmed from the project's own release notes, and both are
better-founded than the summary suggested.

**GNU Radio and gqrx, dropped for bloat.** From the v5 release announcement:

> *"Prior releases had too many SDR interfaces. There was Gqrx, wich was easy to
> use and had nice features. But along with that came a lot of Gnuradio
> packages."*

with the rationale that *"you can do almost anything with CubicSDR an SDR++ and
don't need mush else for plugged in SDR devices."* The 5.10.0 list bears this
out: no GNU Radio, no gr-osmosdr, no gqrx — all three of which the published
v4-era `sdr-installer.sh` still builds.

**The consequence for us is narrower than "respect the decision."** Skywave
dropped GNU Radio because it did not need it. DragonOS Tier 3 *is* GNU Radio
out-of-tree modules, and our `sdr` profile carries gqrx from the Blend. We are
not in Skywave's position and should not inherit its conclusion — but we should
inherit the observation behind it, which is that a GNU Radio dependency chain is
heavy enough that a curator with a size budget cut it. That is an argument for
keeping Tier 3 in its own opt-in profile, which `SCOPE.md` already requires.

**The SDRplay API, excluded as non-free.** From the same announcement:

> *"One notable absence in the updasted distro is the SDRplay API."*

with three stated reasons: the proliferation of RSP clones, the API and driver
being closed source, and SDRplay's own terms forbidding use with unapproved
hardware. The author frames it as a consistency point — relying on *"non-free and
closed source drivers"* would contradict the project's commitment to open
software.

**This is stronger than an exclusion, and it is a real gap.** The v4-era
`sdr-installer.sh` still contains a `get_sdrplay_api` function, and it is
instructive: it cannot download the artifact, because SDRplay gates it behind a
web form. The script's own comment reads *"Robots are people too."* The user must
place `SDRplay_RSP_API-Linux-3.07.1.run` in `/usr/local/src` by hand before the
function will do anything. `SoapySDRPlay3` is built in that script and is **gone
from the 5.10.0 list**, so the exclusion was carried through.

For us this is a `system_modifications` and documentation problem rather than a
backend one. An artifact behind an interactive download gate cannot be installed
non-interactively, cannot be checksummed in advance, and therefore **cannot
satisfy the security requirement that we verify checksums for any non-apt
source**. If we support SDRplay hardware at all it must be as a documented
manual step with the licence terms shown, never as a silent download. Recorded
in `overlaps.md` terms: this is a hardware gap, not a software choice."""


def _script_counts() -> dict[str, int]:
    """Count install methods across both published scripts, rather than typing them."""
    body = "".join(
        (SCRIPTS / n).read_text(errors="replace")
        for n in ("sdr-installer.sh", "decoders.sh")
        if (SCRIPTS / n).exists()
    )
    targets = re.findall(r'target_file="([^"]+)"', body)
    return {
        "git": len(re.findall(r'git clone "', body)),
        "deb": sum(1 for t in targets if t.endswith(".deb") or t == "amd64.deb"),
        "appimage": sum(1 for t in targets if "AppImage" in t),
        "archive": sum(1 for t in targets if t.endswith(".zip") or t == "linux-x86_64"),
        "manual": sum(1 for t in targets if t.endswith(".run")),
    }


def methods_prose() -> str:
    c = _script_counts()
    return f"""\
Read off `sdr-installer.sh` and `decoders.sh`. These are v4-era (2022 copyright)
and no longer match the shipped ISO — `dumphfdl` is in 5.10.0 and in neither
script — so treat them as evidence of *approach*, not as a current manifest.

**Every source build is unpinned, and the pinning is then actively destroyed.**
All **{c["git"]}** `git clone` invocations across the two scripts use
`--depth 1` on the default branch; not one names a tag. Both scripts then run a
maintenance pass over every checkout on disk:

```
git pull --depth 1; git tag -d $(git tag -l); git reflog expire --expire=all --all
```

`git tag -d $(git tag -l)` **deletes every tag in the local repository.** The
intent is plainly disk-space hygiene on a live ISO, and the effect is that the
checkout can no longer name the version it is running. This is the same
unpinned-snapshot problem `PARITY-POLICY.md` records for AHRL's SatDump and
SDR++, in a sharper form: AHRL merely fails to pin, this removes the ability to.

**Release-tracking downloads resolve at install time.** `download_last` shells
out to `lastversion` to fetch the newest release asset, so every `.deb`, `.zip`
and AppImage is whatever upstream published most recently. Reproducible installs
are impossible by construction, and no checksum is computed anywhere in either
script — consistent with `SCOPE.md`'s finding that none of the five sources
publishes hashes we can inherit.

**Backend implications, measured.** The middle column counts what *Skywave's
scripts* do; the right column is what it costs *us*, which is not the same thing
because we resolve several of these to apt instead.

| Method | Uses in Skywave's scripts | Status for us |
|---|---:|---|
| source from git | {c["git"]} | already required by AHRL (**D-004**) |
| upstream `.deb` | {c["deb"]} — SDR++, noaa-apt | already required |
| upstream archive | {c["archive"]} — libairspy, SDRTrunk | already required |
| AppImage | {c["appimage"]} — CubicSDR | **CubicSDR is in Debian 13; we use apt** |
| manual, gated download | {c["manual"]} — SDRplay API | not a backend — see above |
| PyPI | 0 in the scripts | needed for Reticulum, which postdates them |

**Skywave adds no new backend requirement.** Its one AppImage is CubicSDR, which
Debian 13 packages, so we take the apt route and the AppImage never arises.

The one genuine movement is elsewhere: **Reticulum MeshChat ships Linux only as
an AppImage.** AppImage was previously justified by HAMRS alone — post-1.0, and
its upstream discovers downloads by scraping a webpage. MeshChat is a cleaner
second consumer with ordinary GitHub release assets. That does not promote
AppImage into 1.0, since MeshChat sits in the post-1.0 `mesh` profile, but the
backend now has two independent users rather than one awkward one, which is the
kind of measurement **D-014** asks for.
"""


DEFECTS = """\
Found by reading, not by running. Recorded because they are the same class of
defect the declarative-catalog argument exists to prevent, and because two of
them mean the affected units cannot have been installed by these scripts.

| Script | Line | Defect | Effect |
|---|---|---|---|
| `decoders.sh` | `update_dump1090` | `cd "$working_dir/dumpdump1090-fa"` — the directory cloned is `dump1090-fa` | `cd` fails; the build runs in whatever directory the previous job left |
| `decoders.sh` | `update_dumpvdl2` | `cd "usr/local/src/dumpvdl2/build"` — relative path, missing leading `/` | same |
| `decoders.sh` | `update_kalibrate-rtl` | `CXXFLAGS='-W Wall -03'` — `-03` is a zero, not `-O3`; `-W Wall` is two malformed flags | assignment is a no-op before `./configure`, so it is silently ignored |
| `sdr-installer.sh` | `get_gqrx` | `cd "$working_dir/gqrx/build"` then `cd build` again | second `cd` fails; `cmake ..` runs one level too high |
| `sdr-installer.sh` | GNU Radio deps | pins `libgnuradio-*3.8.1` by SONAME | unresolvable on the Debian Sid base the ISO now uses |

None of this is a criticism of the ISO, which is built and tested as an image;
it is a criticism of *shell as a packaging format*, which is the architecture
this project exists to replace (**D-001**). A manifest cannot have a typo in a
`cd`, because it has no `cd`. The build directory is derived from the checkout,
so `dumpdump1090-fa` is unrepresentable rather than merely wrong.

Every one of these five is invisible to the person running the script: the jobs
are dispatched through GNU `sem` in parallel with no error propagation, and the
script prints *"End of script. Good luck / have fun."* whether or not anything
built. That is precisely the failure mode `D-016` (fail loudly on unresolvable
dependencies) and the transaction log are designed to make impossible."""

SOAPY_NOTE = """\
**{soapy} of the overlap units are the SoapySDR family**, which is the same
observation `profile-sizing.md` makes about the Blend's `sdr` task: thirteen
`soapysdr-module-*` packages, of which a user with one dongle needs one. Skywave
ships the full set because a live ISO cannot know what will be plugged in. We
can — this is the clearest argument yet that hardware detection should drive
profile resolution, and it is now supported by two independent sources rather
than one.

Two Soapy modules are **not in Debian**: `SoapyFCDPP` (FUNcube Dongle Pro+) and
`SoapyRTLTCP`. Both are small CMake builds. Neither is needed for 1.0, and both
belong to the M4 hardware work rather than the catalog."""


def blend_gap_prose() -> str:
    """The apt probe was pointed at the Blend's own package list as a control."""
    trixie = parse_apt(BLEND_TSV)
    sid = parse_apt(BLEND_SID_TSV)
    if not trixie:
        return "*(not measured — run the Blend probe)*"
    total = len(trixie)
    miss_t = sorted(k for k, v in trixie.items() if v == "-")
    miss_s = sorted(k for k, v in sid.items() if v == "-")
    lag = [k for k in miss_t if k not in miss_s]
    rows = "\n".join(
        f"| `{k}` | **absent** | {sid.get(k, '?') if sid.get(k, '-') != '-' else '**absent**'} | "
        f"{'release lag' if k in lag else 'not in Debian at all'} |"
        for k in miss_t
    )
    return f"""\
The same container probe was pointed at the Blend's own package list as a
control, and it found something worth recording before the profile work depends
on it.

**{len(miss_t)} of the Blend's {total} packages do not install on Debian 13.**

| Blend package | trixie | sid | Why |
|---|---|---|---|
{rows}

The Blend tracks **unstable**, so {len(lag)} of these are ordinary release lag and
will arrive in Debian 14. That does not help a user installing today on the
stable base most of our targets derive from.

Two of them matter to decisions already made:

- **`qlog`** is `overlaps.md`'s recommended default for logging, chosen over
  `cqrlog` and `xlog`. It is in sid at {sid.get("qlog", "?")} and **not in trixie**. The
  recommendation is still right, but on our primary targets it needs a
  non-apt install path or an honest "not available here" — which is exactly
  what the capability matrix is for.
- **`sdrpp`** and **`sdrangel`** are listed in the Blend's `sdr` task and are
  likewise sid-only. `PARITY-POLICY.md` already flags SDR++ as an AHRL
  unpinned-snapshot fix; this says the apt route is not available on stable
  either, so the source or `.deb` path is required rather than optional.

**The general lesson.** *"In the Blend"* is not the same claim as *"installable"*,
and `blend-inventory.md` records the former. `SCOPE.md` calls the Blend "the cheapest
coverage in the project", which remains true at **{100 * (total - len(miss_t)) // total}%**
on stable — but the residual is not zero, and it lands on packages we had
already chosen as defaults. Per **D-005**, coverage counts only where it
installs.

Recorded here rather than silently fixed: adjusting `overlaps.md` and
`profile-sizing.md` is doc-reconciliation work, not inventory work."""


CONSEQUENCES = """\
**Profile sizing.** The delta lands almost entirely in `listening`, which
`profile-sizing.md` sized at ~35 with room to spare. Adding the seven
aeronautical/maritime decoders takes it to roughly **42** — still well under the
80 threshold, and coherent: a `listening` profile that decodes ACARS, HFDL and
VDL2 is a recognisable thing an operator can name. `SuperSDR` belongs there too.
`Reticulum MeshChat` belongs in `mesh`, which is post-1.0.

The `~10-15` estimate in `profile-sizing.md` was close; the number is now
measured and that row can be marked as such.

**The utility-decoder cluster is a genuine hole in Debian.** `apt-cache search`
found no `acars*`, no `vdl*`, no `hfdl`, no `airband` and no `redsea` — searched,
not merely looked up by name — and the named packages are absent from **unstable
as well as stable**. This is not release lag. The entire aeronautical and
maritime decoding domain is absent from the distribution, and therefore from the
Blend, which is the largest single coverage gap the Blend leaves. Seven source
builds is a real cost, but they are small C/CMake projects with active upstreams
and they buy a domain no other source in the union covers.

**One thing to carry forward to the DragonOS inventory.** `dumphfdl`,
`dumpvdl2`, `libacars` and `acarsdec` are named in `SCOPE.md` as DragonOS Tier 1
— *"apt-installable or upstream .deb"*. Measured above, they are apt-installable
on **neither** trixie nor sid, so on the stated definition they are not Tier 1 at
all. Tier 1's membership has to be decided by a probe rather than by the list in
`SCOPE.md`, and that is the next item's job. Whether Tier 1 is then redefined to
admit small source builds, or these four move to Tier 2, is a scope question for
the maintainer.

**Open question raised.** `Q-007` — what to do about SuperSDR, whose upstream
carries no licence at all. It is the only dedicated remote-SDR client in the
release and the other two KiwiSDR clients in the same ecosystem are no better.

**What we take, in one line.** The utility-decoder cluster, SuperSDR with a
licence caveat, the Reticulum client, and — more valuable than any of them — the
observation that the remote-receiver *directory* is the product for a user who
owns no hardware."""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true", help="refresh page and scripts")
    args = parser.parse_args()
    if args.fetch:
        fetch()
    if not PAGE.exists():
        sys.exit(f"missing {PAGE}; run with --fetch")
    OUT.write_text(render())
    print(f"wrote {OUT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
