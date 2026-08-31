#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Generate docs/reference/not-carried.md — every unit we do not carry, and why.

`PARITY-POLICY.md` promises that a user who moves here from AHRL or 73Linux
finds the dead weight gone *with an explanation*. The explanations exist — in
`dispositions.md`, a maintainer-facing analysis document — but a migrating
operator asking "where did Morse Runner go?" should not have to read a 700-line
classification record to find out. This page is that answer, one row per unit.

## Why the reasons live in this script rather than being parsed from prose

`dispositions.md` records its RETIRE and SUPERSEDE reasoning in prose sections
whose shape is not stable enough to parse. So the reasons here are a curated
table — but a *validated* one: this generator parses the complete index in
`dispositions.md` and refuses to run unless the curated tables cover exactly
the units the index marks RETIRE, SUPERSEDE and REVIVE. Add a disposition
there without a reason here and generation fails naming the unit; remove one
there and the stale entry here fails the same way. The reasons cannot drift
silently, which is the property a hand-written page could not have.

Replacements named by SUPERSEDE rows are checked against the catalog: a row
pointing at a manifest that does not exist fails generation.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from hammunition.manifest.load import load_catalog  # noqa: E402

CATALOG = REPO_ROOT / "catalog" / "packages"
DISPOSITIONS = REPO_ROOT / "docs" / "reference" / "dispositions.md"
OUT = REPO_ROOT / "docs" / "reference" / "not-carried.md"

GENERATED_LINE = re.compile(r"^\*\*Generated:\*\*")

#: RETIRE units: unit -> (where it came from, why it is not carried).
#: The reason categories are PARITY-POLICY's three: world changed, never
#: worked, out of scope. Wording condensed from dispositions.md.
RETIRED: dict[str, tuple[str, str]] = {
    # AHRL — world changed
    "noaa-apt": (
        "AHRL",
        "World changed — the NOAA APT satellites went out of service on "
        "2025-11-09. For today's weather satellites use **SatDump** (carried). "
        "This unit keeps a manifest with `status: retired` so the verdict and "
        "its provenance are findable where an operator would look (D-005).",
    ),
    "wine": (
        "AHRL",
        "Ruled out of the 1.0 core 2026-08-30 (Q-015 decision 5): its only "
        "AHRL consumer, Morse Runner, is reserved and no 1.0 profile needs "
        "Windows-compatibility machinery. VARA brings a *configured Wine "
        "prefix* back post-1.0 as its own prerequisite — a dependency of "
        "that unit, never a catalog unit of its own.",
    ),
    "rf_exposure_calc": (
        "AHRL",
        "Ruled 2026-08-30 (Q-015 decision 7): a menu entry that opens a URL "
        "is not software, and it rots exactly as fast as the URL. The "
        "power-density calculator link — and AHRL's five HF_Propagation "
        "bookmarks (DXLook, HamTab, OpenHamClock, PSKReporter, VOACAP) — "
        "live once, as prose, in `docs/guides/propagation.md`.",
    ),
    "solar_data": (
        "AHRL",
        "Ruled 2026-08-30 (Q-015 decision 7): same reasoning as "
        "`rf_exposure_calc`, plus its implementation depended on "
        "ImageMagick's deprecated `display`. The N0NBH banners it fetched "
        "are linked from `docs/guides/propagation.md` without the plumbing.",
    ),
    "xwxapt": (
        "AHRL",
        "World changed — same NOAA APT shutdown, same pointer: use **SatDump**. "
        "Note `xwefax` (HF radiofax) is *not* in this category: radiofax is "
        "still transmitted, and that unit is carried.",
    ),
    # AHRL — never worked
    "mfc_gpl": (
        "AHRL",
        "Never worked — an empty stub in AHRL v27 (the function body is "
        "comments), depending on the long-dead `libserial-0.1`. Byonics "
        "MicroFox config tool; AHRL's own SOFTWARE doc calls it obsolete and "
        "points at the Byonics website.",
    ),
    "tt3_gpl": (
        "AHRL",
        "Never worked — the same empty-stub shape and the same dead "
        "`libserial-0.1` dependency. Byonics TinyTrak3 configuration GUI.",
    ),
    # AHRL — out of scope
    "browser": (
        "AHRL",
        "Out of scope — we do not install web browsers; every target ships "
        "one. AHRL's browser logic was also its buggiest: `$BROWSER` is never "
        "assigned, and the snapd branch adds an unpinned PPA. Hammunition "
        "depends on `x-www-browser` existing and does not manage it.",
    ),
    "notepadqq": (
        "AHRL",
        "Out of scope — a general-purpose text editor, present for AHRL's "
        "ARRL Teachers Institute menu rather than for radio.",
    ),
    "tkcvs": (
        "AHRL",
        "Out of scope, and the world moved — a Tk GUI for CVS and Subversion. "
        "CVS is dead, and the unit had no menu entry in AHRL and no "
        "connection to radio.",
    ),
    "xosview": (
        "AHRL",
        "Out of scope — an X11 system-load monitor from the 1990s. No menu "
        "entry, not radio.",
    ),
    "backdrops": (
        "AHRL",
        "Out of scope — 20 MB of desktop wallpapers. Hammunition is not a "
        "desktop theme.",
    ),
    "pyautogui": (
        "AHRL",
        "Out of scope — AHRL's own menu-regression test harness, installed "
        "onto every user system. The equivalent here is CI, not a catalog "
        "entry.",
    ),
    "M0IAX": (
        "73Linux",
        "Ruled 2026-08-30 (Q-015 decision 11): JS8Call companion utilities, "
        "third-party and unproblematic — but with no measured demand from "
        "any JS8 operator here. Not carried in 1.0; a post-1.0 candidate "
        "the moment a JS8 profile user asks. Retired with a reason, not "
        "retired as dead.",
    ),
    "PATMENU3": (
        "73Linux",
        "Ruled 2026-08-30 (Q-015 decision 12): doubly unneeded. KM4ACK's "
        "menu wrapper is licence-blocked (D-001) — and the interface it "
        "fronts ships with Pat itself: `pat http` serves the full Winlink "
        "web UI at localhost:8080, documented in the packet profile. "
        "Writing a licence-clean clone of a wrapper around a built-in "
        "feature would be work spent making the product worse.",
    ),
    # 73Linux — licence-blocked scripts (D-001: no licence file in the
    # repository, so KM4ACK's own works cannot be redistributed or derived
    # from; third-party software he *installs* is unaffected).
    "EES": (
        "73Linux",
        "KM4ACK's own script (an emergency email server) in an unlicensed "
        "repository — we cannot ship or derive from it (D-001). The function "
        "is genuinely useful; a licensed equivalent is the path if one is "
        "wanted.",
    ),
    "GPSUPDATE": (
        "73Linux",
        "KM4ACK's own script, unlicensed repository (D-001). GPS-driven "
        "time/position update for the Pi image workflow.",
    ),
    "SHOWLOG": (
        "73Linux",
        "KM4ACK's own script, unlicensed repository (D-001).",
    ),
    "SECURITY": (
        "73Linux",
        "KM4ACK's own script, unlicensed repository (D-001).",
    ),
    "GRIDCALC": (
        "73Linux",
        "KM4ACK's own grid-square calculator, unlicensed repository (D-001). "
        "Useful function; if wanted, we write our own or carry a licensed "
        "equivalent.",
    ),
    "DIPOLE": (
        "73Linux",
        "KM4ACK's own dipole calculator, unlicensed repository (D-001). Same "
        "position as GRIDCALC.",
    ),
    "BATT": (
        "73Linux",
        "KM4ACK's own script, unlicensed repository (D-001).",
    ),
    "PIQSO": (
        "73Linux",
        "KM4ACK's own script, unlicensed repository (D-001).",
    ),
    "PATMENU": (
        "73Linux",
        "KM4ACK's own earlier PAT menu wrapper, unlicensed repository "
        "(D-001). Its successor PATMENU3 is a separate, still-open decision.",
    ),
    # 73Linux — out of scope
    "CONKY": (
        "73Linux",
        "Out of scope — a system monitor, not radio.",
    ),
    "PISTATS": (
        "73Linux",
        "Out of scope — a system monitor, not radio.",
    ),
    "VNC": (
        "73Linux",
        "Out of scope — RealVNC viewer, a proprietary general-purpose remote "
        "desktop.",
    ),
}

#: SUPERSEDE units: unit -> (what to use instead, the one-line trade-off).
#: `instead` is prose; `manifest` names the catalog entry that carries the
#: replacement and is validated to exist. None means the replacement is the
#: Hammunition engine itself rather than software.
SUPERSEDED: dict[str, tuple[str, str | None, str]] = {
    "aa-analyzer": (
        "`flaa`",
        "flaa",
        "Both are RigExpert antenna-analyser front ends; flaa is the "
        "maintained W1HKJ one.",
    ),
    "dump1090": (
        "`readsb`",
        "readsb",
        "readsb is the maintained ADS-B decoder descended from dump1090; "
        "AHRL built an unversioned `dump1090-master` snapshot.",
    ),
    "ESPHamClock": (
        "`hamclock-next` / `openhamclock`",
        "hamclock-next",
        "HamClock's author became a Silent Key on 2026-01-29 and the "
        "hamclock.com data feed sunset in June 2026. The community "
        "successors carry on; the default backend is `ohb.works` (Q-006).",
    ),
    "gpsman": (
        "`gpsbabel` + `gpsd`",
        "gpsbabel",
        "GPSMan is a Tcl relic; gpsbabel converts the data and gpsd serves "
        "the device. The replacement declares `supersedes: [gpsman]` itself.",
    ),
    "grig": (
        "`flrig`",
        "flrig",
        "Same function, maintained, richer rig support.",
    ),
    "owx": (
        "`chirp`",
        "chirp",
        "CHIRP programs the same Wouxun radios owx existed for, plus several "
        "hundred others.",
    ),
    "rtl_sdr_v4": (
        "the distribution's `librtlsdr` (manifest `rtl-sdr`)",
        "rtl-sdr",
        "AHRL hand-deletes the distro library and installs the RTL-SDR Blog "
        "fork from an unpinned clone. We carry the distribution package and "
        "handle the V4 situation by disclosure, not displacement (D-022).",
    ),
    "virtual_radar_server": (
        "`readsb`",
        "readsb",
        "VRS is a dormant Mono application that needs a bundled config patch "
        "just to start. readsb is native and maintained; the tar1090 web "
        "front end it pairs with is in no target's archive, which is a "
        "documented gap rather than a shim.",
    ),
    "vdlm2dec": (
        "`dumpvdl2`",
        "dumpvdl2",
        "dumpvdl2 is the maintained VDL Mode 2 decoder; vdlm2dec's upstream "
        "is archived. The manifest records `superseded_by`.",
    ),
    "ahrl_docs": (
        "the Hammunition engine",
        None,
        "The generated package reference replaces AHRL's PACKAGES/VERSIONS "
        "files (SUPERSEDE #8-12).",
    ),
    "ahrl_menus": (
        "the Hammunition engine",
        None,
        "Profiles and desktop integration replace the xdg menu installer "
        "(SUPERSEDE #8-12).",
    ),
    "ahrl_version": (
        "the Hammunition engine",
        None,
        "`hammunition --version` and `hammunition status` replace the "
        "generated two-line version script (SUPERSEDE #8-12). The flag was "
        "missing until the first VM campaign noticed; added 2026-08-29.",
    ),
    "libhamlib4": (
        "apt `depends` resolution",
        None,
        "A shared library with no operator surface is a dependency, not a "
        "unit: every rig-control manifest that needs hamlib declares it, apt "
        "installs it, and `libhamlib-utils` is the operator-facing hamlib "
        "manifest. Ruled by the maintainer 2026-08-30 (Q-015 decision 3).",
    ),
    "source_libs": (
        "the Hammunition engine",
        None,
        "Manifests declare their own build dependencies; a blanket toolchain "
        "install is replaced by per-unit `build_depends` (SUPERSEDE #8-12).",
    ),
}

#: REVIVE units: unit -> status line. These are the units AHRL shipped
#: disabled (or dead) that the policy says to bring back rather than bury.
#: `manifest` is validated to exist when named.
REVIVED: dict[str, tuple[str | None, str]] = {
    "ardop": (
        "ardopcf",
        "**Revived** (tested 2026-08-28, Debian 13). AHRL's compile error was "
        "not the error: GCC 14 promotes `-Wint-conversion`, and with that "
        "flag relaxed the tag builds clean. Carried as `ardopcf` in the 1.0 "
        "packet core. Caveat recorded in the manifest: the silenced warning "
        "is a real bug in the CM108 PTT path — test CM108 keying before "
        "relying on it; serial and VOX keying are unaffected.",
    ),
    "hamclock_next": (
        "hamclock-next",
        "**Revived.** AHRL v27's own dead code — the install function, "
        "tarball and menu entry all exist, but the function is never called. "
        "Carried as `hamclock-next`, the HamClock successor.",
    ),
    "dream": (
        None,
        "**Still blocked** (measured 2026-08-28): `libqt5webkit5-dev` has no "
        "candidate on Debian 13. Open question: whether Qt5 WebKit is truly "
        "required or only feeds an optional dashboard — that needs the "
        "source read, not the archive probed. Possibly the only DRM decoder, "
        "so this is a documented gap, not a quiet removal.",
    ),
    "mvoice": (
        None,
        "**Still blocked** (measured 2026-08-28): `libopendht-dev` has no "
        "candidate on Debian 13. Upstream is alive and instructs users to "
        "build OpenDHT from source — a build dependency that must itself be "
        "built, which no manifest here can express yet. M17 remains on the "
        "roadmap regardless (D-007).",
    ),
    "ibp": (
        None,
        "**Not yet attempted.** Plan: build current source with the "
        "`-Wno-implicit-int` family AHRL itself used before disabling it. If "
        "it still fails, find a successor that shows IBP beacon status — the "
        "beacons still transmit, so this never becomes RETIRE.",
    ),
    "radiosonde_auto_rx": (
        None,
        "**Waiting on the venv backend, by design.** AHRL's objection — the "
        "upstream install hardcodes user `pi` and lives in `$HOME` — is "
        "exactly what `scope: user` plus a venv backend exists to handle.",
    ),
}

#: Units the index still classes as reserved-to-maintainer (M) or
#: NEEDS-DECISION (?) but whose recorded resolution is "not carried". Each
#: entry asserts the index code it expects: when dispositions.md promotes the
#: unit to X, this table fails loudly and the entry moves to RETIRED.
RESOLVED_NOT_CARRIED: dict[str, tuple[str, str, str]] = {
    "arduino": (
        "M",
        "AHRL",
        "Resolved 2026-08-25: not carried. The Debian `arduino` package is "
        "Arduino IDE 1.x, deprecated upstream, and shipping a deprecated IDE "
        "is worse than shipping nothing. Install IDE 2.x from arduino.cc.",
    ),
    "morse_runner": (
        "M",
        "AHRL",
        "Resolved 2026-08-25, conditional: a Windows binary under Wine, "
        "x86_64-only — ARM users already got nothing. If Morse Runner CE or "
        "a native alternative builds, that is carried and Wine leaves the "
        "1.0 core; otherwise it defers post-1.0 alongside VARA. Either way "
        "no Wine prefix ships in 1.0 for one CW trainer. Native CW trainers "
        "carried today: `qrq`, `xcwcp`, `ebook2cwgui`, `wordsworth`.",
    ),
}


def normalise(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def parse_index() -> list[tuple[str, str]]:
    """(unit, disposition code) for every unit in the complete index.

    Same parse as scripts/gen_parity_coverage.py, same loud failure if the
    index shape changes.
    """
    _, _, index = DISPOSITIONS.read_text().partition("## Complete index")
    units = [
        (match.group(1).strip(), match.group(2))
        for match in re.finditer(r"`([A-Za-z0-9_.+\- ]+)`\s*([SRXCAM?])", index)
    ]
    if not units:  # pragma: no cover - guards a restructure of the source doc
        sys.exit("no units parsed from dispositions.md; the index shape changed")
    return units


def validate(units: list[tuple[str, str]], catalog_names: set[str]) -> None:
    """Every curated table covers exactly what the index says it must."""
    by_code: dict[str, set[str]] = {}
    for unit, code in units:
        by_code.setdefault(code, set()).add(unit)

    problems: list[str] = []
    for label, table, code in (
        ("RETIRED", set(RETIRED), "X"),
        ("SUPERSEDED", set(SUPERSEDED), "S"),
        ("REVIVED", set(REVIVED), "R"),
    ):
        expected = by_code.get(code, set())
        for unit in sorted(expected - table):
            problems.append(f"{label}: index marks `{unit}` {code} but no reason is recorded here")
        for unit in sorted(table - expected):
            problems.append(f"{label}: `{unit}` has an entry here but the index does not mark it {code}")

    index_codes = dict(units)
    for unit, (expected_code, _, _) in RESOLVED_NOT_CARRIED.items():
        actual = index_codes.get(unit)
        if actual != expected_code:
            problems.append(
                f"RESOLVED_NOT_CARRIED: `{unit}` expected index code {expected_code}, "
                f"found {actual!r} — dispositions.md moved; move this entry too"
            )

    for unit, (_, manifest, _) in SUPERSEDED.items():
        if manifest is not None and manifest not in catalog_names:
            problems.append(f"SUPERSEDED: `{unit}` points at manifest `{manifest}`, which does not exist")
    for unit, (manifest, _) in REVIVED.items():
        if manifest is not None and manifest not in catalog_names:
            problems.append(f"REVIVED: `{unit}` points at manifest `{manifest}`, which does not exist")

    if problems:
        sys.exit("not-carried tables disagree with dispositions.md:\n  " + "\n  ".join(problems))


def render(catalog_names: set[str]) -> str:
    units = parse_index()
    validate(units, catalog_names)

    out = [
        "<!-- Generated by scripts/gen_not_carried.py. Do not edit by hand -->",
        "",
        "# Not carried, and why",
        "",
        "Generated by `scripts/gen_not_carried.py`. Do not edit by hand —",
        "regenerate. The reasons live in that script and are validated against",
        "the complete index in `docs/reference/dispositions.md`: a disposition",
        "added there without a reason here fails generation by name.",
        "",
        f"**Generated:** {date.today().isoformat()}",
        "",
        "If you came here from Andy's Ham Radio Linux or 73Linux and something",
        "you used is missing, this page says why. `PARITY-POLICY.md` promises",
        "that nothing is dropped silently: every unit from the five inventory",
        "sources is either carried, replaced by something better with the",
        "trade-off stated, brought back from the dead, or listed here with its",
        "reason. Reproducing the sources faithfully — broken and obsolete",
        "entries included — would be a worse product than the sources.",
        "",
        "This page covers what is *decided*. Units still awaiting a decision",
        "are in `dispositions.md` under NEEDS-DECISION, and units that are",
        "coming but not yet built are in `parity-coverage.md` under",
        "*outstanding, with a reason*.",
        "",
        "---",
        "",
        "## Retired",
        "",
        "Gone on purpose, per the policy's three reason categories: the world",
        "changed, it never worked, or it was never radio.",
        "",
        "| Unit | From | Why |",
        "|---|---|---|",
    ]
    for unit in sorted(RETIRED, key=str.lower):
        source, why = RETIRED[unit]
        out.append(f"| `{unit}` | {source} | {why} |")

    out += [
        "",
        "## Superseded — use this instead",
        "",
        "Same job, better tool. Where the replacement is a catalog manifest it",
        "declares the supersession itself (`supersedes:`), so the link is",
        "reviewable at the manifest rather than only here.",
        "",
        "| Unit | Use instead | Trade-off |",
        "|---|---|---|",
    ]
    for unit in sorted(SUPERSEDED, key=str.lower):
        instead, _, why = SUPERSEDED[unit]
        out.append(f"| `{unit}` | {instead} | {why} |")

    out += [
        "",
        "## Revived — AHRL shipped it broken or disabled; we are bringing it back",
        "",
        "AHRL v27 disables nine units with reasons in comments. Four are",
        "retired above (`noaa-apt`, `xwxapt`, `mfc_gpl`, `tt3_gpl`). The rest",
        "are REVIVE: the policy forbids inheriting a broken verdict without",
        "testing it ourselves, and testing has already overturned one.",
        "",
        "| Unit | Status |",
        "|---|---|",
    ]
    for unit in sorted(REVIVED, key=str.lower):
        _, status = REVIVED[unit]
        out.append(f"| `{unit}` | {status} |")

    out += [
        "",
        "## Decided by the maintainer — not carried",
        "",
        "Classified *reserved to the maintainer* in the index; the recorded",
        "resolution is not to carry them.",
        "",
        "| Unit | From | Resolution |",
        "|---|---|---|",
    ]
    for unit in sorted(RESOLVED_NOT_CARRIED, key=str.lower):
        _, source, why = RESOLVED_NOT_CARRIED[unit]
        out.append(f"| `{unit}` | {source} | {why} |")

    out += [
        "",
        "---",
        "",
        "## What this page is not",
        "",
        "- **Not a list of gaps.** A unit that is coming but waits on a",
        "  backend is in `parity-coverage.md`, with what it waits on.",
        "- **Not a list of open questions.** Units whose fate is undecided",
        "  (`claws-mail`, `putty`, `jtdx`, the bookmark launchers, and the",
        "  rest of NEEDS-DECISION) are in `dispositions.md` with the specific",
        "  question each needs answered.",
        "- **Not inherited verdicts.** Where a unit is here because something",
        "  is broken or dead, the claim was tested by this project or cites",
        "  the event that settled it — never copied from an upstream comment",
        "  (D-005, and the `ardop` row above is why).",
        "",
    ]
    return "\n".join(out)


def _without_date(text: str) -> list[str]:
    return [line for line in text.splitlines() if not GENERATED_LINE.match(line)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if out of date")
    args = parser.parse_args()

    catalog_names = set(load_catalog(CATALOG))
    body = render(catalog_names)
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
