#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Generate docs/reference/parity-coverage.md — every dispositioned unit, and
whether the catalog has it yet.

`PARITY-POLICY.md` gives each of the 150 units in `dispositions.md` exactly one
disposition. That says what SHOULD happen to each. Nothing until now said what
HAS happened, so "how far along is the catalog" was a question answered by
counting files — which measures effort rather than coverage, and cannot tell a
unit that is deliberately absent from one that was forgotten.

The distinction this report exists to make: **a RETIRE unit with no manifest is
finished work, not a gap.** So is a unit reserved to the maintainer, or one
whose disposition is NEEDS-DECISION. Only CARRY, SUPERSEDE, REVIVE and ADD owe
the catalog a manifest, and only those are counted against it.

## How units are matched to manifests

Unit names come from AHRL's toggles, 73Linux's filenames and upstream project
names, so `SDR++` has to find `sdrpp` and `AX25` has to find `ax25-tools`.
Three passes, in order:

1. **Normalised name** — lowercase, punctuation stripped. Catches `AIS-catcher`
   → `ais-catcher` and most of the catalog.
2. **What manifests declare** — apt package names, `provides`, and `supersedes`.
   This is why `gpsman` finds `gpsbabel`: the replacement says so itself, which
   makes the link reviewable in the manifest rather than only here.
3. **`ALIASES` below** — the residue, each with a reason. Every entry is a claim
   and is written to be checked.

Anything still unmatched is reported as missing. A wrong alias would hide a gap,
so the table is deliberately small and each line says why it exists.
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
from hammunition.manifest.schema import AptInstall, PackageManifest, Status  # noqa: E402

CATALOG = REPO_ROOT / "catalog" / "packages"
DISPOSITIONS = REPO_ROOT / "docs" / "reference" / "dispositions.md"
OUT = REPO_ROOT / "docs" / "reference" / "parity-coverage.md"

CODES = {
    "C": "CARRY",
    "S": "SUPERSEDE",
    "R": "REVIVE",
    "X": "RETIRE",
    "A": "ADD",
    "?": "NEEDS-DECISION",
    "M": "reserved to maintainer",
}

#: Dispositions that owe the catalog a manifest. The rest are complete without
#: one, which is the distinction this whole report exists to draw.
OWES_A_MANIFEST = {"C", "S", "R", "A"}

#: Unit name -> manifest name, where nothing the manifests declare can bridge
#: the gap. Each is a claim; each says why.
ALIASES: dict[str, str] = {
    # Renamed on the way into Debian.
    "SDR++": "sdrpp",
    "gqrx": "gqrx-sdr",
    "tqsl": "trustedqsl",
    "svxlink": "svxlink-server",
    # AHRL's toggle names an upstream, ours names the package that provides it.
    "rtl_sdr_v4": "rtl-sdr",
    "ardop": "ardopcf",
    "radiosonde_auto_rx": "radiosonde-auto-rx",
    "GPS": "gpsd",
    # 73Linux filenames for third-party software.
    "AX25": "ax25-tools",
    "BPQ": "linbpq",
    # 73Linux filenames again: PITERM is QtTermTCP, QTSOUND is QtSoundModem,
    # PIAPRS is QtBPQAPRS.
    "PITERM": "qttermtcp",
    "QTSOUND": "qtsoundmodem",
    "PIAPRS": "qtbpqaprs",
    # SUPERSEDE #3: aa-analyzer -> flaa, both RigExpert analyser front ends.
    "aa-analyzer": "flaa",
    # SUPERSEDE #4: Virtual Radar Server -> readsb + tar1090. readsb is the
    # decoder half and is what this catalog carries; tar1090 is a web front end
    # and is in no target's archive.
    "virtual_radar_server": "readsb",
}

#: Units with no manifest for a reason that is recorded elsewhere. Keeps the
#: "missing" list to things genuinely undone.
EXPLAINED: dict[str, str] = {
    "ahrl_docs": "SUPERSEDE #8-12 — replaced by our own engine, not by software",
    "ahrl_menus": "SUPERSEDE #8-12 — replaced by our own engine",
    "ahrl_version": "SUPERSEDE #8-12 — replaced by our own engine",
    "FoxTelem": "post-1.0 — pending an AMSAT constellation census: a partial world-changed case, and neither blocking 1.0 on a satellite survey nor quietly carrying a decoder for re-entered spacecraft serves anybody (Q-015 decision 10, 2026-08-30)",
    "country_files": "post-1.0 — the first data-asset-with-an-update-cadence; a monthly fan-out file deserves a schema shape, not a shoehorn. The consuming apps bundle their own cty.dat meanwhile (Q-015 decision 8, 2026-08-30)",
    "source_libs": "SUPERSEDE #8-12 — replaced by our own engine",
    "libhamlib4": "SUPERSEDE #8-12 — a dependency, not a unit; apt `depends` carries it and `libhamlib-utils` is the operator-facing manifest (Q-015 decision 3, 2026-08-30)",
    "dream": "REVIVE blocked: libqt5webkit5-dev has no candidate on Debian 13 (measured)",
    "mvoice": "REVIVE blocked: libopendht-dev has no candidate on Debian 13 (measured)",
    "ARDOPGUI": "post-1.0 — GUI for ARDOP; ruled CARRY (post-1.0) in dispositions.md, so 1.0 ships `ardopcf` headless",
    "VARA": "post-1.0 — closed software needing a configured Wine prefix",
    "VARIM": "post-1.0 — VARA's messaging client, same constraint",
    "HAMRS": "post-1.0 — AppImage",
    "reticulum-meshchat": "post-1.0 — AppImage, lands in the mesh profile",
}


def normalise(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def parse_index() -> list[tuple[str, str]]:
    """(unit, disposition code) for every unit in the complete index."""
    _, _, index = DISPOSITIONS.read_text().partition("## Complete index")
    units = [
        (match.group(1).strip(), match.group(2))
        for match in re.finditer(r"`([A-Za-z0-9_.+\- ]+)`\s*([SRXCAM?])", index)
    ]
    if not units:  # pragma: no cover - guards a restructure of the source doc
        sys.exit("no units parsed from dispositions.md; the index shape changed")
    return units


def lookup_table(catalog: dict[str, PackageManifest]) -> dict[str, str]:
    """Normalised name -> manifest name, from names and from what manifests declare."""
    table = {normalise(name): name for name in catalog}
    for name, manifest in catalog.items():
        for block in manifest.install:
            if isinstance(block.install, AptInstall):
                for package in block.install.packages:
                    table.setdefault(normalise(package), name)
        for provided in manifest.provides:
            table.setdefault(normalise(provided), name)
        for superseded in manifest.supersedes:
            table.setdefault(normalise(superseded), name)
    for unit, manifest_name in ALIASES.items():
        table[normalise(unit)] = manifest_name
    return table


def render(catalog: dict[str, PackageManifest]) -> str:
    units = parse_index()
    table = lookup_table(catalog)

    resolved: list[tuple[str, str, str | None]] = []
    for unit, code in units:
        resolved.append((unit, code, table.get(normalise(unit))))

    owed = [(u, c, m) for u, c, m in resolved if c in OWES_A_MANIFEST]
    covered = [(u, c, m) for u, c, m in owed if m]
    missing = [(u, c, m) for u, c, m in owed if not m]
    explained = [(u, c) for u, c, m in missing if u in EXPLAINED]
    unexplained = [(u, c) for u, c, m in missing if u not in EXPLAINED]

    bad_alias = sorted(unit for unit, target in ALIASES.items() if target not in catalog)

    out = [
        "<!-- Generated by scripts/gen_parity_coverage.py. Do not edit by hand -->",
        "",
        "# Parity coverage — what the catalog has, against what it owes",
        "",
        "Generated by `scripts/gen_parity_coverage.py`. Do not edit by hand —",
        "regenerate.",
        "",
        f"**Generated:** {date.today().isoformat()}  ",
        "**Source:** the complete index in `docs/reference/dispositions.md`, "
        "matched against `catalog/packages/`.",
        "",
        "`PARITY-POLICY.md` gives every unit one disposition, which says what",
        "*should* happen to it. This says what *has*. The distinction that makes",
        "the number mean anything: **a RETIRE unit with no manifest is finished",
        "work, not a gap**, and so is one reserved to the maintainer or awaiting a",
        "decision. Only CARRY, SUPERSEDE, REVIVE and ADD owe a manifest.",
        "",
        "---",
        "",
        "## Headline",
        "",
        "| | |",
        "|---|---:|",
        f"| Units in the five-source union | **{len(units)}** |",
        f"| …that owe a manifest (C, S, R, A) | **{len(owed)}** |",
        f"| …covered | **{len(covered)}** |",
        f"| …outstanding, with a recorded reason | **{len(explained)}** |",
        f"| …outstanding, unexplained | **{len(unexplained)}** |",
        f"| Manifests in the catalog | **{len(catalog)}** |",
        "",
        f"Coverage of what is owed: **{len(covered)}/{len(owed)}** "
        f"({100 * len(covered) // max(len(owed), 1)}%).",
        "",
        "The catalog is larger than the union because the Debian Blend contributes",
        "152 packages, most of which are not AHRL units, and because hardware",
        "support needs entries no inventory lists.",
        "",
    ]

    if bad_alias:
        out += [
            "> **This report has a broken alias.** "
            + ", ".join(f"`{a}` → `{ALIASES[a]}`" for a in bad_alias)
            + " names a manifest that does not exist, so a unit is being reported "
            "as covered by nothing. Fix `ALIASES` in the generator.",
            "",
        ]

    if unexplained:
        out += [
            "---",
            "",
            "## Outstanding and unexplained",
            "",
            "These owe a manifest, do not have one, and no reason is recorded.",
            "This list should be empty or shrinking; anything sitting here is work",
            "nobody has decided about.",
            "",
            "| Unit | Disposition |",
            "|---|---|",
        ]
        out += [f"| `{unit}` | {CODES[code]} |" for unit, code in sorted(unexplained)]
        out.append("")

    out += [
        "---",
        "",
        "## Outstanding, with a reason",
        "",
        "Absent on purpose. Each names what it waits on.",
        "",
        "| Unit | Disposition | Waiting on |",
        "|---|---|---|",
    ]
    for unit, code in sorted(explained):
        out.append(f"| `{unit}` | {CODES[code]} | {EXPLAINED[unit]} |")
    out.append("")

    by_code: dict[str, list[tuple[str, str, str | None]]] = {}
    for unit, code, manifest_name in resolved:
        by_code.setdefault(code, []).append((unit, code, manifest_name))

    out += [
        "---",
        "",
        "## By disposition",
        "",
        "| Disposition | Units | Covered |",
        "|---|---:|---:|",
    ]
    for code in ("C", "S", "R", "A", "X", "?", "M"):
        rows = by_code.get(code, [])
        got = sum(1 for _, _, m in rows if m)
        owes = "—" if code not in OWES_A_MANIFEST else str(got)
        out.append(f"| {CODES[code]} | {len(rows)} | {owes} |")
    out += [
        "",
        "RETIRE, NEEDS-DECISION and reserved units show no coverage figure because",
        "they owe nothing. Some carry a manifest anyway: `noaa-apt` is RETIRE and",
        "is in the catalog with `status: retired` and its provenance, because",
        "**D-005** says a verdict without provenance is not a verdict and the",
        "catalog is where an operator would look for it.",
        "",
        "---",
        "",
        "## Every unit",
        "",
        "| Unit | Disposition | Manifest |",
        "|---|---|---|",
    ]
    for unit, code, manifest_name in sorted(resolved, key=lambda r: r[0].lower()):
        if manifest_name:
            status = catalog[manifest_name].status
            mark = f"`{manifest_name}`"
            if status is not Status.supported:
                mark += f" *({status.value})*"
        elif unit in EXPLAINED:
            mark = "— *waiting, see above*"
        else:
            mark = "—"
        out.append(f"| `{unit}` | {CODES[code]} | {mark} |")
    out.append("")
    return "\n".join(out)


GENERATED_LINE = re.compile(r"^\*\*Generated:\*\*")


def _without_date(text: str) -> list[str]:
    return [line for line in text.splitlines() if not GENERATED_LINE.match(line)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if out of date")
    args = parser.parse_args()

    body = render(load_catalog(CATALOG))
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
