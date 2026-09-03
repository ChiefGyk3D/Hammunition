#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Generate docs/reference/capability-matrix.md.

CLAUDE.md: "Not every profile works everywhere. Manifests declare per-distro
support and the engine reports honest gaps rather than faking coverage."

`scripts/capability_matrix.py` answers a narrower question -- does a manifest
*resolve* to an install block on a given target -- and it answers it correctly.
What it cannot answer is whether the block would then work, and after this
catalog grew past two hundred manifests the difference stopped being academic:
most entries carry ONE unconditional apt block on purpose, because apt reports
the truth at plan time where a `when:` selector would freeze one evening's
measurement. Resolution therefore says "apt" for every target, including the
four where `sdrangel` does not exist.

This generator merges the resolution with a measured `apt-cache policy` sweep,
so a row says which targets actually offer the package rather than which
targets would try. Refresh the sweep first, from a list this generator writes
so that it cannot lag the catalog:

    scripts/gen_capability_matrix.py --package-list > reference/install-tests/catalog-apt.txt
    scripts/apt-policy-sweep.sh cat-<target> <image> reference/install-tests/catalog-apt.txt

The `cat-` prefix is what this generator reads (`policy-cat-<target>.tsv`);
the sweep script names its output after whatever it is given. A name the
catalog references that a target's sweep never measured renders `apt ?`, not
`apt ✗`: the sweep of 2026-08-28 used a hand-maintained list, ten manifests
added over the following days referenced names it did not have, and every
regeneration until 2026-09-03 reported all ten as absent from every archive
(D-031). The generator prints the shortfall to stderr, and
tests/test_docs_generated.py fails on it wherever the sweep exists.

**This is still the weaker of the two checks.** `apt-cache policy` proves the
archive offers a package; it does not prove dependency resolution succeeds.
`docs/reference/install-verification.md` is the stronger one and covers a
subset. Source and git rows are weaker again -- they say a build is declared,
not that it succeeds, and the manifests that HAVE been built say so in their
own notes.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

import yaml  # noqa: E402

from hammunition.distro import Target  # noqa: E402
from hammunition.manifest.load import load_catalog  # noqa: E402
from hammunition.manifest.schema import AptInstall, PackageManifest  # noqa: E402

CATALOG = REPO_ROOT / "catalog" / "packages"
TARGETS = REPO_ROOT / "containers" / "targets.yaml"
PROBES = REPO_ROOT / "reference" / "probes"
OUT = REPO_ROOT / "docs" / "reference" / "capability-matrix.md"

#: What a cell can say. Ordered worst to best for the summary counts.
ABSENT = "—"
NO_CANDIDATE = "apt ✗"
UNMEASURED = "apt ?"
APT = "apt"


def targets() -> list[tuple[str, Target]]:
    data = yaml.safe_load(TARGETS.read_text())
    out = []
    for entry in data["targets"]:
        out.append(
            (
                entry["name"],
                Target(
                    distro=entry["os_release_id"],
                    version=str(entry["os_release_version"]),
                    arch=entry["arch"],
                ),
            )
        )
    return out


def availability(name: str) -> dict[str, str] | None:
    """Measured `apt-cache policy` answers for one target, or None if unswept."""
    path = PROBES / f"policy-cat-{name}.tsv"
    if not path.exists():
        return None
    out: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if "\t" in line:
            pkg, version = line.split("\t", 1)
            out[pkg] = version
    return out


def apt_names(catalog: dict[str, PackageManifest]) -> list[str]:
    """Every apt package name any block in the catalog references, sorted.

    This is the sweep's input. It is derived rather than kept by hand so that
    a manifest added after the last sweep shows up as unmeasured, never as
    absent."""
    names: set[str] = set()
    for m in catalog.values():
        for block in m.install:
            if isinstance(block.install, AptInstall):
                names.update(block.install.packages)
    return sorted(names)


def cell(
    m: PackageManifest, target: Target, offered: dict[str, str] | None
) -> tuple[str, list[str], list[str]]:
    """Return (cell text, missing apt package names, unmeasured apt package names).

    Missing means the sweep asked and the archive had no candidate. Unmeasured
    means the sweep never asked -- the list predates the manifest -- and the
    cell says `apt ?` rather than claiming an absence nobody measured."""
    block = m.resolve(target.distro, target.version, target.arch)
    if block is None:
        return ABSENT, [], []
    install = block.install
    if not isinstance(install, AptInstall):
        return install.method, [], []
    if offered is None:
        return UNMEASURED, [], []
    unmeasured = [p for p in install.packages if p not in offered]
    if unmeasured:
        return UNMEASURED, [], unmeasured
    missing = [p for p in install.packages if offered[p] == "-"]
    return (NO_CANDIDATE if missing else APT), missing, []


def render(catalog: dict[str, PackageManifest]) -> str:
    names = targets()
    offered = {name: availability(name) for name, _ in names}
    swept = [n for n, o in offered.items() if o is not None]

    rows: dict[str, dict[str, str]] = {}
    gaps: dict[str, dict[str, list[str]]] = {}
    unmeasured: dict[str, set[str]] = {}
    for m in sorted(catalog.values(), key=lambda m: m.name):
        rows[m.name] = {}
        for name, target in names:
            text, missing, unasked = cell(m, target, offered[name])
            rows[m.name][name] = text
            if missing:
                gaps.setdefault(m.name, {})[name] = missing
            if unasked:
                unmeasured.setdefault(name, set()).update(unasked)
    for name in sorted(unmeasured):
        print(
            f"warning: {name}'s sweep never measured {len(unmeasured[name])} "
            f"package name(s) the catalog references -- rendered `{UNMEASURED}`, "
            f"not `{NO_CANDIDATE}`. Regenerate the list with --package-list and "
            f"re-sweep: {', '.join(sorted(unmeasured[name]))}",
            file=sys.stderr,
        )

    out: list[str] = [
        "<!-- Generated by scripts/gen_capability_matrix.py. Do not edit by hand -->",
        "",
        "# Capability matrix",
        "",
        "Generated by `scripts/gen_capability_matrix.py`. Do not edit by hand —",
        "regenerate.",
        "",
        f"**Generated:** {date.today().isoformat()}  ",
        "**Method:** manifest resolution against each target's declared "
        "`(distro, version, arch)`, merged with a measured `apt-cache policy` "
        "sweep inside that target's own image.",
        "",
        "Resolution alone would overstate coverage. Most manifests here carry one",
        "unconditional apt block on purpose — apt reports the truth at plan time,",
        "where a `when:` selector would freeze one evening's measurement — so",
        "resolution says `apt` for every target including the ones where the",
        "package does not exist. The sweep is what separates those.",
        "",
        "| Cell | Meaning |",
        "|---|---|",
        f"| `{APT}` | Resolves to an apt block **and every package has a candidate**. |",
        f"| `{NO_CANDIDATE}` | Resolves to apt, and at least one package is **not in that archive**. Listed below. |",
        "| `source` / `git` / `binary` / `venv` / `node` | Resolves to a build. Declared, not verified here — see below. |",
        f"| `{ABSENT}` | No install block resolves. The manifest does not claim this target. |",
        f"| `{UNMEASURED}` | Resolves to apt and the sweep never asked — either the "
        "target was not swept, or the sweep list predates the package. Not an "
        "absence: nobody measured it. |",
        "",
        "**This is the weaker of the two checks this repository runs.**",
        "`apt-cache policy` proves the archive *offers* a package; it does not",
        "prove dependency resolution succeeds. `install-verification.md` is the",
        "stronger check and covers a subset. `source` and `git` cells are weaker",
        "again: they say a build is declared, not that it succeeds. Manifests whose",
        "build HAS been run in a container say so in their own install notes.",
        "",
        "---",
        "",
        "## Summary",
        "",
    ]

    header = "| Target | " + " | ".join(("apt", "apt ✗", "build", "no block", "unswept")) + " |"
    out.append(header)
    out.append("|---|---:|---:|---:|---:|---:|")
    for target_name, _ in names:
        counts = {APT: 0, NO_CANDIDATE: 0, "build": 0, ABSENT: 0, UNMEASURED: 0}
        for cells in rows.values():
            value = cells[target_name]
            if value in {"source", "git", "binary", "venv", "node", "pipx"}:
                counts["build"] += 1
            else:
                counts[value] += 1
        suffix = "" if target_name in swept else " *(unswept)*"
        out.append(
            f"| {target_name}{suffix} | {counts[APT]} | {counts[NO_CANDIDATE]} | "
            f"{counts['build']} | {counts[ABSENT]} | {counts[UNMEASURED]} |"
        )
    out.append("")
    out.append(f"**{len(catalog)} manifests** against **{len(names)} targets**.")
    out.append("")

    if gaps:
        out.append("---")
        out.append("")
        out.append("## Resolves to apt, and the archive does not have it")
        out.append("")
        out.append(
            "Each of these is an honest gap the engine reports at plan time rather "
            "than a defect. Where a manifest expects it, its install note says so."
        )
        out.append("")
        out.append(
            "**A package behind a third-party repository appears here and is not a "
            "gap.** The sweep measures each target's stock archive; it does not add "
            "the repositories a manifest declares in `apt_repos`, because adding one "
            "is a system modification that must be shown to the operator before it "
            "happens. `code` and `codium` are the two in this catalog and they are "
            "why this paragraph exists."
        )
        out.append("")
        out.append("| Package | Target | Missing apt package(s) |")
        out.append("|---|---|---|")
        for gapped in sorted(gaps):
            for where in sorted(gaps[gapped]):
                names_missing = ", ".join(f"`{p}`" for p in gaps[gapped][where])
                out.append(f"| `{gapped}` | {where} | {names_missing} |")
        out.append("")

    out.append("---")
    out.append("")
    out.append("## Every manifest")
    out.append("")
    out.append("| Package | " + " | ".join(n for n, _ in names) + " |")
    out.append("|---" * (len(names) + 1) + "|")
    for listed in sorted(rows):
        out.append(f"| `{listed}` | " + " | ".join(rows[listed][n] for n, _ in names) + " |")
    out.append("")
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if out of date")
    parser.add_argument(
        "--package-list",
        action="store_true",
        help="print every apt package name the catalog references, for the sweep",
    )
    args = parser.parse_args()

    catalog = load_catalog(CATALOG)
    if args.package_list:
        print("\n".join(apt_names(catalog)))
        return 0

    body = render(catalog)
    if args.check:
        if not OUT.exists() or _without_date(OUT.read_text()) != _without_date(body):
            print(f"{OUT.relative_to(REPO_ROOT)} is out of date; regenerate it")
            return 1
        print(f"{OUT.relative_to(REPO_ROOT)} is up to date")
        return 0
    OUT.write_text(body)
    print(f"wrote {OUT.relative_to(REPO_ROOT)}")
    return 0


GENERATED_LINE = re.compile(r"^\*\*Generated:\*\*")


def _without_date(text: str) -> list[str]:
    """Compare content, not the day it was written."""
    return [ln for ln in text.splitlines() if not GENERATED_LINE.match(ln)]


if __name__ == "__main__":
    raise SystemExit(main())
