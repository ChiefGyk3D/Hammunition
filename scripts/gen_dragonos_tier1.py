#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2026 The Hammunition contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Generate docs/reference/dragonos-tier1-inventory.md from DragonOS's own README.

`SCOPE.md` defines **Tier 1** as *"apt-installable or upstream .deb"* and makes it
the 1.0 SIGINT profile. That definition is only useful if membership is decided by
a probe rather than by a guess, so this generator does both halves:

* parses the unit list out of DragonOS's published ``README.txt`` (versions come
  from the file and cannot drift), and
* reads ``apt-cache policy`` results measured inside **all four** of our x86
  target containers — debian:13, ubuntu:26.04, kali-rolling and parrot.

Tier 1 is the deliverable. Tiers 2 and 3 are named and counted so the denominator
is honest, and deliberately not inventoried — `SCOPE.md` puts Tier 3 behind the
source backend and the pin database.

Source data lives in the gitignored ``reference/dragonos/`` tree. Refresh the
README with ``--fetch``; refresh the probes with ``scripts/run-targets.sh``-style
podman runs (see the header of the generated document for the exact commands).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "reference" / "dragonos"
README = SRC / "README.txt"
OUT = REPO_ROOT / "docs" / "reference" / "dragonos-tier1-inventory.md"

README_URL = "https://sourceforge.net/projects/dragonos-focal/files/README.txt/download"
PROJECT_URL = "https://cemaxecuter.com/"

TARGETS = ["debian-13", "ubuntu-26.04", "kali-rolling", "parrot"]

SECTIONS = [
    "Supported SDRs",
    "Cellular / EW",
    "SDR applications",
    "Frameworks / analysis",
    "Wi-Fi / Bluetooth",
    "Decoders / ham / utils",
    "Speech / AI",
    "Agent platform (one agent, one MCP)",
    "DMR Tier III trunking / AI voice",
    "SDR hardware libs / tools",
]

# Tier assignment. T1 requires apt on at least one target OR an upstream .deb;
# the generator asserts the apt half against the probe and fails if a T1 unit
# has neither, so this table cannot quietly overclaim.
T1 = "T1"
T2 = "T2"
T3 = "T3"
HW = "HW"  # driver/library/firmware — M4 hardware work, not the catalog
BASE = "BASE"  # general-purpose or DragonOS-specific; out of scope
EW = "EW"  # cellular / electronic warfare — needs a maintainer decision

CURATION: dict[str, tuple[str, tuple[str, ...], str]] = {
    # --- Tier 1: in apt somewhere ---------------------------------------
    "Wireshark": (T1, ("wireshark", "tshark", "tcpdump"), "protocol analyser"),
    "aircrack-ng": (T1, ("aircrack-ng",), "Wi-Fi audit suite"),
    "hcxdumptool / hcxtools": (T1, ("hcxdumptool", "hcxtools"), "WPA capture and conversion"),
    "Ubertooth host tools": (T1, ("ubertooth",), "BLE/BT sniffer host tools"),
    "rtl_433": (T1, ("rtl-433",), "ISM 433/868/915 decoder"),
    "multimon-ng": (T1, ("multimon-ng",), "POCSAG/FLEX/AFSK/DTMF"),
    "direwolf": (T1, ("direwolf",), "AX.25 soundmodem; also in our packet core"),
    "fldigi": (T1, ("fldigi",), "already in the catalog"),
    "WSJT-X": (T1, ("wsjtx",), "already in the catalog"),
    "JS8Call": (T1, ("js8call",), "already in the catalog"),
    "QSSTV": (T1, ("qsstv",), "SSTV"),
    "Gpredict": (T1, ("gpredict",), "satellite tracking"),
    "gpsd / ffmpeg / sox": (T1, ("gpsd", "ffmpeg", "sox"), "infrastructure the rest depends on"),
    "inspectrum": (T1, ("inspectrum",), "offline signal visualiser"),
    "GQRX-SDR": (T1, ("gqrx-sdr",), "SDR receiver; Blend `sdr`"),
    "CubicSDR": (T1, ("cubicsdr",), "SDR receiver; Blend `sdr`"),
    "SoapySDR": (T1, ("soapysdr-tools",), "device abstraction; Blend `sdr`"),
    "GNU Radio": (T1, ("gnuradio", "gr-osmosdr", "libvolk-dev"), "framework; Tier 3 depends on it"),
    "UHD": (T1, ("uhd-host", "python3-uhd"), "USRP host tools"),
    "HackTV / HackTV-GUI": (T1, ("hacktv",), "analogue TV transmitter; Blend `nonamateur`"),
    # --- Tier 1: not in apt, but an upstream .deb exists -----------------
    "SDRAngel": (T1, ("sdrangel",), "upstream .deb per Ubuntu release; apt on Kali"),
    "SDRPP": (T1, ("sdrpp",), "upstream .deb; apt on Kali and Parrot"),
    "SatDump": (T1, ("satdump",), "upstream .deb; apt on all four"),
    "AIS-Catcher": (T1, ("ais-catcher",), "upstream .deb; manifest already written"),
    # --- Tier 2: maintained upstream, no .deb; a build or a runtime ------
    "SigDigger": (T2, ("sigdigger",), "no .deb; CMake build"),
    "SDRTrunk": (T2, ("sdrtrunk",), "Java zip release"),
    "Universal Radio Hacker": (T2, ("urh",), "PyPI only, and upstream is archived"),
    "QSpectrumAnalyzer": (T2, ("qspectrumanalyzer",), "PyPI"),
    "GridTracker": (T2, (), "Electron app"),
    "NRSC5": (T2, ("nrsc5",), "CMake build"),
    "DSD-FME": (T2, ("dsd",), "CMake build; needs libmbe"),
    "ACARSDEC": (T2, ("acarsdec",), "CMake build — see the Skywave inventory"),
    "DumpVDL2": (T2, ("dumpvdl2",), "CMake build"),
    "DumpHFDL": (T2, ("dumphfdl",), "CMake build"),
    "iridium-toolkit": (T2, ("iridium-toolkit",), "Python, no licence file upstream"),
    "radiosonde_auto_rx": (T2, ("radiosonde-auto-rx",), "AHRL REVIVE candidate; venv backend"),
    "rtlamr / rtl-power-fftw": (T2, ("rtlamr", "rtl-power-fftw"), "Go binary / CMake build"),
    "LuaRadio": (T2, ("luaradio",), "Lua DSP framework"),
    "QRadioLink": (T2, ("qradiolink",), "CMake build"),
    "WFView": (T2, (), "Icom rig control; CMake build"),
    "HamClock": (T2, (), "see Q-006 — four candidate sources"),
    "CyberEther": (T2, (), "Vulkan/CUDA; heavy GPU dependency"),
    "SDRconnect": (T2, (), "SDRplay, closed source — same objection Skywave raised"),
    "SparkSDR": (T2, (), "closed-source freeware"),
    "SpyServer": (T2, (), "Airspy, closed-source binary"),
    "baudline": (T2, (), "closed-source binary, fetched on first run"),
    "dump1090-fa": (
        T2,
        ("dump1090-fa",),
        "FlightAware repo; `readsb` is our default per overlaps.md",
    ),
    "PySDR": (T2, (), "a textbook, not software"),
    "Blue Dragon": (T2, (), "DragonOS-original BT sniffer"),
    "Iridium-Sniffer / Inmarsat-Sniffer / Meshtastic-Sniffer": (T2, (), "DragonOS-original"),
    # --- Tier 3: GNU Radio out-of-tree ----------------------------------
    "GR OOT modules": (T3, (), "gr-lora_sdr, gr-ieee802-11, gr-tempest, gr-bladeRF, gr-iridium"),
    # --- Hardware libraries and firmware: M4, not the catalog ------------
    "USRP / UHD": (HW, (), "device support"),
    "BladeRF": (HW, (), "device support"),
    "HackRF One": (HW, (), "device support"),
    "LimeSDR": (HW, (), "device support"),
    "RTL-SDR": (HW, (), "device support"),
    "Airspy": (HW, (), "device support"),
    "SDRplay": (HW, (), "closed API — see the Skywave inventory"),
    "ADALM-Pluto": (HW, (), "device support"),
    "HydraSDR": (HW, (), "device support"),
    "Fobos SDR": (HW, (), "device support"),
    "SDDC": (HW, (), "RX888/RX666/BBRF103"),
    "Mirics": (HW, (), "device support"),
    "Red Pitaya": (HW, (), "device support"),
    "SoapyRemote": (HW, (), "network SDR"),
    "VITA 49 / VRT": (HW, (), "network IQ transport"),
    "libbladeRF": (HW, ("libbladerf2",), "library + firmware images"),
    "HackRF": (HW, ("hackrf", "libhackrf0"), "library"),
    "LimeSuiteNG 0+git8f0bdeb / limepcie-dkms": (
        HW,
        ("limesuite",),
        "library + DKMS kernel module",
    ),
    "HydraSDR / Fobos SDR / SDRplay API 3.15.2 / libmirisdr4 / rtl-sdr / airspy / airspyhf": (
        HW,
        ("rtl-sdr", "airspy", "airspyhf", "libmirisdr4"),
        "library set",
    ),
    "OpenCL: intel-opencl-icd, mesa-opencl-icd": (HW, (), "GPU acceleration for SatDump"),
    # --- DragonOS-specific platform: out of scope ------------------------
    "dragon-speech": (BASE, (), "DragonOS-original STT/TTS"),
    "dragon-brain": (BASE, (), "DragonOS-original LLM front end"),
    "dragon-rf": (BASE, (), "DragonOS-original agent"),
    "dragon-gateway": (BASE, (), "DragonOS-original MCP surface"),
    "dragon-provider": (BASE, (), "DragonOS-original runtime"),
    "sdr4space-sdrvm": (BASE, (), "DragonOS-original capture engine"),
    "dragonos-dmr-trunk": (BASE, (), "DragonOS-original DMR site"),
    "dragon-dmr-agent": (BASE, (), "DragonOS-original"),
    # --- Cellular / EW: flagged, not classified --------------------------
    "ransack": (EW, (), "LTE/cellular survey provider"),
    "LTESniffer 2.1.1 / ltesniffer-dl": (EW, (), "LTE downlink+uplink IMSI/RNTI sniffer"),
    "FALCON": (EW, (), "live LTE PDCCH/DCI decoder"),
    "intrusive-lte-mme": (EW, (), "rogue LTE MME / IMSI-catcher lab — **transmits**"),
    "lte-scan": (EW, (), "LTE scanner"),
    "sni5gect": (EW, (), "5G injection"),
    "fiveg-nid": (EW, (), "5G network identity"),
    "ella-core": (EW, (), "5G core"),
    "ocudu": (EW, (), "O-RAN CU/DU"),
    "osmo-nid": (EW, (), "network identity"),
    "srsRAN_4G": (EW, (), "full LTE stack — **transmits**"),
    "gr-gsm": (EW, ("gr-gsm",), "GSM receiver; **in apt on Debian, Kali and Parrot**"),
    "IMSI-catcher": (EW, (), "passive IMSI collection from GSM"),
    "QCSuper": (EW, (), "Qualcomm diagnostic capture; receive-only"),
    "kalibrate-hydrasdr": (EW, (), "clock calibration off GSM bursts"),
    "cmas-pws-4g": (EW, (), "public warning system decoder"),
    "Osmocom core": (EW, (), "full GSM network stack — **transmits**"),
    "osmo-trx 1.7.1 / osmo-sip-connector": (EW, (), "GSM transceiver — **transmits**"),
    "OsmocomBB": (EW, (), "GSM baseband"),
    "Asterisk": (EW, ("asterisk",), "PBX; in apt on Ubuntu and Kali"),
}


def fetch() -> None:
    SRC.mkdir(parents=True, exist_ok=True)
    subprocess.run(["curl", "-sSL", "-o", str(README), README_URL], check=True)
    print(f"fetched {README}")


def parse_readme() -> tuple[str, str, list[tuple[str, str, str]]]:
    """Return (release, base, [(section, name, version), ...])."""
    text = README.read_text(errors="replace")
    parts = text.split("=" * 60)
    if len(parts) < 3:
        sys.exit("README layout changed: expected two '=' dividers")
    header, body = parts[1], parts[1]
    release = ""
    base = ""
    for line in header.splitlines():
        if line.startswith("DragonOS"):
            release = line.strip()
        elif line.startswith("*"):
            base = line.lstrip("*").strip()
        if release and base:
            break

    units: list[tuple[str, str, str]] = []
    section = ""
    for raw in body.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line in SECTIONS:
            section = line
            continue
        if raw[0].isspace() or not section:
            continue
        head = re.sub(r"\s*\(.*$", "", re.split(r"\s{2,}", line)[0]).strip()
        match = re.match(r"^(.*?)\s+((?:v?\d|0\+git)[\w.+-]*)$", head)
        name, version = (match.group(1).strip(), match.group(2)) if match else (head, "")
        units.append((section, name, version))
    return release, base, units


def parse_probe(target: str) -> dict[str, str]:
    path = REPO_ROOT / "reference" / "probes" / f"dragonos-{target}.tsv"
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if "\t" in line:
            pkg, ver = line.split("\t", 1)
            out[pkg.strip()] = ver.strip()
    return out


DEB_UPSTREAM = {
    "SDRAngel": "`f4exb/sdrangel` publishes `sdrangel_7.27.2_ubuntu-26.04_amd64.deb`",
    "SDRPP": "`AlexandreRouma/SDRPlusPlus` publishes `sdrpp_debian_bookworm_amd64.deb`",
    "SatDump": "`SatDump/SatDump` publishes `satdump_1.2.2_ubuntu_24.04_amd64.deb`",
    "AIS-Catcher": "`jvde-github/AIS-catcher` publishes `ais-catcher_debian_bookworm_amd64.deb`",
}


def render() -> str:
    release, base, units = parse_readme()
    probes = {t: parse_probe(t) for t in TARGETS}

    unknown = sorted({n for _s, n, _v in units} - set(CURATION))
    if unknown:
        sys.exit(f"unclassified DragonOS units — add them to CURATION: {unknown}")

    by_tier: dict[str, list[tuple[str, str, str]]] = {}
    for section, name, version in units:
        tier = CURATION[name][0]
        by_tier.setdefault(tier, []).append((section, name, version))

    def apt_state(pkgs: tuple[str, ...]) -> dict[str, bool]:
        return {
            t: bool(pkgs) and all(probes[t].get(p, "-") not in ("", "-") for p in pkgs)
            for t in TARGETS
        }

    tier1 = by_tier.get(T1, [])
    # Guard: a T1 claim must be backed by apt somewhere or a named upstream .deb.
    for _s, name, _v in tier1:
        pkgs = CURATION[name][1]
        if not any(apt_state(pkgs).values()) and name not in DEB_UPSTREAM:
            sys.exit(f"{name} is marked Tier 1 but is in no target's apt and has no .deb")

    out: list[str] = []
    add = out.append
    add("# DragonOS — Tier 1 inventory")
    add("")
    add("Generated by `scripts/gen_dragonos_tier1.py`. Do not edit by hand —")
    add("regenerate. Versions come from DragonOS's published README; availability")
    add("comes from `apt-cache policy` measured inside each target container.")
    add("")
    add(f"**Release inventoried:** {release}  ")
    add(f"**Base:** {base}  ")
    add(f"**Source:** <{README_URL}>  ")
    add(f"**Project:** <{PROJECT_URL}>  ")
    add(f"**apt probes:** {', '.join(TARGETS)} — measured {date.today().isoformat()}  ")
    add(f"**Generated:** {date.today().isoformat()}")
    add("")
    add(SCOPE_NOTE)
    add("")
    add("---")
    add("")
    add("## Summary")
    add("")
    add("| Class | Units | In this document |")
    add("|---|---:|---|")
    labels = [
        (T1, "**Tier 1** — apt or upstream `.deb`", "**yes, in full**"),
        (T2, "Tier 2 — maintained upstream, needs a build", "named only"),
        (T3, "Tier 3 — GNU Radio out-of-tree", "named only"),
        (HW, "Hardware libraries and device support", "named only — M4 work"),
        (EW, "Cellular / EW", "**flagged for decision** — see Q-008"),
        (BASE, "DragonOS-specific platform", "named only — out of scope"),
    ]
    for key, label, shown in labels:
        add(f"| {label} | {len(by_tier.get(key, []))} | {shown} |")
    add(f"| **Total units in the README** | **{len(units)}** | |")
    add("")
    add("`SCOPE.md` sizes the 1.0 SIGINT profile from Tier 1; `profile-sizing.md`")
    add(f"estimated **~12 to 15** units. Measured: **{len(tier1)}** README units — but")
    add("most of those already arrive through the Debian Blend or the existing")
    add("catalog. The genuinely *new* SIGINT contribution is about ten packages, so")
    add("the estimate holds for sizing purposes even though the raw count is higher.")
    add("")
    add("---")
    add("")
    add(f"## Tier 1 — {len(tier1)} units")
    add("")
    add("Membership is decided by the probe, not by the list in `SCOPE.md`. The")
    add("generator refuses to emit a Tier 1 row that is in no target's apt and has")
    add("no named upstream `.deb`, so this table cannot silently overclaim.")
    add("")
    add("| Unit | DragonOS ver. | apt package(s) | deb 13 | ubu 26.04 | kali | parrot | Note |")
    add("|---|---|---|:-:|:-:|:-:|:-:|---|")
    for _section, name, version in sorted(tier1, key=lambda u: u[1].lower()):
        _tier, pkgs, note = CURATION[name]
        state = apt_state(pkgs)
        cells = "".join(" ✅ |" if state[t] else " — |" for t in TARGETS)
        names = ", ".join(f"`{p}`" for p in pkgs) if pkgs else "—"
        add(f"| **{name}** | {version or '—'} | {names} |{cells} {note} |")
    add("")
    add("✅ means *every* listed package resolves on that target. A dash means at")
    add("least one does not — the SoapySDR and GNU Radio rows bundle several.")
    add("")
    add("### The four that are `.deb`-only")
    add("")
    add("| Unit | Upstream artifact |")
    add("|---|---|")
    for unit, deb in DEB_UPSTREAM.items():
        add(f"| {unit} | {deb} |")
    add("")
    add(DEB_NOTE)
    add("")
    add("---")
    add("")
    add("## What the probe changed")
    add("")
    add(findings(probes))
    add("")
    add("---")
    add("")
    add("## Cellular / EW — flagged, not classified")
    add("")
    add(EW_PROSE)
    add("")
    add("| Unit | What it is |")
    add("|---|---|")
    for _s, name, _v in by_tier.get(EW, []):
        add(f"| `{name}` | {CURATION[name][2]} |")
    add("")
    add("---")
    add("")
    add("## Deferred — named, deliberately not inventoried")
    add("")
    add('`SCOPE.md`: *"Do not attempt Tier 3 before the source backend and pin')
    add('database are solid."* The same reasoning applies to Tier 2, which is')
    add("post-1.0. These are recorded so the denominator is honest and so nothing")
    add("is rediscovered later as if it were new.")
    add("")
    for key, heading in (
        (T2, "Tier 2"),
        (T3, "Tier 3"),
        (HW, "Hardware / drivers"),
        (BASE, "DragonOS-specific platform"),
    ):
        rows = by_tier.get(key, [])
        add(f"### {heading} — {len(rows)}")
        add("")
        add("| Unit | Note |")
        add("|---|---|")
        for _s, name, _v in sorted(rows, key=lambda u: u[1].lower()):
            add(f"| `{name}` | {CURATION[name][2]} |")
        add("")
    add("---")
    add("")
    add("## What this changes")
    add("")
    add(CONSEQUENCES)
    add("")
    return "\n".join(out) + "\n"


SCOPE_NOTE = """\
DragonOS is written and curated by **cemaxecuter**. Like AHRL, 73Linux and
Skywave it is an inventory source, never a base (**D-001**). It is by a wide
margin the largest and most expensive of the five, which is why `SCOPE.md` splits
it into tiers and admits only Tier 1 to 1.0.

**Tier 1 is the deliverable here.** Tiers 2 and 3 are counted and named so the
denominator is honest, and are otherwise left alone: `SCOPE.md` puts Tier 3
behind the source backend and the pin database, and neither exists yet.

One thing to state plainly up front: **DragonOS has moved.** Resolute R1 is a
ground-up rebuild on Ubuntu 26.04 whose headline features are an AI agent
platform, a drone-detection story, and a large cellular/EW section. That last
part is not a SIGINT profile in the sense `SCOPE.md` meant, and it is treated
separately below rather than folded into a package count."""

DEB_NOTE = """\
All four publish ordinary GitHub release assets with stable naming — no webpage
scraping, unlike HAMRS. None publishes a checksum file alongside, which is the
pin/hash sub-project `SCOPE.md` names, not a blocker for this inventory.

**Tested 2026-08-26 — the base mismatch was real, and worse than flagged.**
See `docs/reference/install-verification.md` for the full matrix.

| Artifact | Debian 13 | Ubuntu 26.04 |
|---|---|---|
| SatDump, built for Ubuntu 24.04 | ❌ unmet deps | ❌ unmet deps |
| SDR++, `debian_bookworm` | ❌ unmet deps | ❌ unmet deps |
| SDR++, `debian_sid` | ✅ | ✅ |
| SDRangel, built for Ubuntu 26.04 | ❌ unmet deps | ✅ |
| AIS-Catcher, `debian_bookworm` | ✅ | ✅ |

**Only two of the four reach a target through their `.deb`.** SatDump is still
Tier 1, but **by apt** — `satdump 1.2.2-1` is in Debian 13 and installs cleanly.
SDRangel is Tier 1 only on the base it was built for. SDR++ works only through
the `sid`-targeted artifact, which is not the obvious choice and is not
documented upstream.

**SDR++ also has no pinnable release.** Its assets hang off a rolling `nightly`
tag, so the URL never changes and the artifact behind it does. No version to
pin, no checksum published — the pin/hash sub-project `SCOPE.md` names, in its
sharpest form so far.

Consequence for the schema: these units need **per-target install blocks**, not
one URL each. `Selector` already expresses that; the manifests have to use it."""

EW_PROSE = """\
DragonOS Resolute R1 devotes an entire section to cellular and electronic
warfare. It is a substantial part of the release and it cannot be quietly folded
into a `sigint` profile, because it is not the same kind of thing as a passive
decoder.

**The distinction that matters is transmit.** Passively receiving and decoding
GSM control channels is a different legal and ethical category from operating a
rogue base station. DragonOS's own README describes
`intrusive-lte-mme` as a *"clean-room rogue LTE MME / IMSI-catcher lab"* and
qualifies it *"authorized RX/active use"*; `srsRAN_4G`, `Osmocom core` and
`osmo-trx` are complete network stacks that transmit. In most jurisdictions —
including the United States, where operating an unlicensed cellular base station
engages both FCC rules and federal interception statutes — running these against
live spectrum requires specific authorisation that an ordinary user will not
have. Note that DragonOS states the constraint itself; the caveat is in its
README, not something we are adding.

**This is not a refusal and not a judgement of DragonOS.** These are legitimate
tools with legitimate uses: authorised red-team engagements, lab work on
shielded benches, academic research, and vendor testing. DragonOS serves an
audience that has those authorisations. The question is whether **we** ship them
in a one-command installer aimed at licensed hams, where the barrier between
"installed" and "transmitting" is thin and the user may have no authorisation at
all.

`gr-gsm` is worth separating out: it is **in apt on Debian 13, Kali and Parrot**,
it is receive-only, and `PARITY-POLICY.md` already names it in the RF-security
ADD list with the caveat that upstream has stalled for modern GNU Radio.

**Recorded as Q-008 for the maintainer.** The recommendation there is to admit
the receive-only subset to the opt-in RF-security profile with legal framing
per CLAUDE.md, and to keep transmit-capable cellular network emulation out of
1.0 entirely — not because it is illegitimate, but because a curated installer
is the wrong delivery mechanism for it."""

CONSEQUENCES = """\
**Tier 1 is real, and it is cheaper than estimated.** `profile-sizing.md` sized
`sigint` at ~13 from the list in `SCOPE.md`. The measured Tier 1 set is close to
that in units, and most of it is already arriving through the Debian Blend or
the existing catalog — `fldigi`, `wsjtx`, `js8call`, `gpredict`, `direwolf`,
`gqrx-sdr`, `cubicsdr`, `soapysdr-tools`. The genuinely new SIGINT contribution
is a small set: `wireshark`, `aircrack-ng`, `hcxdumptool`/`hcxtools`,
`ubertooth`, `rtl-433`, `inspectrum`, plus the four `.deb` units.

**Kali is the best-covered target, and that is useful rather than incidental.**
It carries `kismet` (with drone-detection capture drivers), `sdrangel`, `sdrpp`
and `kalibrate-rtl` in apt where Debian 13 has none of them. Parrot — our primary
target — carries `kismet`, `sdrpp` and `gr-gsm`. Debian 13 is the *worst*-covered
of the four for this profile, which is worth knowing before the capability matrix
levels every claim down to it. The matrix should show the difference rather than
hide it; a Parrot or Kali user genuinely does get more here, and saying so is the
honest-gaps behaviour CLAUDE.md requires.

**`SCOPE.md`'s Tier 1 list needs correcting.** It names Kismet, readsb,
dumphfdl, DumpVDL2 and AIS-Catcher. Four of the five need a change; only
`readsb` survives as written.

- **Kismet is not in the Resolute R1 README at all.** It is in the FocalX
  README (Kismet 2023-07-R1, plus Kismet MetaGPSD and the Rest API), so
  `SCOPE.md`'s entry traces to the older release. The README is the project's
  own package list rather than a manifest, so this is evidence of absence
  rather than proof of it. Separately and independently of DragonOS, Kismet
  **is** apt-installable on Kali and Parrot — with drone-detection capture
  drivers on Kali — and not on Debian 13 or Ubuntu 26.04, and it ships an
  official signed apt repository our security rules permit when the manifest
  declares it and pins the key. It belongs in the profile on its own merits;
  it should stop being cited as a DragonOS inheritance.
- **`dumphfdl` and `DumpVDL2`** are in no target's apt, and in neither Debian
  stable nor unstable — measured in the Skywave inventory. They are Tier 2.
- **AIS-Catcher** is Tier 1, but by upstream `.deb`, not by apt.
- **readsb** is genuinely apt-installable and is already our ADS-B default per
  `overlaps.md`. It is not in the DragonOS README, which ships `dump1090-fa`
  instead; the `overlaps.md` recommendation is unaffected.

**Universal Radio Hacker is archived.** `jopohl/urh` is read-only on GitHub,
last pushed 2025-12-19, final release v2.10.0 — which is exactly the version
DragonOS ships. It has 12,500 stars and is in none of the four targets' apt —
and `tracker.debian.org/pkg/urh` returns 404 while `sources.debian.org` has no
exact match, so it appears never to have been packaged for Debian at all rather
than removed. `PARITY-POLICY.md` names URH in the RF-security ADD list;
that entry now needs a status. It is not broken, it is frozen, and it installs
from PyPI. Per **D-005** the verdict must be tested by us before it is written
down — and per `PARITY-POLICY.md`, "finished" is a legitimate state for a tool
to be in. Carried forward, not decided here.

**The GNU Radio version is the Tier 3 gate, and the news is good.** DragonOS
Resolute ships GNU Radio **3.10.12**, and so does every one of our four targets:

| Target | `gnuradio` | `gr-osmosdr` | `libvolk-dev` |
|---|---|---|---|
| debian-13 | 3.10.12.0-1 | 0.2.6-4 | 3.2.0-2 |
| ubuntu-26.04 | 3.10.12.0-6 | 0.2.6-6 | 3.3.0-2 |
| kali-rolling | 3.10.12.0-6+b3 | 0.2.6-6+b2 | 3.3.0-3 |
| parrot | 3.10.12.0-1 | 0.2.6-4 | 3.2.0-2 |

Same upstream GNU Radio across all four, differing only in Debian revision, and
matching what DragonOS built its modules against. That removes the worst version
of the Tier 3 problem — we are not chasing four different APIs — and reduces it
to the one `SCOPE.md` already describes: whether each module has a maintained
upstream for 3.10. `libvolk` does differ (3.2 on the Debian-13-derived targets,
3.3 on the newer ones), which is worth remembering when a module links it
directly.

None of this changes the gate. Tier 3 still waits on the source backend and the
pin database, and every module still has to record the API it was built against.
It does mean that when the gate opens, the target is a single API version."""


def findings(probes: dict[str, dict[str, str]]) -> str:
    """Derived: which packages differ across targets, so the prose cannot drift."""
    pkgs = sorted(probes[TARGETS[0]])
    everywhere = [p for p in pkgs if all(probes[t].get(p, "-") != "-" for t in TARGETS)]
    nowhere = [p for p in pkgs if all(probes[t].get(p, "-") == "-" for t in TARGETS)]
    split = [p for p in pkgs if p not in everywhere and p not in nowhere]
    rows = "\n".join(
        f"| `{p}` | "
        + " | ".join("✅" if probes[t].get(p, "-") != "-" else "—" for t in TARGETS)
        + " |"
        for p in split
    )
    return f"""\
{len(pkgs)} candidate package names were probed in each of the four target
containers. **{len(everywhere)}** resolve everywhere, **{len(nowhere)}** resolve
nowhere, and **{len(split)}** differ by target — which is the whole argument for
the capability matrix.

| Package | deb 13 | ubu 26.04 | kali | parrot |
|---|:-:|:-:|:-:|:-:|
{rows}

Two corrections to package names were needed along the way, and both would have
produced a false "not available" if published unchecked: `libvolk2-dev` is
`libvolk-dev` on current Debian, and `libmirisdr0` is `libmirisdr4`. Every
absence above was confirmed with `apt-cache search` on the name stem, not just
`apt-cache policy` on a guess."""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true", help="refresh the README")
    args = parser.parse_args()
    if args.fetch:
        fetch()
    if not README.exists():
        sys.exit(f"missing {README}; run with --fetch")
    OUT.write_text(render())
    print(f"wrote {OUT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
